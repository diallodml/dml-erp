"""
Annulation des saisies erronees.

REGLE : on n'efface jamais, on annule. L'operation reste visible avec son
motif et son auteur. C'est ce qui distingue une correction legitime d'une
manipulation.

REGLE D'ACCES : l'agent corrige ses erreurs du jour ; au-dela, seule la
direction peut annuler. Sans cette limite, on decouvre des annulations sur
des operations d'il y a trois semaines.
"""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import (
    AvanceCollecteur,
    Collecte,
    LigneCollecte,
    Lot,
    MouvementStock,
    Utilisateur,
)
from app.models.enums import (
    TypeAction,
    SensMouvement,
    StatutAvanceCollecteur,
    StatutCollecte,
    TypeMouvementStock,
)
from app.repositories.audit import tracer
from app.repositories.collecte import _recalculer_totaux, prochain_numero


def _verifier_droit(
    utilisateur: Utilisateur, date_operation, code_permission: str
) -> None:
    """
    L'agent annule le jour meme. Au-dela, il faut la direction.
    """
    if getattr(utilisateur, "is_superadmin", False):
        return

    permissions = {p.code for r in utilisateur.roles for p in r.permissions}
    if "annulation.ancienne" in permissions:
        return

    if code_permission not in permissions:
        raise PermissionError("Vous n'avez pas le droit d'annuler cette operation")

    jour = date_operation
    if isinstance(jour, datetime):
        jour = jour.date()
    if jour != date.today():
        raise PermissionError(
            "Cette operation ne date pas d'aujourd'hui : "
            "seule la direction peut l'annuler"
        )


def annuler_avance(
    db: Session, avance_id: UUID, motif: str, utilisateur: Utilisateur
) -> dict:
    """
    Annule une avance. Impossible si elle a deja servi a justifier des achats.
    """
    a = db.get(AvanceCollecteur, avance_id)
    if a is None:
        raise ValueError("Avance introuvable")
    if a.is_deleted:
        raise ValueError("Avance deja annulee")
    if (a.montant_justifie or Decimal("0")) > 0:
        raise ValueError(
            "Cette avance a deja justifie des achats : "
            "annulez d'abord la collecte concernee"
        )

    _verifier_droit(utilisateur, a.date_remise, "annulation.avance")

    a.is_deleted = True
    a.deleted_at = datetime.now(timezone.utc)
    a.deleted_reason = motif
    a.statut = StatutAvanceCollecteur.LITIGIEUSE
    a.montant_reste_du = Decimal("0")
    a.updated_by_id = utilisateur.id
    tracer(db, utilisateur, TypeAction.SUPPRIMER, "avances_collecteur", a.id,
           avant={"numero": a.numero, "montant": a.montant_remis},
           commentaire=motif)
    db.commit()
    return {"numero": a.numero, "message": "Avance annulee"}


def annuler_ligne(
    db: Session, ligne_id: UUID, motif: str, utilisateur: Utilisateur
) -> dict:
    """Supprime une ligne d'achat mal saisie et recalcule les totaux."""
    l = db.get(LigneCollecte, ligne_id)
    if l is None:
        raise ValueError("Ligne introuvable")

    collecte = db.get(Collecte, l.collecte_id)
    if collecte.statut != StatutCollecte.EN_COURS:
        raise ValueError(
            "La collecte est deja receptionnee : annulez d'abord la reception"
        )

    _verifier_droit(utilisateur, l.date_achat, "annulation.ligne")

    numero = l.numero_ligne
    tracer(db, utilisateur, TypeAction.SUPPRIMER, "lignes_collecte", l.id,
           avant={"ligne": l.numero_ligne, "sacs": l.nombre_sacs,
                  "montant": l.montant, "collecte": collecte.numero},
           commentaire=motif)
    db.delete(l)
    db.flush()
    _recalculer_totaux(db, collecte)
    db.commit()
    return {
        "message": f"Ligne {numero} supprimee",
        "nouveau_total": collecte.montant_achat_total,
        "nouveaux_sacs": collecte.nombre_sacs_total,
    }


def annuler_reception(
    db: Session, collecte_id: UUID, motif: str, utilisateur: Utilisateur
) -> dict:
    """
    Revient sur une pesee erronee.

    Impossible si la marchandise est deja entree en stock : il faudrait
    alors extourner le mouvement, ce qui se fait separement.
    """
    c = db.get(Collecte, collecte_id)
    if c is None:
        raise ValueError("Collecte introuvable")
    if c.statut != StatutCollecte.RECEPTIONNEE:
        raise ValueError("Cette collecte n'est pas receptionnee")

    lot = db.query(Lot).filter(Lot.collecte_id == c.id).first()
    if lot is not None:
        raise ValueError(
            f"Le lot {lot.numero} a deja ete cree : extournez-le d'abord"
        )

    _verifier_droit(utilisateur, c.date_reception_magasin, "annulation.reception")

    poids_avant = c.poids_reel_kg
    ecart_avant = c.ecart_poids_kg
    humidite_avant = c.taux_humidite_magasin

    # Rendre l'avance a son etat anterieur
    if c.avance_id:
        avance = db.get(AvanceCollecteur, c.avance_id)
        if avance is not None:
            avance.montant_justifie = max(
                Decimal("0"),
                (avance.montant_justifie or Decimal("0")) - c.montant_achat_total,
            )
            avance.recalculer_apurement()

    c.statut = StatutCollecte.EN_COURS
    c.poids_reel_kg = None
    c.nombre_sacs_recus = None
    c.nombre_sacs_expedies = None
    c.ecart_poids_kg = None
    c.ecart_sacs = None
    c.taux_humidite_magasin = None
    c.taux_impuretes_magasin = None
    c.date_reception_magasin = None
    c.magasin_destination_id = None
    c.observations = ((c.observations or "") + f"\nReception annulee : {motif}").strip()
    c.updated_by_id = utilisateur.id
    tracer(db, utilisateur, TypeAction.SUPPRIMER, "collectes", c.id,
           avant={"numero": c.numero, "poids_reel": poids_avant,
                  "ecart": ecart_avant, "humidite": humidite_avant},
           commentaire=motif)
    db.commit()
    return {"numero": c.numero, "message": "Reception annulee, collecte rouverte"}


def extourner_lot(
    db: Session, lot_id: UUID, motif: str, utilisateur: Utilisateur
) -> dict:
    """
    Sort du stock un lot cree par erreur.

    Le stock est un registre append-only : on n'efface pas le mouvement
    d'entree, on ecrit un mouvement inverse. L'historique reste lisible.
    """
    lot = db.get(Lot, lot_id)
    if lot is None:
        raise ValueError("Lot introuvable")
    if lot.quantite_disponible != lot.quantite_initiale:
        raise ValueError(
            "Ce lot a deja bouge (livraison ou traitement) : "
            "impossible de l'extourner"
        )

    _verifier_droit(utilisateur, lot.date_entree, "annulation.stock")

    entree = (
        db.query(MouvementStock)
        .filter(
            MouvementStock.lot_id == lot.id,
            MouvementStock.sens == SensMouvement.ENTREE,
        )
        .order_by(MouvementStock.date_mouvement)
        .first()
    )

    inverse = MouvementStock(
        numero=prochain_numero(db, MouvementStock, "MVT"),
        type_mouvement=TypeMouvementStock.SORTIE_AJUSTEMENT,
        sens=SensMouvement.SORTIE,
        date_mouvement=datetime.now(timezone.utc),
        produit_id=lot.produit_id,
        lot_id=lot.id,
        magasin_source_id=lot.magasin_id,
        quantite=lot.quantite_disponible,
        unite=lot.unite,
        cout_unitaire=lot.cout_unitaire,
        motif=f"Extourne : {motif}",
        mouvement_extourne_id=entree.id if entree else None,
        created_by_id=utilisateur.id,
    )
    db.add(inverse)

    lot.quantite_disponible = Decimal("0")
    lot.is_deleted = True
    lot.deleted_at = datetime.now(timezone.utc)
    lot.deleted_reason = motif
    tracer(db, utilisateur, TypeAction.SUPPRIMER, "lots", lot.id,
           avant={"numero": lot.numero, "quantite": lot.quantite_initiale,
                  "valeur": lot.valeur_stock},
           commentaire=motif)
    db.commit()
    return {
        "lot": lot.numero,
        "mouvement_inverse": inverse.numero,
        "message": "Lot extourne, stock remis a zero",
    }

"""
Vente a l'industriel et reversement au collecteur.

REGLE DE REVERSEMENT (validee avec la direction) :
- La part DML est la marge fixe convenue x tonnage livre.
- Tout ecart de prix a la hausse reste chez DML.
- L'avance non justifiee est proposee en compensation, mais reste
  modifiable a la saisie : la personne voit ce qu'elle laisse passer.
- On reverse a CHAQUE livraison, pas a l'epuisement du lot : les
  collecteurs travaillent avec peu de tresorerie.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    AvanceCollecteur,
    Collecte,
    Collecteur,
    Lot,
    MouvementStock,
    ReversementCollecteur,
    Utilisateur,
)
from app.models.enums import (
    ModeDetention,
    SensMouvement,
    StatutAvanceCollecteur,
    StatutReversement,
    TypeMouvementStock,
    UniteMesure,
)
from app.repositories.collecte import prochain_numero


def solde_avances(db: Session, collecteur_id: UUID) -> Decimal:
    """Total non justifie, tous documents confondus."""
    total = (
        db.query(func.coalesce(func.sum(AvanceCollecteur.montant_reste_du), 0))
        .filter(
            AvanceCollecteur.collecteur_id == collecteur_id,
            AvanceCollecteur.statut != StatutAvanceCollecteur.APUREE,
        )
        .scalar()
    )
    return Decimal(total or 0)


def livrer(db: Session, donnees, utilisateur: Utilisateur) -> dict:
    """
    Sort la marchandise du lot et calcule ce qui revient au collecteur.

    Le reversement n'est PAS paye ici : il est calcule et mis en attente.
    Separer le calcul du paiement permet de verifier avant de sortir
    l'argent.
    """
    lot = db.get(Lot, donnees.lot_id)
    if lot is None:
        raise ValueError("Lot introuvable")
    if donnees.quantite_kg > lot.quantite_disponible:
        raise ValueError(
            f"Stock insuffisant : {lot.quantite_disponible} kg disponibles"
        )

    mouvement = MouvementStock(
        numero=prochain_numero(db, MouvementStock, "MVT"),
        type_mouvement=TypeMouvementStock.SORTIE_VENTE,
        sens=SensMouvement.SORTIE,
        date_mouvement=donnees.date_livraison,
        produit_id=lot.produit_id,
        lot_id=lot.id,
        magasin_source_id=lot.magasin_id,
        quantite=donnees.quantite_kg,
        unite=UniteMesure.KG,
        cout_unitaire=lot.cout_unitaire,
        created_by_id=utilisateur.id,
    )
    # Informations de livraison, reprises sur le bon
    parties = [
        donnees.client_nom,
        donnees.lieu_livraison,
        donnees.transporteur,
        donnees.immatriculation,
        donnees.telephone_chauffeur,
    ]
    mouvement.observations = "|".join(p or "" for p in parties)
    db.add(mouvement)

    lot.quantite_disponible = lot.quantite_disponible - donnees.quantite_kg

    tonnage = donnees.quantite_kg / Decimal("1000")
    montant_vente = donnees.montant_vente

    collecte = db.get(Collecte, lot.collecte_id) if lot.collecte_id else None
    reversement = None

    if collecte is not None and lot.collecteur_id is not None:
        if collecte.mode_detention == ModeDetention.CONSIGNATION_POURCENTAGE:
            taux = collecte.taux_commission_applique or Decimal("0")
            part_dml = (montant_vente * taux).quantize(Decimal("0.01"))
        else:
            marge = collecte.marge_fixe_tonne_appliquee or Decimal("0")
            part_dml = (tonnage * marge).quantize(Decimal("0.01"))

        compensation = donnees.avance_compensee
        if compensation is None:
            frais = donnees.frais_deduits or Decimal("0")
            disponible = montant_vente - part_dml - frais
            compensation = min(
                solde_avances(db, lot.collecteur_id),
                max(Decimal("0"), disponible),
            )
        compensation = max(Decimal("0"), compensation)

        reversement = ReversementCollecteur(
            numero=prochain_numero(db, ReversementCollecteur, "REV"),
            collecteur_id=lot.collecteur_id,
            collecte_id=collecte.id,
            mode_detention=collecte.mode_detention,
            tonnage_vendu=tonnage,
            montant_vente_brut=montant_vente,
            part_dml=part_dml,
            frais_deduits=donnees.frais_deduits or Decimal("0"),
            avance_compensee=compensation,
            montant_net_du=Decimal("0"),
            date_calcul=date.today(),
            date_echeance=donnees.date_echeance,
            statut=StatutReversement.A_PAYER,
            created_by_id=utilisateur.id,
        )
        reversement.calculer_net()
        db.add(reversement)

        if compensation > 0:
            _imputer_avances(db, lot.collecteur_id, compensation)

    db.commit()
    db.refresh(lot)

    db.refresh(mouvement)
    resultat = {
        "mouvement_id": str(mouvement.id),
        "lot": lot.numero,
        "quantite_livree_kg": donnees.quantite_kg,
        "reste_en_stock_kg": lot.quantite_disponible,
        "montant_vente": montant_vente,
        "cout_marchandise": (donnees.quantite_kg * lot.cout_unitaire).quantize(Decimal("0.01")),
    }
    if reversement is not None:
        db.refresh(reversement)
        resultat["reversement"] = {
            "numero": reversement.numero,
            "part_dml": reversement.part_dml,
            "frais_deduits": reversement.frais_deduits,
            "avance_compensee": reversement.avance_compensee,
            "net_du_collecteur": reversement.montant_net_du,
        }
    return resultat


def _imputer_avances(db: Session, collecteur_id: UUID, montant: Decimal) -> None:
    """Impute la compensation sur les avances les plus anciennes d'abord."""
    restant = montant
    avances = (
        db.query(AvanceCollecteur)
        .filter(
            AvanceCollecteur.collecteur_id == collecteur_id,
            AvanceCollecteur.statut != StatutAvanceCollecteur.APUREE,
        )
        .order_by(AvanceCollecteur.date_remise)
        .all()
    )
    for a in avances:
        if restant <= 0:
            break
        impute = min(restant, a.montant_reste_du)
        a.montant_rendu = (a.montant_rendu or Decimal("0")) + impute
        a.recalculer_apurement()
        restant -= impute


def payer_reversement(
    db: Session, reversement_id: UUID, donnees, utilisateur: Utilisateur
) -> ReversementCollecteur:
    """Sort l'argent et eteint la dette."""
    r = db.get(ReversementCollecteur, reversement_id)
    if r is None:
        raise ValueError("Reversement introuvable")
    if r.statut == StatutReversement.PAYE:
        raise ValueError("Reversement deja paye")

    montant = donnees.montant_paye
    if montant > r.solde_a_payer:
        raise ValueError(
            f"Montant superieur au solde du ({r.solde_a_payer})"
        )

    r.montant_paye = (r.montant_paye or Decimal("0")) + montant
    r.date_paiement = donnees.date_paiement
    r.mode_paiement = donnees.mode_paiement
    r.reference_paiement = donnees.reference_paiement
    r.compte_tresorerie_id = donnees.compte_tresorerie_id
    r.statut = (
        StatutReversement.PAYE
        if r.solde_a_payer <= 0
        else StatutReversement.PARTIEL
    )
    r.updated_by_id = utilisateur.id
    db.commit()
    db.refresh(r)
    return r


def reversements_dus(db: Session) -> List[dict]:
    """Ce que DML doit aux collecteurs, du plus ancien au plus recent."""
    lignes = (
        db.query(ReversementCollecteur, Collecteur.nom)
        .join(Collecteur, Collecteur.id == ReversementCollecteur.collecteur_id)
        .filter(ReversementCollecteur.statut != StatutReversement.PAYE)
        .order_by(ReversementCollecteur.date_calcul)
        .all()
    )
    return [
        {
            "id": str(r.id),
            "numero": r.numero,
            "collecteur": nom,
            "date_calcul": r.date_calcul,
            "date_echeance": r.date_echeance,
            "tonnage": r.tonnage_vendu,
            "vente_brut": r.montant_vente_brut,
            "part_dml": r.part_dml,
            "avance_compensee": r.avance_compensee,
            "net_du": r.montant_net_du,
            "deja_paye": r.montant_paye,
            "solde": r.solde_a_payer,
            "statut": r.statut.value,
        }
        for r, nom in lignes
    ]

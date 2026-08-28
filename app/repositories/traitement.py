"""
Traitement de la marchandise chez un prestataire.

Le lot sort du magasin DML, part chez le tiers, en revient plus leger et
plus sec. Un lot fils est cree avec le poids et le cout reels.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Lot,
    MouvementStock,
    Prestataire,
    Traitement,
    Utilisateur,
)
from app.models.enums import (
    SensMouvement,
    StatutTraitement,
    TypeMouvementStock,
    UniteMesure,
)
from app.repositories.collecte import prochain_numero


def expedier(db: Session, donnees, utilisateur: Utilisateur) -> Traitement:
    """
    Envoie un lot chez le prestataire.

    C'est un TRANSFERT, pas une sortie : la marchandise reste a DML, elle
    change simplement de magasin. On sait toujours ou elle est.
    """
    lot = db.get(Lot, donnees.lot_source_id)
    if lot is None:
        raise ValueError("Lot introuvable")
    if donnees.poids_entree_kg > lot.quantite_disponible:
        raise ValueError(
            f"Stock insuffisant : {lot.quantite_disponible} kg disponibles"
        )

    prestataire = db.get(Prestataire, donnees.prestataire_id)
    if prestataire is None:
        raise ValueError("Prestataire introuvable")
    if prestataire.magasin_id is None:
        raise ValueError(
            "Ce prestataire n'a pas de magasin associe : "
            "creez-lui un magasin de type SOUS_TRAITE"
        )

    sortie = MouvementStock(
        numero=prochain_numero(db, MouvementStock, "MVT"),
        type_mouvement=TypeMouvementStock.SORTIE_TRANSFERT,
        sens=SensMouvement.SORTIE,
        date_mouvement=donnees.date_expedition,
        produit_id=lot.produit_id,
        lot_id=lot.id,
        magasin_source_id=lot.magasin_id,
        magasin_destination_id=prestataire.magasin_id,
        quantite=donnees.poids_entree_kg,
        unite=UniteMesure.KG,
        cout_unitaire=lot.cout_unitaire,
        created_by_id=utilisateur.id,
    )
    db.add(sortie)
    db.flush()

    lot.quantite_disponible = lot.quantite_disponible - donnees.poids_entree_kg

    t = Traitement(
        numero=prochain_numero(db, Traitement, "TRT"),
        prestataire_id=prestataire.id,
        lot_source_id=lot.id,
        statut=StatutTraitement.EXPEDIE,
        type_traitement=donnees.type_traitement,
        date_expedition=donnees.date_expedition,
        date_retour_prevue=donnees.date_retour_prevue,
        poids_entree_kg=donnees.poids_entree_kg,
        humidite_entree=donnees.humidite_entree or lot.taux_humidite_entree,
        impuretes_entree=donnees.impuretes_entree,
        prix_tonne_applique=donnees.prix_tonne_applique or prestataire.prix_tonne,
        base_facturation=donnees.base_facturation or prestataire.base_facturation,
        frais_transport=donnees.frais_transport or Decimal("0"),
        mouvement_sortie_id=sortie.id,
        created_by_id=utilisateur.id,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return t


def receptionner(db: Session, traitement_id: UUID, donnees, utilisateur: Utilisateur):
    """
    Retour du prestataire : pesee, mesure d'humidite, calcul du rendement.

    Cree un lot fils portant le poids et le cout apres traitement. C'est
    ce lot qui sera livre a l'industriel.
    """
    t = db.get(Traitement, traitement_id)
    if t is None:
        raise ValueError("Traitement introuvable")
    if t.statut == StatutTraitement.TERMINE:
        raise ValueError("Traitement deja receptionne")

    t.poids_sortie_kg = donnees.poids_sortie_kg
    t.humidite_sortie = donnees.humidite_sortie
    t.impuretes_sortie = donnees.impuretes_sortie
    t.date_fin = donnees.date_fin
    t.statut = StatutTraitement.TERMINE
    t.updated_by_id = utilisateur.id

    t.evaluer_rendement()
    t.calculer_cout()

    lot_source = db.get(Lot, t.lot_source_id)
    cout_marchandise = t.poids_entree_kg * lot_source.cout_unitaire
    cout_total = cout_marchandise + (t.cout_traitement or Decimal("0")) + t.frais_transport
    cout_unitaire = (cout_total / t.poids_sortie_kg).quantize(Decimal("0.01"))

    prestataire = db.get(Prestataire, t.prestataire_id)

    lot_fils = Lot(
        numero=prochain_numero(db, Lot, "LOT"),
        produit_id=lot_source.produit_id,
        magasin_id=prestataire.magasin_id,
        collecte_id=lot_source.collecte_id,
        collecteur_id=lot_source.collecteur_id,
        mode_detention=lot_source.mode_detention,
        lot_parent_id=lot_source.id,
        quantite_initiale=t.poids_sortie_kg,
        quantite_disponible=t.poids_sortie_kg,
        quantite_reservee=Decimal("0"),
        unite=UniteMesure.KG,
        cout_unitaire=cout_unitaire,
        valeur_stock=cout_total,
        taux_humidite_entree=t.humidite_sortie,
        taux_impuretes_entree=t.impuretes_sortie,
        campagne_agricole=lot_source.campagne_agricole,
    )
    db.add(lot_fils)
    db.flush()

    entree = MouvementStock(
        numero=prochain_numero(db, MouvementStock, "MVT"),
        type_mouvement=TypeMouvementStock.ENTREE_PRODUCTION,
        sens=SensMouvement.ENTREE,
        date_mouvement=donnees.date_fin,
        produit_id=lot_source.produit_id,
        lot_id=lot_fils.id,
        magasin_destination_id=prestataire.magasin_id,
        quantite=t.poids_sortie_kg,
        unite=UniteMesure.KG,
        cout_unitaire=cout_unitaire,
        created_by_id=utilisateur.id,
    )
    db.add(entree)
    db.flush()

    t.lot_traite_id = lot_fils.id
    t.mouvement_entree_id = entree.id

    if prestataire is not None:
        prestataire.nb_traitements = (prestataire.nb_traitements or 0) + 1
        prestataire.tonnage_cumule = (
            prestataire.tonnage_cumule or Decimal("0")
        ) + (t.poids_entree_kg / Decimal("1000"))
        prestataire.perte_inexpliquee_cumulee_kg = (
            prestataire.perte_inexpliquee_cumulee_kg or Decimal("0")
        ) + (t.perte_inexpliquee_kg or Decimal("0"))

    db.commit()
    db.refresh(t)

    return {
        "numero": t.numero,
        "poids_entree_kg": t.poids_entree_kg,
        "poids_sortie_kg": t.poids_sortie_kg,
        "perte_reelle_kg": t.perte_reelle_kg,
        "perte_theorique_kg": t.perte_theorique_kg,
        "perte_inexpliquee_kg": t.perte_inexpliquee_kg,
        "rendement_pct": t.rendement_pct,
        "niveau_alerte": t.niveau_alerte.value if t.niveau_alerte else None,
        "cout_traitement": t.cout_traitement,
        "lot_traite": lot_fils.numero,
        "cout_unitaire_avant": lot_source.cout_unitaire,
        "cout_unitaire_apres": cout_unitaire,
    }


def rendements_prestataires(db: Session) -> List[dict]:
    """Qui traite bien, qui perd de la marchandise."""
    lignes = (
        db.query(
            Prestataire.id,
            Prestataire.nom,
            func.count(Traitement.id).label("nb"),
            func.coalesce(func.sum(Traitement.poids_entree_kg), 0).label("entree"),
            func.coalesce(func.sum(Traitement.poids_sortie_kg), 0).label("sortie"),
            func.coalesce(func.sum(Traitement.perte_theorique_kg), 0).label("theo"),
            func.coalesce(func.sum(Traitement.perte_inexpliquee_kg), 0).label("inexp"),
        )
        .join(Traitement, Traitement.prestataire_id == Prestataire.id)
        .filter(Traitement.statut == StatutTraitement.TERMINE)
        .group_by(Prestataire.id, Prestataire.nom)
        .order_by(func.sum(Traitement.perte_inexpliquee_kg).desc())
        .all()
    )
    return [
        {
            "prestataire_id": str(l.id),
            "nom": l.nom,
            "nb_traitements": l.nb,
            "poids_entree_kg": Decimal(l.entree),
            "poids_sortie_kg": Decimal(l.sortie),
            "perte_theorique_kg": Decimal(l.theo),
            "perte_inexpliquee_kg": Decimal(l.inexp),
            "rendement_pct": (
                (Decimal(l.sortie) / Decimal(l.entree) * 100).quantize(Decimal("0.01"))
                if l.entree else None
            ),
        }
        for l in lignes
    ]

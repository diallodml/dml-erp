"""
Rentabilite reelle de l'activite.

Le cout de revient par lot ne compte que l'achat, les frais annexes et le
sechage. Il ignore l'electricite, le carburant, les salaires, le Starlink.

Ce module rapproche les charges generales du tonnage traite : c'est ce qui
dit si l'activite gagne de l'argent, et pas seulement si chaque camion est
rentable.
"""

from calendar import monthrange
from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    CategorieDepense,
    Collecte,
    MouvementStock,
    MouvementTresorerie,
    Traitement,
)
from app.models.enums import (
    SensMouvement,
    SensTresorerie,
    StatutCollecte,
    StatutTraitement,
    TypeMouvementStock,
)


def _bornes(annee: int, mois: Optional[int]):
    if mois:
        debut = date(annee, mois, 1)
        fin = date(annee, mois, monthrange(annee, mois)[1])
    else:
        debut = date(annee, 1, 1)
        fin = date(annee, 12, 31)
    return debut, fin


def rentabilite(db: Session, annee: int, mois: Optional[int] = None) -> dict:
    """
    Compte de resultat simplifie sur une periode.

    Sans pretention comptable : c'est une vue de gestion, adaptee au
    Systeme Minimal de Tresorerie.
    """
    debut, fin = _bornes(annee, mois)

    # --- Ce qui a ete vendu
    ventes = (
        db.query(
            func.coalesce(func.sum(MouvementStock.montant_vente), 0),
            func.coalesce(func.sum(MouvementStock.quantite), 0),
            func.coalesce(func.sum(MouvementStock.quantite * MouvementStock.cout_unitaire), 0),
            func.count(MouvementStock.id),
        )
        .filter(
            MouvementStock.type_mouvement == TypeMouvementStock.SORTIE_VENTE,
            MouvementStock.sens == SensMouvement.SORTIE,
            func.date(MouvementStock.date_mouvement) >= debut,
            func.date(MouvementStock.date_mouvement) <= fin,
        )
        .first()
    )
    ca = Decimal(ventes[0] or 0)
    kg_vendus = Decimal(ventes[1] or 0)
    cout_marchandise = Decimal(ventes[2] or 0)
    nb_livraisons = ventes[3] or 0

    # --- Ce qui a ete collecte
    collectes = (
        db.query(
            func.coalesce(func.sum(Collecte.poids_reel_kg), 0),
            func.coalesce(func.sum(Collecte.ecart_poids_kg), 0),
            func.count(Collecte.id),
        )
        .filter(
            Collecte.statut == StatutCollecte.RECEPTIONNEE,
            Collecte.date_debut >= debut,
            Collecte.date_debut <= fin,
        )
        .first()
    )
    kg_collectes = Decimal(collectes[0] or 0)
    ecart_kg = Decimal(collectes[1] or 0)
    nb_collectes = collectes[2] or 0

    # --- Perte inexpliquee au traitement
    perte_traitement = Decimal(
        db.query(func.coalesce(func.sum(Traitement.perte_inexpliquee_kg), 0))
        .filter(
            Traitement.statut == StatutTraitement.TERMINE,
            func.date(Traitement.date_fin) >= debut,
            func.date(Traitement.date_fin) <= fin,
        )
        .scalar() or 0
    )

    # --- Les charges generales, par poste
    postes = (
        db.query(
            CategorieDepense.libelle,
            func.coalesce(func.sum(MouvementTresorerie.montant), 0).label("total"),
        )
        .join(MouvementTresorerie,
              MouvementTresorerie.categorie_depense_id == CategorieDepense.id)
        .filter(
            MouvementTresorerie.sens == SensTresorerie.DECAISSEMENT,
            MouvementTresorerie.date_mouvement >= debut,
            MouvementTresorerie.date_mouvement <= fin,
        )
        .group_by(CategorieDepense.libelle)
        .order_by(func.sum(MouvementTresorerie.montant).desc())
        .all()
    )
    charges_totales = sum((Decimal(p.total) for p in postes), Decimal("0"))

    marge_brute = ca - cout_marchandise
    resultat = marge_brute - charges_totales

    # Ce que chaque kilo supporte vraiment
    base_kg = kg_vendus or kg_collectes
    charge_par_kg = (charges_totales / base_kg).quantize(Decimal("0.01")) if base_kg else None
    marge_par_kg = (marge_brute / kg_vendus).quantize(Decimal("0.01")) if kg_vendus else None

    return {
        "periode": {
            "debut": debut,
            "fin": fin,
            "libelle": f"{mois:02d}/{annee}" if mois else str(annee),
        },
        "activite": {
            "nb_collectes": nb_collectes,
            "kg_collectes": kg_collectes,
            "ecart_collecte_kg": ecart_kg,
            "perte_traitement_kg": perte_traitement,
            "nb_livraisons": nb_livraisons,
            "kg_vendus": kg_vendus,
        },
        "resultat": {
            "chiffre_affaires": ca,
            "cout_marchandise": cout_marchandise,
            "marge_brute": marge_brute,
            "charges_generales": charges_totales,
            "resultat_net": resultat,
            "taux_marge": (marge_brute / ca * 100).quantize(Decimal("0.01")) if ca else None,
            "taux_resultat": (resultat / ca * 100).quantize(Decimal("0.01")) if ca else None,
        },
        "au_kilo": {
            "charge_par_kg": charge_par_kg,
            "marge_par_kg": marge_par_kg,
            "resultat_par_kg": (
                (marge_par_kg - charge_par_kg)
                if marge_par_kg is not None and charge_par_kg is not None else None
            ),
        },
        "charges": [
            {
                "libelle": p.libelle,
                "montant": Decimal(p.total),
                "part": (Decimal(p.total) / charges_totales * 100).quantize(Decimal("0.1"))
                    if charges_totales else Decimal("0"),
                "par_kg": (Decimal(p.total) / base_kg).quantize(Decimal("0.01"))
                    if base_kg else None,
            }
            for p in postes
        ],
    }

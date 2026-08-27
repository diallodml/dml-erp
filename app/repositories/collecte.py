"""
Repository du module Collecte.

REGLE : toute lecture passe par le filtre de portee. Les routes n'appellent
jamais db.query() directement.
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
    LigneCollecte,
    Utilisateur,
)
from app.models.enums import StatutAvanceCollecteur, StatutCollecte
from app.repositories.portee import appliquer_portee


# ---------------------------------------------------------------------------
# NUMEROTATION
# ---------------------------------------------------------------------------
def prochain_numero(db: Session, modele, prefixe: str) -> str:
    """Genere AV-2026-0001, COL-2026-0001... par annee civile."""
    annee = date.today().year
    debut = f"{prefixe}-{annee}-"
    dernier = (
        db.query(modele.numero)
        .filter(modele.numero.like(f"{debut}%"))
        .order_by(modele.numero.desc())
        .first()
    )
    suivant = int(dernier[0].split("-")[-1]) + 1 if dernier else 1
    return f"{debut}{suivant:04d}"


# ---------------------------------------------------------------------------
# AVANCES
# ---------------------------------------------------------------------------
def creer_avance(
    db: Session, donnees, utilisateur: Utilisateur
) -> AvanceCollecteur:
    """
    Remet une avance a un collecteur.

    Controle du plafond : au-dela, on refuse. C'est le garde-fou le plus
    simple contre l'accumulation d'avances non justifiees.
    """
    collecteur = db.get(Collecteur, donnees.collecteur_id)
    if collecteur is None:
        raise ValueError("Collecteur introuvable")

    encours = (
        db.query(func.coalesce(func.sum(AvanceCollecteur.montant_reste_du), 0))
        .filter(
            AvanceCollecteur.collecteur_id == collecteur.id,
            AvanceCollecteur.statut != StatutAvanceCollecteur.APUREE,
        )
        .scalar()
    )

    if collecteur.plafond_avance is not None:
        total = Decimal(encours) + donnees.montant_remis
        if total > collecteur.plafond_avance:
            raise ValueError(
                f"Plafond depasse : encours {encours} + {donnees.montant_remis} "
                f"> plafond {collecteur.plafond_avance}"
            )

    avance = AvanceCollecteur(
        numero=prochain_numero(db, AvanceCollecteur, "AV"),
        collecteur_id=donnees.collecteur_id,
        date_remise=donnees.date_remise,
        montant_remis=donnees.montant_remis,
        montant_reste_du=donnees.montant_remis,
        mode_remise=donnees.mode_remise,
        compte_tresorerie_id=donnees.compte_tresorerie_id,
        zone_prevue_id=donnees.zone_prevue_id,
        objet=donnees.objet,
        observations=donnees.observations,
        remis_par_id=utilisateur.id,
        created_by_id=utilisateur.id,
    )
    db.add(avance)
    db.commit()
    db.refresh(avance)
    return avance


def soldes_collecteurs(db: Session) -> List[dict]:
    """Combien chaque collecteur doit-il ? Trie par montant du, decroissant."""
    lignes = (
        db.query(
            Collecteur.id,
            Collecteur.nom,
            func.coalesce(func.sum(AvanceCollecteur.montant_remis), 0).label("remis"),
            func.coalesce(func.sum(AvanceCollecteur.montant_justifie), 0).label("justifie"),
            func.coalesce(func.sum(AvanceCollecteur.montant_reste_du), 0).label("reste"),
            func.count(AvanceCollecteur.id).label("nb"),
        )
        .join(AvanceCollecteur, AvanceCollecteur.collecteur_id == Collecteur.id)
        .filter(AvanceCollecteur.statut != StatutAvanceCollecteur.APUREE)
        .group_by(Collecteur.id, Collecteur.nom)
        .order_by(func.sum(AvanceCollecteur.montant_reste_du).desc())
        .all()
    )
    return [
        {
            "collecteur_id": l.id,
            "nom": l.nom,
            "total_avance": Decimal(l.remis),
            "total_justifie": Decimal(l.justifie),
            "reste_du": Decimal(l.reste),
            "nb_avances_ouvertes": l.nb,
        }
        for l in lignes
    ]


# ---------------------------------------------------------------------------
# COLLECTES
# ---------------------------------------------------------------------------
def creer_collecte(db: Session, donnees, utilisateur: Utilisateur) -> Collecte:
    """
    Ouvre une collecte. Le mode de detention se fige ICI et ne change plus.
    """
    collecte = Collecte(
        numero=prochain_numero(db, Collecte, "COL"),
        collecteur_id=donnees.collecteur_id,
        zone_id=donnees.zone_id,
        avance_id=donnees.avance_id,
        contrat_id=donnees.contrat_id,
        date_debut=donnees.date_debut,
        mode_detention=donnees.mode_detention,
        marge_fixe_tonne_appliquee=donnees.marge_fixe_tonne_appliquee,
        taux_commission_applique=donnees.taux_commission_applique,
        magasin_destination_id=donnees.magasin_destination_id,
        campagne_agricole=donnees.campagne_agricole,
        frais_annexes=donnees.frais_annexes,
        observations=donnees.observations,
        created_by_id=utilisateur.id,
    )
    db.add(collecte)
    db.commit()
    db.refresh(collecte)
    return collecte


def ajouter_ligne(
    db: Session, collecte_id: UUID, donnees, utilisateur: Utilisateur
) -> LigneCollecte:
    """
    Enregistre un achat au marche et met a jour les totaux de la collecte.

    Le poids theorique est ce que DML CROIT avoir achete (nb sacs x poids
    nominal). Le poids reel viendra a la pesee. L'ecart est le chiffre utile.
    """
    collecte = db.get(Collecte, collecte_id)
    if collecte is None:
        raise ValueError("Collecte introuvable")
    if collecte.statut != StatutCollecte.EN_COURS:
        raise ValueError("Collecte cloturee : saisie impossible")

    dernier = (
        db.query(func.coalesce(func.max(LigneCollecte.numero_ligne), 0))
        .filter(LigneCollecte.collecte_id == collecte_id)
        .scalar()
    )

    ligne = LigneCollecte(
        collecte_id=collecte_id,
        numero_ligne=dernier + 1,
        produit_id=donnees.produit_id,
        date_achat=donnees.date_achat,
        base_achat=donnees.base_achat,
        nombre_sacs=donnees.nombre_sacs,
        poids_nominal_sac_kg=donnees.poids_nominal_sac_kg,
        quantite_kg=donnees.quantite_kg,
        prix_unitaire=donnees.prix_unitaire,
        montant=Decimal("0"),
        nom_vendeur=donnees.nom_vendeur,
        telephone_vendeur=donnees.telephone_vendeur,
        appreciation_qualite=donnees.appreciation_qualite,
        taux_humidite_marche=donnees.taux_humidite_marche,
        observations=donnees.observations,
    )
    ligne.calculer_montant()
    db.add(ligne)
    db.flush()

    _recalculer_totaux(db, collecte)
    db.commit()
    db.refresh(ligne)
    return ligne


def _recalculer_totaux(db: Session, collecte: Collecte) -> None:
    """Recalcule sacs, poids theorique et montant depuis les lignes."""
    lignes = (
        db.query(LigneCollecte)
        .filter(LigneCollecte.collecte_id == collecte.id)
        .all()
    )
    collecte.nombre_sacs_total = sum(l.nombre_sacs or 0 for l in lignes)
    collecte.poids_theorique_kg = sum(
        (l.poids_theorique() for l in lignes), Decimal("0.000")
    )
    collecte.montant_achat_total = sum(
        (l.montant for l in lignes), Decimal("0.00")
    )


def receptionner(
    db: Session, collecte_id: UUID, donnees, utilisateur: Utilisateur
) -> Collecte:
    """
    Arrivee au magasin : pesee reelle et calcul de l'ecart.

    C'est le moment de verite. L'ecart entre le poids paye et le poids recu
    dit, collecteur par collecteur, qui achete bien.
    """
    collecte = db.get(Collecte, collecte_id)
    if collecte is None:
        raise ValueError("Collecte introuvable")
    if collecte.statut == StatutCollecte.RECEPTIONNEE:
        raise ValueError("Collecte deja receptionnee")

    collecte.magasin_destination_id = donnees.magasin_destination_id
    collecte.date_reception_magasin = donnees.date_reception_magasin
    collecte.nombre_sacs_expedies = (
        donnees.nombre_sacs_expedies or collecte.nombre_sacs_total
    )
    collecte.nombre_sacs_recus = donnees.nombre_sacs_recus
    collecte.poids_reel_kg = donnees.poids_reel_kg
    collecte.taux_humidite_magasin = donnees.taux_humidite_magasin
    collecte.taux_impuretes_magasin = donnees.taux_impuretes_magasin
    collecte.voyage_id = donnees.voyage_id
    collecte.statut = StatutCollecte.RECEPTIONNEE
    collecte.updated_by_id = utilisateur.id

    collecte.calculer_ecart_poids()

    collecteur = db.get(Collecteur, collecte.collecteur_id)
    if collecteur is not None:
        collecteur.nb_collectes = (collecteur.nb_collectes or 0) + 1
        collecteur.tonnage_cumule = (
            collecteur.tonnage_cumule or Decimal("0")
        ) + (collecte.poids_reel_kg / Decimal("1000"))
        collecteur.ecart_poids_cumule_kg = (
            collecteur.ecart_poids_cumule_kg or Decimal("0")
        ) + (collecte.ecart_poids_kg or Decimal("0"))
        collecteur.date_derniere_collecte = donnees.date_reception_magasin.date()

    if collecte.avance_id:
        avance = db.get(AvanceCollecteur, collecte.avance_id)
        if avance is not None:
            avance.montant_justifie = (
                avance.montant_justifie or Decimal("0")
            ) + collecte.montant_achat_total
            avance.recalculer_apurement()

    db.commit()
    db.refresh(collecte)
    return collecte


def ecarts_collecteurs(
    db: Session, depuis: Optional[date] = None
) -> List[dict]:
    """Qui me coute de l'argent ? Trie du pire au meilleur."""
    q = (
        db.query(
            Collecteur.id,
            Collecteur.nom,
            func.count(Collecte.id).label("nb"),
            func.coalesce(func.sum(Collecte.poids_theorique_kg), 0).label("theo"),
            func.coalesce(func.sum(Collecte.poids_reel_kg), 0).label("reel"),
            func.coalesce(func.sum(Collecte.ecart_poids_kg), 0).label("ecart"),
            func.coalesce(func.sum(Collecte.montant_achat_total), 0).label("montant"),
        )
        .join(Collecte, Collecte.collecteur_id == Collecteur.id)
        .filter(Collecte.statut == StatutCollecte.RECEPTIONNEE)
    )
    if depuis:
        q = q.filter(Collecte.date_debut >= depuis)

    lignes = (
        q.group_by(Collecteur.id, Collecteur.nom)
        .order_by(func.sum(Collecte.ecart_poids_kg).asc())
        .all()
    )

    resultats = []
    for l in lignes:
        theo = Decimal(l.theo)
        ecart = Decimal(l.ecart)
        pct = (ecart / theo * 100).quantize(Decimal("0.01")) if theo else None
        prix_kg = (Decimal(l.montant) / theo) if theo else Decimal("0")
        resultats.append(
            {
                "collecteur_id": l.id,
                "nom": l.nom,
                "nb_collectes": l.nb,
                "poids_theorique_kg": theo,
                "poids_reel_kg": Decimal(l.reel),
                "ecart_kg": ecart,
                "ecart_pourcentage": pct,
                "valeur_ecart": (ecart * prix_kg).quantize(Decimal("0.01")),
            }
        )
    return resultats

"""
Tresorerie : caisses, banques, Mobile Money, et charges courantes.

Deux regles structurantes
-------------------------
1. LE SOLDE NE PEUT PAS DEVENIR NEGATIF sur une caisse physique.
   Une caisse qui contient 150 000 F ne peut pas en sortir 200 000.
   C'est le premier controle de tresorerie, et il evite les caisses
   fantomes.

2. CHAQUE MOUVEMENT PORTE SON TIROIR.
   Entreprise ou compte courant de l'associe. Sans cette distinction,
   impossible de savoir en fin d'annee ce que l'entreprise doit au
   dirigeant -- ou l'inverse.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    CategorieDepense,
    CompteTresorerie,
    MouvementTresorerie,
    Utilisateur,
)
from app.models.enums import SensTresorerie, Tiroir, TypeCompteTresorerie
from app.repositories.collecte import prochain_numero

# Une caisse ou un portefeuille Mobile Money ne peut pas etre a decouvert.
# Une banque, si.
SANS_DECOUVERT = {
    TypeCompteTresorerie.CAISSE,
    TypeCompteTresorerie.COFFRE,
    TypeCompteTresorerie.MOBILE_MONEY,
    TypeCompteTresorerie.CAISSE_CHAUFFEUR,
}


def creer_compte(db: Session, donnees, utilisateur: Utilisateur) -> CompteTresorerie:
    if db.query(CompteTresorerie).filter(
        CompteTresorerie.code == donnees.code
    ).first():
        raise ValueError(f"Le code {donnees.code} existe deja")

    c = CompteTresorerie(
        code=donnees.code,
        libelle=donnees.libelle,
        type_compte=donnees.type_compte,
        tiroir=donnees.tiroir,
        nom_banque=donnees.nom_banque,
        numero_compte=donnees.numero_compte,
        operateur_mm=donnees.operateur_mm,
        numero_telephone=donnees.numero_telephone,
        solde_initial=donnees.solde_initial or Decimal("0"),
        solde_actuel=donnees.solde_initial or Decimal("0"),
        solde_theorique=donnees.solde_initial or Decimal("0"),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def enregistrer_mouvement(
    db: Session, donnees, utilisateur: Utilisateur
) -> MouvementTresorerie:
    """
    Enregistre une entree ou une sortie d'argent et met a jour le solde.
    """
    compte = db.get(CompteTresorerie, donnees.compte_tresorerie_id)
    if compte is None:
        raise ValueError("Compte de tresorerie introuvable")

    montant = donnees.montant
    if donnees.sens == SensTresorerie.DECAISSEMENT:
        if compte.type_compte in SANS_DECOUVERT and montant > compte.solde_actuel:
            raise ValueError(
                f"Solde insuffisant : {compte.libelle} contient "
                f"{compte.solde_actuel} F"
            )
        variation = -montant
    else:
        variation = montant

    m = MouvementTresorerie(
        numero=prochain_numero(db, MouvementTresorerie, "TRS"),
        compte_tresorerie_id=compte.id,
        date_mouvement=donnees.date_mouvement or date.today(),
        sens=donnees.sens,
        montant=montant,
        libelle=donnees.libelle,
        tiroir=donnees.tiroir or compte.tiroir,
        mode_reglement=donnees.mode_reglement,
        beneficiaire=donnees.beneficiaire,
        categorie_depense_id=donnees.categorie_depense_id,
        created_by_id=utilisateur.id,
    )
    db.add(m)

    compte.solde_actuel = compte.solde_actuel + variation
    compte.solde_theorique = compte.solde_theorique + variation

    db.commit()
    db.refresh(m)
    return m


def etat_comptes(db: Session) -> List[dict]:
    """Soldes de tous les comptes, groupes par tiroir."""
    comptes = (
        db.query(CompteTresorerie)
        .filter(CompteTresorerie.is_actif.is_(True))
        .order_by(CompteTresorerie.tiroir, CompteTresorerie.libelle)
        .all()
    )
    return [
        {
            "id": str(c.id),
            "code": c.code,
            "libelle": c.libelle,
            "type": c.type_compte.value,
            "tiroir": c.tiroir.value,
            "solde": c.solde_actuel,
            "banque": c.nom_banque,
            "telephone": c.numero_telephone,
        }
        for c in comptes
    ]


def journal(
    db: Session,
    compte_id: Optional[UUID] = None,
    depuis: Optional[date] = None,
    limite: int = 100,
) -> List[dict]:
    """Derniers mouvements, du plus recent au plus ancien."""
    q = (
        db.query(MouvementTresorerie, CompteTresorerie.libelle, CategorieDepense.libelle)
        .join(CompteTresorerie, CompteTresorerie.id == MouvementTresorerie.compte_tresorerie_id)
        .outerjoin(CategorieDepense, CategorieDepense.id == MouvementTresorerie.categorie_depense_id)
    )
    if compte_id:
        q = q.filter(MouvementTresorerie.compte_tresorerie_id == compte_id)
    if depuis:
        q = q.filter(MouvementTresorerie.date_mouvement >= depuis)

    lignes = (
        q.order_by(MouvementTresorerie.date_mouvement.desc(),
                   MouvementTresorerie.numero.desc())
        .limit(limite)
        .all()
    )
    return [
        {
            "numero": m.numero,
            "date": m.date_mouvement,
            "compte": compte,
            "sens": m.sens.value,
            "montant": m.montant,
            "libelle": m.libelle,
            "categorie": categorie or "—",
            "tiroir": m.tiroir.value,
            "beneficiaire": m.beneficiaire,
            "mode": m.mode_reglement.value if m.mode_reglement else None,
        }
        for m, compte, categorie in lignes
    ]


def depenses_par_categorie(
    db: Session, depuis: Optional[date] = None
) -> List[dict]:
    """
    Ce que l'entreprise depense, par poste.

    C'est ce qui repond a : combien me coute l'electricite par mois ?
    """
    q = (
        db.query(
            CategorieDepense.code,
            CategorieDepense.libelle,
            func.count(MouvementTresorerie.id).label("nb"),
            func.coalesce(func.sum(MouvementTresorerie.montant), 0).label("total"),
        )
        .join(MouvementTresorerie,
              MouvementTresorerie.categorie_depense_id == CategorieDepense.id)
        .filter(MouvementTresorerie.sens == SensTresorerie.DECAISSEMENT)
    )
    if depuis:
        q = q.filter(MouvementTresorerie.date_mouvement >= depuis)

    lignes = (
        q.group_by(CategorieDepense.code, CategorieDepense.libelle)
        .order_by(func.sum(MouvementTresorerie.montant).desc())
        .all()
    )
    return [
        {
            "code": l.code,
            "libelle": l.libelle,
            "nb_operations": l.nb,
            "total": Decimal(l.total),
        }
        for l in lignes
    ]

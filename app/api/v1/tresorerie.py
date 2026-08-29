"""Routes de tresorerie : comptes, mouvements, charges courantes."""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import exiger_permission, get_db, utilisateur_courant
from app.models import Utilisateur
from app.models.enums import (
    ModeReglement,
    OperateurMobileMoney,
    SensTresorerie,
    Tiroir,
    TypeCompteTresorerie,
)
from app.repositories import tresorerie as repo

router = APIRouter(prefix="/api/v1/tresorerie", tags=["Tresorerie"])


class CompteCreer(BaseModel):
    code: str = Field(max_length=30)
    libelle: str = Field(max_length=150)
    type_compte: TypeCompteTresorerie
    tiroir: Tiroir = Tiroir.ENTREPRISE
    solde_initial: Optional[Decimal] = Field(default=None, ge=0)
    nom_banque: Optional[str] = Field(default=None, max_length=150)
    numero_compte: Optional[str] = Field(default=None, max_length=60)
    operateur_mm: Optional[OperateurMobileMoney] = None
    numero_telephone: Optional[str] = Field(default=None, max_length=30)


class MouvementCreer(BaseModel):
    compte_tresorerie_id: UUID
    sens: SensTresorerie
    montant: Decimal = Field(gt=0)
    libelle: str = Field(max_length=255)
    date_mouvement: Optional[date] = None
    tiroir: Optional[Tiroir] = None
    mode_reglement: Optional[ModeReglement] = None
    beneficiaire: Optional[str] = Field(default=None, max_length=200)
    categorie_depense_id: Optional[UUID] = None


class CategorieCreer(BaseModel):
    code: str = Field(max_length=30)
    libelle: str = Field(max_length=150)
    exige_justificatif: bool = True


@router.post("/comptes", status_code=201,
             dependencies=[Depends(exiger_permission("tresorerie.compte.creer"))])
def creer_compte(
    donnees: CompteCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    try:
        c = repo.creer_compte(db, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(c.id), "code": c.code, "libelle": c.libelle, "solde": c.solde_actuel}


@router.get("/comptes",
            dependencies=[Depends(exiger_permission("tresorerie.lire"))])
def comptes(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    return repo.etat_comptes(db)


@router.post("/mouvements", status_code=201,
             dependencies=[Depends(exiger_permission("tresorerie.mouvement.creer"))])
def enregistrer(
    donnees: MouvementCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Entree ou sortie d'argent. Refuse si la caisse est insuffisante."""
    try:
        m = repo.enregistrer_mouvement(db, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    from app.models import CompteTresorerie
    compte = db.get(CompteTresorerie, m.compte_tresorerie_id)
    return {
        "numero": m.numero,
        "montant": m.montant,
        "sens": m.sens.value,
        "nouveau_solde": compte.solde_actuel,
    }


@router.get("/journal",
            dependencies=[Depends(exiger_permission("tresorerie.lire"))])
def journal(
    compte_id: Optional[UUID] = Query(default=None),
    depuis: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    return repo.journal(db, compte_id, depuis)


@router.get("/depenses",
            dependencies=[Depends(exiger_permission("tresorerie.lire"))])
def depenses(
    depuis: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Ce que l'entreprise depense, par poste."""
    return repo.depenses_par_categorie(db, depuis)


@router.get("/categories", include_in_schema=False)
def categories(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    from app.models import CategorieDepense

    return [
        {"id": str(c.id), "code": c.code, "libelle": c.libelle}
        for c in db.query(CategorieDepense)
        .filter(CategorieDepense.is_actif.is_(True))
        .order_by(CategorieDepense.libelle)
        .all()
    ]


@router.post("/categories", status_code=201,
             dependencies=[Depends(exiger_permission("tresorerie.compte.creer"))])
def creer_categorie(
    donnees: CategorieCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    from app.models import CategorieDepense

    if db.query(CategorieDepense).filter(CategorieDepense.code == donnees.code).first():
        raise HTTPException(status_code=400, detail=f"Le code {donnees.code} existe deja")
    c = CategorieDepense(
        code=donnees.code,
        libelle=donnees.libelle,
        exige_justificatif=donnees.exige_justificatif,
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": str(c.id), "code": c.code, "libelle": c.libelle}

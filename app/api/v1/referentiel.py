"""Routes d'administration des referentiels : collecteurs, marches."""

from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import exiger_permission, get_db, utilisateur_courant
from app.models import Collecteur, Utilisateur, ZoneCollecte
from app.models.enums import ModeDetention, StatutCollecteur, TypeCollecteur

router = APIRouter(prefix="/api/v1/referentiel", tags=["Referentiels"])


class CollecteurCreer(BaseModel):
    code: str = Field(max_length=30)
    nom: str = Field(max_length=180)
    telephone: Optional[str] = Field(default=None, max_length=40)
    telephone_mobile_money: Optional[str] = Field(default=None, max_length=40)
    piece_identite: Optional[str] = Field(default=None, max_length=60)
    type_collecteur: TypeCollecteur = TypeCollecteur.INDEPENDANT
    zone_principale_id: Optional[UUID] = None
    mode_detention_habituel: ModeDetention = ModeDetention.MARGE_FIXE_TONNE
    marge_fixe_tonne: Optional[Decimal] = Field(default=None, ge=0)


class PlafondModifier(BaseModel):
    plafond_avance: Decimal = Field(ge=0)


class ZoneCreer(BaseModel):
    code: str = Field(max_length=30)
    libelle: str = Field(max_length=150)
    village: Optional[str] = Field(default=None, max_length=120)
    departement: Optional[str] = Field(default=None, max_length=120)
    region: Optional[str] = Field(default=None, max_length=120)
    jour_marche: Optional[str] = Field(default=None, max_length=60)
    distance_douala_km: Optional[Decimal] = Field(default=None, ge=0)


@router.post("/collecteurs", status_code=201,
             dependencies=[Depends(exiger_permission("referentiel.collecteur.creer"))])
def creer_collecteur(
    donnees: CollecteurCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """
    Cree un collecteur. Le plafond d'avance reste a zero : aucune avance ne
    pourra lui etre versee tant que la direction ne l'aura pas fixe.
    """
    if db.query(Collecteur).filter(Collecteur.code == donnees.code).first():
        raise HTTPException(status_code=400, detail=f"Le code {donnees.code} existe deja")

    c = Collecteur(
        **donnees.model_dump(),
        statut=StatutCollecteur.ACTIF,
        plafond_avance=Decimal("0"),
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return {
        "id": str(c.id),
        "code": c.code,
        "nom": c.nom,
        "plafond_avance": c.plafond_avance,
        "message": "Collecteur cree. La direction doit fixer son plafond avant toute avance.",
    }


@router.get("/collecteurs",
            dependencies=[Depends(exiger_permission("referentiel.collecteur.lire"))])
def lister_collecteurs(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    return [
        {
            "id": str(c.id),
            "code": c.code,
            "nom": c.nom,
            "telephone": c.telephone,
            "statut": c.statut.value,
            "plafond_avance": c.plafond_avance,
            "nb_collectes": c.nb_collectes,
            "ecart_cumule_kg": c.ecart_poids_cumule_kg,
        }
        for c in db.query(Collecteur).order_by(Collecteur.nom).all()
    ]


@router.patch("/collecteurs/{collecteur_id}/plafond",
              dependencies=[Depends(exiger_permission("referentiel.plafond.modifier"))])
def fixer_plafond(
    collecteur_id: UUID,
    donnees: PlafondModifier,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Autorise les avances jusqu'a ce montant. Direction uniquement."""
    c = db.get(Collecteur, collecteur_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Collecteur introuvable")
    c.plafond_avance = donnees.plafond_avance
    db.commit()
    return {"id": str(c.id), "nom": c.nom, "plafond_avance": c.plafond_avance}


@router.post("/zones", status_code=201,
             dependencies=[Depends(exiger_permission("referentiel.zone.creer"))])
def creer_zone(
    donnees: ZoneCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    if db.query(ZoneCollecte).filter(ZoneCollecte.code == donnees.code).first():
        raise HTTPException(status_code=400, detail=f"Le code {donnees.code} existe deja")
    z = ZoneCollecte(**donnees.model_dump())
    db.add(z)
    db.commit()
    db.refresh(z)
    return {"id": str(z.id), "code": z.code, "libelle": z.libelle}

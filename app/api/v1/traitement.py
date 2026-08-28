"""Routes du traitement chez prestataire."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import exiger_permission, get_db, utilisateur_courant
from app.models import Utilisateur
from app.models.enums import BaseFacturationTraitement, TypeTraitement
from app.repositories import traitement as repo

router = APIRouter(prefix="/api/v1/traitement", tags=["Traitement prestataire"])


class ExpeditionCreer(BaseModel):
    prestataire_id: UUID
    lot_source_id: UUID
    date_expedition: datetime
    poids_entree_kg: Decimal = Field(gt=0)
    type_traitement: TypeTraitement = TypeTraitement.SECHAGE
    humidite_entree: Optional[Decimal] = Field(default=None, ge=0, le=100)
    impuretes_entree: Optional[Decimal] = Field(default=None, ge=0, le=100)
    prix_tonne_applique: Optional[Decimal] = Field(default=None, ge=0)
    base_facturation: Optional[BaseFacturationTraitement] = None
    frais_transport: Optional[Decimal] = Field(default=None, ge=0)
    date_retour_prevue: Optional[date] = None


class ReceptionCreer(BaseModel):
    date_fin: datetime
    poids_sortie_kg: Decimal = Field(gt=0)
    humidite_sortie: Optional[Decimal] = Field(default=None, ge=0, le=100)
    impuretes_sortie: Optional[Decimal] = Field(default=None, ge=0, le=100)


@router.post("/expeditions", status_code=201,
             dependencies=[Depends(exiger_permission("traitement.expedier"))])
def expedier(
    donnees: ExpeditionCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Envoie un lot chez le prestataire. Transfert, pas sortie de stock."""
    try:
        t = repo.expedier(db, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "id": str(t.id),
        "numero": t.numero,
        "poids_entree_kg": t.poids_entree_kg,
        "statut": t.statut.value,
    }


@router.post("/{traitement_id}/reception",
             dependencies=[Depends(exiger_permission("traitement.receptionner"))])
def receptionner(
    traitement_id: UUID,
    donnees: ReceptionCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Retour du prestataire : pesee, rendement, nouveau cout de revient."""
    try:
        return repo.receptionner(db, traitement_id, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/tableau/rendements",
            dependencies=[Depends(exiger_permission("traitement.lire"))])
def rendements(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Qui traite bien, qui perd de la marchandise."""
    return repo.rendements_prestataires(db)


@router.get("/en-cours", include_in_schema=False)
def en_cours(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Traitements partis et pas encore revenus."""
    from app.models import Prestataire, Traitement
    from app.models.enums import StatutTraitement

    lignes = (
        db.query(Traitement, Prestataire.nom)
        .join(Prestataire, Prestataire.id == Traitement.prestataire_id)
        .filter(Traitement.statut.in_([
            StatutTraitement.EXPEDIE, StatutTraitement.EN_COURS
        ]))
        .order_by(Traitement.date_expedition)
        .all()
    )
    return [
        {
            "id": str(t.id),
            "nom": f"{t.numero} — {nom} — {round(float(t.poids_entree_kg)/1000, 3)} t",
            "poids_entree_kg": t.poids_entree_kg,
            "humidite_entree": t.humidite_entree,
            "date_expedition": t.date_expedition,
        }
        for t, nom in lignes
    ]


@router.get("/prestataires", include_in_schema=False)
def liste_prestataires(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    from app.models import Prestataire

    return [
        {
            "id": str(p.id),
            "nom": p.nom,
            "prix_tonne": p.prix_tonne,
            "base_facturation": p.base_facturation.value,
            "a_magasin": p.magasin_id is not None,
        }
        for p in db.query(Prestataire).order_by(Prestataire.nom).all()
    ]

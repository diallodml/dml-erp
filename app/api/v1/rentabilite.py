"""Rentabilite reelle de l'activite, charges generales comprises."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import exiger_permission, get_db, utilisateur_courant
from app.models import Utilisateur
from app.repositories import rentabilite as repo

router = APIRouter(prefix="/api/v1/rentabilite", tags=["Rentabilite"])


@router.get("",
            dependencies=[Depends(exiger_permission("rentabilite.lire"))])
def voir(
    annee: Optional[int] = Query(default=None),
    mois: Optional[int] = Query(default=None, ge=1, le=12),
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """
    Compte de resultat de gestion sur la periode.

    Sans mois : l'annee entiere.
    """
    return repo.rentabilite(db, annee or date.today().year, mois)

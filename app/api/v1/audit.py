"""Consultation de la piste d'audit."""

from datetime import date, datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import exiger_permission, get_db, utilisateur_courant
from app.models import Utilisateur
from app.repositories import audit as repo

router = APIRouter(prefix="/api/v1/audit", tags=["Audit"])


@router.get("", dependencies=[Depends(exiger_permission("audit.lire"))])
def journal(
    utilisateur_id: Optional[UUID] = Query(default=None),
    table: Optional[str] = Query(default=None),
    depuis: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Les dernieres actions sensibles."""
    borne = None
    if depuis:
        borne = datetime.combine(depuis, datetime.min.time(), tzinfo=timezone.utc)
    return repo.journal(db, 200, utilisateur_id, table, borne)

"""Routes d'annulation des saisies erronees."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_db, utilisateur_courant
from app.models import Utilisateur
from app.repositories import annulation as repo

router = APIRouter(prefix="/api/v1/annulation", tags=["Annulations"])


class MotifAnnulation(BaseModel):
    motif: str = Field(min_length=5, max_length=255)


def _executer(fonction, db, identifiant, motif, utilisateur):
    try:
        return fonction(db, identifiant, motif, utilisateur)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/avances/{avance_id}")
def annuler_avance(
    avance_id: UUID,
    donnees: MotifAnnulation,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Annule une avance non encore justifiee."""
    return _executer(repo.annuler_avance, db, avance_id, donnees.motif, utilisateur)


@router.post("/lignes/{ligne_id}")
def annuler_ligne(
    ligne_id: UUID,
    donnees: MotifAnnulation,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Supprime une ligne d'achat mal saisie."""
    return _executer(repo.annuler_ligne, db, ligne_id, donnees.motif, utilisateur)


@router.post("/receptions/{collecte_id}")
def annuler_reception(
    collecte_id: UUID,
    donnees: MotifAnnulation,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Revient sur une pesee erronee et rouvre la collecte."""
    return _executer(repo.annuler_reception, db, collecte_id, donnees.motif, utilisateur)


@router.post("/lots/{lot_id}")
def extourner_lot(
    lot_id: UUID,
    donnees: MotifAnnulation,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Sort du stock un lot cree par erreur, par mouvement inverse."""
    return _executer(repo.extourner_lot, db, lot_id, donnees.motif, utilisateur)


@router.get("/lignes/{collecte_id}", include_in_schema=False)
def lignes_collecte(
    collecte_id: UUID,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Lignes d'achat d'une collecte, pour pouvoir en annuler une."""
    from app.models import LigneCollecte, Produit

    lignes = (
        db.query(LigneCollecte, Produit.designation)
        .outerjoin(Produit, Produit.id == LigneCollecte.produit_id)
        .filter(LigneCollecte.collecte_id == collecte_id)
        .order_by(LigneCollecte.numero_ligne)
        .all()
    )
    return [
        {
            "id": str(l.id),
            "numero_ligne": l.numero_ligne,
            "produit": produit or "—",
            "vendeur": l.nom_vendeur or "—",
            "nombre_sacs": l.nombre_sacs,
            "prix_unitaire": l.prix_unitaire,
            "montant": l.montant,
        }
        for l, produit in lignes
    ]

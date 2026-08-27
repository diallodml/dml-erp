"""Routes du module Collecte & Consignation."""

from datetime import date
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import exiger_permission, get_db, utilisateur_courant
from app.models import Collecte, Utilisateur
from app.repositories import collecte as repo
from app.schemas.collecte import (
    AvanceCreer,
    AvanceLire,
    CollecteCreer,
    CollecteLire,
    CollecteReceptionner,
    EcartCollecteur,
    LigneCollecteCreer,
    LigneCollecteLire,
    SoldeCollecteur,
)

router = APIRouter(prefix="/api/v1/collecte", tags=["Collecte & Consignation"])


# ---------------------------------------------------------------------------
# AVANCES
# ---------------------------------------------------------------------------
@router.post("/avances", response_model=AvanceLire, status_code=201,
             dependencies=[Depends(exiger_permission("collecte.avance.creer"))])
def creer_avance(
    donnees: AvanceCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Remet une avance a un collecteur. Refuse si le plafond est depasse."""
    try:
        return repo.creer_avance(db, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/avances/soldes", response_model=List[SoldeCollecteur],
            dependencies=[Depends(exiger_permission("collecte.avance.lire"))])
def soldes(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Combien chaque collecteur doit-il ? Trie par montant du."""
    return repo.soldes_collecteurs(db)


# ---------------------------------------------------------------------------
# COLLECTES
# ---------------------------------------------------------------------------
@router.post("", response_model=CollecteLire, status_code=201,
             dependencies=[Depends(exiger_permission("collecte.collecte.creer"))])
def creer_collecte(
    donnees: CollecteCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Ouvre une collecte. Le mode de detention se fige ici."""
    try:
        return repo.creer_collecte(db, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{collecte_id}/lignes", response_model=LigneCollecteLire, status_code=201,
             dependencies=[Depends(exiger_permission("collecte.ligne.creer"))])
def ajouter_ligne(
    collecte_id: UUID,
    donnees: LigneCollecteCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Saisit un achat au marche, rapporte par le collecteur."""
    try:
        return repo.ajouter_ligne(db, collecte_id, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{collecte_id}/reception", response_model=CollecteLire,
             dependencies=[Depends(exiger_permission("collecte.reception.creer"))])
def receptionner(
    collecte_id: UUID,
    donnees: CollecteReceptionner,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Pesee a l'arrivee au magasin. Calcule l'ecart poids paye / poids recu."""
    try:
        return repo.receptionner(db, collecte_id, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{collecte_id}", response_model=CollecteLire,
            dependencies=[Depends(exiger_permission("collecte.collecte.lire"))])
def lire_collecte(
    collecte_id: UUID,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    collecte = db.get(Collecte, collecte_id)
    if collecte is None:
        raise HTTPException(status_code=404, detail="Collecte introuvable")
    return collecte


# ---------------------------------------------------------------------------
# TABLEAU DE BORD
# ---------------------------------------------------------------------------
@router.get("/tableau/ecarts", response_model=List[EcartCollecteur],
            dependencies=[Depends(exiger_permission("collecte.ecart.lire"))])
def ecarts(
    depuis: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Qui achete bien, qui coute de l'argent. Trie du pire au meilleur."""
    return repo.ecarts_collecteurs(db, depuis)


@router.post("/{collecte_id}/entree-stock", status_code=201,
             dependencies=[Depends(exiger_permission("collecte.stock.creer"))])
def entree_stock(
    collecte_id: UUID,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Cree le lot et le mouvement d'entree depuis une collecte receptionnee."""
    collecte = db.get(Collecte, collecte_id)
    if collecte is None:
        raise HTTPException(status_code=404, detail="Collecte introuvable")
    try:
        lot = repo.entrer_en_stock(db, collecte, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "lot_id": str(lot.id),
        "numero": lot.numero,
        "quantite_kg": lot.quantite_disponible,
        "cout_unitaire": lot.cout_unitaire,
        "valeur_stock": lot.valeur_stock,
        "mode_detention": lot.mode_detention,
    }


@router.get("/tableau/stock",
            dependencies=[Depends(exiger_permission("collecte.stock.lire"))])
def tableau_stock(
    magasin_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Combien de tonnes en magasin, et a qui appartiennent-elles ?"""
    return repo.etat_stock(db, magasin_id)

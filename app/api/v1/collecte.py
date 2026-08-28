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


@router.get("/referentiels", include_in_schema=False)
def referentiels(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Listes deroulantes de la page de saisie."""
    from app.models import Collecteur, Magasin, Produit, ZoneCollecte

    return {
        "collecteurs": [
            {"id": str(c.id), "nom": c.nom}
            for c in db.query(Collecteur).order_by(Collecteur.nom).all()
        ],
        "zones": [
            {"id": str(z.id), "nom": z.libelle}
            for z in db.query(ZoneCollecte).order_by(ZoneCollecte.libelle).all()
        ],
        "produits": [
            {"id": str(p.id), "nom": p.designation}
            for p in db.query(Produit).order_by(Produit.designation).all()
        ],
        "magasins": [
            {"id": str(m.id), "nom": m.nom}
            for m in db.query(Magasin).order_by(Magasin.nom).all()
        ],
    }


@router.get("/referentiels/collectes", include_in_schema=False)
def liste_collectes(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Collectes recentes, pour les listes deroulantes."""
    from app.models import Collecteur

    lignes = (
        db.query(Collecte, Collecteur.nom)
        .join(Collecteur, Collecteur.id == Collecte.collecteur_id)
        .order_by(Collecte.numero.desc())
        .limit(50)
        .all()
    )
    return [
        {
            "id": str(c.id),
            "numero": c.numero,
            "collecteur": nom,
            "statut": c.statut.value,
        }
        for c, nom in lignes
    ]


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


@router.get("/tableau/lots",
            dependencies=[Depends(exiger_permission("collecte.stock.lire"))])
def lots_en_magasin(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """
    Lots en stock, du plus a risque au plus sain.

    Le risque combine deux facteurs : l'humidite d'entree au-dela du seuil
    du produit, et l'age du lot. Du grain a 16 % entre hier n'est pas encore
    un probleme ; le meme lot trois semaines plus tard en est un.
    """
    from datetime import datetime, timezone
    from decimal import Decimal

    from app.models import Collecteur, Lot, Magasin, Produit

    lignes = (
        db.query(Lot, Produit.designation, Produit.taux_humidite_max,
                 Magasin.nom, Collecteur.nom)
        .join(Produit, Produit.id == Lot.produit_id)
        .join(Magasin, Magasin.id == Lot.magasin_id)
        .outerjoin(Collecteur, Collecteur.id == Lot.collecteur_id)
        .filter(Lot.quantite_disponible > 0)
        .all()
    )

    maintenant = datetime.now(timezone.utc)
    resultats = []

    for lot, produit, seuil, magasin, collecteur in lignes:
        age_jours = None
        if lot.date_entree is not None:
            entree = lot.date_entree
            if hasattr(entree, "date"):
                entree = entree.date()
            age_jours = (maintenant.date() - entree).days

        humidite = lot.taux_humidite_entree
        seuil = seuil or Decimal("14.00")
        hors_seuil = humidite is not None and humidite > seuil

        # Le risque monte avec l'humidite ET avec le temps
        if hors_seuil and age_jours is not None and age_jours > 21:
            risque = "URGENCE"
        elif hors_seuil and age_jours is not None and age_jours > 7:
            risque = "CRITIQUE"
        elif hors_seuil:
            risque = "ATTENTION"
        elif age_jours is not None and age_jours > 90:
            risque = "ATTENTION"
        else:
            risque = "INFO"

        resultats.append({
            "id": str(lot.id),
            "numero": lot.numero,
            "produit": produit,
            "magasin": magasin,
            "collecteur": collecteur,
            "mode_detention": lot.mode_detention.value if lot.mode_detention else None,
            "quantite_kg": lot.quantite_disponible,
            "tonnes": (lot.quantite_disponible / Decimal("1000")).quantize(Decimal("0.001")),
            "humidite": humidite,
            "seuil": seuil,
            "hors_seuil": hors_seuil,
            "age_jours": age_jours,
            "cout_unitaire": lot.cout_unitaire,
            "valeur": lot.valeur_stock,
            "risque": risque,
        })

    ordre = {"URGENCE": 0, "CRITIQUE": 1, "ATTENTION": 2, "INFO": 3}
    resultats.sort(key=lambda r: (ordre[r["risque"]], -(r["age_jours"] or 0)))
    return resultats

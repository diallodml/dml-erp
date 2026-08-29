"""Routes de vente aux industriels et de reversement aux collecteurs."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import exiger_permission, get_db, utilisateur_courant
from app.models import Utilisateur
from app.models.enums import ModeReglement
from app.repositories import vente_collecte as repo

router = APIRouter(prefix="/api/v1/vente", tags=["Vente & Reversement"])


class LivraisonCreer(BaseModel):
    lot_id: UUID
    date_livraison: datetime
    quantite_kg: Decimal = Field(gt=0)
    montant_vente: Decimal = Field(ge=0)
    client_nom: Optional[str] = Field(default=None, max_length=200)
    client_id: Optional[UUID] = None
    lieu_livraison: Optional[str] = Field(default=None, max_length=255)
    transporteur: Optional[str] = Field(default=None, max_length=150)
    immatriculation: Optional[str] = Field(default=None, max_length=30)
    telephone_chauffeur: Optional[str] = Field(default=None, max_length=30)
    frais_deduits: Optional[Decimal] = Field(default=None, ge=0)
    avance_compensee: Optional[Decimal] = Field(default=None, ge=0)
    date_echeance: Optional[date] = None


class PaiementCreer(BaseModel):
    montant_paye: Decimal = Field(gt=0)
    date_paiement: date
    mode_paiement: ModeReglement = ModeReglement.MOBILE_MONEY
    reference_paiement: Optional[str] = Field(default=None, max_length=120)
    compte_tresorerie_id: Optional[UUID] = None


@router.post("/livraisons", status_code=201,
             dependencies=[Depends(exiger_permission("vente.livraison.creer"))])
def livrer(
    donnees: LivraisonCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Sort la marchandise du lot et calcule le reversement du collecteur."""
    try:
        return repo.livrer(db, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/reversements",
            dependencies=[Depends(exiger_permission("vente.reversement.lire"))])
def reversements(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Ce que DML doit aux collecteurs."""
    return repo.reversements_dus(db)


@router.post("/reversements/{reversement_id}/paiement",
             dependencies=[Depends(exiger_permission("vente.reversement.payer"))])
def payer(
    reversement_id: UUID,
    donnees: PaiementCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Verse l'argent au collecteur et eteint la dette."""
    try:
        r = repo.payer_reversement(db, reversement_id, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "numero": r.numero,
        "montant_paye": r.montant_paye,
        "solde": r.solde_a_payer,
        "statut": r.statut.value,
    }


@router.get("/lots", include_in_schema=False)
def lots_disponibles(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Lots avec du stock, pour la liste deroulante de livraison."""
    from app.models import Collecteur, Lot, Magasin, Produit

    lignes = (
        db.query(Lot, Produit.designation, Magasin.nom, Collecteur.nom)
        .join(Produit, Produit.id == Lot.produit_id)
        .join(Magasin, Magasin.id == Lot.magasin_id)
        .outerjoin(Collecteur, Collecteur.id == Lot.collecteur_id)
        .filter(Lot.quantite_disponible > 0)
        .order_by(Lot.numero)
        .all()
    )
    return [
        {
            "id": str(lot.id),
            "nom": f"{lot.numero} — {produit} — {round(float(lot.quantite_disponible)/1000, 3)} t"
                   + (f" ({collecteur})" if collecteur else ""),
            "disponible_kg": lot.quantite_disponible,
            "cout_unitaire": lot.cout_unitaire,
            "magasin": magasin,
            "humidite": lot.taux_humidite_entree,
        }
        for lot, produit, magasin, collecteur in lignes
    ]


@router.get("/livraisons/{mouvement_id}/bon", include_in_schema=False)
def bon_livraison(
    mouvement_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Bon de livraison, a faire signer par le destinataire."""
    import base64
    import pathlib

    from fastapi.templating import Jinja2Templates

    from app.core.entreprise import ENTREPRISE
    from app.models import Lot, Magasin, MouvementStock, Produit

    m = db.get(MouvementStock, mouvement_id)
    if m is None:
        raise HTTPException(status_code=404, detail="Livraison introuvable")

    lot = db.get(Lot, m.lot_id) if m.lot_id else None
    produit = db.get(Produit, m.produit_id)
    magasin = db.get(Magasin, m.magasin_source_id) if m.magasin_source_id else None

    logo = ""
    chemin = pathlib.Path("app/static/logo.jpeg")
    if chemin.exists():
        logo = "data:image/jpeg;base64," + base64.b64encode(chemin.read_bytes()).decode()

    def fmt(v, dec=0):
        if v is None:
            return "—"
        return f"{float(v):,.{dec}f}".replace(",", " ").replace(".", ",")

    # client | lieu | transporteur | immatriculation | telephone
    champs = (m.observations or "").split("|")
    while len(champs) < 5:
        champs.append("")
    livraison = {
        "client": champs[0] or "—",
        "lieu": champs[1] or "—",
        "transporteur": champs[2] or "—",
        "immatriculation": champs[3] or "—",
        "telephone": champs[4] or "",
    }

    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(
        request,
        "bon_livraison.html",
        {
            "e": ENTREPRISE,
            "logo": logo,
            "l": livraison,
            "m": m,
            "lot": lot,
            "produit": produit,
            "magasin": magasin,
            "fmt": fmt,
        },
    )

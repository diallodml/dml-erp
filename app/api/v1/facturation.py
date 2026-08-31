"""Bon de commande, bon de livraison, facture."""

from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import exiger_permission, get_db, utilisateur_courant
from app.models import Utilisateur
from app.models.enums import ModeReglement
from app.repositories import facturation as repo

router = APIRouter(prefix="/api/v1/facturation", tags=["Facturation"])


class CommandeCreer(BaseModel):
    client_id: UUID
    reference_client: str = Field(min_length=1, max_length=80)
    produit_id: UUID
    date_commande: date
    tonnage_demande_kg: Decimal = Field(gt=0)
    prix_kg: Decimal = Field(gt=0)
    date_livraison_souhaitee: Optional[date] = None
    lieu_livraison: Optional[str] = Field(default=None, max_length=255)


class LivraisonCreer(BaseModel):
    commande_id: UUID
    lot_id: UUID
    date_livraison: date
    nombre_sacs: int = Field(gt=0)
    poids_sac_kg: Decimal = Field(gt=0, default=Decimal("100"))
    transporteur: Optional[str] = Field(default=None, max_length=180)
    immatriculation: Optional[str] = Field(default=None, max_length=30)
    lieu_livraison: Optional[str] = Field(default=None, max_length=255)


class PeseeCreer(BaseModel):
    date_pesee: datetime
    poids_livre_kg: Decimal = Field(gt=0)
    numero_ticket: Optional[str] = Field(default=None, max_length=60)
    signataire: Optional[str] = Field(default=None, max_length=150)
    reserves: Optional[str] = None


class FactureCreer(BaseModel):
    date_facture: date
    date_echeance: Optional[date] = None
    prix_kg: Optional[Decimal] = Field(default=None, ge=0)
    frais_transport: Optional[Decimal] = Field(default=None, ge=0)
    mode_reglement: Optional[ModeReglement] = None
    conditions: Optional[str] = None


class ReglementCreer(BaseModel):
    montant: Decimal = Field(gt=0)
    date_reglement: date
    mode_reglement: ModeReglement = ModeReglement.VIREMENT
    compte_tresorerie_id: Optional[UUID] = None


@router.post("/commandes", status_code=201,
             dependencies=[Depends(exiger_permission("vente.livraison.creer"))])
def creer_commande(
    donnees: CommandeCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Enregistre le bon de commande recu du client."""
    try:
        bc = repo.creer_commande(db, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(bc.id), "numero": bc.numero,
            "reference_client": bc.reference_client, "montant": bc.montant_ht}


@router.get("/commandes",
            dependencies=[Depends(exiger_permission("vente.reversement.lire"))])
def commandes(
    ouvertes: bool = Query(default=False),
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    return repo.liste_commandes(db, ouvertes)


@router.post("/livraisons", status_code=201,
             dependencies=[Depends(exiger_permission("vente.livraison.creer"))])
def creer_livraison(
    donnees: LivraisonCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Chargement du camion : on compte les sacs."""
    try:
        bl = repo.creer_livraison(db, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(bl.id), "numero": bl.numero,
            "nombre_sacs": bl.nombre_sacs, "poids_charge_kg": bl.poids_charge}


@router.post("/livraisons/{livraison_id}/pesee",
             dependencies=[Depends(exiger_permission("vente.livraison.creer"))])
def pesee(
    livraison_id: UUID,
    donnees: PeseeCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Le client a pese : c'est ce tonnage qui fait foi."""
    try:
        return repo.enregistrer_pesee(db, livraison_id, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/livraisons/{livraison_id}/facture", status_code=201,
             dependencies=[Depends(exiger_permission("vente.livraison.creer"))])
def facturer(
    livraison_id: UUID,
    donnees: FactureCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Facture le tonnage pese, au prix du bon de commande."""
    try:
        return repo.creer_facture(db, livraison_id, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/factures",
            dependencies=[Depends(exiger_permission("vente.reversement.lire"))])
def factures(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    return repo.liste_factures(db)


@router.post("/factures/{facture_id}/reglement",
             dependencies=[Depends(exiger_permission("vente.reversement.payer"))])
def encaisser(
    facture_id: UUID,
    donnees: ReglementCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Enregistre un reglement client."""
    try:
        return repo.encaisser(db, facture_id, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/livraisons-a-peser", include_in_schema=False)
def a_peser(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Camions partis dont le client n'a pas encore communique la pesee."""
    from app.models import BonLivraison, Client
    from app.models.enums import StatutLivraison

    lignes = (
        db.query(BonLivraison, Client.raison_sociale)
        .join(Client, Client.id == BonLivraison.client_id)
        .filter(BonLivraison.statut == StatutLivraison.EN_ROUTE)
        .order_by(BonLivraison.date_livraison)
        .all()
    )
    return [
        {
            "id": str(bl.id),
            "nom": f"{bl.numero} — {client} — {bl.nombre_sacs} sacs "
                   f"({float(bl.poids_charge)/1000:.3f} t estimées)",
            "poids_charge_kg": bl.poids_charge,
            "nombre_sacs": bl.nombre_sacs,
        }
        for bl, client in lignes
    ]


@router.get("/a-facturer", include_in_schema=False)
def a_facturer(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Livraisons pesees mais pas encore facturees."""
    from app.models import BonCommandeClient, BonLivraison, Client
    from app.models.enums import StatutLivraison

    lignes = (
        db.query(BonLivraison, Client.raison_sociale, BonCommandeClient.reference_client)
        .join(Client, Client.id == BonLivraison.client_id)
        .outerjoin(BonCommandeClient, BonCommandeClient.id == BonLivraison.commande_id)
        .filter(
            BonLivraison.statut.in_([StatutLivraison.LIVRE, StatutLivraison.LIVRE_AVEC_ECART]),
            BonLivraison.is_facture.is_(False),
        )
        .order_by(BonLivraison.date_livraison)
        .all()
    )
    return [
        {
            "id": str(bl.id),
            "nom": f"{bl.numero} — {client} — {float(bl.poids_livre)/1000:.3f} t pesées"
                   + (f" (réf. {ref})" if ref else ""),
            "poids_livre_kg": bl.poids_livre,
        }
        for bl, client, ref in lignes
    ]


@router.get("/factures/{facture_id}/document", include_in_schema=False)
def document_facture(
    facture_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Facture imprimable, avec la reference du bon de commande client."""
    import base64
    import pathlib

    from fastapi.templating import Jinja2Templates

    from app.core.entreprise import ENTREPRISE
    from app.models import (
        BonCommandeClient,
        BonLivraison,
        Client,
        FactureVente,
        LigneFactureVente,
    )

    f = db.get(FactureVente, facture_id)
    if f is None:
        raise HTTPException(status_code=404, detail="Facture introuvable")

    client = db.get(Client, f.client_id)
    bc = db.get(BonCommandeClient, f.commande_id) if f.commande_id else None
    bl = db.get(BonLivraison, f.bon_livraison_id) if f.bon_livraison_id else None
    lignes = (
        db.query(LigneFactureVente)
        .filter(LigneFactureVente.facture_id == f.id)
        .all()
    )

    logo = ""
    chemin = pathlib.Path("app/static/logo.jpeg")
    if chemin.exists():
        logo = "data:image/jpeg;base64," + base64.b64encode(chemin.read_bytes()).decode()

    def fmt(v, dec=0):
        if v is None:
            return "—"
        return f"{float(v):,.{dec}f}".replace(",", " ").replace(".", ",")

    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(
        request,
        "doc_facture.html",
        {
            "e": ENTREPRISE, "logo": logo, "f": f, "client": client,
            "bc": bc, "bl": bl, "lignes": lignes, "fmt": fmt,
            "montant_lettres": _lettres(int(f.montant_ttc)),
        },
    )


def _lettres(n: int) -> str:
    from app.api.v1.collecte import _en_lettres
    return _en_lettres(n)


@router.get("/livraisons/{livraison_id}/document", include_in_schema=False)
def document_livraison(
    livraison_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Bon de livraison a remettre au chauffeur et au destinataire."""
    import base64
    import pathlib

    from fastapi.templating import Jinja2Templates

    from app.core.entreprise import ENTREPRISE
    from app.models import (
        BonCommandeClient,
        BonLivraison,
        Client,
        LigneBonLivraison,
        Lot,
        Magasin,
        Produit,
    )

    bl = db.get(BonLivraison, livraison_id)
    if bl is None:
        raise HTTPException(status_code=404, detail="Bon de livraison introuvable")

    client = db.get(Client, bl.client_id)
    bc = db.get(BonCommandeClient, bl.commande_id) if bl.commande_id else None
    magasin = db.get(Magasin, bl.magasin_id) if bl.magasin_id else None

    lignes = []
    for l in db.query(LigneBonLivraison).filter(
        LigneBonLivraison.bon_livraison_id == bl.id
    ).all():
        produit = db.get(Produit, l.produit_id) if l.produit_id else None
        lot = db.get(Lot, l.lot_id) if l.lot_id else None
        lignes.append({
            "designation": produit.designation if produit else "Produits agricoles",
            "lot": lot.numero if lot else "—",
            "humidite": lot.taux_humidite_entree if lot else None,
            "quantite": l.quantite_livree,
        })

    logo = ""
    chemin = pathlib.Path("app/static/logo.jpeg")
    if chemin.exists():
        logo = "data:image/jpeg;base64," + base64.b64encode(chemin.read_bytes()).decode()

    def fmt(v, dec=0):
        if v is None:
            return "—"
        return f"{float(v):,.{dec}f}".replace(",", " ").replace(".", ",")

    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(
        request,
        "doc_livraison.html",
        {
            "e": ENTREPRISE, "logo": logo, "bl": bl, "client": client,
            "bc": bc, "magasin": magasin, "lignes": lignes, "fmt": fmt,
        },
    )


class ProformaCreer(BaseModel):
    client_id: UUID
    produit_id: UUID
    date_emission: date
    quantite_kg: Decimal = Field(gt=0)
    prix_kg: Decimal = Field(gt=0)
    validite_jours: Optional[int] = Field(default=15, ge=1)
    objet: Optional[str] = Field(default=None, max_length=255)
    frais_transport: Optional[Decimal] = Field(default=None, ge=0)
    conditions_paiement: Optional[str] = None
    conditions_livraison: Optional[str] = None
    proforma_origine_id: Optional[UUID] = None


class TransformerProforma(BaseModel):
    reference_client: str = Field(min_length=1, max_length=80)
    date_commande: date
    date_livraison_souhaitee: Optional[date] = None
    lieu_livraison: Optional[str] = Field(default=None, max_length=255)


@router.post("/proformas", status_code=201,
             dependencies=[Depends(exiger_permission("vente.livraison.creer"))])
def creer_proforma(
    donnees: ProformaCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Offre de prix. Renseigner proforma_origine_id pour une revision."""
    try:
        pf = repo.creer_proforma(db, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": str(pf.id), "numero": pf.numero, "version": pf.version,
            "montant": pf.montant_ttc}


@router.get("/proformas",
            dependencies=[Depends(exiger_permission("vente.reversement.lire"))])
def proformas(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    return repo.liste_proformas(db)


@router.post("/proformas/{proforma_id}/commande", status_code=201,
             dependencies=[Depends(exiger_permission("vente.livraison.creer"))])
def transformer(
    proforma_id: UUID,
    donnees: TransformerProforma,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Le client a accepte : la proforma devient un bon de commande."""
    try:
        return repo.transformer_proforma(db, proforma_id, donnees, utilisateur)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/proformas/{proforma_id}/document", include_in_schema=False)
def document_proforma(
    proforma_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Proforma imprimable, a envoyer au client."""
    import base64
    import pathlib

    from fastapi.templating import Jinja2Templates

    from app.core.entreprise import ENTREPRISE
    from app.models import Client, LigneProforma, Proforma

    pf = db.get(Proforma, proforma_id)
    if pf is None:
        raise HTTPException(status_code=404, detail="Proforma introuvable")

    client = db.get(Client, pf.client_id)
    lignes = (
        db.query(LigneProforma)
        .filter(LigneProforma.proforma_id == pf.id)
        .order_by(LigneProforma.ordre)
        .all()
    )

    logo = ""
    chemin = pathlib.Path("app/static/logo.jpeg")
    if chemin.exists():
        logo = "data:image/jpeg;base64," + base64.b64encode(chemin.read_bytes()).decode()

    def fmt(v, dec=0):
        if v is None:
            return "—"
        return f"{float(v):,.{dec}f}".replace(",", " ").replace(".", ",")

    templates = Jinja2Templates(directory="app/templates")
    return templates.TemplateResponse(
        request,
        "doc_proforma.html",
        {"e": ENTREPRISE, "logo": logo, "pf": pf, "client": client,
         "lignes": lignes, "fmt": fmt},
    )

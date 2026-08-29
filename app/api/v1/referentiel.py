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


@router.get("/collecteurs/{collecteur_id}/historique",
            dependencies=[Depends(exiger_permission("referentiel.collecteur.lire"))])
def historique_collecteur(
    collecteur_id: UUID,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """
    Tout ce qu'on sait d'un collecteur, sur une page.

    A consulter avant de lui remettre une nouvelle avance : un ecart qui
    se repete n'est pas un accident.
    """
    from decimal import Decimal

    from app.models import AvanceCollecteur, Collecte, ReversementCollecteur, ZoneCollecte
    from app.models.enums import StatutCollecte

    c = db.get(Collecteur, collecteur_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Collecteur introuvable")

    avances = (
        db.query(AvanceCollecteur)
        .filter(AvanceCollecteur.collecteur_id == collecteur_id)
        .order_by(AvanceCollecteur.date_remise.desc())
        .limit(30)
        .all()
    )

    collectes = (
        db.query(Collecte, ZoneCollecte.libelle)
        .outerjoin(ZoneCollecte, ZoneCollecte.id == Collecte.zone_id)
        .filter(Collecte.collecteur_id == collecteur_id)
        .order_by(Collecte.date_debut.desc())
        .limit(30)
        .all()
    )

    reversements = (
        db.query(ReversementCollecteur)
        .filter(ReversementCollecteur.collecteur_id == collecteur_id)
        .order_by(ReversementCollecteur.date_calcul.desc())
        .limit(30)
        .all()
    )

    receptionnees = [c2 for c2, _ in collectes
                     if c2.statut == StatutCollecte.RECEPTIONNEE]
    theo = sum((c2.poids_theorique_kg or Decimal("0")) for c2 in receptionnees)
    reel = sum((c2.poids_reel_kg or Decimal("0")) for c2 in receptionnees)
    ecart = reel - theo

    return {
        "collecteur": {
            "id": str(c.id),
            "code": c.code,
            "nom": c.nom,
            "telephone": c.telephone,
            "statut": c.statut.value,
            "plafond_avance": c.plafond_avance,
            "marge_fixe_tonne": c.marge_fixe_tonne,
            "nb_collectes": c.nb_collectes,
            "tonnage_cumule": c.tonnage_cumule,
        },
        "synthese": {
            "poids_theorique_kg": theo,
            "poids_reel_kg": reel,
            "ecart_kg": ecart,
            "ecart_pourcentage": (
                (ecart / theo * 100).quantize(Decimal("0.01")) if theo else None
            ),
            "reste_du_avances": sum(
                (a.montant_reste_du or Decimal("0")) for a in avances
            ),
            "solde_reversements": sum(
                (r.montant_net_du - r.montant_paye) for r in reversements
            ),
        },
        "avances": [
            {
                "numero": a.numero,
                "date": a.date_remise,
                "remis": a.montant_remis,
                "justifie": a.montant_justifie,
                "reste_du": a.montant_reste_du,
                "statut": a.statut.value,
            }
            for a in avances
        ],
        "collectes": [
            {
                "numero": c2.numero,
                "date": c2.date_debut,
                "marche": zone or "—",
                "statut": c2.statut.value,
                "sacs": c2.nombre_sacs_total,
                "poids_theorique_kg": c2.poids_theorique_kg,
                "poids_reel_kg": c2.poids_reel_kg,
                "ecart_kg": c2.ecart_poids_kg,
                "montant": c2.montant_achat_total,
                "humidite": c2.taux_humidite_magasin,
            }
            for c2, zone in collectes
        ],
        "reversements": [
            {
                "numero": r.numero,
                "date": r.date_calcul,
                "tonnage": r.tonnage_vendu,
                "net_du": r.montant_net_du,
                "paye": r.montant_paye,
                "statut": r.statut.value,
            }
            for r in reversements
        ],
    }


# ---------------------------------------------------------------------------
# PRODUITS
# ---------------------------------------------------------------------------
class ProduitCreer(BaseModel):
    code: str = Field(max_length=40)
    designation: str = Field(max_length=200)
    famille_code: Optional[str] = Field(default=None, max_length=30)
    poids_sac_kg: Optional[Decimal] = Field(default=None, gt=0)
    taux_humidite_max: Optional[Decimal] = Field(default=None, ge=0, le=100)
    taux_impuretes_max: Optional[Decimal] = Field(default=None, ge=0, le=100)
    variete: Optional[str] = Field(default=None, max_length=120)


@router.post("/produits", status_code=201,
             dependencies=[Depends(exiger_permission("referentiel.produit.creer"))])
def creer_produit(
    donnees: ProduitCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """
    Cree un produit. Le seuil d'humidite pilote le controle qualite :
    laissez-le vide pour un article qui ne s'en soucie pas (emballages,
    consommables).
    """
    from app.models import FamilleProduit, Produit
    from app.models.enums import UniteMesure

    if db.query(Produit).filter(Produit.code == donnees.code).first():
        raise HTTPException(status_code=400, detail=f"Le code {donnees.code} existe deja")

    famille_id = None
    if donnees.famille_code:
        f = db.query(FamilleProduit).filter(
            FamilleProduit.code == donnees.famille_code
        ).first()
        if f is None:
            f = FamilleProduit(code=donnees.famille_code, nom=donnees.famille_code.title())
            db.add(f)
            db.flush()
        famille_id = f.id

    p = Produit(
        code=donnees.code,
        designation=donnees.designation,
        famille_id=famille_id,
        variete=donnees.variete,
        unite_base=UniteMesure.KG,
        poids_sac_kg=donnees.poids_sac_kg or Decimal("100"),
        taux_humidite_max=donnees.taux_humidite_max,
        taux_impuretes_max=donnees.taux_impuretes_max,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": str(p.id), "code": p.code, "designation": p.designation}


@router.get("/produits",
            dependencies=[Depends(exiger_permission("referentiel.produit.lire"))])
def lister_produits(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    from app.models import FamilleProduit, Produit

    lignes = (
        db.query(Produit, FamilleProduit.nom)
        .outerjoin(FamilleProduit, FamilleProduit.id == Produit.famille_id)
        .order_by(Produit.designation)
        .all()
    )
    return [
        {
            "id": str(p.id),
            "code": p.code,
            "designation": p.designation,
            "famille": fam or "—",
            "poids_sac_kg": p.poids_sac_kg,
            "taux_humidite_max": p.taux_humidite_max,
            "taux_impuretes_max": p.taux_impuretes_max,
        }
        for p, fam in lignes
    ]


# ---------------------------------------------------------------------------
# MAGASINS
# ---------------------------------------------------------------------------
class MagasinCreer(BaseModel):
    code: str = Field(max_length=30)
    nom: str = Field(max_length=150)
    type_magasin: str = "PRINCIPAL"
    ville: str = Field(default="Douala", max_length=80)
    quartier: Optional[str] = Field(default=None, max_length=120)
    region: Optional[str] = Field(default=None, max_length=80)


@router.post("/magasins", status_code=201,
             dependencies=[Depends(exiger_permission("referentiel.magasin.creer"))])
def creer_magasin(
    donnees: MagasinCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    from app.models import Magasin
    from app.models.enums import TypeMagasin

    if db.query(Magasin).filter(Magasin.code == donnees.code).first():
        raise HTTPException(status_code=400, detail=f"Le code {donnees.code} existe deja")

    try:
        type_mag = TypeMagasin(donnees.type_magasin)
    except ValueError:
        raise HTTPException(status_code=400, detail="Type de magasin inconnu")

    m = Magasin(
        code=donnees.code,
        nom=donnees.nom,
        type_magasin=type_mag,
        ville=donnees.ville,
        quartier=donnees.quartier,
        region=donnees.region,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"id": str(m.id), "code": m.code, "nom": m.nom}


@router.get("/magasins",
            dependencies=[Depends(exiger_permission("referentiel.magasin.creer"))])
def lister_magasins(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    from app.models import Magasin

    return [
        {
            "id": str(m.id),
            "code": m.code,
            "nom": m.nom,
            "type": m.type_magasin.value,
            "ville": m.ville,
        }
        for m in db.query(Magasin).order_by(Magasin.nom).all()
    ]


# ---------------------------------------------------------------------------
# PRESTATAIRES
# ---------------------------------------------------------------------------
class PrestataireCreer(BaseModel):
    code: str = Field(max_length=30)
    nom: str = Field(max_length=180)
    telephone: Optional[str] = Field(default=None, max_length=40)
    ville: str = Field(default="Douala", max_length=80)
    prix_tonne: Optional[Decimal] = Field(default=None, ge=0)
    base_facturation: str = "TONNE_ENTREE"
    delai_habituel_jours: Optional[int] = Field(default=None, ge=0)


@router.post("/prestataires", status_code=201,
             dependencies=[Depends(exiger_permission("referentiel.prestataire.creer"))])
def creer_prestataire(
    donnees: PrestataireCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """
    Cree un prestataire ET son magasin virtuel.

    Sans magasin associe, impossible de savoir ou se trouve la marchandise
    pendant le traitement : on le cree donc automatiquement.
    """
    from app.models import Magasin, Prestataire
    from app.models.enums import BaseFacturationTraitement, TypeMagasin

    if db.query(Prestataire).filter(Prestataire.code == donnees.code).first():
        raise HTTPException(status_code=400, detail=f"Le code {donnees.code} existe deja")

    code_mag = f"MAG-{donnees.code}"[:30]
    mag = db.query(Magasin).filter(Magasin.code == code_mag).first()
    if mag is None:
        mag = Magasin(
            code=code_mag,
            nom=f"Chez {donnees.nom}",
            type_magasin=TypeMagasin.SOUS_TRAITE,
            ville=donnees.ville,
        )
        db.add(mag)
        db.flush()

    try:
        base = BaseFacturationTraitement(donnees.base_facturation)
    except ValueError:
        raise HTTPException(status_code=400, detail="Base de facturation inconnue")

    p = Prestataire(
        code=donnees.code,
        nom=donnees.nom,
        telephone=donnees.telephone,
        ville=donnees.ville,
        magasin_id=mag.id,
        prix_tonne=donnees.prix_tonne,
        base_facturation=base,
        delai_habituel_jours=donnees.delai_habituel_jours,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": str(p.id), "code": p.code, "nom": p.nom, "magasin": mag.nom}


# ---------------------------------------------------------------------------
# CLIENTS INDUSTRIELS
# ---------------------------------------------------------------------------
class ClientCreer(BaseModel):
    code: str = Field(max_length=30)
    raison_sociale: str = Field(max_length=200)
    adresse_livraison: Optional[str] = Field(default=None, max_length=255)
    ville: str = Field(default="Douala", max_length=80)
    telephone: Optional[str] = Field(default=None, max_length=30)
    email: Optional[str] = Field(default=None, max_length=180)
    niu: Optional[str] = Field(default=None, max_length=30)
    contact_principal: Optional[str] = Field(default=None, max_length=150)
    type_client: str = "INDUSTRIEL"


@router.post("/clients", status_code=201,
             dependencies=[Depends(exiger_permission("referentiel.client.creer"))])
def creer_client(
    donnees: ClientCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    from app.models import Client

    if db.query(Client).filter(Client.code == donnees.code).first():
        raise HTTPException(status_code=400, detail=f"Le code {donnees.code} existe deja")

    from app.models.enums import TypeClient

    donnees_dict = donnees.model_dump()
    try:
        donnees_dict["type_client"] = TypeClient(donnees_dict["type_client"])
    except ValueError:
        raise HTTPException(status_code=400, detail="Type de client inconnu")

    c = Client(**donnees_dict)
    db.add(c)
    db.commit()
    db.refresh(c)
    return {"id": str(c.id), "code": c.code, "raison_sociale": c.raison_sociale}


@router.get("/clients",
            dependencies=[Depends(exiger_permission("referentiel.client.lire"))])
def lister_clients(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    from app.models import Client

    return [
        {
            "id": str(c.id),
            "code": c.code,
            "raison_sociale": c.raison_sociale,
            "adresse_livraison": c.adresse_livraison,
            "ville": c.ville,
            "telephone": c.telephone,
            "contact_principal": c.contact_principal,
        }
        for c in db.query(Client).order_by(Client.raison_sociale).all()
    ]

"""Schemas Pydantic du module Collecte & Consignation."""

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import (
    AppreciationQualiteMarche,
    BaseAchatMarche,
    ModeDetention,
    ModeReglement,
    StatutAvanceCollecteur,
    StatutCollecte,
)


# ---------------------------------------------------------------------------
# AVANCE
# ---------------------------------------------------------------------------
class AvanceCreer(BaseModel):
    collecteur_id: UUID
    date_remise: date
    montant_remis: Decimal = Field(gt=0)
    mode_remise: ModeReglement = ModeReglement.ESPECES
    compte_tresorerie_id: Optional[UUID] = None
    zone_prevue_id: Optional[UUID] = None
    objet: Optional[str] = Field(default=None, max_length=255)
    observations: Optional[str] = None


class AvanceLire(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero: str
    collecteur_id: UUID
    statut: StatutAvanceCollecteur
    date_remise: date
    montant_remis: Decimal
    montant_justifie: Decimal
    montant_rendu: Decimal
    montant_reste_du: Decimal
    mode_remise: ModeReglement
    objet: Optional[str] = None


# ---------------------------------------------------------------------------
# LIGNE DE COLLECTE (un achat au marche)
# ---------------------------------------------------------------------------
class LigneCollecteCreer(BaseModel):
    produit_id: UUID
    date_achat: date
    base_achat: BaseAchatMarche = BaseAchatMarche.AU_SAC
    nombre_sacs: Optional[int] = Field(default=None, gt=0)
    poids_nominal_sac_kg: Optional[Decimal] = Field(default=None, gt=0)
    quantite_kg: Optional[Decimal] = Field(default=None, gt=0)
    prix_unitaire: Decimal = Field(gt=0)
    nom_vendeur: Optional[str] = Field(default=None, max_length=180)
    telephone_vendeur: Optional[str] = Field(default=None, max_length=40)
    appreciation_qualite: AppreciationQualiteMarche = (
        AppreciationQualiteMarche.NON_APPRECIE
    )
    taux_humidite_marche: Optional[Decimal] = Field(default=None, ge=0, le=100)
    observations: Optional[str] = None

    @field_validator("nombre_sacs")
    @classmethod
    def sacs_obligatoires_si_au_sac(cls, v, info):
        base = info.data.get("base_achat")
        if base == BaseAchatMarche.AU_SAC and v is None:
            raise ValueError("nombre_sacs est obligatoire quand on achete au sac")
        return v


class LigneCollecteLire(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero_ligne: int
    produit_id: UUID
    date_achat: date
    base_achat: BaseAchatMarche
    nombre_sacs: Optional[int] = None
    poids_nominal_sac_kg: Optional[Decimal] = None
    quantite_kg: Optional[Decimal] = None
    prix_unitaire: Decimal
    montant: Decimal
    nom_vendeur: Optional[str] = None
    appreciation_qualite: AppreciationQualiteMarche
    taux_humidite_marche: Optional[Decimal] = None


# ---------------------------------------------------------------------------
# COLLECTE
# ---------------------------------------------------------------------------
class CollecteCreer(BaseModel):
    collecteur_id: UUID
    zone_id: UUID
    date_debut: date
    mode_detention: ModeDetention
    marge_fixe_tonne_appliquee: Optional[Decimal] = Field(default=None, ge=0)
    taux_commission_applique: Optional[Decimal] = Field(default=None, ge=0, le=1)
    avance_id: Optional[UUID] = None
    contrat_id: Optional[UUID] = None
    magasin_destination_id: Optional[UUID] = None
    campagne_agricole: Optional[str] = Field(default=None, max_length=20)
    frais_annexes: Decimal = Field(default=Decimal("0"), ge=0)
    observations: Optional[str] = None

    @field_validator("marge_fixe_tonne_appliquee")
    @classmethod
    def marge_obligatoire(cls, v, info):
        if info.data.get("mode_detention") == ModeDetention.MARGE_FIXE_TONNE and v is None:
            raise ValueError(
                "marge_fixe_tonne_appliquee est obligatoire en mode MARGE_FIXE_TONNE"
            )
        return v


class CollecteReceptionner(BaseModel):
    """Saisie a l'arrivee au magasin : c'est ici que l'ecart apparait."""

    magasin_destination_id: UUID
    date_reception_magasin: datetime
    nombre_sacs_expedies: Optional[int] = Field(default=None, ge=0)
    nombre_sacs_recus: int = Field(ge=0)
    poids_reel_kg: Decimal = Field(gt=0)
    taux_humidite_magasin: Optional[Decimal] = Field(default=None, ge=0, le=100)
    taux_impuretes_magasin: Optional[Decimal] = Field(default=None, ge=0, le=100)
    voyage_id: Optional[UUID] = None
    observations: Optional[str] = None


class CollecteLire(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    numero: str
    collecteur_id: UUID
    zone_id: UUID
    statut: StatutCollecte
    mode_detention: ModeDetention
    date_debut: date
    nombre_sacs_total: int
    poids_theorique_kg: Decimal
    poids_reel_kg: Optional[Decimal] = None
    ecart_poids_kg: Optional[Decimal] = None
    ecart_sacs: Optional[int] = None
    montant_achat_total: Decimal
    frais_annexes: Decimal
    taux_humidite_magasin: Optional[Decimal] = None
    lignes: List[LigneCollecteLire] = []


# ---------------------------------------------------------------------------
# TABLEAUX DE BORD
# ---------------------------------------------------------------------------
class SoldeCollecteur(BaseModel):
    """Reponse a : combien ce collecteur me doit-il ?"""

    collecteur_id: UUID
    nom: str
    total_avance: Decimal
    total_justifie: Decimal
    reste_du: Decimal
    nb_avances_ouvertes: int


class EcartCollecteur(BaseModel):
    """Reponse a : qui me coute de l'argent ?"""

    collecteur_id: UUID
    nom: str
    nb_collectes: int
    poids_theorique_kg: Decimal
    poids_reel_kg: Decimal
    ecart_kg: Decimal
    ecart_pourcentage: Optional[Decimal] = None
    valeur_ecart: Optional[Decimal] = None

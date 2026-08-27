"""
DML SARLU - ERP | MODULE 2
STOCKS & MULTI-MAGASINS (+ INTEGRATION IoT)
===========================================

Principes :
  * `Magasin` est arborescent (site -> sous-magasin) et peut etre VIRTUEL
    (stock en transit, stock detenu chez un tiers, rebut).
  * `Emplacement` est recursif : Zone > Allee > Rangee > Palette / Tas / Silo.
  * `MouvementStock` est l'unique source de verite du stock. Aucun stock n'est
    modifie sans mouvement : c'est un registre append-only (jamais de UPDATE
    de quantite hors extourne).
  * Un transfert inter-magasin genere DEUX mouvements (SORTIE puis ENTREE)
    relies par un `TransfertStock`, ce qui permet de gerer le stock en route.
  * L'IoT (ESP32 + DHT22/SHT31) alimente `MesureCapteur` via webhook, et le
    moteur de regles produit des `AlerteIoT` rattachees au tas concerne.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import (
    BaseModel,
    DocumentModel,
    EnumCol,
    Money,
    Quantity,
    Rate,
    ReferentielModel,
)
from .enums import (
    ModeDetention,
    CausePerte,
    Devise,
    MethodeValorisation,
    NiveauAlerte,
    SensMouvement,
    StatutCapteur,
    StatutLot,
    StatutValidation,
    TypeAlerteIoT,
    TypeCapteur,
    TypeEmplacement,
    TypeInventaire,
    TypeMagasin,
    TypeMouvementStock,
    UniteMesure,
)

if TYPE_CHECKING:
    from .achats import ReceptionBarriere
    from .logistique import Voyage
    from .rh_securite import AffectationMagasin, Employe
    from .ventes import BonLivraison


# ===========================================================================
# RESEAU DE MAGASINS
# ===========================================================================
class Magasin(ReferentielModel):
    """Entrepot physique ou virtuel."""

    __tablename__ = "magasins"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    nom: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    type_magasin: Mapped[TypeMagasin] = mapped_column(EnumCol(TypeMagasin), nullable=False, index=True)
    magasin_parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL"), index=True
    )

    # --- Localisation
    adresse: Mapped[Optional[str]] = mapped_column(Text)
    quartier: Mapped[Optional[str]] = mapped_column(String(120))
    ville: Mapped[str] = mapped_column(String(80), default="Douala", nullable=False, index=True)
    region: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    pays: Mapped[str] = mapped_column(String(60), default="Cameroun", nullable=False)
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))

    # --- Caracteristiques
    capacite_tonnes: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 3))
    surface_m2: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2))
    is_virtuel: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_sous_douane: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dispose_pont_bascule: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    dispose_iot: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # --- Gestion
    responsable_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="SET NULL"), index=True
    )
    telephone: Mapped[Optional[str]] = mapped_column(String(30))
    methode_valorisation: Mapped[MethodeValorisation] = mapped_column(
        EnumCol(MethodeValorisation), default=MethodeValorisation.CUMP, nullable=False
    )
    compte_stock_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )
    centre_cout: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    # --- Relations
    magasin_parent: Mapped[Optional["Magasin"]] = relationship(
        remote_side="Magasin.id", back_populates="sous_magasins"
    )
    sous_magasins: Mapped[List["Magasin"]] = relationship(back_populates="magasin_parent")
    responsable: Mapped[Optional["Employe"]] = relationship()
    emplacements: Mapped[List["Emplacement"]] = relationship(
        back_populates="magasin", cascade="all, delete-orphan"
    )
    lots: Mapped[List["Lot"]] = relationship(back_populates="magasin")
    capteurs: Mapped[List["Capteur"]] = relationship(back_populates="magasin")
    affectations: Mapped[List["AffectationMagasin"]] = relationship(back_populates="magasin")
    voyages_au_depart: Mapped[List["Voyage"]] = relationship(
        back_populates="magasin_depart", foreign_keys="Voyage.magasin_depart_id"
    )
    voyages_a_arrivee: Mapped[List["Voyage"]] = relationship(
        back_populates="magasin_arrivee", foreign_keys="Voyage.magasin_arrivee_id"
    )


class Emplacement(ReferentielModel):
    """Emplacement interne recursif : Zone > Allee > Rangee > Palette / Tas."""

    __tablename__ = "emplacements"

    magasin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="CASCADE"), nullable=False, index=True
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("emplacements.id", ondelete="CASCADE"), index=True
    )
    code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    libelle: Mapped[Optional[str]] = mapped_column(String(150))
    type_emplacement: Mapped[TypeEmplacement] = mapped_column(
        EnumCol(TypeEmplacement), nullable=False, index=True
    )
    chemin_complet: Mapped[Optional[str]] = mapped_column(
        String(255), index=True, comment="Ex: MAG-A/ZONE-1/ALLEE-3/TAS-07 (denormalise pour la recherche)"
    )
    niveau: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    capacite_tonnes: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3))
    quantite_actuelle: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    produit_dedie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="SET NULL")
    )
    is_bloque: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    code_barre: Mapped[Optional[str]] = mapped_column(String(80), unique=True, index=True)

    magasin: Mapped[Magasin] = relationship(back_populates="emplacements")
    parent: Mapped[Optional["Emplacement"]] = relationship(
        remote_side="Emplacement.id", back_populates="enfants"
    )
    enfants: Mapped[List["Emplacement"]] = relationship(back_populates="parent")
    capteurs: Mapped[List["Capteur"]] = relationship(back_populates="emplacement")

    __table_args__ = (
        UniqueConstraint("magasin_id", "code", name="uq_emplacement_magasin_code"),
    )


# ===========================================================================
# ARTICLES
# ===========================================================================
class FamilleProduit(ReferentielModel):
    """Cereales, oleagineux, legumineuses, intrants, emballages, consommables."""

    __tablename__ = "familles_produit"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    nom: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("familles_produit.id", ondelete="SET NULL")
    )
    description: Mapped[Optional[str]] = mapped_column(Text)

    parent: Mapped[Optional["FamilleProduit"]] = relationship(remote_side="FamilleProduit.id")
    produits: Mapped[List["Produit"]] = relationship(back_populates="famille")


class Produit(ReferentielModel):
    """
    Article negociable : Mais, Sorgho, Sesame, Arachide, Soja...
    Porte les seuils qualite qui pilotent le rejet automatique a la barriere.
    """

    __tablename__ = "produits"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    designation: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    nom_scientifique: Mapped[Optional[str]] = mapped_column(String(150))
    famille_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("familles_produit.id", ondelete="SET NULL"), index=True
    )
    variete: Mapped[Optional[str]] = mapped_column(String(120))
    origine_habituelle: Mapped[Optional[str]] = mapped_column(String(150))
    code_barre: Mapped[Optional[str]] = mapped_column(String(80), unique=True, index=True)
    code_sh: Mapped[Optional[str]] = mapped_column(String(20), comment="Nomenclature douaniere (systeme harmonise)")

    # --- Unites
    unite_base: Mapped[UniteMesure] = mapped_column(
        EnumCol(UniteMesure), default=UniteMesure.KG, nullable=False
    )
    poids_sac_kg: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), default=Decimal("100"))
    densite: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), comment="kg/m3, pour les silos")

    # --- SEUILS DE CONTROLE QUALITE (regle metier centrale)
    taux_humidite_max: Mapped[Decimal] = mapped_column(
        Numeric(5, 2),
        default=Decimal("14.00"),
        nullable=False,
        comment="Au-dela : rejet automatique a la barriere",
    )
    taux_humidite_optimal: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), default=Decimal("12.00"))
    taux_impuretes_max: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("2.00"), nullable=False
    )
    taux_grains_casses_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    taux_grains_moisis_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    poids_specifique_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), comment="kg/hl")

    # --- Conditions de stockage surveillees par IoT
    temperature_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    temperature_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), default=Decimal("30.00"))
    humidite_ambiante_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), default=Decimal("65.00"))
    duree_conservation_jours: Mapped[Optional[int]] = mapped_column(Integer)

    # --- Gestion
    gere_par_lot: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    seuil_alerte_stock: Mapped[Optional[Decimal]] = mapped_column(Quantity)
    stock_securite: Mapped[Optional[Decimal]] = mapped_column(Quantity)

    # --- Valorisation & comptabilite
    prix_achat_reference: Mapped[Optional[Decimal]] = mapped_column(Money)
    prix_vente_reference: Mapped[Optional[Decimal]] = mapped_column(Money)
    cump_global: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    taux_tva: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.1925"), nullable=False)
    compte_stock_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )
    compte_achat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )
    compte_vente_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )

    photo_url: Mapped[Optional[str]] = mapped_column(String(500))
    description: Mapped[Optional[str]] = mapped_column(Text)

    famille: Mapped[Optional[FamilleProduit]] = relationship(back_populates="produits")
    lots: Mapped[List["Lot"]] = relationship(back_populates="produit")
    mouvements: Mapped[List["MouvementStock"]] = relationship(back_populates="produit")

    __table_args__ = (
        CheckConstraint("taux_humidite_max > 0 AND taux_humidite_max <= 100", name="humidite_max_valide"),
    )


class Lot(ReferentielModel):
    """
    Lot de marchandise = unite de tracabilite. Cree a la reception apres
    controle qualite favorable, rattache a un emplacement precis.
    """

    __tablename__ = "lots"

    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    produit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    magasin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    emplacement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("emplacements.id", ondelete="SET NULL"), index=True
    )
    reception_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("receptions_barriere.id", ondelete="SET NULL"), index=True
    )
    fournisseur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="SET NULL"), index=True
    )
    lot_parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), comment="Issu d'un reconditionnement"
    )

    # --- Origine collecte village & statut juridique de la marchandise
    collecte_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("collectes.id", ondelete="SET NULL"), index=True
    )
    collecteur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("collecteurs.id", ondelete="SET NULL"), index=True
    )
    mode_detention: Mapped[ModeDetention] = mapped_column(
        EnumCol(ModeDetention), default=ModeDetention.PROPRIETE, nullable=False, index=True,
        comment="Ce lot appartient-il a DML ou est-il detenu pour un tiers ?"
    )

    # --- Quantites
    quantite_initiale: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    quantite_disponible: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False, index=True)
    quantite_reservee: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    nombre_sacs: Mapped[Optional[int]] = mapped_column(Integer)
    unite: Mapped[UniteMesure] = mapped_column(EnumCol(UniteMesure), default=UniteMesure.KG, nullable=False)

    # --- Valorisation
    cout_unitaire: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    valeur_stock: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    # --- Qualite a l'entree (figee)
    taux_humidite_entree: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    taux_impuretes_entree: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    campagne_agricole: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    region_origine: Mapped[Optional[str]] = mapped_column(String(120), index=True)

    # --- Cycle de vie
    date_entree: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    date_peremption: Mapped[Optional[date]] = mapped_column(Date, index=True)
    date_dernier_controle: Mapped[Optional[date]] = mapped_column(Date)
    statut: Mapped[StatutLot] = mapped_column(
        EnumCol(StatutLot), default=StatutLot.EN_QUARANTAINE, nullable=False, index=True
    )
    motif_blocage: Mapped[Optional[str]] = mapped_column(Text)

    produit: Mapped[Produit] = relationship(back_populates="lots")
    magasin: Mapped[Magasin] = relationship(back_populates="lots")
    emplacement: Mapped[Optional[Emplacement]] = relationship()
    mouvements: Mapped[List["MouvementStock"]] = relationship(back_populates="lot")

    @property
    def quantite_libre(self) -> Decimal:
        return self.quantite_disponible - self.quantite_reservee

    @property
    def age_jours(self) -> int:
        return (date.today() - self.date_entree).days

    __table_args__ = (
        CheckConstraint("quantite_disponible >= 0", name="quantite_lot_positive"),
        CheckConstraint("quantite_reservee >= 0", name="reservation_positive"),
        Index("ix_lots_produit_magasin_statut", "produit_id", "magasin_id", "statut"),
    )


# ===========================================================================
# MOUVEMENTS
# ===========================================================================
class MouvementStock(DocumentModel):
    """
    Registre unique des flux physiques. Append-only : une correction se fait
    par un mouvement inverse, jamais par modification.
    """

    __tablename__ = "mouvements_stock"

    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    type_mouvement: Mapped[TypeMouvementStock] = mapped_column(
        EnumCol(TypeMouvementStock), nullable=False, index=True
    )
    sens: Mapped[SensMouvement] = mapped_column(EnumCol(SensMouvement), nullable=False, index=True)
    date_mouvement: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )

    produit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), index=True
    )

    # --- Origine / destination (l'un ou l'autre selon le sens)
    magasin_source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="RESTRICT"), index=True
    )
    emplacement_source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("emplacements.id", ondelete="SET NULL")
    )
    magasin_destination_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="RESTRICT"), index=True
    )
    emplacement_destination_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("emplacements.id", ondelete="SET NULL")
    )

    # --- Quantites et valorisation
    quantite: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unite: Mapped[UniteMesure] = mapped_column(EnumCol(UniteMesure), default=UniteMesure.KG, nullable=False)
    nombre_sacs: Mapped[Optional[int]] = mapped_column(Integer)
    cout_unitaire: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    valeur_totale: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    stock_avant: Mapped[Optional[Decimal]] = mapped_column(Quantity)
    stock_apres: Mapped[Optional[Decimal]] = mapped_column(Quantity)

    # --- Rattachements documentaires
    reception_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("receptions_barriere.id", ondelete="SET NULL"), index=True
    )
    bon_livraison_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bons_livraison.id", ondelete="SET NULL"), index=True
    )
    transfert_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("transferts_stock.id", ondelete="SET NULL"), index=True
    )
    inventaire_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventaires.id", ondelete="SET NULL")
    )
    declaration_perte_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("declarations_perte.id", ondelete="SET NULL")
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="SET NULL"), index=True
    )
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )

    mouvement_extourne_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("mouvements_stock.id", ondelete="SET NULL")
    )
    motif: Mapped[Optional[str]] = mapped_column(Text)
    reference_externe: Mapped[Optional[str]] = mapped_column(String(80))
    is_valide: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    valide_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    date_validation: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    produit: Mapped[Produit] = relationship(back_populates="mouvements")
    lot: Mapped[Optional[Lot]] = relationship(back_populates="mouvements")
    magasin_source: Mapped[Optional[Magasin]] = relationship(foreign_keys=[magasin_source_id])
    magasin_destination: Mapped[Optional[Magasin]] = relationship(foreign_keys=[magasin_destination_id])
    transfert: Mapped[Optional["TransfertStock"]] = relationship(back_populates="mouvements")

    __table_args__ = (
        CheckConstraint("quantite > 0", name="quantite_mouvement_positive"),
        Index("ix_mouvements_produit_date", "produit_id", "date_mouvement"),
        Index("ix_mouvements_type_date", "type_mouvement", "date_mouvement"),
    )


class TransfertStock(DocumentModel):
    """
    Transfert inter-magasins. Entre l'expedition et la reception, la
    marchandise vit dans un magasin virtuel "EN TRANSIT" -> tracabilite totale
    et detection des ecarts de route.
    """

    __tablename__ = "transferts_stock"

    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    magasin_source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    magasin_destination_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="SET NULL"), index=True
    )
    date_expedition: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    date_reception: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    quantite_expediee: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    quantite_recue: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    ecart_quantite: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    valeur_transferee: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    statut: Mapped[StatutValidation] = mapped_column(
        EnumCol(StatutValidation), default=StatutValidation.BROUILLON, nullable=False, index=True
    )
    expediteur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    receptionnaire_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    motif: Mapped[Optional[str]] = mapped_column(Text)

    lignes: Mapped[List["LigneTransfert"]] = relationship(
        back_populates="transfert", cascade="all, delete-orphan"
    )
    mouvements: Mapped[List[MouvementStock]] = relationship(back_populates="transfert")

    __table_args__ = (
        CheckConstraint("magasin_source_id <> magasin_destination_id", name="transfert_magasins_distincts"),
    )


class LigneTransfert(BaseModel):
    __tablename__ = "lignes_transfert"

    transfert_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("transferts_stock.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False
    )
    lot_source_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL")
    )
    lot_destination_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL")
    )
    quantite_expediee: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    quantite_recue: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    ecart: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    cout_unitaire: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    transfert: Mapped[TransfertStock] = relationship(back_populates="lignes")


class DeclarationPerte(DocumentModel):
    """Pertes, coulages, freintes : formalisees et validees hierarchiquement."""

    __tablename__ = "declarations_perte"

    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    magasin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    emplacement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("emplacements.id", ondelete="SET NULL")
    )
    produit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), index=True
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="SET NULL"), comment="Si freinte de transport"
    )
    date_constat: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    cause: Mapped[CausePerte] = mapped_column(EnumCol(CausePerte), nullable=False, index=True)
    quantite_perdue: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    taux_perte: Mapped[Optional[Decimal]] = mapped_column(Rate, comment="% du lot")
    valeur_perte: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    responsable_presume_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="SET NULL")
    )
    is_imputee: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Retenue sur salaire ou sur solde chauffeur"
    )
    photos_urls: Mapped[Optional[dict]] = mapped_column(JSON)
    statut: Mapped[StatutValidation] = mapped_column(
        EnumCol(StatutValidation), default=StatutValidation.SOUMIS, nullable=False, index=True
    )
    validateur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )

    __table_args__ = (CheckConstraint("quantite_perdue > 0", name="perte_positive"),)


class Inventaire(DocumentModel):
    """Inventaire tournant, annuel ou ponctuel."""

    __tablename__ = "inventaires"

    numero: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    magasin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    type_inventaire: Mapped[TypeInventaire] = mapped_column(EnumCol(TypeInventaire), nullable=False)
    date_inventaire: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    date_cloture: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    statut: Mapped[StatutValidation] = mapped_column(
        EnumCol(StatutValidation), default=StatutValidation.BROUILLON, nullable=False, index=True
    )
    nombre_references: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    valeur_theorique: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    valeur_physique: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    ecart_valeur: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    equipe: Mapped[Optional[dict]] = mapped_column(JSON, comment="Liste des agents compteurs")
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )
    observations: Mapped[Optional[str]] = mapped_column(Text)

    lignes: Mapped[List["LigneInventaire"]] = relationship(
        back_populates="inventaire", cascade="all, delete-orphan"
    )


class LigneInventaire(BaseModel):
    __tablename__ = "lignes_inventaire"

    inventaire_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("inventaires.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False
    )
    lot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL")
    )
    emplacement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("emplacements.id", ondelete="SET NULL")
    )
    quantite_theorique: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    quantite_physique: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    ecart_quantite: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    cout_unitaire: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    ecart_valeur: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cause_ecart: Mapped[Optional[CausePerte]] = mapped_column(EnumCol(CausePerte))
    compteur_1: Mapped[Optional[str]] = mapped_column(String(120))
    compteur_2: Mapped[Optional[str]] = mapped_column(String(120))
    observations: Mapped[Optional[str]] = mapped_column(Text)

    inventaire: Mapped[Inventaire] = relationship(back_populates="lignes")


# ===========================================================================
# INTEGRATION IoT (ESP32)
# ===========================================================================
class Capteur(ReferentielModel):
    """
    Sonde connectee installee sur un tas / une zone / un silo.
    L'authentification du webhook se fait par `cle_api_hash` + `identifiant_device`.
    """

    __tablename__ = "capteurs"

    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    identifiant_device: Mapped[str] = mapped_column(
        String(80), unique=True, nullable=False, index=True, comment="Chip ID / MAC de l'ESP32"
    )
    libelle: Mapped[str] = mapped_column(String(150), nullable=False)
    type_capteur: Mapped[TypeCapteur] = mapped_column(EnumCol(TypeCapteur), nullable=False, index=True)
    modele_materiel: Mapped[Optional[str]] = mapped_column(String(80), comment="DHT22, SHT31, PZEM-004T...")
    version_firmware: Mapped[Optional[str]] = mapped_column(String(40))

    magasin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="CASCADE"), nullable=False, index=True
    )
    emplacement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("emplacements.id", ondelete="SET NULL"), index=True
    )
    position_description: Mapped[Optional[str]] = mapped_column(String(255))

    # --- Securite du webhook
    cle_api_hash: Mapped[Optional[str]] = mapped_column(String(255))
    is_authentifie: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Parametrage
    intervalle_emission_s: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    seuil_temperature_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    seuil_temperature_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2), default=Decimal("30.00"))
    seuil_humidite_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    seuil_humidite_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), default=Decimal("65.00"))
    delai_silence_alerte_s: Mapped[int] = mapped_column(
        Integer, default=1800, nullable=False, comment="Au-dela : alerte CAPTEUR_MUET"
    )

    # --- Etat courant (denormalise pour le dashboard temps reel)
    statut: Mapped[StatutCapteur] = mapped_column(
        EnumCol(StatutCapteur), default=StatutCapteur.ACTIF, nullable=False, index=True
    )
    derniere_communication: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    derniere_temperature: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    derniere_humidite: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    niveau_batterie: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    rssi: Mapped[Optional[int]] = mapped_column(Integer)

    date_installation: Mapped[Optional[date]] = mapped_column(Date)
    date_derniere_calibration: Mapped[Optional[date]] = mapped_column(Date)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    magasin: Mapped[Magasin] = relationship(back_populates="capteurs")
    emplacement: Mapped[Optional[Emplacement]] = relationship(back_populates="capteurs")
    mesures: Mapped[List["MesureCapteur"]] = relationship(
        back_populates="capteur", cascade="all, delete-orphan"
    )
    alertes: Mapped[List["AlerteIoT"]] = relationship(back_populates="capteur", cascade="all, delete-orphan")


class MesureCapteur(BaseModel):
    """
    Serie temporelle brute recue par webhook POST /api/v1/iot/mesures.
    Table a fort volume : envisager TimescaleDB ou un partitionnement mensuel.
    """

    __tablename__ = "mesures_capteur"

    capteur_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("capteurs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    horodatage: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    horodatage_reception: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    temperature: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    humidite: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    co2_ppm: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    niveau_cm: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    poids_kg: Mapped[Optional[Decimal]] = mapped_column(Quantity)
    tension_batterie: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 3))
    rssi: Mapped[Optional[int]] = mapped_column(Integer)
    lot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), index=True
    )
    is_hors_seuil: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    score_anomalie: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 5), comment="Sortie du detecteur (Isolation Forest / EWMA)"
    )
    payload_brut: Mapped[Optional[dict]] = mapped_column(JSON)

    capteur: Mapped[Capteur] = relationship(back_populates="mesures")

    __table_args__ = (
        Index("ix_mesures_capteur_id_horodatage", "capteur_id", "horodatage"),
        UniqueConstraint("capteur_id", "horodatage", name="uq_mesure_capteur_horodatage"),
    )


class AlerteIoT(BaseModel):
    """Alerte generee par le moteur de regles ou le detecteur d'anomalies."""

    __tablename__ = "alertes_iot"

    capteur_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("capteurs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mesure_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("mesures_capteur.id", ondelete="SET NULL")
    )
    lot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), index=True
    )
    magasin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL"), index=True
    )
    type_alerte: Mapped[TypeAlerteIoT] = mapped_column(EnumCol(TypeAlerteIoT), nullable=False, index=True)
    niveau: Mapped[NiveauAlerte] = mapped_column(EnumCol(NiveauAlerte), nullable=False, index=True)
    date_declenchement: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )
    valeur_mesuree: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3))
    seuil_reference: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 3))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    is_acquittee: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    acquittee_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    date_acquittement: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    action_corrective: Mapped[Optional[str]] = mapped_column(Text)
    notification_envoyee: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    capteur: Mapped[Capteur] = relationship(back_populates="alertes")

    __table_args__ = (Index("ix_alertes_iot_niveau_date", "niveau", "date_declenchement"),)

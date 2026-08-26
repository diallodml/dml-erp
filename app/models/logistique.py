"""
DML SARLU - ERP | MODULE 1
LOGISTIQUE, FLOTTE & CHAUFFEURS
===============================

Coeur operationnel. Le `Voyage` (feuille de route) est le pivot analytique :
il agrege le chauffeur, le camion, les magasins, la marchandise, les depenses
de route et le rattachement comptable. Toute depense terrain remonte ici.
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
    CategoriePermis,
    Devise,
    NiveauAlerte,
    ProprieteActif,
    StatutChauffeur,
    StatutMaintenance,
    StatutValidation,
    StatutVehicule,
    StatutVoyage,
    TypeCarburant,
    TypeChauffeur,
    TypeDepenseVoyage,
    TypeDocumentVehicule,
    TypeIncident,
    TypeMaintenance,
    TypeVehicule,
    TypeVoyage,
)

if TYPE_CHECKING:
    from .achats import Fournisseur, ReceptionBarriere
    from .rh_securite import Employe
    from .stocks import Magasin
    from .ventes import BonLivraison, Client


# ===========================================================================
# CHAUFFEURS
# ===========================================================================
class Chauffeur(ReferentielModel):
    """
    Chauffeur interne (lie a un `Employe`) ou externe (lie a un transporteur
    sous-traitant enregistre comme `Fournisseur`).
    """

    __tablename__ = "chauffeurs"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    type_chauffeur: Mapped[TypeChauffeur] = mapped_column(
        EnumCol(TypeChauffeur), nullable=False, index=True
    )

    # Interne -> employe_id renseigne ; Externe -> identite portee ici
    employe_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="SET NULL"), unique=True, index=True
    )
    sous_traitant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="SET NULL"), index=True
    )

    nom: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    prenom: Mapped[Optional[str]] = mapped_column(String(100))
    date_naissance: Mapped[Optional[date]] = mapped_column(Date)
    numero_cni: Mapped[Optional[str]] = mapped_column(String(40), index=True)
    telephone: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    telephone_secondaire: Mapped[Optional[str]] = mapped_column(String(30))
    contact_urgence_nom: Mapped[Optional[str]] = mapped_column(String(120))
    contact_urgence_tel: Mapped[Optional[str]] = mapped_column(String(30))
    adresse: Mapped[Optional[str]] = mapped_column(Text)
    ville_base: Mapped[str] = mapped_column(String(80), default="Douala", nullable=False)
    photo_url: Mapped[Optional[str]] = mapped_column(String(500))

    # --- Exploitation
    statut: Mapped[StatutChauffeur] = mapped_column(
        EnumCol(StatutChauffeur), default=StatutChauffeur.DISPONIBLE, nullable=False, index=True
    )
    vehicule_habituel_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vehicules.id", ondelete="SET NULL", use_alter=True, name="fk_chauffeur_vehicule_habituel"),
        index=True,
    )
    date_recrutement: Mapped[Optional[date]] = mapped_column(Date)
    annees_experience: Mapped[Optional[int]] = mapped_column(Integer)
    zones_maitrisees: Mapped[Optional[str]] = mapped_column(
        Text, comment="Axes couverts : Douala-Ngaoundere, Douala-Garoua..."
    )

    # --- Indicateurs de performance (recalcules par batch)
    nombre_voyages: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kilometrage_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("0"), nullable=False)
    tonnage_total_transporte: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    taux_ponctualite: Mapped[Optional[Decimal]] = mapped_column(Rate)
    note_globale: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2), comment="Note /20")
    nombre_incidents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    consommation_moyenne: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 2), comment="Litres / 100 km observes"
    )

    # --- Finance
    solde_avances: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False, comment="Avances non justifiees en circulation"
    )
    compte_tiers_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )

    motif_blacklist: Mapped[Optional[str]] = mapped_column(Text)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    # --- Relations
    employe: Mapped[Optional["Employe"]] = relationship(back_populates="chauffeur")
    sous_traitant: Mapped[Optional["Fournisseur"]] = relationship(back_populates="chauffeurs")
    vehicule_habituel: Mapped[Optional["Vehicule"]] = relationship(
        foreign_keys=[vehicule_habituel_id], post_update=True
    )
    permis: Mapped[List["PermisConduire"]] = relationship(
        back_populates="chauffeur", cascade="all, delete-orphan", order_by="desc(PermisConduire.date_expiration)"
    )
    voyages: Mapped[List["Voyage"]] = relationship(
        back_populates="chauffeur", foreign_keys="Voyage.chauffeur_id"
    )
    evaluations: Mapped[List["EvaluationChauffeur"]] = relationship(
        back_populates="chauffeur", cascade="all, delete-orphan"
    )

    @property
    def nom_complet(self) -> str:
        return f"{self.nom} {self.prenom or ''}".strip()

    @property
    def permis_valide(self) -> bool:
        aujourdhui = date.today()
        return any(p.is_actif and p.date_expiration >= aujourdhui for p in self.permis)

    __table_args__ = (
        CheckConstraint(
            "(type_chauffeur <> 'INTERNE') OR (employe_id IS NOT NULL)",
            name="chauffeur_interne_doit_avoir_employe",
        ),
        Index("ix_chauffeurs_statut_type", "statut", "type_chauffeur"),
    )


class PermisConduire(BaseModel):
    """Historisation des permis (renouvellements successifs)."""

    __tablename__ = "permis_conduire"

    chauffeur_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chauffeurs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    categories: Mapped[str] = mapped_column(
        String(40), nullable=False, comment="Categories cumulees, ex: 'B,C,E'"
    )
    categorie_principale: Mapped[CategoriePermis] = mapped_column(
        EnumCol(CategoriePermis, length=10), nullable=False
    )
    pays_delivrance: Mapped[str] = mapped_column(String(60), default="Cameroun", nullable=False)
    lieu_delivrance: Mapped[Optional[str]] = mapped_column(String(120))
    date_delivrance: Mapped[date] = mapped_column(Date, nullable=False)
    date_expiration: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    is_actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    scan_url: Mapped[Optional[str]] = mapped_column(String(500))
    alerte_jours_avant: Mapped[int] = mapped_column(Integer, default=30, nullable=False)

    chauffeur: Mapped[Chauffeur] = relationship(back_populates="permis")

    @property
    def jours_avant_expiration(self) -> int:
        return (self.date_expiration - date.today()).days

    __table_args__ = (
        UniqueConstraint("chauffeur_id", "numero", name="uq_permis_chauffeur_numero"),
        CheckConstraint("date_expiration > date_delivrance", name="permis_dates_coherentes"),
    )


class EvaluationChauffeur(DocumentModel):
    """Evaluation periodique de performance."""

    __tablename__ = "evaluations_chauffeur"

    chauffeur_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chauffeurs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    periode_debut: Mapped[date] = mapped_column(Date, nullable=False)
    periode_fin: Mapped[date] = mapped_column(Date, nullable=False)
    note_ponctualite: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    note_entretien_vehicule: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    note_consommation: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    note_respect_procedures: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    note_relation_client: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    note_justification_frais: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    note_globale: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2), index=True)
    points_forts: Mapped[Optional[str]] = mapped_column(Text)
    axes_amelioration: Mapped[Optional[str]] = mapped_column(Text)
    evaluateur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )

    chauffeur: Mapped[Chauffeur] = relationship(back_populates="evaluations")


# ===========================================================================
# FLOTTE
# ===========================================================================
class Vehicule(ReferentielModel):
    """Camion, tracteur, remorque ou vehicule leger."""

    __tablename__ = "vehicules"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    immatriculation: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    type_vehicule: Mapped[TypeVehicule] = mapped_column(EnumCol(TypeVehicule), nullable=False, index=True)
    marque: Mapped[Optional[str]] = mapped_column(String(60))
    modele: Mapped[Optional[str]] = mapped_column(String(60))
    annee_fabrication: Mapped[Optional[int]] = mapped_column(Integer)
    numero_chassis: Mapped[Optional[str]] = mapped_column(String(60), unique=True, index=True)
    numero_moteur: Mapped[Optional[str]] = mapped_column(String(60))
    couleur: Mapped[Optional[str]] = mapped_column(String(40))

    # --- Capacites
    charge_utile_tonnes: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3))
    poids_vide_kg: Mapped[Optional[Decimal]] = mapped_column(Quantity, comment="Tare de reference")
    ptac_kg: Mapped[Optional[Decimal]] = mapped_column(Quantity, comment="Poids total autorise en charge")
    volume_m3: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    nombre_essieux: Mapped[Optional[int]] = mapped_column(Integer)

    # --- Carburant / consommation
    type_carburant: Mapped[TypeCarburant] = mapped_column(
        EnumCol(TypeCarburant), default=TypeCarburant.GASOIL, nullable=False
    )
    capacite_reservoir_l: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    consommation_reference: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 2), comment="Litres / 100 km de reference constructeur ou historique"
    )

    # --- Exploitation
    statut: Mapped[StatutVehicule] = mapped_column(
        EnumCol(StatutVehicule), default=StatutVehicule.DISPONIBLE, nullable=False, index=True
    )
    kilometrage_actuel: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), nullable=False, index=True
    )
    date_dernier_releve_km: Mapped[Optional[date]] = mapped_column(Date)
    magasin_rattachement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL"), index=True
    )
    remorque_attelee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("vehicules.id", ondelete="SET NULL", use_alter=True, name="fk_vehicule_remorque"),
    )

    # --- Propriete & immobilisation
    propriete: Mapped[ProprieteActif] = mapped_column(
        EnumCol(ProprieteActif), default=ProprieteActif.PROPRE, nullable=False, index=True
    )
    sous_traitant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="SET NULL"), index=True
    )
    date_acquisition: Mapped[Optional[date]] = mapped_column(Date)
    valeur_acquisition: Mapped[Optional[Decimal]] = mapped_column(Money)
    duree_amortissement_annees: Mapped[Optional[int]] = mapped_column(Integer)
    compte_immobilisation_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )
    valeur_nette_comptable: Mapped[Optional[Decimal]] = mapped_column(Money)

    # --- Telematique / IoT (option boitier GPS)
    identifiant_tracker: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    derniere_position_lat: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))
    derniere_position_lng: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))
    derniere_position_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    observations: Mapped[Optional[str]] = mapped_column(Text)

    # --- Relations
    sous_traitant: Mapped[Optional["Fournisseur"]] = relationship(back_populates="vehicules")
    remorque_attelee: Mapped[Optional["Vehicule"]] = relationship(
        remote_side="Vehicule.id", foreign_keys=[remorque_attelee_id], post_update=True
    )
    documents: Mapped[List["DocumentVehicule"]] = relationship(
        back_populates="vehicule", cascade="all, delete-orphan"
    )
    maintenances: Mapped[List["Maintenance"]] = relationship(
        back_populates="vehicule", cascade="all, delete-orphan"
    )
    plans_maintenance: Mapped[List["PlanMaintenance"]] = relationship(
        back_populates="vehicule", cascade="all, delete-orphan"
    )
    voyages: Mapped[List["Voyage"]] = relationship(
        back_populates="vehicule", foreign_keys="Voyage.vehicule_id"
    )
    ravitaillements: Mapped[List["RavitaillementCarburant"]] = relationship(
        back_populates="vehicule", cascade="all, delete-orphan"
    )

    @property
    def documents_expires(self) -> List["DocumentVehicule"]:
        return [d for d in self.documents if d.is_expire]

    __table_args__ = (
        CheckConstraint("kilometrage_actuel >= 0", name="km_positif"),
        Index("ix_vehicules_statut_type", "statut", "type_vehicule"),
    )


class DocumentVehicule(BaseModel):
    """Assurance, visite technique, carte grise, licence de transport, vignette."""

    __tablename__ = "documents_vehicule"

    vehicule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vehicules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type_document: Mapped[TypeDocumentVehicule] = mapped_column(
        EnumCol(TypeDocumentVehicule), nullable=False, index=True
    )
    numero: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    emetteur: Mapped[Optional[str]] = mapped_column(String(180), comment="Compagnie d'assurance, centre technique")
    fournisseur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="SET NULL")
    )
    date_debut: Mapped[date] = mapped_column(Date, nullable=False)
    date_expiration: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    montant: Mapped[Optional[Decimal]] = mapped_column(Money)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    alerte_jours_avant: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    is_actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    fichier_url: Mapped[Optional[str]] = mapped_column(String(500))
    observations: Mapped[Optional[str]] = mapped_column(Text)

    vehicule: Mapped[Vehicule] = relationship(back_populates="documents")

    @property
    def jours_avant_expiration(self) -> int:
        return (self.date_expiration - date.today()).days

    @property
    def is_expire(self) -> bool:
        return self.date_expiration < date.today()

    @property
    def niveau_alerte(self) -> NiveauAlerte:
        jours = self.jours_avant_expiration
        if jours < 0:
            return NiveauAlerte.URGENCE
        if jours <= 7:
            return NiveauAlerte.CRITIQUE
        if jours <= self.alerte_jours_avant:
            return NiveauAlerte.ATTENTION
        return NiveauAlerte.INFO

    __table_args__ = (
        Index("ix_doc_vehicule_type_expiration", "type_document", "date_expiration"),
        CheckConstraint("date_expiration >= date_debut", name="doc_vehicule_dates_coherentes"),
    )


class PlanMaintenance(BaseModel):
    """Regle d'echeance preventive (ex: vidange tous les 10 000 km ou 6 mois)."""

    __tablename__ = "plans_maintenance"

    vehicule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vehicules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    libelle: Mapped[str] = mapped_column(String(180), nullable=False)
    type_maintenance: Mapped[TypeMaintenance] = mapped_column(EnumCol(TypeMaintenance), nullable=False)
    periodicite_km: Mapped[Optional[int]] = mapped_column(Integer)
    periodicite_jours: Mapped[Optional[int]] = mapped_column(Integer)
    dernier_km_execute: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    derniere_date_execution: Mapped[Optional[date]] = mapped_column(Date)
    prochain_km: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2), index=True)
    prochaine_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    seuil_alerte_km: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    seuil_alerte_jours: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    is_actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    vehicule: Mapped[Vehicule] = relationship(back_populates="plans_maintenance")


class Maintenance(DocumentModel):
    """Intervention d'entretien ou de reparation."""

    __tablename__ = "maintenances"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    vehicule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vehicules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    plan_maintenance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("plans_maintenance.id", ondelete="SET NULL")
    )
    type_maintenance: Mapped[TypeMaintenance] = mapped_column(
        EnumCol(TypeMaintenance), nullable=False, index=True
    )
    date_entree_atelier: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_sortie_atelier: Mapped[Optional[date]] = mapped_column(Date)
    kilometrage: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    description_panne: Mapped[Optional[str]] = mapped_column(Text)
    travaux_realises: Mapped[Optional[str]] = mapped_column(Text)
    pieces_remplacees: Mapped[Optional[dict]] = mapped_column(JSON)

    prestataire_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="SET NULL"), index=True
    )
    cout_pieces: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cout_main_oeuvre: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cout_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    immobilisation_jours: Mapped[Optional[int]] = mapped_column(Integer)
    statut: Mapped[StatutMaintenance] = mapped_column(
        EnumCol(StatutMaintenance), default=StatutMaintenance.PLANIFIEE, nullable=False, index=True
    )
    prochaine_echeance_km: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    prochaine_echeance_date: Mapped[Optional[date]] = mapped_column(Date)
    facture_achat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("factures_achat.id", ondelete="SET NULL")
    )
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )

    vehicule: Mapped[Vehicule] = relationship(back_populates="maintenances")


# ===========================================================================
# VOYAGES / FEUILLES DE ROUTE
# ===========================================================================
class Voyage(DocumentModel):
    """
    Feuille de route : unite de gestion operationnelle ET analytique.
    Rattache marchandise, ressources (chauffeur/camion), frais et comptabilite.
    """

    __tablename__ = "voyages"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    type_voyage: Mapped[TypeVoyage] = mapped_column(EnumCol(TypeVoyage), nullable=False, index=True)
    statut: Mapped[StatutVoyage] = mapped_column(
        EnumCol(StatutVoyage), default=StatutVoyage.PLANIFIE, nullable=False, index=True
    )

    # --- Ressources
    chauffeur_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chauffeurs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    chauffeur_second_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chauffeurs.id", ondelete="SET NULL")
    )
    apprenti_nom: Mapped[Optional[str]] = mapped_column(String(120))
    vehicule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vehicules.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    remorque_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vehicules.id", ondelete="SET NULL")
    )

    # --- Itineraire
    magasin_depart_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL"), index=True
    )
    magasin_arrivee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL"), index=True
    )
    lieu_depart: Mapped[str] = mapped_column(String(180), nullable=False)
    lieu_arrivee: Mapped[str] = mapped_column(String(180), nullable=False)
    itineraire_detail: Mapped[Optional[str]] = mapped_column(Text, comment="Etapes intermediaires")
    distance_prevue_km: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))
    distance_reelle_km: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))

    # --- Tiers concerne
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), index=True
    )
    fournisseur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="SET NULL"), index=True
    )

    # --- Chronologie
    date_depart_prevue: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    date_depart_reelle: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    date_arrivee_prevue: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    date_arrivee_reelle: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    date_cloture: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # --- Compteurs & carburant
    kilometrage_depart: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    kilometrage_arrivee: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    carburant_litres: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0"), nullable=False)
    carburant_montant: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    consommation_constatee: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))

    # --- Marchandise
    tonnage_prevu: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    tonnage_charge: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    tonnage_livre: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    ecart_tonnage: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    designation_marchandise: Mapped[Optional[str]] = mapped_column(String(255))

    # --- Budget & finance
    budget_alloue: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    avance_versee: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_depenses: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    solde_chauffeur: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False, comment="Positif = a rembourser au chauffeur"
    )
    prix_transport_facture: Mapped[Optional[Decimal]] = mapped_column(
        Money, comment="Si transport refacture (client ou sous-traitance)"
    )
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )

    # --- Documents & suivi
    numero_lettre_voiture: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    scan_feuille_route_url: Mapped[Optional[str]] = mapped_column(String(500))
    responsable_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    observations: Mapped[Optional[str]] = mapped_column(Text)

    # --- Relations
    chauffeur: Mapped[Chauffeur] = relationship(back_populates="voyages", foreign_keys=[chauffeur_id])
    chauffeur_second: Mapped[Optional[Chauffeur]] = relationship(foreign_keys=[chauffeur_second_id])
    vehicule: Mapped[Vehicule] = relationship(back_populates="voyages", foreign_keys=[vehicule_id])
    remorque: Mapped[Optional[Vehicule]] = relationship(foreign_keys=[remorque_id])
    magasin_depart: Mapped[Optional["Magasin"]] = relationship(
        foreign_keys=[magasin_depart_id], back_populates="voyages_au_depart"
    )
    magasin_arrivee: Mapped[Optional["Magasin"]] = relationship(
        foreign_keys=[magasin_arrivee_id], back_populates="voyages_a_arrivee"
    )
    depenses: Mapped[List["DepenseVoyage"]] = relationship(
        back_populates="voyage", cascade="all, delete-orphan"
    )
    ravitaillements: Mapped[List["RavitaillementCarburant"]] = relationship(back_populates="voyage")
    incidents: Mapped[List["IncidentVoyage"]] = relationship(
        back_populates="voyage", cascade="all, delete-orphan"
    )
    positions: Mapped[List["PositionVoyage"]] = relationship(
        back_populates="voyage", cascade="all, delete-orphan"
    )
    receptions: Mapped[List["ReceptionBarriere"]] = relationship(back_populates="voyage")
    bons_livraison: Mapped[List["BonLivraison"]] = relationship(back_populates="voyage")

    @property
    def duree_heures(self) -> Optional[Decimal]:
        if self.date_depart_reelle and self.date_arrivee_reelle:
            delta = self.date_arrivee_reelle - self.date_depart_reelle
            return Decimal(delta.total_seconds()) / Decimal(3600)
        return None

    @property
    def cout_par_tonne(self) -> Optional[Decimal]:
        if self.tonnage_livre and self.tonnage_livre > 0:
            return self.total_depenses / self.tonnage_livre
        return None

    __table_args__ = (
        Index("ix_voyages_statut_depart", "statut", "date_depart_prevue"),
        Index("ix_voyages_chauffeur_date", "chauffeur_id", "date_depart_reelle"),
        CheckConstraint("tonnage_charge >= 0 AND tonnage_livre >= 0", name="tonnages_positifs"),
    )


class DepenseVoyage(DocumentModel):
    """Frais de route : peage, carburant, perdiem, manutention, escorte..."""

    __tablename__ = "depenses_voyage"

    voyage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type_depense: Mapped[TypeDepenseVoyage] = mapped_column(
        EnumCol(TypeDepenseVoyage), nullable=False, index=True
    )
    libelle: Mapped[str] = mapped_column(String(255), nullable=False)
    date_depense: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    lieu: Mapped[Optional[str]] = mapped_column(String(180))
    montant: Mapped[Decimal] = mapped_column(Money, nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    paye_par_chauffeur: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, comment="Sinon paye directement par le siege"
    )
    compte_tresorerie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_tresorerie.id", ondelete="SET NULL")
    )
    categorie_depense_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories_depense.id", ondelete="SET NULL")
    )

    justificatif_url: Mapped[Optional[str]] = mapped_column(String(500))
    numero_recu: Mapped[Optional[str]] = mapped_column(String(80))
    is_justifie: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    statut: Mapped[StatutValidation] = mapped_column(
        EnumCol(StatutValidation), default=StatutValidation.SOUMIS, nullable=False, index=True
    )
    validateur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )
    observations: Mapped[Optional[str]] = mapped_column(Text)

    voyage: Mapped[Voyage] = relationship(back_populates="depenses")

    __table_args__ = (CheckConstraint("montant >= 0", name="montant_depense_positif"),)


class RavitaillementCarburant(DocumentModel):
    """Plein de carburant : base du calcul de consommation et detection de coulage."""

    __tablename__ = "ravitaillements_carburant"

    vehicule_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vehicules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="SET NULL"), index=True
    )
    chauffeur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chauffeurs.id", ondelete="SET NULL")
    )
    date_ravitaillement: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    station: Mapped[Optional[str]] = mapped_column(String(180))
    fournisseur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="SET NULL")
    )
    quantite_litres: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    prix_unitaire: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    montant: Mapped[Decimal] = mapped_column(Money, nullable=False)
    kilometrage: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    is_plein_complet: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    numero_bon: Mapped[Optional[str]] = mapped_column(String(80))
    justificatif_url: Mapped[Optional[str]] = mapped_column(String(500))
    consommation_calculee: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(8, 2), comment="L/100km depuis le plein precedent"
    )
    is_anomalie: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True, comment="Ecart > seuil vs reference"
    )

    vehicule: Mapped[Vehicule] = relationship(back_populates="ravitaillements")
    voyage: Mapped[Optional[Voyage]] = relationship(back_populates="ravitaillements")

    __table_args__ = (CheckConstraint("quantite_litres > 0", name="litres_positifs"),)


class IncidentVoyage(DocumentModel):
    """Panne, accident, controle routier, perte de marchandise."""

    __tablename__ = "incidents_voyage"

    voyage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type_incident: Mapped[TypeIncident] = mapped_column(EnumCol(TypeIncident), nullable=False, index=True)
    date_incident: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    lieu: Mapped[Optional[str]] = mapped_column(String(180))
    gravite: Mapped[NiveauAlerte] = mapped_column(
        EnumCol(NiveauAlerte), default=NiveauAlerte.ATTENTION, nullable=False
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    mesures_prises: Mapped[Optional[str]] = mapped_column(Text)
    retard_genere_heures: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    quantite_perdue: Mapped[Optional[Decimal]] = mapped_column(Quantity)
    cout_estime: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    responsabilite_chauffeur: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    declare_assurance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    numero_sinistre: Mapped[Optional[str]] = mapped_column(String(80))
    photos_urls: Mapped[Optional[dict]] = mapped_column(JSON)

    voyage: Mapped[Voyage] = relationship(back_populates="incidents")


class PositionVoyage(BaseModel):
    """
    Trace GPS remontee par le mobile du chauffeur (Flutter) ou un boitier
    telematique. Volume eleve : partitionnement recommande en production.
    """

    __tablename__ = "positions_voyage"

    voyage_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    horodatage: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    vitesse_kmh: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    altitude_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    precision_m: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2))
    source: Mapped[str] = mapped_column(String(30), default="MOBILE", nullable=False)

    voyage: Mapped[Voyage] = relationship(back_populates="positions")

    __table_args__ = (Index("ix_positions_voyage_id_horodatage", "voyage_id", "horodatage"),)

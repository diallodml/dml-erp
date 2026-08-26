"""
DML SARLU - ERP | MODULE 6
RESSOURCES HUMAINES & SECURITE (RBAC)
=====================================

Points d'architecture :
  * `Utilisateur` (compte de connexion) est distinct de `Employe` (personne
    physique dans les effectifs) : un chauffeur sous-traitant peut avoir un
    compte sans etre salarie, un manutentionnaire journalier peut etre
    salarie sans compte.
  * Le RBAC est a 3 niveaux : Role -> Permission -> Portee de donnees.
    C'est la `PorteeDonnees` qui implemente l'exigence "un chauffeur ne voit
    que sa feuille de route, un magasinier que son magasin".
  * `AffectationMagasin` materialise le perimetre physique d'un utilisateur.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import (
    Base,
    BaseModel,
    DocumentModel,
    EnumCol,
    Money,
    Rate,
    ReferentielModel,
)
from .enums import (
    Devise,
    ModeReglement,
    PorteeDonnees,
    Sexe,
    SituationMatrimoniale,
    StatutEmploye,
    StatutPointage,
    StatutValidation,
    TypeAbsence,
    TypeAction,
    TypeContrat,
)

if TYPE_CHECKING:
    from .logistique import Chauffeur, Voyage
    from .stocks import Magasin


# ===========================================================================
# TABLES D'ASSOCIATION
# ===========================================================================
role_permission_table = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
    Column("permission_id", Uuid(as_uuid=True), ForeignKey("permissions.id", ondelete="CASCADE"), primary_key=True),
)

utilisateur_role_table = Table(
    "utilisateur_roles",
    Base.metadata,
    Column("utilisateur_id", Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Uuid(as_uuid=True), ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)


# ===========================================================================
# SECURITE / RBAC
# ===========================================================================
class Permission(BaseModel):
    """
    Permission atomique, identifiee par un code canonique :
        `<module>.<ressource>.<action>`   ex: "stocks.mouvement.valider"
    """

    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    ressource: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[TypeAction] = mapped_column(EnumCol(TypeAction), nullable=False)
    libelle: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_sensible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    roles: Mapped[List["Role"]] = relationship(
        secondary=role_permission_table, back_populates="permissions"
    )

    __table_args__ = (Index("ix_permissions_module_ressource", "module", "ressource"),)


class Role(ReferentielModel):
    """Role metier : DG, DAF, Comptable, Chef magasinier, Chauffeur, Agent barriere..."""

    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    nom: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    niveau_hierarchique: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    portee_par_defaut: Mapped[PorteeDonnees] = mapped_column(
        EnumCol(PorteeDonnees), default=PorteeDonnees.MAGASIN_AFFECTE, nullable=False
    )
    is_systeme: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    plafond_validation: Mapped[Optional[Decimal]] = mapped_column(
        Money, comment="Montant maximal validable sans escalade hierarchique"
    )

    permissions: Mapped[List[Permission]] = relationship(
        secondary=role_permission_table, back_populates="roles", lazy="selectin"
    )
    utilisateurs: Mapped[List["Utilisateur"]] = relationship(
        secondary=utilisateur_role_table, back_populates="roles"
    )


class Utilisateur(BaseModel):
    """Compte de connexion a l'ERP."""

    __tablename__ = "utilisateurs"

    login: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(180), unique=True, index=True)
    telephone: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    mot_de_passe_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    nom_affichage: Mapped[str] = mapped_column(String(180), nullable=False)

    employe_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="SET NULL"), unique=True, index=True
    )

    # --- Etat du compte
    is_actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_superadmin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    doit_changer_mdp: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mfa_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_secret: Mapped[Optional[str]] = mapped_column(String(64))

    # --- Portee de donnees effective (surcharge le role si renseignee)
    portee_donnees: Mapped[Optional[PorteeDonnees]] = mapped_column(EnumCol(PorteeDonnees))

    # --- Traçabilite des connexions
    derniere_connexion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    derniere_ip: Mapped[Optional[str]] = mapped_column(String(60))
    tentatives_echouees: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    verrouille_jusqu_a: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # --- Preferences
    langue: Mapped[str] = mapped_column(String(5), default="fr", nullable=False)
    token_fcm: Mapped[Optional[str]] = mapped_column(String(255), comment="Push mobile Flutter")

    employe: Mapped[Optional["Employe"]] = relationship(back_populates="utilisateur", foreign_keys=[employe_id])
    roles: Mapped[List[Role]] = relationship(
        secondary=utilisateur_role_table, back_populates="utilisateurs", lazy="selectin"
    )
    affectations_magasin: Mapped[List["AffectationMagasin"]] = relationship(
        back_populates="utilisateur",
        cascade="all, delete-orphan",
        foreign_keys="AffectationMagasin.utilisateur_id",
    )


class AffectationMagasin(BaseModel):
    """
    Perimetre physique d'un utilisateur.
    Un magasinier avec portee MAGASIN_AFFECTE ne peut lire/ecrire que sur les
    magasins listes ici (filtre applique dans la couche repository FastAPI).
    """

    __tablename__ = "affectations_magasin"

    utilisateur_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    magasin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="CASCADE"), nullable=False, index=True
    )
    is_principal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    peut_valider: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    date_debut: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    date_fin: Mapped[Optional[date]] = mapped_column(Date)

    utilisateur: Mapped[Utilisateur] = relationship(
        back_populates="affectations_magasin", foreign_keys=[utilisateur_id]
    )
    magasin: Mapped["Magasin"] = relationship(back_populates="affectations")

    __table_args__ = (
        UniqueConstraint("utilisateur_id", "magasin_id", "date_debut", name="uq_affectation_user_magasin"),
    )


class JournalAudit(BaseModel):
    """
    Piste d'audit inalterable : qui a fait quoi, sur quel enregistrement,
    avec quelles valeurs avant/apres. Exigence de controle interne et OHADA.
    """

    __tablename__ = "journal_audit"

    utilisateur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL"), index=True
    )
    horodatage: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    action: Mapped[TypeAction] = mapped_column(EnumCol(TypeAction), nullable=False)
    table_cible: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    enregistrement_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), index=True)
    valeurs_avant: Mapped[Optional[dict]] = mapped_column(JSON)
    valeurs_apres: Mapped[Optional[dict]] = mapped_column(JSON)
    adresse_ip: Mapped[Optional[str]] = mapped_column(String(60))
    user_agent: Mapped[Optional[str]] = mapped_column(String(255))
    commentaire: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (Index("ix_audit_table_date", "table_cible", "horodatage"),)


# ===========================================================================
# PERSONNEL
# ===========================================================================
class Departement(ReferentielModel):
    """Direction / service : Logistique, Magasin, Achats, Commercial, Compta, DG."""

    __tablename__ = "departements"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    nom: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    responsable_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("employes.id", ondelete="SET NULL", use_alter=True, name="fk_departement_responsable"),
    )
    centre_cout: Mapped[Optional[str]] = mapped_column(String(30), comment="Code analytique")

    employes: Mapped[List["Employe"]] = relationship(
        back_populates="departement", foreign_keys="Employe.departement_id"
    )
    responsable: Mapped[Optional["Employe"]] = relationship(foreign_keys=[responsable_id], post_update=True)


class Employe(ReferentielModel):
    """Personne physique aux effectifs de DML SARLU."""

    __tablename__ = "employes"

    matricule: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    nom: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    prenom: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    sexe: Mapped[Optional[Sexe]] = mapped_column(EnumCol(Sexe))
    date_naissance: Mapped[Optional[date]] = mapped_column(Date)
    lieu_naissance: Mapped[Optional[str]] = mapped_column(String(120))
    nationalite: Mapped[str] = mapped_column(String(60), default="Camerounaise", nullable=False)
    situation_matrimoniale: Mapped[Optional[SituationMatrimoniale]] = mapped_column(
        EnumCol(SituationMatrimoniale)
    )
    nombre_enfants: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- Identification legale
    numero_cni: Mapped[Optional[str]] = mapped_column(String(40), unique=True, index=True)
    date_expiration_cni: Mapped[Optional[date]] = mapped_column(Date)
    numero_cnps: Mapped[Optional[str]] = mapped_column(String(40), index=True)
    niu: Mapped[Optional[str]] = mapped_column(String(30), comment="Numero identifiant unique DGI")

    # --- Coordonnees
    telephone: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    telephone_urgence: Mapped[Optional[str]] = mapped_column(String(30))
    email: Mapped[Optional[str]] = mapped_column(String(180))
    adresse: Mapped[Optional[str]] = mapped_column(Text)
    quartier: Mapped[Optional[str]] = mapped_column(String(100))
    ville: Mapped[str] = mapped_column(String(80), default="Douala", nullable=False)

    # --- Contrat
    departement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("departements.id", ondelete="SET NULL"), index=True
    )
    poste: Mapped[str] = mapped_column(String(120), nullable=False)
    type_contrat: Mapped[TypeContrat] = mapped_column(EnumCol(TypeContrat), nullable=False)
    categorie_professionnelle: Mapped[Optional[str]] = mapped_column(String(20), comment="Convention collective")
    date_embauche: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_fin_contrat: Mapped[Optional[date]] = mapped_column(Date, index=True)
    date_sortie: Mapped[Optional[date]] = mapped_column(Date)
    motif_sortie: Mapped[Optional[str]] = mapped_column(String(255))
    statut: Mapped[StatutEmploye] = mapped_column(
        EnumCol(StatutEmploye), default=StatutEmploye.ACTIF, nullable=False, index=True
    )
    superieur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="SET NULL")
    )

    # --- Remuneration
    salaire_base: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    prime_transport: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    prime_logement: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    autres_primes: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    mode_paiement_salaire: Mapped[ModeReglement] = mapped_column(
        EnumCol(ModeReglement), default=ModeReglement.ESPECES, nullable=False
    )
    numero_compte_bancaire: Mapped[Optional[str]] = mapped_column(String(60))
    numero_mobile_money: Mapped[Optional[str]] = mapped_column(String(30))

    # --- Comptabilite auxiliaire
    compte_tiers_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )

    photo_url: Mapped[Optional[str]] = mapped_column(String(500))
    observations: Mapped[Optional[str]] = mapped_column(Text)

    # --- Relations
    departement: Mapped[Optional[Departement]] = relationship(
        back_populates="employes", foreign_keys=[departement_id]
    )
    superieur: Mapped[Optional["Employe"]] = relationship(remote_side="Employe.id", foreign_keys=[superieur_id])
    utilisateur: Mapped[Optional[Utilisateur]] = relationship(
        back_populates="employe", uselist=False, foreign_keys="Utilisateur.employe_id"
    )
    chauffeur: Mapped[Optional["Chauffeur"]] = relationship(back_populates="employe", uselist=False)
    pointages: Mapped[List["Pointage"]] = relationship(back_populates="employe", cascade="all, delete-orphan")
    absences: Mapped[List["Absence"]] = relationship(
        back_populates="employe", cascade="all, delete-orphan", foreign_keys="Absence.employe_id"
    )
    avances: Mapped[List["AvanceSalaire"]] = relationship(
        back_populates="employe", cascade="all, delete-orphan", foreign_keys="AvanceSalaire.employe_id"
    )
    bulletins: Mapped[List["BulletinPaie"]] = relationship(back_populates="employe", cascade="all, delete-orphan")

    @property
    def nom_complet(self) -> str:
        return f"{self.nom} {self.prenom or ''}".strip()

    @property
    def salaire_brut_theorique(self) -> Decimal:
        return (
            self.salaire_base + self.prime_transport + self.prime_logement + self.autres_primes
        )

    __table_args__ = (
        Index("ix_employes_nom_prenom", "nom", "prenom"),
        CheckConstraint("salaire_base >= 0", name="salaire_base_positif"),
    )


class Pointage(BaseModel):
    """Presence journaliere."""

    __tablename__ = "pointages"

    employe_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date_pointage: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    heure_arrivee: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    heure_depart: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    statut: Mapped[StatutPointage] = mapped_column(
        EnumCol(StatutPointage), default=StatutPointage.PRESENT, nullable=False, index=True
    )
    retard_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    heures_travaillees: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"), nullable=False)
    heures_supplementaires: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"), nullable=False)
    magasin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL"), index=True
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="SET NULL")
    )
    saisi_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    observations: Mapped[Optional[str]] = mapped_column(Text)

    employe: Mapped[Employe] = relationship(back_populates="pointages")

    __table_args__ = (
        UniqueConstraint("employe_id", "date_pointage", name="uq_pointage_employe_jour"),
    )


class Absence(DocumentModel):
    """Conges, maladies, permissions, sanctions."""

    __tablename__ = "absences"

    employe_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type_absence: Mapped[TypeAbsence] = mapped_column(EnumCol(TypeAbsence), nullable=False, index=True)
    date_debut: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_fin: Mapped[date] = mapped_column(Date, nullable=False)
    nombre_jours: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    is_remuneree: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    motif: Mapped[Optional[str]] = mapped_column(Text)
    justificatif_url: Mapped[Optional[str]] = mapped_column(String(500))
    statut: Mapped[StatutValidation] = mapped_column(
        EnumCol(StatutValidation), default=StatutValidation.SOUMIS, nullable=False, index=True
    )
    validateur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    date_validation: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    motif_refus: Mapped[Optional[str]] = mapped_column(Text)

    employe: Mapped[Employe] = relationship(back_populates="absences", foreign_keys=[employe_id])

    __table_args__ = (CheckConstraint("date_fin >= date_debut", name="periode_absence_coherente"),)


class AvanceSalaire(DocumentModel):
    """
    Avance sur salaire. Genere un decaissement de tresorerie et une retenue
    echelonnee sur les bulletins de paie suivants.
    """

    __tablename__ = "avances_salaire"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    employe_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    date_demande: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    date_versement: Mapped[Optional[date]] = mapped_column(Date)
    montant: Mapped[Decimal] = mapped_column(Money, nullable=False)
    motif: Mapped[Optional[str]] = mapped_column(Text)
    mode_reglement: Mapped[ModeReglement] = mapped_column(
        EnumCol(ModeReglement), default=ModeReglement.ESPECES, nullable=False
    )
    compte_tresorerie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_tresorerie.id", ondelete="SET NULL"), index=True
    )
    nombre_echeances: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    retenue_mensuelle: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_rembourse: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    statut: Mapped[StatutValidation] = mapped_column(
        EnumCol(StatutValidation), default=StatutValidation.SOUMIS, nullable=False, index=True
    )
    validateur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )

    employe: Mapped[Employe] = relationship(back_populates="avances", foreign_keys=[employe_id])

    @property
    def solde_restant(self) -> Decimal:
        return self.montant - self.montant_rembourse

    __table_args__ = (CheckConstraint("montant > 0", name="montant_avance_positif"),)


class BulletinPaie(DocumentModel):
    """Bulletin de paie mensuel (bases CNPS / IRPP / CFC / FNE Cameroun)."""

    __tablename__ = "bulletins_paie"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    employe_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    periode_annee: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    periode_mois: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    date_paiement: Mapped[Optional[date]] = mapped_column(Date)

    jours_travailles: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"), nullable=False)
    heures_supplementaires: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("0"), nullable=False)

    salaire_base: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    primes: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    heures_sup_montant: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    salaire_brut: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    base_cotisable: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    # --- Retenues salariales
    cnps_salarie: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    irpp: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cac: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cfc_salarie: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    redevance_audiovisuelle: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    retenue_avances: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    autres_retenues: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_retenues: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    # --- Charges patronales
    cnps_patronal: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cfc_patronal: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    fne: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_charges_patronales: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    net_a_payer: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    mode_reglement: Mapped[ModeReglement] = mapped_column(
        EnumCol(ModeReglement), default=ModeReglement.ESPECES, nullable=False
    )
    compte_tresorerie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_tresorerie.id", ondelete="SET NULL")
    )
    statut: Mapped[StatutValidation] = mapped_column(
        EnumCol(StatutValidation), default=StatutValidation.BROUILLON, nullable=False, index=True
    )
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )
    detail_calcul: Mapped[Optional[dict]] = mapped_column(JSON, comment="Trace du moteur de paie")

    employe: Mapped[Employe] = relationship(back_populates="bulletins")

    __table_args__ = (
        UniqueConstraint("employe_id", "periode_annee", "periode_mois", name="uq_bulletin_employe_periode"),
        CheckConstraint("periode_mois BETWEEN 1 AND 12", name="mois_valide"),
    )

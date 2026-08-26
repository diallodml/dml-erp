"""
DML SARLU - ERP | MODULE 5
FINANCE & COMPTABILITE (SYSCOHADA revise)
=========================================

Trois exigences structurantes :

1. PARTIE DOUBLE STRICTE
   `EcritureComptable` (piece) + `LigneEcriture` (debit/credit).
   Une ecriture validee est immuable : toute correction passe par une
   extourne. Le controle total_debit == total_credit est contraint en base.

2. SEPARATION "DOUBLE TIROIR"
   Chaque `CompteTresorerie` et chaque `MouvementTresorerie` porte un `Tiroir`
   (ENTREPRISE ou ASSOCIE). Les prelevements du PDG transitent par
   `CompteCourantAssocie` (compte 462 SYSCOHADA), jamais par les charges.
   C'est ce qui rend la DSF defendable en cas de controle.

3. PREPARATION DE LA LIASSE FISCALE (DSF)
   `BalanceCompte` stocke les soldes periodiques ; `PosteDSF` +
   `MappingPosteDSF` decrivent la ventilation des comptes vers les postes
   du bilan, du compte de resultat et du TAFIRE.
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
    Rate,
    ReferentielModel,
)
from .enums import (
    ClasseCompte,
    Devise,
    ModeReglement,
    OperateurMobileMoney,
    SensCompte,
    SensTresorerie,
    StatutDeclarationFiscale,
    StatutEcriture,
    StatutExercice,
    StatutValidation,
    TableauDSF,
    Tiroir,
    TypeCompte,
    TypeCompteTresorerie,
    TypeImpot,
    TypeJournal,
    TypeMouvementCompteCourant,
    TypeOrigineEcriture,
)

if TYPE_CHECKING:
    from .rh_securite import Employe


# ===========================================================================
# REFERENTIEL COMPTABLE
# ===========================================================================
class ExerciceComptable(BaseModel):
    __tablename__ = "exercices_comptables"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    libelle: Mapped[str] = mapped_column(String(120), nullable=False)
    date_debut: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_fin: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    statut: Mapped[StatutExercice] = mapped_column(
        EnumCol(StatutExercice), default=StatutExercice.OUVERT, nullable=False, index=True
    )
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    date_cloture_effective: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    cloture_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    resultat_net: Mapped[Optional[Decimal]] = mapped_column(Money)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    ecritures: Mapped[List["EcritureComptable"]] = relationship(back_populates="exercice")

    __table_args__ = (CheckConstraint("date_fin > date_debut", name="exercice_dates_coherentes"),)


class CompteOHADA(ReferentielModel):
    """
    Plan comptable SYSCOHADA revise, arborescent.
    Exemples utiles a DML : 311 (stocks marchandises), 401 (fournisseurs),
    411 (clients), 462 (associes, comptes courants), 521 (banques),
    571 (caisse), 601 (achats), 624 (transports), 701 (ventes).
    """

    __tablename__ = "comptes_ohada"

    numero: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    intitule: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    classe: Mapped[ClasseCompte] = mapped_column(EnumCol(ClasseCompte, length=5), nullable=False, index=True)
    type_compte: Mapped[TypeCompte] = mapped_column(
        EnumCol(TypeCompte), default=TypeCompte.GENERAL, nullable=False, index=True
    )
    compte_parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL"), index=True
    )
    niveau: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_collectif: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Compte de regroupement, non mouvementable"
    )
    is_mouvementable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_lettrable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sens_normal: Mapped[Optional[SensCompte]] = mapped_column(EnumCol(SensCompte))
    solde_debiteur: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    solde_crediteur: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    compte_parent: Mapped[Optional["CompteOHADA"]] = relationship(
        remote_side="CompteOHADA.id", back_populates="sous_comptes"
    )
    sous_comptes: Mapped[List["CompteOHADA"]] = relationship(back_populates="compte_parent")
    lignes: Mapped[List["LigneEcriture"]] = relationship(back_populates="compte")

    @property
    def solde(self) -> Decimal:
        return self.solde_debiteur - self.solde_crediteur


class JournalComptable(ReferentielModel):
    __tablename__ = "journaux_comptables"

    code: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    libelle: Mapped[str] = mapped_column(String(120), nullable=False)
    type_journal: Mapped[TypeJournal] = mapped_column(EnumCol(TypeJournal), nullable=False, index=True)
    compte_contrepartie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )
    compte_tresorerie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("comptes_tresorerie.id", ondelete="SET NULL", use_alter=True, name="fk_journal_tresorerie"),
    )
    prefixe_numerotation: Mapped[Optional[str]] = mapped_column(String(10))
    dernier_numero: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    ecritures: Mapped[List["EcritureComptable"]] = relationship(back_populates="journal")


# ===========================================================================
# TRESORERIE (multi-caisses / multi-banques / mobile money)
# ===========================================================================
class CompteTresorerie(ReferentielModel):
    """
    Caisse physique, coffre, compte bancaire ou portefeuille Mobile Money.
    Le champ `tiroir` materialise la separation patrimoniale.
    """

    __tablename__ = "comptes_tresorerie"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    libelle: Mapped[str] = mapped_column(String(150), nullable=False)
    type_compte: Mapped[TypeCompteTresorerie] = mapped_column(
        EnumCol(TypeCompteTresorerie), nullable=False, index=True
    )
    tiroir: Mapped[Tiroir] = mapped_column(
        EnumCol(Tiroir), default=Tiroir.ENTREPRISE, nullable=False, index=True
    )

    # --- Banque
    nom_banque: Mapped[Optional[str]] = mapped_column(String(150))
    numero_compte: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    rib_iban: Mapped[Optional[str]] = mapped_column(String(60))
    code_swift: Mapped[Optional[str]] = mapped_column(String(20))
    agence: Mapped[Optional[str]] = mapped_column(String(120))

    # --- Mobile Money
    operateur_mm: Mapped[Optional[OperateurMobileMoney]] = mapped_column(EnumCol(OperateurMobileMoney))
    numero_telephone: Mapped[Optional[str]] = mapped_column(String(30), index=True)

    # --- Caisse
    magasin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL"), index=True
    )
    caissier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="SET NULL")
    )
    plafond_encaisse: Mapped[Optional[Decimal]] = mapped_column(
        Money, comment="Seuil au-dela duquel un versement en banque est requis"
    )

    # --- Soldes
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    solde_initial: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    solde_actuel: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False, index=True)
    solde_theorique: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    date_dernier_rapprochement: Mapped[Optional[date]] = mapped_column(Date)

    compte_comptable_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )
    compte_courant_associe_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("comptes_courants_associes.id", ondelete="SET NULL", use_alter=True, name="fk_tresorerie_cca"),
        comment="Renseigne si tiroir = ASSOCIE",
    )
    autorise_decouvert: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    mouvements: Mapped[List["MouvementTresorerie"]] = relationship(back_populates="compte")

    __table_args__ = (
        CheckConstraint(
            "(tiroir <> 'ASSOCIE') OR (compte_courant_associe_id IS NOT NULL)",
            name="tiroir_associe_exige_compte_courant",
        ),
        Index("ix_tresorerie_type_tiroir", "type_compte", "tiroir"),
    )


class CompteCourantAssocie(ReferentielModel):
    """
    Compte courant d'associe (SYSCOHADA 4621).
    Toute somme avancee ou prelevee par le PDG y est enregistree, ce qui
    evite la confusion avec la tresorerie sociale et les charges de l'entreprise.
    """

    __tablename__ = "comptes_courants_associes"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    nom_associe: Mapped[str] = mapped_column(String(180), nullable=False)
    employe_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="SET NULL")
    )
    qualite: Mapped[Optional[str]] = mapped_column(String(120), comment="Gerant, associe unique...")
    part_capital: Mapped[Optional[Decimal]] = mapped_column(Rate)
    compte_comptable_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    solde: Mapped[Decimal] = mapped_column(
        Money,
        default=Decimal("0"),
        nullable=False,
        comment="Positif = la societe doit a l'associe ; negatif = l'associe doit a la societe",
    )
    total_apports: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_retraits: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    is_remunere: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    taux_interet: Mapped[Optional[Decimal]] = mapped_column(Rate)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    mouvements: Mapped[List["MouvementCompteCourant"]] = relationship(
        back_populates="compte_courant", cascade="all, delete-orphan"
    )


class MouvementCompteCourant(DocumentModel):
    """Apport, retrait ou remboursement sur le compte courant d'associe."""

    __tablename__ = "mouvements_compte_courant"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    compte_courant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_courants_associes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type_mouvement: Mapped[TypeMouvementCompteCourant] = mapped_column(
        EnumCol(TypeMouvementCompteCourant), nullable=False, index=True
    )
    date_mouvement: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    montant: Mapped[Decimal] = mapped_column(Money, nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    libelle: Mapped[str] = mapped_column(String(255), nullable=False)
    compte_tresorerie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_tresorerie.id", ondelete="SET NULL"), index=True
    )
    mode_reglement: Mapped[Optional[ModeReglement]] = mapped_column(EnumCol(ModeReglement))
    solde_avant: Mapped[Optional[Decimal]] = mapped_column(Money)
    solde_apres: Mapped[Optional[Decimal]] = mapped_column(Money)
    justificatif_url: Mapped[Optional[str]] = mapped_column(String(500))
    statut: Mapped[StatutValidation] = mapped_column(
        EnumCol(StatutValidation), default=StatutValidation.VALIDE, nullable=False
    )
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )
    observations: Mapped[Optional[str]] = mapped_column(Text)

    compte_courant: Mapped[CompteCourantAssocie] = relationship(back_populates="mouvements")

    __table_args__ = (CheckConstraint("montant > 0", name="montant_cca_positif"),)


class CategorieDepense(ReferentielModel):
    """Nature analytique d'une charge, reliee a un compte OHADA de classe 6."""

    __tablename__ = "categories_depense"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    libelle: Mapped[str] = mapped_column(String(150), nullable=False)
    compte_charge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories_depense.id", ondelete="SET NULL")
    )
    is_deductible_fiscalement: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    exige_justificatif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    plafond_sans_validation: Mapped[Optional[Decimal]] = mapped_column(Money)
    description: Mapped[Optional[str]] = mapped_column(Text)

    parent: Mapped[Optional["CategorieDepense"]] = relationship(remote_side="CategorieDepense.id")


class MouvementTresorerie(DocumentModel):
    """
    Flux d'encaissement / decaissement. Vue "tresorier" complementaire de la
    comptabilite generale. Chaque mouvement pointe vers son document d'origine.
    """

    __tablename__ = "mouvements_tresorerie"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    compte_tresorerie_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_tresorerie.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    date_mouvement: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    date_valeur: Mapped[Optional[date]] = mapped_column(Date)
    sens: Mapped[SensTresorerie] = mapped_column(EnumCol(SensTresorerie), nullable=False, index=True)
    montant: Mapped[Decimal] = mapped_column(Money, nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    taux_change: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("1"), nullable=False)
    libelle: Mapped[str] = mapped_column(String(255), nullable=False)
    tiroir: Mapped[Tiroir] = mapped_column(
        EnumCol(Tiroir), default=Tiroir.ENTREPRISE, nullable=False, index=True
    )
    mode_reglement: Mapped[Optional[ModeReglement]] = mapped_column(EnumCol(ModeReglement))
    beneficiaire: Mapped[Optional[str]] = mapped_column(String(200))
    categorie_depense_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("categories_depense.id", ondelete="SET NULL"), index=True
    )

    # --- Rattachement au document d'origine
    reglement_client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reglements_client.id", ondelete="SET NULL"), index=True
    )
    reglement_fournisseur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("reglements_fournisseur.id", ondelete="SET NULL"), index=True
    )
    depense_voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("depenses_voyage.id", ondelete="SET NULL"), index=True
    )
    avance_salaire_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("avances_salaire.id", ondelete="SET NULL")
    )
    bulletin_paie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bulletins_paie.id", ondelete="SET NULL")
    )
    mouvement_compte_courant_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("mouvements_compte_courant.id", ondelete="SET NULL")
    )
    transfert_tresorerie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("transferts_tresorerie.id", ondelete="SET NULL"), index=True
    )
    declaration_fiscale_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("declarations_fiscales.id", ondelete="SET NULL")
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="SET NULL"), comment="Axe analytique"
    )
    magasin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL"), comment="Axe analytique"
    )

    solde_avant: Mapped[Optional[Decimal]] = mapped_column(Money)
    solde_apres: Mapped[Optional[Decimal]] = mapped_column(Money)
    reference_piece: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    justificatif_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_rapproche: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    date_rapprochement: Mapped[Optional[date]] = mapped_column(Date)
    is_valide: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL"), index=True
    )

    compte: Mapped[CompteTresorerie] = relationship(back_populates="mouvements")

    __table_args__ = (
        CheckConstraint("montant > 0", name="montant_tresorerie_positif"),
        Index("ix_tresorerie_compte_date", "compte_tresorerie_id", "date_mouvement"),
        Index("ix_tresorerie_tiroir_date", "tiroir", "date_mouvement"),
    )


class TransfertTresorerie(DocumentModel):
    """
    Virement interne : caisse -> banque, banque -> mobile money, ou
    tresorerie entreprise <-> compte courant associe (mouvement sensible,
    systematiquement justifie).
    """

    __tablename__ = "transferts_tresorerie"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    compte_source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_tresorerie.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    compte_destination_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_tresorerie.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    date_transfert: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    montant: Mapped[Decimal] = mapped_column(Money, nullable=False)
    frais: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    motif: Mapped[str] = mapped_column(String(255), nullable=False)
    is_inter_tiroir: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True, comment="Alerte de controle interne si vrai"
    )
    reference: Mapped[Optional[str]] = mapped_column(String(120))
    justificatif_url: Mapped[Optional[str]] = mapped_column(String(500))
    statut: Mapped[StatutValidation] = mapped_column(
        EnumCol(StatutValidation), default=StatutValidation.VALIDE, nullable=False
    )
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint("compte_source_id <> compte_destination_id", name="transfert_comptes_distincts"),
        CheckConstraint("montant > 0", name="montant_transfert_positif"),
    )


# ===========================================================================
# COMPTABILITE GENERALE
# ===========================================================================
class EcritureComptable(DocumentModel):
    """
    Piece comptable. Le lien vers le document metier d'origine est
    polymorphe (`origine_type` + `origine_id`) afin d'eviter des cycles de
    cles etrangeres : ce sont les documents qui portent `ecriture_id`.
    """

    __tablename__ = "ecritures_comptables"

    numero_piece: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    journal_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("journaux_comptables.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    exercice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("exercices_comptables.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    date_ecriture: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    date_piece: Mapped[Optional[date]] = mapped_column(Date)
    libelle: Mapped[str] = mapped_column(String(255), nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(120), index=True)

    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    taux_change: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("1"), nullable=False)
    total_debit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    total_credit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    tiroir: Mapped[Tiroir] = mapped_column(
        EnumCol(Tiroir), default=Tiroir.ENTREPRISE, nullable=False, index=True
    )
    statut: Mapped[StatutEcriture] = mapped_column(
        EnumCol(StatutEcriture), default=StatutEcriture.BROUILLON, nullable=False, index=True
    )
    date_validation: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    valide_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )

    # --- Origine (lien polymorphe, sans FK pour eviter les cycles)
    origine_type: Mapped[TypeOrigineEcriture] = mapped_column(
        EnumCol(TypeOrigineEcriture), default=TypeOrigineEcriture.SAISIE_MANUELLE, nullable=False, index=True
    )
    origine_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid(as_uuid=True), index=True)

    ecriture_extournee_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )
    piece_jointe_url: Mapped[Optional[str]] = mapped_column(String(500))
    observations: Mapped[Optional[str]] = mapped_column(Text)

    journal: Mapped[JournalComptable] = relationship(back_populates="ecritures")
    exercice: Mapped[ExerciceComptable] = relationship(back_populates="ecritures")
    lignes: Mapped[List["LigneEcriture"]] = relationship(
        back_populates="ecriture", cascade="all, delete-orphan", order_by="LigneEcriture.ordre"
    )

    @property
    def is_equilibree(self) -> bool:
        return self.total_debit == self.total_credit

    __table_args__ = (
        CheckConstraint("total_debit = total_credit", name="ecriture_equilibree"),
        Index("ix_ecritures_journal_date", "journal_id", "date_ecriture"),
        Index("ix_ecritures_origine", "origine_type", "origine_id"),
    )


class LigneEcriture(BaseModel):
    """
    Ligne de la partie double, enrichie des axes analytiques de DML
    (magasin, voyage, vehicule) pour produire des marges par site et par camion.
    """

    __tablename__ = "lignes_ecriture"

    ecriture_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordre: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    compte_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    libelle: Mapped[str] = mapped_column(String(255), nullable=False)
    debit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    credit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    sens: Mapped[SensCompte] = mapped_column(EnumCol(SensCompte), nullable=False)

    # --- Comptes auxiliaires
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), index=True
    )
    fournisseur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="SET NULL"), index=True
    )
    employe_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("employes.id", ondelete="SET NULL"), index=True
    )

    # --- Axes analytiques
    magasin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL"), index=True
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="SET NULL"), index=True
    )
    vehicule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vehicules.id", ondelete="SET NULL"), index=True
    )
    produit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="SET NULL"), index=True
    )
    centre_cout: Mapped[Optional[str]] = mapped_column(String(30), index=True)

    # --- Lettrage
    code_lettrage: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    date_lettrage: Mapped[Optional[date]] = mapped_column(Date)
    date_echeance: Mapped[Optional[date]] = mapped_column(Date, index=True)

    ecriture: Mapped[EcritureComptable] = relationship(back_populates="lignes")
    compte: Mapped[CompteOHADA] = relationship(back_populates="lignes")

    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0", name="montants_ligne_positifs"),
        CheckConstraint(
            "(debit = 0 AND credit > 0) OR (debit > 0 AND credit = 0)",
            name="ligne_debit_ou_credit_exclusif",
        ),
        Index("ix_lignes_ecriture_compte_lettrage", "compte_id", "code_lettrage"),
    )


# ===========================================================================
# FISCALITE & LIASSE (DSF)
# ===========================================================================
class DeclarationFiscale(DocumentModel):
    """TVA mensuelle, IRPP, CNPS, acomptes IS, patente, DSF annuelle."""

    __tablename__ = "declarations_fiscales"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    type_impot: Mapped[TypeImpot] = mapped_column(EnumCol(TypeImpot), nullable=False, index=True)
    exercice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("exercices_comptables.id", ondelete="SET NULL"), index=True
    )
    periode_annee: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    periode_mois: Mapped[Optional[int]] = mapped_column(Integer, index=True)
    date_echeance: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_depot: Mapped[Optional[date]] = mapped_column(Date)
    date_paiement: Mapped[Optional[date]] = mapped_column(Date)

    base_imposable: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_du: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_credit: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False, comment="Credit de TVA reportable"
    )
    penalites: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_paye: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    statut: Mapped[StatutDeclarationFiscale] = mapped_column(
        EnumCol(StatutDeclarationFiscale), default=StatutDeclarationFiscale.A_PREPARER, nullable=False, index=True
    )
    reference_dgi: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    centre_impots: Mapped[Optional[str]] = mapped_column(String(120))
    compte_tresorerie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_tresorerie.id", ondelete="SET NULL")
    )
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )
    document_url: Mapped[Optional[str]] = mapped_column(String(500))
    detail_calcul: Mapped[Optional[dict]] = mapped_column(JSON)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        UniqueConstraint(
            "type_impot", "periode_annee", "periode_mois", name="uq_declaration_type_periode"
        ),
    )


class BalanceCompte(BaseModel):
    """
    Balance periodique agregee : socle de la liasse fiscale (DSF) et des
    etats financiers. Recalculee par batch ou vue materialisee.
    """

    __tablename__ = "balances_comptes"

    exercice_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("exercices_comptables.id", ondelete="CASCADE"), nullable=False, index=True
    )
    compte_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="CASCADE"), nullable=False, index=True
    )
    periode_annee: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    periode_mois: Mapped[Optional[int]] = mapped_column(
        Integer, index=True, comment="NULL = cumul annuel"
    )
    report_debit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    report_credit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    mouvement_debit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    mouvement_credit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    solde_debiteur: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    solde_crediteur: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    date_calcul: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint(
            "exercice_id", "compte_id", "periode_annee", "periode_mois", name="uq_balance_compte_periode"
        ),
    )


class PosteDSF(ReferentielModel):
    """Poste de la liasse fiscale SYSCOHADA (bilan, compte de resultat, TAFIRE)."""

    __tablename__ = "postes_dsf"

    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    libelle: Mapped[str] = mapped_column(String(255), nullable=False)
    tableau: Mapped[TableauDSF] = mapped_column(EnumCol(TableauDSF), nullable=False, index=True)
    ordre: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    poste_parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("postes_dsf.id", ondelete="SET NULL")
    )
    formule: Mapped[Optional[str]] = mapped_column(
        Text, comment="Expression de calcul si poste agrege, ex: 'AD + AF - AH'"
    )
    is_total: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    poste_parent: Mapped[Optional["PosteDSF"]] = relationship(remote_side="PosteDSF.id")
    mappings: Mapped[List["MappingPosteDSF"]] = relationship(
        back_populates="poste", cascade="all, delete-orphan"
    )


class MappingPosteDSF(BaseModel):
    """Ventilation d'un prefixe de comptes vers un poste de la liasse."""

    __tablename__ = "mappings_poste_dsf"

    poste_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("postes_dsf.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prefixe_compte: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    sens_retenu: Mapped[Optional[SensCompte]] = mapped_column(
        EnumCol(SensCompte), comment="NULL = solde net"
    )
    signe: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="1 ou -1")
    commentaire: Mapped[Optional[str]] = mapped_column(Text)

    poste: Mapped[PosteDSF] = relationship(back_populates="mappings")

    __table_args__ = (
        UniqueConstraint("poste_id", "prefixe_compte", name="uq_mapping_poste_prefixe"),
        CheckConstraint("signe IN (-1, 1)", name="signe_valide"),
    )

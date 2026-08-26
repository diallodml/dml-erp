"""
DML SARLU - ERP | MODULE 3
ACHATS & CONTROLE QUALITE
=========================

Le processus barriere est le point de controle critique de l'entreprise :

    Camion arrive -> ReceptionBarriere (pesee BRUT)
                  -> Echantillonnage
                  -> ControleQualite (humidimetre SKZ + impuretes)
                  -> Decision : ACCEPTE / DECOTE / REJETE
                  -> Si accepte : dechargement, pesee TARE, poids NET
                  -> Creation du Lot + MouvementStock ENTREE_ACHAT
                  -> FactureAchat sur poids net retenu

La regle "rejet automatique si humidite > seuil" est portee par
`Produit.taux_humidite_max` (14 % par defaut) et evaluee par
`ControleQualite.evaluer_decision()`, doublee d'une contrainte de coherence.
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
    DecisionQualite,
    Devise,
    ModeReglement,
    MotifRejetQualite,
    StatutCommandeAchat,
    StatutFacture,
    StatutReception,
    Tiroir,
    TypeFournisseur,
    UniteMesure,
)

if TYPE_CHECKING:
    from .logistique import Chauffeur, Vehicule, Voyage
    from .stocks import Lot, Magasin, MouvementStock, Produit


# ===========================================================================
# FOURNISSEURS
# ===========================================================================
class Fournisseur(ReferentielModel):
    """
    Cooperative, grossiste, collecteur, transporteur sous-traitant,
    prestataire de service ou administration.
    """

    __tablename__ = "fournisseurs"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    raison_sociale: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    nom_commercial: Mapped[Optional[str]] = mapped_column(String(200))
    type_fournisseur: Mapped[TypeFournisseur] = mapped_column(
        EnumCol(TypeFournisseur), nullable=False, index=True
    )
    is_transporteur: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # --- Identification legale
    numero_rccm: Mapped[Optional[str]] = mapped_column(String(60))
    niu: Mapped[Optional[str]] = mapped_column(String(30), index=True, comment="Identifiant unique DGI")
    numero_contribuable: Mapped[Optional[str]] = mapped_column(String(40))
    regime_fiscal: Mapped[Optional[str]] = mapped_column(String(60))
    is_assujetti_tva: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    taux_air_applicable: Mapped[Decimal] = mapped_column(
        Rate, default=Decimal("0.0220"), nullable=False, comment="Acompte sur impot sur le revenu retenu"
    )

    # --- Coordonnees
    contact_principal: Mapped[Optional[str]] = mapped_column(String(150))
    telephone: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    telephone_secondaire: Mapped[Optional[str]] = mapped_column(String(30))
    email: Mapped[Optional[str]] = mapped_column(String(180))
    adresse: Mapped[Optional[str]] = mapped_column(Text)
    ville: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    region: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    pays: Mapped[str] = mapped_column(String(60), default="Cameroun", nullable=False)
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))

    # --- Conditions commerciales
    delai_paiement_jours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mode_reglement_habituel: Mapped[ModeReglement] = mapped_column(
        EnumCol(ModeReglement), default=ModeReglement.ESPECES, nullable=False
    )
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    numero_compte_bancaire: Mapped[Optional[str]] = mapped_column(String(60))
    numero_mobile_money: Mapped[Optional[str]] = mapped_column(String(30))
    compte_tiers_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )

    # --- Evaluation
    encours_actuel: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    volume_annuel_tonnes: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    taux_rejet_qualite: Mapped[Optional[Decimal]] = mapped_column(
        Rate, comment="% de livraisons rejetees a la barriere"
    )
    note_fiabilite: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    is_agree: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    date_agrement: Mapped[Optional[date]] = mapped_column(Date)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    contacts: Mapped[List["ContactFournisseur"]] = relationship(
        back_populates="fournisseur", cascade="all, delete-orphan"
    )
    commandes: Mapped[List["CommandeAchat"]] = relationship(back_populates="fournisseur")
    receptions: Mapped[List["ReceptionBarriere"]] = relationship(back_populates="fournisseur")
    factures: Mapped[List["FactureAchat"]] = relationship(back_populates="fournisseur")
    chauffeurs: Mapped[List["Chauffeur"]] = relationship(back_populates="sous_traitant")
    vehicules: Mapped[List["Vehicule"]] = relationship(back_populates="sous_traitant")


class ContactFournisseur(BaseModel):
    __tablename__ = "contacts_fournisseur"

    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nom: Mapped[str] = mapped_column(String(150), nullable=False)
    fonction: Mapped[Optional[str]] = mapped_column(String(120))
    telephone: Mapped[Optional[str]] = mapped_column(String(30))
    email: Mapped[Optional[str]] = mapped_column(String(180))
    is_principal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    fournisseur: Mapped[Fournisseur] = relationship(back_populates="contacts")


# ===========================================================================
# COMMANDES D'ACHAT
# ===========================================================================
class CommandeAchat(DocumentModel):
    __tablename__ = "commandes_achat"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    date_commande: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    date_livraison_prevue: Mapped[Optional[date]] = mapped_column(Date, index=True)
    magasin_destination_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL"), index=True
    )
    acheteur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    reference_fournisseur: Mapped[Optional[str]] = mapped_column(String(80))
    statut: Mapped[StatutCommandeAchat] = mapped_column(
        EnumCol(StatutCommandeAchat), default=StatutCommandeAchat.BROUILLON, nullable=False, index=True
    )
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    taux_change: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("1"), nullable=False)
    montant_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_tva: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_ttc: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    avance_versee: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    conditions: Mapped[Optional[str]] = mapped_column(Text)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    fournisseur: Mapped[Fournisseur] = relationship(back_populates="commandes")
    lignes: Mapped[List["LigneCommandeAchat"]] = relationship(
        back_populates="commande", cascade="all, delete-orphan"
    )
    receptions: Mapped[List["ReceptionBarriere"]] = relationship(back_populates="commande_achat")


class LigneCommandeAchat(BaseModel):
    __tablename__ = "lignes_commande_achat"

    commande_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("commandes_achat.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    designation: Mapped[Optional[str]] = mapped_column(String(255))
    quantite_commandee: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    quantite_recue: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    unite: Mapped[UniteMesure] = mapped_column(EnumCol(UniteMesure), default=UniteMesure.KG, nullable=False)
    prix_unitaire: Mapped[Decimal] = mapped_column(Money, nullable=False)
    remise_taux: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    montant_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    taux_tva: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    montant_ttc: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    commande: Mapped[CommandeAchat] = relationship(back_populates="lignes")

    __table_args__ = (CheckConstraint("quantite_commandee > 0", name="qte_commandee_positive"),)


# ===========================================================================
# RECEPTION A LA BARRIERE
# ===========================================================================
class ReceptionBarriere(DocumentModel):
    """
    Ticket de pesee et dossier de reception. Charniere entre le module
    logistique (camion / chauffeur), les achats et les stocks.
    """

    __tablename__ = "receptions_barriere"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    numero_ticket_pesee: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    magasin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # --- Origine de la marchandise
    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    commande_achat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("commandes_achat.id", ondelete="SET NULL"), index=True
    )
    produit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # --- LIAISON MODULE LOGISTIQUE : qui a livre ?
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="SET NULL"), index=True
    )
    vehicule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vehicules.id", ondelete="SET NULL"), index=True
    )
    chauffeur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chauffeurs.id", ondelete="SET NULL"), index=True
    )
    immatriculation_declaree: Mapped[Optional[str]] = mapped_column(
        String(30), index=True, comment="Saisie libre si camion non enregistre"
    )
    chauffeur_declare: Mapped[Optional[str]] = mapped_column(String(150))
    telephone_chauffeur: Mapped[Optional[str]] = mapped_column(String(30))

    # --- Chronologie barriere
    date_arrivee: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )
    heure_pesee_brut: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    heure_debut_dechargement: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    heure_fin_dechargement: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    heure_pesee_tare: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    heure_sortie: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # --- PESEE
    pont_bascule: Mapped[Optional[str]] = mapped_column(String(80))
    poids_brut: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    poids_tare: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    poids_net: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False, index=True)
    nombre_sacs: Mapped[Optional[int]] = mapped_column(Integer)
    poids_moyen_sac: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3))
    unite: Mapped[UniteMesure] = mapped_column(EnumCol(UniteMesure), default=UniteMesure.KG, nullable=False)

    # --- Retenues issues du controle qualite
    deduction_humidite: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    deduction_impuretes: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    deduction_emballage: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    poids_net_retenu: Mapped[Decimal] = mapped_column(
        Quantity, default=Decimal("0"), nullable=False, comment="Base de facturation fournisseur"
    )

    # --- Valorisation
    prix_unitaire_convenu: Mapped[Optional[Decimal]] = mapped_column(Money)
    montant_estime: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    # --- Destination en magasin
    emplacement_destination_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("emplacements.id", ondelete="SET NULL")
    )
    lot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("lots.id", ondelete="SET NULL", use_alter=True, name="fk_reception_lot"),
        comment="Lot cree apres acceptation",
    )

    statut: Mapped[StatutReception] = mapped_column(
        EnumCol(StatutReception), default=StatutReception.ARRIVE_BARRIERE, nullable=False, index=True
    )
    agent_barriere_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    magasinier_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    photos_urls: Mapped[Optional[dict]] = mapped_column(JSON)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    # --- Relations
    fournisseur: Mapped[Fournisseur] = relationship(back_populates="receptions")
    commande_achat: Mapped[Optional[CommandeAchat]] = relationship(back_populates="receptions")
    voyage: Mapped[Optional["Voyage"]] = relationship(back_populates="receptions")
    produit: Mapped["Produit"] = relationship()
    controle_qualite: Mapped[Optional["ControleQualite"]] = relationship(
        back_populates="reception", uselist=False, cascade="all, delete-orphan"
    )
    lot: Mapped[Optional["Lot"]] = relationship(foreign_keys=[lot_id], post_update=True)

    @property
    def duree_immobilisation_minutes(self) -> Optional[int]:
        if self.heure_sortie:
            return int((self.heure_sortie - self.date_arrivee).total_seconds() // 60)
        return None

    def calculer_poids_net(self) -> Decimal:
        self.poids_net = (self.poids_brut or Decimal("0")) - (self.poids_tare or Decimal("0"))
        return self.poids_net

    def calculer_poids_retenu(self) -> Decimal:
        self.poids_net_retenu = (
            self.poids_net
            - self.deduction_humidite
            - self.deduction_impuretes
            - self.deduction_emballage
        )
        return self.poids_net_retenu

    __table_args__ = (
        CheckConstraint("poids_brut >= 0 AND poids_tare >= 0", name="pesees_positives"),
        CheckConstraint("poids_net >= 0", name="poids_net_positif"),
        Index("ix_receptions_statut_date", "statut", "date_arrivee"),
        Index("ix_receptions_fournisseur_produit", "fournisseur_id", "produit_id"),
    )


class ControleQualite(DocumentModel):
    """
    Analyse obligatoire avant entree en magasin.
    Mesures : humidimetre SKZ (taux d'humidite), tamisage (impuretes),
    comptage des grains casses / moisis, poids specifique.
    """

    __tablename__ = "controles_qualite"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    reception_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("receptions_barriere.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    produit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    date_controle: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )
    controleur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )

    # --- Echantillonnage
    reference_echantillon: Mapped[Optional[str]] = mapped_column(String(60))
    nombre_prelevements: Mapped[Optional[int]] = mapped_column(Integer)
    poids_echantillon_g: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2))

    # --- MESURES
    appareil_humidimetre: Mapped[Optional[str]] = mapped_column(
        String(80), default="SKZ", comment="Reference de l'humidimetre utilise"
    )
    taux_humidite: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, index=True)
    taux_impuretes: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0"), nullable=False)
    taux_grains_casses: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    taux_grains_moisis: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    taux_grains_attaques: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    poids_specifique: Mapped[Optional[Decimal]] = mapped_column(Numeric(8, 2), comment="kg/hl")
    temperature_masse: Mapped[Optional[Decimal]] = mapped_column(Numeric(6, 2))
    presence_insectes: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    presence_corps_etrangers: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    odeur_conforme: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    couleur_conforme: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # --- Seuils appliques (figes au moment du controle, pour l'audit)
    seuil_humidite_applique: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("14.00"), nullable=False
    )
    seuil_impuretes_applique: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("2.00"), nullable=False
    )

    # --- DECISION
    decision: Mapped[DecisionQualite] = mapped_column(
        EnumCol(DecisionQualite), default=DecisionQualite.EN_ATTENTE, nullable=False, index=True
    )
    is_rejet_automatique: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, comment="Declenche par depassement de seuil, sans arbitrage"
    )
    motif_rejet: Mapped[Optional[MotifRejetQualite]] = mapped_column(EnumCol(MotifRejetQualite))
    commentaire_decision: Mapped[Optional[str]] = mapped_column(Text)

    # --- Decote appliquee
    taux_decote: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    poids_deduit: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    montant_decote: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    # --- Derogation hierarchique (tracee)
    derogation_accordee: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    derogation_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    motif_derogation: Mapped[Optional[str]] = mapped_column(Text)

    photos_urls: Mapped[Optional[dict]] = mapped_column(JSON)
    mesures_detaillees: Mapped[Optional[dict]] = mapped_column(
        JSON, comment="Releves individuels par prelevement"
    )

    reception: Mapped[ReceptionBarriere] = relationship(back_populates="controle_qualite")

    # -- Regle metier -------------------------------------------------------
    def evaluer_decision(self) -> DecisionQualite:
        """
        Applique la regle de rejet automatique.
        A appeler dans le service avant persistance ; les seuils doivent avoir
        ete copies depuis le `Produit` au moment de l'ouverture du controle.
        """
        if self.taux_humidite > self.seuil_humidite_applique:
            self.is_rejet_automatique = True
            self.motif_rejet = MotifRejetQualite.HUMIDITE_EXCESSIVE
            self.decision = DecisionQualite.REJETE
        elif self.taux_impuretes > self.seuil_impuretes_applique:
            self.is_rejet_automatique = True
            self.motif_rejet = MotifRejetQualite.IMPURETES_EXCESSIVES
            self.decision = DecisionQualite.REJETE
        elif self.presence_insectes:
            self.motif_rejet = MotifRejetQualite.INFESTATION_INSECTES
            self.decision = DecisionQualite.REJETE
        elif self.taux_decote > 0:
            self.decision = DecisionQualite.ACCEPTE_AVEC_DECOTE
        else:
            self.decision = DecisionQualite.ACCEPTE
        return self.decision

    @property
    def is_conforme(self) -> bool:
        return self.decision in (
            DecisionQualite.ACCEPTE,
            DecisionQualite.ACCEPTE_AVEC_DECOTE,
            DecisionQualite.ACCEPTE_APRES_SECHAGE,
        )

    __table_args__ = (
        CheckConstraint("taux_humidite >= 0 AND taux_humidite <= 100", name="humidite_plage_valide"),
        CheckConstraint("taux_impuretes >= 0 AND taux_impuretes <= 100", name="impuretes_plage_valide"),
        # Coherence : au-dela du seuil, la decision ne peut etre un accord
        # que si une derogation explicite a ete accordee.
        CheckConstraint(
            "(taux_humidite <= seuil_humidite_applique) "
            "OR (decision IN ('REJETE', 'EN_ATTENTE', 'ACCEPTE_APRES_SECHAGE')) "
            "OR (derogation_accordee = true)",
            name="rejet_obligatoire_hors_seuil_humidite",
        ),
        Index("ix_controles_decision_date", "decision", "date_controle"),
    )


# ===========================================================================
# FACTURATION FOURNISSEUR
# ===========================================================================
class FactureAchat(DocumentModel):
    __tablename__ = "factures_achat"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    numero_fournisseur: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    commande_achat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("commandes_achat.id", ondelete="SET NULL"), index=True
    )
    date_facture: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    date_echeance: Mapped[Optional[date]] = mapped_column(Date, index=True)
    date_reception_facture: Mapped[Optional[date]] = mapped_column(Date)

    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    taux_change: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("1"), nullable=False)
    montant_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    remise: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_tva: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    retenue_air: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False, comment="Acompte sur impot sur le revenu retenu a la source"
    )
    autres_retenues: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    frais_transport: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_ttc: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    net_a_payer: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_regle: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    statut: Mapped[StatutFacture] = mapped_column(
        EnumCol(StatutFacture), default=StatutFacture.BROUILLON, nullable=False, index=True
    )
    scan_url: Mapped[Optional[str]] = mapped_column(String(500))
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )
    observations: Mapped[Optional[str]] = mapped_column(Text)

    fournisseur: Mapped[Fournisseur] = relationship(back_populates="factures")
    lignes: Mapped[List["LigneFactureAchat"]] = relationship(
        back_populates="facture", cascade="all, delete-orphan"
    )
    reglements: Mapped[List["ReglementFournisseur"]] = relationship(back_populates="facture")

    @property
    def solde_du(self) -> Decimal:
        return self.net_a_payer - self.montant_regle

    __table_args__ = (Index("ix_factures_achat_statut_echeance", "statut", "date_echeance"),)


class LigneFactureAchat(BaseModel):
    __tablename__ = "lignes_facture_achat"

    facture_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("factures_achat.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="SET NULL"), index=True
    )
    reception_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("receptions_barriere.id", ondelete="SET NULL"), index=True
    )
    designation: Mapped[str] = mapped_column(String(255), nullable=False)
    quantite: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unite: Mapped[UniteMesure] = mapped_column(EnumCol(UniteMesure), default=UniteMesure.KG, nullable=False)
    prix_unitaire: Mapped[Decimal] = mapped_column(Money, nullable=False)
    montant_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    taux_tva: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    montant_tva: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_ttc: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    compte_charge_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )

    facture: Mapped[FactureAchat] = relationship(back_populates="lignes")


class ReglementFournisseur(DocumentModel):
    __tablename__ = "reglements_fournisseur"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    facture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("factures_achat.id", ondelete="SET NULL"), index=True
    )
    fournisseur_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("fournisseurs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    date_reglement: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    montant: Mapped[Decimal] = mapped_column(Money, nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    mode_reglement: Mapped[ModeReglement] = mapped_column(EnumCol(ModeReglement), nullable=False, index=True)
    compte_tresorerie_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_tresorerie.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tiroir: Mapped[Tiroir] = mapped_column(
        EnumCol(Tiroir),
        default=Tiroir.ENTREPRISE,
        nullable=False,
        index=True,
        comment="Separation stricte tresorerie societe / compte courant associe",
    )
    reference_transaction: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    numero_cheque: Mapped[Optional[str]] = mapped_column(String(60))
    beneficiaire: Mapped[Optional[str]] = mapped_column(String(180))
    justificatif_url: Mapped[Optional[str]] = mapped_column(String(500))
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )
    observations: Mapped[Optional[str]] = mapped_column(Text)

    facture: Mapped[Optional[FactureAchat]] = relationship(back_populates="reglements")

    __table_args__ = (CheckConstraint("montant > 0", name="montant_reglement_fournisseur_positif"),)

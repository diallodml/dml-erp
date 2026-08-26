"""
DML SARLU - ERP | MODULE 4
VENTES & CRM (B2B)
==================

Cycle de vente complet :

    Proforma -> BonCommandeClient -> BonLivraison -> FactureVente -> ReglementClient

Le `BonLivraison` est le point de jonction avec les modules 1 et 2 :
il porte le voyage, le chauffeur et le camion, et chacune de ses lignes
genere un `MouvementStock` de type SORTIE_VENTE sur un lot precis.

Le controle d'encours (limite de credit) est evalue au moment de la
confirmation de commande, pas a la facturation : c'est la que le risque nait.
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
    CanalRelance,
    Devise,
    ModeReglement,
    StatutClient,
    StatutCommandeVente,
    StatutFacture,
    StatutLivraison,
    StatutProforma,
    Tiroir,
    TypeClient,
    TypeInteractionCRM,
    UniteMesure,
)

if TYPE_CHECKING:
    from .logistique import Chauffeur, Vehicule, Voyage
    from .stocks import Lot, Magasin, MouvementStock, Produit


# ===========================================================================
# CLIENTS
# ===========================================================================
class Client(ReferentielModel):
    """Client industriel, grossiste ou exportateur."""

    __tablename__ = "clients"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    raison_sociale: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    nom_commercial: Mapped[Optional[str]] = mapped_column(String(200))
    type_client: Mapped[TypeClient] = mapped_column(EnumCol(TypeClient), nullable=False, index=True)
    secteur_activite: Mapped[Optional[str]] = mapped_column(String(120))

    # --- Identification legale
    numero_rccm: Mapped[Optional[str]] = mapped_column(String(60))
    niu: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    regime_fiscal: Mapped[Optional[str]] = mapped_column(String(60))
    is_assujetti_tva: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_exonere_tva: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reference_exoneration: Mapped[Optional[str]] = mapped_column(String(80))

    # --- Coordonnees
    contact_principal: Mapped[Optional[str]] = mapped_column(String(150))
    telephone: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    email: Mapped[Optional[str]] = mapped_column(String(180))
    site_web: Mapped[Optional[str]] = mapped_column(String(180))
    adresse_siege: Mapped[Optional[str]] = mapped_column(Text)
    adresse_livraison: Mapped[Optional[str]] = mapped_column(Text)
    ville: Mapped[Optional[str]] = mapped_column(String(80), index=True)
    pays: Mapped[str] = mapped_column(String(60), default="Cameroun", nullable=False)
    latitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))
    longitude: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 7))

    # --- Conditions commerciales & RISQUE CREDIT
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    limite_credit: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False, comment="0 = paiement comptant obligatoire"
    )
    delai_paiement_jours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    encours_actuel: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False, index=True, comment="Recalcule a chaque facture/reglement"
    )
    encours_echu: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    mode_reglement_habituel: Mapped[ModeReglement] = mapped_column(
        EnumCol(ModeReglement), default=ModeReglement.VIREMENT, nullable=False
    )
    remise_habituelle: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    compte_tiers_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )

    # --- Suivi commercial
    commercial_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL"), index=True
    )
    statut: Mapped[StatutClient] = mapped_column(
        EnumCol(StatutClient), default=StatutClient.PROSPECT, nullable=False, index=True
    )
    is_bloque: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    motif_blocage: Mapped[Optional[str]] = mapped_column(Text)
    date_premiere_commande: Mapped[Optional[date]] = mapped_column(Date)
    chiffre_affaires_cumule: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    tonnage_cumule: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    note_solvabilite: Mapped[Optional[Decimal]] = mapped_column(Numeric(4, 2))
    observations: Mapped[Optional[str]] = mapped_column(Text)

    contacts: Mapped[List["ContactClient"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    proformas: Mapped[List["Proforma"]] = relationship(back_populates="client")
    commandes: Mapped[List["BonCommandeClient"]] = relationship(back_populates="client")
    bons_livraison: Mapped[List["BonLivraison"]] = relationship(back_populates="client")
    factures: Mapped[List["FactureVente"]] = relationship(back_populates="client")
    interactions: Mapped[List["InteractionCRM"]] = relationship(
        back_populates="client", cascade="all, delete-orphan"
    )
    relances: Mapped[List["RelanceClient"]] = relationship(back_populates="client")

    @property
    def credit_disponible(self) -> Decimal:
        return self.limite_credit - self.encours_actuel

    @property
    def is_depassement_encours(self) -> bool:
        return self.encours_actuel > self.limite_credit

    __table_args__ = (
        CheckConstraint("limite_credit >= 0", name="limite_credit_positive"),
        Index("ix_clients_statut_encours", "statut", "encours_actuel"),
    )


class ContactClient(BaseModel):
    __tablename__ = "contacts_client"

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    nom: Mapped[str] = mapped_column(String(150), nullable=False)
    fonction: Mapped[Optional[str]] = mapped_column(String(120))
    telephone: Mapped[Optional[str]] = mapped_column(String(30))
    email: Mapped[Optional[str]] = mapped_column(String(180))
    is_principal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_decideur: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)

    client: Mapped[Client] = relationship(back_populates="contacts")


# ===========================================================================
# PROFORMA
# ===========================================================================
class Proforma(DocumentModel):
    __tablename__ = "proformas"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    date_emission: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    duree_validite_jours: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    date_expiration: Mapped[Optional[date]] = mapped_column(Date, index=True)
    objet: Mapped[Optional[str]] = mapped_column(String(255))
    magasin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL")
    )
    commercial_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )

    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    taux_change: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("1"), nullable=False)
    montant_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    remise_globale: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_tva: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    frais_transport: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_ttc: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    conditions_paiement: Mapped[Optional[str]] = mapped_column(Text)
    conditions_livraison: Mapped[Optional[str]] = mapped_column(Text)
    incoterm: Mapped[Optional[str]] = mapped_column(String(20))
    statut: Mapped[StatutProforma] = mapped_column(
        EnumCol(StatutProforma), default=StatutProforma.BROUILLON, nullable=False, index=True
    )
    date_reponse_client: Mapped[Optional[date]] = mapped_column(Date)
    motif_refus: Mapped[Optional[str]] = mapped_column(Text)
    pdf_url: Mapped[Optional[str]] = mapped_column(String(500))

    client: Mapped[Client] = relationship(back_populates="proformas")
    lignes: Mapped[List["LigneProforma"]] = relationship(
        back_populates="proforma", cascade="all, delete-orphan"
    )
    commandes: Mapped[List["BonCommandeClient"]] = relationship(back_populates="proforma")


class LigneProforma(BaseModel):
    __tablename__ = "lignes_proforma"

    proforma_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("proformas.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False
    )
    ordre: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    designation: Mapped[Optional[str]] = mapped_column(String(255))
    quantite: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unite: Mapped[UniteMesure] = mapped_column(EnumCol(UniteMesure), default=UniteMesure.KG, nullable=False)
    prix_unitaire: Mapped[Decimal] = mapped_column(Money, nullable=False)
    remise_taux: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    montant_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    taux_tva: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.1925"), nullable=False)
    montant_ttc: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    proforma: Mapped[Proforma] = relationship(back_populates="lignes")


# ===========================================================================
# BON DE COMMANDE CLIENT
# ===========================================================================
class BonCommandeClient(DocumentModel):
    __tablename__ = "bons_commande_client"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    proforma_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("proformas.id", ondelete="SET NULL"), index=True
    )
    reference_client: Mapped[Optional[str]] = mapped_column(
        String(80), index=True, comment="Numero de commande cote client"
    )
    date_commande: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    date_livraison_souhaitee: Mapped[Optional[date]] = mapped_column(Date, index=True)
    magasin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="SET NULL"), index=True
    )
    lieu_livraison: Mapped[Optional[str]] = mapped_column(String(255))
    commercial_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )

    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    montant_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    remise_globale: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_tva: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_ttc: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    acompte_recu: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    # --- Controle du risque credit au moment de la confirmation
    encours_client_a_la_commande: Mapped[Optional[Decimal]] = mapped_column(Money)
    depassement_encours: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    derogation_credit_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    motif_derogation_credit: Mapped[Optional[str]] = mapped_column(Text)

    statut: Mapped[StatutCommandeVente] = mapped_column(
        EnumCol(StatutCommandeVente), default=StatutCommandeVente.BROUILLON, nullable=False, index=True
    )
    conditions: Mapped[Optional[str]] = mapped_column(Text)
    bon_commande_scan_url: Mapped[Optional[str]] = mapped_column(String(500))

    client: Mapped[Client] = relationship(back_populates="commandes")
    proforma: Mapped[Optional[Proforma]] = relationship(back_populates="commandes")
    lignes: Mapped[List["LigneBonCommande"]] = relationship(
        back_populates="commande", cascade="all, delete-orphan"
    )
    bons_livraison: Mapped[List["BonLivraison"]] = relationship(back_populates="commande")

    __table_args__ = (Index("ix_bc_client_statut", "client_id", "statut"),)


class LigneBonCommande(BaseModel):
    __tablename__ = "lignes_bon_commande"

    commande_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bons_commande_client.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    ordre: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    designation: Mapped[Optional[str]] = mapped_column(String(255))
    quantite_commandee: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    quantite_livree: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    quantite_facturee: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    quantite_reservee: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    unite: Mapped[UniteMesure] = mapped_column(EnumCol(UniteMesure), default=UniteMesure.KG, nullable=False)
    prix_unitaire: Mapped[Decimal] = mapped_column(Money, nullable=False)
    remise_taux: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    montant_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    taux_tva: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.1925"), nullable=False)
    montant_ttc: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    specifications_qualite: Mapped[Optional[str]] = mapped_column(Text)

    commande: Mapped[BonCommandeClient] = relationship(back_populates="lignes")

    @property
    def reste_a_livrer(self) -> Decimal:
        return self.quantite_commandee - self.quantite_livree


# ===========================================================================
# BON DE LIVRAISON  (jonction stocks <-> logistique)
# ===========================================================================
class BonLivraison(DocumentModel):
    __tablename__ = "bons_livraison"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    commande_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bons_commande_client.id", ondelete="SET NULL"), index=True
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    magasin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("magasins.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    date_livraison: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)

    # --- LIAISON MODULE LOGISTIQUE
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("voyages.id", ondelete="SET NULL"), index=True
    )
    chauffeur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("chauffeurs.id", ondelete="SET NULL"), index=True
    )
    vehicule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("vehicules.id", ondelete="SET NULL"), index=True
    )
    immatriculation_declaree: Mapped[Optional[str]] = mapped_column(String(30))
    transporteur_externe: Mapped[Optional[str]] = mapped_column(String(180))

    lieu_livraison: Mapped[Optional[str]] = mapped_column(String(255))
    heure_chargement: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    heure_depart: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    heure_arrivee_client: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # --- Pesees
    poids_charge: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    poids_livre: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    ecart_poids: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    nombre_sacs: Mapped[Optional[int]] = mapped_column(Integer)
    numero_ticket_pesee: Mapped[Optional[str]] = mapped_column(String(60))

    statut: Mapped[StatutLivraison] = mapped_column(
        EnumCol(StatutLivraison), default=StatutLivraison.PREPARE, nullable=False, index=True
    )
    signataire_client: Mapped[Optional[str]] = mapped_column(String(150))
    fonction_signataire: Mapped[Optional[str]] = mapped_column(String(120))
    signature_url: Mapped[Optional[str]] = mapped_column(String(500))
    photos_urls: Mapped[Optional[dict]] = mapped_column(JSON)
    reserves_client: Mapped[Optional[str]] = mapped_column(Text)
    is_facture: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    client: Mapped[Client] = relationship(back_populates="bons_livraison")
    commande: Mapped[Optional[BonCommandeClient]] = relationship(back_populates="bons_livraison")
    voyage: Mapped[Optional["Voyage"]] = relationship(back_populates="bons_livraison")
    lignes: Mapped[List["LigneBonLivraison"]] = relationship(
        back_populates="bon_livraison", cascade="all, delete-orphan"
    )

    __table_args__ = (Index("ix_bl_statut_date", "statut", "date_livraison"),)


class LigneBonLivraison(BaseModel):
    """Chaque ligne genere un MouvementStock SORTIE_VENTE sur un lot precis."""

    __tablename__ = "lignes_bon_livraison"

    bon_livraison_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bons_livraison.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ligne_commande_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lignes_bon_commande.id", ondelete="SET NULL")
    )
    produit_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lots.id", ondelete="SET NULL"), index=True
    )
    emplacement_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("emplacements.id", ondelete="SET NULL")
    )
    mouvement_stock_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("mouvements_stock.id", ondelete="SET NULL"), index=True
    )
    designation: Mapped[Optional[str]] = mapped_column(String(255))
    quantite_prevue: Mapped[Decimal] = mapped_column(Quantity, default=Decimal("0"), nullable=False)
    quantite_livree: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unite: Mapped[UniteMesure] = mapped_column(EnumCol(UniteMesure), default=UniteMesure.KG, nullable=False)
    nombre_sacs: Mapped[Optional[int]] = mapped_column(Integer)
    prix_unitaire: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cout_revient_unitaire: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)

    bon_livraison: Mapped[BonLivraison] = relationship(back_populates="lignes")

    __table_args__ = (CheckConstraint("quantite_livree > 0", name="qte_livree_positive"),)


# ===========================================================================
# FACTURATION & ENCAISSEMENTS
# ===========================================================================
class FactureVente(DocumentModel):
    __tablename__ = "factures_vente"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    commande_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bons_commande_client.id", ondelete="SET NULL"), index=True
    )
    bon_livraison_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("bons_livraison.id", ondelete="SET NULL"), index=True
    )
    facture_origine_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("factures_vente.id", ondelete="SET NULL"), comment="Si avoir"
    )
    is_avoir: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    date_facture: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    date_echeance: Mapped[Optional[date]] = mapped_column(Date, index=True)
    exercice_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("exercices_comptables.id", ondelete="SET NULL"), index=True
    )

    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    taux_change: Mapped[Decimal] = mapped_column(Numeric(14, 6), default=Decimal("1"), nullable=False)
    montant_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    remise_globale: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    base_taxable: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    taux_tva: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.1925"), nullable=False)
    montant_tva: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    precompte: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    frais_transport: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_ttc: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_regle: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cout_revient_total: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False, comment="Pour la marge par facture"
    )

    statut: Mapped[StatutFacture] = mapped_column(
        EnumCol(StatutFacture), default=StatutFacture.BROUILLON, nullable=False, index=True
    )
    mode_reglement_prevu: Mapped[Optional[ModeReglement]] = mapped_column(EnumCol(ModeReglement))
    conditions_paiement: Mapped[Optional[str]] = mapped_column(Text)
    mention_legale: Mapped[Optional[str]] = mapped_column(Text)
    pdf_url: Mapped[Optional[str]] = mapped_column(String(500))
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )
    date_derniere_relance: Mapped[Optional[date]] = mapped_column(Date)
    niveau_relance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    client: Mapped[Client] = relationship(back_populates="factures", foreign_keys=[client_id])
    lignes: Mapped[List["LigneFactureVente"]] = relationship(
        back_populates="facture", cascade="all, delete-orphan"
    )
    reglements: Mapped[List["ReglementClient"]] = relationship(back_populates="facture")
    relances: Mapped[List["RelanceClient"]] = relationship(back_populates="facture")

    @property
    def solde_du(self) -> Decimal:
        return self.montant_ttc - self.montant_regle

    @property
    def jours_retard(self) -> int:
        if self.date_echeance and self.solde_du > 0:
            return max(0, (date.today() - self.date_echeance).days)
        return 0

    @property
    def marge_brute(self) -> Decimal:
        return self.montant_ht - self.cout_revient_total

    __table_args__ = (
        Index("ix_factures_vente_statut_echeance", "statut", "date_echeance"),
        Index("ix_factures_vente_client_date", "client_id", "date_facture"),
    )


class LigneFactureVente(BaseModel):
    __tablename__ = "lignes_facture_vente"

    facture_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("factures_vente.id", ondelete="CASCADE"), nullable=False, index=True
    )
    produit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("produits.id", ondelete="SET NULL"), index=True
    )
    ligne_livraison_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("lignes_bon_livraison.id", ondelete="SET NULL")
    )
    ordre: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    designation: Mapped[str] = mapped_column(String(255), nullable=False)
    quantite: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unite: Mapped[UniteMesure] = mapped_column(EnumCol(UniteMesure), default=UniteMesure.KG, nullable=False)
    prix_unitaire: Mapped[Decimal] = mapped_column(Money, nullable=False)
    remise_taux: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0"), nullable=False)
    montant_ht: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    taux_tva: Mapped[Decimal] = mapped_column(Rate, default=Decimal("0.1925"), nullable=False)
    montant_tva: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    montant_ttc: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    cout_revient_unitaire: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    compte_produit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_ohada.id", ondelete="SET NULL")
    )

    facture: Mapped[FactureVente] = relationship(back_populates="lignes")


class ReglementClient(DocumentModel):
    __tablename__ = "reglements_client"

    numero: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    facture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("factures_vente.id", ondelete="SET NULL"), index=True
    )
    date_reglement: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    date_valeur: Mapped[Optional[date]] = mapped_column(Date)
    montant: Mapped[Decimal] = mapped_column(Money, nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    mode_reglement: Mapped[ModeReglement] = mapped_column(EnumCol(ModeReglement), nullable=False, index=True)
    compte_tresorerie_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("comptes_tresorerie.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    tiroir: Mapped[Tiroir] = mapped_column(
        EnumCol(Tiroir), default=Tiroir.ENTREPRISE, nullable=False, index=True
    )
    reference_transaction: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    numero_cheque: Mapped[Optional[str]] = mapped_column(String(60))
    banque_emettrice: Mapped[Optional[str]] = mapped_column(String(120))
    is_encaisse: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_impaye: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    justificatif_url: Mapped[Optional[str]] = mapped_column(String(500))
    encaisse_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )
    observations: Mapped[Optional[str]] = mapped_column(Text)

    facture: Mapped[Optional[FactureVente]] = relationship(back_populates="reglements")

    __table_args__ = (CheckConstraint("montant > 0", name="montant_reglement_client_positif"),)


# ===========================================================================
# RECOUVREMENT & CRM
# ===========================================================================
class RelanceClient(DocumentModel):
    __tablename__ = "relances_client"

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    facture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("factures_vente.id", ondelete="SET NULL"), index=True
    )
    date_relance: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    niveau: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)
    canal: Mapped[CanalRelance] = mapped_column(EnumCol(CanalRelance), nullable=False)
    montant_reclame: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    jours_retard: Mapped[Optional[int]] = mapped_column(Integer)
    contenu: Mapped[Optional[str]] = mapped_column(Text)
    reponse_client: Mapped[Optional[str]] = mapped_column(Text)
    engagement_paiement: Mapped[Optional[date]] = mapped_column(Date)
    prochaine_relance: Mapped[Optional[date]] = mapped_column(Date, index=True)
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )
    document_url: Mapped[Optional[str]] = mapped_column(String(500))

    client: Mapped[Client] = relationship(back_populates="relances")
    facture: Mapped[Optional[FactureVente]] = relationship(back_populates="relances")


class InteractionCRM(DocumentModel):
    __tablename__ = "interactions_crm"

    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("contacts_client.id", ondelete="SET NULL")
    )
    type_interaction: Mapped[TypeInteractionCRM] = mapped_column(
        EnumCol(TypeInteractionCRM), nullable=False, index=True
    )
    date_interaction: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow, index=True
    )
    objet: Mapped[str] = mapped_column(String(255), nullable=False)
    compte_rendu: Mapped[Optional[str]] = mapped_column(Text)
    resultat: Mapped[Optional[str]] = mapped_column(String(255))
    prochaine_action: Mapped[Optional[str]] = mapped_column(Text)
    date_prochaine_action: Mapped[Optional[date]] = mapped_column(Date, index=True)
    agent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("utilisateurs.id", ondelete="SET NULL"), index=True
    )
    piece_jointe_url: Mapped[Optional[str]] = mapped_column(String(500))

    client: Mapped[Client] = relationship(back_populates="interactions")

"""
DML SARLU - ERP | MODULE 7 : TRANSPORT POUR COMPTE DE TIERS
==========================================================

Activite distincte du negoce : DML achemine la marchandise d'un client de
Douala vers les autres villes du Cameroun. Cette marchandise n'appartient
PAS a DML.

Trois principes structurants
----------------------------
1. ETANCHEITE DU STOCK
   La marchandise transportee ne genere JAMAIS de MouvementStock.
   Elle est decrite par `LigneMarchandiseTiers`, rattachee a une mission.
   La confondre avec le stock propre fausserait l'inventaire et le bilan.

2. GROUPAGE : 1 VOYAGE -> N MISSIONS
   Un camion peut charger la marchandise de plusieurs clients.
   Le cout reel du voyage (carburant, peages, avance chauffeur, prix
   negocie avec le transporteur) est donc VENTILE entre les missions
   (`VentilationCoutVoyage`). Sans cette ventilation, aucune marge par
   client n'est calculable sur un camion groupe.

3. FACTURATION A LA TONNE
   Le prix de vente vient d'une grille par axe (`TarifTransport`), le cout
   vient de la negociation avec le transporteur (`AttributionFret`).
   L'ecart des deux est la marge de l'activite transport.
   Comptablement : compte 706 (services vendus), jamais 701.

Note d'implementation
---------------------
La facturation reutilise `FactureVente` du module Ventes : une mission
pointe vers sa facture, et la ligne de facture porte un compte 706.
On ne duplique pas la chaine de facturation ni le suivi d'encours.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
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
    BaseFacturationTransport,
    ClePartitionCout,
    Devise,
    EtatMarchandiseTiers,
    NiveauAlerte,
    ResponsabiliteLitige,
    SensNegociation,
    StatutCandidature,
    StatutLitigeTransport,
    StatutMissionTransport,
    StatutOffreFret,
    StatutSessionMobile,
    TypeLitigeTransport,
    TypeVehicule,
    UniteMesure,
    ZoneApplication,
)


# ===========================================================================
# 1. REFERENTIEL : AXES ET TARIFS
# ===========================================================================
class AxeTransport(ReferentielModel):
    """
    Un corridor commercial : Douala -> Garoua, Douala -> Bertoua...

    Sert de cle d'analyse : rentabilite par axe, prix de marche par axe,
    saisonnalite (route de l'Adamaoua en saison des pluies).
    """

    __tablename__ = "axes_transport"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    libelle: Mapped[str] = mapped_column(String(150), nullable=False)

    ville_depart: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    region_depart: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    ville_arrivee: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    region_arrivee: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)

    distance_km: Mapped[Optional[Decimal]] = mapped_column(Quantity, nullable=True)
    duree_estimee_heures: Mapped[Optional[Decimal]] = mapped_column(Quantity, nullable=True)

    # Realites terrain : etat de route, postes de controle, saisonnalite
    nb_postes_controle: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    budget_peage_indicatif: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    praticable_saison_pluies: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    observations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    tarifs: Mapped[List["TarifTransport"]] = relationship(
        back_populates="axe", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("ville_depart", "ville_arrivee", name="uq_axe_depart_arrivee"),
    )


class TarifTransport(ReferentielModel):
    """
    Grille de prix de VENTE au client, a la tonne.

    Le tonnage minimum facturable est la protection contre les demi-charges :
    un camion de 30 t qui part avec 18 t coute le meme carburant.

    `tolerance_freinte_pct` fixe l'ecart de poids depart/arrivee admis avant
    qu'il ne devienne un litige a la charge du transporteur.
    """

    __tablename__ = "tarifs_transport"

    axe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("axes_transport.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Tarif general (client_id NULL) ou tarif negocie propre a un client
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # Optionnel : certains produits coutent plus cher (fragile, vrac, dangereux)
    produit_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("produits.id", ondelete="SET NULL"), nullable=True
    )
    type_vehicule: Mapped[Optional[TypeVehicule]] = mapped_column(
        EnumCol(TypeVehicule), nullable=True
    )

    prix_tonne: Mapped[Decimal] = mapped_column(Money, nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    tonnage_minimum_facturable: Mapped[Decimal] = mapped_column(
        Quantity, default=Decimal("0.000"), nullable=False
    )
    prix_forfait_camion: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    base_facturation: Mapped[BaseFacturationTransport] = mapped_column(
        EnumCol(BaseFacturationTransport),
        default=BaseFacturationTransport.TONNAGE_DEPART,
        nullable=False,
    )
    tolerance_freinte_pct: Mapped[Decimal] = mapped_column(
        Rate, default=Decimal("0.0050"), nullable=False  # 0,50 %
    )

    date_debut: Mapped[date] = mapped_column(Date, nullable=False)
    date_fin: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    axe: Mapped["AxeTransport"] = relationship(back_populates="tarifs")

    __table_args__ = (
        CheckConstraint("prix_tonne >= 0", name="tarif_prix_positif"),
        CheckConstraint(
            "tolerance_freinte_pct >= 0 AND tolerance_freinte_pct <= 1",
            name="tarif_tolerance_entre_0_et_1",
        ),
        Index("ix_tarifs_transport_axe_client_debut", "axe_id", "client_id", "date_debut"),
    )

    def prix_applicable(self, tonnage: Decimal) -> Decimal:
        """Prix HT de la prestation pour un tonnage donne."""
        if self.base_facturation == BaseFacturationTransport.FORFAIT_CAMION:
            return self.prix_forfait_camion or Decimal("0.00")
        base = max(tonnage, self.tonnage_minimum_facturable)
        return (base * self.prix_tonne).quantize(Decimal("0.01"))


# ===========================================================================
# 2. BOURSE DE FRET : OFFRE -> CANDIDATURE -> NEGOCIATION -> ATTRIBUTION
# ===========================================================================
class OffreFret(DocumentModel):
    """
    Annonce publiee dans la zone publique de l'application chauffeur.

    REGLE DE CONFIDENTIALITE : aucune donnee identifiant le client final
    (nom, adresse exacte, valeur de la marchandise) ne figure ici.
    Ces informations ne sont revelees qu'au transporteur retenu.
    """

    __tablename__ = "offres_fret"

    numero: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    statut: Mapped[StatutOffreFret] = mapped_column(
        EnumCol(StatutOffreFret), default=StatutOffreFret.BROUILLON, nullable=False, index=True
    )

    axe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("axes_transport.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Description publique, volontairement generique
    designation_marchandise: Mapped[str] = mapped_column(String(200), nullable=False)
    tonnage: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unite: Mapped[UniteMesure] = mapped_column(
        EnumCol(UniteMesure), default=UniteMesure.TONNE, nullable=False
    )
    type_vehicule_requis: Mapped[Optional[TypeVehicule]] = mapped_column(
        EnumCol(TypeVehicule), nullable=True
    )
    bachage_requis: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    date_chargement_prevue: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_livraison_souhaitee: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Prix indicatif : ancre la negociation. Champ vide => propositions hautes.
    prix_indicatif_tonne: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    publiee_le: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Fermeture automatique : evite les offres fantomes encore visibles
    expire_le: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    attribuee_le: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    nb_candidatures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    commentaire_interne: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    candidatures: Mapped[List["CandidatureFret"]] = relationship(
        back_populates="offre", cascade="all, delete-orphan"
    )
    attribution: Mapped[Optional["AttributionFret"]] = relationship(
        back_populates="offre", uselist=False
    )

    __table_args__ = (
        CheckConstraint("tonnage > 0", name="offre_tonnage_positif"),
        Index("ix_offres_fret_statut_chargement", "statut", "date_chargement_prevue"),
    )

    @property
    def is_visible_transporteurs(self) -> bool:
        return self.statut in (StatutOffreFret.PUBLIEE, StatutOffreFret.EN_NEGOCIATION)


class CandidatureFret(DocumentModel):
    """
    Positionnement d'un transporteur sur une offre.

    `delai_reponse_secondes` est calcule a la soumission : c'est le critere
    de rapidite, l'un des deux axes d'arbitrage avec le prix.
    """

    __tablename__ = "candidatures_fret"

    offre_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("offres_fret.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chauffeur_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chauffeurs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    vehicule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("vehicules.id", ondelete="SET NULL"), nullable=True
    )
    # Camion non enregistre chez DML (transporteur externe occasionnel)
    immatriculation_declaree: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    capacite_declaree_tonnes: Mapped[Optional[Decimal]] = mapped_column(Quantity, nullable=True)

    statut: Mapped[StatutCandidature] = mapped_column(
        EnumCol(StatutCandidature), default=StatutCandidature.SOUMISE, nullable=False, index=True
    )
    prix_propose_tonne: Mapped[Decimal] = mapped_column(Money, nullable=False)
    montant_propose: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    disponible_le: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    soumise_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delai_reponse_secondes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)

    # Photographie du profil au moment de la candidature (auditable)
    note_transporteur: Mapped[Optional[Decimal]] = mapped_column(Rate, nullable=True)
    nb_missions_a_date: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    offre: Mapped["OffreFret"] = relationship(back_populates="candidatures")
    negociations: Mapped[List["NegociationFret"]] = relationship(
        back_populates="candidature", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("offre_id", "chauffeur_id", name="uq_candidature_offre_chauffeur"),
        CheckConstraint("prix_propose_tonne >= 0", name="candidature_prix_positif"),
        Index("ix_candidatures_fret_offre_prix", "offre_id", "prix_propose_tonne"),
    )


class NegociationFret(BaseModel):
    """
    Chaque contre-proposition, dans les deux sens.

    Conserver l'historique sert trois choses : savoir qui gonfle
    systematiquement ses prix, trancher un litige sur le montant convenu,
    et construire une base de prix de marche par axe et par saison.
    """

    __tablename__ = "negociations_fret"

    candidature_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidatures_fret.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sens: Mapped[SensNegociation] = mapped_column(EnumCol(SensNegociation), nullable=False)
    prix_propose_tonne: Mapped[Decimal] = mapped_column(Money, nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    auteur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True
    )
    horodatage: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    candidature: Mapped["CandidatureFret"] = relationship(back_populates="negociations")

    __table_args__ = (
        Index("ix_negociations_fret_candidature_horodatage", "candidature_id", "horodatage"),
    )


class AttributionFret(DocumentModel):
    """
    Decision finale. Declenche la creation du voyage et l'ouverture de
    l'acces mission pour le seul transporteur retenu.

    `cout_transporteur_*` est le COUT de DML, a distinguer du prix de vente
    au client porte par la mission.
    """

    __tablename__ = "attributions_fret"

    offre_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("offres_fret.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    candidature_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("candidatures_fret.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
    chauffeur_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chauffeurs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("voyages.id", ondelete="SET NULL"), nullable=True, index=True
    )

    cout_transporteur_tonne: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cout_transporteur_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    attribuee_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    attribuee_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True
    )
    motif_choix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    offre: Mapped["OffreFret"] = relationship(back_populates="attribution")

    __table_args__ = (
        CheckConstraint("cout_transporteur_total >= 0", name="attribution_cout_positif"),
    )


# ===========================================================================
# 3. LA MISSION : LE CONTRAT COMMERCIAL AVEC LE CLIENT
# ===========================================================================
class MissionTransport(DocumentModel):
    """
    Un client, une marchandise, un point de depart, une destination.

    GROUPAGE : plusieurs missions peuvent partager le meme `voyage_id`.
    Le voyage est le camion ; la mission est le contrat.
    """

    __tablename__ = "missions_transport"

    numero: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    statut: Mapped[StatutMissionTransport] = mapped_column(
        EnumCol(StatutMissionTransport),
        default=StatutMissionTransport.PLANIFIEE,
        nullable=False,
        index=True,
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    axe_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("axes_transport.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("voyages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    offre_fret_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("offres_fret.id", ondelete="SET NULL"), nullable=True
    )

    # --- Points reels (confidentiels jusqu'a l'attribution)
    adresse_enlevement: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    contact_enlevement: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    telephone_enlevement: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    adresse_livraison: Mapped[str] = mapped_column(String(255), nullable=False)
    nom_destinataire: Mapped[str] = mapped_column(String(150), nullable=False)
    telephone_destinataire: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)

    # --- Tonnages : la base de la facturation
    tonnage_prevu: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    tonnage_charge: Mapped[Optional[Decimal]] = mapped_column(Quantity, nullable=True)
    tonnage_livre: Mapped[Optional[Decimal]] = mapped_column(Quantity, nullable=True)
    ecart_tonnage: Mapped[Optional[Decimal]] = mapped_column(Quantity, nullable=True)
    ecart_dans_tolerance: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)

    # --- Prix de vente (grille figee au moment du contrat : auditable)
    tarif_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("tarifs_transport.id", ondelete="SET NULL"), nullable=True
    )
    prix_vente_tonne: Mapped[Decimal] = mapped_column(Money, nullable=False)
    tonnage_minimum_applique: Mapped[Decimal] = mapped_column(
        Quantity, default=Decimal("0.000"), nullable=False
    )
    base_facturation: Mapped[BaseFacturationTransport] = mapped_column(
        EnumCol(BaseFacturationTransport),
        default=BaseFacturationTransport.TONNAGE_DEPART,
        nullable=False,
    )
    tolerance_freinte_appliquee: Mapped[Decimal] = mapped_column(
        Rate, default=Decimal("0.0050"), nullable=False
    )
    tonnage_facture: Mapped[Optional[Decimal]] = mapped_column(Quantity, nullable=True)
    montant_ht: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    # --- Rentabilite (renseignee par la ventilation du cout du voyage)
    cout_impute: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)

    # --- Chronologie
    date_enlevement_prevue: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_enlevement_reelle: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    date_livraison_prevue: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_livraison_reelle: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Facturation : reutilise la chaine Ventes, avec un compte 706
    facture_vente_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("factures_vente.id", ondelete="SET NULL"), nullable=True, index=True
    )

    valeur_declaree_marchandise: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    assurance_souscrite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    observations: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lignes: Mapped[List["LigneMarchandiseTiers"]] = relationship(
        back_populates="mission", cascade="all, delete-orphan"
    )
    lettre_voiture: Mapped[Optional["LettreDeVoiture"]] = relationship(
        back_populates="mission", uselist=False, cascade="all, delete-orphan"
    )
    litiges: Mapped[List["LitigeTransport"]] = relationship(
        back_populates="mission", cascade="all, delete-orphan"
    )
    ventilation: Mapped[Optional["VentilationCoutVoyage"]] = relationship(
        back_populates="mission", uselist=False
    )

    __table_args__ = (
        CheckConstraint("tonnage_prevu > 0", name="mission_tonnage_prevu_positif"),
        CheckConstraint("prix_vente_tonne >= 0", name="mission_prix_positif"),
        Index("ix_missions_transport_client_statut", "client_id", "statut"),
        Index("ix_missions_transport_voyage_statut", "voyage_id", "statut"),
    )

    # -- Regles metier -----------------------------------------------------
    def tonnage_a_facturer(self) -> Decimal:
        """Applique la base de facturation et le plancher contractuel."""
        if self.base_facturation == BaseFacturationTransport.FORFAIT_CAMION:
            return Decimal("0.000")
        if self.base_facturation == BaseFacturationTransport.TONNAGE_ARRIVEE:
            base = self.tonnage_livre or self.tonnage_charge or self.tonnage_prevu
        else:
            base = self.tonnage_charge or self.tonnage_prevu
        return max(base, self.tonnage_minimum_applique)

    def calculer_montant(self) -> Decimal:
        self.tonnage_facture = self.tonnage_a_facturer()
        self.montant_ht = (self.tonnage_facture * self.prix_vente_tonne).quantize(Decimal("0.01"))
        return self.montant_ht

    def evaluer_freinte(self) -> Optional[bool]:
        """
        Ecart depart/arrivee. Au-dela de la tolerance contractuelle,
        la difference devient un litige a instruire.
        """
        if self.tonnage_charge is None or self.tonnage_livre is None:
            return None
        self.ecart_tonnage = self.tonnage_charge - self.tonnage_livre
        if self.tonnage_charge == 0:
            self.ecart_dans_tolerance = True
        else:
            taux = abs(self.ecart_tonnage) / self.tonnage_charge
            self.ecart_dans_tolerance = taux <= self.tolerance_freinte_appliquee
        return self.ecart_dans_tolerance

    @property
    def marge(self) -> Optional[Decimal]:
        if self.montant_ht is None or self.cout_impute is None:
            return None
        return self.montant_ht - self.cout_impute


class LigneMarchandiseTiers(BaseModel):
    """
    Detail de la marchandise confiee. NE GENERE AUCUN MOUVEMENT DE STOCK :
    cette marchandise n'appartient pas a DML.
    """

    __tablename__ = "lignes_marchandise_tiers"

    mission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("missions_transport.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero_ligne: Mapped[int] = mapped_column(Integer, nullable=False)

    designation: Mapped[str] = mapped_column(String(200), nullable=False)
    nature_emballage: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    nombre_colis: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    poids: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    unite: Mapped[UniteMesure] = mapped_column(
        EnumCol(UniteMesure), default=UniteMesure.TONNE, nullable=False
    )
    volume_m3: Mapped[Optional[Decimal]] = mapped_column(Quantity, nullable=True)

    marchandise_dangereuse: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    marchandise_fragile: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    etat_chargement: Mapped[Optional[EtatMarchandiseTiers]] = mapped_column(
        EnumCol(EtatMarchandiseTiers), nullable=True
    )
    etat_livraison: Mapped[Optional[EtatMarchandiseTiers]] = mapped_column(
        EnumCol(EtatMarchandiseTiers), nullable=True
    )
    valeur_declaree: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)

    mission: Mapped["MissionTransport"] = relationship(back_populates="lignes")

    __table_args__ = (
        UniqueConstraint("mission_id", "numero_ligne", name="uq_ligne_marchandise_mission_numero"),
        CheckConstraint("poids > 0", name="ligne_marchandise_poids_positif"),
    )


class LettreDeVoiture(DocumentModel):
    """
    Document legal accompagnant la marchandise. C'est la piece qui engage
    la responsabilite de DML en cas de perte ou d'avarie : etat contradictoire
    au chargement, etat a la livraison, reserves du destinataire.
    """

    __tablename__ = "lettres_voiture"

    numero: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    mission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("missions_transport.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    expediteur: Mapped[str] = mapped_column(String(150), nullable=False)
    destinataire: Mapped[str] = mapped_column(String(150), nullable=False)
    lieu_chargement: Mapped[str] = mapped_column(String(255), nullable=False)
    lieu_livraison: Mapped[str] = mapped_column(String(255), nullable=False)

    date_emission: Mapped[date] = mapped_column(Date, nullable=False)
    date_chargement: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    date_livraison: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    chauffeur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("chauffeurs.id", ondelete="SET NULL"), nullable=True
    )
    vehicule_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("vehicules.id", ondelete="SET NULL"), nullable=True
    )
    immatriculation: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    # Preuves : signatures et photos horodatees
    signature_expediteur: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    signature_chauffeur: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    signature_destinataire: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    nom_signataire_reception: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    url_photos_chargement: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url_photos_livraison: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    reserves_emises: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    detail_reserves: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    mission: Mapped["MissionTransport"] = relationship(back_populates="lettre_voiture")


# ===========================================================================
# 4. GROUPAGE : VENTILATION DU COUT DU VOYAGE
# ===========================================================================
class VentilationCoutVoyage(BaseModel):
    """
    Coeur analytique du groupage.

    Un camion transporte 12 t pour le client A et 18 t pour le client B.
    Le voyage a coute 520 000 FCFA (prix transporteur + peages + carburant).
    Sans ventilation, aucune marge par client n'existe.

    Cle par defaut : le TONNAGE. La cle VALEUR se justifie quand une
    marchandise de forte valeur mobilise l'assurance et la responsabilite.
    """

    __tablename__ = "ventilations_cout_voyage"

    voyage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("voyages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("missions_transport.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    cle_repartition: Mapped[ClePartitionCout] = mapped_column(
        EnumCol(ClePartitionCout), default=ClePartitionCout.TONNAGE, nullable=False
    )
    base_mission: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    base_voyage_totale: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    quote_part: Mapped[Decimal] = mapped_column(Rate, nullable=False)

    cout_voyage_total: Mapped[Decimal] = mapped_column(Money, nullable=False)
    cout_impute: Mapped[Decimal] = mapped_column(Money, nullable=False)
    calcule_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    commentaire: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    mission: Mapped["MissionTransport"] = relationship(back_populates="ventilation")

    __table_args__ = (
        CheckConstraint("base_voyage_totale > 0", name="ventilation_base_totale_positive"),
        CheckConstraint(
            "quote_part >= 0 AND quote_part <= 1", name="ventilation_quote_part_entre_0_et_1"
        ),
    )


# ===========================================================================
# 5. LITIGES
# ===========================================================================
class LitigeTransport(DocumentModel):
    """
    Manquant, avarie, retard, vol. Trace la reclamation du client, la
    responsabilite retenue et le denouement financier.

    L'imputation au transporteur alimente son profil : c'est ce qui le fera
    sortir du vivier s'il recidive.
    """

    __tablename__ = "litiges_transport"

    numero: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    mission_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("missions_transport.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chauffeur_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("chauffeurs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    type_litige: Mapped[TypeLitigeTransport] = mapped_column(
        EnumCol(TypeLitigeTransport), nullable=False, index=True
    )
    statut: Mapped[StatutLitigeTransport] = mapped_column(
        EnumCol(StatutLitigeTransport),
        default=StatutLitigeTransport.OUVERT,
        nullable=False,
        index=True,
    )
    gravite: Mapped[NiveauAlerte] = mapped_column(
        EnumCol(NiveauAlerte), default=NiveauAlerte.ATTENTION, nullable=False
    )

    date_constat: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    quantite_litigieuse: Mapped[Optional[Decimal]] = mapped_column(Quantity, nullable=True)

    montant_reclame: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    montant_retenu: Mapped[Optional[Decimal]] = mapped_column(Money, nullable=True)
    responsabilite: Mapped[ResponsabiliteLitige] = mapped_column(
        EnumCol(ResponsabiliteLitige),
        default=ResponsabiliteLitige.INDETERMINEE,
        nullable=False,
    )
    impute_transporteur: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    couvert_assurance: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    date_resolution: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resolu_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True
    )

    mission: Mapped["MissionTransport"] = relationship(back_populates="litiges")


# ===========================================================================
# 6. VIVIER DE TRANSPORTEURS
# ===========================================================================
class ProfilTransporteur(BaseModel):
    """
    Reputation d'un transporteur externe dans la bourse de fret.

    `nb_desistements` est le garde-fou du critere "moins cher" : sans lui,
    un transporteur candidate tres bas pour etre retenu, puis se retire ou
    renegocie une fois sur place.
    """

    __tablename__ = "profils_transporteur"

    chauffeur_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chauffeurs.id", ondelete="CASCADE"), nullable=False, unique=True
    )

    note_globale: Mapped[Optional[Decimal]] = mapped_column(Rate, nullable=True, index=True)
    nb_missions_realisees: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nb_missions_a_lheure: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nb_litiges: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    nb_desistements: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    tonnage_cumule: Mapped[Decimal] = mapped_column(
        Quantity, default=Decimal("0.000"), nullable=False
    )
    delai_reponse_moyen_secondes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    date_premiere_mission: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_derniere_mission: Mapped[Optional[date]] = mapped_column(
        Date, nullable=True, index=True
    )

    # Exclusion du vivier
    is_suspendu: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    motif_suspension: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    suspendu_jusquau: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    __table_args__ = (
        CheckConstraint("nb_desistements >= 0", name="profil_desistements_positifs"),
    )

    @property
    def taux_litige(self) -> Optional[Decimal]:
        if not self.nb_missions_realisees:
            return None
        return Decimal(self.nb_litiges) / Decimal(self.nb_missions_realisees)

    def est_eligible(self, seuil_desistements: int = 3) -> bool:
        """
        Eligibilite a la bourse de fret.

        NOTE : la validite du permis et des documents du vehicule est
        verifiee separement (module Logistique) et conditionne aussi
        l'affichage des offres.
        """
        if self.is_suspendu:
            return False
        return self.nb_desistements < seuil_desistements


# ===========================================================================
# 7. ACCES MOBILE DU CHAUFFEUR : DEUX ZONES, EXPIRATION AUTOMATIQUE
# ===========================================================================
class SessionMobile(BaseModel):
    """
    Un appareil, un utilisateur, une fenetre de validite.

    On ne compte JAMAIS sur une desactivation manuelle : personne ne pensera
    a couper l'acces du chauffeur le vendredi soir. L'acces doit mourir seul.
    """

    __tablename__ = "sessions_mobile"

    utilisateur_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("utilisateurs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    identifiant_appareil: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    modele_appareil: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    plateforme: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    version_app: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    appareil_entreprise: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    statut: Mapped[StatutSessionMobile] = mapped_column(
        EnumCol(StatutSessionMobile),
        default=StatutSessionMobile.ACTIVE,
        nullable=False,
        index=True,
    )
    jeton_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ouverte_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    derniere_activite: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    derniere_synchronisation: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expire_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    revoquee_le: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoquee_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True
    )
    motif_revocation: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    acces: Mapped[List["AccesMission"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_sessions_mobile_utilisateur_statut", "utilisateur_id", "statut"),
    )


class AccesMission(BaseModel):
    """
    Droit d'acces a la zone MISSION, rattache a un voyage precis.

    Le chauffeur externe ne recoit pas un compte permanent sur les donnees
    d'exploitation : il recoit une fenetre, qui se referme a la cloture du
    voyage. La zone PUBLIQUE (bourse de fret) reste accessible tant que le
    compte n'est pas suspendu.

    OFFLINE : l'application ecrit en local meme sans jeton valide ; seule la
    SYNCHRONISATION est bloquee. Entre Douala et Garoua le reseau disparait,
    et perdre les donnees d'un voyage serait pire que le risque d'acces.
    """

    __tablename__ = "acces_mission"

    session_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("sessions_mobile.id", ondelete="CASCADE"), nullable=True, index=True
    )
    utilisateur_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("utilisateurs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    chauffeur_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("chauffeurs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    voyage_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("voyages.id", ondelete="CASCADE"), nullable=False, index=True
    )

    zone: Mapped[ZoneApplication] = mapped_column(
        EnumCol(ZoneApplication), default=ZoneApplication.MISSION, nullable=False
    )
    ouvert_le: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expire_le: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    ferme_le: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_actif: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    revoque_le: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    revoque_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("utilisateurs.id", ondelete="SET NULL"), nullable=True
    )
    motif_revocation: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    session: Mapped[Optional["SessionMobile"]] = relationship(back_populates="acces")

    __table_args__ = (
        UniqueConstraint("utilisateur_id", "voyage_id", name="uq_acces_mission_utilisateur_voyage"),
        Index("ix_acces_mission_voyage_actif", "voyage_id", "is_actif"),
    )


__all__ = [
    "AxeTransport",
    "TarifTransport",
    "OffreFret",
    "CandidatureFret",
    "NegociationFret",
    "AttributionFret",
    "MissionTransport",
    "LigneMarchandiseTiers",
    "LettreDeVoiture",
    "VentilationCoutVoyage",
    "LitigeTransport",
    "ProfilTransporteur",
    "SessionMobile",
    "AccesMission",
]

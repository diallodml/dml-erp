"""
DML SARL - ERP | MODULE 8 : COLLECTE VILLAGE & CONSIGNATION
==========================================================

Le vrai flux d'entree de la marchandise chez DML : des collecteurs achetent
au sac dans les marches de village, la marchandise remonte vers les magasins
de Douala, puis elle est vendue aux industriels.

Ce module remplace la logique "camion fournisseur a la barriere" comme point
d'entree principal. `ReceptionBarriere` reste valable pour les livraisons
directes de gros fournisseurs.

Quatre points structurants
--------------------------
1. LE MODE DE DETENTION SE FIGE A L'ENTREE
   Chaque lot est soit PROPRIETE, soit en depot. Jamais "on verra".
   Sans cette decision figee, le comptable ne sait pas quoi enregistrer
   et le bilan est faux. Voir `ModeDetention` dans enums.py pour le
   traitement comptable de chaque mode.

2. L'AVANCE AU COLLECTEUR EST LE PREMIER POINT DE FUITE
   On remet des especes, le collecteur achete, il doit justifier.
   `AvanceCollecteur` suit le cycle complet : remis / justifie / reste du.
   C'est le chiffre que la direction doit voir chaque semaine.

3. ON PAIE AU SAC, ON RECOIT AU KILO
   Le collecteur paie un nombre de sacs ; le magasin pese des kilos.
   L'ecart entre le poids theorique paye et le poids reel recu
   (`ecart_poids_kg`) chiffre, collecteur par collecteur, qui achete bien.

4. L'HUMIDITE EST APPRECIEE A L'OEIL AU MARCHE
   `AppreciationQualiteMarche` enregistre l'estimation sans instrument.
   Quand un humidimetre sera deploye chez les collecteurs, le champ
   `taux_humidite_marche` prendra le relais et l'ecart avec la mesure
   au magasin deviendra mesurable.
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
    Numeric,
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
    AppreciationQualiteMarche,
    BaseAchatMarche,
    Devise,
    ModeDetention,
    ModeReglement,
    StatutAvanceCollecteur,
    StatutCollecte,
    StatutCollecteur,
    StatutReversement,
    TypeCollecteur,
    UniteMesure,
)


# ===========================================================================
# 1. REFERENTIEL : ZONES ET COLLECTEURS
# ===========================================================================
class ZoneCollecte(ReferentielModel):
    """
    Marche de village ou bassin de production.

    Sert d'axe d'analyse : quel marche donne la meilleure qualite, a quel
    prix, a quelle saison. C'est ce qui permet d'orienter les collecteurs
    la ou l'achat est le plus rentable.
    """

    __tablename__ = "zones_collecte"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    libelle: Mapped[str] = mapped_column(String(150), nullable=False)

    village: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    arrondissement: Mapped[Optional[str]] = mapped_column(String(120))
    departement: Mapped[Optional[str]] = mapped_column(String(120), index=True)
    region: Mapped[Optional[str]] = mapped_column(String(120), index=True)

    # Le marche ne se tient pas tous les jours : information operationnelle
    jour_marche: Mapped[Optional[str]] = mapped_column(
        String(60), comment="Jour(s) de tenue du marche hebdomadaire"
    )
    distance_douala_km: Mapped[Optional[Decimal]] = mapped_column(Quantity)
    accessible_saison_pluies: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    observations: Mapped[Optional[str]] = mapped_column(Text)

    collectes: Mapped[List["Collecte"]] = relationship(back_populates="zone")


class Collecteur(ReferentielModel):
    """
    Partenaire qui achete pour le compte de DML dans les marches.

    `mode_detention_habituel` est un defaut de saisie, PAS une regle :
    le mode se decide et se fige sur chaque collecte.
    """

    __tablename__ = "collecteurs"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    nom: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    type_collecteur: Mapped[TypeCollecteur] = mapped_column(
        EnumCol(TypeCollecteur), default=TypeCollecteur.INDEPENDANT, nullable=False
    )
    statut: Mapped[StatutCollecteur] = mapped_column(
        EnumCol(StatutCollecteur), default=StatutCollecteur.ACTIF, nullable=False, index=True
    )

    telephone: Mapped[Optional[str]] = mapped_column(String(40), index=True)
    telephone_mobile_money: Mapped[Optional[str]] = mapped_column(String(40))
    piece_identite: Mapped[Optional[str]] = mapped_column(String(60))
    adresse: Mapped[Optional[str]] = mapped_column(String(255))

    # Lien optionnel vers un employe (collecteur salarie)
    employe_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("employes.id", ondelete="SET NULL"), unique=True
    )
    zone_principale_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("zones_collecte.id", ondelete="SET NULL"), index=True
    )

    # --- Conditions commerciales par defaut
    mode_detention_habituel: Mapped[ModeDetention] = mapped_column(
        EnumCol(ModeDetention), default=ModeDetention.MARGE_FIXE_TONNE, nullable=False
    )
    marge_fixe_tonne: Mapped[Optional[Decimal]] = mapped_column(
        Money, comment="Marge DML par tonne, convenue a l'avance"
    )
    taux_commission: Mapped[Optional[Decimal]] = mapped_column(
        Rate, comment="Uniquement si CONSIGNATION_POURCENTAGE"
    )
    plafond_avance: Mapped[Optional[Decimal]] = mapped_column(Money)

    # --- Reputation (alimentee par les collectes)
    nb_collectes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tonnage_cumule: Mapped[Decimal] = mapped_column(
        Quantity, default=Decimal("0"), nullable=False
    )
    ecart_poids_cumule_kg: Mapped[Decimal] = mapped_column(
        Quantity, default=Decimal("0"), nullable=False,
        comment="Cumul des ecarts poids paye / poids recu : negatif = perte pour DML"
    )
    humidite_moyenne_livree: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    nb_litiges: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    date_derniere_collecte: Mapped[Optional[date]] = mapped_column(Date, index=True)

    avances: Mapped[List["AvanceCollecteur"]] = relationship(back_populates="collecteur")
    collectes: Mapped[List["Collecte"]] = relationship(back_populates="collecteur")
    contrats: Mapped[List["ContratConsignation"]] = relationship(back_populates="collecteur")

    __table_args__ = (
        CheckConstraint(
            "taux_commission IS NULL OR (taux_commission >= 0 AND taux_commission <= 1)",
            name="collecteur_taux_commission_valide",
        ),
    )


class ContratConsignation(DocumentModel):
    """
    L'ecrit avec le collecteur.

    INDISPENSABLE FACE AU FISC : sans contrat ecrit, l'administration peut
    requalifier une consignation en achat-vente, avec redressement de TVA
    sur le chiffre d'affaires entier plutot que sur la seule marge.
    """

    __tablename__ = "contrats_consignation"

    numero: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    collecteur_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collecteurs.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    mode_detention: Mapped[ModeDetention] = mapped_column(
        EnumCol(ModeDetention), nullable=False
    )
    marge_fixe_tonne: Mapped[Optional[Decimal]] = mapped_column(Money)
    taux_commission: Mapped[Optional[Decimal]] = mapped_column(Rate)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    date_signature: Mapped[date] = mapped_column(Date, nullable=False)
    date_debut: Mapped[date] = mapped_column(Date, nullable=False)
    date_fin: Mapped[Optional[date]] = mapped_column(Date)

    # Qui supporte quoi : la reponse determine la qualification juridique
    risque_perte_supporte_par_dml: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="True => achat-vente en substance, quel que soit l'intitule"
    )
    delai_reversement_jours: Mapped[Optional[int]] = mapped_column(Integer)
    document_signe: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    url_document: Mapped[Optional[str]] = mapped_column(Text)
    clauses_particulieres: Mapped[Optional[str]] = mapped_column(Text)

    collecteur: Mapped["Collecteur"] = relationship(back_populates="contrats")

    __table_args__ = (
        CheckConstraint(
            "mode_detention <> 'CONSIGNATION_POURCENTAGE' OR taux_commission IS NOT NULL",
            name="contrat_commission_exige_taux",
        ),
        CheckConstraint(
            "mode_detention <> 'MARGE_FIXE_TONNE' OR marge_fixe_tonne IS NOT NULL",
            name="contrat_marge_fixe_exige_montant",
        ),
    )


# ===========================================================================
# 2. L'AVANCE : PREMIER POINT DE FUITE
# ===========================================================================
class AvanceCollecteur(DocumentModel):
    """
    Especes remises au collecteur pour acheter au marche.

    Cycle : on remet -> il achete -> il justifie par des lignes d'achat ->
    on rapproche. `montant_reste_du` est le chiffre a surveiller.

    Le paiement au marche se fait en especes : c'est structurellement le
    moment ou l'argent peut disparaitre sans trace. D'ou l'exigence de
    justification ligne a ligne.
    """

    __tablename__ = "avances_collecteur"

    numero: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    collecteur_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collecteurs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    statut: Mapped[StatutAvanceCollecteur] = mapped_column(
        EnumCol(StatutAvanceCollecteur),
        default=StatutAvanceCollecteur.ACCORDEE,
        nullable=False,
        index=True,
    )

    date_remise: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    montant_remis: Mapped[Decimal] = mapped_column(Money, nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    mode_remise: Mapped[ModeReglement] = mapped_column(
        EnumCol(ModeReglement), default=ModeReglement.ESPECES, nullable=False
    )

    # D'ou sort l'argent : trace obligatoire vers la tresorerie
    compte_tresorerie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("comptes_tresorerie.id", ondelete="SET NULL"), index=True
    )
    mouvement_tresorerie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("mouvements_tresorerie.id", ondelete="SET NULL")
    )
    remis_par_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("utilisateurs.id", ondelete="SET NULL")
    )

    # --- Apurement
    montant_justifie: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False
    )
    montant_rendu: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False
    )
    montant_reste_du: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False, index=True
    )
    date_apurement: Mapped[Optional[date]] = mapped_column(Date)

    zone_prevue_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("zones_collecte.id", ondelete="SET NULL")
    )
    objet: Mapped[Optional[str]] = mapped_column(String(255))
    observations: Mapped[Optional[str]] = mapped_column(Text)

    collecteur: Mapped["Collecteur"] = relationship(back_populates="avances")
    collectes: Mapped[List["Collecte"]] = relationship(back_populates="avance")

    __table_args__ = (
        CheckConstraint("montant_remis > 0", name="avance_montant_positif"),
        CheckConstraint(
            "montant_justifie >= 0 AND montant_rendu >= 0",
            name="avance_apurement_positif",
        ),
        Index("ix_avances_collecteur_statut_date", "statut", "date_remise"),
    )

    def recalculer_apurement(self) -> Decimal:
        """Met a jour le reste du et le statut."""
        self.montant_reste_du = (
            self.montant_remis - self.montant_justifie - self.montant_rendu
        )
        if self.montant_reste_du <= Decimal("0"):
            self.statut = StatutAvanceCollecteur.APUREE
        elif self.montant_justifie > Decimal("0"):
            self.statut = StatutAvanceCollecteur.PARTIELLEMENT_JUSTIFIEE
        return self.montant_reste_du


# ===========================================================================
# 3. LA COLLECTE : CE QUI SE PASSE AU MARCHE
# ===========================================================================
class Collecte(DocumentModel):
    """
    Une campagne d'achat sur un marche : le collecteur achete plusieurs
    lots de sacs, souvent aupres de plusieurs vendeurs, sur un ou
    plusieurs jours de marche.

    Le MODE DE DETENTION se fige ici et ne change plus.
    """

    __tablename__ = "collectes"

    numero: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    collecteur_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collecteurs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    zone_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("zones_collecte.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    avance_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("avances_collecteur.id", ondelete="SET NULL"), index=True
    )
    contrat_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("contrats_consignation.id", ondelete="SET NULL")
    )

    statut: Mapped[StatutCollecte] = mapped_column(
        EnumCol(StatutCollecte), default=StatutCollecte.EN_COURS, nullable=False, index=True
    )

    # --- LE CHAMP STRUCTURANT : fige a la creation, ne change plus
    mode_detention: Mapped[ModeDetention] = mapped_column(
        EnumCol(ModeDetention), nullable=False, index=True
    )
    marge_fixe_tonne_appliquee: Mapped[Optional[Decimal]] = mapped_column(Money)
    taux_commission_applique: Mapped[Optional[Decimal]] = mapped_column(Rate)

    date_debut: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    date_cloture: Mapped[Optional[date]] = mapped_column(Date)
    campagne_agricole: Mapped[Optional[str]] = mapped_column(String(20), index=True)

    # --- Totaux au marche (payes)
    nombre_sacs_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    poids_theorique_kg: Mapped[Decimal] = mapped_column(
        Quantity, default=Decimal("0"), nullable=False,
        comment="Nb sacs x poids nominal du sac : ce que DML croit avoir achete"
    )
    montant_achat_total: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False
    )
    frais_annexes: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False,
        comment="Manutention, taxes de marche, sacherie, gardiennage"
    )
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    # --- Ce qui arrive reellement au magasin
    magasin_destination_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("magasins.id", ondelete="SET NULL"), index=True
    )
    voyage_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("voyages.id", ondelete="SET NULL"), index=True
    )
    nombre_sacs_expedies: Mapped[Optional[int]] = mapped_column(Integer)
    nombre_sacs_recus: Mapped[Optional[int]] = mapped_column(Integer)
    poids_reel_kg: Mapped[Optional[Decimal]] = mapped_column(
        Quantity, comment="Pese a l'arrivee au magasin"
    )
    ecart_poids_kg: Mapped[Optional[Decimal]] = mapped_column(
        Quantity, index=True,
        comment="poids_reel - poids_theorique. Negatif = DML a paye du vide."
    )
    ecart_sacs: Mapped[Optional[int]] = mapped_column(Integer)

    # --- Qualite constatee au magasin (l'instrument, enfin)
    taux_humidite_magasin: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    taux_impuretes_magasin: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    date_reception_magasin: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True)
    )

    observations: Mapped[Optional[str]] = mapped_column(Text)

    collecteur: Mapped["Collecteur"] = relationship(back_populates="collectes")
    zone: Mapped["ZoneCollecte"] = relationship(back_populates="collectes")
    avance: Mapped[Optional["AvanceCollecteur"]] = relationship(back_populates="collectes")
    lignes: Mapped[List["LigneCollecte"]] = relationship(
        back_populates="collecte", cascade="all, delete-orphan"
    )
    reversements: Mapped[List["ReversementCollecteur"]] = relationship(
        back_populates="collecte"
    )

    __table_args__ = (
        CheckConstraint("nombre_sacs_total >= 0", name="collecte_sacs_positifs"),
        CheckConstraint(
            "mode_detention <> 'MARGE_FIXE_TONNE' OR marge_fixe_tonne_appliquee IS NOT NULL",
            name="collecte_marge_fixe_exige_montant",
        ),
        Index("ix_collectes_collecteur_statut", "collecteur_id", "statut"),
        Index("ix_collectes_zone_date", "zone_id", "date_debut"),
    )

    # -- Regles metier -----------------------------------------------------
    def calculer_ecart_poids(self) -> Optional[Decimal]:
        """
        Ecart entre le poids paye (theorique, au sac) et le poids recu.

        C'est LE chiffre qui dit si un collecteur achete bien. Un ecart
        systematiquement negatif signifie des sacs sous-remplis, ou du
        grain qui disparait en route.
        """
        if self.poids_reel_kg is None or self.poids_theorique_kg is None:
            return None
        self.ecart_poids_kg = self.poids_reel_kg - self.poids_theorique_kg
        if self.nombre_sacs_recus is not None and self.nombre_sacs_expedies is not None:
            self.ecart_sacs = self.nombre_sacs_recus - self.nombre_sacs_expedies
        return self.ecart_poids_kg

    @property
    def cout_revient_kg(self) -> Optional[Decimal]:
        """Cout reel au kilo effectivement recu, frais annexes compris."""
        base = self.poids_reel_kg or self.poids_theorique_kg
        if not base:
            return None
        total = self.montant_achat_total + self.frais_annexes
        return (total / base).quantize(Decimal("0.01"))

    @property
    def is_hors_bilan(self) -> bool:
        """Seule la vraie commission sort du bilan de DML."""
        return self.mode_detention == ModeDetention.CONSIGNATION_POURCENTAGE


class LigneCollecte(BaseModel):
    """
    Un achat elementaire au marche : tant de sacs, a tel prix, aupres de
    tel vendeur.

    C'est la piece justificative de l'avance. Sans ces lignes, l'avance
    ne peut pas etre apuree.
    """

    __tablename__ = "lignes_collecte"

    collecte_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collectes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    numero_ligne: Mapped[int] = mapped_column(Integer, nullable=False)
    produit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("produits.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    date_achat: Mapped[date] = mapped_column(Date, nullable=False)
    nom_vendeur: Mapped[Optional[str]] = mapped_column(
        String(180), comment="Producteur ou grossiste du marche"
    )
    telephone_vendeur: Mapped[Optional[str]] = mapped_column(String(40))

    # --- On paie au sac
    base_achat: Mapped[BaseAchatMarche] = mapped_column(
        EnumCol(BaseAchatMarche), default=BaseAchatMarche.AU_SAC, nullable=False
    )
    nombre_sacs: Mapped[Optional[int]] = mapped_column(Integer)
    poids_nominal_sac_kg: Mapped[Optional[Decimal]] = mapped_column(
        Quantity, comment="Poids suppose d'un sac (100 kg, 50 kg...)"
    )
    quantite_kg: Mapped[Optional[Decimal]] = mapped_column(Quantity)
    prix_unitaire: Mapped[Decimal] = mapped_column(
        Money, nullable=False, comment="Prix par sac ou par kg selon base_achat"
    )
    montant: Mapped[Decimal] = mapped_column(Money, nullable=False)
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    # --- Qualite appreciee sans instrument
    appreciation_qualite: Mapped[AppreciationQualiteMarche] = mapped_column(
        EnumCol(AppreciationQualiteMarche),
        default=AppreciationQualiteMarche.NON_APPRECIE,
        nullable=False,
    )
    taux_humidite_marche: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), comment="Renseigne uniquement si un humidimetre est disponible"
    )

    observations: Mapped[Optional[str]] = mapped_column(Text)

    collecte: Mapped["Collecte"] = relationship(back_populates="lignes")

    __table_args__ = (
        UniqueConstraint("collecte_id", "numero_ligne", name="uq_ligne_collecte_numero"),
        CheckConstraint("montant >= 0", name="ligne_collecte_montant_positif"),
        CheckConstraint(
            "base_achat <> 'AU_SAC' OR nombre_sacs IS NOT NULL",
            name="ligne_collecte_au_sac_exige_nombre",
        ),
    )

    def poids_theorique(self) -> Decimal:
        """Poids suppose achete : c'est sur cette base que DML a paye."""
        if self.base_achat == BaseAchatMarche.AU_SAC and self.nombre_sacs:
            nominal = self.poids_nominal_sac_kg or Decimal("100.000")
            return Decimal(self.nombre_sacs) * nominal
        return self.quantite_kg or Decimal("0.000")

    def calculer_montant(self) -> Decimal:
        if self.base_achat == BaseAchatMarche.AU_SAC and self.nombre_sacs:
            self.montant = (Decimal(self.nombre_sacs) * self.prix_unitaire).quantize(
                Decimal("0.01")
            )
        elif self.quantite_kg:
            self.montant = (self.quantite_kg * self.prix_unitaire).quantize(
                Decimal("0.01")
            )
        return self.montant


# ===========================================================================
# 4. LE REVERSEMENT AU COLLECTEUR
# ===========================================================================
class ReversementCollecteur(DocumentModel):
    """
    Ce que DML doit au collecteur apres la vente aux industriels.

    En consignation, DML detient de l'argent qui ne lui appartient pas.
    Ce montant doit etre visible en permanence : c'est une dette, pas une
    marge disponible.

    Le solde d'une avance non apuree se compense ici plutot que de courir
    apres l'argent separement.
    """

    __tablename__ = "reversements_collecteur"

    numero: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    collecteur_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("collecteurs.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    collecte_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("collectes.id", ondelete="SET NULL"), index=True
    )

    statut: Mapped[StatutReversement] = mapped_column(
        EnumCol(StatutReversement), default=StatutReversement.A_PAYER, nullable=False, index=True
    )
    mode_detention: Mapped[ModeDetention] = mapped_column(
        EnumCol(ModeDetention), nullable=False
    )

    # --- Base de calcul
    tonnage_vendu: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    montant_vente_brut: Mapped[Decimal] = mapped_column(
        Money, nullable=False, comment="Encaisse aupres de l'industriel"
    )
    part_dml: Mapped[Decimal] = mapped_column(
        Money, nullable=False, comment="Marge fixe x tonnage, ou % du montant"
    )
    frais_deduits: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False,
        comment="Transport, manutention, stockage refactures au collecteur"
    )
    avance_compensee: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False
    )
    montant_net_du: Mapped[Decimal] = mapped_column(Money, nullable=False, index=True)
    montant_paye: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False
    )
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)

    date_calcul: Mapped[date] = mapped_column(Date, nullable=False)
    date_echeance: Mapped[Optional[date]] = mapped_column(Date, index=True)
    date_paiement: Mapped[Optional[date]] = mapped_column(Date)
    mode_paiement: Mapped[Optional[ModeReglement]] = mapped_column(EnumCol(ModeReglement))
    reference_paiement: Mapped[Optional[str]] = mapped_column(String(120))
    compte_tresorerie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("comptes_tresorerie.id", ondelete="SET NULL")
    )
    ecriture_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("ecritures_comptables.id", ondelete="SET NULL")
    )

    observations: Mapped[Optional[str]] = mapped_column(Text)

    collecte: Mapped[Optional["Collecte"]] = relationship(back_populates="reversements")

    __table_args__ = (
        CheckConstraint("tonnage_vendu > 0", name="reversement_tonnage_positif"),
        CheckConstraint("montant_paye >= 0", name="reversement_paye_positif"),
        Index("ix_reversements_collecteur_id_statut", "collecteur_id", "statut"),
    )

    def calculer_net(self) -> Decimal:
        """Ce qui reste du au collecteur, avances et frais deduits."""
        self.montant_net_du = (
            self.montant_vente_brut
            - self.part_dml
            - self.frais_deduits
            - self.avance_compensee
        )
        return self.montant_net_du

    @property
    def solde_a_payer(self) -> Decimal:
        return self.montant_net_du - self.montant_paye


__all__ = [
    "ZoneCollecte",
    "Collecteur",
    "ContratConsignation",
    "AvanceCollecteur",
    "Collecte",
    "LigneCollecte",
    "ReversementCollecteur",
]

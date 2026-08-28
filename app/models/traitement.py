"""
DML SARL - ERP | MODULE 9 : TRAITEMENT CHEZ PRESTATAIRE
======================================================

Entre le magasin DML et l'industriel, la marchandise passe chez un
prestataire : sechage, triage, fumigation. Elle ne revient jamais chez
DML -- elle part de chez le prestataire directement vers le client.

Trois points structurants
-------------------------
1. LE STOCK NE DISPARAIT PAS, IL SE DEPLACE
   La sortie du magasin DML est un TRANSFERT vers un magasin de type
   SOUS_TRAITE. A tout moment on sait ou est la marchandise et qui en
   repond. Une simple sortie de stock ferait perdre sa trace.

2. LE POIDS DIMINUE, LE COUT AU KILO AUGMENTE
   Du mais a 17 % seche a 13 % perd environ 4,6 % de son poids. Sur
   19 tonnes, ce sont 850 kg qui s'evaporent -- plus le cout du
   traitement. Sans ce recalcul, le prix de revient est faux et la
   marge de vente est surestimee.

3. LE RENDEMENT DU PRESTATAIRE EST MESURE
   `perte_theorique_kg` applique la formule de deshydratation ; l'ecart
   avec la perte reelle est ce qui n'est pas explique par la physique.
   Un ecart repete chez le meme prestataire est une information qui vaut
   cher.
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
    BaseFacturationTraitement,
    Devise,
    NiveauAlerte,
    StatutTraitement,
    TypeTraitement,
)


# ===========================================================================
# 1. LE PRESTATAIRE
# ===========================================================================
class Prestataire(ReferentielModel):
    """
    Entreprise qui traite la marchandise avant livraison a l'industriel.

    `magasin_id` pointe vers un magasin de type SOUS_TRAITE : c'est la que
    le stock de DML se trouve pendant le traitement.
    """

    __tablename__ = "prestataires"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    nom: Mapped[str] = mapped_column(String(180), nullable=False, index=True)
    telephone: Mapped[Optional[str]] = mapped_column(String(40))
    adresse: Mapped[Optional[str]] = mapped_column(String(255))
    ville: Mapped[str] = mapped_column(String(80), default="Douala", nullable=False)
    contact_principal: Mapped[Optional[str]] = mapped_column(String(150))

    # Le stock detenu chez ce prestataire vit dans ce magasin virtuel
    magasin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("magasins.id", ondelete="SET NULL"), unique=True, index=True
    )

    # --- Conditions commerciales
    types_traitement: Mapped[Optional[str]] = mapped_column(
        String(255), comment="Prestations proposees, en clair"
    )
    prix_tonne: Mapped[Optional[Decimal]] = mapped_column(Money)
    base_facturation: Mapped[BaseFacturationTraitement] = mapped_column(
        EnumCol(BaseFacturationTraitement),
        default=BaseFacturationTraitement.TONNE_ENTREE,
        nullable=False,
        comment="Tonne entree par defaut : son travail porte sur ce qu'il recoit",
    )
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    delai_habituel_jours: Mapped[Optional[int]] = mapped_column(Integer)
    capacite_tonnes_jour: Mapped[Optional[Decimal]] = mapped_column(Quantity)

    # --- Reputation, alimentee par les traitements
    nb_traitements: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tonnage_cumule: Mapped[Decimal] = mapped_column(
        Quantity, default=Decimal("0"), nullable=False
    )
    perte_inexpliquee_cumulee_kg: Mapped[Decimal] = mapped_column(
        Quantity, default=Decimal("0"), nullable=False,
        comment="Cumul des ecarts entre perte reelle et perte theorique de sechage"
    )
    nb_litiges: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    assurance_marchandise: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
        comment="Le prestataire couvre-t-il la marchandise qu'il detient ?"
    )
    contrat_signe: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    observations: Mapped[Optional[str]] = mapped_column(Text)

    traitements: Mapped[List["Traitement"]] = relationship(back_populates="prestataire")


# ===========================================================================
# 2. LE TRAITEMENT
# ===========================================================================
class Traitement(DocumentModel):
    """
    Un lot part chez le prestataire, en ressort plus leger et plus sec.

    Le lot d'origine est diminue ; un lot fils est cree avec le poids et
    le cout reels apres traitement. C'est ce lot fils qui sera livre.
    """

    __tablename__ = "traitements"

    numero: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    prestataire_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prestataires.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lots.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    lot_traite_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("lots.id", ondelete="SET NULL"), index=True,
        comment="Lot fils cree en sortie de traitement"
    )

    statut: Mapped[StatutTraitement] = mapped_column(
        EnumCol(StatutTraitement), default=StatutTraitement.PLANIFIE,
        nullable=False, index=True,
    )
    type_traitement: Mapped[TypeTraitement] = mapped_column(
        EnumCol(TypeTraitement), default=TypeTraitement.SECHAGE, nullable=False
    )

    # --- Mouvements de stock : le transfert aller
    mouvement_sortie_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("mouvements_stock.id", ondelete="SET NULL")
    )
    mouvement_entree_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("mouvements_stock.id", ondelete="SET NULL")
    )

    # --- Chronologie
    date_expedition: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    date_retour_prevue: Mapped[Optional[date]] = mapped_column(Date)
    date_fin: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # --- Poids : le coeur du module
    poids_entree_kg: Mapped[Decimal] = mapped_column(Quantity, nullable=False)
    poids_sortie_kg: Mapped[Optional[Decimal]] = mapped_column(Quantity)
    perte_reelle_kg: Mapped[Optional[Decimal]] = mapped_column(Quantity, index=True)
    perte_theorique_kg: Mapped[Optional[Decimal]] = mapped_column(
        Quantity, comment="Perte expliquee par la deshydratation seule"
    )
    perte_inexpliquee_kg: Mapped[Optional[Decimal]] = mapped_column(
        Quantity, index=True,
        comment="perte_reelle - perte_theorique : ce que la physique n'explique pas"
    )

    # --- Qualite avant / apres
    humidite_entree: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    humidite_sortie: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    impuretes_entree: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))
    impuretes_sortie: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2))

    # --- Cout
    prix_tonne_applique: Mapped[Optional[Decimal]] = mapped_column(Money)
    base_facturation: Mapped[BaseFacturationTraitement] = mapped_column(
        EnumCol(BaseFacturationTraitement),
        default=BaseFacturationTraitement.TONNE_ENTREE,
        nullable=False,
    )
    tonnage_facture: Mapped[Optional[Decimal]] = mapped_column(Quantity)
    cout_traitement: Mapped[Optional[Decimal]] = mapped_column(Money)
    frais_transport: Mapped[Decimal] = mapped_column(
        Money, default=Decimal("0"), nullable=False
    )
    devise: Mapped[Devise] = mapped_column(EnumCol(Devise), default=Devise.XAF, nullable=False)
    facture_recue: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reference_facture: Mapped[Optional[str]] = mapped_column(String(80))

    # --- Suivi
    niveau_alerte: Mapped[Optional[NiveauAlerte]] = mapped_column(EnumCol(NiveauAlerte))
    observations: Mapped[Optional[str]] = mapped_column(Text)

    prestataire: Mapped["Prestataire"] = relationship(back_populates="traitements")

    __table_args__ = (
        CheckConstraint("poids_entree_kg > 0", name="traitement_poids_entree_positif"),
        CheckConstraint(
            "poids_sortie_kg IS NULL OR poids_sortie_kg > 0",
            name="traitement_poids_sortie_positif",
        ),
        Index("ix_traitements_prestataire_statut", "prestataire_id", "statut"),
    )

    # -- Regles metier -----------------------------------------------------
    def calculer_perte_theorique(self) -> Optional[Decimal]:
        """
        Perte de poids expliquee par la seule deshydratation.

        Formule standard du sechage des grains :
            poids_sec = poids_humide x (100 - humidite_depart)
                                     / (100 - humidite_arrivee)

        Exemple : 19 240 kg a 17 % seches a 13 %
            19 240 x (100-17)/(100-13) = 18 355 kg  ->  885 kg de perte
        """
        if self.humidite_entree is None or self.humidite_sortie is None:
            return None
        if self.humidite_sortie >= Decimal("100"):
            return None
        poids_attendu = (
            self.poids_entree_kg
            * (Decimal("100") - self.humidite_entree)
            / (Decimal("100") - self.humidite_sortie)
        )
        self.perte_theorique_kg = (self.poids_entree_kg - poids_attendu).quantize(
            Decimal("0.001")
        )
        return self.perte_theorique_kg

    def evaluer_rendement(self) -> Optional[Decimal]:
        """
        Compare la perte reelle a la perte theorique.

        L'ecart est ce que le sechage n'explique pas : grain reste sur
        place, mauvaise pesee, ou detournement. Un ecart repete chez le
        meme prestataire merite une conversation.
        """
        if self.poids_sortie_kg is None:
            return None
        self.perte_reelle_kg = self.poids_entree_kg - self.poids_sortie_kg
        theorique = self.calculer_perte_theorique()
        if theorique is None:
            self.perte_inexpliquee_kg = None
            return None
        self.perte_inexpliquee_kg = (self.perte_reelle_kg - theorique).quantize(
            Decimal("0.001")
        )

        # Alerte proportionnee au poids traite
        if self.poids_entree_kg > 0:
            taux = abs(self.perte_inexpliquee_kg) / self.poids_entree_kg
            if taux >= Decimal("0.03"):
                self.niveau_alerte = NiveauAlerte.URGENCE
            elif taux >= Decimal("0.015"):
                self.niveau_alerte = NiveauAlerte.CRITIQUE
            elif taux >= Decimal("0.005"):
                self.niveau_alerte = NiveauAlerte.ATTENTION
            else:
                self.niveau_alerte = NiveauAlerte.INFO
        return self.perte_inexpliquee_kg

    def calculer_cout(self) -> Optional[Decimal]:
        """Facture du prestataire selon la base convenue."""
        if self.prix_tonne_applique is None:
            return None
        if self.base_facturation == BaseFacturationTraitement.FORFAIT_LOT:
            self.tonnage_facture = None
            self.cout_traitement = self.prix_tonne_applique
            return self.cout_traitement

        base_kg = (
            self.poids_sortie_kg
            if self.base_facturation == BaseFacturationTraitement.TONNE_SORTIE
            and self.poids_sortie_kg is not None
            else self.poids_entree_kg
        )
        self.tonnage_facture = (base_kg / Decimal("1000")).quantize(Decimal("0.001"))
        self.cout_traitement = (
            self.tonnage_facture * self.prix_tonne_applique
        ).quantize(Decimal("0.01"))
        return self.cout_traitement

    @property
    def rendement_pct(self) -> Optional[Decimal]:
        """Part du poids entre qui ressort effectivement."""
        if self.poids_sortie_kg is None or not self.poids_entree_kg:
            return None
        return (self.poids_sortie_kg / self.poids_entree_kg * 100).quantize(
            Decimal("0.01")
        )


__all__ = ["Prestataire", "Traitement"]

"""
DML SARLU - ERP | Package `models`
==================================

Importer ce module suffit a enregistrer l'integralite du schema dans
`Base.metadata` (indispensable pour Alembic et pour la resolution des
relations declarees par chaine de caracteres).

    from dml_erp.models import Base
    Base.metadata.create_all(engine)
"""

from .base import (
    AuditMixin,
    Base,
    BaseModel,
    DocumentModel,
    ReferentielModel,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)

# --- Enumerations
from . import enums  # noqa: F401

# --- Module 6 : RH & Securite (charge en premier : reference par tous)
from .rh_securite import (
    Absence,
    AffectationMagasin,
    AvanceSalaire,
    BulletinPaie,
    Departement,
    Employe,
    JournalAudit,
    Permission,
    Pointage,
    Role,
    Utilisateur,
    role_permission_table,
    utilisateur_role_table,
)

# --- Module 5 : Finance & Comptabilite
from .finance import (
    BalanceCompte,
    CategorieDepense,
    CompteCourantAssocie,
    CompteOHADA,
    CompteTresorerie,
    DeclarationFiscale,
    EcritureComptable,
    ExerciceComptable,
    JournalComptable,
    LigneEcriture,
    MappingPosteDSF,
    MouvementCompteCourant,
    MouvementTresorerie,
    PosteDSF,
    TransfertTresorerie,
)

# --- Module 2 : Stocks & Multi-magasins
from .stocks import (
    AlerteIoT,
    Capteur,
    DeclarationPerte,
    Emplacement,
    FamilleProduit,
    Inventaire,
    LigneInventaire,
    LigneTransfert,
    Lot,
    Magasin,
    MesureCapteur,
    MouvementStock,
    Produit,
    TransfertStock,
)

# --- Module 3 : Achats & Controle qualite
from .achats import (
    CommandeAchat,
    ContactFournisseur,
    ControleQualite,
    FactureAchat,
    Fournisseur,
    LigneCommandeAchat,
    LigneFactureAchat,
    ReceptionBarriere,
    ReglementFournisseur,
)

# --- Module 1 : Logistique, Flotte & Chauffeurs
from .logistique import (
    Chauffeur,
    DepenseVoyage,
    DocumentVehicule,
    EvaluationChauffeur,
    IncidentVoyage,
    Maintenance,
    PermisConduire,
    PlanMaintenance,
    PositionVoyage,
    RavitaillementCarburant,
    Vehicule,
    Voyage,
)

# --- Module 4 : Ventes & CRM
from .ventes import (
    BonCommandeClient,
    BonLivraison,
    Client,
    ContactClient,
    FactureVente,
    InteractionCRM,
    LigneBonCommande,
    LigneBonLivraison,
    LigneFactureVente,
    LigneProforma,
    Proforma,
    RelanceClient,
    ReglementClient,
)

# --- Module 7 : Transport pour compte de tiers (bourse de fret, groupage)
from .transport import (
    AccesMission,
    AttributionFret,
    AxeTransport,
    CandidatureFret,
    LettreDeVoiture,
    LigneMarchandiseTiers,
    LitigeTransport,
    MissionTransport,
    NegociationFret,
    OffreFret,
    ProfilTransporteur,
    SessionMobile,
    TarifTransport,
    VentilationCoutVoyage,
)

__all__ = [
    # Socle
    "Base", "BaseModel", "DocumentModel", "ReferentielModel",
    "UUIDMixin", "TimestampMixin", "SoftDeleteMixin", "AuditMixin",
    "enums",
    # RH & Securite
    "Role", "Permission", "Utilisateur", "AffectationMagasin", "JournalAudit",
    "Departement", "Employe", "Pointage", "Absence", "AvanceSalaire", "BulletinPaie",
    "role_permission_table", "utilisateur_role_table",
    # Logistique
    "Chauffeur", "PermisConduire", "EvaluationChauffeur", "Vehicule",
    "DocumentVehicule", "PlanMaintenance", "Maintenance", "Voyage",
    "DepenseVoyage", "RavitaillementCarburant", "IncidentVoyage", "PositionVoyage",
    # Stocks
    "Magasin", "Emplacement", "FamilleProduit", "Produit", "Lot", "MouvementStock",
    "TransfertStock", "LigneTransfert", "DeclarationPerte", "Inventaire",
    "LigneInventaire", "Capteur", "MesureCapteur", "AlerteIoT",
    # Achats
    "Fournisseur", "ContactFournisseur", "CommandeAchat", "LigneCommandeAchat",
    "ReceptionBarriere", "ControleQualite", "FactureAchat", "LigneFactureAchat",
    "ReglementFournisseur",
    # Ventes
    "Client", "ContactClient", "Proforma", "LigneProforma", "BonCommandeClient",
    "LigneBonCommande", "BonLivraison", "LigneBonLivraison", "FactureVente",
    "LigneFactureVente", "ReglementClient", "RelanceClient", "InteractionCRM",
    # Finance
    "ExerciceComptable", "CompteOHADA", "JournalComptable", "CompteTresorerie",
    "CompteCourantAssocie", "MouvementCompteCourant", "CategorieDepense",
    "MouvementTresorerie", "TransfertTresorerie", "EcritureComptable",
    "LigneEcriture", "DeclarationFiscale", "BalanceCompte", "PosteDSF",
    "MappingPosteDSF",
    # Transport pour compte de tiers
    "AxeTransport", "TarifTransport", "OffreFret", "CandidatureFret",
    "NegociationFret", "AttributionFret", "MissionTransport",
    "LigneMarchandiseTiers", "LettreDeVoiture", "VentilationCoutVoyage",
    "LitigeTransport", "ProfilTransporteur", "SessionMobile", "AccesMission",
]

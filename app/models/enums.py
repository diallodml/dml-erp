"""
DML SARLU - ERP
Catalogue centralise des enumerations metier.

Regle : toute valeur discrete du domaine est declaree ici, jamais en dur
dans les modeles ni dans les services.
"""

from __future__ import annotations

from enum import Enum


# ===========================================================================
# TRANSVERSE
# ===========================================================================
class Devise(str, Enum):
    XAF = "XAF"          # Franc CFA BEAC (devise de tenue de compte)
    EUR = "EUR"
    USD = "USD"
    NGN = "NGN"          # Naira (corridor Nigeria)
    XOF = "XOF"


class UniteMesure(str, Enum):
    KG = "KG"
    TONNE = "TONNE"
    SAC = "SAC"
    LITRE = "LITRE"
    UNITE = "UNITE"
    M3 = "M3"


class StatutValidation(str, Enum):
    BROUILLON = "BROUILLON"
    SOUMIS = "SOUMIS"
    VALIDE = "VALIDE"
    REFUSE = "REFUSE"
    ANNULE = "ANNULE"


class NiveauAlerte(str, Enum):
    INFO = "INFO"
    ATTENTION = "ATTENTION"
    CRITIQUE = "CRITIQUE"
    URGENCE = "URGENCE"


# ===========================================================================
# MODULE 6 - RH & SECURITE
# ===========================================================================
class Sexe(str, Enum):
    MASCULIN = "MASCULIN"
    FEMININ = "FEMININ"


class SituationMatrimoniale(str, Enum):
    CELIBATAIRE = "CELIBATAIRE"
    MARIE = "MARIE"
    DIVORCE = "DIVORCE"
    VEUF = "VEUF"


class TypeContrat(str, Enum):
    CDI = "CDI"
    CDD = "CDD"
    STAGE = "STAGE"
    JOURNALIER = "JOURNALIER"          # manutentionnaires / dockers
    PRESTATAIRE = "PRESTATAIRE"
    APPRENTISSAGE = "APPRENTISSAGE"


class StatutEmploye(str, Enum):
    ACTIF = "ACTIF"
    SUSPENDU = "SUSPENDU"
    CONGE = "CONGE"
    DEMISSIONNE = "DEMISSIONNE"
    LICENCIE = "LICENCIE"
    RETRAITE = "RETRAITE"


class StatutPointage(str, Enum):
    PRESENT = "PRESENT"
    RETARD = "RETARD"
    ABSENT = "ABSENT"
    MISSION = "MISSION"
    CONGE = "CONGE"
    REPOS = "REPOS"


class TypeAbsence(str, Enum):
    CONGE_ANNUEL = "CONGE_ANNUEL"
    MALADIE = "MALADIE"
    MATERNITE = "MATERNITE"
    PERMISSION = "PERMISSION"
    ABSENCE_INJUSTIFIEE = "ABSENCE_INJUSTIFIEE"
    MISE_A_PIED = "MISE_A_PIED"
    DECES_FAMILLE = "DECES_FAMILLE"


class TypeAction(str, Enum):
    """Actions elementaires du RBAC."""
    LIRE = "LIRE"
    CREER = "CREER"
    MODIFIER = "MODIFIER"
    SUPPRIMER = "SUPPRIMER"
    VALIDER = "VALIDER"
    EXPORTER = "EXPORTER"
    ANNULER = "ANNULER"


class PorteeDonnees(str, Enum):
    """Portee d'une permission : le coeur de la restriction par magasin/chauffeur."""
    GLOBAL = "GLOBAL"                   # DG, DAF : tout voir
    MAGASIN_AFFECTE = "MAGASIN_AFFECTE" # magasinier : uniquement son magasin
    PROPRE = "PROPRE"                   # chauffeur : uniquement ses propres feuilles de route
    DEPARTEMENT = "DEPARTEMENT"


# ===========================================================================
# MODULE 1 - LOGISTIQUE, FLOTTE & CHAUFFEURS
# ===========================================================================
class TypeChauffeur(str, Enum):
    INTERNE = "INTERNE"                 # salarie DML
    SOUS_TRAITANT = "SOUS_TRAITANT"     # rattache a un transporteur externe
    OCCASIONNEL = "OCCASIONNEL"


class StatutChauffeur(str, Enum):
    DISPONIBLE = "DISPONIBLE"
    EN_MISSION = "EN_MISSION"
    REPOS = "REPOS"
    SUSPENDU = "SUSPENDU"
    BLACKLISTE = "BLACKLISTE"
    INACTIF = "INACTIF"


class CategoriePermis(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    D = "D"
    E = "E"
    F = "F"
    CE = "CE"
    DE = "DE"


class TypeVehicule(str, Enum):
    CAMION_BENNE = "CAMION_BENNE"
    CAMION_PLATEAU = "CAMION_PLATEAU"
    TRACTEUR_ROUTIER = "TRACTEUR_ROUTIER"
    REMORQUE = "REMORQUE"
    SEMI_REMORQUE = "SEMI_REMORQUE"
    FOURGON = "FOURGON"
    PICKUP = "PICKUP"
    VEHICULE_LEGER = "VEHICULE_LEGER"
    CHARIOT_ELEVATEUR = "CHARIOT_ELEVATEUR"
    MOTO = "MOTO"


class StatutVehicule(str, Enum):
    DISPONIBLE = "DISPONIBLE"
    EN_MISSION = "EN_MISSION"
    EN_MAINTENANCE = "EN_MAINTENANCE"
    IMMOBILISE = "IMMOBILISE"       # papiers expires, panne lourde
    HORS_SERVICE = "HORS_SERVICE"
    CEDE = "CEDE"


class ProprieteActif(str, Enum):
    PROPRE = "PROPRE"               # propriete DML SARLU
    LOUE = "LOUE"
    SOUS_TRAITANT = "SOUS_TRAITANT"
    LEASING = "LEASING"


class TypeCarburant(str, Enum):
    GASOIL = "GASOIL"
    ESSENCE = "ESSENCE"
    ELECTRIQUE = "ELECTRIQUE"
    HYBRIDE = "HYBRIDE"


class TypeDocumentVehicule(str, Enum):
    CARTE_GRISE = "CARTE_GRISE"
    ASSURANCE = "ASSURANCE"
    VISITE_TECHNIQUE = "VISITE_TECHNIQUE"
    LICENCE_TRANSPORT = "LICENCE_TRANSPORT"
    PATENTE = "PATENTE"
    VIGNETTE = "VIGNETTE"
    CARTE_BLEUE = "CARTE_BLEUE"
    AUTORISATION_TRANSIT = "AUTORISATION_TRANSIT"
    CERTIFICAT_JAUGEAGE = "CERTIFICAT_JAUGEAGE"


class TypeMaintenance(str, Enum):
    PREVENTIVE = "PREVENTIVE"
    CURATIVE = "CURATIVE"
    VIDANGE = "VIDANGE"
    PNEUMATIQUE = "PNEUMATIQUE"
    CARROSSERIE = "CARROSSERIE"
    REVISION_GENERALE = "REVISION_GENERALE"


class StatutMaintenance(str, Enum):
    PLANIFIEE = "PLANIFIEE"
    EN_COURS = "EN_COURS"
    TERMINEE = "TERMINEE"
    ANNULEE = "ANNULEE"


class TypeVoyage(str, Enum):
    COLLECTE_ACHAT = "COLLECTE_ACHAT"           # brousse -> magasin
    LIVRAISON_CLIENT = "LIVRAISON_CLIENT"
    TRANSFERT_INTER_MAGASIN = "TRANSFERT_INTER_MAGASIN"
    EXPORT_PORT = "EXPORT_PORT"                 # magasin -> port de Douala
    IMPORT_PORT = "IMPORT_PORT"
    RETOUR_VIDE = "RETOUR_VIDE"
    SERVICE_TIERS = "SERVICE_TIERS"             # transport facture a un tiers
    ADMINISTRATIF = "ADMINISTRATIF"


class StatutVoyage(str, Enum):
    PLANIFIE = "PLANIFIE"
    AVANCE_VERSEE = "AVANCE_VERSEE"
    EN_CHARGEMENT = "EN_CHARGEMENT"
    EN_ROUTE = "EN_ROUTE"
    ARRIVE = "ARRIVE"
    EN_DECHARGEMENT = "EN_DECHARGEMENT"
    LIVRE = "LIVRE"
    CLOTURE = "CLOTURE"          # justificatifs remis + solde chauffeur regle
    ANNULE = "ANNULE"
    INCIDENT = "INCIDENT"


class TypeDepenseVoyage(str, Enum):
    CARBURANT = "CARBURANT"
    PEAGE = "PEAGE"
    PESAGE = "PESAGE"
    PERDIEM = "PERDIEM"
    MANUTENTION = "MANUTENTION"
    ESCORTE = "ESCORTE"
    DOUANE = "DOUANE"
    AMENDE = "AMENDE"
    REPARATION_ROUTE = "REPARATION_ROUTE"
    GARDIENNAGE = "GARDIENNAGE"
    HEBERGEMENT = "HEBERGEMENT"
    TAXE_COMMUNALE = "TAXE_COMMUNALE"
    AUTRE = "AUTRE"


class TypeIncident(str, Enum):
    PANNE = "PANNE"
    ACCIDENT = "ACCIDENT"
    VOL = "VOL"
    RETARD = "RETARD"
    CONTROLE_ROUTIER = "CONTROLE_ROUTIER"
    INTEMPERIE = "INTEMPERIE"
    PERTE_MARCHANDISE = "PERTE_MARCHANDISE"
    LITIGE_CLIENT = "LITIGE_CLIENT"


# ===========================================================================
# MODULE 2 - STOCKS & MULTI-MAGASINS
# ===========================================================================
class TypeMagasin(str, Enum):
    PRINCIPAL = "PRINCIPAL"
    SECONDAIRE = "SECONDAIRE"
    QUAI_TRANSIT = "QUAI_TRANSIT"
    ENTREPOT_PORTUAIRE = "ENTREPOT_PORTUAIRE"
    MAGASIN_BROUSSE = "MAGASIN_BROUSSE"     # points de collecte
    VIRTUEL = "VIRTUEL"                     # stock en transit, stock client, rebut
    SOUS_TRAITE = "SOUS_TRAITE"             # magasin loue / tiers detenteur


class TypeEmplacement(str, Enum):
    ZONE = "ZONE"
    ALLEE = "ALLEE"
    RANGEE = "RANGEE"
    PALETTE = "PALETTE"
    CASIER = "CASIER"
    TAS = "TAS"          # tas de vrac (mais, sorgho)
    SILO = "SILO"
    CUVE = "CUVE"


class TypeMouvementStock(str, Enum):
    ENTREE_ACHAT = "ENTREE_ACHAT"
    ENTREE_RETOUR_CLIENT = "ENTREE_RETOUR_CLIENT"
    ENTREE_TRANSFERT = "ENTREE_TRANSFERT"
    ENTREE_AJUSTEMENT = "ENTREE_AJUSTEMENT"
    ENTREE_PRODUCTION = "ENTREE_PRODUCTION"    # sortie de conditionnement/triage
    SORTIE_VENTE = "SORTIE_VENTE"
    SORTIE_TRANSFERT = "SORTIE_TRANSFERT"
    SORTIE_AJUSTEMENT = "SORTIE_AJUSTEMENT"
    SORTIE_PERTE = "SORTIE_PERTE"
    SORTIE_CONSOMMATION = "SORTIE_CONSOMMATION"
    SORTIE_ECHANTILLON = "SORTIE_ECHANTILLON"
    REINTEGRATION = "REINTEGRATION"


class SensMouvement(str, Enum):
    ENTREE = "ENTREE"
    SORTIE = "SORTIE"
    INTERNE = "INTERNE"     # deplacement d'emplacement a emplacement


class CausePerte(str, Enum):
    COULAGE = "COULAGE"                 # ecoulement de vrac
    FREINTE_TRANSPORT = "FREINTE_TRANSPORT"
    HUMIDITE_MOISISSURE = "HUMIDITE_MOISISSURE"
    RONGEURS = "RONGEURS"
    INSECTES = "INSECTES"
    VOL = "VOL"
    CASSE_EMBALLAGE = "CASSE_EMBALLAGE"
    INCENDIE = "INCENDIE"
    INONDATION = "INONDATION"
    ERREUR_PESEE = "ERREUR_PESEE"
    AUTRE = "AUTRE"


class StatutLot(str, Enum):
    EN_QUARANTAINE = "EN_QUARANTAINE"   # en attente de controle qualite
    DISPONIBLE = "DISPONIBLE"
    RESERVE = "RESERVE"
    BLOQUE = "BLOQUE"
    EPUISE = "EPUISE"
    REJETE = "REJETE"


class TypeInventaire(str, Enum):
    TOURNANT = "TOURNANT"
    ANNUEL = "ANNUEL"
    PONCTUEL = "PONCTUEL"


class MethodeValorisation(str, Enum):
    CUMP = "CUMP"       # cout unitaire moyen pondere (norme OHADA usuelle)
    FIFO = "FIFO"
    LIFO = "LIFO"


# --- IoT ------------------------------------------------------------------
class TypeCapteur(str, Enum):
    TEMPERATURE_HUMIDITE = "TEMPERATURE_HUMIDITE"   # DHT22 / SHT31
    TEMPERATURE = "TEMPERATURE"
    HUMIDITE_GRAIN = "HUMIDITE_GRAIN"
    CO2 = "CO2"
    NIVEAU_SILO = "NIVEAU_SILO"
    POIDS = "POIDS"
    OUVERTURE_PORTE = "OUVERTURE_PORTE"
    ENERGIE = "ENERGIE"


class StatutCapteur(str, Enum):
    ACTIF = "ACTIF"
    HORS_LIGNE = "HORS_LIGNE"
    MAINTENANCE = "MAINTENANCE"
    BATTERIE_FAIBLE = "BATTERIE_FAIBLE"
    DEFAILLANT = "DEFAILLANT"
    RETIRE = "RETIRE"


class TypeAlerteIoT(str, Enum):
    TEMPERATURE_HAUTE = "TEMPERATURE_HAUTE"
    TEMPERATURE_BASSE = "TEMPERATURE_BASSE"
    HUMIDITE_HAUTE = "HUMIDITE_HAUTE"
    HUMIDITE_BASSE = "HUMIDITE_BASSE"
    CAPTEUR_MUET = "CAPTEUR_MUET"
    BATTERIE_FAIBLE = "BATTERIE_FAIBLE"
    ANOMALIE_IA = "ANOMALIE_IA"
    INTRUSION = "INTRUSION"


# ===========================================================================
# MODULE 3 - ACHATS & CONTROLE QUALITE
# ===========================================================================
class TypeFournisseur(str, Enum):
    COOPERATIVE = "COOPERATIVE"
    GROSSISTE = "GROSSISTE"
    PRODUCTEUR = "PRODUCTEUR"
    COLLECTEUR = "COLLECTEUR"
    IMPORTATEUR = "IMPORTATEUR"
    TRANSPORTEUR = "TRANSPORTEUR"
    PRESTATAIRE_SERVICE = "PRESTATAIRE_SERVICE"
    ADMINISTRATION = "ADMINISTRATION"


class StatutCommandeAchat(str, Enum):
    BROUILLON = "BROUILLON"
    VALIDEE = "VALIDEE"
    ENVOYEE = "ENVOYEE"
    PARTIELLEMENT_RECUE = "PARTIELLEMENT_RECUE"
    RECUE = "RECUE"
    FACTUREE = "FACTUREE"
    SOLDEE = "SOLDEE"
    ANNULEE = "ANNULEE"


class StatutReception(str, Enum):
    ARRIVE_BARRIERE = "ARRIVE_BARRIERE"
    PESEE_BRUT = "PESEE_BRUT"
    ECHANTILLONNAGE = "ECHANTILLONNAGE"
    EN_ANALYSE = "EN_ANALYSE"
    ACCEPTE = "ACCEPTE"
    REJETE = "REJETE"
    EN_DECHARGEMENT = "EN_DECHARGEMENT"
    PESEE_TARE = "PESEE_TARE"
    STOCKE = "STOCKE"
    CLOTURE = "CLOTURE"
    ANNULE = "ANNULE"


class DecisionQualite(str, Enum):
    EN_ATTENTE = "EN_ATTENTE"
    ACCEPTE = "ACCEPTE"
    ACCEPTE_AVEC_DECOTE = "ACCEPTE_AVEC_DECOTE"
    ACCEPTE_APRES_SECHAGE = "ACCEPTE_APRES_SECHAGE"
    REJETE = "REJETE"


class MotifRejetQualite(str, Enum):
    HUMIDITE_EXCESSIVE = "HUMIDITE_EXCESSIVE"
    IMPURETES_EXCESSIVES = "IMPURETES_EXCESSIVES"
    GRAINS_MOISIS = "GRAINS_MOISIS"
    INFESTATION_INSECTES = "INFESTATION_INSECTES"
    ODEUR_ANORMALE = "ODEUR_ANORMALE"
    CORPS_ETRANGERS = "CORPS_ETRANGERS"
    MELANGE_VARIETES = "MELANGE_VARIETES"
    AUTRE = "AUTRE"


# ===========================================================================
# MODULE 4 - VENTES & CRM
# ===========================================================================
class TypeClient(str, Enum):
    INDUSTRIEL = "INDUSTRIEL"       # brasseries, provenderies, huileries
    GROSSISTE = "GROSSISTE"
    EXPORTATEUR = "EXPORTATEUR"
    DETAILLANT = "DETAILLANT"
    ONG_INSTITUTION = "ONG_INSTITUTION"
    ADMINISTRATION = "ADMINISTRATION"


class StatutClient(str, Enum):
    PROSPECT = "PROSPECT"
    ACTIF = "ACTIF"
    INACTIF = "INACTIF"
    BLOQUE = "BLOQUE"           # depassement encours / impaye
    CONTENTIEUX = "CONTENTIEUX"


class StatutProforma(str, Enum):
    BROUILLON = "BROUILLON"
    ENVOYEE = "ENVOYEE"
    ACCEPTEE = "ACCEPTEE"
    REFUSEE = "REFUSEE"
    EXPIREE = "EXPIREE"
    TRANSFORMEE = "TRANSFORMEE"
    ANNULEE = "ANNULEE"


class StatutCommandeVente(str, Enum):
    BROUILLON = "BROUILLON"
    CONFIRMEE = "CONFIRMEE"
    EN_PREPARATION = "EN_PREPARATION"
    PARTIELLEMENT_LIVREE = "PARTIELLEMENT_LIVREE"
    LIVREE = "LIVREE"
    FACTUREE = "FACTUREE"
    ANNULEE = "ANNULEE"


class StatutLivraison(str, Enum):
    PREPARE = "PREPARE"
    CHARGE = "CHARGE"
    EN_ROUTE = "EN_ROUTE"
    LIVRE = "LIVRE"
    LIVRE_AVEC_ECART = "LIVRE_AVEC_ECART"
    RETOURNE = "RETOURNE"
    ANNULE = "ANNULE"


class StatutFacture(str, Enum):
    BROUILLON = "BROUILLON"
    EMISE = "EMISE"
    PARTIELLEMENT_REGLEE = "PARTIELLEMENT_REGLEE"
    REGLEE = "REGLEE"
    EN_RETARD = "EN_RETARD"
    CONTENTIEUX = "CONTENTIEUX"
    ANNULEE = "ANNULEE"
    AVOIR = "AVOIR"


class TypeInteractionCRM(str, Enum):
    APPEL = "APPEL"
    VISITE = "VISITE"
    EMAIL = "EMAIL"
    WHATSAPP = "WHATSAPP"
    REUNION = "REUNION"
    RECLAMATION = "RECLAMATION"


class CanalRelance(str, Enum):
    TELEPHONE = "TELEPHONE"
    EMAIL = "EMAIL"
    COURRIER = "COURRIER"
    VISITE = "VISITE"
    MISE_EN_DEMEURE = "MISE_EN_DEMEURE"
    HUISSIER = "HUISSIER"


# ===========================================================================
# MODULE 5 - FINANCE & COMPTABILITE (OHADA / SYSCOHADA revise)
# ===========================================================================
class ClasseCompte(str, Enum):
    CLASSE_1 = "1"   # Ressources durables
    CLASSE_2 = "2"   # Actif immobilise
    CLASSE_3 = "3"   # Stocks
    CLASSE_4 = "4"   # Tiers
    CLASSE_5 = "5"   # Tresorerie
    CLASSE_6 = "6"   # Charges des activites ordinaires
    CLASSE_7 = "7"   # Produits des activites ordinaires
    CLASSE_8 = "8"   # Autres charges et produits (HAO)
    CLASSE_9 = "9"   # Comptabilite analytique / engagements


class TypeCompte(str, Enum):
    GENERAL = "GENERAL"
    AUXILIAIRE_CLIENT = "AUXILIAIRE_CLIENT"
    AUXILIAIRE_FOURNISSEUR = "AUXILIAIRE_FOURNISSEUR"
    AUXILIAIRE_SALARIE = "AUXILIAIRE_SALARIE"
    ANALYTIQUE = "ANALYTIQUE"


class SensCompte(str, Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"


class TypeJournal(str, Enum):
    ACHAT = "ACHAT"
    VENTE = "VENTE"
    BANQUE = "BANQUE"
    CAISSE = "CAISSE"
    MOBILE_MONEY = "MOBILE_MONEY"
    PAIE = "PAIE"
    STOCK = "STOCK"
    OPERATIONS_DIVERSES = "OPERATIONS_DIVERSES"
    A_NOUVEAUX = "A_NOUVEAUX"
    CLOTURE = "CLOTURE"


class StatutEcriture(str, Enum):
    BROUILLON = "BROUILLON"
    VALIDEE = "VALIDEE"     # non modifiable (irreversibilite OHADA)
    CLOTUREE = "CLOTUREE"
    EXTOURNEE = "EXTOURNEE"


class StatutExercice(str, Enum):
    OUVERT = "OUVERT"
    CLOTURE_PROVISOIRE = "CLOTURE_PROVISOIRE"
    CLOTURE_DEFINITIVE = "CLOTURE_DEFINITIVE"


class TypeCompteTresorerie(str, Enum):
    CAISSE = "CAISSE"
    COFFRE = "COFFRE"
    BANQUE = "BANQUE"
    MOBILE_MONEY = "MOBILE_MONEY"
    CAISSE_CHAUFFEUR = "CAISSE_CHAUFFEUR"   # avances en circulation


class Tiroir(str, Enum):
    """
    SEPARATION STRICTE "DOUBLE TIROIR".
    Toute ligne de tresorerie DOIT etre affectee a un tiroir : la confusion
    patrimoniale entre le PDG et la societe est le principal risque fiscal.
    """
    ENTREPRISE = "ENTREPRISE"       # tresorerie sociale de DML SARLU
    ASSOCIE = "ASSOCIE"             # compte courant d'associe du PDG


class SensTresorerie(str, Enum):
    ENCAISSEMENT = "ENCAISSEMENT"
    DECAISSEMENT = "DECAISSEMENT"


class ModeReglement(str, Enum):
    ESPECES = "ESPECES"
    VIREMENT = "VIREMENT"
    CHEQUE = "CHEQUE"
    MOBILE_MONEY = "MOBILE_MONEY"
    TRAITE = "TRAITE"
    COMPENSATION = "COMPENSATION"
    CREDIT_DOCUMENTAIRE = "CREDIT_DOCUMENTAIRE"


class OperateurMobileMoney(str, Enum):
    ORANGE_MONEY = "ORANGE_MONEY"
    MTN_MOMO = "MTN_MOMO"
    EU_MOBILE = "EU_MOBILE"
    AUTRE = "AUTRE"


class TypeMouvementCompteCourant(str, Enum):
    APPORT = "APPORT"                       # le PDG injecte des fonds
    RETRAIT = "RETRAIT"                     # le PDG preleve
    REMBOURSEMENT = "REMBOURSEMENT"
    AFFECTATION_RESULTAT = "AFFECTATION_RESULTAT"
    DEPENSE_PERSONNELLE = "DEPENSE_PERSONNELLE"   # payee par la caisse societe
    INTERET = "INTERET"


class TypeImpot(str, Enum):
    TVA = "TVA"
    IRPP = "IRPP"
    IS = "IS"
    ACOMPTE_IS = "ACOMPTE_IS"
    AIR = "AIR"                     # acompte sur impot sur le revenu
    PRECOMPTE = "PRECOMPTE"
    CNPS = "CNPS"
    CFC = "CFC"                     # credit foncier
    FNE = "FNE"                     # fonds national de l'emploi
    PATENTE = "PATENTE"
    TAXE_COMMUNALE = "TAXE_COMMUNALE"
    DROITS_DOUANE = "DROITS_DOUANE"
    DSF = "DSF"                     # declaration statistique et fiscale


class StatutDeclarationFiscale(str, Enum):
    A_PREPARER = "A_PREPARER"
    PREPAREE = "PREPAREE"
    DEPOSEE = "DEPOSEE"
    PAYEE = "PAYEE"
    EN_RETARD = "EN_RETARD"
    CONTESTEE = "CONTESTEE"


class TableauDSF(str, Enum):
    BILAN_ACTIF = "BILAN_ACTIF"
    BILAN_PASSIF = "BILAN_PASSIF"
    COMPTE_RESULTAT = "COMPTE_RESULTAT"
    TABLEAU_FLUX_TRESORERIE = "TABLEAU_FLUX_TRESORERIE"
    NOTES_ANNEXES = "NOTES_ANNEXES"


class TypeOrigineEcriture(str, Enum):
    """Document metier a l'origine d'une ecriture (lien polymorphe)."""
    FACTURE_VENTE = "FACTURE_VENTE"
    FACTURE_ACHAT = "FACTURE_ACHAT"
    REGLEMENT_CLIENT = "REGLEMENT_CLIENT"
    REGLEMENT_FOURNISSEUR = "REGLEMENT_FOURNISSEUR"
    MOUVEMENT_TRESORERIE = "MOUVEMENT_TRESORERIE"
    MOUVEMENT_STOCK = "MOUVEMENT_STOCK"
    DEPENSE_VOYAGE = "DEPENSE_VOYAGE"
    BULLETIN_PAIE = "BULLETIN_PAIE"
    AVANCE_SALAIRE = "AVANCE_SALAIRE"
    COMPTE_COURANT_ASSOCIE = "COMPTE_COURANT_ASSOCIE"
    MAINTENANCE = "MAINTENANCE"
    DECLARATION_FISCALE = "DECLARATION_FISCALE"
    MISSION_TRANSPORT = "MISSION_TRANSPORT"
    LITIGE_TRANSPORT = "LITIGE_TRANSPORT"
    SAISIE_MANUELLE = "SAISIE_MANUELLE"


# ===========================================================================
# MODULE 7 : TRANSPORT POUR COMPTE DE TIERS (bourse de fret + groupage)
# ===========================================================================
class StatutOffreFret(str, Enum):
    BROUILLON = "BROUILLON"
    PUBLIEE = "PUBLIEE"
    EN_NEGOCIATION = "EN_NEGOCIATION"
    ATTRIBUEE = "ATTRIBUEE"
    EXPIREE = "EXPIREE"
    ANNULEE = "ANNULEE"


class StatutCandidature(str, Enum):
    SOUMISE = "SOUMISE"
    EN_NEGOCIATION = "EN_NEGOCIATION"
    RETENUE = "RETENUE"
    REFUSEE = "REFUSEE"
    RETIREE = "RETIREE"          # le transporteur se retire de lui-meme
    DESISTEMENT = "DESISTEMENT"  # retrait APRES attribution : penalisant


class SensNegociation(str, Enum):
    TRANSPORTEUR = "TRANSPORTEUR"
    DML = "DML"


class StatutMissionTransport(str, Enum):
    PLANIFIEE = "PLANIFIEE"
    EN_CHARGEMENT = "EN_CHARGEMENT"
    EN_ROUTE = "EN_ROUTE"
    LIVREE = "LIVREE"
    FACTUREE = "FACTUREE"
    CLOTUREE = "CLOTUREE"
    ANNULEE = "ANNULEE"


class BaseFacturationTransport(str, Enum):
    """Sur quel tonnage la prestation est facturee au client."""
    TONNAGE_DEPART = "TONNAGE_DEPART"      # pese au chargement (recommande)
    TONNAGE_ARRIVEE = "TONNAGE_ARRIVEE"    # pese a la livraison
    TONNAGE_MINIMUM = "TONNAGE_MINIMUM"    # plancher contractuel applique
    FORFAIT_CAMION = "FORFAIT_CAMION"      # camion complet, hors tonnage


class ClePartitionCout(str, Enum):
    """Groupage : cle de ventilation du cout du voyage entre les missions."""
    TONNAGE = "TONNAGE"
    VALEUR = "VALEUR"
    VOLUME = "VOLUME"
    EGALE = "EGALE"
    MANUELLE = "MANUELLE"


class EtatMarchandiseTiers(str, Enum):
    BON = "BON"
    EMBALLAGE_ENDOMMAGE = "EMBALLAGE_ENDOMMAGE"
    MOUILLE = "MOUILLE"
    SOUILLE = "SOUILLE"
    PARTIELLEMENT_MANQUANT = "PARTIELLEMENT_MANQUANT"
    MANQUANT = "MANQUANT"


class TypeLitigeTransport(str, Enum):
    MANQUANT = "MANQUANT"
    AVARIE = "AVARIE"
    RETARD = "RETARD"
    VOL = "VOL"
    PERTE_TOTALE = "PERTE_TOTALE"
    ERREUR_DESTINATAIRE = "ERREUR_DESTINATAIRE"
    DOCUMENT_MANQUANT = "DOCUMENT_MANQUANT"


class ResponsabiliteLitige(str, Enum):
    TRANSPORTEUR = "TRANSPORTEUR"
    DML = "DML"
    CLIENT = "CLIENT"
    TIERS = "TIERS"
    FORCE_MAJEURE = "FORCE_MAJEURE"
    INDETERMINEE = "INDETERMINEE"


class StatutLitigeTransport(str, Enum):
    OUVERT = "OUVERT"
    EN_INSTRUCTION = "EN_INSTRUCTION"
    RECONNU = "RECONNU"
    CONTESTE = "CONTESTE"
    REGLE = "REGLE"
    CLASSE_SANS_SUITE = "CLASSE_SANS_SUITE"


class StatutSessionMobile(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIREE = "EXPIREE"
    REVOQUEE = "REVOQUEE"
    DECONNECTEE = "DECONNECTEE"


class ZoneApplication(str, Enum):
    """Deux zones dans l'app chauffeur : publique (bourse) et mission."""
    PUBLIQUE = "PUBLIQUE"
    MISSION = "MISSION"

"""
Repository du module Collecte.

REGLE : toute lecture passe par le filtre de portee. Les routes n'appellent
jamais db.query() directement.
"""

from datetime import date
from decimal import Decimal
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    AvanceCollecteur,
    Collecte,
    Collecteur,
    LigneCollecte,
    Utilisateur,
)
from app.models.enums import StatutAvanceCollecteur, StatutCollecte
from app.repositories.portee import appliquer_portee


# ---------------------------------------------------------------------------
# NUMEROTATION
# ---------------------------------------------------------------------------
def prochain_numero(db: Session, modele, prefixe: str) -> str:
    """Genere AV-2026-0001, COL-2026-0001... par annee civile."""
    annee = date.today().year
    debut = f"{prefixe}-{annee}-"
    dernier = (
        db.query(modele.numero)
        .filter(modele.numero.like(f"{debut}%"))
        .order_by(modele.numero.desc())
        .first()
    )
    suivant = int(dernier[0].split("-")[-1]) + 1 if dernier else 1
    return f"{debut}{suivant:04d}"


# ---------------------------------------------------------------------------
# AVANCES
# ---------------------------------------------------------------------------
def creer_avance(
    db: Session, donnees, utilisateur: Utilisateur
) -> AvanceCollecteur:
    """
    Remet une avance a un collecteur.

    Controle du plafond : au-dela, on refuse. C'est le garde-fou le plus
    simple contre l'accumulation d'avances non justifiees.
    """
    collecteur = db.get(Collecteur, donnees.collecteur_id)
    if collecteur is None:
        raise ValueError("Collecteur introuvable")

    encours = (
        db.query(func.coalesce(func.sum(AvanceCollecteur.montant_reste_du), 0))
        .filter(
            AvanceCollecteur.collecteur_id == collecteur.id,
            AvanceCollecteur.statut != StatutAvanceCollecteur.APUREE,
        )
        .scalar()
    )

    if collecteur.plafond_avance is not None:
        total = Decimal(encours) + donnees.montant_remis
        if total > collecteur.plafond_avance:
            raise ValueError(
                f"Plafond depasse : encours {encours} + {donnees.montant_remis} "
                f"> plafond {collecteur.plafond_avance}"
            )

    avance = AvanceCollecteur(
        numero=prochain_numero(db, AvanceCollecteur, "AV"),
        collecteur_id=donnees.collecteur_id,
        date_remise=donnees.date_remise,
        montant_remis=donnees.montant_remis,
        montant_reste_du=donnees.montant_remis,
        mode_remise=donnees.mode_remise,
        compte_tresorerie_id=donnees.compte_tresorerie_id,
        zone_prevue_id=donnees.zone_prevue_id,
        objet=donnees.objet,
        observations=donnees.observations,
        remis_par_id=utilisateur.id,
        created_by_id=utilisateur.id,
    )
    db.add(avance)
    db.commit()
    db.refresh(avance)
    return avance


def soldes_collecteurs(db: Session) -> List[dict]:
    """Combien chaque collecteur doit-il ? Trie par montant du, decroissant."""
    lignes = (
        db.query(
            Collecteur.id,
            Collecteur.nom,
            func.coalesce(func.sum(AvanceCollecteur.montant_remis), 0).label("remis"),
            func.coalesce(func.sum(AvanceCollecteur.montant_justifie), 0).label("justifie"),
            func.coalesce(func.sum(AvanceCollecteur.montant_reste_du), 0).label("reste"),
            func.count(AvanceCollecteur.id).label("nb"),
        )
        .join(AvanceCollecteur, AvanceCollecteur.collecteur_id == Collecteur.id)
        .filter(AvanceCollecteur.statut != StatutAvanceCollecteur.APUREE)
        .group_by(Collecteur.id, Collecteur.nom)
        .order_by(func.sum(AvanceCollecteur.montant_reste_du).desc())
        .all()
    )
    return [
        {
            "collecteur_id": l.id,
            "nom": l.nom,
            "total_avance": Decimal(l.remis),
            "total_justifie": Decimal(l.justifie),
            "reste_du": Decimal(l.reste),
            "nb_avances_ouvertes": l.nb,
        }
        for l in lignes
    ]


# ---------------------------------------------------------------------------
# COLLECTES
# ---------------------------------------------------------------------------
def creer_collecte(db: Session, donnees, utilisateur: Utilisateur) -> Collecte:
    """
    Ouvre une collecte. Le mode de detention se fige ICI et ne change plus.
    """
    collecte = Collecte(
        numero=prochain_numero(db, Collecte, "COL"),
        collecteur_id=donnees.collecteur_id,
        zone_id=donnees.zone_id,
        avance_id=donnees.avance_id,
        contrat_id=donnees.contrat_id,
        date_debut=donnees.date_debut,
        mode_detention=donnees.mode_detention,
        marge_fixe_tonne_appliquee=donnees.marge_fixe_tonne_appliquee,
        taux_commission_applique=donnees.taux_commission_applique,
        magasin_destination_id=donnees.magasin_destination_id,
        campagne_agricole=donnees.campagne_agricole,
        frais_annexes=donnees.frais_annexes,
        observations=donnees.observations,
        created_by_id=utilisateur.id,
    )
    db.add(collecte)
    db.commit()
    db.refresh(collecte)
    return collecte


def ajouter_ligne(
    db: Session, collecte_id: UUID, donnees, utilisateur: Utilisateur
) -> LigneCollecte:
    """
    Enregistre un achat au marche et met a jour les totaux de la collecte.

    Le poids theorique est ce que DML CROIT avoir achete (nb sacs x poids
    nominal). Le poids reel viendra a la pesee. L'ecart est le chiffre utile.
    """
    collecte = db.get(Collecte, collecte_id)
    if collecte is None:
        raise ValueError("Collecte introuvable")
    if collecte.statut != StatutCollecte.EN_COURS:
        raise ValueError("Collecte cloturee : saisie impossible")

    dernier = (
        db.query(func.coalesce(func.max(LigneCollecte.numero_ligne), 0))
        .filter(LigneCollecte.collecte_id == collecte_id)
        .scalar()
    )

    ligne = LigneCollecte(
        collecte_id=collecte_id,
        numero_ligne=dernier + 1,
        produit_id=donnees.produit_id,
        date_achat=donnees.date_achat,
        base_achat=donnees.base_achat,
        nombre_sacs=donnees.nombre_sacs,
        poids_nominal_sac_kg=donnees.poids_nominal_sac_kg,
        quantite_kg=donnees.quantite_kg,
        prix_unitaire=donnees.prix_unitaire,
        montant=Decimal("0"),
        nom_vendeur=donnees.nom_vendeur,
        telephone_vendeur=donnees.telephone_vendeur,
        appreciation_qualite=donnees.appreciation_qualite,
        taux_humidite_marche=donnees.taux_humidite_marche,
        observations=donnees.observations,
    )
    ligne.calculer_montant()
    db.add(ligne)
    db.flush()

    _recalculer_totaux(db, collecte)
    db.commit()
    db.refresh(ligne)
    return ligne


def _recalculer_totaux(db: Session, collecte: Collecte) -> None:
    """Recalcule sacs, poids theorique et montant depuis les lignes."""
    lignes = (
        db.query(LigneCollecte)
        .filter(LigneCollecte.collecte_id == collecte.id)
        .all()
    )
    collecte.nombre_sacs_total = sum(l.nombre_sacs or 0 for l in lignes)
    collecte.poids_theorique_kg = sum(
        (l.poids_theorique() for l in lignes), Decimal("0.000")
    )
    collecte.montant_achat_total = sum(
        (l.montant for l in lignes), Decimal("0.00")
    )


def receptionner(
    db: Session, collecte_id: UUID, donnees, utilisateur: Utilisateur
) -> Collecte:
    """
    Arrivee au magasin : pesee reelle et calcul de l'ecart.

    C'est le moment de verite. L'ecart entre le poids paye et le poids recu
    dit, collecteur par collecteur, qui achete bien.
    """
    collecte = db.get(Collecte, collecte_id)
    if collecte is None:
        raise ValueError("Collecte introuvable")
    if collecte.statut == StatutCollecte.RECEPTIONNEE:
        raise ValueError("Collecte deja receptionnee")

    collecte.magasin_destination_id = donnees.magasin_destination_id
    collecte.date_reception_magasin = donnees.date_reception_magasin
    collecte.nombre_sacs_expedies = (
        donnees.nombre_sacs_expedies or collecte.nombre_sacs_total
    )
    collecte.nombre_sacs_recus = donnees.nombre_sacs_recus
    collecte.poids_reel_kg = donnees.poids_reel_kg
    collecte.taux_humidite_magasin = donnees.taux_humidite_magasin
    collecte.taux_impuretes_magasin = donnees.taux_impuretes_magasin
    collecte.voyage_id = donnees.voyage_id
    collecte.statut = StatutCollecte.RECEPTIONNEE
    collecte.updated_by_id = utilisateur.id

    collecte.calculer_ecart_poids()

    collecteur = db.get(Collecteur, collecte.collecteur_id)
    if collecteur is not None:
        collecteur.nb_collectes = (collecteur.nb_collectes or 0) + 1
        collecteur.tonnage_cumule = (
            collecteur.tonnage_cumule or Decimal("0")
        ) + (collecte.poids_reel_kg / Decimal("1000"))
        collecteur.ecart_poids_cumule_kg = (
            collecteur.ecart_poids_cumule_kg or Decimal("0")
        ) + (collecte.ecart_poids_kg or Decimal("0"))
        collecteur.date_derniere_collecte = donnees.date_reception_magasin.date()

    if collecte.avance_id:
        avance = db.get(AvanceCollecteur, collecte.avance_id)
        if avance is not None:
            avance.montant_justifie = (
                avance.montant_justifie or Decimal("0")
            ) + collecte.montant_achat_total
            avance.recalculer_apurement()

    db.commit()
    db.refresh(collecte)

    # Chiffrer le surcout si la marchandise est trop humide
    lignes = (
        db.query(LigneCollecte)
        .filter(LigneCollecte.collecte_id == collecte.id)
        .all()
    )
    collecte.alerte_qualite = None
    if lignes and collecte.taux_humidite_magasin is not None:
        collecte.alerte_qualite = evaluer_qualite(
            db,
            lignes[0].produit_id,
            collecte.poids_reel_kg,
            collecte.taux_humidite_magasin,
            collecte.montant_achat_total + collecte.frais_annexes,
        )

    return collecte


def ecarts_collecteurs(
    db: Session, depuis: Optional[date] = None
) -> List[dict]:
    """Qui me coute de l'argent ? Trie du pire au meilleur."""
    q = (
        db.query(
            Collecteur.id,
            Collecteur.nom,
            func.count(Collecte.id).label("nb"),
            func.coalesce(func.sum(Collecte.poids_theorique_kg), 0).label("theo"),
            func.coalesce(func.sum(Collecte.poids_reel_kg), 0).label("reel"),
            func.coalesce(func.sum(Collecte.ecart_poids_kg), 0).label("ecart"),
            func.coalesce(func.sum(Collecte.montant_achat_total), 0).label("montant"),
        )
        .join(Collecte, Collecte.collecteur_id == Collecteur.id)
        .filter(Collecte.statut == StatutCollecte.RECEPTIONNEE)
    )
    if depuis:
        q = q.filter(Collecte.date_debut >= depuis)

    lignes = (
        q.group_by(Collecteur.id, Collecteur.nom)
        .order_by(func.sum(Collecte.ecart_poids_kg).asc())
        .all()
    )

    resultats = []
    for l in lignes:
        theo = Decimal(l.theo)
        ecart = Decimal(l.ecart)
        pct = (ecart / theo * 100).quantize(Decimal("0.01")) if theo else None
        prix_kg = (Decimal(l.montant) / theo) if theo else Decimal("0")
        resultats.append(
            {
                "collecteur_id": l.id,
                "nom": l.nom,
                "nb_collectes": l.nb,
                "poids_theorique_kg": theo,
                "poids_reel_kg": Decimal(l.reel),
                "ecart_kg": ecart,
                "ecart_pourcentage": pct,
                "valeur_ecart": (ecart * prix_kg).quantize(Decimal("0.01")),
            }
        )
    return resultats


# ---------------------------------------------------------------------------
# ENTREE EN STOCK
# ---------------------------------------------------------------------------
def entrer_en_stock(
    db: Session, collecte: Collecte, utilisateur: Utilisateur
):
    """
    Cree le lot et le mouvement d'entree a partir d'une collecte receptionnee.

    Le lot porte le MODE DE DETENTION : c'est ce qui permet de dire, dans un
    magasin ou tout est melange, ce qui appartient a DML et ce qui est detenu
    pour un collecteur.

    Le cout unitaire est le cout de revient REEL : (achat + frais annexes)
    divise par le poids EFFECTIVEMENT recu -- pas le poids paye. Valoriser
    sur le poids theorique surevaluerait le stock des kilos qui n'existent pas.
    """
    from app.models import Lot, MouvementStock
    from app.models.enums import SensMouvement, TypeMouvementStock, UniteMesure

    if collecte.statut != StatutCollecte.RECEPTIONNEE:
        raise ValueError("La collecte doit etre receptionnee")
    if collecte.poids_reel_kg is None or collecte.poids_reel_kg <= 0:
        raise ValueError("Poids reel absent : impossible d'entrer en stock")

    existant = db.query(Lot).filter(Lot.collecte_id == collecte.id).first()
    if existant is not None:
        raise ValueError(f"Stock deja cree pour cette collecte (lot {existant.numero})")

    lignes = (
        db.query(LigneCollecte)
        .filter(LigneCollecte.collecte_id == collecte.id)
        .all()
    )
    if not lignes:
        raise ValueError("Aucune ligne d'achat : rien a entrer en stock")

    produits = {l.produit_id for l in lignes}
    if len(produits) > 1:
        raise ValueError(
            "Collecte multi-produits : creation de lot par produit non geree"
        )
    produit_id = lignes[0].produit_id

    cout_total = collecte.montant_achat_total + collecte.frais_annexes
    cout_unitaire = (cout_total / collecte.poids_reel_kg).quantize(Decimal("0.01"))

    lot = Lot(
        numero=prochain_numero(db, Lot, "LOT"),
        produit_id=produit_id,
        magasin_id=collecte.magasin_destination_id,
        collecte_id=collecte.id,
        collecteur_id=collecte.collecteur_id,
        mode_detention=collecte.mode_detention,
        quantite_initiale=collecte.poids_reel_kg,
        quantite_disponible=collecte.poids_reel_kg,
        quantite_reservee=Decimal("0"),
        nombre_sacs=collecte.nombre_sacs_recus,
        unite=UniteMesure.KG,
        cout_unitaire=cout_unitaire,
        valeur_stock=cout_total,
        taux_humidite_entree=collecte.taux_humidite_magasin,
        taux_impuretes_entree=collecte.taux_impuretes_magasin,
        campagne_agricole=collecte.campagne_agricole,
    )
    db.add(lot)
    db.flush()

    mouvement = MouvementStock(
        numero=prochain_numero(db, MouvementStock, "MVT"),
        type_mouvement=TypeMouvementStock.ENTREE_ACHAT,
        sens=SensMouvement.ENTREE,
        date_mouvement=collecte.date_reception_magasin,
        produit_id=produit_id,
        lot_id=lot.id,
        magasin_destination_id=collecte.magasin_destination_id,
        quantite=collecte.poids_reel_kg,
        unite=UniteMesure.KG,
        cout_unitaire=cout_unitaire,
        created_by_id=utilisateur.id,
    )
    db.add(mouvement)
    db.commit()
    db.refresh(lot)
    return lot


def etat_stock(db: Session, magasin_id: Optional[UUID] = None) -> List[dict]:
    """
    Combien de tonnes en magasin, et a qui appartiennent-elles ?

    Le decoupage par mode de detention est la reponse a : "je detiens
    40 tonnes, dont 25 a moi et 15 pour Amadou".
    """
    from app.models import Lot, Magasin, Produit

    q = (
        db.query(
            Magasin.nom.label("magasin"),
            Produit.designation.label("produit"),
            Lot.mode_detention,
            func.count(Lot.id).label("nb_lots"),
            func.coalesce(func.sum(Lot.quantite_disponible), 0).label("quantite"),
            func.coalesce(func.sum(Lot.valeur_stock), 0).label("valeur"),
        )
        .join(Magasin, Magasin.id == Lot.magasin_id)
        .join(Produit, Produit.id == Lot.produit_id)
        .filter(Lot.quantite_disponible > 0)
    )
    if magasin_id:
        q = q.filter(Lot.magasin_id == magasin_id)

    lignes = (
        q.group_by(Magasin.nom, Produit.designation, Lot.mode_detention)
        .order_by(Magasin.nom, Produit.designation)
        .all()
    )
    return [
        {
            "magasin": l.magasin,
            "produit": l.produit,
            "mode_detention": l.mode_detention,
            "nb_lots": l.nb_lots,
            "quantite_kg": Decimal(l.quantite),
            "tonnes": (Decimal(l.quantite) / 1000).quantize(Decimal("0.001")),
            "valeur": Decimal(l.valeur),
        }
        for l in lignes
    ]


def evaluer_qualite(
    db: Session,
    produit_id: UUID,
    poids_kg: Decimal,
    humidite: Optional[Decimal],
    montant_achat: Decimal,
    prix_sechage_tonne: Decimal = Decimal("8000"),
) -> dict:
    """
    Chiffre ce qu'un lot trop humide va couter.

    On ne decote pas le collecteur -- DML paie le meme prix quelle que
    soit l'humidite. Mais le surcout est reel : le grain va perdre du
    poids au sechage, et le sechage se paie.

    Cette fonction le rend visible AU MOMENT DE LA PESEE, pas trois
    semaines plus tard.
    """
    from app.models import Produit

    produit = db.get(Produit, produit_id)
    seuil = (produit.taux_humidite_max if produit else None) or Decimal("14.00")

    if humidite is None:
        return {"mesure": False, "seuil": seuil}

    hors_seuil = humidite > seuil
    if not hors_seuil:
        return {
            "mesure": True,
            "hors_seuil": False,
            "humidite": humidite,
            "seuil": seuil,
            "message": "Humidite dans les limites du produit.",
        }

    # Perte de poids par deshydratation jusqu'au seuil
    poids_apres = (
        poids_kg * (Decimal("100") - humidite) / (Decimal("100") - seuil)
    ).quantize(Decimal("0.001"))
    perte = (poids_kg - poids_apres).quantize(Decimal("0.001"))

    cout_sechage = (
        (poids_kg / Decimal("1000")) * prix_sechage_tonne
    ).quantize(Decimal("0.01"))

    cout_avant = (montant_achat / poids_kg).quantize(Decimal("0.01")) if poids_kg else Decimal("0")
    cout_apres = (
        (montant_achat + cout_sechage) / poids_apres
    ).quantize(Decimal("0.01")) if poids_apres else Decimal("0")
    surcout_kg = (cout_apres - cout_avant).quantize(Decimal("0.01"))
    surcout_total = (surcout_kg * poids_apres).quantize(Decimal("0.01"))

    return {
        "mesure": True,
        "hors_seuil": True,
        "humidite": humidite,
        "seuil": seuil,
        "ecart_points": (humidite - seuil).quantize(Decimal("0.01")),
        "poids_apres_sechage": poids_apres,
        "perte_sechage_kg": perte,
        "cout_sechage": cout_sechage,
        "cout_kg_avant": cout_avant,
        "cout_kg_apres": cout_apres,
        "surcout_kg": surcout_kg,
        "surcout_total": surcout_total,
        "message": (
            f"Ce lot est a {humidite} % au lieu de {seuil} %. "
            f"Il perdra environ {perte} kg au sechage, qui coutera "
            f"{cout_sechage} F. Votre kilo revient a {cout_apres} F "
            f"au lieu de {cout_avant} F."
        ),
    }

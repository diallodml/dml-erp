"""
Ce qui demande une action aujourd'hui.

Le systeme sait beaucoup de choses, mais il attend qu'on lui pose la
question. Personne ne consultera cinq ecrans chaque matin. Ce module fait
remonter tout seul ce qui cloche.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    AvanceCollecteur,
    Collecte,
    Collecteur,
    CompteTresorerie,
    Lot,
    MouvementStock,
    Prestataire,
    Produit,
    ReversementCollecteur,
    Traitement,
)
from app.models.enums import (
    SensMouvement,
    StatutAvanceCollecteur,
    StatutCollecte,
    StatutReversement,
    StatutTraitement,
    TypeMouvementStock,
)

URGENCE, CRITIQUE, ATTENTION = "URGENCE", "CRITIQUE", "ATTENTION"
_ORDRE = {URGENCE: 0, CRITIQUE: 1, ATTENTION: 2}


def _jour(valeur):
    """Accepte une date ou un datetime, renvoie toujours une date."""
    return valeur.date() if hasattr(valeur, "date") else valeur


def alertes(db: Session) -> list[dict]:
    """Liste triee du plus urgent au moins urgent."""
    liste = []
    aujourdhui = date.today()

    # --- Lots humides qui dorment
    lots = (
        db.query(Lot, Produit.designation, Produit.taux_humidite_max)
        .join(Produit, Produit.id == Lot.produit_id)
        .filter(Lot.quantite_disponible > 0)
        .all()
    )
    for lot, produit, seuil in lots:
        if lot.taux_humidite_entree is None:
            continue
        seuil = seuil or Decimal("14.00")
        if lot.taux_humidite_entree <= seuil:
            continue
        jours = (aujourdhui - _jour(lot.date_entree)).days if lot.date_entree else 0
        if jours > 21:
            niveau = URGENCE
        elif jours > 7:
            niveau = CRITIQUE
        else:
            continue
        liste.append({
            "niveau": niveau,
            "titre": f"{lot.numero} — {produit} à {lot.taux_humidite_entree} %",
            "detail": (
                f"{float(lot.quantite_disponible)/1000:.3f} t stockées depuis {jours} jours "
                f"au-dessus du seuil de {seuil} %. Ce grain chauffe."
            ),
            "action": "Envoyer au séchage",
            "lien": "/traitement",
        })

    # --- Traitements partis et jamais revenus
    partis = (
        db.query(Traitement, Prestataire.nom)
        .join(Prestataire, Prestataire.id == Traitement.prestataire_id)
        .filter(Traitement.statut.in_([StatutTraitement.EXPEDIE, StatutTraitement.EN_COURS]))
        .all()
    )
    for t, presta in partis:
        jours = (datetime.now(timezone.utc) - t.date_expedition).days
        delai = t.date_retour_prevue
        en_retard = (delai and aujourdhui > delai) or jours > 14
        if not en_retard:
            continue
        liste.append({
            "niveau": CRITIQUE if jours > 21 else ATTENTION,
            "titre": f"{t.numero} — {float(t.poids_entree_kg)/1000:.3f} t chez {presta}",
            "detail": f"Parti depuis {jours} jours, toujours pas revenu.",
            "action": "Relancer le prestataire",
            "lien": "/traitement",
        })

    # --- Collecteurs qui doivent trop
    soldes = (
        db.query(
            Collecteur.nom,
            func.coalesce(func.sum(AvanceCollecteur.montant_reste_du), 0).label("du"),
            func.min(AvanceCollecteur.date_remise).label("plus_ancienne"),
        )
        .join(AvanceCollecteur, AvanceCollecteur.collecteur_id == Collecteur.id)
        .filter(
            AvanceCollecteur.statut != StatutAvanceCollecteur.APUREE,
            AvanceCollecteur.is_deleted.is_(False),
        )
        .group_by(Collecteur.id, Collecteur.nom)
        .having(func.sum(AvanceCollecteur.montant_reste_du) > 0)
        .all()
    )
    for nom, du, plus_ancienne in soldes:
        jours = (aujourdhui - plus_ancienne).days if plus_ancienne else 0
        if jours < 15:
            continue
        liste.append({
            "niveau": URGENCE if jours > 45 else CRITIQUE,
            "titre": f"{nom} doit {int(du):,} F".replace(",", " "),
            "detail": f"Avance non justifiée depuis {jours} jours.",
            "action": "Voir sa fiche",
            "lien": "/collecteur",
        })

    # --- Clients qui n'ont pas paye
    impayes = (
        db.query(MouvementStock)
        .filter(
            MouvementStock.type_mouvement == TypeMouvementStock.SORTIE_VENTE,
            MouvementStock.sens == SensMouvement.SORTIE,
            MouvementStock.montant_vente.isnot(None),
        )
        .all()
    )
    for m in impayes:
        reste = (m.montant_vente or Decimal("0")) - (m.montant_encaisse or Decimal("0"))
        if reste <= 0:
            continue
        jours = (aujourdhui - _jour(m.date_mouvement)).days
        if jours < 15:
            continue
        champs = (m.observations or "").split("|")
        client = champs[0] if champs and champs[0] else "un client"
        liste.append({
            "niveau": URGENCE if jours > 45 else CRITIQUE,
            "titre": f"{client} doit {int(reste):,} F".replace(",", " "),
            "detail": f"Livraison {m.numero} non encaissée depuis {jours} jours.",
            "action": "Voir les ventes",
            "lien": "/livraisons",
        })

    # --- Collectes recues mais jamais entrees en stock
    en_attente = (
        db.query(Collecte)
        .filter(Collecte.statut == StatutCollecte.RECEPTIONNEE)
        .all()
    )
    avec_lot = {
        row[0] for row in db.query(Lot.collecte_id).filter(Lot.collecte_id.isnot(None)).all()
    }
    for c in en_attente:
        if c.id in avec_lot:
            continue
        jours = (aujourdhui - _jour(c.date_reception_magasin)).days if c.date_reception_magasin else 0
        if jours < 2:
            continue
        liste.append({
            "niveau": ATTENTION,
            "titre": f"{c.numero} pesée mais pas en stock",
            "detail": f"Réceptionnée il y a {jours} jours, la marchandise n'est pas entrée.",
            "action": "Entrer en stock",
            "lien": "/collectes",
        })

    # --- Caisses presque vides
    comptes = (
        db.query(CompteTresorerie)
        .filter(CompteTresorerie.is_actif.is_(True))
        .all()
    )
    for c in comptes:
        if c.solde_actuel is None or c.solde_actuel > Decimal("50000"):
            continue
        liste.append({
            "niveau": ATTENTION if c.solde_actuel > 0 else CRITIQUE,
            "titre": f"{c.libelle} : {int(c.solde_actuel):,} F".replace(",", " "),
            "detail": "Ce compte est presque vide.",
            "action": "Voir la caisse",
            "lien": "/tresorerie",
        })

    # --- Reversements dus depuis longtemps
    dus = (
        db.query(ReversementCollecteur, Collecteur.nom)
        .join(Collecteur, Collecteur.id == ReversementCollecteur.collecteur_id)
        .filter(ReversementCollecteur.statut != StatutReversement.PAYE)
        .all()
    )
    for r, nom in dus:
        solde = r.montant_net_du - (r.montant_paye or Decimal("0"))
        if solde <= 0:
            continue
        jours = (aujourdhui - r.date_calcul).days if r.date_calcul else 0
        if jours < 10:
            continue
        liste.append({
            "niveau": CRITIQUE if jours > 30 else ATTENTION,
            "titre": f"Vous devez {int(solde):,} F à {nom}".replace(",", " "),
            "detail": f"Reversement {r.numero} calculé il y a {jours} jours.",
            "action": "Payer",
            "lien": "/vente",
        })

    liste.sort(key=lambda a: _ORDRE[a["niveau"]])
    return liste

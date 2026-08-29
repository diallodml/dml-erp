"""
Export CSV pour le comptable.

Le comptable travaille sur Excel, pas sur l'ERP. Ces exports lui donnent
les chiffres sans qu'il ait a les ressaisir -- et vous laissent une copie
lisible ailleurs que dans PostgreSQL.

Format : point-virgule et BOM UTF-8, pour qu'Excel ouvre correctement les
accents et les colonnes sur un poste francophone.
"""

import csv
import io
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import exiger_permission, get_db, utilisateur_courant
from app.models import Utilisateur

router = APIRouter(prefix="/api/v1/export", tags=["Exports"])


def _csv(nom: str, entetes: list, lignes: list) -> StreamingResponse:
    tampon = io.StringIO()
    tampon.write("\ufeff")  # Excel reconnait l'UTF-8
    ecrivain = csv.writer(tampon, delimiter=";")
    ecrivain.writerow(entetes)
    for l in lignes:
        ecrivain.writerow([
            str(v).replace(".", ",") if isinstance(v, (Decimal, float))
            else ("" if v is None else v)
            for v in l
        ])
    tampon.seek(0)
    return StreamingResponse(
        iter([tampon.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nom}"'},
    )


@router.get("/tresorerie", dependencies=[Depends(exiger_permission("tresorerie.lire"))])
def export_tresorerie(
    depuis: Optional[date] = Query(default=None),
    jusqua: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Journal de tresorerie : toutes les entrees et sorties."""
    from app.models import CategorieDepense, CompteTresorerie, MouvementTresorerie

    q = (
        db.query(MouvementTresorerie, CompteTresorerie.libelle, CategorieDepense.libelle)
        .join(CompteTresorerie, CompteTresorerie.id == MouvementTresorerie.compte_tresorerie_id)
        .outerjoin(CategorieDepense,
                   CategorieDepense.id == MouvementTresorerie.categorie_depense_id)
    )
    if depuis:
        q = q.filter(MouvementTresorerie.date_mouvement >= depuis)
    if jusqua:
        q = q.filter(MouvementTresorerie.date_mouvement <= jusqua)

    lignes = [
        [
            m.numero, m.date_mouvement, compte,
            "Entrée" if m.sens.value == "ENCAISSEMENT" else "Sortie",
            m.montant, m.libelle, categorie or "", m.beneficiaire or "",
            m.mode_reglement.value if m.mode_reglement else "",
            "Associé" if m.tiroir.value == "ASSOCIE" else "Entreprise",
        ]
        for m, compte, categorie in q.order_by(MouvementTresorerie.date_mouvement).all()
    ]
    return _csv(
        f"tresorerie_{date.today()}.csv",
        ["Pièce", "Date", "Compte", "Sens", "Montant", "Motif",
         "Poste", "Bénéficiaire", "Mode", "Tiroir"],
        lignes,
    )


@router.get("/collectes", dependencies=[Depends(exiger_permission("collecte.collecte.lire"))])
def export_collectes(
    depuis: Optional[date] = Query(default=None),
    jusqua: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Achats au marche : ce qui a ete paye, ce qui est arrive."""
    from app.models import Collecte, Collecteur, ZoneCollecte

    q = (
        db.query(Collecte, Collecteur.nom, ZoneCollecte.libelle)
        .join(Collecteur, Collecteur.id == Collecte.collecteur_id)
        .outerjoin(ZoneCollecte, ZoneCollecte.id == Collecte.zone_id)
    )
    if depuis:
        q = q.filter(Collecte.date_debut >= depuis)
    if jusqua:
        q = q.filter(Collecte.date_debut <= jusqua)

    lignes = [
        [
            c.numero, c.date_debut, collecteur, zone or "",
            c.statut.value, c.mode_detention.value,
            c.nombre_sacs_total, c.poids_theorique_kg, c.poids_reel_kg,
            c.ecart_poids_kg, c.montant_achat_total, c.frais_annexes,
            c.taux_humidite_magasin,
        ]
        for c, collecteur, zone in q.order_by(Collecte.date_debut).all()
    ]
    return _csv(
        f"collectes_{date.today()}.csv",
        ["Pièce", "Date", "Collecteur", "Marché", "Statut", "Détention",
         "Sacs", "Poids payé (kg)", "Poids reçu (kg)", "Écart (kg)",
         "Montant achat", "Frais annexes", "Humidité %"],
        lignes,
    )


@router.get("/ventes", dependencies=[Depends(exiger_permission("vente.reversement.lire"))])
def export_ventes(
    depuis: Optional[date] = Query(default=None),
    jusqua: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Livraisons : ce qui est parti, a qui, pour combien."""
    from app.models import Lot, MouvementStock, Produit
    from app.models.enums import SensMouvement, TypeMouvementStock

    q = (
        db.query(MouvementStock, Produit.designation, Lot.numero)
        .outerjoin(Produit, Produit.id == MouvementStock.produit_id)
        .outerjoin(Lot, Lot.id == MouvementStock.lot_id)
        .filter(
            MouvementStock.type_mouvement == TypeMouvementStock.SORTIE_VENTE,
            MouvementStock.sens == SensMouvement.SORTIE,
        )
    )
    if depuis:
        q = q.filter(MouvementStock.date_mouvement >= depuis)
    if jusqua:
        q = q.filter(MouvementStock.date_mouvement <= jusqua)

    lignes = []
    for m, produit, lot in q.order_by(MouvementStock.date_mouvement).all():
        champs = (m.observations or "").split("|")
        while len(champs) < 5:
            champs.append("")
        vente = m.montant_vente or Decimal("0")
        cout = (m.quantite * (m.cout_unitaire or Decimal("0"))).quantize(Decimal("0.01"))
        lignes.append([
            m.numero, m.date_mouvement.date() if m.date_mouvement else "",
            champs[0], champs[1], produit or "", lot or "",
            m.quantite, m.cout_unitaire, cout, vente, vente - cout,
            m.montant_encaisse or Decimal("0"),
            vente - (m.montant_encaisse or Decimal("0")),
            champs[2], champs[3],
        ])

    return _csv(
        f"ventes_{date.today()}.csv",
        ["Pièce", "Date", "Client", "Lieu", "Produit", "Lot",
         "Quantité (kg)", "Coût/kg", "Coût total", "Vente", "Marge",
         "Encaissé", "Reste dû", "Transporteur", "Immatriculation"],
        lignes,
    )

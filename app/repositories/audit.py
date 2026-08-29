"""
Piste d'audit : qui a fait quoi, quand, avec quel motif.

Ce journal ne s'efface pas. C'est ce qui lui donne sa valeur : le jour ou
un chiffre ne colle pas, il dit ce qui s'est passe et qui l'a fait.

On n'enregistre que les actions SENSIBLES -- annulations, paiements,
changements de plafond, derogations. Tracer chaque lecture noierait
l'information utile.
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import JournalAudit, Utilisateur
from app.models.enums import TypeAction


def _serialiser(valeurs: Optional[dict]) -> Optional[dict]:
    """Les Decimal et les dates ne passent pas en JSON tels quels."""
    if not valeurs:
        return None
    propre = {}
    for cle, v in valeurs.items():
        if isinstance(v, Decimal):
            propre[cle] = float(v)
        elif hasattr(v, "isoformat"):
            propre[cle] = v.isoformat()
        elif isinstance(v, UUID):
            propre[cle] = str(v)
        elif hasattr(v, "value"):
            propre[cle] = v.value
        else:
            propre[cle] = v
    return propre


def tracer(
    db: Session,
    utilisateur: Optional[Utilisateur],
    action: TypeAction,
    table: str,
    enregistrement_id: Optional[UUID] = None,
    avant: Optional[dict] = None,
    apres: Optional[dict] = None,
    commentaire: Optional[str] = None,
) -> None:
    """
    Ajoute une ligne au journal. Ne fait pas de commit : la trace vit dans
    la meme transaction que l'operation qu'elle decrit. Si l'operation
    echoue, la trace disparait avec elle.
    """
    db.add(JournalAudit(
        utilisateur_id=utilisateur.id if utilisateur else None,
        horodatage=datetime.now(timezone.utc),
        action=action,
        table_cible=table,
        enregistrement_id=enregistrement_id,
        valeurs_avant=_serialiser(avant),
        valeurs_apres=_serialiser(apres),
        commentaire=commentaire,
    ))


def journal(
    db: Session,
    limite: int = 200,
    utilisateur_id: Optional[UUID] = None,
    table: Optional[str] = None,
    depuis=None,
) -> list[dict]:
    """Les dernieres actions sensibles, de la plus recente a la plus ancienne."""
    q = (
        db.query(JournalAudit, Utilisateur.nom_affichage, Utilisateur.login)
        .outerjoin(Utilisateur, Utilisateur.id == JournalAudit.utilisateur_id)
    )
    if utilisateur_id:
        q = q.filter(JournalAudit.utilisateur_id == utilisateur_id)
    if table:
        q = q.filter(JournalAudit.table_cible == table)
    if depuis:
        q = q.filter(JournalAudit.horodatage >= depuis)

    lignes = q.order_by(JournalAudit.horodatage.desc()).limit(limite).all()

    return [
        {
            "id": str(j.id),
            "horodatage": j.horodatage,
            "utilisateur": nom or login or "système",
            "action": j.action.value,
            "table": j.table_cible,
            "enregistrement_id": str(j.enregistrement_id) if j.enregistrement_id else None,
            "avant": j.valeurs_avant,
            "apres": j.valeurs_apres,
            "commentaire": j.commentaire,
        }
        for j, nom, login in lignes
    ]

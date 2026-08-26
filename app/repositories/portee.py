"""
Filtre de portee des donnees (RBAC).

REGLE ABSOLUE : ce filtre s'applique dans la couche repository,
JAMAIS dans le routeur. Une seule route qui l'oublie et un chauffeur
voit toute la flotte.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Query, Session

from app.models import AffectationMagasin, Chauffeur, Utilisateur
from app.models.enums import PorteeDonnees


def portee_utilisateur(utilisateur: Utilisateur, code_permission: str) -> PorteeDonnees:
    """
    Determine la portee la plus large accordee a l'utilisateur
    pour une permission donnee.
    """
    plus_large = None
    ordre = {
        PorteeDonnees.PROPRE: 1,
        PorteeDonnees.DEPARTEMENT: 2,
        PorteeDonnees.MAGASIN_AFFECTE: 3,
        PorteeDonnees.GLOBAL: 4,
    }

    for role in utilisateur.roles:
        for permission in role.permissions:
            if permission.code != code_permission:
                continue
            if plus_large is None or ordre[permission.portee] > ordre[plus_large]:
                plus_large = permission.portee

    return plus_large or PorteeDonnees.PROPRE


def magasins_autorises(db: Session, utilisateur: Utilisateur) -> list[UUID]:
    """Liste des magasins sur lesquels l'utilisateur est affecte."""
    lignes = (
        db.query(AffectationMagasin.magasin_id)
        .filter(
            AffectationMagasin.utilisateur_id == utilisateur.id,
            AffectationMagasin.is_actif.is_(True),
        )
        .all()
    )
    return [ligne[0] for ligne in lignes]


def chauffeur_de(db: Session, utilisateur: Utilisateur) -> Optional[UUID]:
    """Retourne l'id du chauffeur lie a ce compte, s'il existe."""
    if utilisateur.employe_id is None:
        return None
    chauffeur = (
        db.query(Chauffeur)
        .filter(Chauffeur.employe_id == utilisateur.employe_id)
        .first()
    )
    return chauffeur.id if chauffeur else None


def appliquer_portee(
    query: Query,
    db: Session,
    utilisateur: Utilisateur,
    modele,
    code_permission: str,
    champ_magasin: str = "magasin_id",
    champ_chauffeur: str = "chauffeur_id",
) -> Query:
    """
    Restreint une requete selon la portee de l'utilisateur.

    GLOBAL          -> aucune restriction
    MAGASIN_AFFECTE -> uniquement les magasins affectes
    PROPRE          -> uniquement ses propres donnees
    DEPARTEMENT     -> traite comme PROPRE tant que le decoupage
                       par departement n'est pas cable

    Si le modele ne porte pas le champ attendu, la requete renvoie
    un ensemble VIDE plutot que tout : en cas de doute, on ferme.
    """
    portee = portee_utilisateur(utilisateur, code_permission)

    if portee == PorteeDonnees.GLOBAL:
        return query

    if portee == PorteeDonnees.MAGASIN_AFFECTE:
        if not hasattr(modele, champ_magasin):
            return query.filter(False)
        autorises = magasins_autorises(db, utilisateur)
        if not autorises:
            return query.filter(False)
        return query.filter(getattr(modele, champ_magasin).in_(autorises))

    if not hasattr(modele, champ_chauffeur):
        return query.filter(False)
    mon_id = chauffeur_de(db, utilisateur)
    if mon_id is None:
        return query.filter(False)
    return query.filter(getattr(modele, champ_chauffeur) == mon_id)

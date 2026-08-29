"""Administration des comptes utilisateurs."""

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import exiger_permission, get_db, utilisateur_courant
from app.core.security import hasher_mot_de_passe
from app.models import Role, Utilisateur

router = APIRouter(prefix="/api/v1/utilisateurs", tags=["Utilisateurs"])


class UtilisateurCreer(BaseModel):
    login: str = Field(min_length=3, max_length=80)
    nom_affichage: str = Field(min_length=2, max_length=180)
    mot_de_passe: str = Field(min_length=8)
    email: Optional[str] = Field(default=None, max_length=180)
    telephone: Optional[str] = Field(default=None, max_length=30)
    roles: List[str] = Field(default_factory=list)


class MotDePasseReinit(BaseModel):
    mot_de_passe: str = Field(min_length=8)


class RolesModifier(BaseModel):
    roles: List[str]


@router.get("", dependencies=[Depends(exiger_permission("securite.utilisateur.lire"))])
def lister(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    return [
        {
            "id": str(u.id),
            "login": u.login,
            "nom_affichage": u.nom_affichage,
            "email": u.email,
            "telephone": u.telephone,
            "is_actif": u.is_actif,
            "is_superadmin": u.is_superadmin,
            "doit_changer_mdp": u.doit_changer_mdp,
            "roles": [r.code for r in u.roles],
            "bloque": u.bloque_jusqua is not None,
            "tentatives": u.tentatives_echouees or 0,
        }
        for u in db.query(Utilisateur).order_by(Utilisateur.login).all()
    ]


@router.get("/roles", include_in_schema=False)
def lister_roles(
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    return [
        {
            "code": r.code,
            "nom": r.nom,
            "portee": r.portee_par_defaut.value,
            "nb_permissions": len(r.permissions),
        }
        for r in db.query(Role).order_by(Role.niveau_hierarchique).all()
    ]


@router.post("", status_code=201,
             dependencies=[Depends(exiger_permission("securite.utilisateur.creer"))])
def creer(
    donnees: UtilisateurCreer,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """
    Cree un compte. Le mot de passe devra etre change a la premiere
    connexion : celui que vous saisissez ici transite par vous.
    """
    if db.query(Utilisateur).filter(Utilisateur.login == donnees.login).first():
        raise HTTPException(status_code=400, detail=f"Le login {donnees.login} existe deja")

    roles = db.query(Role).filter(Role.code.in_(donnees.roles)).all() if donnees.roles else []
    if donnees.roles and len(roles) != len(donnees.roles):
        raise HTTPException(status_code=400, detail="Un role demande n'existe pas")

    u = Utilisateur(
        login=donnees.login,
        nom_affichage=donnees.nom_affichage,
        email=donnees.email,
        telephone=donnees.telephone,
        mot_de_passe_hash=hasher_mot_de_passe(donnees.mot_de_passe),
        is_actif=True,
        is_superadmin=False,
        doit_changer_mdp=True,
    )
    u.roles = roles
    db.add(u)
    db.commit()
    db.refresh(u)
    return {
        "id": str(u.id),
        "login": u.login,
        "roles": [r.code for r in u.roles],
        "message": "Compte cree. L'utilisateur devra changer son mot de passe.",
    }


@router.patch("/{utilisateur_id}/roles",
              dependencies=[Depends(exiger_permission("securite.utilisateur.creer"))])
def modifier_roles(
    utilisateur_id: UUID,
    donnees: RolesModifier,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    u = db.get(Utilisateur, utilisateur_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if u.is_superadmin:
        raise HTTPException(
            status_code=400,
            detail="Les roles d'un superadministrateur ne se modifient pas ici",
        )
    u.roles = db.query(Role).filter(Role.code.in_(donnees.roles)).all()
    db.commit()
    return {"login": u.login, "roles": [r.code for r in u.roles]}


@router.patch("/{utilisateur_id}/mot-de-passe",
              dependencies=[Depends(exiger_permission("securite.utilisateur.creer"))])
def reinitialiser(
    utilisateur_id: UUID,
    donnees: MotDePasseReinit,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Reinitialise un mot de passe. L'utilisateur devra le changer."""
    u = db.get(Utilisateur, utilisateur_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    u.mot_de_passe_hash = hasher_mot_de_passe(donnees.mot_de_passe)
    u.doit_changer_mdp = True
    db.commit()
    return {"login": u.login, "message": "Mot de passe reinitialise"}


@router.patch("/{utilisateur_id}/activation",
              dependencies=[Depends(exiger_permission("securite.utilisateur.creer"))])
def basculer_activation(
    utilisateur_id: UUID,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """
    Active ou desactive un compte.

    On ne supprime jamais un utilisateur : ses saisies passees doivent
    rester attribuables. On coupe son acces, c'est tout.
    """
    u = db.get(Utilisateur, utilisateur_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if u.id == utilisateur.id:
        raise HTTPException(status_code=400, detail="Vous ne pouvez pas desactiver votre propre compte")
    u.is_actif = not u.is_actif
    db.commit()
    return {"login": u.login, "is_actif": u.is_actif}


@router.patch("/{utilisateur_id}/debloquer",
              dependencies=[Depends(exiger_permission("securite.utilisateur.creer"))])
def debloquer(
    utilisateur_id: UUID,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """Leve un blocage sans attendre les 15 minutes."""
    u = db.get(Utilisateur, utilisateur_id)
    if u is None:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    u.tentatives_echouees = 0
    u.bloque_jusqua = None
    db.commit()
    return {"login": u.login, "message": "Compte debloque"}

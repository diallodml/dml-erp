from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.core.deps import get_db, utilisateur_courant
from app.core.security import creer_jeton, verifier_mot_de_passe
from app.models import Utilisateur

router = APIRouter(prefix="/api/v1/auth", tags=["Authentification"])


@router.post("/login")
def login(
    donnees: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Echange un login et un mot de passe contre un jeton."""
    utilisateur = (
        db.query(Utilisateur)
        .filter(Utilisateur.login == donnees.username)
        .first()
    )

    if utilisateur is None or not verifier_mot_de_passe(
        donnees.password, utilisateur.mot_de_passe_hash
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiant ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not utilisateur.is_actif:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte desactive",
        )

    return {
        "access_token": creer_jeton(utilisateur.id),
        "token_type": "bearer",
        "doit_changer_mdp": utilisateur.doit_changer_mdp,
    }


@router.get("/moi")
def moi(utilisateur: Utilisateur = Depends(utilisateur_courant)):
    """Retourne le profil de l'utilisateur connecte."""
    return {
        "id": str(utilisateur.id),
        "login": utilisateur.login,
        "nom_affichage": utilisateur.nom_affichage,
        "is_superadmin": utilisateur.is_superadmin,
        "roles": [role.code for role in utilisateur.roles],
    }

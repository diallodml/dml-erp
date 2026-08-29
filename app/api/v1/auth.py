from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
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

    from datetime import datetime, timedelta, timezone

    MAX_TENTATIVES = 5
    DUREE_BLOCAGE = 15  # minutes

    maintenant = datetime.now(timezone.utc)

    if utilisateur is not None and utilisateur.bloque_jusqua:
        blocage = utilisateur.bloque_jusqua
        if blocage.tzinfo is None:
            blocage = blocage.replace(tzinfo=timezone.utc)
        if blocage > maintenant:
            restant = int((blocage - maintenant).total_seconds() / 60) + 1
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"Compte bloque apres {MAX_TENTATIVES} tentatives. "
                    f"Reessayez dans {restant} minute(s), ou demandez a la direction."
                ),
            )
        utilisateur.tentatives_echouees = 0
        utilisateur.bloque_jusqua = None

    if utilisateur is None or not verifier_mot_de_passe(
        donnees.password, utilisateur.mot_de_passe_hash
    ):
        if utilisateur is not None:
            utilisateur.tentatives_echouees = (utilisateur.tentatives_echouees or 0) + 1
            if utilisateur.tentatives_echouees >= MAX_TENTATIVES:
                utilisateur.bloque_jusqua = maintenant + timedelta(minutes=DUREE_BLOCAGE)
            db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Identifiant ou mot de passe incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        )

    utilisateur.tentatives_echouees = 0
    utilisateur.bloque_jusqua = None
    db.commit()

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
        "permissions": sorted({
            p.code for role in utilisateur.roles for p in role.permissions
        }),
    }


class ChangementMotDePasse(BaseModel):
    ancien: str
    nouveau: str = Field(min_length=8)


@router.post("/changer-mot-de-passe")
def changer_mot_de_passe(
    donnees: ChangementMotDePasse,
    db: Session = Depends(get_db),
    utilisateur: Utilisateur = Depends(utilisateur_courant),
):
    """
    L'utilisateur change son propre mot de passe.

    Obligatoire a la premiere connexion : le mot de passe provisoire est
    passe par la direction, il ne doit pas rester en service.
    """
    from app.core.security import hasher_mot_de_passe

    if not verifier_mot_de_passe(donnees.ancien, utilisateur.mot_de_passe_hash):
        raise HTTPException(status_code=400, detail="Ancien mot de passe incorrect")
    if donnees.ancien == donnees.nouveau:
        raise HTTPException(
            status_code=400, detail="Le nouveau mot de passe doit etre different"
        )

    utilisateur.mot_de_passe_hash = hasher_mot_de_passe(donnees.nouveau)
    utilisateur.doit_changer_mdp = False
    db.commit()
    return {"message": "Mot de passe change"}

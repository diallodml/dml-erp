from typing import Generator, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.security import lire_jeton
from app.models import Utilisateur

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utilisateur_courant(
    jeton: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Utilisateur:
    """Identifie l'utilisateur a partir du jeton. Rejette si invalide."""
    refus = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Identifiants invalides",
        headers={"WWW-Authenticate": "Bearer"},
    )

    identifiant = lire_jeton(jeton)
    if identifiant is None:
        raise refus

    utilisateur = db.query(Utilisateur).filter(Utilisateur.id == identifiant).first()
    if utilisateur is None:
        raise refus

    if not utilisateur.is_actif:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Compte desactive",
        )

    return utilisateur


def exiger_permission(code_permission: str):
    """
    Verifie que l'utilisateur detient une permission avant d'executer la route.

    Usage : dependencies=[Depends(exiger_permission("collecte.avance.creer"))]

    Le superadmin passe toujours. C'est volontaire : sans cela, une erreur de
    parametrage des roles vous enfermerait dehors de votre propre systeme.
    """

    def verificateur(
        utilisateur: Utilisateur = Depends(utilisateur_courant),
    ) -> Utilisateur:
        if getattr(utilisateur, "is_superadmin", False):
            return utilisateur

        detenues = {
            p.code for role in utilisateur.roles for p in role.permissions
        }
        if code_permission not in detenues:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Vous n'avez pas la permission d'effectuer cette action",
            )
        return utilisateur

    return verificateur

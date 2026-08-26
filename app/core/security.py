from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import jwt, JWTError

from app.core.config import settings

ALGORITHM = "HS256"


def hasher_mot_de_passe(mot_de_passe: str) -> str:
    sel = bcrypt.gensalt()
    empreinte = bcrypt.hashpw(mot_de_passe.encode("utf-8"), sel)
    return empreinte.decode("utf-8")


def verifier_mot_de_passe(clair: str, hache: str) -> bool:
    return bcrypt.checkpw(clair.encode("utf-8"), hache.encode("utf-8"))


def creer_jeton(sujet: str, expire_minutes: Optional[int] = None) -> str:
    duree = expire_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    expiration = datetime.now(timezone.utc) + timedelta(minutes=duree)
    donnees = {"sub": str(sujet), "exp": expiration}
    return jwt.encode(donnees, settings.SECRET_KEY, algorithm=ALGORITHM)


def lire_jeton(jeton: str) -> Optional[str]:
    try:
        donnees = jwt.decode(jeton, settings.SECRET_KEY, algorithms=[ALGORITHM])
        return donnees.get("sub")
    except JWTError:
        return None

"""
Cree le premier compte administrateur.
A executer une seule fois, au demarrage du systeme.
"""

import sys
from getpass import getpass

from app.core.database import SessionLocal
from app.core.security import hasher_mot_de_passe
from app.models import Utilisateur

db = SessionLocal()

login = input("Login de l'administrateur : ").strip()
if not login:
    print("Login vide. Abandon.")
    sys.exit(1)

existant = db.query(Utilisateur).filter(Utilisateur.login == login).first()
if existant:
    print(f"Le login '{login}' existe deja. Abandon.")
    sys.exit(1)

nom = input("Nom affiche : ").strip() or login
email = input("Email (optionnel) : ").strip() or None

mdp = getpass("Mot de passe : ")
mdp2 = getpass("Confirmer : ")
if mdp != mdp2:
    print("Les mots de passe ne correspondent pas. Abandon.")
    sys.exit(1)
if len(mdp) < 8:
    print("Mot de passe trop court (8 caracteres minimum). Abandon.")
    sys.exit(1)

admin = Utilisateur(
    login=login,
    nom_affichage=nom,
    email=email,
    mot_de_passe_hash=hasher_mot_de_passe(mdp),
    is_actif=True,
    is_superadmin=True,
    doit_changer_mdp=False,
)

db.add(admin)
db.commit()
db.refresh(admin)

print(f"\nAdministrateur cree : {admin.login} (id {admin.id})")
db.close()

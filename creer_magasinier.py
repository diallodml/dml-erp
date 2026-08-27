from app.core.database import SessionLocal
from app.core.security import hasher_mot_de_passe
from app.models import Role, Utilisateur

db = SessionLocal()

u = db.query(Utilisateur).filter(Utilisateur.login == "magasinier1").first()
if u is None:
    u = Utilisateur(
        login="magasinier1",
        nom_affichage="Magasinier Test",
        mot_de_passe_hash=hasher_mot_de_passe("Magasin2026"),
        is_actif=True,
        is_superadmin=False,
        doit_changer_mdp=False,
    )
    db.add(u)
    db.flush()

role = db.query(Role).filter(Role.code == "MAGASINIER").first()
u.roles = [role]
db.commit()
print("Compte magasinier1 cree, role MAGASINIER")
db.close()

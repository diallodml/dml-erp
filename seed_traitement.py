from app.core.database import SessionLocal
from app.models import Permission, Role
from app.models.enums import TypeAction

db = SessionLocal()

NOUVELLES = [
    ("traitement.expedier", "traitement", "expedition", TypeAction.CREER,
     "Envoyer un lot chez un prestataire", False),
    ("traitement.receptionner", "traitement", "reception", TypeAction.CREER,
     "Receptionner un lot traite", False),
    ("traitement.lire", "traitement", "rendement", TypeAction.LIRE,
     "Consulter les rendements des prestataires", True),
]

perms = {}
for code, module, ressource, action, libelle, sensible in NOUVELLES:
    p = db.query(Permission).filter(Permission.code == code).first()
    if p is None:
        p = Permission(code=code, module=module, ressource=ressource,
                       action=action, libelle=libelle, is_sensible=sensible)
        db.add(p)
        db.flush()
    perms[code] = p

magasinier = db.query(Role).filter(Role.code == "MAGASINIER").first()
if magasinier:
    ajout = [perms["traitement.expedier"], perms["traitement.receptionner"]]
    magasinier.permissions = list(
        {p.id: p for p in list(magasinier.permissions) + ajout}.values()
    )

direction = db.query(Role).filter(Role.code == "DIRECTION").first()
if direction:
    direction.permissions = list(
        {p.id: p for p in list(direction.permissions) + list(perms.values())}.values()
    )

db.commit()
for r in db.query(Role).order_by(Role.niveau_hierarchique).all():
    print(f"{r.code:15} {len(r.permissions)} permissions")
db.close()

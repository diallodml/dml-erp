from app.core.database import SessionLocal
from app.models import Permission, Role
from app.models.enums import TypeAction

db = SessionLocal()

PERMS = [
    ("referentiel.client.creer", "referentiel", "client", TypeAction.CREER,
     "Creer un client industriel", False),
    ("referentiel.client.lire", "referentiel", "client", TypeAction.LIRE,
     "Consulter les clients", False),
]

perms = {}
for code, module, ressource, action, libelle, sensible in PERMS:
    p = db.query(Permission).filter(Permission.code == code).first()
    if p is None:
        p = Permission(code=code, module=module, ressource=ressource,
                       action=action, libelle=libelle, is_sensible=sensible)
        db.add(p)
        db.flush()
    perms[code] = p

for code_role in ("DIRECTION", "AGENT_SAISIE"):
    r = db.query(Role).filter(Role.code == code_role).first()
    if r:
        r.permissions = list(
            {p.id: p for p in list(r.permissions) + list(perms.values())}.values()
        )

magasinier = db.query(Role).filter(Role.code == "MAGASINIER").first()
if magasinier:
    magasinier.permissions = list(
        {p.id: p for p in list(magasinier.permissions) + [perms["referentiel.client.lire"]]}.values()
    )

db.commit()
for r in db.query(Role).order_by(Role.niveau_hierarchique).all():
    print(f"{r.code:15} {len(r.permissions)} permissions")
db.close()

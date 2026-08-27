from app.core.database import SessionLocal
from app.models import Permission, Role
from app.models.enums import TypeAction

db = SessionLocal()

NOUVELLES = [
    ("vente.livraison.creer", "vente", "livraison", TypeAction.CREER,
     "Livrer un industriel et sortir du stock", False),
    ("vente.reversement.lire", "vente", "reversement", TypeAction.LIRE,
     "Consulter ce que DML doit aux collecteurs", False),
    ("vente.reversement.payer", "vente", "reversement", TypeAction.VALIDER,
     "Payer un collecteur", True),
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

agent = db.query(Role).filter(Role.code == "AGENT_SAISIE").first()
if agent:
    ajout = [perms["vente.livraison.creer"], perms["vente.reversement.lire"]]
    agent.permissions = list({p.id: p for p in list(agent.permissions) + ajout}.values())

direction = db.query(Role).filter(Role.code == "DIRECTION").first()
if direction:
    direction.permissions = list(
        {p.id: p for p in list(direction.permissions) + list(perms.values())}.values()
    )

db.commit()
for r in db.query(Role).order_by(Role.niveau_hierarchique).all():
    print(f"{r.code:15} {len(r.permissions)} permissions")
db.close()

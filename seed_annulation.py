from app.core.database import SessionLocal
from app.models import Permission, Role
from app.models.enums import TypeAction

db = SessionLocal()

PERMS = [
    ("annulation.avance", "annulation", "avance", TypeAction.SUPPRIMER,
     "Annuler une avance du jour", True),
    ("annulation.ligne", "annulation", "ligne", TypeAction.SUPPRIMER,
     "Supprimer une ligne d'achat du jour", False),
    ("annulation.reception", "annulation", "reception", TypeAction.SUPPRIMER,
     "Annuler une reception du jour", True),
    ("annulation.stock", "annulation", "stock", TypeAction.SUPPRIMER,
     "Extourner un lot du jour", True),
    ("annulation.ancienne", "annulation", "ancienne", TypeAction.VALIDER,
     "Annuler une operation anterieure au jour meme", True),
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

# L'agent corrige ses erreurs du jour, pas au-dela
agent = db.query(Role).filter(Role.code == "AGENT_SAISIE").first()
if agent:
    ajout = [perms[c] for c in ("annulation.avance", "annulation.ligne")]
    agent.permissions = list({p.id: p for p in list(agent.permissions) + ajout}.values())

magasinier = db.query(Role).filter(Role.code == "MAGASINIER").first()
if magasinier:
    ajout = [perms[c] for c in ("annulation.reception", "annulation.stock")]
    magasinier.permissions = list({p.id: p for p in list(magasinier.permissions) + ajout}.values())

# Seule la direction peut remonter dans le temps
direction = db.query(Role).filter(Role.code == "DIRECTION").first()
if direction:
    direction.permissions = list(
        {p.id: p for p in list(direction.permissions) + list(perms.values())}.values()
    )

db.commit()
for r in db.query(Role).order_by(Role.niveau_hierarchique).all():
    print(f"{r.code:15} {len(r.permissions)} permissions")
db.close()

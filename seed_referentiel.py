from app.core.database import SessionLocal
from app.models import Permission, Role
from app.models.enums import TypeAction

db = SessionLocal()

NOUVELLES = [
    ("referentiel.produit.creer", "referentiel", "produit", TypeAction.CREER,
     "Creer un produit", False),
    ("referentiel.produit.lire", "referentiel", "produit", TypeAction.LIRE,
     "Consulter les produits", False),
    ("referentiel.magasin.creer", "referentiel", "magasin", TypeAction.CREER,
     "Creer un magasin", False),
    ("referentiel.prestataire.creer", "referentiel", "prestataire", TypeAction.CREER,
     "Creer un prestataire de traitement", False),
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
    ajout = [perms["referentiel.produit.creer"], perms["referentiel.produit.lire"]]
    agent.permissions = list({p.id: p for p in list(agent.permissions) + ajout}.values())

magasinier = db.query(Role).filter(Role.code == "MAGASINIER").first()
if magasinier:
    magasinier.permissions = list(
        {p.id: p for p in list(magasinier.permissions) + [perms["referentiel.produit.lire"]]}.values()
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

"""Ajoute les permissions d'administration des referentiels."""

from app.core.database import SessionLocal
from app.models import Permission, Role
from app.models.enums import TypeAction

db = SessionLocal()

NOUVELLES = [
    ("referentiel.collecteur.creer", "referentiel", "collecteur", TypeAction.CREER,
     "Creer un collecteur", False),
    ("referentiel.collecteur.lire", "referentiel", "collecteur", TypeAction.LIRE,
     "Consulter les collecteurs", False),
    ("referentiel.zone.creer", "referentiel", "zone", TypeAction.CREER,
     "Creer un marche de collecte", False),
    ("referentiel.plafond.modifier", "referentiel", "plafond", TypeAction.MODIFIER,
     "Fixer le plafond d'avance d'un collecteur", True),
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
    ajout = [perms[c] for c in
             ["referentiel.collecteur.creer", "referentiel.collecteur.lire",
              "referentiel.zone.creer"]]
    agent.permissions = list({p.id: p for p in list(agent.permissions) + ajout}.values())

direction = db.query(Role).filter(Role.code == "DIRECTION").first()
if direction:
    direction.permissions = list(
        {p.id: p for p in list(direction.permissions) + list(perms.values())}.values()
    )

db.commit()
print("")
for r in db.query(Role).order_by(Role.niveau_hierarchique).all():
    print(f"{r.code:15} {len(r.permissions)} permissions")
print("")
db.close()

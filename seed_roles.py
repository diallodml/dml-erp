"""
Cree les permissions et les roles du module Collecte.
Reexecutable sans risque : ne cree que ce qui manque.
"""

from app.core.database import SessionLocal
from app.models import Permission, Role
from app.models.enums import PorteeDonnees, TypeAction

db = SessionLocal()

PERMISSIONS = [
    ("collecte.avance.creer", "collecte", "avance", TypeAction.CREER,
     "Remettre une avance a un collecteur", True),
    ("collecte.avance.lire", "collecte", "avance", TypeAction.LIRE,
     "Consulter les avances et soldes", False),
    ("collecte.collecte.creer", "collecte", "collecte", TypeAction.CREER,
     "Ouvrir une collecte", False),
    ("collecte.collecte.lire", "collecte", "collecte", TypeAction.LIRE,
     "Consulter les collectes", False),
    ("collecte.ligne.creer", "collecte", "ligne", TypeAction.CREER,
     "Saisir un achat au marche", False),
    ("collecte.reception.creer", "collecte", "reception", TypeAction.CREER,
     "Receptionner une collecte au magasin", False),
    ("collecte.stock.creer", "collecte", "stock", TypeAction.CREER,
     "Entrer la marchandise en stock", False),
    ("collecte.stock.lire", "collecte", "stock", TypeAction.LIRE,
     "Consulter l'etat du stock", False),
    ("collecte.ecart.lire", "collecte", "ecart", TypeAction.LIRE,
     "Consulter les ecarts par collecteur", True),
]

perms = {}
for code, module, ressource, action, libelle, sensible in PERMISSIONS:
    p = db.query(Permission).filter(Permission.code == code).first()
    if p is None:
        p = Permission(
            code=code, module=module, ressource=ressource, action=action,
            libelle=libelle, is_sensible=sensible,
        )
        db.add(p)
        db.flush()
    perms[code] = p

ROLES = [
    ("AGENT_SAISIE", "Agent de saisie", PorteeDonnees.GLOBAL, 30, [
        "collecte.avance.creer", "collecte.avance.lire",
        "collecte.collecte.creer", "collecte.collecte.lire",
        "collecte.ligne.creer",
    ]),
    ("MAGASINIER", "Magasinier", PorteeDonnees.MAGASIN_AFFECTE, 40, [
        "collecte.collecte.lire",
        "collecte.reception.creer",
        "collecte.stock.creer", "collecte.stock.lire",
    ]),
    ("DIRECTION", "Direction", PorteeDonnees.GLOBAL, 10,
     [c for c, *_ in PERMISSIONS]),
]

for code, nom, portee, niveau, codes_perms in ROLES:
    r = db.query(Role).filter(Role.code == code).first()
    if r is None:
        r = Role(
            code=code, nom=nom, portee_par_defaut=portee,
            niveau_hierarchique=niveau, is_systeme=True,
        )
        db.add(r)
        db.flush()
    r.permissions = [perms[c] for c in codes_perms]

db.commit()

print("")
print("=== ROLES CREES ===")
for r in db.query(Role).order_by(Role.niveau_hierarchique).all():
    print(f"{r.code:15} portee={r.portee_par_defaut.value:16} {len(r.permissions)} permissions")
print("")
db.close()

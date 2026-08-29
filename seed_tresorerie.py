from app.core.database import SessionLocal
from app.models import CategorieDepense, Permission, Role
from app.models.enums import TypeAction

db = SessionLocal()

PERMS = [
    ("tresorerie.lire", "tresorerie", "compte", TypeAction.LIRE,
     "Consulter les soldes et le journal", True),
    ("tresorerie.mouvement.creer", "tresorerie", "mouvement", TypeAction.CREER,
     "Enregistrer une entree ou une sortie d'argent", True),
    ("tresorerie.compte.creer", "tresorerie", "compte", TypeAction.CREER,
     "Creer un compte de tresorerie ou une categorie", True),
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

direction = db.query(Role).filter(Role.code == "DIRECTION").first()
if direction:
    direction.permissions = list(
        {p.id: p for p in list(direction.permissions) + list(perms.values())}.values()
    )

CATEGORIES = [
    ("ELECTRICITE", "Electricite ENEO"),
    ("EAU", "Eau CAMWATER"),
    ("INTERNET", "Internet et telecommunications"),
    ("CARBURANT", "Carburant et lubrifiants"),
    ("LOYER", "Loyer et charges locatives"),
    ("SALAIRES", "Salaires et charges sociales"),
    ("TRANSPORT", "Transport et manutention"),
    ("ENTRETIEN", "Entretien et reparations"),
    ("FOURNITURES", "Fournitures de bureau"),
    ("IMPOTS", "Impots et taxes"),
    ("BANQUE", "Frais bancaires et Mobile Money"),
    ("DIVERS", "Charges diverses"),
]

for code, libelle in CATEGORIES:
    if db.query(CategorieDepense).filter(CategorieDepense.code == code).first() is None:
        db.add(CategorieDepense(code=code, libelle=libelle))

db.commit()
print("")
for r in db.query(Role).order_by(Role.niveau_hierarchique).all():
    print(f"{r.code:15} {len(r.permissions)} permissions")
print(f"\n{db.query(CategorieDepense).count()} categories de depense")
db.close()

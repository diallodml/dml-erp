from app.core.database import SessionLocal
from app.models import Permission, Role
from app.models.enums import TypeAction

db = SessionLocal()

p = db.query(Permission).filter(Permission.code == "rentabilite.lire").first()
if p is None:
    p = Permission(
        code="rentabilite.lire", module="rentabilite", ressource="resultat",
        action=TypeAction.LIRE, libelle="Consulter la rentabilite de l'activite",
        is_sensible=True,
    )
    db.add(p)
    db.flush()

direction = db.query(Role).filter(Role.code == "DIRECTION").first()
if direction:
    direction.permissions = list(
        {x.id: x for x in list(direction.permissions) + [p]}.values()
    )

db.commit()
for r in db.query(Role).order_by(Role.niveau_hierarchique).all():
    print(f"{r.code:15} {len(r.permissions)} permissions")
db.close()

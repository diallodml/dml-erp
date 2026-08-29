from app.core.database import SessionLocal
from app.models import Permission, Role
from app.models.enums import TypeAction

db = SessionLocal()

p = db.query(Permission).filter(Permission.code == "audit.lire").first()
if p is None:
    p = Permission(
        code="audit.lire", module="audit", ressource="journal",
        action=TypeAction.LIRE, libelle="Consulter la piste d'audit",
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

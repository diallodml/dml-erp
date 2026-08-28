from decimal import Decimal

from app.core.database import SessionLocal
from app.models import Magasin, Prestataire
from app.models.enums import BaseFacturationTraitement, TypeMagasin

db = SessionLocal()

mag = db.query(Magasin).filter(Magasin.code == "MAG-PRESTA").first()
if mag is None:
    mag = Magasin(
        code="MAG-PRESTA",
        nom="Chez le prestataire",
        type_magasin=TypeMagasin.SOUS_TRAITE,
        ville="Douala",
    )
    db.add(mag)
    db.flush()

p = db.query(Prestataire).filter(Prestataire.code == "PRESTA-01").first()
if p is None:
    p = Prestataire(
        code="PRESTA-01",
        nom="Sechoir de Bonaberi",
        ville="Douala",
        magasin_id=mag.id,
        prix_tonne=Decimal("8000.00"),
        base_facturation=BaseFacturationTraitement.TONNE_ENTREE,
        delai_habituel_jours=3,
    )
    db.add(p)

db.commit()
print("Prestataire cree :", p.nom)
db.close()

"""Donnees de test pour derouler le cycle collecte. Pas pour la production."""

from decimal import Decimal

from app.core.database import SessionLocal
from app.models import Collecteur, FamilleProduit, Magasin, Produit, ZoneCollecte
from app.models.enums import ModeDetention, TypeCollecteur, TypeMagasin, UniteMesure

db = SessionLocal()

zone = db.query(ZoneCollecte).filter(ZoneCollecte.code == "ZC-TEST").first()
if zone is None:
    zone = ZoneCollecte(
        code="ZC-TEST",
        libelle="Marche de Guider",
        village="Guider",
        departement="Mayo-Louti",
        region="Nord",
        jour_marche="Samedi",
        distance_douala_km=Decimal("1050.000"),
    )
    db.add(zone)

collecteur = db.query(Collecteur).filter(Collecteur.code == "COL-TEST").first()
if collecteur is None:
    collecteur = Collecteur(
        code="COL-TEST",
        nom="Amadou Bello",
        type_collecteur=TypeCollecteur.INDEPENDANT,
        telephone="+237600000000",
        mode_detention_habituel=ModeDetention.MARGE_FIXE_TONNE,
        marge_fixe_tonne=Decimal("15000.00"),
        plafond_avance=Decimal("5000000.00"),
    )
    db.add(collecteur)

famille = db.query(FamilleProduit).filter(FamilleProduit.code == "CEREALES").first()
if famille is None:
    famille = FamilleProduit(code="CEREALES", nom="Cereales")
    db.add(famille)
    db.flush()

produit = db.query(Produit).filter(Produit.code == "MAIS").first()
if produit is None:
    produit = Produit(
        code="MAIS",
        designation="Mais grain",
        famille_id=famille.id,
        unite_base=UniteMesure.KG,
        poids_sac_kg=Decimal("100.000"),
        taux_humidite_max=Decimal("14.00"),
        taux_impuretes_max=Decimal("2.00"),
    )
    db.add(produit)

magasin = db.query(Magasin).filter(Magasin.code == "MAG-A").first()
if magasin is None:
    magasin = Magasin(
        code="MAG-A",
        nom="Magasin A - Douala",
        type_magasin=TypeMagasin.PRINCIPAL,
        ville="Douala",
    )
    db.add(magasin)

db.commit()

print("")
print("=== IDENTIFIANTS POUR SWAGGER ===")
print("collecteur_id          :", db.query(Collecteur).filter(Collecteur.code == "COL-TEST").first().id)
print("zone_id                :", db.query(ZoneCollecte).filter(ZoneCollecte.code == "ZC-TEST").first().id)
print("produit_id             :", db.query(Produit).filter(Produit.code == "MAIS").first().id)
print("magasin_destination_id :", db.query(Magasin).filter(Magasin.code == "MAG-A").first().id)
print("")
db.close()

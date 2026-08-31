"""
Bon de commande, bon de livraison, facture.

Le flux reel chez DML
---------------------
1. Le client envoie un bon de commande : sa reference, le tonnage
   demande, et le PRIX AU KILO convenu.
2. DML charge le camion et compte les sacs. On ne pese pas au depart.
3. L'industriel pese a l'arrivee et communique le tonnage + un numero de
   ticket. C'est CE tonnage qui fait foi.
4. La facture applique le prix du bon de commande au tonnage pese, et
   porte la reference du client.

Point de controle
-----------------
DML facture sur une pesee qu'il n'a pas faite. L'ecart entre le poids
theorique des sacs charges et le tonnage annonce par le client est le seul
controle possible. `ecart_poids` le chiffre a chaque livraison.
"""

from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    BonCommandeClient,
    BonLivraison,
    Client,
    FactureVente,
    LigneBonCommande,
    LigneBonLivraison,
    LigneFactureVente,
    Lot,
    MouvementStock,
    Produit,
    Utilisateur,
)
from app.models.enums import (
    SensMouvement,
    StatutCommandeVente,
    StatutFacture,
    StatutLivraison,
    TypeMouvementStock,
    UniteMesure,
)
from app.repositories.collecte import prochain_numero


# ---------------------------------------------------------------------------
# BON DE COMMANDE
# ---------------------------------------------------------------------------
def creer_commande(db: Session, donnees, utilisateur: Utilisateur) -> BonCommandeClient:
    """
    Enregistre la commande recue du client.

    Le prix au kilo est fixe ici : la facture le reprendra tel quel.
    """
    montant = (donnees.tonnage_demande_kg * donnees.prix_kg).quantize(Decimal("0.01"))

    bc = BonCommandeClient(
        numero=prochain_numero(db, BonCommandeClient, "BC"),
        client_id=donnees.client_id,
        reference_client=donnees.reference_client,
        date_commande=donnees.date_commande,
        date_livraison_souhaitee=donnees.date_livraison_souhaitee,
        lieu_livraison=donnees.lieu_livraison,
        montant_ht=montant,
        montant_ttc=montant,
        statut=StatutCommandeVente.CONFIRMEE,
        created_by_id=utilisateur.id,
    )
    db.add(bc)
    db.flush()

    ligne = LigneBonCommande(
        commande_id=bc.id,
        produit_id=donnees.produit_id,
        quantite_commandee=donnees.tonnage_demande_kg,
        unite=UniteMesure.KG,
        prix_unitaire=donnees.prix_kg,
        montant_ht=montant,
        montant_ttc=montant,
    )
    db.add(ligne)
    db.commit()
    db.refresh(bc)
    return bc


def liste_commandes(db: Session, ouvertes_seulement: bool = False) -> list[dict]:
    q = (
        db.query(BonCommandeClient, Client.raison_sociale)
        .join(Client, Client.id == BonCommandeClient.client_id)
    )
    if ouvertes_seulement:
        q = q.filter(BonCommandeClient.statut.in_([
            StatutCommandeVente.CONFIRMEE,
            StatutCommandeVente.PARTIELLEMENT_LIVREE,
        ]))

    resultats = []
    for bc, client in q.order_by(BonCommandeClient.date_commande.desc()).limit(200).all():
        lignes = (
            db.query(LigneBonCommande, Produit.designation)
            .outerjoin(Produit, Produit.id == LigneBonCommande.produit_id)
            .filter(LigneBonCommande.commande_id == bc.id)
            .all()
        )
        demande = sum((l.quantite_commandee for l, _ in lignes), Decimal("0"))
        prix = lignes[0][0].prix_unitaire if lignes else Decimal("0")
        produit = lignes[0][1] if lignes else "—"

        livre = Decimal(
            db.query(func.coalesce(func.sum(BonLivraison.poids_livre), 0))
            .filter(BonLivraison.commande_id == bc.id)
            .scalar() or 0
        )

        facture, encaisse = (
            db.query(
                func.coalesce(func.sum(FactureVente.montant_ttc), 0),
                func.coalesce(func.sum(FactureVente.montant_regle), 0),
            )
            .filter(FactureVente.commande_id == bc.id)
            .first()
        )
        facture = Decimal(facture or 0)
        encaisse = Decimal(encaisse or 0)

        resultats.append({
            "id": str(bc.id),
            "numero": bc.numero,
            "reference_client": bc.reference_client or "—",
            "client": client,
            "produit": produit,
            "date_commande": bc.date_commande,
            "date_souhaitee": bc.date_livraison_souhaitee,
            "lieu_livraison": bc.lieu_livraison or "—",
            "tonnage_demande_kg": demande,
            "tonnage_livre_kg": livre,
            "reste_kg": demande - livre,
            "prix_kg": prix,
            "montant_prevu": bc.montant_ht,
            "montant_facture": facture,
            "montant_encaisse": encaisse,
            "reste_du": facture - encaisse,
            "statut": bc.statut.value,
        })
    return resultats


# ---------------------------------------------------------------------------
# BON DE LIVRAISON
# ---------------------------------------------------------------------------
def creer_livraison(db: Session, donnees, utilisateur: Utilisateur) -> BonLivraison:
    """
    Chargement du camion. On compte les sacs, on ne pese pas.

    Le poids charge est une ESTIMATION : nombre de sacs x poids nominal.
    """
    bc = db.get(BonCommandeClient, donnees.commande_id)
    if bc is None:
        raise ValueError("Bon de commande introuvable")

    lot = db.get(Lot, donnees.lot_id)
    if lot is None:
        raise ValueError("Lot introuvable")

    poids_theorique = (
        Decimal(donnees.nombre_sacs) * donnees.poids_sac_kg
    ).quantize(Decimal("0.001"))

    if poids_theorique > lot.quantite_disponible:
        raise ValueError(
            f"Stock insuffisant : {lot.quantite_disponible} kg disponibles "
            f"dans le lot {lot.numero}"
        )

    bl = BonLivraison(
        numero=prochain_numero(db, BonLivraison, "BL"),
        client_id=bc.client_id,
        commande_id=bc.id,
        magasin_id=lot.magasin_id,
        date_livraison=donnees.date_livraison,
        lieu_livraison=donnees.lieu_livraison or bc.lieu_livraison,
        transporteur_externe=donnees.transporteur,
        immatriculation_declaree=donnees.immatriculation,
        nombre_sacs=donnees.nombre_sacs,
        poids_charge=poids_theorique,
        statut=StatutLivraison.EN_ROUTE,
        created_by_id=utilisateur.id,
    )
    db.add(bl)
    db.flush()

    ligne = LigneBonLivraison(
        bon_livraison_id=bl.id,
        produit_id=lot.produit_id,
        lot_id=lot.id,
        quantite_livree=poids_theorique,
        unite=UniteMesure.KG,
        nombre_sacs=donnees.nombre_sacs,
        cout_revient_unitaire=lot.cout_unitaire,
    )
    db.add(ligne)
    db.commit()
    db.refresh(bl)
    return bl


def enregistrer_pesee(
    db: Session, livraison_id: UUID, donnees, utilisateur: Utilisateur
) -> dict:
    """
    L'industriel a pese et communique le tonnage.

    C'est ce chiffre qui fait foi pour la facture. L'ecart avec le poids
    theorique des sacs est le seul controle dont DML dispose.
    """
    bl = db.get(BonLivraison, livraison_id)
    if bl is None:
        raise ValueError("Bon de livraison introuvable")
    if bl.statut == StatutLivraison.LIVRE:
        raise ValueError("Pesee deja enregistree")

    bl.poids_livre = donnees.poids_livre_kg
    bl.ecart_poids = (bl.poids_livre - bl.poids_charge).quantize(Decimal("0.001"))
    bl.numero_ticket_pesee = donnees.numero_ticket
    bl.signataire_client = donnees.signataire
    bl.reserves_client = donnees.reserves
    bl.statut = (
        StatutLivraison.LIVRE_AVEC_ECART
        if abs(bl.ecart_poids) > Decimal("50")
        else StatutLivraison.LIVRE
    )
    bl.updated_by_id = utilisateur.id

    # La marchandise sort du stock sur le poids REELLEMENT pese
    ligne = (
        db.query(LigneBonLivraison)
        .filter(LigneBonLivraison.bon_livraison_id == bl.id)
        .first()
    )
    if ligne is not None and ligne.lot_id:
        lot = db.get(Lot, ligne.lot_id)
        sortie = min(bl.poids_livre, lot.quantite_disponible)

        mvt = MouvementStock(
            numero=prochain_numero(db, MouvementStock, "MVT"),
            type_mouvement=TypeMouvementStock.SORTIE_VENTE,
            sens=SensMouvement.SORTIE,
            date_mouvement=donnees.date_pesee,
            produit_id=ligne.produit_id,
            lot_id=lot.id,
            magasin_source_id=lot.magasin_id,
            quantite=sortie,
            unite=UniteMesure.KG,
            cout_unitaire=lot.cout_unitaire,
            nombre_sacs=bl.nombre_sacs,
            reference_externe=bl.numero,
            created_by_id=utilisateur.id,
        )
        db.add(mvt)
        db.flush()
        ligne.quantite_livree = sortie
        ligne.mouvement_stock_id = mvt.id
        lot.quantite_disponible = lot.quantite_disponible - sortie

    # Statut de la commande
    bc = db.get(BonCommandeClient, bl.commande_id) if bl.commande_id else None
    if bc is not None:
        total_livre = Decimal(
            db.query(func.coalesce(func.sum(BonLivraison.poids_livre), 0))
            .filter(BonLivraison.commande_id == bc.id)
            .scalar() or 0
        )
        demande = Decimal(
            db.query(func.coalesce(func.sum(LigneBonCommande.quantite_commandee), 0))
            .filter(LigneBonCommande.commande_id == bc.id)
            .scalar() or 0
        )
        bc.statut = (
            StatutCommandeVente.LIVREE if total_livre >= demande
            else StatutCommandeVente.PARTIELLEMENT_LIVREE
        )

    db.commit()
    db.refresh(bl)
    return {
        "numero": bl.numero,
        "poids_charge_kg": bl.poids_charge,
        "poids_livre_kg": bl.poids_livre,
        "ecart_kg": bl.ecart_poids,
        "nombre_sacs": bl.nombre_sacs,
        "ticket": bl.numero_ticket_pesee,
    }


# ---------------------------------------------------------------------------
# FACTURE
# ---------------------------------------------------------------------------
def creer_facture(db: Session, livraison_id: UUID, donnees, utilisateur: Utilisateur):
    """
    Facture la livraison : tonnage pese chez le client x prix du bon de
    commande.

    La reference du bon de commande client figure sur la facture --
    c'est ce qui permet a l'industriel de la rapprocher de sa commande.
    """
    bl = db.get(BonLivraison, livraison_id)
    if bl is None:
        raise ValueError("Bon de livraison introuvable")
    if bl.statut not in (StatutLivraison.LIVRE, StatutLivraison.LIVRE_AVEC_ECART):
        raise ValueError("Enregistrez d'abord la pesee du client")
    if bl.is_facture:
        raise ValueError("Cette livraison est deja facturee")

    bc = db.get(BonCommandeClient, bl.commande_id) if bl.commande_id else None

    ligne_bl = (
        db.query(LigneBonLivraison)
        .filter(LigneBonLivraison.bon_livraison_id == bl.id)
        .first()
    )

    # Le prix vient du bon de commande, sauf correction explicite
    prix_kg = donnees.prix_kg
    if prix_kg is None and bc is not None:
        lc = (
            db.query(LigneBonCommande)
            .filter(LigneBonCommande.commande_id == bc.id)
            .first()
        )
        prix_kg = lc.prix_unitaire if lc else Decimal("0")
    prix_kg = prix_kg or Decimal("0")

    montant = (bl.poids_livre * prix_kg).quantize(Decimal("0.01"))
    transport = donnees.frais_transport or Decimal("0")
    total = montant + transport

    cout = Decimal("0")
    if ligne_bl is not None:
        cout = (bl.poids_livre * (ligne_bl.cout_revient_unitaire or Decimal("0"))).quantize(
            Decimal("0.01")
        )

    facture = FactureVente(
        numero=prochain_numero(db, FactureVente, "FA"),
        client_id=bl.client_id,
        commande_id=bl.commande_id,
        bon_livraison_id=bl.id,
        date_facture=donnees.date_facture,
        date_echeance=donnees.date_echeance,
        montant_ht=montant,
        base_taxable=montant,
        taux_tva=Decimal("0"),
        montant_tva=Decimal("0"),
        frais_transport=transport,
        montant_ttc=total,
        cout_revient_total=cout,
        statut=StatutFacture.EMISE,
        mode_reglement_prevu=donnees.mode_reglement,
        conditions_paiement=donnees.conditions,
        created_by_id=utilisateur.id,
    )
    db.add(facture)
    db.flush()

    produit = db.get(Produit, ligne_bl.produit_id) if ligne_bl else None
    db.add(LigneFactureVente(
        facture_id=facture.id,
        produit_id=ligne_bl.produit_id if ligne_bl else None,
        designation=(produit.designation if produit else "Produits agricoles")
                    + (f" — {bl.nombre_sacs} sacs" if bl.nombre_sacs else ""),
        quantite=bl.poids_livre,
        unite=UniteMesure.KG,
        prix_unitaire=prix_kg,
        montant_ht=montant,
        montant_ttc=montant,
    ))

    bl.is_facture = True
    db.commit()
    db.refresh(facture)

    return {
        "id": str(facture.id),
        "numero": facture.numero,
        "reference_client": bc.reference_client if bc else None,
        "tonnage_kg": bl.poids_livre,
        "prix_kg": prix_kg,
        "montant_ht": montant,
        "frais_transport": transport,
        "montant_ttc": total,
        "marge": total - cout,
    }


def liste_factures(db: Session) -> list[dict]:
    """Factures emises, avec ce qui reste du."""
    lignes = (
        db.query(FactureVente, Client.raison_sociale, BonCommandeClient.reference_client,
                 BonLivraison.numero)
        .join(Client, Client.id == FactureVente.client_id)
        .outerjoin(BonCommandeClient, BonCommandeClient.id == FactureVente.commande_id)
        .outerjoin(BonLivraison, BonLivraison.id == FactureVente.bon_livraison_id)
        .order_by(FactureVente.date_facture.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": str(f.id),
            "numero": f.numero,
            "reference_client": ref or "—",
            "bon_livraison": bl or "—",
            "client": client,
            "date_facture": f.date_facture,
            "date_echeance": f.date_echeance,
            "montant_ttc": f.montant_ttc,
            "montant_regle": f.montant_regle,
            "reste_du": f.montant_ttc - (f.montant_regle or Decimal("0")),
            "marge": f.montant_ttc - (f.cout_revient_total or Decimal("0")),
            "statut": f.statut.value,
        }
        for f, client, ref, bl in lignes
    ]


def encaisser(db: Session, facture_id: UUID, donnees, utilisateur: Utilisateur) -> dict:
    """Enregistre un reglement client et alimente la tresorerie."""
    f = db.get(FactureVente, facture_id)
    if f is None:
        raise ValueError("Facture introuvable")

    solde = f.montant_ttc - (f.montant_regle or Decimal("0"))
    if donnees.montant > solde:
        raise ValueError(f"Montant superieur au solde du ({solde} F)")

    f.montant_regle = (f.montant_regle or Decimal("0")) + donnees.montant
    f.statut = (
        StatutFacture.REGLEE
        if f.montant_regle >= f.montant_ttc
        else StatutFacture.PARTIELLEMENT_REGLEE
    )
    f.updated_by_id = utilisateur.id

    if donnees.compte_tresorerie_id:
        from app.models import CompteTresorerie, MouvementTresorerie
        from app.models.enums import SensTresorerie

        compte = db.get(CompteTresorerie, donnees.compte_tresorerie_id)
        if compte is not None:
            client = db.get(Client, f.client_id)
            db.add(MouvementTresorerie(
                numero=prochain_numero(db, MouvementTresorerie, "TRS"),
                compte_tresorerie_id=compte.id,
                date_mouvement=donnees.date_reglement,
                sens=SensTresorerie.ENCAISSEMENT,
                montant=donnees.montant,
                libelle=f"Reglement facture {f.numero}",
                tiroir=compte.tiroir,
                mode_reglement=donnees.mode_reglement,
                beneficiaire=client.raison_sociale if client else None,
                created_by_id=utilisateur.id,
            ))
            compte.solde_actuel = compte.solde_actuel + donnees.montant
            compte.solde_theorique = compte.solde_theorique + donnees.montant

    db.commit()
    db.refresh(f)
    return {
        "numero": f.numero,
        "montant_regle": f.montant_regle,
        "reste_du": f.montant_ttc - f.montant_regle,
        "statut": f.statut.value,
    }


# ---------------------------------------------------------------------------
# PROFORMA
# ---------------------------------------------------------------------------
def creer_proforma(db: Session, donnees, utilisateur: Utilisateur):
    """
    Offre de prix envoyee au client.

    Le client accepte et commande, ou il contre-propose : on cree alors une
    REVISION qui garde le lien vers l'originale. L'historique montre comment
    le prix a evolue -- utile pour savoir qui negocie systematiquement.
    """
    from datetime import timedelta

    from app.models import LigneProforma, Proforma
    from app.models.enums import StatutProforma

    montant = (donnees.quantite_kg * donnees.prix_kg).quantize(Decimal("0.01"))

    origine = None
    version = 1
    if donnees.proforma_origine_id:
        origine = db.get(Proforma, donnees.proforma_origine_id)
        if origine is None:
            raise ValueError("Proforma d'origine introuvable")
        version = (origine.version or 1) + 1
        origine.statut = StatutProforma.REFUSEE
        origine.motif_refus = "Revisee : contre-proposition du client"
        origine.date_reponse_client = date.today()

    pf = Proforma(
        numero=prochain_numero(db, Proforma, "PRO"),
        client_id=donnees.client_id,
        date_emission=donnees.date_emission,
        duree_validite_jours=donnees.validite_jours or 15,
        date_expiration=donnees.date_emission + timedelta(days=donnees.validite_jours or 15),
        objet=donnees.objet,
        montant_ht=montant,
        montant_ttc=montant + (donnees.frais_transport or Decimal("0")),
        frais_transport=donnees.frais_transport or Decimal("0"),
        conditions_paiement=donnees.conditions_paiement,
        conditions_livraison=donnees.conditions_livraison,
        statut=StatutProforma.ENVOYEE,
        proforma_origine_id=donnees.proforma_origine_id,
        version=version,
        created_by_id=utilisateur.id,
    )
    db.add(pf)
    db.flush()

    produit = db.get(Produit, donnees.produit_id)
    db.add(LigneProforma(
        proforma_id=pf.id,
        produit_id=donnees.produit_id,
        designation=produit.designation if produit else None,
        quantite=donnees.quantite_kg,
        unite=UniteMesure.KG,
        prix_unitaire=donnees.prix_kg,
        montant_ht=montant,
        montant_ttc=montant,
    ))
    db.commit()
    db.refresh(pf)
    return pf


def liste_proformas(db: Session) -> list[dict]:
    """Proformas emises, avec l'historique des revisions."""
    from app.models import LigneProforma, Proforma

    lignes = (
        db.query(Proforma, Client.raison_sociale)
        .join(Client, Client.id == Proforma.client_id)
        .order_by(Proforma.date_emission.desc(), Proforma.numero.desc())
        .limit(200)
        .all()
    )

    resultats = []
    for pf, client in lignes:
        detail = (
            db.query(LigneProforma, Produit.designation)
            .outerjoin(Produit, Produit.id == LigneProforma.produit_id)
            .filter(LigneProforma.proforma_id == pf.id)
            .first()
        )
        origine = None
        if pf.proforma_origine_id:
            o = db.get(Proforma, pf.proforma_origine_id)
            origine = o.numero if o else None

        resultats.append({
            "id": str(pf.id),
            "numero": pf.numero,
            "version": pf.version or 1,
            "revise_de": origine,
            "client": client,
            "produit": detail[1] if detail else "—",
            "quantite_kg": detail[0].quantite if detail else Decimal("0"),
            "prix_kg": detail[0].prix_unitaire if detail else Decimal("0"),
            "montant_ttc": pf.montant_ttc,
            "date_emission": pf.date_emission,
            "date_expiration": pf.date_expiration,
            "statut": pf.statut.value,
            "objet": pf.objet,
        })
    return resultats


def transformer_proforma(db: Session, proforma_id: UUID, donnees, utilisateur: Utilisateur):
    """
    Le client a accepte : la proforma devient un bon de commande.

    Le prix et le tonnage sont repris tels quels -- pas de ressaisie, donc
    pas d'ecart entre ce qui a ete propose et ce qui est commande.
    """
    from app.models import LigneProforma, Proforma
    from app.models.enums import StatutProforma

    pf = db.get(Proforma, proforma_id)
    if pf is None:
        raise ValueError("Proforma introuvable")
    if pf.statut == StatutProforma.TRANSFORMEE:
        raise ValueError("Cette proforma a deja ete transformee en commande")

    ligne = (
        db.query(LigneProforma)
        .filter(LigneProforma.proforma_id == pf.id)
        .first()
    )
    if ligne is None:
        raise ValueError("Proforma sans ligne : impossible de la transformer")

    bc = BonCommandeClient(
        numero=prochain_numero(db, BonCommandeClient, "BC"),
        client_id=pf.client_id,
        proforma_id=pf.id,
        reference_client=donnees.reference_client,
        date_commande=donnees.date_commande,
        date_livraison_souhaitee=donnees.date_livraison_souhaitee,
        lieu_livraison=donnees.lieu_livraison,
        montant_ht=ligne.montant_ht,
        montant_ttc=ligne.montant_ht,
        statut=StatutCommandeVente.CONFIRMEE,
        created_by_id=utilisateur.id,
    )
    db.add(bc)
    db.flush()

    db.add(LigneBonCommande(
        commande_id=bc.id,
        produit_id=ligne.produit_id,
        designation=ligne.designation,
        quantite_commandee=ligne.quantite,
        unite=UniteMesure.KG,
        prix_unitaire=ligne.prix_unitaire,
        montant_ht=ligne.montant_ht,
        montant_ttc=ligne.montant_ht,
    ))

    pf.statut = StatutProforma.TRANSFORMEE
    pf.date_reponse_client = donnees.date_commande
    db.commit()
    db.refresh(bc)

    return {
        "numero": bc.numero,
        "proforma": pf.numero,
        "reference_client": bc.reference_client,
        "tonnage_kg": ligne.quantite,
        "prix_kg": ligne.prix_unitaire,
        "montant": bc.montant_ht,
    }

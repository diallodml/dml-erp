// ERP DML SARL - fonctions communes
const DML = {
  jeton()      { return localStorage.getItem("dml_jeton"); },
  profil()     { try { return JSON.parse(localStorage.getItem("dml_profil")); } catch { return null; } },
  peut(code)   { const p = DML.profil(); return p && (p.is_superadmin || (p.permissions || []).includes(code)); },

  deconnecter() {
    localStorage.removeItem("dml_jeton");
    localStorage.removeItem("dml_profil");
    location.href = "/";
  },

  async api(chemin, options = {}) {
    const entetes = { "Content-Type": "application/json", ...(options.headers || {}) };
    const j = DML.jeton();
    if (j) entetes["Authorization"] = "Bearer " + j;

    const reponse = await fetch(chemin, { ...options, headers: entetes });

    if (reponse.status === 401) { DML.deconnecter(); throw new Error("Session expiree"); }
    if (reponse.status === 403) throw new Error("Vous n'avez pas la permission d'effectuer cette action");

    const corps = await reponse.json().catch(() => null);
    if (!reponse.ok) {
      const d = corps && corps.detail;
      throw new Error(typeof d === "string" ? d : "La requete a echoue");
    }
    return corps;
  },

  exigerSession() {
    if (!DML.jeton()) { location.href = "/"; return false; }
    return true;
  },

  // Barre haute commune, adaptee au role
  barre(pageCourante) {
    const p = DML.profil() || {};
    const liens = [];
    if (DML.peut("collecte.ecart.lire") || DML.peut("collecte.stock.lire"))
      liens.push(["/tableau", "Bord"]);
    liens.push(["/saisie", "Saisie"]);
    if (DML.peut("collecte.collecte.lire"))
      liens.push(["/collectes", "Collectes"]);
    if (DML.peut("collecte.stock.lire"))
      liens.push(["/magasin", "Magasin"]);
    if (DML.peut("traitement.expedier"))
      liens.push(["/traitement", "Traitement"]);
    if (DML.peut("vente.livraison.creer"))
      liens.push(["/vente", "Livrer"]);
    if (DML.peut("vente.reversement.lire"))
      liens.push(["/livraisons", "Ventes"]);
    if (DML.peut("tresorerie.lire"))
      liens.push(["/tresorerie", "Caisse"]);
    if (DML.peut("securite.utilisateur.creer"))
      liens.push(["/utilisateurs", "Comptes"]);
    if (DML.peut("referentiel.collecteur.creer"))
      liens.push(["/referentiel", "Référentiels"]);
    if (DML.peut("referentiel.collecteur.lire"))
      liens.push(["/collecteur", "Fiches"]);

    const nav = liens.map(([href, texte]) =>
      `<a href="${href}"${href === pageCourante ? ' aria-current="page"' : ""}>${texte}</a>`
    ).join("");

    const roles = (p.roles || []).join(" · ") || (p.is_superadmin ? "Direction" : "Sans role");

    document.body.insertAdjacentHTML("afterbegin", `
      <header class="barre">
        <span class="marque">DML SARL</span>
        <nav>${nav}</nav>
        <span class="qui">
          <b>${p.nom_affichage || p.login || ""}</b>
          <span class="badge-role">${roles}</span>
          <button class="deconnexion" onclick="DML.deconnecter()">Quitter</button>
        </span>
      </header>`);
  },

  // Formatage
  fcfa(v)   { return new Intl.NumberFormat("fr-FR").format(Math.round(Number(v) || 0)) + " F"; },
  kg(v)     { return new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 0 }).format(Number(v) || 0) + " kg"; },
  tonnes(v) { return new Intl.NumberFormat("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 3 }).format(Number(v) || 0) + " t"; },

  message(cible, texte, type = "ok") {
    const el = document.getElementById(cible);
    if (!el) return;
    el.className = "message " + type;
    el.textContent = texte;
    el.hidden = false;
  },
  cacherMessage(cible) {
    const el = document.getElementById(cible);
    if (el) el.hidden = true;
  },
};

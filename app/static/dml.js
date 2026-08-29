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
      if (typeof d === "string") throw new Error(d);
      if (Array.isArray(d)) {
        throw new Error("Champ invalide — " +
          d.map(e => (e.loc || []).slice(-1)[0] + " : " + e.msg).join(" | "));
      }
      throw new Error("La requete a echoue");
    }
    return corps;
  },

  // --- Deconnexion automatique apres inactivite
  veille(minutes = 30) {
    let dernier = Date.now();
    let avertissement = null;
    const limite = minutes * 60 * 1000;

    const reveiller = () => {
      dernier = Date.now();
      if (avertissement) {
        avertissement.remove();
        avertissement = null;
      }
    };

    ["click", "keydown", "scroll", "touchstart"].forEach(
      e => document.addEventListener(e, reveiller, { passive: true })
    );

    setInterval(() => {
      const inactif = Date.now() - dernier;
      if (inactif >= limite) {
        localStorage.setItem("dml_expire", "1");
        DML.deconnecter();
      } else if (inactif >= limite - 60000 && !avertissement) {
        avertissement = document.createElement("div");
        avertissement.style.cssText =
          "position:fixed;bottom:20px;right:20px;background:#A8322D;color:#fff;" +
          "padding:12px 18px;font-family:Inter,sans-serif;font-size:14px;z-index:99;" +
          "max-width:300px;line-height:1.5";
        avertissement.textContent =
          "Vous allez être déconnecté dans une minute. Bougez la souris pour rester connecté.";
        document.body.appendChild(avertissement);
      }
    }, 10000);
  },

  exigerSession() {
    if (!DML.jeton()) { location.href = "/"; return false; }
    const p = DML.profil();
    if (p && p.doit_changer_mdp && !location.pathname.startsWith("/mot-de-passe")) {
      location.href = "/mot-de-passe";
      return false;
    }
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
    if (DML.peut("rentabilite.lire"))
      liens.push(["/rentabilite", "Résultat"]);
    if (DML.peut("securite.utilisateur.creer"))
      liens.push(["/utilisateurs", "Comptes"]);
    if (DML.peut("audit.lire"))
      liens.push(["/audit", "Journal"]);
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
    DML.veille(30);
  },

  async telecharger(url, nom) {
    try {
      const r = await fetch(url, {
        headers: { "Authorization": "Bearer " + DML.jeton() },
      });
      if (!r.ok) throw new Error("Export indisponible");
      const blob = await r.blob();
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = nom;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { alert(e.message); }
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

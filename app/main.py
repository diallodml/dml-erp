from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.v1 import rentabilite, annulation, auth, collecte, referentiel, traitement, tresorerie, utilisateur, vente

app = FastAPI(
    title="ERP DML SARL",
    description="Negoce agro-industriel, logistique et transport - Douala",
    version="0.3.0",
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

app.include_router(auth.router)
app.include_router(annulation.router)
app.include_router(collecte.router)
app.include_router(referentiel.router)
app.include_router(vente.router)
app.include_router(traitement.router)
app.include_router(utilisateur.router)
app.include_router(tresorerie.router)
app.include_router(rentabilite.router)


@app.get("/health", tags=["Systeme"])
def health():
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def page_connexion(request: Request):
    return templates.TemplateResponse(request, "connexion.html")


@app.get("/tableau", response_class=HTMLResponse, include_in_schema=False)
def page_tableau(request: Request):
    return templates.TemplateResponse(request, "tableau.html")


@app.get("/saisie", response_class=HTMLResponse, include_in_schema=False)
def page_saisie(request: Request):
    return templates.TemplateResponse(request, "saisie.html")


@app.get("/referentiel", response_class=HTMLResponse, include_in_schema=False)
def page_referentiel(request: Request):
    return templates.TemplateResponse(request, "referentiel.html")


@app.get("/vente", response_class=HTMLResponse, include_in_schema=False)
def page_vente(request: Request):
    return templates.TemplateResponse(request, "vente.html")


@app.get("/traitement", response_class=HTMLResponse, include_in_schema=False)
def page_traitement(request: Request):
    return templates.TemplateResponse(request, "traitement.html")


@app.get("/magasin", response_class=HTMLResponse, include_in_schema=False)
def page_magasin(request: Request):
    return templates.TemplateResponse(request, "magasin.html")


@app.get("/collecteur", response_class=HTMLResponse, include_in_schema=False)
def page_collecteur(request: Request):
    return templates.TemplateResponse(request, "collecteur.html")


@app.get("/utilisateurs", response_class=HTMLResponse, include_in_schema=False)
def page_utilisateurs(request: Request):
    return templates.TemplateResponse(request, "utilisateur.html")


@app.get("/tresorerie", response_class=HTMLResponse, include_in_schema=False)
def page_tresorerie(request: Request):
    return templates.TemplateResponse(request, "tresorerie.html")


@app.get("/collectes", response_class=HTMLResponse, include_in_schema=False)
def page_collectes(request: Request):
    return templates.TemplateResponse(request, "collectes.html")


@app.get("/livraisons", response_class=HTMLResponse, include_in_schema=False)
def page_livraisons(request: Request):
    return templates.TemplateResponse(request, "livraisons.html")


@app.get("/rentabilite", response_class=HTMLResponse, include_in_schema=False)
def page_rentabilite(request: Request):
    return templates.TemplateResponse(request, "rentabilite.html")

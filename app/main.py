from fastapi import FastAPI

from app.api.v1 import auth

app = FastAPI(
    title="ERP DML SARL",
    description="Negoce agro-industriel, logistique et transport - Douala",
    version="0.1.0",
)

app.include_router(auth.router)


@app.get("/health", tags=["Systeme"])
def health():
    return {"status": "ok"}

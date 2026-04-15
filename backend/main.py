from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import auth, accounts, products, logs, scheduler_router, settings as settings_router

app = FastAPI(title="imaotai_watcher", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api")
app.include_router(accounts.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(scheduler_router.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")


@app.get("/api/health")
def health():
    return {"status": "ok"}

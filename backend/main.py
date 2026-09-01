import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import auth, accounts, products, logs, scheduler_router, settings as settings_router
from init_db import init as init_db
from scheduler.main import start_scheduler, stop_scheduler
from utils.logger import get_logger

logger = get_logger(__name__)

# Populated by the Docker build (frontend built into backend/static/); absent
# in plain local dev where the frontend runs separately via `npm run dev`.
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing database...")
    init_db()
    logger.info("Database ready.")

    # The scheduler used to be a separate container coordinated over Redis;
    # now it's just a background thread inside this same process.
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="imaotai_watcher", version="1.0.0", lifespan=lifespan)

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


# Serve the built frontend (if present) so the whole app is one process on
# one port. Registered last so /api/* above always wins first. A plain
# StaticFiles(html=True) mount at "/" would swallow every path (including
# client-side routes like /accounts) and 404 them itself -- Starlette's
# html mode only serves index.html for directory-shaped paths, not a full
# SPA history-API fallback -- so instead: mount the hashed build assets at
# their real sub-path, and catch everything else with a handler that
# serves the matching static file if one exists, or index.html otherwise
# (letting React Router take over client-side routing).
if os.path.isdir(_STATIC_DIR):
    _assets_dir = os.path.join(_STATIC_DIR, "assets")
    if os.path.isdir(_assets_dir):
        app.mount("/assets", StaticFiles(directory=_assets_dir), name="static-assets")

    _static_dir_real = os.path.realpath(_STATIC_DIR)

    @app.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        candidate = os.path.realpath(os.path.join(_static_dir_real, full_path))
        if (
            full_path
            and candidate.startswith(_static_dir_real + os.sep)
            and os.path.isfile(candidate)
        ):
            return FileResponse(candidate)
        return FileResponse(os.path.join(_static_dir_real, "index.html"))
else:
    logger.info("未找到 static/ 目录，跳过挂载前端静态文件（本地开发时前端单独用 npm run dev 启动）")

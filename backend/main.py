from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

from backend.db import init_db
from backend.routers import lastfm, scrobbles, artistas, albums, stats, images, settings

app = FastAPI(title="Fiscal de Música")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(lastfm.router,    prefix="/api/lastfm",    tags=["lastfm"])
app.include_router(scrobbles.router, prefix="/api/scrobbles", tags=["scrobbles"])
app.include_router(artistas.router,  prefix="/api/artistas",  tags=["artistas"])
app.include_router(albums.router,    prefix="/api/albums",    tags=["albums"])
app.include_router(stats.router,     prefix="/api/stats",     tags=["stats"])
app.include_router(images.router,    prefix="/images",        tags=["images"])
app.include_router(settings.router,  prefix="/api/settings",  tags=["settings"])

FRONTEND = Path(__file__).parent.parent / "frontend"
app.mount("/css", StaticFiles(directory=str(FRONTEND / "css")), name="css")
app.mount("/js",  StaticFiles(directory=str(FRONTEND / "js")),  name="js")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def root():
    return FileResponse(str(FRONTEND / "index.html"))


@app.get("/{path:path}")
def spa(path: str):
    f = FRONTEND / path
    if f.exists() and f.suffix in {".html", ".css", ".js", ".png", ".jpg", ".svg", ".ico"}:
        return FileResponse(str(f))
    return FileResponse(str(FRONTEND / "index.html"))

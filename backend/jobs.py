"""Runner genérico de jobs em background.

Cada job é uma função `fn(job: Job)` registrada por nome. O runner mantém
um Job vivo por nome, com phase / current / total / last_log / error.
Frontend dispara via `POST /api/jobs/{name}/start` e faz polling em
`GET /api/jobs/{name}` até `phase in ('done','error')`.

Threading é OK aqui — operações são I/O bound (httpx, psycopg) e cada
worker abre suas próprias conexões via `get_db()`.
"""
import logging
import threading
from datetime import datetime
from typing import Callable

log = logging.getLogger(__name__)


class Job:
    def __init__(self, name: str, title: str):
        self.name = name
        self.title = title
        self.phase: str = "idle"           # idle | running | done | error
        self.current: int = 0
        self.total: int | None = None
        self.last_log: str = ""
        self.error: str | None = None
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self._lock = threading.Lock()

    def set(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                if k.startswith("_"):
                    continue
                setattr(self, k, v)

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "name": self.name,
                "title": self.title,
                "phase": self.phase,
                "current": self.current,
                "total": self.total,
                "last_log": self.last_log,
                "error": self.error,
                "started_at":  self.started_at.isoformat()  if self.started_at  else None,
                "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            }


_JOBS: dict[str, Job] = {}
_FUNCS: dict[str, Callable[[Job], None]] = {}
_REGISTRY_LOCK = threading.Lock()


def register(name: str, title: str, fn: Callable[[Job], None]) -> None:
    """Registra um job. Idempotente — sobrescreve se já existir."""
    _JOBS[name] = Job(name=name, title=title)
    _FUNCS[name] = fn


def start(name: str) -> Job:
    """Dispara o job em thread daemon. Levanta RuntimeError se já estiver rodando.
    Reinicia o estado a cada start (depois de done/error pode rodar de novo)."""
    if name not in _FUNCS:
        raise KeyError(name)

    with _REGISTRY_LOCK:
        job = _JOBS[name]
        if job.phase == "running":
            raise RuntimeError("Job já em andamento")
        job.set(
            phase="running",
            current=0,
            total=None,
            last_log="iniciando...",
            error=None,
            started_at=datetime.now(),
            finished_at=None,
        )

    fn = _FUNCS[name]

    def runner():
        try:
            fn(job)
            if job.phase == "running":
                job.set(phase="done", finished_at=datetime.now())
        except Exception as e:
            log.exception("job %s falhou", name)
            job.set(phase="error", error=str(e), finished_at=datetime.now())

    t = threading.Thread(target=runner, daemon=True, name=f"job-{name}")
    t.start()
    return job


def get(name: str) -> Job | None:
    return _JOBS.get(name)


def list_all() -> list[Job]:
    return list(_JOBS.values())

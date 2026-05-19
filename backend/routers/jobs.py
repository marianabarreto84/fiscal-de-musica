from fastapi import APIRouter, HTTPException

from backend import jobs

router = APIRouter()


@router.get("")
def list_jobs():
    """Lista todos os jobs registrados, com o estado da última execução."""
    return [j.to_dict() for j in jobs.list_all()]


@router.get("/{name}")
def get_job(name: str):
    j = jobs.get(name)
    if j is None:
        raise HTTPException(404, "Job não encontrado")
    return j.to_dict()


@router.post("/{name}/start")
def start_job(name: str):
    try:
        j = jobs.start(name)
        return j.to_dict()
    except KeyError:
        raise HTTPException(404, "Job não encontrado")
    except RuntimeError as e:
        raise HTTPException(409, str(e))

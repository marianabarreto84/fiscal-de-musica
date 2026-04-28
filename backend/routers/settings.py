from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.db import get_db

router = APIRouter()


class SettingBody(BaseModel):
    value: str | None = None


@router.get("/{key}")
def get_setting(key: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT value FROM musicas.config WHERE key = %s", (key,)
        ).fetchone()
    if row is None:
        raise HTTPException(404, "Configuração não encontrada")
    return {"key": key, "value": row["value"]}


@router.put("/{key}")
def set_setting(key: str, body: SettingBody):
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO musicas.config (key, value, updated_at)
            VALUES (%s, %s, now())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
            """,
            (key, body.value),
        )
    return {"key": key, "value": body.value}

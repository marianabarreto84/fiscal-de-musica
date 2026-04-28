from fastapi import APIRouter
from fastapi.responses import FileResponse, Response
from backend.config import IMAGES_DIR

router = APIRouter()

_PLACEHOLDER = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01'
    b'\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00'
    b'\x00\x0cIDATx\x9cc\x18\x18\x18\x00\x00\x00\x02\x00\x01'
    b'\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82'
)


@router.get("/{tipo}/{filename}")
def serve_image(tipo: str, filename: str):
    path = IMAGES_DIR / tipo / filename
    if path.exists():
        return FileResponse(str(path))
    return Response(content=_PLACEHOLDER, media_type="image/png")

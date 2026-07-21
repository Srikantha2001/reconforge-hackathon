from fastapi import APIRouter

from ..actors import ACTORS
from ..schemas import Actor

router = APIRouter(prefix="/api/actors", tags=["actors"])


@router.get("", response_model=list[Actor])
def list_actors():
    return ACTORS

from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..seed.generator import write_seed

router = APIRouter(prefix="/api/seed", tags=["seed"])

SEED_DIR = Path(__file__).resolve().parent.parent.parent / "data"


@router.get("/info")
def seed_info():
    ledger_path = SEED_DIR / "ledger.csv"
    statement_path = SEED_DIR / "statement.csv"
    if not ledger_path.exists() or not statement_path.exists():
        return {"exists": False, "ledger_columns": [], "statement_columns": []}

    import pandas as pd

    ledger_columns = list(pd.read_csv(ledger_path, nrows=0).columns)
    statement_columns = list(pd.read_csv(statement_path, nrows=0).columns)
    return {"exists": True, "ledger_columns": ledger_columns, "statement_columns": statement_columns}


@router.post("/generate")
def seed_generate():
    try:
        write_seed(SEED_DIR)
    except AssertionError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"status": "ok", "dir": str(SEED_DIR)}

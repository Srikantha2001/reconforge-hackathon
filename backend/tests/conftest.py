"""Test environment setup.

This module-level code (not a fixture body) runs when pytest loads this
conftest.py, which happens before any test module's `from app... import`
triggers Settings() to be constructed and cached — so these env vars are what
the app actually boots with for the whole test session.
"""
import os
import shutil
from pathlib import Path

TEST_DIR = Path(__file__).parent
TEST_DB_PATH = TEST_DIR / "test_reconforge.db"
TEST_UPLOAD_DIR = TEST_DIR / "test_uploads"

# Fresh DB file every test session.
if TEST_DB_PATH.exists():
    TEST_DB_PATH.unlink()
if TEST_UPLOAD_DIR.exists():
    shutil.rmtree(TEST_UPLOAD_DIR)

os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB_PATH}"
os.environ["LLM_PROVIDER"] = "stub"
os.environ["UPLOAD_DIR"] = str(TEST_UPLOAD_DIR)
os.environ["STP_THRESHOLD"] = "0.90"

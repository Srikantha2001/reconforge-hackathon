"""REPRODUCIBILITY TEST — the proof-of-determinism artefact (Law 4).

Runs the deterministic engine twice over the seed dataset and asserts the two
SHA-256 output hashes are identical. Same input, same output, every time — not
because we got lucky, but because the engine has no randomness. That is what a
financial control looks like.

Run:  python -m pytest backend/tests/test_reproducibility.py -v
Or:   python backend/tests/test_reproducibility.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.engine.runner import reconcile  # noqa: E402
from app.seed.generator import generate, load_aux  # noqa: E402


def run_engine_once():
    df_a, df_b, config = generate()
    result = reconcile(df_a, df_b, config, aux_data=load_aux())
    return result.output_hash, result


def test_reproducibility():
    print("\n" + "=" * 60)
    print("RECONOS REPRODUCIBILITY TEST")
    print("=" * 60)

    hash_1, r1 = run_engine_once()
    print(f"\nSide A rows: {r1.total_a} | Side B rows: {r1.total_b}")
    print(f"Matched: {r1.matched_count} | Open breaks: {r1.break_count} | "
          f"Explained: {len(r1.explained_breaks)}")
    print(f"Pass 1 hash: {hash_1}")

    hash_2, _ = run_engine_once()
    print(f"Pass 2 hash: {hash_2}")

    print("\n" + "=" * 60)
    if hash_1 == hash_2:
        print("REPRODUCIBILITY: PASS")
        print(f"   SHA256: {hash_1}")
        print("   Identical inputs produced identical hash across two runs.")
        print("   This is a financial control, not a software feature.")
    else:
        print("REPRODUCIBILITY: FAIL")
        print(f"   Hash 1: {hash_1}")
        print(f"   Hash 2: {hash_2}")
    print("=" * 60 + "\n")

    assert hash_1 == hash_2, f"DETERMINISM VIOLATION: {hash_1} != {hash_2}"


if __name__ == "__main__":
    test_reproducibility()

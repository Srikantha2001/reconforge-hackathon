"""Seed generator: must contain every break archetype + the 3-day drift
cluster, and must be reproducible."""
from app.seed.generator import (
    EXPECTED_ARCHETYPES,
    assert_all_archetypes_present,
    generate,
)
from app.engine.runner import reconcile


def test_seed_contains_all_archetypes_and_drift_cluster():
    df_a, df_b, config = generate()
    assert_all_archetypes_present(df_a, df_b)  # raises AssertionError if not


def test_seed_row_counts_in_expected_range():
    df_a, df_b, _config = generate()
    assert 60 <= len(df_a) <= 100
    assert 60 <= len(df_b) <= 100


def test_seed_is_reproducible():
    df_a1, df_b1, config = generate()
    df_a2, df_b2, _ = generate()
    r1 = reconcile(df_a1, df_b1, config)
    r2 = reconcile(df_a2, df_b2, config)
    assert r1.output_hash == r2.output_hash


def test_seed_archetype_set_matches_all_ten():
    assert len(EXPECTED_ARCHETYPES) == 10
    df_a, df_b, config = generate()
    result = reconcile(df_a, df_b, config)
    found = {b["archetype"] for b in result.breaks}
    assert EXPECTED_ARCHETYPES <= found

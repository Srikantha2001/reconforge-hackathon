"""Transform pipeline (P3) — registry pattern, null-safe, pure.

A config's ``transforms.side_a`` / ``transforms.side_b`` are ordered lists of
``{step, op, ...}`` dicts. ``TransformPipeline.apply`` runs them in step order
against a copy of the side's frame. Every op is null-safe: numeric work goes
through ``pd.to_numeric(errors="coerce")`` and string work through ``.astype(str)``
so a NaN or malformed cell never raises.

Available ops (mirrors config_schema.TRANSFORM_OPS):
  sign_flip, abs_value, upper_case, lower_case, strip, round2,
  strip_leading_zeros, date_normalise, compute_market_value,
  enrich_from_aux, corporate_action_adjust
"""
from __future__ import annotations

import re
from typing import Any, Callable, Dict, List

import pandas as pd

_REGISTRY: Dict[str, Callable[..., pd.DataFrame]] = {}


def _register(name: str):
    def deco(fn: Callable[..., pd.DataFrame]) -> Callable[..., pd.DataFrame]:
        _REGISTRY[name] = fn
        return fn

    return deco


# --- Condition parsing (sign_flip) -----------------------------------------
# Supports the single form the config uses: "<column> == '<value>'".
_COND_RE = re.compile(r"^\s*(\w+)\s*==\s*'([^']*)'\s*$")


def _condition_mask(df: pd.DataFrame, condition: str) -> pd.Series:
    m = _COND_RE.match(condition or "")
    if not m:
        return pd.Series(False, index=df.index)
    col, val = m.group(1), m.group(2)
    if col not in df.columns:
        return pd.Series(False, index=df.index)
    return df[col].astype(str) == val


# --- Ops -------------------------------------------------------------------
@_register("sign_flip")
def _sign_flip(df: pd.DataFrame, *, column: str, condition: str = "", aux=None, **_) -> pd.DataFrame:
    if column not in df.columns:
        return df
    mask = _condition_mask(df, condition)
    nums = pd.to_numeric(df[column], errors="coerce")
    df.loc[mask, column] = -nums[mask]
    return df


@_register("abs_value")
def _abs_value(df: pd.DataFrame, *, column: str, aux=None, **_) -> pd.DataFrame:
    if column in df.columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").abs()
    return df


@_register("upper_case")
def _upper_case(df: pd.DataFrame, *, column: str, aux=None, **_) -> pd.DataFrame:
    if column in df.columns:
        df[column] = df[column].astype(str).str.upper()
    return df


@_register("lower_case")
def _lower_case(df: pd.DataFrame, *, column: str, aux=None, **_) -> pd.DataFrame:
    if column in df.columns:
        df[column] = df[column].astype(str).str.lower()
    return df


@_register("strip")
def _strip(df: pd.DataFrame, *, column: str, aux=None, **_) -> pd.DataFrame:
    if column in df.columns:
        df[column] = df[column].astype(str).str.strip()
    return df


@_register("round2")
def _round2(df: pd.DataFrame, *, column: str, aux=None, **_) -> pd.DataFrame:
    if column in df.columns:
        df[column] = pd.to_numeric(df[column], errors="coerce").round(2)
    return df


@_register("strip_leading_zeros")
def _strip_leading_zeros(df: pd.DataFrame, *, column: str, aux=None, **_) -> pd.DataFrame:
    if column not in df.columns:
        return df

    def _strip(v: Any) -> str:
        s = str(v).strip()
        stripped = s.lstrip("0")
        return stripped if stripped else "0"  # keep a lone "0"

    df[column] = df[column].map(_strip)
    return df


@_register("date_normalise")
def _date_normalise(
    df: pd.DataFrame, *, column: str, input_format: str = None, aux=None, **_
) -> pd.DataFrame:
    if column not in df.columns:
        return df
    parsed = pd.to_datetime(df[column], format=input_format, errors="coerce")
    df[column] = parsed.dt.strftime("%Y-%m-%d")
    return df


@_register("compute_market_value")
def _compute_market_value(
    df: pd.DataFrame,
    *,
    quantity_col: str = "quantity",
    price_col: str = "price",
    output_col: str = "computed_market_value",
    aux=None,
    **_,
) -> pd.DataFrame:
    if quantity_col in df.columns and price_col in df.columns:
        qty = pd.to_numeric(df[quantity_col], errors="coerce")
        price = pd.to_numeric(df[price_col], errors="coerce")
        df[output_col] = (qty * price).round(2)
    return df


@_register("enrich_from_aux")
def _enrich_from_aux(
    df: pd.DataFrame,
    *,
    aux_alias: str,
    join_column: str,
    add_columns: List[str] = None,
    aux: Dict[str, pd.DataFrame] = None,
    **_,
) -> pd.DataFrame:
    aux = aux or {}
    if aux_alias not in aux or join_column not in df.columns:
        return df
    aux_df = aux[aux_alias]
    if join_column not in aux_df.columns:
        return df
    cols = [join_column] + [c for c in (add_columns or []) if c in aux_df.columns]
    df = df.merge(aux_df[cols], on=join_column, how="left")
    return df


@_register("corporate_action_adjust")
def _corporate_action_adjust(
    df: pd.DataFrame,
    *,
    isin_col: str = "isin",
    quantity_col: str = "quantity",
    date_col: str = "settlement_date",
    aux: Dict[str, pd.DataFrame] = None,
    **_,
) -> pd.DataFrame:
    """Multiply pre-ex-date quantities by the split ratio.

    A trade whose date is on or before a corporate action's ex_date is
    expressed in pre-split terms; multiply its quantity by the ratio so it
    lines up with post-split custody records. Implemented as an available op;
    the seed's POSITION config does not invoke it (TRD024 is handled as a
    position-control explained break instead — see runner).
    """
    aux = aux or {}
    ca = aux.get("corporate_actions")
    if ca is None or isin_col not in df.columns or quantity_col not in df.columns:
        return df
    for _, event in ca.iterrows():
        isin = event.get("isin")
        ex_date = str(event.get("ex_date", ""))
        try:
            ratio = float(event.get("ratio"))
        except (TypeError, ValueError):
            continue
        mask = df[isin_col].astype(str) == str(isin)
        if date_col in df.columns:
            mask &= df[date_col].astype(str) <= ex_date
        df.loc[mask, quantity_col] = (
            pd.to_numeric(df.loc[mask, quantity_col], errors="coerce") * ratio
        )
    return df


class TransformPipeline:
    """Applies an ordered transform list to one side's frame."""

    @staticmethod
    def apply(
        df: pd.DataFrame,
        transforms: List[Dict[str, Any]],
        aux_data: Dict[str, pd.DataFrame] = None,
    ) -> pd.DataFrame:
        out = df.copy()
        for t in sorted(transforms or [], key=lambda x: x.get("step", 0)):
            op = t.get("op")
            fn = _REGISTRY.get(op)
            if fn is None:
                continue
            kwargs = {k: v for k, v in t.items() if k not in ("step", "op")}
            out = fn(out, aux=aux_data or {}, **kwargs)
        return out

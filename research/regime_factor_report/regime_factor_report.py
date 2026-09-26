#!/usr/bin/env python3
"""Generate human-readable regime factor diagnostics from a long-format CSV.

Designed for files with columns:
alpha, dimension, state, samples, ic_mean, ic_std, ic_ir, win_rate[, t_stat, p_value]

`t_stat` / `p_value` are the Newey-West significance of the IC mean
(`sherpa.metrics.factor.ic_significance`). They drive the significance gate of
`04_regime_matrix.csv`: only alphas with |t_stat| >= --min-abs-t are eligible, and
eligible alphas are ranked by |IC_IR| (see QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md §3.1).

No third-party dependencies are required.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

REQUIRED_COLUMNS = [
    "alpha", "dimension", "state", "samples",
    "ic_mean", "ic_std", "ic_ir", "win_rate",
]

DEFAULT_STATE_ORDER = {
    "trend": ["ALL", "bear", "neutral", "bull"],
    "volatility": ["ALL", "low", "normal", "high"],
    "dispersion": ["ALL", "low", "normal", "high"],
    "liquidity": ["ALL", "starved", "normal", "high"],
}

NUMERIC_FIELDS = ["samples", "ic_mean", "ic_std", "ic_ir", "win_rate"]

# Optional significance columns produced by `conditional_ic_summary`. Older profile CSVs
# lack them; the significance gate then refuses to run unless --min-abs-t 0 is passed.
SIGNIFICANCE_COLUMNS = ["t_stat", "p_value"]

# Default significance gate for 04_regime_matrix.csv: |t| >= 3 (two-sided p ~ 0.0027).
# ~100 alphas x 12 states is ~1200 tests; at this cutoff pure luck yields ~3 false
# positives, versus ~55 at the classic |t| >= 2 (Harvey, Liu & Zhu 2016 argue for 3.0).
DEFAULT_MIN_ABS_T = 3.0


def parse_float(value: str) -> Optional[float]:
    if value is None or value.strip() == "":
        return None
    try:
        v = float(value)
    except ValueError:
        return None
    return v if math.isfinite(v) else None


def parse_int(value: str) -> int:
    if value is None or value.strip() == "":
        return 0
    try:
        return int(float(value))
    except ValueError:
        return 0


def fmt(value: Any) -> Any:
    """Format floats for stable, readable CSV output while preserving non-floats."""
    if isinstance(value, float):
        if not math.isfinite(value):
            return ""
        return f"{value:.8f}"
    if value is None:
        return ""
    return value


def quantile(values: Sequence[float], p: float) -> float:
    vals = sorted(v for v in values if v is not None and math.isfinite(v))
    if not vals:
        return float("nan")
    if len(vals) == 1:
        return vals[0]
    x = (len(vals) - 1) * p
    lo = math.floor(x)
    hi = math.ceil(x)
    if lo == hi:
        return vals[lo]
    return vals[lo] * (hi - x) + vals[hi] * (x - lo)


def median(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None and math.isfinite(v)]
    return statistics.median(vals) if vals else None


def mean(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None and math.isfinite(v)]
    return statistics.fmean(vals) if vals else None


def write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: Optional[List[str]] = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        if not rows:
            raise ValueError(f"Cannot infer columns for empty output: {path}")
        fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: fmt(row.get(k)) for k in fieldnames})


def load_rows(path: Path) -> Tuple[List[Dict[str, Any]], List[str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        columns = reader.fieldnames or []
        missing = [c for c in REQUIRED_COLUMNS if c not in columns]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(missing)}")

        rows: List[Dict[str, Any]] = []
        for lineno, raw in enumerate(reader, start=2):
            row: Dict[str, Any] = dict(raw)
            row["alpha"] = (raw.get("alpha") or "").strip()
            row["dimension"] = (raw.get("dimension") or "").strip()
            row["state"] = (raw.get("state") or "").strip()
            row["samples"] = parse_int(raw.get("samples", ""))
            for key in ["ic_mean", "ic_std", "ic_ir", "win_rate"]:
                row[key] = parse_float(raw.get(key, ""))
            for key in SIGNIFICANCE_COLUMNS:
                row[key] = parse_float(raw.get(key, "")) if key in columns else None
            row["_line"] = lineno
            rows.append(row)
    return rows, columns


def validate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    errors: List[str] = []
    warnings: List[str] = []
    seen = set()
    duplicate_keys = []
    for r in rows:
        key = (r["alpha"], r["dimension"], r["state"])
        if key in seen:
            duplicate_keys.append(key)
        seen.add(key)
        if not r["alpha"] or not r["dimension"] or not r["state"]:
            errors.append(f"Blank key field at input line {r['_line']}")
    if duplicate_keys:
        errors.append(f"Duplicate alpha/dimension/state keys: {len(duplicate_keys)}")

    missing_metric_rows = sum(
        1 for r in rows
        if r["samples"] <= 0 or any(r[k] is None for k in ["ic_mean", "ic_std", "ic_ir", "win_rate"])
    )
    if missing_metric_rows:
        warnings.append(f"{missing_metric_rows} rows have zero samples and/or missing metrics")

    return {
        "errors": errors,
        "warnings": warnings,
        "duplicate_key_count": len(duplicate_keys),
        "missing_metric_row_count": missing_metric_rows,
    }


def derive_thresholds(rows: List[Dict[str, Any]]) -> Dict[str, float]:
    non_all_abs_ir = [
        abs(r["ic_ir"]) for r in rows
        if r["state"] != "ALL" and r["ic_ir"] is not None
    ]
    by_pair: Dict[Tuple[str, str], List[float]] = defaultdict(list)
    for r in rows:
        if r["state"] != "ALL" and r["ic_ir"] is not None:
            by_pair[(r["alpha"], r["dimension"])].append(r["ic_ir"])
    spreads = [max(vs) - min(vs) for vs in by_pair.values() if len(vs) >= 2]

    return {
        "abs_ir_q25": quantile(non_all_abs_ir, 0.25),
        "abs_ir_q50": quantile(non_all_abs_ir, 0.50),
        "abs_ir_q75": quantile(non_all_abs_ir, 0.75),
        "abs_ir_q90": quantile(non_all_abs_ir, 0.90),
        "ir_spread_q25": quantile(spreads, 0.25),
        "ir_spread_q50": quantile(spreads, 0.50),
        "ir_spread_q75": quantile(spreads, 0.75),
        "ir_spread_q90": quantile(spreads, 0.90),
        "low_sample_abs": 100.0,
        "low_sample_fraction": 0.10,
    }


def state_order_for(dimension: str, states: Iterable[str]) -> List[str]:
    observed = list(dict.fromkeys(states))
    preferred = DEFAULT_STATE_ORDER.get(dimension, [])
    ordered = [s for s in preferred if s in observed]
    ordered += sorted(s for s in observed if s not in ordered)
    return ordered


def sample_warning(samples: int, all_samples: int, thresholds: Dict[str, float]) -> bool:
    if samples <= 0:
        return True
    if samples < thresholds["low_sample_abs"]:
        return True
    if all_samples > 0 and samples / all_samples < thresholds["low_sample_fraction"]:
        return True
    return False


def classify_dimension(
    state_rows: List[Dict[str, Any]], thresholds: Dict[str, float]
) -> Tuple[str, Dict[str, Any]]:
    valid = [r for r in state_rows if r["ic_ir"] is not None and r["samples"] > 0]
    if not valid:
        return "Data Quality Issue", {
            "sign_flip": False,
            "material_sign_flip": False,
            "ir_spread": None,
            "max_abs_ir": None,
            "median_abs_ir": None,
        }

    irs = [r["ic_ir"] for r in valid]
    abs_irs = [abs(v) for v in irs]
    spread = max(irs) - min(irs)
    sign_flip = any(v > 0 for v in irs) and any(v < 0 for v in irs)

    # Material reversal requires both sides to clear the lower-quartile strength
    # threshold, so tiny noise around zero does not count as a regime reversal.
    material = thresholds["abs_ir_q25"]
    material_pos = any(v >= material for v in irs)
    material_neg = any(v <= -material for v in irs)
    material_sign_flip = material_pos and material_neg

    max_abs = max(abs_irs)
    med_abs = statistics.median(abs_irs)
    q50 = thresholds["abs_ir_q50"]
    q75 = thresholds["abs_ir_q75"]
    spread_q25 = thresholds["ir_spread_q25"]
    spread_q75 = thresholds["ir_spread_q75"]

    if max_abs < q50:
        label = "Weak / Noise"
    elif material_sign_flip and spread >= spread_q75:
        label = "Regime-Reversal"
    elif max_abs >= q75 and spread >= spread_q75:
        label = "Conditional"
    elif spread <= spread_q25 and med_abs >= q50 and not sign_flip:
        label = "Stable"
    else:
        label = "Mixed / Moderate"

    return label, {
        "sign_flip": sign_flip,
        "material_sign_flip": material_sign_flip,
        "ir_spread": spread,
        "max_abs_ir": max_abs,
        "median_abs_ir": med_abs,
    }


def build_dimension_diagnostics(
    rows: List[Dict[str, Any]], thresholds: Dict[str, float]
) -> List[Dict[str, Any]]:
    groups: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        groups[(r["alpha"], r["dimension"])].append(r)

    out: List[Dict[str, Any]] = []
    for (alpha, dim), group in groups.items():
        all_row = next((r for r in group if r["state"] == "ALL"), None)
        states = [r for r in group if r["state"] != "ALL"]
        label, stats = classify_dimension(states, thresholds)
        valid = [r for r in states if r["ic_ir"] is not None and r["samples"] > 0]

        best = max(valid, key=lambda r: abs(r["ic_ir"])) if valid else None
        weakest = min(valid, key=lambda r: abs(r["ic_ir"])) if valid else None
        all_samples = all_row["samples"] if all_row else 0
        low_sample_states = [
            r["state"] for r in valid
            if sample_warning(r["samples"], all_samples, thresholds)
        ]
        out.append({
            "alpha": alpha,
            "dimension": dim,
            "classification": label,
            "baseline_ic_mean": all_row["ic_mean"] if all_row else None,
            "baseline_ic_ir": all_row["ic_ir"] if all_row else None,
            "baseline_win_rate": all_row["win_rate"] if all_row else None,
            "ir_spread": stats["ir_spread"],
            "max_abs_ir": stats["max_abs_ir"],
            "median_abs_ir": stats["median_abs_ir"],
            "sign_flip": stats["sign_flip"],
            "material_sign_flip": stats["material_sign_flip"],
            "best_state": best["state"] if best else "",
            "best_state_ic_mean": best["ic_mean"] if best else None,
            "best_state_ic_ir": best["ic_ir"] if best else None,
            "best_state_abs_ic_ir": abs(best["ic_ir"]) if best else None,
            "best_state_direction": (
                "original" if best and best["ic_mean"] is not None and best["ic_mean"] >= 0 else
                "invert" if best and best["ic_mean"] is not None else ""
            ),
            "best_state_samples": best["samples"] if best else 0,
            "best_state_low_sample": (
                sample_warning(best["samples"], all_samples, thresholds) if best else True
            ),
            "weakest_state": weakest["state"] if weakest else "",
            "low_sample_states": "|".join(low_sample_states),
            "valid_state_count": len(valid),
        })

    rank = {
        "Regime-Reversal": 0,
        "Conditional": 1,
        "Stable": 2,
        "Mixed / Moderate": 3,
        "Weak / Noise": 4,
        "Data Quality Issue": 5,
    }
    out.sort(key=lambda r: (
        rank.get(r["classification"], 99),
        -(r["ir_spread"] if r["ir_spread"] is not None else -1),
        r["alpha"], r["dimension"],
    ))
    return out


def build_factor_overview(
    rows: List[Dict[str, Any]], diagnostics: List[Dict[str, Any]], thresholds: Dict[str, float]
) -> List[Dict[str, Any]]:
    by_alpha_rows: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_alpha_diag: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_alpha_rows[r["alpha"]].append(r)
    for d in diagnostics:
        by_alpha_diag[d["alpha"]].append(d)

    out: List[Dict[str, Any]] = []
    for alpha, alpha_rows in by_alpha_rows.items():
        ds = by_alpha_diag[alpha]
        all_rows = [r for r in alpha_rows if r["state"] == "ALL" and r["ic_ir"] is not None]
        nonall = [r for r in alpha_rows if r["state"] != "ALL" and r["ic_ir"] is not None and r["samples"] > 0]
        best = max(nonall, key=lambda r: abs(r["ic_ir"])) if nonall else None

        labels = Counter(d["classification"] for d in ds)
        if labels["Data Quality Issue"] == len(ds) or not nonall:
            factor_class = "Data Quality Issue"
        elif labels["Regime-Reversal"] > 0:
            factor_class = "Regime-Reversal"
        elif labels["Conditional"] > 0:
            factor_class = "Conditional"
        elif labels["Weak / Noise"] == len(ds):
            factor_class = "Weak / Noise"
        elif labels["Stable"] == len(ds):
            factor_class = "Stable"
        else:
            factor_class = "Mixed / Moderate"

        # Best dimension by regime sensitivity (IR spread)
        best_dim = max(
            (d for d in ds if d["ir_spread"] is not None),
            key=lambda d: d["ir_spread"],
            default=None,
        )
        best_all_samples = 0
        if best:
            matching_all = next((
                r for r in alpha_rows
                if r["dimension"] == best["dimension"] and r["state"] == "ALL"
            ), None)
            best_all_samples = matching_all["samples"] if matching_all else 0

        out.append({
            "alpha": alpha,
            "factor_classification": factor_class,
            "baseline_ic_mean_median": median(r["ic_mean"] for r in all_rows),
            "baseline_ic_ir_median": median(r["ic_ir"] for r in all_rows),
            "baseline_win_rate_median": median(r["win_rate"] for r in all_rows),
            "baseline_ic_ir_range": (
                max(r["ic_ir"] for r in all_rows) - min(r["ic_ir"] for r in all_rows)
                if len(all_rows) >= 2 else 0.0 if len(all_rows) == 1 else None
            ),
            "best_regime_dimension": best["dimension"] if best else "",
            "best_regime_state": best["state"] if best else "",
            "best_regime_ic_mean": best["ic_mean"] if best else None,
            "best_regime_ic_ir": best["ic_ir"] if best else None,
            "best_regime_abs_ic_ir": abs(best["ic_ir"]) if best else None,
            "best_regime_direction": (
                "original" if best and best["ic_mean"] is not None and best["ic_mean"] >= 0 else
                "invert" if best and best["ic_mean"] is not None else ""
            ),
            "best_regime_samples": best["samples"] if best else 0,
            "best_regime_low_sample": (
                sample_warning(best["samples"], best_all_samples, thresholds) if best else True
            ),
            "most_sensitive_dimension": best_dim["dimension"] if best_dim else "",
            "max_ir_spread": best_dim["ir_spread"] if best_dim else None,
            "regime_reversal_dimensions": "|".join(
                sorted(d["dimension"] for d in ds if d["classification"] == "Regime-Reversal")
            ),
            "conditional_dimensions": "|".join(
                sorted(d["dimension"] for d in ds if d["classification"] == "Conditional")
            ),
            "low_sample_dimensions": "|".join(
                sorted(d["dimension"] for d in ds if d["low_sample_states"])
            ),
            "valid_regime_rows": len(nonall),
        })

    class_rank = {
        "Regime-Reversal": 0,
        "Conditional": 1,
        "Stable": 2,
        "Mixed / Moderate": 3,
        "Weak / Noise": 4,
        "Data Quality Issue": 5,
    }
    out.sort(key=lambda r: (
        class_rank.get(r["factor_classification"], 99),
        -(r["max_ir_spread"] if r["max_ir_spread"] is not None else -1),
        -(r["best_regime_abs_ic_ir"] if r["best_regime_abs_ic_ir"] is not None else -1),
        r["alpha"],
    ))
    return out


def build_leaderboard(rows: List[Dict[str, Any]], thresholds: Dict[str, float]) -> List[Dict[str, Any]]:
    all_samples_lookup = {
        (r["alpha"], r["dimension"]): r["samples"]
        for r in rows if r["state"] == "ALL"
    }
    out = []
    for r in rows:
        if r["state"] == "ALL" or r["ic_ir"] is None or r["samples"] <= 0:
            continue
        all_samples = all_samples_lookup.get((r["alpha"], r["dimension"]), 0)
        out.append({
            "dimension": r["dimension"],
            "state": r["state"],
            "alpha": r["alpha"],
            "samples": r["samples"],
            "sample_fraction_of_all": (r["samples"] / all_samples) if all_samples else None,
            "low_sample": sample_warning(r["samples"], all_samples, thresholds),
            "ic_mean": r["ic_mean"],
            "ic_std": r["ic_std"],
            "ic_ir": r["ic_ir"],
            "abs_ic_ir": abs(r["ic_ir"]),
            "win_rate": r["win_rate"],
            "t_stat": r.get("t_stat"),
            "abs_t_stat": abs(r["t_stat"]) if r.get("t_stat") is not None else None,
            "p_value": r.get("p_value"),
            "significant": is_significant(r.get("t_stat"), thresholds),
            "direction": "original" if r["ic_mean"] is not None and r["ic_mean"] >= 0 else "invert",
        })
    # Significant alphas first, then by |IC_IR|: significance is the gate, |IC_IR| the ranking key.
    out.sort(key=lambda r: (r["dimension"], r["state"], not r["significant"], -r["abs_ic_ir"], r["alpha"]))
    return out


def is_significant(t_stat: Optional[float], thresholds: Dict[str, float]) -> bool:
    """Significance gate: |t_stat| >= thresholds["min_abs_t"]; a gate of 0 disables it."""
    min_abs_t = thresholds.get("min_abs_t", 0.0)
    if min_abs_t <= 0:
        return True
    return t_stat is not None and abs(t_stat) >= min_abs_t


def build_regime_matrix(
    leaderboard: List[Dict[str, Any]],
    dimensions: Sequence[str],
    rows: List[Dict[str, Any]],
    thresholds: Dict[str, float],
    top_k: int = 3,
) -> List[Dict[str, Any]]:
    """Build a consolidated Dimension x State regime matrix picking the top K alphas per state.

    Selection rule (QUANT_RESEARCH_TO_LIVE_LIFECYCLE.md §3.1):
    1. gate: only alphas whose conditional IC mean is significant (|t_stat| >= min_abs_t);
    2. rank: eligible alphas by |IC_IR| descending, take the first K.
    A state with fewer than K significant alphas gets fewer entries -- insignificant
    alphas are never used to pad the list. `significant_count` records how many passed.
    """
    matrix: List[Dict[str, Any]] = []

    by_dim_state: Dict[Tuple[str, str], List[Dict[str, Any]]] = defaultdict(list)
    for r in leaderboard:
        by_dim_state[(r["dimension"], r["state"])].append(r)

    for dim in dimensions:
        dim_states = sorted(set(r["state"] for r in rows if r["dimension"] == dim and r["state"] != "ALL"))
        ordered_states = state_order_for(dim, dim_states)

        for state in ordered_states:
            all_candidates = by_dim_state.get((dim, state), [])
            candidates = [c for c in all_candidates if c["significant"]]
            top_alphas = candidates[:top_k]

            # State-level sample stats come from any alpha in the state (they share the same
            # bars), not from the top picks -- a state with no significant alpha still has samples.
            reference = all_candidates[0] if all_candidates else None
            state_samples = reference["samples"] if reference else 0
            state_fraction = reference["sample_fraction_of_all"] if reference else None
            state_low_sample = reference["low_sample"] if reference else True

            signed_alpha_list = []
            summary_list = []
            for item in top_alphas:
                prefix = "+" if item["direction"] == "original" else "-"
                signed_name = f"{prefix}{item['alpha']}"
                signed_alpha_list.append(signed_name)
                ir_str = f"{item['ic_ir']:.4f}" if item.get("ic_ir") is not None else "N/A"
                t_str = f"{item['t_stat']:.2f}" if item.get("t_stat") is not None else "N/A"
                wr_str = f"{item['win_rate']*100:.1f}%" if item.get("win_rate") is not None else "N/A"
                summary_list.append(f"{signed_name} (IR={ir_str}, t={t_str}, WR={wr_str})")

            row: Dict[str, Any] = {
                "dimension": dim,
                "state": state,
                "samples": state_samples,
                "sample_fraction_of_all": state_fraction,
                "low_sample": state_low_sample,
                "min_abs_t": thresholds.get("min_abs_t", 0.0),
                "candidate_count": len(all_candidates),
                "significant_count": len(candidates),
                "top_signed_alphas": " | ".join(signed_alpha_list),
                "top_alphas_summary": " | ".join(summary_list),
            }

            for i in range(1, top_k + 1):
                if i <= len(top_alphas):
                    item = top_alphas[i - 1]
                    prefix = "+" if item["direction"] == "original" else "-"
                    row[f"top{i}_alpha"] = item["alpha"]
                    row[f"top{i}_direction"] = item["direction"]
                    row[f"top{i}_signed_alpha"] = f"{prefix}{item['alpha']}"
                    row[f"top{i}_ic_ir"] = item["ic_ir"]
                    row[f"top{i}_abs_ic_ir"] = item["abs_ic_ir"]
                    row[f"top{i}_win_rate"] = item["win_rate"]
                    row[f"top{i}_ic_mean"] = item["ic_mean"]
                    row[f"top{i}_ic_std"] = item["ic_std"]
                    row[f"top{i}_t_stat"] = item["t_stat"]
                    row[f"top{i}_p_value"] = item["p_value"]
                    row[f"top{i}_low_sample"] = item["low_sample"]
                else:
                    row[f"top{i}_alpha"] = ""
                    row[f"top{i}_direction"] = ""
                    row[f"top{i}_signed_alpha"] = ""
                    row[f"top{i}_ic_ir"] = None
                    row[f"top{i}_abs_ic_ir"] = None
                    row[f"top{i}_win_rate"] = None
                    row[f"top{i}_ic_mean"] = None
                    row[f"top{i}_ic_std"] = None
                    row[f"top{i}_t_stat"] = None
                    row[f"top{i}_p_value"] = None
                    row[f"top{i}_low_sample"] = None

            matrix.append(row)

    return matrix


def build_dimension_wide(
    rows: List[Dict[str, Any]], dimension: str, diagnostics: List[Dict[str, Any]], thresholds: Dict[str, float]
) -> List[Dict[str, Any]]:
    dim_rows = [r for r in rows if r["dimension"] == dimension]
    by_alpha: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in dim_rows:
        by_alpha[r["alpha"]].append(r)
    diag_map = {(d["alpha"], d["dimension"]): d for d in diagnostics}
    states = state_order_for(dimension, (r["state"] for r in dim_rows))

    out = []
    for alpha, group in by_alpha.items():
        row: Dict[str, Any] = {"alpha": alpha}
        by_state = {r["state"]: r for r in group}
        all_samples = by_state.get("ALL", {}).get("samples", 0) if by_state.get("ALL") else 0
        for state in states:
            r = by_state.get(state)
            prefix = state
            for metric in ["samples", "ic_mean", "ic_std", "ic_ir", "win_rate"]:
                row[f"{prefix}_{metric}"] = r.get(metric) if r else None
            if state != "ALL":
                row[f"{prefix}_abs_ic_ir"] = abs(r["ic_ir"]) if r and r["ic_ir"] is not None else None
                row[f"{prefix}_direction"] = (
                    "original" if r and r["ic_mean"] is not None and r["ic_mean"] >= 0 else
                    "invert" if r and r["ic_mean"] is not None else ""
                )
                row[f"{prefix}_low_sample"] = sample_warning(r["samples"], all_samples, thresholds) if r else True
        d = diag_map.get((alpha, dimension), {})
        for key in [
            "classification", "ir_spread", "max_abs_ir", "median_abs_ir", "sign_flip",
            "material_sign_flip", "best_state", "best_state_ic_mean", "best_state_ic_ir",
            "best_state_abs_ic_ir", "best_state_direction", "best_state_samples",
            "best_state_low_sample", "weakest_state", "low_sample_states", "valid_state_count",
        ]:
            row[key] = d.get(key)
        out.append(row)

    class_rank = {
        "Regime-Reversal": 0,
        "Conditional": 1,
        "Stable": 2,
        "Mixed / Moderate": 3,
        "Weak / Noise": 4,
        "Data Quality Issue": 5,
    }
    out.sort(key=lambda r: (
        class_rank.get(r.get("classification"), 99),
        -(r.get("ir_spread") if r.get("ir_spread") is not None else -1),
        -(r.get("best_state_abs_ic_ir") if r.get("best_state_abs_ic_ir") is not None else -1),
        r["alpha"],
    ))
    return out


def make_dataset_summary(rows: List[Dict[str, Any]], validation: Dict[str, Any], thresholds: Dict[str, float]) -> List[Dict[str, Any]]:
    alphas = sorted(set(r["alpha"] for r in rows))
    dimensions = sorted(set(r["dimension"] for r in rows))
    metrics = [
        ("row_count", len(rows)),
        ("alpha_count", len(alphas)),
        ("dimension_count", len(dimensions)),
        ("dimensions", "|".join(dimensions)),
        ("missing_metric_rows", validation["missing_metric_row_count"]),
        ("duplicate_keys", validation["duplicate_key_count"]),
    ]
    for k, v in thresholds.items():
        metrics.append((f"threshold_{k}", v))
    for dim in dimensions:
        states = state_order_for(dim, [r["state"] for r in rows if r["dimension"] == dim])
        metrics.append((f"states_{dim}", "|".join(states)))
    return [{"metric": k, "value": v} for k, v in metrics]


def write_findings(
    path: Path,
    rows: List[Dict[str, Any]],
    overview: List[Dict[str, Any]],
    diagnostics: List[Dict[str, Any]],
    leaderboard: List[Dict[str, Any]],
    validation: Dict[str, Any],
    thresholds: Dict[str, float],
    regime_matrix: Optional[List[Dict[str, Any]]] = None,
) -> None:
    class_counts = Counter(r["factor_classification"] for r in overview)
    dim_class_counts = Counter(r["classification"] for r in diagnostics)

    # Sensitivity: do not filter low sample, but label it visibly.
    top_sens = sorted(
        (d for d in diagnostics if d["ir_spread"] is not None),
        key=lambda d: d["ir_spread"], reverse=True,
    )[:15]
    # Robust strength list excludes low-sample states.
    top_strength = sorted(
        (r for r in leaderboard if not r["low_sample"]),
        key=lambda r: r["abs_ic_ir"], reverse=True,
    )[:15]
    top_low_sample = sorted(
        (r for r in leaderboard if r["low_sample"]),
        key=lambda r: r["abs_ic_ir"], reverse=True,
    )[:10]

    missing_alphas = sorted(set(
        r["alpha"] for r in rows
        if r["samples"] <= 0 or r["ic_ir"] is None
    ))

    lines = []
    lines.append("# Important Findings\n")
    lines.append("This file is generated automatically from the input CSV. It highlights where a human reviewer should look first.\n")
    lines.append("## Dataset health\n")
    lines.append(f"- Rows: **{len(rows)}**; factors: **{len(set(r['alpha'] for r in rows))}**; dimensions: **{len(set(r['dimension'] for r in rows))}**.")
    lines.append(f"- Missing/zero-sample metric rows: **{validation['missing_metric_row_count']}**.")
    if missing_alphas:
        lines.append(f"- Factors with missing/zero-sample rows: **{', '.join(missing_alphas)}**.")
    lines.append("- A state is flagged `low_sample=True` if it has fewer than 100 samples or less than 10% of its dimension's ALL sample count.")
    lines.append("\n## Data-derived thresholds\n")
    lines.append(f"- |IC_IR| median: **{thresholds['abs_ir_q50']:.4f}**; upper quartile: **{thresholds['abs_ir_q75']:.4f}**.")
    lines.append(f"- IR-spread upper quartile: **{thresholds['ir_spread_q75']:.4f}**. This is used as the primary 'regime-sensitive' cutoff.")
    lines.append("- Material sign reversal requires meaningful IC_IR on both sides of zero; tiny sign changes near zero are not promoted to `Regime-Reversal`.\n")

    lines.append("## Factor-level classification counts\n")
    for name in ["Regime-Reversal", "Conditional", "Stable", "Mixed / Moderate", "Weak / Noise", "Data Quality Issue"]:
        lines.append(f"- {name}: **{class_counts.get(name, 0)}**")

    lines.append("\n## Dimension-level classification counts\n")
    for name in ["Regime-Reversal", "Conditional", "Stable", "Mixed / Moderate", "Weak / Noise", "Data Quality Issue"]:
        lines.append(f"- {name}: **{dim_class_counts.get(name, 0)}**")

    if regime_matrix:
        lines.append("\n## Regime strategy matrix (Top alphas per state)\n")
        lines.append(
            f"Only alphas with |t_stat| >= {thresholds.get('min_abs_t', 0.0):g} are eligible; eligible alphas "
            "are ranked by |IC_IR|. `Significant` = eligible / all alphas in the state.\n"
        )
        lines.append("| Dimension | State | Samples | Low sample? | Significant | Top 1 Alpha | Top 2 Alpha | Top 3 Alpha |")
        lines.append("|---|---|---:|:---:|---:|---|---|---|")

        def _cell(m: Dict[str, Any], i: int) -> str:
            if not m.get(f"top{i}_signed_alpha"):
                return "-"
            t = m.get(f"top{i}_t_stat")
            t_str = f", t={t:.2f}" if t is not None else ""
            return f"`{m[f'top{i}_signed_alpha']}` (IR={m[f'top{i}_ic_ir']:.4f}{t_str})"

        for m in regime_matrix:
            lines.append(
                f"| {m['dimension']} | {m['state']} | {m['samples']} | {m['low_sample']} | "
                f"{m['significant_count']}/{m['candidate_count']} | {_cell(m, 1)} | {_cell(m, 2)} | {_cell(m, 3)} |"
            )

    lines.append("\n## Most regime-sensitive factor/dimension pairs\n")
    lines.append("| Rank | Factor | Dimension | Class | IR spread | Best state | Best IC_IR | Best samples | Low sample? |")
    lines.append("|---:|---|---|---|---:|---|---:|---:|---|")
    for i, d in enumerate(top_sens, 1):
        lines.append(
            f"| {i} | {d['alpha']} | {d['dimension']} | {d['classification']} | "
            f"{d['ir_spread']:.4f} | {d['best_state']} | {d['best_state_ic_ir']:.4f} | "
            f"{d['best_state_samples']} | {d['best_state_low_sample']} |"
        )

    lines.append("\n## Strongest regime observations after excluding low-sample states\n")
    lines.append("| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Direction | Samples | Win rate |")
    lines.append("|---:|---|---|---|---:|---:|---|---:|---:|")
    for i, r in enumerate(top_strength, 1):
        lines.append(
            f"| {i} | {r['alpha']} | {r['dimension']} | {r['state']} | {r['ic_ir']:.4f} | "
            f"{r['abs_ic_ir']:.4f} | {r['direction']} | {r['samples']} | {r['win_rate']:.4f} |"
        )

    if top_low_sample:
        lines.append("\n## Strong-looking results that are low-sample (treat cautiously)\n")
        lines.append("| Rank | Factor | Dimension | State | IC_IR | |IC_IR| | Samples | Sample fraction |")
        lines.append("|---:|---|---|---|---:|---:|---:|---:|")
        for i, r in enumerate(top_low_sample, 1):
            frac = r["sample_fraction_of_all"] or 0.0
            lines.append(
                f"| {i} | {r['alpha']} | {r['dimension']} | {r['state']} | {r['ic_ir']:.4f} | "
                f"{r['abs_ic_ir']:.4f} | {r['samples']} | {frac:.4f} |"
            )

    lines.append("\n## Reading order\n")
    lines.append("1. Start with `01_factor_overview.csv` to decide which factors deserve attention.")
    lines.append("2. Open `02_dimension_diagnostics.csv` to see *which dimension* creates the regime dependency.")
    lines.append("3. Open the matching file in `dimensions/` to compare every state side by side.")
    lines.append("4. Use `04_regime_matrix.csv` as the unified Dimension x State matrix to configure multi-factor regime allocation.")
    lines.append("5. Use `03_regime_leaderboard.csv` or `leaderboards/` when asking 'what is strongest in this specific state?'.")
    lines.append("6. Always check `low_sample` before acting on an extreme IC/IR.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build human-readable regime alpha diagnostics.")
    parser.add_argument("input_csv", type=Path, help="Long-format regime alpha profile CSV")
    parser.add_argument("--output-dir", type=Path, default=Path("results"), help="Directory for generated results")
    parser.add_argument("--top-n", type=int, default=25, help="Rows per per-state leaderboard file")
    parser.add_argument("--matrix-top-k", type=int, default=3, help="Number of top alphas per regime state in 04_regime_matrix.csv")
    parser.add_argument(
        "--min-abs-t", type=float, default=DEFAULT_MIN_ABS_T,
        help="Significance gate for 04_regime_matrix.csv: only alphas with |t_stat| >= this are eligible (0 disables)",
    )
    args = parser.parse_args()

    rows, columns = load_rows(args.input_csv)
    missing_sig = [c for c in SIGNIFICANCE_COLUMNS if c not in columns]
    if args.min_abs_t > 0 and missing_sig:
        raise SystemExit(
            f"{args.input_csv} lacks significance columns {missing_sig}; it was produced before "
            "the significance test existed. Re-run run_alpha_regime_profile.py, or pass --min-abs-t 0 "
            "to build the report without the significance gate."
        )
    validation = validate(rows)
    if validation["errors"]:
        raise ValueError("Input validation failed: " + "; ".join(validation["errors"]))

    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    (output / "dimensions").mkdir(exist_ok=True)
    (output / "leaderboards").mkdir(exist_ok=True)

    thresholds = derive_thresholds(rows)
    thresholds["min_abs_t"] = args.min_abs_t
    diagnostics = build_dimension_diagnostics(rows, thresholds)
    overview = build_factor_overview(rows, diagnostics, thresholds)
    leaderboard = build_leaderboard(rows, thresholds)
    summary = make_dataset_summary(rows, validation, thresholds)

    write_csv(output / "00_dataset_summary.csv", summary)
    write_csv(output / "01_factor_overview.csv", overview)
    write_csv(output / "02_dimension_diagnostics.csv", diagnostics)
    write_csv(output / "03_regime_leaderboard.csv", leaderboard)

    dimensions = sorted(set(r["dimension"] for r in rows))
    matrix = build_regime_matrix(leaderboard, dimensions, rows, thresholds, top_k=args.matrix_top_k)
    write_csv(output / "04_regime_matrix.csv", matrix)

    for dim in dimensions:
        wide = build_dimension_wide(rows, dim, diagnostics, thresholds)
        write_csv(output / "dimensions" / f"{dim}_report.csv", wide)

    for dim in dimensions:
        states = sorted(set(r["state"] for r in rows if r["dimension"] == dim and r["state"] != "ALL"))
        for state in states:
            subset = [r for r in leaderboard if r["dimension"] == dim and r["state"] == state]
            subset.sort(key=lambda r: (not r["significant"], r["low_sample"], -r["abs_ic_ir"], r["alpha"]))
            if subset:
                write_csv(output / "leaderboards" / f"{dim}_{state}_top.csv", subset[: args.top_n])

    (output / "thresholds.json").write_text(json.dumps(thresholds, indent=2), encoding="utf-8")
    (output / "validation.json").write_text(json.dumps(validation, indent=2), encoding="utf-8")
    write_findings(output / "IMPORTANT_FINDINGS.md", rows, overview, diagnostics, leaderboard, validation, thresholds, regime_matrix=matrix)

    print(f"Generated report for {len(set(r['alpha'] for r in rows))} factors in: {output.resolve()}")
    if validation["warnings"]:
        print("Warnings:")
        for w in validation["warnings"]:
            print(f"  - {w}")


if __name__ == "__main__":
    main()

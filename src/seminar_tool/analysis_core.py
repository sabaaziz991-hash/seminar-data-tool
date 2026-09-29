"""Statistical core for the seminar study (single source of truth for every number in the paper).

Pure functions: they receive DataFrames and return plain dicts, so the same code serves
the paper (run_all.py) and the desktop tool.
"""
from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

IV_MAIN = "any_district_plus_appeal_media"
DV_MAIN = "court_intervention"

# Proceedings filed as ע"פ that are not appeals against a homicide conviction or sentence.
# Identified by reading the opening of each judgment.
NON_MERITS_APPEALS: dict[str, str] = {
    'ע"פ 4402/10': "ערעור פסלות שופט",
    'ע"פ 8058/10': "ערעור פסלות שופט",
    'ע"פ 9131/10': "ערעור פסלות שופט",
    'ע"פ 8129/13': "ערעור פסלות שופט",
    'ע"פ 1728/14': "ערעור פסלות שופט",
    'ע"פ 4290/14': "ערעור פסלות שופט",
    'ע"פ 414/15': "ערעור פסלות שופט",
    'ע"פ 5/17': "ערעור פסלות שופט",
    'ע"פ 5113/19': "ערעור פסלות שופט",
    'ע"פ 5647/19': "ערעור פסלות שופט",
    'ע"פ 1075/20': "ערעור פסלות שופט",
    'ע"פ 3652/15': "ערעור על הכרזה כבר-הסגרה",
    'ע"פ 8304/17': "ערעור על הכרזה כבר-הסגרה",
    'ע"פ 4576/18': "ערעור על הכרזה כבר-הסגרה",
    'ע"פ 1548/13': "ערעור לפי חוק נשיאת עונש מאסר במדינת אזרחותו של האסיר",
    'ע"פ 9112/15': "ערעור לפי חוק נשיאת עונש מאסר במדינת אזרחותו של האסיר",
    'ע"פ 5121/17': "ערעור על החלטה בעניין מועד שחרור של אסיר שנשפט בחו\"ל",
    'ע"פ 310/14': "ערעור על דחיית בקשה לפיצויים לאחר זיכוי",
    'ע"פ 2471/13': "ערעור על החלטה בעניין מועד הפקדת רישיון נהיגה",
}


def add_scope_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["non_merits_reason"] = out["case_number"].map(NON_MERITS_APPEALS).fillna("")
    out["merits_appeal"] = (out["non_merits_reason"] == "").astype(int)
    out["homicide_murder"] = (out["offense_group"] == "homicide_murder").astype(int)
    return out


# ---------------------------------------------------------------- 2x2 statistics
def _wilson(k: int, n: int, z: float = 1.959964) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return centre - half, centre + half


def two_by_two(df: pd.DataFrame, iv: str = IV_MAIN, dv: str = DV_MAIN) -> dict[str, Any]:
    d = df[[iv, dv]].dropna().astype(int)
    a = int(((d[iv] == 1) & (d[dv] == 1)).sum())  # exposed, event
    b = int(((d[iv] == 1) & (d[dv] == 0)).sum())
    c = int(((d[iv] == 0) & (d[dv] == 1)).sum())
    e = int(((d[iv] == 0) & (d[dv] == 0)).sum())
    n1, n0, n = a + b, c + e, a + b + c + e
    table = np.array([[a, b], [c, e]])
    chi2_y, p_y, _, expected = stats.chi2_contingency(table, correction=True)
    chi2_u, p_u, _, _ = stats.chi2_contingency(table, correction=False)
    or_f, p_fisher = stats.fisher_exact(table, alternative="two-sided")
    _, p_fisher_greater = stats.fisher_exact(table, alternative="greater")
    p1, p0 = a / n1, c / n0
    # Woolf CI for the odds ratio (Haldane correction only if a zero cell exists)
    cells = [a, b, c, e]
    adj = 0.5 if 0 in cells else 0.0
    aa, bb, cc, ee = (x + adj for x in cells)
    log_or = math.log((aa * ee) / (bb * cc))
    se = math.sqrt(1 / aa + 1 / bb + 1 / cc + 1 / ee)
    or_lo, or_hi = math.exp(log_or - 1.96 * se), math.exp(log_or + 1.96 * se)
    # Newcombe hybrid-score CI for the risk difference
    l1, u1 = _wilson(a, n1)
    l0, u0 = _wilson(c, n0)
    rd = p1 - p0
    rd_lo = rd - math.sqrt((p1 - l1) ** 2 + (u0 - p0) ** 2)
    rd_hi = rd + math.sqrt((u1 - p1) ** 2 + (p0 - l0) ** 2)
    phi = math.copysign(math.sqrt(chi2_u / n), a * e - b * c)
    return {
        "n": n, "n_exposed": n1, "n_unexposed": n0,
        "events_exposed": a, "events_unexposed": c, "events_total": a + c,
        "rate_exposed": p1, "rate_unexposed": p0,
        "rate_exposed_ci": _wilson(a, n1), "rate_unexposed_ci": _wilson(c, n0),
        "risk_difference": rd, "risk_difference_ci": (rd_lo, rd_hi),
        "odds_ratio": (a * e) / (b * c) if b * c else float("inf"),
        "odds_ratio_ci": (or_lo, or_hi),
        "chi2_yates": float(chi2_y), "p_chi2_yates": float(p_y),
        "chi2_uncorrected": float(chi2_u), "p_chi2_uncorrected": float(p_u),
        "fisher_p_two_sided": float(p_fisher), "fisher_p_one_sided_greater": float(p_fisher_greater),
        "phi": phi, "min_expected_count": float(expected.min()),
        "table": {"exposed": [a, b], "unexposed": [c, e]},
    }


# ---------------------------------------------------------------- regression
def logistic(df: pd.DataFrame, focal: str, dv: str = DV_MAIN, controls: list[str] | None = None) -> dict[str, Any]:
    import statsmodels.api as sm

    cols = [dv, focal] + (controls or [])
    d = df[cols].dropna().astype(float)
    X = sm.add_constant(d[[focal] + (controls or [])], has_constant="add")
    res = sm.Logit(d[dv], X).fit(disp=0)
    ci = res.conf_int().loc[focal]
    return {
        "n": int(len(d)), "events": int(d[dv].sum()), "controls": controls or [],
        "b": float(res.params[focal]), "se": float(res.bse[focal]),
        "odds_ratio": float(math.exp(res.params[focal])),
        "odds_ratio_ci": (float(math.exp(ci[0])), float(math.exp(ci[1]))),
        "p": float(res.pvalues[focal]),
        "pseudo_r2": float(res.prsquared), "llr_p": float(res.llr_pvalue),
        "all_terms": {k: {"or": float(math.exp(v)), "p": float(res.pvalues[k])} for k, v in res.params.items() if k != "const"},
    }


# ---------------------------------------------------------------- power
def power_analysis(n_exposed: int, n_unexposed: int, p_unexposed: float, p_exposed: float) -> dict[str, Any]:
    from statsmodels.stats.power import NormalIndPower
    from statsmodels.stats.proportion import proportion_effectsize

    pw = NormalIndPower()
    ratio = n_unexposed / n_exposed
    h_obs = proportion_effectsize(p_exposed, p_unexposed)
    power_two = pw.power(effect_size=h_obs, nobs1=n_exposed, alpha=0.05, ratio=ratio, alternative="two-sided")
    power_one = pw.power(effect_size=h_obs, nobs1=n_exposed, alpha=0.05, ratio=ratio, alternative="larger")
    h_mde = pw.solve_power(effect_size=None, nobs1=n_exposed, alpha=0.05, power=0.80, ratio=ratio, alternative="two-sided")
    # convert Cohen's h back to a proportion for the exposed group
    p_mde = math.sin((h_mde + 2 * math.asin(math.sqrt(p_unexposed))) / 2) ** 2
    n_needed = pw.solve_power(effect_size=h_obs, nobs1=None, alpha=0.05, power=0.80, ratio=ratio, alternative="two-sided")
    return {
        "cohens_h_observed": float(h_obs),
        "power_observed_two_sided": float(power_two),
        "power_observed_one_sided": float(power_one),
        "mde_h_80pct": float(h_mde),
        "mde_rate_exposed_80pct": float(p_mde),
        "mde_rate_difference_80pct": float(p_mde - p_unexposed),
        "n_exposed_needed_for_80pct_at_observed_effect": float(n_needed),
        "n_total_needed_for_80pct_at_observed_effect": float(n_needed * (1 + ratio)),
    }


# ---------------------------------------------------------------- descriptives
def rate_table(df: pd.DataFrame, by: str, dv: str = DV_MAIN) -> list[dict[str, Any]]:
    rows = []
    for key, g in df.groupby(by, dropna=False):
        k, n = int(g[dv].sum()), int(len(g))
        rows.append({"group": key if not isinstance(key, float) else int(key), "n": n, "events": k,
                     "rate": k / n if n else float("nan"), "ci": _wilson(k, n)})
    return rows


def salience_bucket(count: float) -> str:
    c = int(count)
    if c == 0:
        return "0"
    if c == 1:
        return "1"
    if c <= 4:
        return "2-4"
    return "5+"


def dose_response(df: pd.DataFrame, count_col: str = "district_plus_appeal_article_count") -> dict[str, Any]:
    d = df.copy()
    d["bucket"] = d[count_col].fillna(0).map(salience_bucket)
    order = ["0", "1", "2-4", "5+"]
    rows = {r["group"]: r for r in rate_table(d, "bucket")}
    table = [rows[b] for b in order if b in rows]
    # Cochran-Armitage test for trend (scores 0..3)
    score = {b: i for i, b in enumerate(order)}
    x = np.array([score[r["group"]] for r in table], dtype=float)
    n = np.array([r["n"] for r in table], dtype=float)
    k = np.array([r["events"] for r in table], dtype=float)
    p_bar = k.sum() / n.sum()
    t = np.sum(x * (k - n * p_bar))
    var = p_bar * (1 - p_bar) * (np.sum(n * x ** 2) - np.sum(n * x) ** 2 / n.sum())
    z = t / math.sqrt(var)
    among_covered = d[d[count_col].fillna(0) > 0]
    rho, p_rho = stats.spearmanr(among_covered[count_col], among_covered[DV_MAIN])
    return {"buckets": table, "cochran_armitage_z": float(z), "cochran_armitage_p": float(2 * (1 - stats.norm.cdf(abs(z)))),
            "spearman_count_vs_intervention_among_covered": float(rho), "spearman_p": float(p_rho),
            "n_covered": int(len(among_covered))}


def group_comparison_categorical(df: pd.DataFrame, col: str, iv: str = IV_MAIN) -> dict[str, Any]:
    ct = pd.crosstab(df[col], df[iv])
    chi2, p, dof, exp = stats.chi2_contingency(ct.values)
    use_fisher = ct.shape == (2, 2) and exp.min() < 5
    out = {"table": {str(k): [int(v) for v in row] for k, row in zip(ct.index, ct.values)},
           "columns": [int(c) for c in ct.columns], "chi2": float(chi2), "dof": int(dof), "p": float(p),
           "min_expected": float(exp.min())}
    if use_fisher:
        out["fisher_p"] = float(stats.fisher_exact(ct.values)[1])
    return out


def mann_whitney(df: pd.DataFrame, col: str, iv: str = IV_MAIN) -> dict[str, Any]:
    x1 = df.loc[df[iv] == 1, col].dropna().astype(float)
    x0 = df.loc[df[iv] == 0, col].dropna().astype(float)
    u, p = stats.mannwhitneyu(x1, x0, alternative="two-sided")
    r_rb = 2 * u / (len(x1) * len(x0)) - 1  # rank-biserial: >0 means exposed tends higher
    return {"n_exposed": int(len(x1)), "n_unexposed": int(len(x0)),
            "median_exposed": float(x1.median()), "median_unexposed": float(x0.median()),
            "iqr_exposed": (float(x1.quantile(.25)), float(x1.quantile(.75))),
            "iqr_unexposed": (float(x0.quantile(.25)), float(x0.quantile(.75))),
            "mean_exposed": float(x1.mean()), "mean_unexposed": float(x0.mean()),
            "U": float(u), "p": float(p), "rank_biserial": float(r_rb)}

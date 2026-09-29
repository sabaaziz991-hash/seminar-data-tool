"""All analyses of the paper, in the order of the findings chapter.

Wraps the paper's statistical core (analysis_core.py, copied unchanged) and adds the few
SPSS-style extras reported in the paper (Wald, Nagelkerke, Mantel-Haenszel, linear-by-linear,
Mann-Whitney z, standardised beta, SPSS power formula).

Input: a DataFrame in the format of study_dataset_final.csv.
Output: a JSON-friendly dict {sections: [...], values: {...}, golden: {...}}.
"""
from __future__ import annotations

import json
import math
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from . import analysis_core as core

# ------------------------------------------------------------------ labels
IV_LABELS = {
    "media_any": "בולטות מוקדמת (חלון מרכזי)",
    "media_district_any": "בולטות בשלב הערכאה הדיונית בלבד",
    "media_appeal_any": "בולטות בשלב הערעור בלבד",
    "media_primo_any": "מאגר עיתונות (Primo)",
    "media_combined_appeal_any": "שלב הערעור, Google או Primo",
}
# six components of the textual-complexity index (reasoning section), in the paper's order
COMPLEXITY_COMPONENTS = ["r_sentence_len", "r_sentence_len_p90", "r_word_len", "r_long_words_pct",
                         "r_very_long_words_pct", "r_paren_per_1000"]
COMPLEXITY_LABELS = {
    "r_sentence_len": "אורך משפט ממוצע",
    "r_sentence_len_p90": "אורך משפט באחוזון 90",
    "r_word_len": "אורך מילה ממוצע",
    "r_long_words_pct": "% מילים של 7+ אותיות",
    "r_very_long_words_pct": "% מילים של 9+ אותיות",
    "r_paren_per_1000": "סוגריים ל-1,000 מילים",
}
LENGTH_AND_COMPONENTS = ([("r_words", "אורך ההנמקה (מילים)", 0), ("words", "אורך פסק הדין כולו (מילים)", 0)]
                         + [(c, COMPLEXITY_LABELS[c], 2) for c in COMPLEXITY_COMPONENTS])
RELIEF_LABELS = {0: "ללא שינוי", 1: "הקלה בעונש", 2: "המרה לעבירה קלה", 3: "זיכוי", 4: "החזרה לערכאה", 5: "החמרה בעונש"}
BUCKET_LABELS = {0: "0 ידיעות", 1: "ידיעה אחת", 2: "2–4 ידיעות", 3: "5 ידיעות ומעלה"}

TEXT_COLUMNS = ("case_id", "case_number", "decision_date", "non_merits_reason", "reasoning_method")

# columns each part needs; a part is skipped (with a Hebrew note) if one is missing
NEEDS = {
    "desc": ["media_any", "intervention"],
    "main": ["media_any", "intervention"],
    "logit_adj": ["media_any", "intervention", "year_c", "homicide_murder"],
    "dose": ["media_count", "intervention"],
    "refs": ["media_any", "media_ref_any"],
}


# ------------------------------------------------------------------ formatting helpers
def fmt_p(p: float) -> str:
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return "—"
    if p < 0.001:
        return "<.001"
    return f"{p:.3f}".replace("0.", ".", 1) if p < 1 else "1.000"


def fmt(x: Any, d: int = 3) -> str:
    if x is None:
        return "—"
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return str(x)
    if math.isnan(xf):
        return "—"
    if math.isinf(xf):
        return "∞"
    s = f"{xf:,.{d}f}"
    return s.replace("-", "−")


def pct(k: int, n: int, d: int = 1) -> str:
    return f"{k}/{n} = {100 * k / n:.{d}f}%" if n else f"{k}/0"


def ci(lo: float, hi: float, d: int = 3, scale: float = 1.0) -> str:
    return f"[{fmt(lo * scale, d)}, {fmt(hi * scale, d)}]"


def _num(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    return df[cols].apply(pd.to_numeric, errors="coerce")


def has(df: pd.DataFrame, part: str) -> list[str]:
    """Return the list of missing columns for an analysis part."""
    return [c for c in NEEDS.get(part, []) if c not in df.columns]


# ------------------------------------------------------------------ building blocks
def table_2x2(df: pd.DataFrame, iv: str, dv: str) -> dict[str, Any]:
    """analysis_core.two_by_two + relative risk (SPSS 'cohort' estimate)."""
    r = core.two_by_two(df, iv=iv, dv=dv)
    a, n1, c, n0 = r["events_exposed"], r["n_exposed"], r["events_unexposed"], r["n_unexposed"]
    if a and c:
        rr = (a / n1) / (c / n0)
        se = math.sqrt(1 / a - 1 / n1 + 1 / c - 1 / n0)
        r["rr"], r["rr_ci"] = rr, (math.exp(math.log(rr) - 1.96 * se), math.exp(math.log(rr) + 1.96 * se))
    else:
        r["rr"], r["rr_ci"] = float("nan"), (float("nan"), float("nan"))
    return r


def logistic_full(df: pd.DataFrame, focal: str, dv: str, controls: list[str] | None = None) -> dict[str, Any]:
    """analysis_core.logistic + Wald, model chi-square and Nagelkerke R² as printed by SPSS."""
    import statsmodels.api as sm

    r = core.logistic(df, focal=focal, dv=dv, controls=controls)
    cols = [dv, focal] + (controls or [])
    d = df[cols].dropna().astype(float)
    X = sm.add_constant(d[[focal] + (controls or [])], has_constant="add")
    res = sm.Logit(d[dv], X).fit(disp=0)
    n = len(d)
    cox_snell = 1 - math.exp(2 * (res.llnull - res.llf) / n)
    r["wald"] = (r["b"] / r["se"]) ** 2
    r["model_chi2"] = float(2 * (res.llf - res.llnull))
    r["model_df"] = int(res.df_model)
    r["model_p"] = float(res.llr_pvalue)
    r["nagelkerke"] = cox_snell / (1 - math.exp(2 * res.llnull / n))
    cis = res.conf_int()
    r["terms"] = {k: {"b": float(res.params[k]), "se": float(res.bse[k]), "wald": float((res.params[k] / res.bse[k]) ** 2),
                      "p": float(res.pvalues[k]), "or": float(math.exp(res.params[k])),
                      "or_ci": (float(math.exp(cis.loc[k, 0])), float(math.exp(cis.loc[k, 1])))}
                  for k in res.params.index if k != "const"}
    return r


def mantel_haenszel(df: pd.DataFrame, iv: str, dv: str, strata: str) -> dict[str, Any]:
    from statsmodels.stats.contingency_tables import StratifiedTable

    tables = []
    for _, g in df.groupby(strata):
        d = g[[iv, dv]].dropna().astype(int)
        t = np.array([[((d[iv] == 1) & (d[dv] == 1)).sum(), ((d[iv] == 1) & (d[dv] == 0)).sum()],
                      [((d[iv] == 0) & (d[dv] == 1)).sum(), ((d[iv] == 0) & (d[dv] == 0)).sum()]], dtype=float)
        tables.append(t)
    st = StratifiedTable(tables)
    test = st.test_null_odds(correction=True)          # SPSS "Mantel-Haenszel" (continuity-corrected)
    bd = st.test_equal_odds(adjust=False)                # Breslow-Day
    lo, hi = st.oddsratio_pooled_confint()
    return {"chi2": float(test.statistic), "p": float(test.pvalue), "bd_chi2": float(bd.statistic), "bd_p": float(bd.pvalue),
            "or": float(st.oddsratio_pooled), "or_ci": (float(lo), float(hi))}


def mann_whitney_spss(df: pd.DataFrame, col: str, iv: str = "media_any") -> dict[str, Any]:
    """analysis_core.mann_whitney + the U and z exactly as SPSS prints them (smaller U, tie-corrected z)."""
    r = core.mann_whitney(df, col, iv=iv)
    x1 = df.loc[df[iv] == 1, col].dropna().astype(float)
    x0 = df.loc[df[iv] == 0, col].dropna().astype(float)
    n1, n0 = len(x1), len(x0)
    n = n1 + n0
    ranks = stats.rankdata(np.concatenate([x1, x0]))
    _, counts = np.unique(np.concatenate([x1, x0]), return_counts=True)
    tie = (counts ** 3 - counts).sum()
    u1 = ranks[:n1].sum() - n1 * (n1 + 1) / 2
    u = min(u1, n1 * n0 - u1)
    sd = math.sqrt(n1 * n0 / 12 * ((n + 1) - tie / (n * (n - 1))))
    r["U_spss"] = float(u)
    r["z"] = float((u - n1 * n0 / 2) / sd)
    return r


def ols_beta(df: pd.DataFrame, dv: str, focal: str, control: str) -> dict[str, Any]:
    import statsmodels.api as sm

    d = df[[dv, focal, control]].dropna().astype(float)
    res = sm.OLS(d[dv], sm.add_constant(d[[focal, control]])).fit()
    ci_ = res.conf_int()
    sd_y = d[dv].std()
    return {"n": int(len(d)), "b": float(res.params[focal]), "b_ci": (float(ci_.loc[focal, 0]), float(ci_.loc[focal, 1])),
            "beta": float(res.params[focal] * d[focal].std() / sd_y), "p": float(res.pvalues[focal]),
            "b_control": float(res.params[control]), "b_control_ci": (float(ci_.loc[control, 0]), float(ci_.loc[control, 1])),
            "beta_control": float(res.params[control] * d[control].std() / sd_y), "p_control": float(res.pvalues[control]),
            "r2": float(res.rsquared)}


def complexity_index(df: pd.DataFrame) -> dict[str, Any]:
    """Textual-complexity index as in section G of 02_analysis.sps:
    z-scores of the six components (sample SD) -> principal components on the correlation matrix ->
    first component; score = regression-method factor score (weights = eigenvector / sqrt(eigenvalue))."""
    X = df[COMPLEXITY_COMPONENTS].astype(float)
    Z = (X - X.mean()) / X.std()
    R = np.corrcoef(Z.values, rowvar=False)
    eigval, eigvec = np.linalg.eigh(R)
    lam, v = float(eigval[-1]), eigvec[:, -1]
    if v.sum() < 0:
        v = -v
    loadings = v * math.sqrt(lam)
    weights = v / math.sqrt(lam)
    score = pd.Series(Z.values @ weights, index=df.index)
    k, n = R.shape[0], len(Z)
    inv = np.linalg.inv(R)
    partial = -inv / np.sqrt(np.outer(np.diag(inv), np.diag(inv)))
    off = ~np.eye(k, dtype=bool)
    kmo = float((R[off] ** 2).sum() / ((R[off] ** 2).sum() + (partial[off] ** 2).sum()))
    bart = float(-(n - 1 - (2 * k + 5) / 6) * math.log(np.linalg.det(R)))
    bart_df = k * (k - 1) // 2
    alpha = float(k / (k - 1) * (1 - Z.var().sum() / Z.sum(axis=1).var()))
    return {"score": score, "eigenvalue": lam, "eigenvalues": sorted(eigval.tolist(), reverse=True), "var_pct": 100 * lam / k, "loadings": loadings.tolist(),
            "weights": weights.tolist(), "kmo": kmo, "bartlett_chi2": bart, "bartlett_df": bart_df,
            "bartlett_p": float(stats.chi2.sf(bart, bart_df)), "alpha": alpha}


def power_spss(p1: float, p0: float, n1: int, n0: int) -> dict[str, float]:
    """Same formulas as section H of 02_analysis.sps (two-proportion z test, Cohen's h)."""
    z_a2, z_a1, z_b = 1.959964, 1.644854, 0.841621
    h = 2 * math.asin(math.sqrt(p1)) - 2 * math.asin(math.sqrt(p0))
    n_eff = n1 * n0 / (n1 + n0)
    z = abs(h) * math.sqrt(n_eff)
    power_2s = stats.norm.cdf(z - z_a2) + stats.norm.cdf(-z - z_a2)
    power_1s = stats.norm.cdf(z - z_a1)
    h_mde = (z_a2 + z_b) / math.sqrt(n_eff)
    p1_mde = math.sin((h_mde + 2 * math.asin(math.sqrt(p0))) / 2) ** 2
    n1_needed = ((z_a2 + z_b) / h) ** 2 * (1 + n1 / n0) if h else float("inf")
    h_mde_1s = (z_a1 + z_b) / math.sqrt(n_eff)
    p1_mde_1s = math.sin((h_mde_1s + 2 * math.asin(math.sqrt(p0))) / 2) ** 2
    n1_needed_1s = ((z_a1 + z_b) / h) ** 2 * (1 + n1 / n0) if h else float("inf")
    return {"h": h, "power_2s": float(power_2s), "power_1s": float(power_1s), "h_mde": h_mde, "p1_mde": p1_mde,
            "n1_needed": n1_needed, "n_total_needed": n1_needed * (1 + n0 / n1),
            "h_mde_1s": h_mde_1s, "p1_mde_1s": p1_mde_1s, "n1_needed_1s": n1_needed_1s}


def chi2_plain(df: pd.DataFrame, row: str, col: str) -> dict[str, Any]:
    ct = pd.crosstab(df[row], df[col])
    chi2, p, dof, _ = stats.chi2_contingency(ct.values, correction=False)
    return {"chi2": float(chi2), "p": float(p), "df": int(dof)}


# ------------------------------------------------------------------ the full report
class Report:
    def __init__(self) -> None:
        self.sections: list[dict[str, Any]] = []
        self.values: dict[str, float] = {}

    def section(self, sid: str, title: str, help_text: str) -> dict[str, Any]:
        s = {"id": sid, "title": title, "help": help_text, "blocks": []}
        self.sections.append(s)
        return s

    @staticmethod
    def table(sec: dict[str, Any], columns: list[str], rows: list[list[Any]], caption: str = "") -> None:
        sec["blocks"].append({"type": "table", "caption": caption, "columns": columns, "rows": rows})

    @staticmethod
    def note(sec: dict[str, Any], text: str, kind: str = "info") -> None:
        sec["blocks"].append({"type": "note", "text": text, "kind": kind})

    def put(self, key: str, value: Any) -> None:
        try:
            self.values[key] = float(value)
        except (TypeError, ValueError):
            pass

    def put_2x2(self, prefix: str, r: dict[str, Any]) -> None:
        self.put(f"{prefix}.a", r["events_exposed"]); self.put(f"{prefix}.n1", r["n_exposed"])
        self.put(f"{prefix}.c", r["events_unexposed"]); self.put(f"{prefix}.n0", r["n_unexposed"])
        self.put(f"{prefix}.n", r["n"])
        self.put(f"{prefix}.chi2", r["chi2_uncorrected"]); self.put(f"{prefix}.p", r["p_chi2_uncorrected"])
        self.put(f"{prefix}.fisher2", r["fisher_p_two_sided"]); self.put(f"{prefix}.fisher1", r["fisher_p_one_sided_greater"])
        self.put(f"{prefix}.phi", r["phi"]); self.put(f"{prefix}.or", r["odds_ratio"])
        self.put(f"{prefix}.or_lo", r["odds_ratio_ci"][0]); self.put(f"{prefix}.or_hi", r["odds_ratio_ci"][1])


def _row_2x2(label: str, r: dict[str, Any], fisher_main: bool = False) -> list[str]:
    test = f"χ²={fmt(r['chi2_uncorrected'])}, p={fmt_p(r['p_chi2_uncorrected'])}"
    fisher = f"דו-צ' p={fmt_p(r['fisher_p_two_sided'])}; חד-צ' p={fmt_p(r['fisher_p_one_sided_greater'])}"
    if fisher_main or r["min_expected_count"] < 5:
        test = "Fisher (שכיחות צפויה < 5)"
    return [label, pct(r["events_exposed"], r["n_exposed"]), pct(r["events_unexposed"], r["n_unexposed"]),
            test, fisher, f"{fmt(r['odds_ratio'])} {ci(*r['odds_ratio_ci'])}"]


@contextmanager
def guarded(rep: "Report", sec: dict[str, Any]):
    """If one analysis cannot be computed on a user's file, show a Hebrew note instead of failing everything."""
    try:
        yield
    except Exception as exc:  # noqa: BLE001
        rep.note(sec, f"לא ניתן היה לחשב חלק זה על הנתונים ({type(exc).__name__}: {exc}).", "warn")


ROB_COLUMNS = ["בדיקה", "עם בולטות (התערבות)", "ללא בולטות (התערבות)", "מבחן (דו-צדדי)", "p חד-צדדי (Fisher)", "OR [95% CI]"]


def _rob_row(label: str, r: dict[str, Any]) -> list[str]:
    """Row of Table 4: two-sided test (χ² + Fisher, or Fisher alone when an expected count is < 5), one-sided Fisher."""
    if r["min_expected_count"] < 5:
        test = f"Fisher p={fmt_p(r['fisher_p_two_sided'])} (שכיחות צפויה < 5)"
    else:
        test = f"χ²(1)={fmt(r['chi2_uncorrected'])}, p={fmt_p(r['p_chi2_uncorrected'])}; Fisher דו-צ' p={fmt_p(r['fisher_p_two_sided'])}"
    return [label, pct(r["events_exposed"], r["n_exposed"]), pct(r["events_unexposed"], r["n_unexposed"]),
            test, fmt_p(r["fisher_p_one_sided_greater"]), f"{fmt(r['odds_ratio'])} {ci(*r['odds_ratio_ci'])}"]


def run_all(df_in: pd.DataFrame, extras: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run every analysis. `extras` may hold study-only tables (media refs, media items) for descriptive checks."""
    extras = extras or {}
    rep = Report()
    df = df_in.copy()
    numeric_cols = [c for c in df.columns if c not in TEXT_COLUMNS]
    for c in numeric_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "merits_appeal" not in df.columns:
        df["merits_appeal"] = 1
    full = df
    main = df[df["merits_appeal"] == 1].copy()
    rep.put("desc.n_main", len(main)); rep.put("desc.n_full", len(full))

    # ---------------------------------------------------------------- A. sample description
    sec = rep.section("desc", f"תיאור המדגם (N={len(main)})",
                      "כמה תיקים יש בכל קבוצה: סוג עבירה, בולטות תקשורתית, מספר ידיעות ותוצאת הערעור.")
    with guarded(rep, sec):
        rows = [["תיקים במדגם הניתוח (ערעורים לגופו)", f"{len(main)}"],
                ["תיקים בקורפוס המלא (כולל הליכים שהוחרגו)", f"{len(full)}"]]
        if "homicide_murder" in main:
            m = int((main.homicide_murder == 1).sum())
            rows.append(["רצח או ניסיון לרצח / המתה אחרת", f"{m} ({100*m/len(main):.1f}%) / {len(main)-m} ({100*(len(main)-m)/len(main):.1f}%)"])
            rep.put("desc.murder_n", m)
        k = int((main.media_any == 1).sum())
        rows.append(["עם בולטות מוקדמת / ללא", f"{k} ({100*k/len(main):.1f}%) / {len(main)-k} ({100*(len(main)-k)/len(main):.1f}%)"])
        rep.put("desc.media_n", k)
        if "media_count" in main:
            mc = main.media_count.fillna(0)
            rows.append(["ידיעות: סך הכול, ממוצע, ס\"ת, מקסימום",
                         f"{int(mc.sum())}; M={mc.mean():.3f}; SD={mc.std():.3f}; מקס' {int(mc.max())}"])
            rep.put("desc.items_total", mc.sum()); rep.put("desc.items_mean", mc.mean())
            rep.put("desc.items_sd", mc.std()); rep.put("desc.items_max", mc.max())
        if {"media_district_count", "media_appeal_count"} <= set(main.columns):
            rows.append(["ידיעות בשלב הערכאה הדיונית / בשלב הערעור",
                         f"{int(main.media_district_count.sum())} / {int(main.media_appeal_count.sum())}"])
            rep.put("desc.items_district", main.media_district_count.sum()); rep.put("desc.items_appeal", main.media_appeal_count.sum())
        if "media_bucket" in main:
            vc = main.media_bucket.value_counts()
            rows.append(["קבוצות מספר ידיעות", "; ".join(f"{BUCKET_LABELS.get(int(b), b)}: {int(vc.get(b, 0))}" for b in [0, 1, 2, 3])])
            for b in (1, 2, 3):
                rep.put(f"desc.bucket_{b}", vc.get(b, 0))
        iv_n = int((main.intervention == 1).sum())
        rows.append(["התערבות בית המשפט העליון", f"{iv_n} ({100*iv_n/len(main):.1f}%)"])
        rep.put("desc.intervention_n", iv_n)
        if "relief_type" in main:
            vc = main.relief_type.value_counts()
            rows.append(["סוג ההתערבות", "; ".join(f"{RELIEF_LABELS[c]}: {int(vc.get(c, 0))}" for c in [1, 2, 3, 4, 5] if vc.get(c, 0))])
            for c in (1, 2, 3, 5):
                rep.put(f"desc.relief_{c}", vc.get(c, 0))
        rep.table(sec, ["מדד", "ערך"], rows)
        bal = []
        for key, col, label in (("offense", "homicide_murder", "סוג עבירה"), ("timeline", "timeline_clean", "ציר זמן ודאי"), ("year", "year", "שנת ההכרעה")):
            if col in main and main[col].nunique() > 1:
                r = chi2_plain(main, col, "media_any")
                bal.append([label, f"χ²({r['df']})={fmt(r['chi2'])}", fmt_p(r["p"])])
                rep.put(f"balance.{key}.chi2", r["chi2"]); rep.put(f"balance.{key}.p", r["p"])
        if bal:
            rep.table(sec, ["משתנה", "χ²", "p"], bal, "איזון בין תיקים עם בולטות ובלעדיה")

    # ---------------------------------------------------------------- B. main hypothesis
    sec = rep.section("main", "בדיקת ההשערה: בולטות תקשורתית והתערבות",
                      "האם שיעור ההתערבות גבוה יותר בתיקים שסוקרו לפני פסק הדין? טבלת 2×2 ומבחנים.")
    with guarded(rep, sec):
        r = table_2x2(main, "media_any", "intervention")
        t = r["table"]
        rep.table(sec, ["", "התערבות", "ללא התערבות", "סה\"כ", "שיעור התערבות [95% CI]"], [
            ["עם בולטות", t["exposed"][0], t["exposed"][1], r["n_exposed"],
             f"{100*r['rate_exposed']:.1f}% {ci(*r['rate_exposed_ci'], d=1, scale=100)}"],
            ["ללא בולטות", t["unexposed"][0], t["unexposed"][1], r["n_unexposed"],
             f"{100*r['rate_unexposed']:.1f}% {ci(*r['rate_unexposed_ci'], d=1, scale=100)}"],
        ], "טבלת 2×2 (מדגם מרכזי)")
        rep.table(sec, ["מבחן / מדד", "ערך"], [
            ["הפרש שיעורים (נק' אחוז) [95% CI]", f"{fmt(100*r['risk_difference'], 1)} {ci(*r['risk_difference_ci'], d=1, scale=100)}"],
            ["Pearson χ²(1)", f"{fmt(r['chi2_uncorrected'], 3)}, p={fmt_p(r['p_chi2_uncorrected'])}"],
            ["χ² עם תיקון רציפות (Yates)", f"{fmt(r['chi2_yates'])}, p={fmt_p(r['p_chi2_yates'])}"],
            ["מבחן Fisher המדויק", f"דו-צדדי p={fmt_p(r['fisher_p_two_sided'])}; חד-צדדי p={fmt_p(r['fisher_p_one_sided_greater'])}"],
            ["φ (גודל אפקט)", fmt(r["phi"], 3)],
            ["יחס סיכויים OR [95% CI]", f"{fmt(r['odds_ratio'], 3)} {ci(*r['odds_ratio_ci'], d=3)}"],
            ["סיכון יחסי RR [95% CI]", f"{fmt(r['rr'])} {ci(*r['rr_ci'])}"],
            ["שכיחות צפויה מינימלית", fmt(r["min_expected_count"])],
        ], "מבחנים")
        rep.put_2x2("main", r)
        rep.put("main.rate1_pct", 100 * r["rate_exposed"]); rep.put("main.rate0_pct", 100 * r["rate_unexposed"])
        rep.put("main.rate1_lo_pct", 100 * r["rate_exposed_ci"][0]); rep.put("main.rate1_hi_pct", 100 * r["rate_exposed_ci"][1])
        rep.put("main.rate0_lo_pct", 100 * r["rate_unexposed_ci"][0]); rep.put("main.rate0_hi_pct", 100 * r["rate_unexposed_ci"][1])
        rep.put("main.rd_pct", 100 * r["risk_difference"])
        rep.put("main.rd_lo_pct", 100 * r["risk_difference_ci"][0]); rep.put("main.rd_hi_pct", 100 * r["risk_difference_ci"][1])
        rep.put("main.yates", r["chi2_yates"]); rep.put("main.p_yates", r["p_chi2_yates"])
        rep.put("main.p_chi2", r["p_chi2_uncorrected"])
        rep.put("main.rr", r["rr"]); rep.put("main.rr_lo", r["rr_ci"][0]); rep.put("main.rr_hi", r["rr_ci"][1])
        rep.put("main.min_expected", r["min_expected_count"])
        main_rates = (r["rate_exposed"], r["rate_unexposed"], r["n_exposed"], r["n_unexposed"])

    # ---------------------------------------------------------------- C. logistic regression
    sec = rep.section("logit", "רגרסיה לוגיסטית",
                      "אותה שאלה במודל רגרסיה: לפני ואחרי בקרה על שנת ההכרעה וסוג העבירה (רצח או ניסיון לרצח / המתה אחרת).")
    with guarded(rep, sec):
        models = [("unadj", "ללא בקרות", None)]
        if not has(main, "logit_adj"):
            models.append(("adj", "בבקרת שנה וסוג עבירה", ["year_c", "homicide_murder"]))
        else:
            rep.note(sec, "המודל המתוקנן דולג: חסרות עמודות " + ", ".join(has(main, "logit_adj")), "warn")
        term_labels = {"media_any": "בולטות מוקדמת", "year_c": "שנה (ממורכזת ל-2015)", "homicide_murder": "רצח או ניסיון לרצח (לעומת המתה אחרת)"}
        rows = []
        for key, label, controls in models:
            lr = logistic_full(main, "media_any", "intervention", controls)
            for term, tr in lr["terms"].items():
                rows.append([label, term_labels.get(term, term), fmt(tr["b"], 3), fmt(tr["se"], 3), fmt(tr["wald"]),
                             fmt_p(tr["p"]), f"{fmt(tr['or'], 3)} {ci(*tr['or_ci'])}"])
            rows.append([label, "המודל כולו", f"χ²({lr['model_df']})={fmt(lr['model_chi2'])}", "", "", fmt_p(lr["model_p"]),
                         f"Nagelkerke R²={fmt(lr['nagelkerke'], 3)}"])
            p = f"logit.{key}"
            rep.put(f"{p}.b", lr["b"]); rep.put(f"{p}.se", lr["se"]); rep.put(f"{p}.wald", lr["wald"]); rep.put(f"{p}.p", lr["p"])
            rep.put(f"{p}.or", lr["odds_ratio"]); rep.put(f"{p}.or_lo", lr["odds_ratio_ci"][0]); rep.put(f"{p}.or_hi", lr["odds_ratio_ci"][1])
            rep.put(f"{p}.model_chi2", lr["model_chi2"]); rep.put(f"{p}.model_p", lr["model_p"]); rep.put(f"{p}.nagelkerke", lr["nagelkerke"])
            if key == "adj":
                rep.put(f"{p}.year_or", lr["terms"]["year_c"]["or"]); rep.put(f"{p}.year_p", lr["terms"]["year_c"]["p"])
                rep.put(f"{p}.murder_or", lr["terms"]["homicide_murder"]["or"]); rep.put(f"{p}.murder_p", lr["terms"]["homicide_murder"]["p"])
        rep.table(sec, ["מודל", "משתנה", "B", "SE", "Wald", "p", "OR [95% CI]"], rows)

    # ---------------------------------------------------------------- D. robustness
    sec = rep.section("robust", "בדיקות חוסן",
                      "האם התוצאה נשמרת כשמשנים את הגדרת הבולטות, את המשתנה התלוי או את המדגם?")
    with guarded(rep, sec):
        rows = []
        r0 = table_2x2(main, "media_any", "intervention")
        rows.append(_rob_row(f"ניתוח מרכזי (N={len(main)})", r0))
        if "media_district_any" in main and main.media_district_any.nunique() > 1:
            # trial-court stage: only appeals for which a trial-court window could be computed (media_district_window=1)
            sub = main[main.media_district_window == 1] if "media_district_window" in main else main
            rr_ = table_2x2(sub, "media_district_any", "intervention")
            rows.append(_rob_row(f"סיקור בשלב הערכאה הדיונית בלבד (n={len(sub)})", rr_)); rep.put_2x2("rob.district", rr_)
        for key, iv, label in (("appeal", "media_appeal_any", "סיקור בשלב הערעור בלבד"),
                               ("primo", "media_primo_any", "מאגר עיתונות (Primo)"),
                               ("combined", "media_combined_appeal_any", "שלב הערעור, Google או Primo")):
            if iv in main and main[iv].nunique() > 1:
                rr_ = table_2x2(main, iv, "intervention")
                rows.append(_rob_row(label, rr_)); rep.put_2x2(f"rob.{key}", rr_)
        if "defendant_helped" in main:
            rr_ = table_2x2(main, "media_any", "defendant_helped")
            rows.append(_rob_row("משתנה תלוי: הקלה עם הנאשם", rr_)); rep.put_2x2("rob.helped", rr_)
        if "timeline_clean" in main:
            sub = main[main.timeline_clean == 1]
            if len(sub) and sub.media_any.nunique() > 1:
                rr_ = table_2x2(sub, "media_any", "intervention")
                rows.append(_rob_row(f"ציר זמן ודאי (n={len(sub)})", rr_)); rep.put_2x2("rob.timeline", rr_)
        if "decision_date" in main:
            sub = main[main.decision_date.astype(str) < "2019-07-10"]
            if 0 < len(sub) < len(main) and sub.media_any.nunique() > 1:
                rr_ = table_2x2(sub, "media_any", "intervention")
                rows.append(_rob_row(f"הכרעות לפני תחילת תיקון 137 (10.7.2019; n={len(sub)})", rr_)); rep.put_2x2("rob.pre137", rr_)
        if "attempt_only" in main and main.attempt_only.sum() > 0:
            sub = main[main.attempt_only == 0]
            if sub.media_any.nunique() > 1:
                rr_ = table_2x2(sub, "media_any", "intervention")
                rows.append(_rob_row(f"ללא ערעורי ניסיון לרצח בלבד (n={len(sub)})", rr_)); rep.put_2x2("rob.no_attempt", rr_)
            att = main[main.attempt_only == 1]
            rep.put("attempt.main", len(att)); rep.put("attempt.main_salient", (att.media_any == 1).sum())
            rep.put("attempt.main_not_salient", (att.media_any == 0).sum())
            if "attempt_only" in full:
                rep.put("attempt.full", full.attempt_only.sum())
        if len(full) != len(main):
            rr_ = table_2x2(full, "media_any", "intervention")
            rows.append(_rob_row(f"קורפוס מלא (N={len(full)})", rr_)); rep.put_2x2("rob.full", rr_)
        if "homicide_murder" in main and main.homicide_murder.nunique() > 1:
            for val, key, label in ((0, "stratum_other", "ריבוד לפי עבירה — המתה אחרת"),
                                    (1, "stratum_murder", "ריבוד — רצח או ניסיון לרצח")):
                rr_ = table_2x2(main[main.homicide_murder == val], "media_any", "intervention")
                row = _rob_row(label, rr_); row[3] = row[4] = "—"
                rows.append(row); rep.put_2x2(f"rob.{key}", rr_)
            mh = mantel_haenszel(main, "media_any", "intervention", "homicide_murder")
            rows.append(["Mantel–Haenszel (משותף לשתי השכבות)", "", "",
                         f"χ²={fmt(mh['chi2'])}, p={fmt_p(mh['p'])}; Breslow–Day χ²(1)={fmt(mh['bd_chi2'])}, p={fmt_p(mh['bd_p'])}",
                         "", f"{fmt(mh['or'])} {ci(*mh['or_ci'])}"])
            rep.put("rob.mh.chi2", mh["chi2"]); rep.put("rob.mh.p", mh["p"]); rep.put("rob.mh.bd_p", mh["bd_p"])
            rep.put("rob.mh.bd_chi2", mh["bd_chi2"])
            rep.put("rob.mh.or", mh["or"]); rep.put("rob.mh.or_lo", mh["or_ci"][0]); rep.put("rob.mh.or_hi", mh["or_ci"][1])
        rep.table(sec, ROB_COLUMNS, rows)

    # ---------------------------------------------------------------- E. dose-response
    sec = rep.section("dose", "מינון: מספר הידיעות",
                      "האם יותר ידיעות קשורות לשיעור התערבות גבוה יותר? חלוקה לארבע קבוצות ומבחן מגמה.")
    with guarded(rep, sec):
        if not has(main, "dose"):
            cdf = main.rename(columns={"media_any": core.IV_MAIN, "intervention": core.DV_MAIN,
                                       "media_count": "district_plus_appeal_article_count"})
            dr = core.dose_response(cdf)
            order = {"0": 0, "1": 1, "2-4": 2, "5+": 3}
            rows = []
            for b in dr["buckets"]:
                code = order[b["group"]]
                rows.append([BUCKET_LABELS[code], b["n"], b["events"], f"{100*b['rate']:.1f}%", ci(*b["ci"], d=1, scale=100)])
                rep.put(f"dose.b{code}.a", b["events"]); rep.put(f"dose.b{code}.n", b["n"])
            rep.table(sec, ["קבוצה", "תיקים", "התערבויות", "שיעור", "95% CI"], rows)
            bucket = cdf["district_plus_appeal_article_count"].fillna(0).map(core.salience_bucket).map(order)
            ct = pd.crosstab(bucket, cdf[core.DV_MAIN])
            chi2, p, dof, _ = stats.chi2_contingency(ct.values, correction=False)
            rr_ = stats.pearsonr(bucket, cdf[core.DV_MAIN])[0]
            linlin = (len(cdf) - 1) * rr_ ** 2
            p_lin = float(stats.chi2.sf(linlin, 1))
            rep.table(sec, ["מבחן", "ערך"], [
                [f"Pearson χ²({dof})", f"{fmt(chi2)}, p={fmt_p(p)}"],
                ["מגמה ליניארית (Linear-by-Linear) χ²(1)", f"{fmt(linlin)}, p={fmt_p(p_lin)}"],
                ["Cochran–Armitage z", f"{fmt(dr['cochran_armitage_z'])}, p={fmt_p(dr['cochran_armitage_p'])}"],
                [f"Spearman ρ בין מספר הידיעות להתערבות (תיקים מסוקרים, n={dr['n_covered']})",
                 f"{fmt(dr['spearman_count_vs_intervention_among_covered'])}, p={fmt_p(dr['spearman_p'])}"],
            ])
            rep.put("dose.chi2", chi2); rep.put("dose.p", p); rep.put("dose.linlin", linlin); rep.put("dose.linlin_p", p_lin)
            rep.put("dose.spearman", dr["spearman_count_vs_intervention_among_covered"]); rep.put("dose.spearman_p", dr["spearman_p"])
        else:
            rep.note(sec, "ניתוח המינון דולג: חסרות עמודות " + ", ".join(has(main, "dose")), "warn")

    # ---------------------------------------------------------------- F. media references in the judgment
    sec = rep.section("refs", "ניתוח משלים א: אזכורי תקשורת בפסק הדין",
                      "האם בפסקי דין של תיקים שסוקרו מופיעים יותר אזכורים לתקשורת? (אזכורים שאומתו ידנית בהקשרם)")
    with guarded(rep, sec):
        if not has(main, "refs"):
            rows = []
            for key, dv, label in (("any", "media_ref_any", "אזכור מאומת כלשהו"),
                                   ("reas", "media_ref_reasoning", "אזכור בתוך פרק ההנמקה"),
                                   ("cov", "media_ref_coverage", "אזכור סיקור התיק / טענת השפעה (A/C)"),
                                   ("pressure", "media_ref_pressure", "טענת השפעה בלבד (C)")):
                if dv not in main:
                    continue
                rr_ = table_2x2(main, "media_any", dv)
                row = _row_2x2(label, rr_)
                row[5] = f"{fmt(rr_['odds_ratio'])} {ci(*rr_['odds_ratio_ci'])}; φ={fmt(rr_['phi'])}"
                rows.append(row); rep.put_2x2(f"ref.{key}", rr_)
            rep.table(sec, ["אזכור", "עם בולטות", "ללא בולטות", "מבחן χ²", "Fisher", "OR [95% CI]; φ"], rows)
            if "media_ref_count" in main:
                rep.put("ref.count_main", main.media_ref_count.sum()); rep.put("ref.cases_main", (main.media_ref_count > 0).sum())
                rep.put("ref.count_full", full.media_ref_count.sum()); rep.put("ref.cases_full", (full.media_ref_count > 0).sum())
                info = (f"בקורפוס המלא: {int(full.media_ref_count.sum())} אזכורים מאומתים ב-{int((full.media_ref_count > 0).sum())} תיקים; "
                        f"במדגם הניתוח: {int(main.media_ref_count.sum())} אזכורים ב-{int((main.media_ref_count > 0).sum())} תיקים.")
                refs = extras.get("refs")
                if refs is not None:
                    rr2 = refs.manual_reason.value_counts()
                    reas = refs[refs.in_reasoning == 1]
                    info += (f" לפי סוג (קורפוס מלא): מידע (B) {int(rr2.get('B', 0))}; סיקור (A) {int(rr2.get('A', 0))}; "
                             f"השפעה/לחץ (C) {int(rr2.get('C', 0))}. בתוך פרק ההנמקה: {len(reas)} אזכורים ב-{reas.case_id.nunique()} תיקים.")
                    rm = refs[refs.case_id.isin(set(main.case_id))].manual_reason.value_counts()
                    info += (f" במדגם הניתוח: מידע (B) {int(rm.get('B', 0))}; סיקור (A) {int(rm.get('A', 0))}; "
                             f"השפעה/לחץ (C) {int(rm.get('C', 0))}.")
                    for code in ("A", "B", "C"):
                        rep.put(f"ref.{code}_full", rr2.get(code, 0))
                        rep.put(f"ref.{code}_main", rm.get(code, 0))
                    rep.put("ref.reasoning_full", len(reas)); rep.put("ref.reasoning_cases_full", reas.case_id.nunique())
                rep.note(sec, info)
        else:
            rep.note(sec, "הניתוח דולג: חסרות עמודות " + ", ".join(has(main, "refs")), "warn")

    # ---------------------------------------------------------------- G. textual complexity of the reasoning
    sec = rep.section("complexity", "ניתוח משלים ב: אורך ומורכבות טקסטואלית של ההנמקה",
                      "האם ההנמקה בתיקים שסוקרו ארוכה ומורכבת יותר? מדד מורכבות משוקלל משישה רכיבים (רכיב ראשי ראשון), "
                      "מבחן t, Mann–Whitney ורגרסיה בבקרת אורך ההנמקה.")
    with guarded(rep, sec):
        if "reasoning_method" in main:
            vc = main.reasoning_method.value_counts()
            labels = {"heading_discussion_decision": "כותרת \"דיון והכרעה\"", "heading_discussion_numbered": "כותרת \"דיון\" ממוספרת",
                      "court_turn_phrase": "ביטוי מעבר (\"לאחר שעיינתי...\")", "whole_judgment": "ללא סימן — כל פסק הדין"}
            rep.table(sec, ["אופן חילוץ פרק ההנמקה", "תיקים", "%"],
                      [[labels.get(k, k), int(v), f"{100*v/len(main):.1f}%"] for k, v in vc.items()])
            for k, v in vc.items():
                rep.put(f"cx.method.{k}", v)
            whole = main.reasoning_method == "whole_judgment"
            w1, w0 = 100 * whole[main.media_any == 1].mean(), 100 * whole[main.media_any == 0].mean()
            rep.note(sec, f"פרק ההנמקה = פסק הדין כולו (לא נמצא סימן): {w1:.1f}% בתיקים בולטים, {w0:.1f}% בתיקים שאינם בולטים.")
            rep.put("cx.whole_pct1", w1); rep.put("cx.whole_pct0", w0)
        missing_cx = [c for c in COMPLEXITY_COMPONENTS if c not in main]
        if not missing_cx:
            cx = complexity_index(main)
            rows = [[COMPLEXITY_LABELS[c], fmt(cx["loadings"][i], 3), fmt(cx["weights"][i], 3)] for i, c in enumerate(COMPLEXITY_COMPONENTS)]
            rep.table(sec, ["רכיב (ציון z)", "טעינה", "מקדם ציון (משקל)"], rows, "ניתוח רכיבים ראשיים — רכיב אחד")
            rep.table(sec, ["מדד", "ערך"], [
                ["ערך עצמי; % שונות מוסברת", f"{fmt(cx['eigenvalue'], 3)}; {fmt(cx['var_pct'], 1)}%"],
                ["ערכים עצמיים (כל הרכיבים)", ", ".join(fmt(e, 3) for e in cx["eigenvalues"])],
                ["KMO", fmt(cx["kmo"], 3)],
                [f"Bartlett χ²({cx['bartlett_df']})", f"{fmt(cx['bartlett_chi2'])}, p={fmt_p(cx['bartlett_p'])}"],
                ["α של קרונבך (ששת ציוני z)", fmt(cx["alpha"], 3)],
            ])
            for i in range(6):
                rep.put(f"cx.w{i+1}", cx["weights"][i]); rep.put(f"cx.load{i+1}", cx["loadings"][i])
            rep.put("cx.eigen", cx["eigenvalue"]); rep.put("cx.var_pct", cx["var_pct"]); rep.put("cx.kmo", cx["kmo"])
            rep.put("cx.bartlett", cx["bartlett_chi2"]); rep.put("cx.alpha", cx["alpha"])
            for i, e in enumerate(cx["eigenvalues"][:3], start=1):
                rep.put(f"cx.eig{i}", e)
            main = main.assign(complexity=cx["score"])
            g1, g0 = main.loc[main.media_any == 1, "complexity"], main.loc[main.media_any == 0, "complexity"]
            tt = stats.ttest_ind(g1, g0, equal_var=True)
            n1_, n0_ = len(g1), len(g0)
            sp = math.sqrt(((n1_ - 1) * g1.var() + (n0_ - 1) * g0.var()) / (n1_ + n0_ - 2))
            dd = (g1.mean() - g0.mean()) / sp
            se_d = math.sqrt((n1_ + n0_) / (n1_ * n0_) + dd ** 2 / (2 * (n1_ + n0_)))
            mwc = mann_whitney_spss(main, "complexity")
            rep.table(sec, ["", "עם בולטות", "ללא בולטות"], [
                ["מדד מורכבות: ממוצע (ס\"ת)", f"{fmt(g1.mean(), 3)} ({fmt(g1.std())})", f"{fmt(g0.mean(), 3)} ({fmt(g0.std())})"],
            ], "השוואת קבוצות")
            rep.table(sec, ["מבחן", "ערך"], [
                [f"t({n1_ + n0_ - 2}) (שונויות שוות)", f"{fmt(tt.statistic)}, p={fmt_p(tt.pvalue)}"],
                ["d של כהן [95% CI]", f"{fmt(dd)} {ci(dd - 1.96 * se_d, dd + 1.96 * se_d)}"],
                ["Mann–Whitney", f"U={fmt(mwc['U_spss'], 1)}, z={fmt(mwc['z'])}, p={fmt_p(mwc['p'])}, "
                             f"r={fmt(abs(mwc['z']) / math.sqrt(n1_ + n0_), 2)}"],
            ])
            rep.put("cx.mean1", g1.mean()); rep.put("cx.mean0", g0.mean()); rep.put("cx.sd1", g1.std()); rep.put("cx.sd0", g0.std())
            rep.put("cx.t", tt.statistic); rep.put("cx.t_p", tt.pvalue); rep.put("cx.d", dd)
            rep.put("cx.d_lo", dd - 1.96 * se_d); rep.put("cx.d_hi", dd + 1.96 * se_d); rep.put("cx.mw_z", mwc["z"])
            rep.put("cx.mw_r", abs(mwc["z"]) / math.sqrt(n1_ + n0_))
            if "r_words_log" in main:
                o = ols_beta(main, "complexity", "media_any", "r_words_log")
                rep.table(sec, ["משתנה", "B [95% CI]", "β", "p"], [
                    ["בולטות מוקדמת", f"{fmt(o['b'])} {ci(*o['b_ci'])}", fmt(o["beta"]), fmt_p(o["p"])],
                    ["לוג אורך ההנמקה", f"{fmt(o['b_control'])} {ci(*o['b_control_ci'])}", fmt(o["beta_control"]), fmt_p(o["p_control"])],
                ], f"רגרסיה ליניארית: מדד המורכבות בבקרת אורך ההנמקה (R²={fmt(o['r2'], 3)})")
                rep.put("cx.ols.b", o["b"]); rep.put("cx.ols.b_lo", o["b_ci"][0]); rep.put("cx.ols.b_hi", o["b_ci"][1])
                rep.put("cx.ols.beta", o["beta"]); rep.put("cx.ols.p", o["p"]); rep.put("cx.ols.beta_len", o["beta_control"])
        elif any(c in main for c in COMPLEXITY_COMPONENTS):
            rep.note(sec, "מדד המורכבות דולג: חסרות עמודות " + ", ".join(missing_cx), "warn")
        rows = []
        for col, label, d in LENGTH_AND_COMPONENTS:
            if col not in main:
                continue
            mw = mann_whitney_spss(main, col)
            r_eff = abs(mw["z"]) / math.sqrt(mw["n_exposed"] + mw["n_unexposed"])
            rows.append([label, fmt(mw["mean_exposed"], d), fmt(mw["mean_unexposed"], d), fmt(mw["median_exposed"], d),
                         fmt(mw["median_unexposed"], d), fmt(mw["U_spss"], 1 if mw["U_spss"] % 1 else 0), fmt(mw["z"]), fmt_p(mw["p"]),
                         fmt(r_eff, 2)])
            rep.put(f"mw.{col}.r", r_eff)
            for k, v in (("mean1", mw["mean_exposed"]), ("mean0", mw["mean_unexposed"]), ("med1", mw["median_exposed"]),
                         ("med0", mw["median_unexposed"]), ("U", mw["U_spss"]), ("z", mw["z"]), ("p", mw["p"])):
                rep.put(f"mw.{col}.{k}", v)
        if rows:
            rep.table(sec, ["מדד", "ממוצע עם", "ממוצע ללא", "חציון עם", "חציון ללא", "U", "z", "p", "r = |z|/√N"], rows,
                      "אורך ורכיבי המורכבות — Mann–Whitney (דו-צדדי)")
        elif "reasoning_method" not in main:
            rep.note(sec, "הניתוח דולג: אין בקובץ עמודות אורך/מורכבות.", "warn")

    # ---------------------------------------------------------------- G2. Holm correction for the secondary question
    sec = rep.section("holm", "תיקון למבחנים מרובים (Holm) — השאלה המשנית",
                      "14 המבחנים של הניתוחים המשלימים (4 מבחני אזכורים, 7 מבחני Mann–Whitney ו-3 מבחנים של מדד המורכבות) "
                      "מתוקנים יחד בשיטת Holm, כדי לבדוק שהממצאים המובהקים אינם תוצאה של ריבוי מבחנים.")
    with guarded(rep, sec):
        tests: list[tuple[str, str, float]] = []
        for key, dv, label in (("any", "media_ref_any", "אזכור מאומת כלשהו"), ("reas", "media_ref_reasoning", "אזכור בפרק ההנמקה"),
                               ("cov", "media_ref_coverage", "אזכור סיקור / טענת השפעה"), ("pressure", "media_ref_pressure", "טענת השפעה בלבד")):
            if dv in main and main[dv].nunique() > 1:
                r_ = table_2x2(main, "media_any", dv)
                tests.append((key, label, r_["fisher_p_two_sided"] if r_["min_expected_count"] < 5 else r_["p_chi2_uncorrected"]))
        for col, label, _ in LENGTH_AND_COMPONENTS:
            if col != "words" and col in main:
                tests.append((col, f"Mann–Whitney: {label}", mann_whitney_spss(main, col)["p"]))
        if not [c for c in COMPLEXITY_COMPONENTS if c not in main]:
            mm = main.assign(complexity=complexity_index(main)["score"])
            g1, g0 = mm.loc[mm.media_any == 1, "complexity"], mm.loc[mm.media_any == 0, "complexity"]
            tests.append(("cx_t", "מדד המורכבות: מבחן t", float(stats.ttest_ind(g1, g0).pvalue)))
            tests.append(("cx_mw", "מדד המורכבות: Mann–Whitney", mann_whitney_spss(mm, "complexity")["p"]))
            if "r_words_log" in mm:
                tests.append(("cx_ols", "מדד המורכבות: רגרסיה בבקרת אורך", ols_beta(mm, "complexity", "media_any", "r_words_log")["p"]))
        if len(tests) >= 2:
            order = sorted(range(len(tests)), key=lambda i: tests[i][2])
            adj, running = [0.0] * len(tests), 0.0
            for rank, i in enumerate(order):
                running = max(running, min(1.0, (len(tests) - rank) * tests[i][2]))
                adj[i] = running
            rows = []
            for (key, label, p_raw), p_adj in zip(tests, adj):
                rows.append([label, fmt_p(p_raw), fmt_p(p_adj) if p_adj >= 0.001 or p_adj < 0.0005 else f"{p_adj:.4f}".replace("0.", ".", 1),
                             "כן" if p_adj < 0.05 else "לא"])
                rep.put(f"holm.{key}", p_adj)
            rep.table(sec, ["מבחן", "p לפני תיקון", "p אחרי תיקון Holm", "מובהק (α=.05)?"], rows)
            rep.note(sec, f"מספר המבחנים: {len(tests)}. במבחני האזכורים: χ², או Fisher כששכיחות צפויה קטנה מ-5.")

    # ---------------------------------------------------------------- H. power
    sec = rep.section("power", "עוצמה סטטיסטית (ניתוח רגישות)",
                      "מה האפקט הקטן ביותר שאפשר היה לגלות בגודל המדגם הזה? (נוסחת h של כהן, כמו בקובץ ה-SPSS; "
                      "המבחן החד-צדדי הוא כלל ההכרעה, והדו-צדדי מוצג בסוגריים)")
    with guarded(rep, sec):
        p1, p0, n1, n0 = main_rates
        if 0 < p0 < 1 and 0 < p1 < 1 and n1 and n0:
            pw = power_spss(p1, p0, n1, n0)
            rep.table(sec, ["מדד", "ערך"], [
                ["h של כהן (אפקט נצפה)", fmt(pw["h"], 3)],
                ["עוצמה חד-צדדית / דו-צדדית (α=.05)", f"{fmt(pw['power_1s'])} / {fmt(pw['power_2s'])}"],
                ["אפקט מינימלי לגילוי בעוצמה .80 — חד-צדדי (כלל ההכרעה)",
                 f"{100*pw['p1_mde_1s']:.1f}% מול {100*p0:.1f}% (≈{100*(pw['p1_mde_1s']-p0):.1f} נק' אחוז; h={fmt(pw['h_mde_1s'], 3)})"],
                ["תיקים מסוקרים נדרשים לגילוי האפקט הנצפה — חד-צדדי", f"כ-{pw['n1_needed_1s']:,.0f} (באותו יחס בין הקבוצות)"],
                ["(דו-צדדי: אפקט מינימלי; תיקים מסוקרים נדרשים)",
                 f"{100*pw['p1_mde']:.1f}% מול {100*p0:.1f}% (h={fmt(pw['h_mde'], 3)}); כ-{pw['n1_needed']:,.0f}"],
            ])
            rep.put("power.mde_1s_rate_pct", 100 * pw["p1_mde_1s"]); rep.put("power.mde_1s_h", pw["h_mde_1s"])
            rep.put("power.mde_1s_diff_pct", 100 * (pw["p1_mde_1s"] - p0)); rep.put("power.n1_needed_1s", pw["n1_needed_1s"])
            rep.put("power.h", pw["h"]); rep.put("power.two_sided", pw["power_2s"]); rep.put("power.one_sided", pw["power_1s"])
            rep.put("power.mde_rate_pct", 100 * pw["p1_mde"]); rep.put("power.mde_h", pw["h_mde"]); rep.put("power.n1_needed", pw["n1_needed"])
            core_pw = core.power_analysis(n1, n0, p0, p1)
            rep.note(sec, f"בדיקה צולבת (statsmodels): עוצמה דו-צדדית {fmt(core_pw['power_observed_two_sided'])}.")

    # ---------------------------------------------------------------- I. measurement quality (study data only)
    g, q, pr = extras.get("google"), extras.get("queries"), extras.get("primo")
    if g is not None and q is not None and pr is not None:
        sec = rep.section("quality", "איכות המדידה (נתוני המחקר)",
                          "כמה ידיעות ושאילתות נבדקו, וכמה נכללו או הוחרגו בניקוי הידני.")
        vc = g.curation_status.value_counts()
        pv = pr.curation_status.value_counts()
        rep.table(sec, ["מדד", "ערך"], [
            ["פריטי Google News שנבדקו", f"{len(g)}: נכללו {vc.get('included', 0)}, תיק שגוי {vc.get('excluded_wrong_case', 0)}, מחוץ לחלון {vc.get('excluded_after_window', 0)}"],
            ["שאילתות שם מדויק", f"{len(q)} (שלב ערעור {int((q.window_type == 'appeal_stage_pre_decision_media').sum())}; שלב הערכאה הדיונית {int((q.window_type == 'district_verdict_stage_media').sum())})"],
            ["רשומות Primo", f"{len(pr)}: נכללו {pv.get('included', 0)} ({pr[pr.curation_status == 'included'].case_id.nunique()} תיקים)"],
        ])
        rep.put("quality.google_items", len(g)); rep.put("quality.google_included", vc.get("included", 0))
        rep.put("quality.google_wrong_case", vc.get("excluded_wrong_case", 0)); rep.put("quality.google_outside", vc.get("excluded_after_window", 0))
        rep.put("quality.queries", len(q)); rep.put("quality.queries_appeal", (q.window_type == "appeal_stage_pre_decision_media").sum())
        rep.put("quality.queries_district", (q.window_type == "district_verdict_stage_media").sum())
        rep.put("quality.primo_records", len(pr)); rep.put("quality.primo_included", pv.get("included", 0))
        rep.put("quality.primo_cases", pr[pr.curation_status == "included"].case_id.nunique())
        if {"media_primo_any", "media_appeal_any"} <= set(main.columns):
            both = int(((main.media_primo_any == 1) & (main.media_appeal_any == 1)).sum())
            in_main = int(((main.media_primo_any == 1) & (main.media_any == 1)).sum())
            rep.table(sec, ["Primo לעומת Google News (מדגם הניתוח)", "תיקים"], [
                ["תיקים עם רשומת Primo", int((main.media_primo_any == 1).sum())],
                ["מהם — גם ידיעת Google News בשלב הערעור", both], ["מהם — בולטים גם בחלון המרכזי", in_main]])
            rep.put("quality.primo_and_appeal", both); rep.put("quality.primo_and_main", in_main)
        orv = extras.get("outcome_review")
        if orv is not None and "relief_type" in main:
            manual_main = int(main.case_id.isin(set(orv.case_id)).sum())
            harsher = int(((main.relief_type == 5) & ~main.case_id.isin(set(orv.case_id))).sum())
            auto = len(main) - manual_main - harsher
            rep.table(sec, ["קידוד תוצאת הערעור (מדגם הניתוח)", "תיקים"], [
                ["נבדקו ידנית (לא סווגו אוטומטית בביטחון)", manual_main], ["תוצאות החמרה שנבדקו ידנית בנפרד", harsher],
                ["סווגו אוטומטית בלבד", auto], [f"סה״כ בדיקות ידניות בקורפוס המלא ({len(full)})", int(orv.case_id.nunique())]])
            rep.put("quality.outcome_manual_main", manual_main); rep.put("quality.outcome_harsher_main", harsher)
            rep.put("quality.outcome_auto_main", auto); rep.put("quality.outcome_manual_full", orv.case_id.nunique())

    return {"n_main": int(len(main)), "n_full": int(len(full)), "sections": rep.sections, "values": rep.values}


# ------------------------------------------------------------------ golden comparison
def matches(got: float, expected: float, d: int) -> bool:
    """True if the exact value, rounded once to the paper's number of decimals, equals the paper's value."""
    return abs(got - expected) <= 0.5 * 10 ** (-d) + 1e-9


def compare_golden(values: dict[str, float], golden_path: Path) -> dict[str, Any]:
    spec = json.loads(Path(golden_path).read_text(encoding="utf-8"))
    items = []
    for it in spec["items"]:
        got = values.get(it["key"])
        exp = it["expected"]
        d = it["decimals"]
        if got is None or (isinstance(got, float) and math.isnan(got)):
            ok, shown = False, "חסר"
        elif exp == "<.001":
            ok, shown = got < 0.0005, fmt_p(got)
        else:
            ok, shown = matches(got, float(exp), d), f"{got:.{max(d, 0)}f}"
        items.append({"key": it["key"], "label": it["label"], "section": it["key"].split(".")[0],
                      "expected": exp if isinstance(exp, str) else f"{float(exp):.{d}f}", "got": shown, "ok": bool(ok)})
    n_ok = sum(i["ok"] for i in items)
    return {"checked": len(items), "matched": n_ok, "all_ok": n_ok == len(items), "items": items}

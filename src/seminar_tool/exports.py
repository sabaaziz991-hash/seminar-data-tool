"""Excel exports of the tool (study data, rebuilt population, Google News items, text measures)."""
from __future__ import annotations

import io
from typing import Any

import pandas as pd


def _autosize(ws: Any) -> None:
    for col in ws.columns:
        width = max((len(str(c.value)) if c.value is not None else 0) for c in col)
        ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 70)


def frames_to_excel(frames: list[tuple[str, pd.DataFrame]]) -> bytes:
    from openpyxl.styles import Font

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for name, df in frames:
            df.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            ws.sheet_view.rightToLeft = True
            for c in ws[1]:
                c.font = Font(bold=True)
            _autosize(ws)
    return buf.getvalue()

"""Recalculate a workbook with headless LibreOffice and check for formula errors.

openpyxl writes formulas without cached results. Running the file through
LibreOffice stores computed values, so previews and pandas can read them, and
lets the pipeline fail if any formula evaluates to an error.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import warnings
from pathlib import Path

from openpyxl import load_workbook

ERRORS = ("#VALUE!", "#NAME?", "#DIV/0!", "#REF!", "#N/A", "#NUM!", "#NULL!", "Err:")


def available() -> bool:
    return shutil.which("soffice") is not None


def recalc(path: Path, timeout: int = 180) -> dict:
    path = Path(path)
    formulas = sum(
        1 for ws in load_workbook(path).worksheets for row in ws.iter_rows() for c in row
        if isinstance(c.value, str) and c.value.startswith("=")
    )
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp) / "profile"
        subprocess.run(
            ["soffice", f"-env:UserInstallation=file://{profile}", "--headless", "--calc",
             "--convert-to", "xlsx", "--outdir", tmp, str(path)],
            check=True, capture_output=True, timeout=timeout,
        )
        shutil.copyfile(Path(tmp) / path.name, path)
    errors = []
    with warnings.catch_warnings():
        # LibreOffice writes extensions openpyxl does not read; harmless for this check.
        warnings.simplefilter("ignore", UserWarning)
        wb = load_workbook(path, data_only=True)
    for ws in wb.worksheets:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith(ERRORS):
                    errors.append(f"{ws.title}!{c.coordinate}={c.value}")
    return {"status": "success" if not errors else "errors_found", "total_formulas": formulas,
            "errors": errors}

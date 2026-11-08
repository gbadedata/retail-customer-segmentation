"""Render workbook sheets to PNG for the README (docs/).

Needs LibreOffice (soffice), poppler (pdftoppm) and Pillow. Not part of the
pipeline: run it after `make run` when the workbook layout changes.

    python scripts/render_previews.py outputs/customer_segments_pack.xlsx docs Segment_Summary Customer_Lookup
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import warnings
from pathlib import Path

from openpyxl import load_workbook
from PIL import Image, ImageChops


def crop(path: Path, pad: int = 24) -> None:
    im = Image.open(path).convert("RGB")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    box = ImageChops.difference(im, bg).getbbox()
    if box:
        left, top, right, bottom = box
        im.crop((max(left - pad, 0), max(top - pad, 0), min(right + pad, im.width),
                 min(bottom + pad, im.height))).save(path)


def render(xlsx: Path, out_dir: Path, sheets: list[str], dpi: int = 120) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    made = []
    with tempfile.TemporaryDirectory() as tmp:
        for sheet in sheets:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                wb = load_workbook(xlsx)
            for ws in wb.worksheets:
                ws.sheet_state = "visible" if ws.title == sheet else "hidden"
            ws = wb[sheet]
            wb.active = wb.sheetnames.index(sheet)
            ws.page_setup.orientation = "landscape"
            ws.sheet_properties.pageSetUpPr.fitToPage = True
            ws.page_setup.fitToWidth = ws.page_setup.fitToHeight = 1
            if ws.max_row > 60:  # long data tables: show the top of the sheet only
                ws.print_area = f"A1:{ws.cell(row=1, column=min(ws.max_column, 16)).column_letter}28"
            src = Path(tmp) / f"{sheet}.xlsx"
            wb.save(src)
            subprocess.run(["soffice", f"-env:UserInstallation=file://{tmp}/profile", "--headless",
                            "--convert-to", "pdf", "--outdir", tmp, str(src)], check=True, capture_output=True)
            stem = out_dir / f"excel_{sheet.lower()}"
            subprocess.run(["pdftoppm", "-f", "1", "-l", "1", "-r", str(dpi), "-png", "-singlefile",
                            str(Path(tmp) / f"{sheet}.pdf"), str(stem)], check=True)
            png = stem.with_suffix(".png")
            crop(png)
            made.append(png)
    return made


if __name__ == "__main__":
    xlsx, out, *names = sys.argv[1:]
    for p in render(Path(xlsx), Path(out), names):
        print("wrote", p)

#!/usr/bin/env python3
"""
One-off (re-runnable) converter: turns the large .xlsx recommendation
workbooks into per-sheet Parquet files under data_parquet/.

Why: reading .xlsx with openpyxl has a huge parse-time memory spike
(often 10-20x the file size), which is what pushes the Streamlit app over
Community Cloud's ~1 GB limit. Parquet reads with a fraction of the peak
memory, loads faster, and is smaller on disk.

The app's loader (load_all_data) reads the Parquet output via the manifest
written here. Re-run this script whenever the source .xlsx files change:

    python3 convert_to_parquet.py

Dtypes are intentionally left as pandas' defaults (same as the previous
openpyxl path) so downstream behaviour is unchanged.
"""
import json
import os
import re

import pandas as pd

# Mirrors EXCEL_FILES in app.py — ORDER MATTERS (first file wins on
# duplicate sheet names).
EXCEL_FILES = [
    "Recommendations GitHub.xlsx",
    "Recommendations GitHub Home.xlsx",
    "Recommendations GitHub Books.xlsx",
    "Recommendations GitHub IntBooks.xlsx",
]

OUT_DIR = "data_parquet"


def _safe(name: str) -> str:
    """Filesystem-safe slug for a sheet name (manifest keeps the real name)."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", name.strip())
    return slug or "sheet"


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    manifest = {"files": []}

    for path in EXCEL_FILES:
        if not os.path.exists(path):
            print(f"  skip (missing): {path}")
            continue
        stem = os.path.splitext(os.path.basename(path))[0]
        file_dir = os.path.join(OUT_DIR, _safe(stem))
        os.makedirs(file_dir, exist_ok=True)

        ef = pd.ExcelFile(path, engine="openpyxl")
        sheets = []
        used = set()
        for sheet in ef.sheet_names:
            df = pd.read_excel(ef, sheet_name=sheet)
            # Match the loader's column hygiene up-front.
            df.columns = [str(c).strip() for c in df.columns]
            # openpyxl produces "object" columns that often mix int + str in
            # the same column (e.g. 'Inserted Date'); pyarrow can't infer a
            # type for those. Normalise object columns to plain strings
            # (nulls preserved as None) so the round-trip is lossless for the
            # app, which stringifies these columns anyway.
            for col in df.columns:
                if df[col].dtype == object:
                    s = df[col]
                    df[col] = s.where(s.notna(), None).map(
                        lambda v: v if (v is None or isinstance(v, str)) else str(v)
                    )
            # Parquet needs string column names and unique names.
            base = _safe(sheet)
            fname = base
            i = 1
            while fname in used:
                i += 1
                fname = f"{base}_{i}"
            used.add(fname)
            rel = os.path.join(_safe(stem), f"{fname}.parquet")
            df.to_parquet(os.path.join(OUT_DIR, rel), engine="pyarrow", index=False)
            sheets.append({"name": sheet, "path": rel.replace(os.sep, "/")})
            print(f"  {path} :: {sheet} -> {rel}  ({len(df):,} rows)")
        ef.close()
        manifest["files"].append({"name": os.path.basename(path), "sheets": sheets})

    with open(os.path.join(OUT_DIR, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"\nWrote manifest with {len(manifest['files'])} file(s).")


if __name__ == "__main__":
    main()

"""Utility script to merge odometer readings into horometer sheet.

The script expects ``Horometro.xlsx`` and ``Odometro.xlsx`` files in the
``excel`` directory.  It will copy the ``LECTURA`` column from the
odometer file into the horometer file for matching asset codes and
produce ``Horometro_actualizado.xlsx``.

The column names are matched in a case–insensitive way.  If a column is
missing the script leaves the original value untouched.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

BASE_PATH = Path(__file__).resolve().parent / "excel"

HOROMETRO_FILE = BASE_PATH / "Horometro.xlsx"
ODOMETRO_FILE = BASE_PATH / "Odometro.xlsx"
OUTPUT_FILE = BASE_PATH / "Horometro_actualizado.xlsx"

KEY_COL = "CODIGO"
VALUE_COL = "LECTURA"


def main() -> int:
    try:
        horometro_df = pd.read_excel(HOROMETRO_FILE)
        odometro_df = pd.read_excel(ODOMETRO_FILE)
    except FileNotFoundError as exc:
        sys.stderr.write(f"Archivo faltante: {exc}\n")
        return 1

    # Normalise column names to simplify matching
    h_cols = {c.lower(): c for c in horometro_df.columns}
    o_cols = {c.lower(): c for c in odometro_df.columns}

    key_h = h_cols.get(KEY_COL.lower()) or next(iter(h_cols.values()))
    key_o = o_cols.get(KEY_COL.lower()) or next(iter(o_cols.values()))
    val_o = o_cols.get(VALUE_COL.lower()) or None

    merged = horometro_df.merge(
        odometro_df[[key_o, val_o]] if val_o else odometro_df[[key_o]],
        left_on=key_h,
        right_on=key_o,
        how="left",
        suffixes=("", "_odo"),
    )

    if val_o and f"{val_o}_odo" in merged.columns and VALUE_COL in h_cols.values():
        # Update the reading column when available
        merged[h_cols.get(VALUE_COL.lower(), VALUE_COL)] = merged[
            f"{val_o}_odo"
        ].combine_first(merged[h_cols.get(VALUE_COL.lower(), VALUE_COL)])
        merged.drop(columns=[f"{val_o}_odo"], inplace=True)

    merged.to_excel(OUTPUT_FILE, index=False)
    print(f"Archivo generado: {OUTPUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
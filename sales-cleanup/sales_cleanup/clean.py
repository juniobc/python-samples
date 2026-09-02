"""Clean a messy sales export into a tidy table, and summarise it.

Real client input looks like `data/sales_raw.csv`: mixed date formats, currency
strings ("$19.90", "R$ 45,00", "1.299,00"), stray whitespace, inconsistent
casing, blank rows, negative quantities, and exact duplicates.

`clean(df)` is pure (DataFrame in, DataFrame out) so it is unit-tested with no
files. `run()` wires files together.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd

CANON_COLUMNS = {
    "order id": "order_id",
    "date": "date",
    "customer": "customer",
    "product": "product",
    "qty": "qty",
    "unit price": "unit_price",
    "notes": "notes",
}

_NUM_JUNK = re.compile(r"[^\d,.\-]")


def _to_number(value) -> float | None:
    """Parse '$19.90', 'R$ 45,00', '1,299.00', '1.299,00' -> float."""
    if pd.isna(value):
        return None
    s = _NUM_JUNK.sub("", str(value)).strip()
    if not s or s in {"-", ".", ","}:
        return None
    # Decide the decimal separator: whichever separator appears last.
    last_dot, last_comma = s.rfind("."), s.rfind(",")
    if last_comma > last_dot:            # 1.299,00  ->  1299.00
        s = s.replace(".", "").replace(",", ".")
    else:                               # 1,299.00  ->  1299.00
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def _clean_text(value) -> str | None:
    if pd.isna(value):
        return None
    s = re.sub(r"\s+", " ", str(value)).strip()
    return s or None


# Company suffixes that should stay upper-cased after title-casing.
_SUFFIX_FIX = {"Llc": "LLC", "Ltd": "LTD", "Ltda": "LTDA", "Sa": "SA", "Plc": "PLC"}


def _title_company(value: str | None) -> str | None:
    if value is None:
        return None
    s = re.sub(r"\s+", " ", value.title()).strip()  # "acme  corp" / "ACME CORP" -> "Acme Corp"
    for word, fixed in _SUFFIX_FIX.items():
        s = re.sub(rf"\b{word}\b", fixed, s)
    return s


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: CANON_COLUMNS.get(c.strip().lower(), c.strip().lower()) for c in df.columns})

    df["customer"] = df["customer"].map(_clean_text).map(_title_company)
    df["product"] = df["product"].map(_clean_text).map(
        lambda s: s.title() if s else None
    )
    df["date"] = pd.to_datetime(df["date"], errors="coerce", format="mixed", dayfirst=False)
    df["qty"] = pd.to_numeric(df["qty"], errors="coerce")
    df["unit_price"] = df["unit_price"].map(_to_number)

    before = len(df)
    df = df.dropna(subset=["date", "customer", "product", "qty", "unit_price"])
    df = df[df["qty"] > 0]
    df = df.drop_duplicates(subset=["date", "customer", "product", "qty", "unit_price"])
    df = df.sort_values("date").reset_index(drop=True)

    df["qty"] = df["qty"].astype(int)
    df["line_total"] = (df["qty"] * df["unit_price"]).round(2)

    df.attrs["rows_in"] = before
    df.attrs["rows_out"] = len(df)
    return df[["order_id", "date", "customer", "product", "qty", "unit_price", "line_total"]]


def summarise(clean_df: pd.DataFrame) -> dict[str, pd.DataFrame]:
    by_month = (
        clean_df.assign(month=clean_df["date"].dt.to_period("M").astype(str))
        .groupby("month", as_index=False)["line_total"].sum()
        .rename(columns={"line_total": "revenue"})
    )
    by_product = (
        clean_df.groupby("product", as_index=False)
        .agg(units=("qty", "sum"), revenue=("line_total", "sum"))
        .sort_values("revenue", ascending=False, ignore_index=True)
    )
    top_customers = (
        clean_df.groupby("customer", as_index=False)["line_total"].sum()
        .rename(columns={"line_total": "revenue"})
        .sort_values("revenue", ascending=False, ignore_index=True)
    )
    return {"by_month": by_month, "by_product": by_product, "top_customers": top_customers}


def run(src: Path, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = pd.read_csv(src, dtype=str)
    tidy = clean(raw)
    tidy.to_csv(out_dir / "sales_clean.csv", index=False)

    reports = summarise(tidy)
    for name, table in reports.items():
        table.to_csv(out_dir / f"{name}.csv", index=False)

    print(f"{src.name}: {raw.shape[0]} rows in -> {len(tidy)} clean rows")
    print(f"  wrote {out_dir/'sales_clean.csv'} and {len(reports)} report(s)")
    print(f"  total revenue: {tidy['line_total'].sum():,.2f}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Clean a messy sales CSV and summarise it.")
    p.add_argument("src", nargs="?", default="data/sales_raw.csv", type=Path)
    p.add_argument("-o", "--out", default="out", type=Path)
    args = p.parse_args()
    run(args.src, args.out)

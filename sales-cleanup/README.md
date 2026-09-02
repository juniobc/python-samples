# sales-cleanup

A work sample for the most common Python data job: **"here's a messy export,
clean it and give me a summary."**

`data/sales_raw.csv` is deliberately awful — the stuff real client files actually
contain:

| Problem in the raw file | What `clean()` does |
|---|---|
| `$19.90`, `R$ 45,00`, `1,299.00`, `1.299,00` | parses all to `float`, detecting the decimal separator |
| `2026-01-05`, `05/01/2026`, `Jan 9 2026`, `2026/02/03` | one `datetime` column (date locale is a one-line switch) |
| `  Acme Corp `, `acme corp`, `ACME CORP` | one canonical `Acme Corp`; `LLC` stays upper-cased |
| blank date / customer / product / qty | row dropped, count reported |
| `qty = -1` | dropped |
| byte-for-byte duplicate rows | de-duplicated on the business key |

## Run

```bash
python -m venv .venv && . .venv/Scripts/activate
pip install -r requirements.txt

python -m sales_cleanup.clean            # reads data/sales_raw.csv, writes out/
#   out/sales_clean.csv
#   out/by_month.csv   out/by_product.csv   out/top_customers.csv
```

```
sales_raw.csv: 15 rows in -> 9 clean rows
  total revenue: 14,787.40
```

## Tests

```bash
pytest -q          # 20 tests, no files touched — clean() and helpers are pure
```

## Design

- **`clean(df) -> df`** and **`summarise(df) -> {name: df}`** are pure. `run()` is
  the only file I/O.
- Currency parsing keys on which of `.` / `,` appears **last** — that's the
  decimal separator — so US and EU formats both work without a config flag.
- Dropped-row reasons are reported, not silent. `df.attrs["rows_in"/"rows_out"]`
  carry the counts.

## Real client version

Same core, plus: your date locale, your dedup key, output to Excel / Postgres /
Google Sheets, a scheduled run, and a one-page runbook. The raw file you send me
replaces `data/sales_raw.csv`; nothing else changes.

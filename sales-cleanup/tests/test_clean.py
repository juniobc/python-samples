"""Tests for the pure cleaning logic — no files touched.

    pytest -q
"""
from __future__ import annotations

import io

import pandas as pd
import pytest

from sales_cleanup.clean import _to_number, _title_company, clean, summarise

RAW = """Order ID,Date,Customer,Product,Qty,Unit Price,Notes
1001, 2026-01-05 ,  Acme Corp ,Widget A,3,"$19.90",
1002,05/01/2026,acme corp,Widget A,1,$19.90,dup?
1003,2026-01-07,Beta LLC,widget b,2,"R$ 45,00",BRL
1004,Jan 9 2026,Beta  LLC,Widget B,,45.00,missing qty
1005,2026-01-12,Gamma Inc.,Widget C,10,"1,299.00",
1007,2026/02/03,gamma inc,Widget C,-1,1299,negative qty
1008,,Delta Co,Widget B,2,45,no date
1009,2026-02-15,Delta Co,WIDGET B,2,"$45.00 ",
1010,2026-02-15,Delta Co,WIDGET B,2,"$45.00",exact dup of 1009
1013,2026-03-20,Gamma Inc.,Widget C,1,"1.299,00",EU format
1014,2026-03-28,  ,Widget A,2,19.9,blank customer
"""


@pytest.fixture(scope="module")
def tidy():
    return clean(pd.read_csv(io.StringIO(RAW), dtype=str))


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("$19.90", 19.90),
        ("R$ 45,00", 45.00),
        ("1,299.00", 1299.00),
        ("1.299,00", 1299.00),
        (" 19,90 ", 19.90),
        ("45.00 ", 45.00),
        ("", None),
        (None, None),
    ],
)
def test_to_number(raw, expected):
    assert _to_number(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("acme corp", "Acme Corp"),
        ("ACME CORP", "Acme Corp"),
        ("beta  llc", "Beta LLC"),
        ("Gamma Inc.", "Gamma Inc."),
    ],
)
def test_title_company(raw, expected):
    assert _title_company(raw) == expected


def test_drops_rows_missing_required_fields(tidy):
    # rows 1004 (no qty), 1008 (no date), 1014 (no customer) must be gone
    assert 1004 not in tidy["order_id"].values
    assert 1008 not in tidy["order_id"].values
    assert 1014 not in tidy["order_id"].values


def test_drops_non_positive_qty(tidy):
    assert 1007 not in tidy["order_id"].values
    assert (tidy["qty"] > 0).all()


def test_dedupes_exact_duplicate(tidy):
    # 1009 and 1010 are the same sale — only one survives
    delta = tidy[tidy["customer"] == "Delta Co"]
    assert len(delta) == 1


def test_currency_variants_all_parse_to_same_price(tidy):
    gamma = tidy[tidy["customer"] == "Gamma Inc."]
    assert set(gamma["unit_price"]) == {1299.00}


def test_customer_and_product_are_normalised(tidy):
    assert set(tidy["customer"]) <= {"Acme Corp", "Beta LLC", "Gamma Inc.", "Delta Co"}
    assert set(tidy["product"]) <= {"Widget A", "Widget B", "Widget C"}


def test_line_total_is_qty_times_price(tidy):
    assert (tidy["line_total"] == (tidy["qty"] * tidy["unit_price"]).round(2)).all()


def test_dates_are_datetimes_and_sorted(tidy):
    assert pd.api.types.is_datetime64_any_dtype(tidy["date"])
    assert tidy["date"].is_monotonic_increasing


def test_summary_revenue_matches_line_totals(tidy):
    reports = summarise(tidy)
    assert reports["by_month"]["revenue"].sum() == pytest.approx(tidy["line_total"].sum())
    assert reports["by_product"]["revenue"].sum() == pytest.approx(tidy["line_total"].sum())

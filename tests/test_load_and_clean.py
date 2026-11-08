import pandas as pd
import pytest

from segments import clean, load


def _raw(rows):
    cols = ["Invoice", "StockCode", "Description", "Quantity", "InvoiceDate", "Price", "Customer ID", "Country"]
    return pd.DataFrame(rows, columns=cols).astype(str)


def test_contract_parses_day_first_and_normalises_ids():
    df = load.validate(_raw([["1", "10001", "X", "2", "01/12/2009 07:45", "1.5", "13085.0", "UK"],
                             ["2", "10001", "X", "2", "13/12/2009 09:58", "1.5", "13085", "UK"]]), "t")
    assert df["InvoiceDate"].iloc[0] == pd.Timestamp("2009-12-01 07:45")
    assert df["InvoiceDate"].iloc[1] == pd.Timestamp("2009-12-13 09:58")
    assert list(df["Customer ID"]) == ["13085", "13085"]


def test_contract_rejects_month_first_dates():
    with pytest.raises(load.ContractError, match="dd/mm"):
        load.validate(_raw([["1", "10001", "X", "2", "2009-12-01 07:45", "1.5", "13085", "UK"]]), "t")


def test_contract_rejects_missing_column():
    with pytest.raises(load.ContractError, match="missing"):
        load.validate(_raw([["1", "10001", "X", "2", "01/12/2009 07:45", "1.5", "13085", "UK"]]).drop(
            columns="Price"), "t")


def test_load_handles_byte_order_mark(tmp_path):
    header = "Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country\n"
    line = "1,10001,X,2,01/12/2009 07:45,1.5,13085,United Kingdom\n"
    for name in load.FILES:
        (tmp_path / name).write_text(header + line, encoding="utf-8-sig")
    df = load.load(tmp_path)
    assert "Invoice" in df.columns and len(df) == 2


def _frame():
    t = pd.Timestamp
    rows = [
        # file 1
        ("100", "10001", 2, t("2010-11-30 10:00"), 2.0, "12001", 1),   # purchase
        ("100", "10002", 1, t("2010-12-05 10:00"), 3.0, "12001", 1),   # purchase, later copied into file 2
        ("C101", "10001", -1, t("2010-11-30 11:00"), 2.0, "12001", 1),  # return
        ("102", "10003", 1, t("2010-11-01 10:00"), 5.0, None, 1),       # missing customer
        ("103", "POST", 1, t("2010-11-01 10:00"), 18.0, "12001", 1),    # non-product
        ("104", "10004", 1, t("2010-11-01 10:00"), 0.0, "12001", 1),    # bad price
        ("105", "10005", -3, t("2010-11-01 10:00"), 1.0, "12001", 1),   # bad quantity
        ("106", "10006", 2, t("2010-11-02 10:00"), 1.0, "12002", 1),    # purchase
        ("106", "10006", 2, t("2010-11-02 10:00"), 1.0, "12002", 1),    # exact duplicate
        ("107", "gift_0001_20", 1, t("2010-11-03 10:00"), 17.0, "12002", 1),  # voucher
        # file 2
        ("100", "10002", 1, t("2010-12-05 10:00"), 3.0, "12001", 2),   # overlap copy
        ("200", "10001", 4, t("2011-01-10 10:00"), 2.0, "12002", 2),   # purchase
    ]
    df = pd.DataFrame(rows, columns=["Invoice", "StockCode", "Quantity", "InvoiceDate", "Price", "Customer ID",
                                     "source_file"])
    df["Description"], df["Country"] = "X", "United Kingdom"
    df["Customer ID"] = df["Customer ID"].astype("string")
    return df


def test_every_row_lands_in_exactly_one_bucket_and_value_reconciles():
    res = clean.clean(_frame())
    log = res.log.set_index("reason")
    assert log.loc["purchase", "rows"] == 4
    assert log.loc["return", "rows"] == 1
    for reason in ("overlap_duplicate", "missing_customer", "bad_price", "bad_quantity", "exact_duplicate"):
        assert log.loc[reason, "rows"] == 1, reason
    assert log.loc["non_product", "rows"] == 2
    assert res.reconciliation["balanced"]
    assert res.reconciliation["accounted_rows"] == len(_frame())
    assert res.overlap_check == {"rows": 1, "matched": 1, "unmatched": 0, "from": "2010-12-05",
                                 "to": "2010-12-05"}


def test_first_rule_wins():
    df = _frame()
    # A POST line with no customer: missing_customer comes before non_product.
    extra = df.iloc[[4]].copy()
    extra["Customer ID"] = pd.NA
    res = clean.clean(pd.concat([df, extra], ignore_index=True))
    assert res.log.set_index("reason").loc["missing_customer", "rows"] == 2

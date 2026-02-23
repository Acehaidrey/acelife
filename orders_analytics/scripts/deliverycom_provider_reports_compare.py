import pandas as pd
from decimal import Decimal, ROUND_HALF_UP

PROV_PATH = "orders_analytics/data/raw/deliverycom/orders_from_provider_reports.csv"
BILL_PATH = "orders_analytics/data/raw/deliverycom/billings_raw.csv"
OUT_PATH = "orders_analytics/data/raw/deliverycom/provider_reports_vs_billings_differences.csv"


def to_decimal(val):
    if pd.isna(val):
        return None
    try:
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def compute_commission(df, service_col, pct_col, tx_col):
    service = df[service_col].apply(to_decimal).fillna(Decimal("0.00"))
    pct = df[pct_col].apply(to_decimal).fillna(Decimal("0.00"))
    tx = df[tx_col].apply(to_decimal).fillna(Decimal("0.00"))
    return (service - pct - tx).apply(lambda x: x.quantize(Decimal("0.01")))


def main():
    prov = pd.read_csv(PROV_PATH, dtype=str)
    bill = pd.read_csv(BILL_PATH, dtype=str)

    prov["order_id"] = prov["Order_Id"].astype(str)
    bill["order_id"] = bill["order_id"].astype(str)

    prov_comm = compute_commission(
        prov,
        "Service_Fee_For_Invoice",
        "CC_Percent_Fee_For_Invoice",
        "CC_Transaction_Fee_For_Invoice",
    )
    bill_comm = compute_commission(
        bill,
        "service_fee",
        "account_cc_percent_fee",
        "account_cc_transaction_fee",
    )

    prov = prov.assign(provider_commission=prov_comm)
    bill = bill.assign(billing_commission=bill_comm)

    merged = prov[["order_id", "provider_commission"]].merge(
        bill[["order_id", "billing_commission"]],
        on="order_id",
        how="outer",
        indicator=True,
    )

    def diff_row(row):
        if row["_merge"] != "both":
            return True
        if row["provider_commission"] is None or row["billing_commission"] is None:
            return True
        return abs(row["provider_commission"] - row["billing_commission"]) > Decimal("0.01")

    merged = merged[merged.apply(diff_row, axis=1)].copy()
    merged["diff"] = (
        merged.apply(
            lambda r: "" if r["_merge"] != "both" else f"{(r['provider_commission'] - r['billing_commission']):.2f}",
            axis=1,
        )
    )
    merged.to_csv(OUT_PATH, index=False)
    print(f"Wrote {len(merged)} row(s) -> {OUT_PATH}")


if __name__ == "__main__":
    main()

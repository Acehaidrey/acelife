from __future__ import annotations


VA_TASK_SHEET = "1bnwEN-yY-ton6VLbAxyuu13LeAUzUAF9G_G6KCQ5Mro"

SHEETS = {
    "chownow_manual_missing_orders": {
        "sheet_id": VA_TASK_SHEET,
        "gid": "2049893089",
        "format": "csv",
        "out": "orders_analytics/data/raw/chownow/chownow_manual_missing_orders.csv",
    },
    "ezcater_order_history": {
        "sheet_id": VA_TASK_SHEET,
        "gid": "391969615",
        "format": "csv",
        "out": "Takeout/GoogleSheets/ezcater_order_history.csv",
    },
    "grubhub_order_history": {
        "sheet_id": VA_TASK_SHEET,
        "gid": "104633095",
        "format": "csv",
        "out": "Takeout/GoogleSheets/grubhub_order_history.csv",
    },
    "slice_order_history": {
        "sheet_id": VA_TASK_SHEET,
        "gid": "1537424369",
        "format": "csv",
        "out": "Takeout/GoogleSheets/slice_order_history.csv",
    },
    "beyond_menu_order_history": {
        "sheet_id": VA_TASK_SHEET,
        "gid": "1752158193",
        "format": "csv",
        "out": "orders_analytics/data/raw/beyondmenu/beyond_menu_order_history.csv",
    },
    "beyond_menu_annual_billing_summary": {
        "sheet_id": VA_TASK_SHEET,
        "gid": "89032459",
        "format": "csv",
        "out": "orders_analytics/data/raw/beyondmenu/beyond_menu_annual_billing_summary.csv",
    },
    "monthly_finance_report_history": {
        "sheet_id": VA_TASK_SHEET,
        "gid": "1693982203",
        "format": "csv",
        "out": "Takeout/GoogleSheets/monthly_finance_report_history.csv",
    },
}

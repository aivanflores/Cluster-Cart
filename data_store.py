"""
Adding new transactions to the system (used by the dashboard's upload feature).

A new transaction line is inserted into MySQL's `transactions` table; a line identical to
one already stored is skipped, so uploading the same file twice never counts anything twice.
RFM is then recomputed for every affected customer, and only customers who are new or whose
RFM changed get a (possibly new) segment from the saved classifier -- everyone else keeps the
segment they already have. Recommendations always come from the segment_rules table that
main.py built with Association Rule Mining; an upload does not re-run the rule mining.
"""
import pandas as pd

import db
from classification import assign_segments
from rfm import compute_rfm


def add_transactions(new_transactions):
    """
    new_transactions: a table in the `transactions` table's column format
    (see db.to_transactions_table). Returns a summary dictionary for the dashboard to display.
    """
    added = db.add_transactions(new_transactions)
    already_stored = len(new_transactions) - added

    all_transactions = db.load_transactions()
    invoices = all_transactions.rename(columns={"customer_id": "Customer ID", "invoice": "Invoice",
                                                "invoice_date": "InvoiceDate", "total": "Total"})
    rfm, reference_date = compute_rfm(invoices)

    old = db.load_customers().set_index("customer_id")
    before = old[["recency", "frequency", "monetary"]].reindex(rfm.index)
    unchanged = ((before["recency"] == rfm["Recency"])
                & (before["frequency"] == rfm["Frequency"])
                & ((before["monetary"] - rfm["Monetary"]).abs() < 0.01))

    to_update = rfm[~unchanged]
    if not to_update.empty:
        scored = assign_segments(to_update).rename(columns={
            "Customer ID": "customer_id", "Recency": "recency",
            "Frequency": "frequency", "Monetary": "monetary", "Segment": "segment"})
        db.upsert_customers(scored)

    customers_now = db.load_customers().set_index("customer_id")
    affected_ids = new_transactions["customer_id"].unique()
    affected = customers_now.reindex(affected_ids).reset_index()
    affected["Previous segment"] = affected["customer_id"].map(old["segment"])
    affected.insert(1, "Status", ["New customer" if pd.isna(previous) else "Existing customer"
                                  for previous in affected["Previous segment"]])

    recommendations = db.top_recommendations().set_index("segment")["recommendation"]
    affected["Recommendation"] = affected["segment"].map(recommendations)

    new_segment_by_id = customers_now["segment"].reindex(old.index)
    return {
        "affected": affected.rename(columns={"customer_id": "Customer ID", "recency": "Recency",
                                              "frequency": "Frequency", "monetary": "Monetary",
                                              "segment": "Segment"}),
        "new_customers": int((affected["Status"] == "New customer").sum()),
        "existing_customers": int((affected["Status"] == "Existing customer").sum()),
        "already_stored": int(already_stored),
        "moved": int((new_segment_by_id != old["segment"]).sum()),
        "total_customers": len(customers_now),
        "reference_date": reference_date,
    }


def reset_to_original():
    """Undo all uploads: go back to the data that main.py created."""
    db.restore_snapshot()

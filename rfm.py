"""
Steps 4 and 5: compute RFM per customer, then scale it.
"""
import numpy as np
import pandas as pd
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler, FunctionTransformer

from config import RFM_COLUMNS, USE_LOG


def make_invoice_table(df):
    """
    Shrink the transactions to one row per invoice: Customer ID, Invoice, InvoiceDate, Total.
    This is all we need to compute RFM, and it is small enough to store, so new
    transactions can be added later without needing the huge original file.
    """
    invoice = df["Invoice"].astype(str).str.replace(r"\.0$", "", regex=True)      # "536365.0" -> "536365"
    df = df.assign(Invoice=invoice, Total=df["Quantity"] * df["Price"])
    return df.groupby(["Customer ID", "Invoice"], as_index=False).agg(
        InvoiceDate=("InvoiceDate", "max"),
        Total=("Total", "sum"),
    )


def compute_rfm(invoices):
    """
    One row per customer, from the invoice table:
      Recency   = days between the customer's last purchase and the most recent date in the data
      Frequency = number of different invoices
      Monetary  = total spent
    """
    reference_date = invoices["InvoiceDate"].max()                # acts as "today"

    rfm = invoices.groupby("Customer ID").agg(
        LastPurchase=("InvoiceDate", "max"),
        Frequency=("Invoice", "nunique"),
        Monetary=("Total", "sum"),
    )
    rfm["Recency"] = (reference_date - rfm["LastPurchase"]).dt.days
    rfm = rfm[RFM_COLUMNS].round({"Monetary": 2})
    return rfm, reference_date


def scale_rfm(rfm):
    """
    K-Means uses distances, so a big-number column (Monetary) would overpower a
    small-number column (Frequency). Scaling puts all three on the same footing.
    Returns the fitted scaler (needed later for new customers) and the scaled values.
    """
    if USE_LOG:
        scaler = make_pipeline(FunctionTransformer(np.log1p), StandardScaler())
    else:
        scaler = StandardScaler()

    X_scaled = scaler.fit_transform(rfm[RFM_COLUMNS])
    return scaler, X_scaled

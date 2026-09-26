"""
Step 3: load and clean the data.
"""
import io

import pandas as pd

from config import DATA_FILE, SHEET_NAME, CACHE_FILE

# Some versions of the dataset use different column names, so we make them match
COLUMN_RENAMES = {"InvoiceNo": "Invoice", "UnitPrice": "Price", "CustomerID": "Customer ID"}
REQUIRED_COLUMNS = ["Invoice", "Quantity", "InvoiceDate", "Price", "Customer ID"]


def load_data():
    """Read the Kaggle file. Excel is slow, so we save a CSV copy the first time."""
    if CACHE_FILE.exists():
        return pd.read_csv(CACHE_FILE, dtype={"Invoice": str, "StockCode": str},
                           parse_dates=["InvoiceDate"])

    raw = pd.read_excel(DATA_FILE, sheet_name=SHEET_NAME)
    raw = raw.rename(columns=COLUMN_RENAMES)
    raw.to_csv(CACHE_FILE, index=False)
    return raw


def clean_data(raw):
    """
    Remove unusable rows and keep a log of how many rows are left after each step.
    Returns the clean data and the log (as a table).
    """
    log = [{"Step": "Raw data", "Rows remaining": len(raw), "Rows removed": 0}]

    def log_step(label, data):
        before = log[-1]["Rows remaining"]
        log.append({"Step": label, "Rows remaining": len(data), "Rows removed": before - len(data)})

    df = raw.dropna(subset=["Customer ID"])                       # 1. no customer = unusable
    log_step("Removed missing Customer ID", df)

    df = df[~df["Invoice"].astype(str).str.startswith("C")]       # 2. cancellations start with "C"
    log_step("Removed cancellations (Invoice starts with 'C')", df)

    df = df[df["Quantity"] > 0]                                   # 3. returns not caught by the "C" flag
    log_step("Removed negative Quantity", df)

    df = df[df["Price"] > 0]                                      # 4. free items / data-entry errors
    log_step("Removed zero Price", df)

    df = df.copy()
    df["Customer ID"] = df["Customer ID"].astype(int)             # 12346.0 -> 12346
    return df, pd.DataFrame(log)


def prepare_uploaded_data(df):
    """
    Get a file uploaded in the dashboard ready for clean_data():
    fix the column names, check the required columns exist, and fix the data types.
    """
    df = df.rename(columns=lambda name: str(name).strip()).rename(columns=COLUMN_RENAMES)

    missing = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing)
                         + ". The file needs: " + ", ".join(REQUIRED_COLUMNS) + ".")

    df = df.copy()
    # StockCode/Description are optional for RFM, but the recommendations (Step 8) are
    # built from them, so an upload without these columns just won't affect those patterns.
    if "StockCode" not in df.columns:
        df["StockCode"] = "UNKNOWN"
    if "Description" not in df.columns:
        df["Description"] = "UNKNOWN ITEM"
    df["Invoice"] = df["Invoice"].astype(str)
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    for column in ["Quantity", "Price", "Customer ID"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")     # bad values become empty, then get removed

    return df.dropna(subset=["InvoiceDate"])


def read_uploaded_file(file_bytes, file_name):
    """Read a .csv or .xlsx file uploaded in the dashboard (Excel: first sheet only)."""
    if file_name.lower().endswith(".csv"):
        try:
            return pd.read_csv(io.BytesIO(file_bytes), low_memory=False)
        except UnicodeDecodeError:                                  # some CSV files are not UTF-8
            return pd.read_csv(io.BytesIO(file_bytes), low_memory=False, encoding="latin-1")
    return pd.read_excel(io.BytesIO(file_bytes))

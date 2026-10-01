"""
MySQL storage for ClusterCart (matches a fresh XAMPP install: root user, no password, localhost).
Start the MySQL module in the XAMPP Control Panel before running main.py or app.py.

Tables:
  transactions            one row per purchased item line (used for RFM and for Association Rule Mining)
  customers               one row per customer: RFM values + segment
  segment_rules           the Association Rule Mining results per segment (Step 8 recommendations)
  transactions_original, customers_original   snapshots made by main.py, used by the dashboard's "Undo uploads"
"""
from sqlalchemy import create_engine, text

from config import DB_CONFIG

TRANSACTION_COLUMNS = {
    "Invoice": "invoice", "StockCode": "stock_code", "Description": "description",
    "Quantity": "quantity", "InvoiceDate": "invoice_date", "Price": "price",
    "Customer ID": "customer_id",
}


def _url(include_db=True):
    db_name = f"/{DB_CONFIG['database']}" if include_db else ""
    return (f"mysql+pymysql://{DB_CONFIG['user']}:{DB_CONFIG['password']}"
            f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}{db_name}")


def get_engine():
    return create_engine(_url())


def to_transactions_table(df):
    """
    Turn a cleaned dataframe (Invoice, StockCode, Description, Quantity, InvoiceDate,
    Price, Customer ID) into the column names the `transactions` table uses.
    """
    for missing, default in [("StockCode", "UNKNOWN"), ("Description", "UNKNOWN ITEM")]:
        if missing not in df.columns:
            df = df.assign(**{missing: default})

    out = df.rename(columns=TRANSACTION_COLUMNS)[list(TRANSACTION_COLUMNS.values())].copy()
    out["invoice"] = out["invoice"].astype(str)
    out["description"] = out["description"].fillna("UNKNOWN ITEM").astype(str).str.strip()
    out["customer_id"] = out["customer_id"].astype(int)
    out["total"] = (out["quantity"] * out["price"]).round(2)

    # The Online Retail II file itself contains some exact-duplicate lines (same invoice,
    # product, customer, quantity, price and time) -- keep one copy of each, matching the
    # `unique_line` key in the transactions table, so main.py can save this without errors.
    dedup_columns = ["invoice", "stock_code", "customer_id", "quantity", "price", "invoice_date"]
    return out.drop_duplicates(subset=dedup_columns, keep="first")


# ---------------- Setup ----------------
def init_database():
    """Create the database and tables if they do not exist yet. Safe to call every run."""
    server = create_engine(_url(include_db=False))
    with server.begin() as conn:
        conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {DB_CONFIG['database']}"))

    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS transactions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                invoice VARCHAR(20) NOT NULL,
                stock_code VARCHAR(20),
                description VARCHAR(255),
                quantity INT NOT NULL,
                invoice_date DATETIME NOT NULL,
                price DECIMAL(10,2) NOT NULL,
                customer_id INT NOT NULL,
                total DECIMAL(12,2) NOT NULL,
                UNIQUE KEY unique_line (invoice, stock_code, customer_id, quantity, price, invoice_date),
                INDEX (customer_id), INDEX (invoice)
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS customers (
                customer_id INT PRIMARY KEY,
                recency INT NOT NULL,
                frequency INT NOT NULL,
                monetary DECIMAL(12,2) NOT NULL,
                segment VARCHAR(50) NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS segment_rules (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                segment VARCHAR(50) NOT NULL,
                rank_in_segment INT NOT NULL,
                antecedents VARCHAR(255) NOT NULL,
                consequents VARCHAR(255) NOT NULL,
                support DECIMAL(6,4) NOT NULL,
                confidence DECIMAL(6,4) NOT NULL,
                lift DECIMAL(8,4) NOT NULL,
                recommendation TEXT NOT NULL
            )
        """))
        conn.execute(text("CREATE TABLE IF NOT EXISTS transactions_original LIKE transactions"))
        conn.execute(text("CREATE TABLE IF NOT EXISTS customers_original LIKE customers"))


def has_data():
    """True once main.py has run at least once."""
    with get_engine().connect() as conn:
        return conn.execute(text("SELECT COUNT(*) FROM customers")).scalar() > 0


# ---------------- Transactions ----------------
def replace_transactions(df):
    """Overwrite the transactions table (used by main.py for a full rebuild from the Excel file)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE transactions"))
    df.to_sql("transactions", engine, if_exists="append", index=False, chunksize=2000)


def add_transactions(df):
    """
    Insert new transaction lines (used by the dashboard's upload feature).
    A line identical to one already stored is skipped, so re-uploading a file never
    counts anything twice. Returns how many lines were actually added.
    """
    engine = get_engine()
    with engine.begin() as conn:
        df.to_sql("_incoming", conn, if_exists="replace", index=False)
        result = conn.execute(text("""
            INSERT IGNORE INTO transactions (invoice, stock_code, description, quantity,
                                             invoice_date, price, customer_id, total)
            SELECT invoice, stock_code, description, quantity, invoice_date, price, customer_id, total
            FROM _incoming
        """))
        conn.execute(text("DROP TABLE _incoming"))
        return result.rowcount


def load_transactions():
    import pandas as pd
    return pd.read_sql("SELECT * FROM transactions", get_engine(), parse_dates=["invoice_date"])

def customer_items(customer_id):
    """Every product one customer bought, with total units, biggest first."""
    import pandas as pd
    query = text("""
        SELECT description, SUM(quantity) AS units
        FROM transactions WHERE customer_id = :cid
        GROUP BY description ORDER BY units DESC
    """)
    return pd.read_sql(query, get_engine(), params={"cid": int(customer_id)})


# ---------------- Customers ----------------
def replace_customers(df):
    """Overwrite the customers table (used by main.py for a full rebuild)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE customers"))
    df.to_sql("customers", engine, if_exists="append", index=False, chunksize=2000)


def upsert_customers(df):
    """Insert new customers, or update the RFM/segment of ones that already exist."""
    with get_engine().begin() as conn:
        for row in df.itertuples(index=False):
            conn.execute(text("""
                INSERT INTO customers (customer_id, recency, frequency, monetary, segment)
                VALUES (:customer_id, :recency, :frequency, :monetary, :segment)
                ON DUPLICATE KEY UPDATE recency=:recency, frequency=:frequency,
                                       monetary=:monetary, segment=:segment
            """), dict(customer_id=int(row.customer_id), recency=int(row.recency),
                       frequency=int(row.frequency), monetary=float(row.monetary),
                       segment=row.segment))


def load_customers():
    import pandas as pd
    return pd.read_sql("SELECT * FROM customers", get_engine())


# ---------------- Segment rules (Association Rule Mining) ----------------
def replace_segment_rules(df):
    """Overwrite the segment_rules table (used by main.py after each rule-mining run)."""
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE segment_rules"))
    df.to_sql("segment_rules", engine, if_exists="append", index=False, chunksize=1000)


def load_segment_rules():
    import pandas as pd
    return pd.read_sql("SELECT * FROM segment_rules ORDER BY segment, rank_in_segment", get_engine())


def top_recommendations():
    """One row per segment: its single best recommendation (rank_in_segment = 1)."""
    import pandas as pd
    return pd.read_sql("SELECT segment, recommendation FROM segment_rules WHERE rank_in_segment = 1",
                       get_engine())


# ---------------- Snapshots (for "Undo uploads") ----------------
def save_snapshot():
    """Copy the current transactions/customers into *_original. Called once by main.py."""
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE TABLE transactions_original"))
        conn.execute(text("INSERT INTO transactions_original SELECT * FROM transactions"))
        conn.execute(text("TRUNCATE TABLE customers_original"))
        conn.execute(text("INSERT INTO customers_original SELECT * FROM customers"))


def restore_snapshot():
    """Undo uploads: copy transactions_original/customers_original back over the live tables."""
    with get_engine().begin() as conn:
        conn.execute(text("TRUNCATE TABLE transactions"))
        conn.execute(text("INSERT INTO transactions SELECT * FROM transactions_original"))
        conn.execute(text("TRUNCATE TABLE customers"))
        conn.execute(text("INSERT INTO customers SELECT * FROM customers_original"))

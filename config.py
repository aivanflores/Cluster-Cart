"""
Settings for ClusterCart. Change things here, not inside the other files.
"""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent          # the folder this file is in

# ---------------- Data ----------------
DATA_FILE  = BASE_DIR / "online_retail_II.xlsx"     # the Kaggle file
SHEET_NAME = "Year 2010-2011"                       # only this sheet is in scope
CACHE_FILE = BASE_DIR / "retail_2010_2011.csv"      # fast copy made on the first run

# ---------------- Database (MySQL, via XAMPP) ----------------
# Matches a fresh XAMPP install: MySQL on localhost, user "root", no password.
# Start the MySQL module in the XAMPP Control Panel before running main.py or app.py.
# If your MySQL root user has a password, put it here.
DB_CONFIG = {
    "host":     "localhost",
    "port":     3306,
    "user":     "root",
    "password": "",
    "database": "clustercart",
}

# ---------------- Model settings ----------------
CHOSEN_K      = 4          # number of segments (confirm with the elbow + silhouette results)
USE_LOG       = False      # True = log-transform RFM before scaling (helps with skewed data)
MANUAL_LABELS = {}         # optional override, e.g. {0: "Loyal Customers", 1: "Inactive Customers"}
RANDOM_STATE  = 42         # keeps results the same every run

# ---------------- Association Rule Mining (Step 8: campaign recommendations) ----------------
MIN_SUPPORT      = 0.02    # a product combination must appear in at least this fraction of orders
MIN_CONFIDENCE   = 0.30    # a rule must be true at least this often to be kept
TOP_N_ITEMS      = 200     # only look at the N best-selling products (keeps this fast to run)
RULES_PER_SEGMENT = 5      # how many rules to keep and store for each segment

# ---------------- Output (charts + the saved classifier; the data itself lives in MySQL) ----------------
OUTPUT_DIR = BASE_DIR / "outputs"
SHOW_PLOTS = False         # True = also open charts in a window (they are always saved as PNG)

# ---------------- Fixed values ----------------
RFM_COLUMNS = ["Recency", "Frequency", "Monetary"]

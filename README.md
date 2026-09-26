# ClusterCart – Customer Segmentation and Targeted Marketing Recommendation System

## Files
| File | What it does |
|---|---|
| `config.py` | All settings: database connection, model settings (K), Association Rule Mining settings |
| `db.py` | MySQL storage: creates the database/tables, saves and loads customers/transactions/rules |
| `cleaning.py` | Step 3 – load and clean the data |
| `rfm.py` | Steps 4–5 – compute RFM and scale it |
| `clustering.py` | Step 6 – find K, run K-Means, name the segments, charts |
| `classification.py` | Step 7 – Decision Tree vs KNN, assign new customers to a segment |
| `association.py` | Step 8 – **Association Rule Mining** (FP-Growth), replaces the old fixed if/else lookup |
| `main.py` | Runs everything in order (Steps 3–8) and saves the results to MySQL |
| `data_store.py` | Adds uploaded transactions to MySQL (used by the dashboard) |
| `app.py` | Streamlit dashboard: segment overview, ARM-based recommendations, upload, filterable table |

## Tech stack
| Purpose | Tool |
|---|---|
| Language | Python |
| Data cleaning, RFM | Pandas, NumPy |
| Scaling | Scikit-learn (preprocessing) |
| Clustering | Scikit-learn (KMeans) |
| Classification | Scikit-learn (tree, neighbors) |
| **Recommendations** | **Association Rule Mining — FP-Growth via `mlxtend`** (not if/else) |
| Database | **MySQL, via XAMPP** |
| Python ↔ MySQL | SQLAlchemy + PyMySQL |
| Web app / dashboard | Streamlit + Altair |
| Exploratory visualization (dev-side) | Matplotlib |
| Model storage | joblib |

## Setup (once)
1. **Install XAMPP** (if you haven't) and open the **XAMPP Control Panel**. Click **Start** next to **MySQL**. You do not need to start Apache — Flask/Streamlit is not used here, and this app runs its own server.
2. Put `online_retail_II.xlsx` in this folder.
3. Open a terminal inside this folder and set up Python:

| Step | Mac | Windows |
|---|---|---|
| Create venv | `python3 -m venv .venv` | `python -m venv .venv` |
| Activate venv | `source .venv/bin/activate` | `.venv\Scripts\activate` (PowerShell: `.venv\Scripts\Activate.ps1`) |
| Install libraries | `pip install -r requirements.txt` | `pip install -r requirements.txt` |

4. If your MySQL root user has a password (most fresh XAMPP installs do not), open `config.py` and fill in `DB_CONFIG["password"]`.

## Run
| Step | Mac | Windows |
|---|---|---|
| 1. Build the database (first run takes 1–3 min) | `python main.py` | `python main.py` |
| 2. Open the dashboard | `streamlit run app.py` | `streamlit run app.py` |

Stop the dashboard with Ctrl+C. You can browse the tables directly at `http://localhost/phpmyadmin` → database `clustercart`.

## Dashboard tabs
- **Dashboard** – system totals, segment cards (customers, average R/F/M, ARM-based recommendation, "Download campaign list"), charts, and an expander showing the actual association rules behind each recommendation
- **New Customers** – assign one customer by typing RFM values, or upload a transactions file (.csv/.xlsx). The file can hold new customers only or new purchases of existing customers. The system cleans it, updates RFM for every customer, assigns segments automatically and **updates the Dashboard and Customer Table tabs**. A sample file can be downloaded from the page, and an "Undo uploads" button restores the original data.
- **Customer Table** – filter by segment, search by Customer ID, sort by clicking a column, download the filtered table

## How Step 8 (recommendations) works now
`main.py` groups each segment's orders and runs **FP-Growth** (an algorithm that finds the same
rules as Apriori, faster) to find products frequently bought together, using `mlxtend`. The
strongest rule per segment becomes that segment's recommendation, e.g. *"Customers who buy X
also buy Y 62% of the time (lift 3.1). Bundle or cross-promote these items for this segment."*
All the rules found (not just the top one) are saved in the `segment_rules` table and shown in
the dashboard's "How these recommendations were found" expander — useful for defending this in
front of your panel. A segment with too few orders to find a pattern gets a fallback message
instead of a rule.

## How uploads work
`main.py` stores one row per **purchased item line** in `outputs`'s MySQL equivalent, the
`transactions` table (not one row per invoice, because Association Rule Mining needs to know
which items were bought together). An upload inserts its lines (a line identical to one already
stored is skipped, so it's never counted twice), recomputes RFM for every customer, and gives a
segment to customers who are new or whose RFM changed — everyone else keeps their existing
segment. The model is **not** retrained and the four segments stay the same. **Recommendations
are not recalculated by an upload** — they stay as `main.py` last computed them; run it again to
refresh them from the newest data. Running `main.py` again also resets all uploads, since it
rebuilds the whole database from the Excel file.

## Power BI
`main.py` also exports `outputs/customer_segments.csv` for **Get Data → Text/CSV**, if you would
rather not connect Power BI to MySQL directly.

## Note on hosting
This app saves data to a MySQL database, so it needs a real MySQL server running — it cannot be
deployed to a plain static or serverless host without also hosting MySQL somewhere (e.g. a small
cloud MySQL instance) and pointing `DB_CONFIG` at it.

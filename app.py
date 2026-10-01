"""
ClusterCart dashboard (Streamlit)
Start MySQL in the XAMPP Control Panel, run main.py once, then:  streamlit run app.py
"""
import hashlib

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.exc import OperationalError

import db
from classification import assign_new_customer
from cleaning import clean_data, prepare_uploaded_data, read_uploaded_file
from data_store import add_transactions, reset_to_original
from rfm import make_invoice_table

st.set_page_config(page_title="ClusterCart", layout="wide")

st.html(
    """
    <style>
    /* Main tabs: nasa right side, itinaas para pumantay sa title */
    [role="tablist"] {
        justify-content: flex-end !important;
        gap: 1.75rem !important;
        position: relative;
        top: -4.8rem;
    }
    [role="tab"] {
        font-size: 1.35rem !important;   /* mas malaki nang konti, pero mas maliit sa title */
        font-weight: 600 !important;
    }

    /* Ibalik sa normal ang maliliit na tabs sa loob (Recency / Frequency / Monetary) */
    [role="tabpanel"] [role="tablist"] {
        justify-content: flex-start !important;
        gap: 0.5rem !important;
        top: 0;
    }
    [role="tabpanel"] [role="tab"] {
        font-size: 1rem !important;
    }
    </style>
    """
)

SAMPLE_FILE = """Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country
700001,85123A,SAMPLE ITEM A,6,2011-12-01 10:30:00,2.55,90001,United Kingdom
700002,22423,SAMPLE ITEM B,12,2011-12-05 14:10:00,4.95,90001,United Kingdom
700003,84029E,SAMPLE ITEM C,3,2011-11-02 09:00:00,3.75,90002,United Kingdom
"""


# ---------- Loading ----------
def load_customers():
    return db.load_customers().rename(columns={"customer_id": "Customer ID", "recency": "Recency",
                                                "frequency": "Frequency", "monetary": "Monetary",
                                                "segment": "Segment"})


def load_recommendations():
    return db.top_recommendations().set_index("segment")["recommendation"]


def load_segment_rules():
    rules = db.load_segment_rules()
    return rules[rules["antecedents"] != ""]      # drop the "not enough data" placeholder rows


def upload_and_add(file_bytes, file_name):
    """Read an uploaded transactions file, clean it, and add it to the system's data."""
    raw = read_uploaded_file(file_bytes, file_name)
    df, cleaning_log = clean_data(prepare_uploaded_data(raw))
    if df.empty:
        raise ValueError("No valid rows are left after cleaning (missing Customer ID, cancellations, "
                         "negative quantity, zero price). Please check the file.")

    transactions = db.to_transactions_table(df)
    summary = add_transactions(transactions)
    summary["cleaning_log"] = cleaning_log
    return summary


# ---------- Reusable pieces ----------
def csv_bytes(table):
    return table.to_csv(index=False).encode("utf-8")


def totals_row(data):
    """Whole-system totals, shown at the top of the Dashboard tab."""
    cols = st.columns(4)
    cols[0].metric("Total customers", f"{len(data):,}", border=True)
    cols[1].metric("Total revenue", f"£{data['Monetary'].sum():,.0f}", border=True)
    cols[2].metric("Avg orders / customer", f"{data['Frequency'].mean():.1f}", border=True)
    cols[3].metric("Avg spend / customer", f"£{data['Monetary'].mean():,.0f}", border=True)


def segment_overview(data, recommendations, key):
    """Segment cards (with campaign-list download), bar chart, scatter plot, and RFM distributions."""
    st.subheader("Segment profiles")
    profile = data.groupby("Segment").agg(
        Customers=("Customer ID", "count"),
        Recency=("Recency", "mean"),
        Frequency=("Frequency", "mean"),
        Monetary=("Monetary", "mean"),
    )

    for segment, row in profile.iterrows():
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([1.2, 1.5, 3, 1.4], vertical_alignment="center")
            with c1:
                st.markdown(f"**{segment}**")
                st.metric("Customers", f"{int(row['Customers']):,}")
            with c2:
                st.caption(
                    f"Avg Recency: {row['Recency']:.0f} days  \n"
                    f"Avg Frequency: {row['Frequency']:.1f} orders  \n"
                    f"Avg Monetary: £{row['Monetary']:,.0f}"
                )
            with c3:
                st.write(recommendations.get(segment, "No recommendation yet -- run main.py."))
            with c4:
                st.download_button(
                    "Download campaign list",
                    csv_bytes(data[data["Segment"] == segment]),
                    file_name=f"{segment.lower().replace(' ', '_')}_campaign_list.csv",
                    mime="text/csv",
                    key=f"{key}_download_{segment}",
                    on_click="ignore",
                )

        left, right = st.columns(2)
    with left:
        st.subheader("Customers per segment")
        counts = data["Segment"].value_counts().reset_index()
        counts.columns = ["Segment", "Customers"]
        st.altair_chart(
            alt.Chart(counts).mark_bar().encode(
                x=alt.X("Segment:N", sort="-y", title=None),
                y="Customers:Q",
                color=alt.Color("Segment:N", legend=None),
                tooltip=["Segment", "Customers"],
            ),
            width="stretch",
        )
        st.caption(
            "This chart shows how many customers belong to each segment. A taller bar means "
            "a bigger group. Use it to see where most of your customers are, and which segments "
            "are small but may be worth targeting, such as High-Spending Customers."
        )
    with right:
        st.subheader("Frequency vs Monetary")
        st.altair_chart(
            alt.Chart(data).mark_circle(size=30, opacity=0.5).encode(
                x=alt.X("Frequency:Q", scale=alt.Scale(type="log")),
                y=alt.Y("Monetary:Q", scale=alt.Scale(type="log")),
                color="Segment:N",
                tooltip=["Customer ID", "Recency", "Frequency", "Monetary", "Segment"],
            ).interactive(),
            width="stretch",
        )
        st.caption(
            "Each dot is one customer. The further right a dot is, the more orders that customer "
            "made. The higher up it is, the more they spent. The colors show their segment, so you "
            "can see how the groups separate. Both axes use a log scale so small and big spenders "
            "fit in one chart. Hover over a dot to see the customer's details."
        )

        SEGMENT_COLORS = {
        "High-Spending Customers": "#2a66c4",
        "Inactive Customers": "#93c6fa",
        "Loyal Customers": "#e8433a",
        "Regular Customers": "#f2aeab",
    }

    st.subheader("Revenue share per segment")
    revenue = data.groupby("Segment", as_index=False)["Monetary"].sum()
    revenue["Share"] = revenue["Monetary"] / revenue["Monetary"].sum()

    pie_col, text_col = st.columns([2, 1], vertical_alignment="center")
    with pie_col:
        st.altair_chart(
            alt.Chart(revenue).mark_arc(innerRadius=70).encode(
                theta=alt.Theta("Monetary:Q"),
                color=alt.Color(
                    "Segment:N",
                    scale=alt.Scale(domain=list(SEGMENT_COLORS), range=list(SEGMENT_COLORS.values())),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("Segment:N"),
                    alt.Tooltip("Monetary:Q", title="Revenue (£)", format=",.0f"),
                    alt.Tooltip("Share:Q", title="Share of revenue", format=".1%"),
                ],
            ).properties(height=320),
            width="stretch",
        )
    with text_col:
        legend_lines = "".join(
            f"<div style='margin-bottom:6px'><span style='color:{color}; font-size:1.1rem'>●</span> "
            f"{name}</div>"
            for name, color in SEGMENT_COLORS.items()
        )
        st.markdown(f"<div style='color:#6b6f80'><b>Segment</b>{legend_lines}</div>",
                    unsafe_allow_html=True)
        st.caption(
            "This chart shows how much of the total revenue comes from each segment. "
            "A bigger slice means that segment brings in more money. Compare it with the "
            "'Customers per segment' chart: a small group can still earn a big share of revenue. "
            "Hover over a slice to see the exact amount and percentage."
        )

    st.subheader("How each segment behaves (Recency, Frequency, Monetary)")
    st.caption(
        "Each dot is one customer. The box covers the middle 50% of customers in that segment, "
        "and the line inside it is the median. A higher box means higher values: more days since "
        "the last purchase (Recency), more orders (Frequency), or more spending (Monetary)."
    )
    metric_tabs = st.tabs(["Recency (days)", "Frequency (orders)", "Monetary (£)"])
    for tab, metric in zip(metric_tabs, ["Recency", "Frequency", "Monetary"]):
        with tab:
            log_scale = metric != "Recency"
            scale = alt.Scale(type="log") if log_scale else alt.Scale(type="linear")
            box = alt.Chart(data).mark_boxplot(size=40).encode(
                x=alt.X("Segment:N", title=None), y=alt.Y(f"{metric}:Q", scale=scale), color="Segment:N")
            points = alt.Chart(data).mark_circle(size=8, opacity=0.3).encode(
                x="Segment:N", y=alt.Y(f"{metric}:Q", scale=scale), color=alt.Color("Segment:N", legend=None))
            st.altair_chart((box + points).properties(height=320), width="stretch")


def recommendation_evidence(key):
    """Association Rule Mining results shown as a chart per segment."""
    rules = load_segment_rules()
    st.subheader("Product pairings per segment (Association Rule Mining)")
    st.caption(
        "Each bar is a rule: customers who buy the items on the left of the arrow also buy "
        "the items on the right. A longer bar (higher lift) means the items sell together much "
        "more than chance. A darker bar means the pairing is true more often (confidence)."
    )
    if rules.empty:
        st.write("No rules yet -- run main.py first.")
        return

    for column in ["support", "confidence", "lift"]:
        rules[column] = rules[column].astype(float)
    rules["Rule"] = (rules["antecedents"] + "  →  " + rules["consequents"]).str.slice(0, 80)

    segments = sorted(rules["segment"].unique())
    for tab, segment in zip(st.tabs(segments), segments):
        group = rules[rules["segment"] == segment]
        with tab:
            st.altair_chart(
                alt.Chart(group).mark_bar().encode(
                    x=alt.X("lift:Q", title="Lift (strength of the pairing)"),
                    y=alt.Y("Rule:N", sort="-x", title=None, axis=alt.Axis(labelLimit=450)),
                    color=alt.Color("confidence:Q", title="Confidence",
                                    scale=alt.Scale(scheme="blues", domain=[0, 1])),
                    tooltip=[
                        alt.Tooltip("antecedents:N", title="If they buy"),
                        alt.Tooltip("consequents:N", title="They also buy"),
                        alt.Tooltip("support:Q", format=".1%", title="Support"),
                        alt.Tooltip("confidence:Q", format=".0%", title="Confidence"),
                        alt.Tooltip("lift:Q", format=".2f", title="Lift"),
                    ],
                ).properties(height=60 * len(group) + 40),
                width="stretch",
            )
            with st.expander("See the full table"):
                st.dataframe(
                    group[["antecedents", "consequents", "support", "confidence", "lift"]],
                    hide_index=True, width="stretch", key=f"{key}_rules_{segment}",
                )


def customer_table(data, key):
    """Customer table you can filter by segment and Customer ID, with a download button."""
    all_segments = sorted(data["Segment"].unique())
    col1, col2 = st.columns(2)
    chosen = col1.multiselect("Segment", all_segments, default=all_segments, key=f"{key}_segments")
    search = col2.text_input("Search Customer ID", key=f"{key}_search")

    filtered = data[data["Segment"].isin(chosen)]
    if search.strip():
        filtered = filtered[filtered["Customer ID"].astype(str).str.contains(search.strip(), regex=False)]

    st.caption(f"Showing {len(filtered):,} of {len(data):,} customers. Click a column name to sort.")
    st.dataframe(filtered, width="stretch", hide_index=True)
    st.download_button("Download this table (CSV)", csv_bytes(filtered), file_name="customers.csv",
                       mime="text/csv", key=f"{key}_download", on_click="ignore")
    return filtered

def customer_details(row):
    """Details of one customer: segment, top purchases, and which segment rules fit them."""
    customer_id = int(row["Customer ID"])
    st.subheader(f"Customer {customer_id}")

    cols = st.columns(4)
    cols[0].metric("Segment", row["Segment"], border=True)
    cols[1].metric("Recency", f"{row['Recency']:.0f} days", border=True)
    cols[2].metric("Frequency", f"{row['Frequency']:.0f} orders", border=True)
    cols[3].metric("Monetary", f"£{float(row['Monetary']):,.0f}", border=True)

    items = db.customer_items(customer_id)
    items["units"] = items["units"].astype(float)
    bought = set(items["description"])

    st.markdown("**Most bought products**")
    st.altair_chart(
        alt.Chart(items.head(10)).mark_bar().encode(
            x=alt.X("units:Q", title="Units bought"),
            y=alt.Y("description:N", sort="-x", title=None, axis=alt.Axis(labelLimit=350)),
            tooltip=["description", "units"],
        ).properties(height=300),
        width="stretch",
    )

    rules = load_segment_rules()
    rules = rules[rules["segment"] == row["Segment"]].copy()
    if rules.empty:
        return

    def fit(rule):
        if not set(rule["antecedents"].split(", ")) <= bought:
            return "Not a fit yet"
        if set(rule["consequents"].split(", ")) <= bought:
            return "Already buys both"
        return "Recommend now"

    rules["Fit for this customer"] = rules.apply(fit, axis=1)
    st.markdown("**Rules from this customer's segment**")
    st.caption("'Recommend now' = the customer already buys the first items but not the "
               "paired items yet, so they are the best target for that offer.")
    st.dataframe(
        rules[["Fit for this customer", "antecedents", "consequents", "confidence", "lift"]],
        hide_index=True, width="stretch",
    )


# ---------- Page ----------
try:
    system_ready = db.has_data()
except OperationalError:
    st.error(
        "Could not connect to MySQL. Start the **MySQL** module in the XAMPP Control Panel, "
        "then refresh this page. If your MySQL root user has a password, add it in config.py "
        "(DB_CONFIG)."
    )
    st.stop()

if not system_ready:
    st.error("Results not found. Run main.py first (python main.py) to build the database.")
    st.stop()

customers = load_customers()
recommendations = load_recommendations()

st.title("ClusterCart")
st.caption("Customer Segmentation and Targeted Marketing Recommendation System")

tab_dashboard, tab_new, tab_table = st.tabs(["Dashboard", "New Customers", "Customer Table"])

# ----- Tab 1: overview of the existing customers -----
with tab_dashboard:
    totals_row(customers)
    st.divider()
    segment_overview(customers, recommendations, key="main")
    recommendation_evidence(key="main")

# ----- Tab 2: new customers (one at a time, or upload a file that updates the dashboard) -----
with tab_new:
    st.subheader("Assign one customer")
    c1, c2, c3 = st.columns(3)
    recency = c1.number_input("Recency (days since last purchase)", min_value=0, value=30)
    frequency = c2.number_input("Frequency (number of orders)", min_value=1, value=5)
    monetary = c3.number_input("Monetary (total spent, GBP)", min_value=0.0, value=500.0)

    if st.button("Assign segment"):
        segment = assign_new_customer(recency, frequency, monetary)
        st.success(f"Segment: {segment}")
        st.write(f"Recommended action: **{recommendations.get(segment, 'No recommendation yet.')}**")

    st.divider()
    st.subheader("Add new transactions (upload a file)")
    st.write(
        "Upload a transactions file (.csv or .xlsx) with the same columns as the Online Retail II data: "
        "Invoice, Quantity, InvoiceDate, Price, Customer ID (StockCode and Description are optional, "
        "but needed if you want these purchases to affect the recommendations). The file can contain "
        "new customers only, or new purchases of existing customers. The system cleans it, updates every "
        "customer's RFM, assigns segments automatically, and **updates the Dashboard and Customer Table "
        "tabs**. An invoice line that is already in the system is not counted twice."
    )
    st.download_button("Download sample file", SAMPLE_FILE, file_name="sample_transactions.csv",
                       mime="text/csv", on_click="ignore")

    version = st.session_state.setdefault("uploader_version", 0)
    uploaded = st.file_uploader("Transactions file", type=["csv", "xlsx"], key=f"uploader_{version}")

    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        file_id = hashlib.md5(file_bytes).hexdigest()
        if st.session_state.get("processed_file") != file_id:          # only add a file once
            st.session_state["last_update"] = None
            try:
                with st.spinner("Cleaning the data and updating the dashboard..."):
                    st.session_state["last_update"] = upload_and_add(file_bytes, uploaded.name)
                st.session_state["processed_file"] = file_id
            except Exception as error:
                st.error(f"Could not process the file: {error}")
            else:
                st.rerun()                                             # refresh the other tabs

    update = st.session_state.get("last_update")
    if update:
        st.success(f"Dashboard updated: {update['new_customers']} new customer(s) added and "
                   f"{update['existing_customers']} existing customer(s) recalculated. "
                   f"The system now has {update['total_customers']:,} customers.")
        if update["already_stored"]:
            st.info(f"{update['already_stored']} line(s) in the file were already in the system, "
                    "so they were not counted twice.")
        if update["moved"]:
            st.info(f"{update['moved']} existing customer(s) are now in a different segment.")
        st.caption(f"Reference date ('today' for Recency): {update['reference_date']:%Y-%m-%d}. "
                  "Recommendations are not recalculated by an upload -- run main.py to refresh those.")
        with st.expander("Cleaning log"):
            st.dataframe(update["cleaning_log"], hide_index=True)
        st.subheader("Customers in this file")
        customer_table(update["affected"], key="upload_table")

    with st.expander("Undo uploads"):
        st.write("Go back to the original data created by main.py. All uploaded transactions are removed.")
        if st.button("Reset to original data"):
            reset_to_original()
            st.session_state["uploader_version"] += 1                  # clears the file box
            st.session_state["processed_file"] = None
            st.session_state["last_update"] = None
            st.rerun()

# ----- Tab 3: browse the existing customers -----
# ----- Tab 3: browse the existing customers -----
with tab_table:
    filtered = customer_table(customers, key="table")
    if len(filtered) == 1:
        st.divider()
        customer_details(filtered.iloc[0])
    else:
        st.caption("Tip: type a full Customer ID in the search box to see that customer's details here.")

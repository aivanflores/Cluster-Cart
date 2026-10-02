"""
ClusterCart dashboard (Streamlit)
Start MySQL in the XAMPP Control Panel, run main.py once, then:  streamlit run app.py
"""
import base64
import hashlib
import html
import re

import altair as alt
import pandas as pd
import streamlit as st
from sqlalchemy.exc import OperationalError

import db
from classification import assign_new_customer
from cleaning import clean_data, prepare_uploaded_data, read_uploaded_file
from data_store import add_transactions, reset_to_original

st.set_page_config(page_title="ClusterCart", page_icon="🛒", layout="wide")

SAMPLE_FILE = """Invoice,StockCode,Description,Quantity,InvoiceDate,Price,Customer ID,Country
700001,85123A,SAMPLE ITEM A,6,2011-12-01 10:30:00,2.55,90001,United Kingdom
700002,22423,SAMPLE ITEM B,12,2011-12-05 14:10:00,4.95,90001,United Kingdom
700003,84029E,SAMPLE ITEM C,3,2011-11-02 09:00:00,3.75,90002,United Kingdom
"""

# ---------- Brand: colors, logo, segment icons ----------
CORAL = "#FF5A4F"
CORAL_DARK = "#D93A30"
CORAL_SOFT = "#FFF1EF"
INK = "#2B2D42"
MUTED = "#6B6F80"

LOGO_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
    '<rect width="48" height="48" rx="13" fill="#FF5A4F"/>'
    '<path d="M9 15h5l4 15h15l3-10H17" fill="none" stroke="#fff" stroke-width="3" '
    'stroke-linecap="round" stroke-linejoin="round"/>'
    '<circle cx="21" cy="36" r="2.7" fill="#fff"/><circle cx="32" cy="36" r="2.7" fill="#fff"/>'
    '<circle cx="23" cy="11" r="2.2" fill="#fff"/><circle cx="30" cy="8" r="2.2" fill="#fff"/>'
    '<circle cx="36" cy="13" r="2.2" fill="#fff"/></svg>'
)
LOGO_URI = "data:image/svg+xml;base64," + base64.b64encode(LOGO_SVG.encode()).decode()

# Simple line icons (drawn on a 48x48 grid)
ICONS = {
    "users": '<circle cx="24" cy="15" r="6"/><path d="M13 40c0-7 5-12 11-12s11 5 11 12"/>'
             '<circle cx="9" cy="21" r="4"/><path d="M3 38c0-5 2-8 6-9"/>'
             '<circle cx="39" cy="21" r="4"/><path d="M45 38c0-5-2-8-6-9"/>',
    "chart": '<rect x="9" y="29" width="7" height="12"/><rect x="20" y="21" width="7" height="20"/>'
             '<rect x="31" y="27" width="7" height="14"/><path d="M8 20l10-9 8 6 14-11"/><path d="M33 6h8v8"/>',
    "cart": '<path d="M5 9h6l5 23h22l4-16H13"/><circle cx="19" cy="39" r="2.8"/><circle cx="35" cy="39" r="2.8"/>',
    "card": '<rect x="5" y="11" width="38" height="26" rx="4"/><path d="M5 20h38M11 30h10"/>',
    "revenue": '<circle cx="24" cy="24" r="18"/><path d="M30 17c-1.5-1.5-3.5-2.3-6-2.3-3.5 0-6 1.8-6 4.5s2 4 6 5 6 2.3 6 5-2.5 4.8-6 4.8c-2.5 0-4.5-.8-6-2.3M24 11v26"/>',
    "star": '<path d="M24 5l5.6 12.4L43 19l-10 9.2L35.6 42 24 35.2 12.4 42 15 28.2 5 19l13.4-1.6z"/>',
    "shield": '<path d="M24 5l15 5.5V23c0 9.5-6.5 17-15 21-8.5-4-15-11.5-15-21V10.5z"/><path d="M16 24l6 6 11-12"/>',
    "tag": '<path d="M7 7h17l19 19-17 17L7 24z"/><circle cx="16" cy="16" r="3"/>',
    "clock": '<circle cx="24" cy="24" r="18"/><path d="M24 12v13l8 5"/>',
    "user-plus": '<circle cx="19" cy="15" r="7"/><path d="M5 41c0-8 6-13 14-13s14 5 14 13"/><path d="M38 14v12M32 20h12"/>',
    "refresh": '<path d="M39 20a15 15 0 0 0-27-5"/><path d="M10 7v9h9"/><path d="M9 28a15 15 0 0 0 27 5"/><path d="M38 41v-9h-9"/>',
    "swap": '<path d="M8 17h32M33 10l7 7-7 7"/><path d="M40 33H8M15 26l-7 7 7 7"/>',
}


# Same font as the rest of the site (set in .streamlit/config.toml) for every chart
FONT = "Plus Jakarta Sans"


@alt.theme.register("clustercart", enable=True)
def clustercart_theme():
    return alt.theme.ThemeConfig({"config": {
        "font": FONT,
        "axis": {"labelFont": FONT, "titleFont": FONT, "labelColor": MUTED, "titleColor": INK,
                 "titleFontWeight": 600, "gridColor": "#EEF0F4", "domainColor": "#D9DCE5"},
        "legend": {"labelFont": FONT, "titleFont": FONT, "labelColor": INK, "titleColor": INK},
        "title": {"font": FONT, "color": INK},
        "header": {"labelFont": FONT, "titleFont": FONT},
    }})


def icon_svg(name, size=28):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none" stroke="{INK}" '
           f'stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')
    image = base64.b64encode(svg.encode()).decode()
    return f'<img src="data:image/svg+xml;base64,{image}" width="{size}" height="{size}" alt="">'


# Icon and color for each segment type (matched by name, so renamed segments still work).
# Colors checked for color-blind separation and equal visual weight.
SEGMENT_STYLE = {
    "High-Spending": ("star", "#4453C7"),     # indigo
    "Loyal": ("shield", "#F2554A"),           # coral, ang accent ng site
    "Regular": ("tag", "#E3A21A"),            # amber
    "Inactive": ("clock", "#12A08C"),         # teal
}


def seg_style(name):
    for key, (icon, color) in SEGMENT_STYLE.items():
        if key.lower() in str(name).lower():
            return icon, color
    return "users", "#8D99AE"


def seg_icon_svg(name, size=30):
    return icon_svg(seg_style(name)[0], size)


def seg_color(name):
    return seg_style(name)[1]


def seg_scale(segments):
    names = sorted(set(segments))
    return alt.Scale(domain=names, range=[seg_color(name) for name in names])


def seg_slug(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).lower()).strip("_")


STATIC_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
:root { --nav-up: -2.4rem; --radius: 8px; }          /* raise or lower the nav bar to line up with the title */
.block-container, [data-testid="stVerticalBlockBorderWrapper"] { border-radius: var(--radius) !important; border-color: #E8EAF0 !important; } { padding-top: 5rem !important; }

/* ---------- Header ---------- */
.cc-kicker { color: #6B6F80; font-size: 0.95rem; margin-bottom: 0.35rem; }
.cc-brand { display: flex; align-items: center; gap: 0.8rem; font-size: 2.7rem;
            font-weight: 800; color: #2B2D42; line-height: 1.1; }
.cc-brand img { height: 3rem; width: 3rem; }
.cc-brand b { color: #FF5A4F; }

/* ---------- Nav tabs (right side) ---------- */
[role="tablist"] { justify-content: flex-end !important; gap: 1.75rem !important;
                   position: relative; top: var(--nav-up); }
[role="tab"] { background: #FFF1EF !important; border-radius: 6px !important;
               color: #2B2D42 !important; font-size: 1.7rem !important; font-weight: 700 !important;
               padding: 0.55rem 0.85rem !important; transition: background-color 0.15s ease, color 0.15s ease; }
[role="tab"]:hover { background: #FFE1DD !important; color: #2B2D42 !important; }
[role="tab"][aria-selected="true"] { background: #D93A30 !important; color: #FFFFFF !important; }
[role="tabpanel"] [role="tablist"] { justify-content: flex-start !important; gap: 0.5rem !important; top: 0 !important; }
[role="tabpanel"] [role="tab"] { font-size: 1rem !important; }
@media (max-width: 640px) {
    [role="tablist"] { justify-content: flex-start !important; gap: 0.4rem !important;
                                            position: static !important; top: 0 !important; flex-wrap: wrap !important; }
    [role="tab"] { font-size: 1.15rem !important; padding: 0.4rem 0.55rem !important; }
}

/* ---------- Buttons ---------- */
.stButton > button, .stDownloadButton > button { border-radius: var(--radius); font-weight: 600; }
.stDownloadButton > button { border: 1px solid #FF5A4F; color: #D93A30; }
.stDownloadButton > button:hover { background: #FFF1EF; border-color: #D93A30; color: #D93A30; }

/* ---------- KPI cards ---------- */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 1rem; }
.kpi { display: flex; align-items: center; gap: 1rem; background: #FFFFFF; border: 1px solid #E8EAF0;
       border-radius: var(--radius); padding: 1.1rem 1.3rem; }
.kpi-icon { width: 3.2rem; height: 3.2rem; border-radius: var(--radius); background: #F4F5F8;
            display: flex; align-items: center; justify-content: center; }
.kpi-label { color: #6B6F80; font-size: 0.9rem; }
.kpi-value { color: #FF5A4F; font-size: 1.8rem; font-weight: 800; line-height: 1.15; }

/* ---------- Segment cards ---------- */
.seg-head { display: flex; align-items: center; gap: 0.9rem; }
.seg-icon { width: 3.6rem; height: 3.6rem; border-radius: var(--radius); display: flex;
            align-items: center; justify-content: center; }
.seg-name { font-weight: 800; font-size: 1.15rem; color: #2B2D42; }
.seg-count { display: flex; align-items: center; gap: 0.45rem; font-size: 1.6rem; font-weight: 800; color: #2B2D42; line-height: 1.2; }
.seg-count-icon { display: flex; flex: 0 0 auto; }
.seg-bar { height: 8px; border-radius: 6px; background: #F1E4E2; margin-top: 0.7rem; overflow: hidden; }
.seg-bar div { height: 100%; border-radius: 6px; }
.stat-row { display: flex; gap: 0.6rem; flex-wrap: wrap; }
.stat { flex: 1; min-width: 5.5rem; background: #FFFFFF; border: 1px solid #E8EAF0; border-radius: var(--radius);
        padding: 0.55rem 0.7rem; }
.stat-label { color: #6B6F80; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; }
.stat-value { color: #2B2D42; font-size: 1.1rem; font-weight: 700; }
.reco-label, .reco-text { font-family: 'Inter', sans-serif; }
.reco-label { color: #D93A30; font-weight: 700; font-size: 0.8rem; text-transform: uppercase;
              letter-spacing: 0.05em; margin-bottom: 0.2rem; }
.reco-text { color: #2B2D42; font-size: 0.95rem; line-height: 1.45; }

/* ---------- Result card (New Customers) ---------- */
.result { display: flex; align-items: center; gap: 1rem; border-radius: var(--radius); padding: 1.1rem 1.3rem;
          background: #FF5A4F; color: #FFFFFF; }
.result-icon { width: 3.6rem; height: 3.6rem; border-radius: var(--radius); background: #FFFFFF;
               display: flex; align-items: center; justify-content: center; }
.result-label { opacity: 0.85; font-size: 0.85rem; }
.result-name { font-size: 1.6rem; font-weight: 800; line-height: 1.2; }
/* ---------- Footer ---------- */
.cc-footer { margin-top: 3rem; padding: 1.2rem 0 0.4rem; border-top: 1px solid #E8EAF0;
             display: flex; justify-content: space-between; flex-wrap: wrap; gap: 0.4rem 1.5rem;
             color: #6B6F80; font-size: 0.85rem; }
.cc-footer b { color: #2B2D42; font-weight: 600; }
.result-reco { margin-top: 0.8rem; color: #2B2D42; font-size: 0.95rem; }
</style>
"""


def segment_css(segments):
    rules = []
    for segment in segments:
        color = seg_color(segment)
        rules.append(
            f".st-key-seg_{seg_slug(segment)} {{ border-left: 5px solid {color} !important; "
            f"border-radius: var(--radius) !important; background: #FFFFFF !important; }}"
        )
    return "<style>" + "".join(rules) + "</style>"

st.html(STATIC_CSS)


# ---------- Loading ----------
def load_customers():
    table = db.load_customers().rename(columns={"customer_id": "Customer ID", "recency": "Recency",
                                                 "frequency": "Frequency", "monetary": "Monetary",
                                                 "segment": "Segment"})
    for column in ["Recency", "Frequency", "Monetary"]:
        table[column] = table[column].astype(float)
    return table


def load_recommendations():
    return db.top_recommendations().set_index("segment")["recommendation"]


def load_segment_rules():
    rules = db.load_segment_rules()
    return rules[rules["antecedents"] != ""]      # drop the "not enough data" placeholder rows


def prepare_upload_preview(file_bytes, file_name):
    """Read and clean an uploaded transactions file without saving it."""
    raw = read_uploaded_file(file_bytes, file_name)
    df, cleaning_log = clean_data(prepare_uploaded_data(raw))
    if df.empty:
        raise ValueError("No valid rows are left after cleaning (missing Customer ID, cancellations, "
                         "negative quantity, zero price). Please check the file.")
    return df, cleaning_log


def upload_and_add(df, cleaning_log):
    """Save a cleaned upload and return the dashboard summary."""
    summary = add_transactions(db.to_transactions_table(df))
    summary["cleaning_log"] = cleaning_log
    return summary


# ---------- Reusable pieces ----------
def csv_bytes(table):
    return table.to_csv(index=False).encode("utf-8")


def chart_header(title, description):
    """Title + short description together, so it is clear which chart they belong to."""
    st.subheader(title)
    st.caption(description)


def kpi_row(items):
    """Row of KPI cards. items = [(icon, label, value), ...]"""
    cards = "".join(
        f"<div class='kpi'><div class='kpi-icon'>{icon}</div>"
        f"<div><div class='kpi-label'>{label}</div><div class='kpi-value'>{value}</div></div></div>"
        for icon, label, value in items
    )
    st.html(f"<div class='kpi-grid'>{cards}</div>")


def totals_row(data):
    """Whole-system totals, shown at the top of the Dashboard tab."""
    kpi_row([
        (icon_svg("users"), "Total customers", f"{len(data):,}"),
        (icon_svg("revenue"), "Total revenue", f"£{data['Monetary'].sum():,.0f}"),
        (icon_svg("cart"), "Avg orders / customer", f"{data['Frequency'].mean():.1f}"),
        (icon_svg("card"), "Avg spend / customer", f"£{data['Monetary'].mean():,.0f}"),
    ])


def scatter_axis(title=None):
    """Few, very pale gridlines so the dots stand out (log scales draw many lines by default)."""
    return alt.Axis(title=title, tickCount=5, gridColor="#F3F4F7", gridWidth=0.6, domain=False, ticks=False)


def with_bar_labels(bars, field, fmt=",", horizontal=False):
    """Writes each bar's value at its end, so the axis is not needed to read it."""
    text = (bars.mark_text(align="left", baseline="middle", dx=5, fontSize=12, fontWeight=600) if horizontal
            else bars.mark_text(baseline="bottom", dy=-4, fontSize=12, fontWeight=600))
    return bars + text.encode(text=alt.Text(f"{field}:Q", format=fmt), color=alt.value(INK))


def scatter_highlight(everyone, highlight, height=360):
    """All customers as faint dots, with the chosen customers highlighted on top."""
    highlight = highlight.assign(Monetary=highlight["Monetary"].astype(float).clip(lower=1))
    everyone = everyone.assign(Monetary=everyone["Monetary"].astype(float).clip(lower=1))
    x = alt.X("Frequency:Q", scale=alt.Scale(type="log"), axis=scatter_axis("Frequency (orders)"))
    y = alt.Y("Monetary:Q", scale=alt.Scale(type="log"), axis=scatter_axis("Monetary (£)"))
    base = alt.Chart(everyone).mark_circle(size=22, opacity=0.35, color="#D9DCE5").encode(x=x, y=y)
    top = alt.Chart(highlight).mark_point(filled=True, size=230, stroke=INK, strokeWidth=1.5, opacity=1).encode(
        x=x, y=y,
        color=alt.Color("Segment:N", scale=seg_scale(highlight["Segment"]), title="Segment"),
        tooltip=["Customer ID", "Recency", "Frequency", "Monetary", "Segment"],
    )
    return (base + top).properties(height=height)


def open_segment_customers(segment):
    """Select a segment and navigate to its customers in the Customer Table tab."""
    st.session_state["table_segments_filter"] = [segment]
    st.session_state["table_search"] = ""
    st.session_state["main_tabs"] = "Customer Table"


def segment_overview(data, recommendations):
    """Segment profile cards, bar chart, scatter plot, revenue donut and RFM box plots."""
    profile = data.groupby("Segment").agg(
        Customers=("Customer ID", "count"),
        Recency=("Recency", "mean"),
        Frequency=("Frequency", "mean"),
        Monetary=("Monetary", "mean"),
    ).sort_values("Monetary", ascending=False)
    total = profile["Customers"].sum()
    st.html(segment_css(profile.index))

    st.subheader("Segment profiles")
    st.caption("The groups K-Means found, from highest to lowest average spend. Each card shows who is in "
               "the group, how they behave, and the campaign we recommend for them.")

    for segment, row in profile.iterrows():
        icon, color = seg_style(segment)
        share = row["Customers"] / total * 100
        reco = str(recommendations.get(segment, "No recommendation yet -- run main.py."))
        with st.container(border=True, key=f"seg_{seg_slug(segment)}"):
            c1, c2 = st.columns(2, vertical_alignment="top", gap="large")
            with c1:
                st.html(
                    f"<div class='seg-head'><div class='seg-icon' style='background:{color}26'>{seg_icon_svg(segment)}</div>"
                    f"<div><div class='seg-name'>{html.escape(str(segment))}</div>"
                    f"<div class='seg-count'><span class='seg-count-icon'>{icon_svg('users', 19)}</span>"
                    f"{int(row['Customers']):,}</div>"
                    f"</div></div>"
                )
                action_col, view_col = st.columns(2, gap="small")
                with action_col:
                    with st.expander("Recommended campaign"):
                        st.write(reco)
                with view_col:
                    st.button(
                        "View customers",
                        icon=":material/groups:",
                        width="stretch",
                        key=f"view_segment_{seg_slug(segment)}",
                        on_click=open_segment_customers,
                        args=(str(segment),),
                    )
            with c2:
                st.html(
                    "<div class='stat-row'>"
                    f"<div class='stat'><div class='stat-label'>Recency</div><div class='stat-value'>{row['Recency']:.0f} days</div></div>"
                    f"<div class='stat'><div class='stat-label'>Frequency</div><div class='stat-value'>{row['Frequency']:.1f} orders</div></div>"
                    f"<div class='stat'><div class='stat-label'>Monetary</div><div class='stat-value'>£{row['Monetary']:,.0f}</div></div>"
                    "</div>"
                )

    st.divider()
    scale = seg_scale(data["Segment"])
    left, right = st.columns(2, gap="large")
    with left:
        chart_header(
            "Customers per segment",
            "How many customers belong to each segment. A longer bar means a bigger group. "
            "Small segments, like High-Spending Customers, may still be worth targeting.",
        )
        counts = data["Segment"].value_counts().reset_index()
        counts.columns = ["Segment", "Customers"]
        st.altair_chart(
            with_bar_labels(alt.Chart(counts).mark_bar(cornerRadiusTopRight=8, cornerRadiusBottomRight=8).encode(
                y=alt.Y("Segment:N", sort="-x", title=None, axis=alt.Axis(labelLimit=220)),
                x=alt.X("Customers:Q"),
                color=alt.Color("Segment:N", scale=scale, legend=None),
                tooltip=["Segment", "Customers"],
            ), "Customers", horizontal=True).properties(height=320),
            width="stretch",
        )
    with right:
        chart_header(
            "Frequency vs Monetary",
            "Each dot is one customer. Further right means more orders, higher up means more "
            "spending. Colors show the segment. Hover over a dot for details.",
        )
        st.altair_chart(
            alt.Chart(data).mark_circle(size=30, opacity=0.55).encode(
                x=alt.X("Frequency:Q", scale=alt.Scale(type="log"), axis=scatter_axis("Frequency (orders)")),
                y=alt.Y("Monetary:Q", scale=alt.Scale(type="log"), axis=scatter_axis("Monetary (£)")),
                color=alt.Color("Segment:N", scale=scale),
                tooltip=["Customer ID", "Recency", "Frequency", "Monetary", "Segment"],
            ).interactive(),
            width="stretch",
        )

    st.divider()

    # ----- Share of customers vs share of revenue -----
    chart_header(
        "Share of customers vs share of revenue",
        "For each segment, the gray bar is its share of all customers and the coral bar is its share "
        "of all revenue. A coral bar taller than the gray one means the segment earns more than its "
        "size suggests; a shorter one means many customers but little money. Hover for the exact numbers.",
    )
    shares = data.groupby("Segment").agg(Customers=("Customer ID", "count"), Revenue=("Monetary", "sum"))
    shares["Share of customers"] = shares["Customers"] / shares["Customers"].sum()
    shares["Share of revenue"] = shares["Revenue"] / shares["Revenue"].sum()
    order = shares.sort_values("Share of revenue", ascending=False).index.tolist()
    shares = shares.reset_index().melt(
        id_vars=["Segment", "Customers", "Revenue"],
        value_vars=["Share of customers", "Share of revenue"], var_name="Measure", value_name="Share",
    )
    measures = ["Share of customers", "Share of revenue"]
    bars = alt.Chart(shares).encode(
        x=alt.X("Segment:N", sort=order, title=None, axis=alt.Axis(labelAngle=0, labelLimit=160)),
        xOffset=alt.XOffset("Measure:N", sort=measures),
        y=alt.Y("Share:Q", title="Share of total", axis=alt.Axis(format="%")),
    )
    st.altair_chart(
        (
            bars.mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                color=alt.Color("Measure:N", sort=measures, title=None,
                                scale=alt.Scale(domain=measures, range=["#6B7389", CORAL]),
                                legend=alt.Legend(orient="top")),
                tooltip=[
                    alt.Tooltip("Segment:N"),
                    alt.Tooltip("Measure:N", title="Measure"),
                    alt.Tooltip("Share:Q", format=".1%"),
                    alt.Tooltip("Customers:Q", format=","),
                    alt.Tooltip("Revenue:Q", title="Revenue (£)", format=",.0f"),
                ],
            )
            + bars.mark_text(dy=-8, fontSize=12, color=INK).encode(text=alt.Text("Share:Q", format=".0%"))
        ).properties(height=360),
        width="stretch",
    )

    st.divider()

    # ----- Box plots -----
    chart_header(
        "How each segment behaves (Recency, Frequency, Monetary)",
        "Each dot is one customer. The box covers the middle 50% of the segment and the line "
        "inside is the median. A higher box means more days since the last purchase (Recency), "
        "more orders (Frequency), or more spending (Monetary).",
    )
    metric_tabs = st.tabs(["Recency (days)", "Frequency (orders)", "Monetary (£)"])
    for tab, metric in zip(metric_tabs, ["Recency", "Frequency", "Monetary"]):
        with tab:
            axis_scale = alt.Scale(type="log") if metric != "Recency" else alt.Scale(type="linear")
            box = alt.Chart(data).mark_boxplot(size=40).encode(
                x=alt.X("Segment:N", title=None, axis=alt.Axis(labelAngle=0)),
                y=alt.Y(f"{metric}:Q", scale=axis_scale),
                color=alt.Color("Segment:N", scale=scale, legend=None))
            points = alt.Chart(data).mark_circle(size=8, opacity=0.3).encode(
                x="Segment:N", y=alt.Y(f"{metric}:Q", scale=axis_scale),
                color=alt.Color("Segment:N", scale=scale, legend=None))
            st.altair_chart((box + points).properties(height=320), width="stretch")


def recommendation_evidence(key):
    """Association Rule Mining results shown as a chart per segment."""
    rules = load_segment_rules()
    st.divider()
    chart_header(
        "Product pairings per segment (Association Rule Mining)",
        "Each bar is a rule: customers who buy the items on the left of the arrow also buy the items "
        "on the right. A longer bar (higher lift) means the items sell together much more than chance. "
        "A darker bar means the pairing is true more often (confidence).",
    )
    if rules.empty:
        st.write("No rules yet -- run main.py first.")
        return

    rules = rules.copy()
    for column in ["support", "confidence", "lift"]:
        rules[column] = rules[column].astype(float)
    rules["Rule"] = (rules["antecedents"] + "  →  " + rules["consequents"]).str.slice(0, 80)

    segments = sorted(rules["segment"].unique())
    for tab, segment in zip(st.tabs(list(segments)), segments):
        group = rules[rules["segment"] == segment]
        with tab:
            st.altair_chart(
                with_bar_labels(alt.Chart(group).mark_bar().encode(
                    x=alt.X("lift:Q", title="Lift (strength of the pairing)"),
                    y=alt.Y("Rule:N", sort="-x", title=None, axis=alt.Axis(labelLimit=450)),
                    color=alt.Color("confidence:Q", title="Confidence",
                                    scale=alt.Scale(range=["#FFD0CA", CORAL_DARK], domain=[0, 1])),
                    tooltip=[
                        alt.Tooltip("antecedents:N", title="If they buy"),
                        alt.Tooltip("consequents:N", title="They also buy"),
                        alt.Tooltip("support:Q", format=".1%", title="Support"),
                        alt.Tooltip("confidence:Q", format=".0%", title="Confidence"),
                        alt.Tooltip("lift:Q", format=".2f", title="Lift"),
                    ],
                ), "lift", fmt=".2f", horizontal=True).properties(height=60 * len(group) + 40),
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
    chosen = col1.multiselect(
        "Segment", all_segments, default=[], placeholder="Select segments", key=f"{key}_segments_filter",
    )
    search = col2.text_input("Search Customer ID", key=f"{key}_search", icon=":material/search:")

    filtered = data[data["Segment"].isin(chosen)] if chosen else data.iloc[0:0]
    if search.strip() and not chosen:
        filtered = data
    if search.strip():
        filtered = filtered[filtered["Customer ID"].astype(str).str.contains(search.strip(), regex=False)]

    if chosen or search.strip():
        st.caption(f"Showing {len(filtered):,} of {len(data):,} customers. Click a column name to sort.")
    else:
        st.caption("Select one or more segments or search by customer ID to view customers.")
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
        with_bar_labels(alt.Chart(items.head(10)).mark_bar(color=CORAL).encode(
            x=alt.X("units:Q", title="Units bought"),
            y=alt.Y("description:N", sort="-x", title=None, axis=alt.Axis(labelLimit=350)),
            tooltip=["description", "units"],
        ), "units", horizontal=True).properties(height=300),
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


# ---------- New Customers tab ----------
def assign_one_customer(customers, recommendations):
    """Form on the left; the result and a chart showing where the customer lands on the right."""
    st.subheader("Assign one customer")
    st.caption("Enter a new customer's RFM values to see which segment they belong to, "
               "and where they sit among your existing customers.")
    form_col, result_col = st.columns([1, 1.5], gap="large")

    with form_col:
        with st.container(border=True):
            recency = st.number_input("Recency (days since last purchase)", min_value=0, value=None,
                                      placeholder="30", key="new_customer_recency")
            frequency = st.number_input("Frequency (number of orders)", min_value=1, value=None,
                                        placeholder="5", key="new_customer_frequency")
            monetary = st.number_input("Monetary (total spent, GBP)", min_value=0.0, value=None,
                                       placeholder="500.00", key="new_customer_monetary")
            can_assign = all(value is not None for value in (recency, frequency, monetary))
            if st.button("Assign segment", type="primary", width="stretch",
                         disabled=not can_assign or st.session_state.get("assigning_segment", False)):
                st.session_state["assigning_segment"] = True
                try:
                    with st.spinner("Assigning segment..."):
                        segment = assign_new_customer(recency, frequency, monetary)
                    st.session_state["assigned"] = {"Customer ID": "New customer", "Recency": float(recency),
                                                    "Frequency": float(frequency), "Monetary": float(monetary),
                                                    "Segment": segment}
                finally:
                    st.session_state["assigning_segment"] = False

    with result_col:
        with st.container(border=True):
            assigned = st.session_state.get("assigned")
            if not assigned:
                st.caption("After filling the form, the chart will show up here.")
            else:
                segment = assigned["Segment"]
                reco = html.escape(str(recommendations.get(segment, "No recommendation yet.")))
                st.html(
                    f"<div class='result'><div class='result-icon' style='background:#FFFFFF'>{seg_icon_svg(segment)}</div>"
                    f"<div><div class='result-label'>Assigned segment</div>"
                    f"<div class='result-name'>{html.escape(str(segment))}</div></div></div>"
                    f"<div class='result-reco'><b>Recommended action:</b> {reco}</div>"
                )
                st.altair_chart(scatter_highlight(customers, pd.DataFrame([assigned]), height=300), width="stretch")
                st.caption("The big marker is the new customer. The faint dots are your existing customers, "
                           "so you can see which group they land in.")


@st.dialog("Reset to original data?", icon=":material/restore:")
def confirm_reset_dialog():
    st.write("All uploaded transactions will be removed. This cannot be undone.")
    confirm_col, cancel_col = st.columns(2)
    if confirm_col.button("Reset data", type="primary", width="stretch"):
        with st.spinner("Restoring original data..."):
            reset_to_original()
        st.session_state["uploader_version"] += 1
        st.session_state["processed_file"] = None
        st.session_state["upload_preview_id"] = None
        st.session_state["upload_preview"] = None
        st.session_state["upload_preview_error"] = None
        st.session_state["last_update"] = None
        st.rerun()
    if cancel_col.button("Cancel", width="stretch"):
        st.rerun()


def upload_section(customers):
    st.subheader("Add new transactions (upload a file)")
    st.write("Upload a CSV or Excel transactions file. Review the cleaned preview, then confirm to add it.")
    st.download_button("Download sample file", SAMPLE_FILE, file_name="sample_transactions.csv",
                       mime="text/csv", on_click="ignore")

    version = st.session_state.setdefault("uploader_version", 0)
    uploaded = st.file_uploader("Transactions file", type=["csv", "xlsx"], key=f"uploader_{version}")

    if uploaded is not None:
        file_bytes = uploaded.getvalue()
        file_id = hashlib.md5(file_bytes).hexdigest()
        if st.session_state.get("upload_preview_id") != file_id:
            st.session_state["upload_preview_id"] = file_id
            st.session_state["upload_preview"] = None
            st.session_state["upload_preview_error"] = None
            st.session_state["last_update"] = None
            try:
                with st.spinner("Cleaning the uploaded data..."):
                    cleaned, cleaning_log = prepare_upload_preview(file_bytes, uploaded.name)
                st.session_state["upload_preview"] = {"cleaned": cleaned, "cleaning_log": cleaning_log}
            except Exception as error:
                st.session_state["upload_preview_error"] = str(error)

        if st.session_state.get("upload_preview_error"):
            st.error(f"Could not read the file: {st.session_state['upload_preview_error']}")
        preview = st.session_state.get("upload_preview")
        if preview:
            cleaned = preview["cleaned"]
            st.caption(f"Cleaned preview: first 5 of {len(cleaned):,} valid rows. Nothing is saved yet.")
            st.dataframe(cleaned.head(5), hide_index=True, width="stretch")
            already_added = st.session_state.get("processed_file") == file_id
            if already_added:
                st.success("Transactions added. The Dashboard and Customer Table are updated.")
            if st.button("Confirm and add transactions", type="primary", icon=":material/save:",
                         disabled=already_added or st.session_state.get("upload_saving", False),
                         key=f"confirm_upload_{version}"):
                st.session_state["upload_saving"] = True
                st.session_state["processed_file"] = file_id
                try:
                    with st.spinner("Saving transactions and updating customer segments..."):
                        st.session_state["last_update"] = upload_and_add(
                            cleaned, preview["cleaning_log"],
                        )
                except Exception as error:
                    st.session_state["processed_file"] = None
                    st.error(f"Could not save the file: {error}")
                else:
                    st.rerun()
                finally:
                    st.session_state["upload_saving"] = False

    update = st.session_state.get("last_update")
    if update:
        st.success("Dashboard updated. The new customers are already counted in the Dashboard and Customer Table tabs.")
        kpi_row([
            (icon_svg("user-plus"), "New customers", f"{update['new_customers']:,}"),
            (icon_svg("refresh"), "Existing recalculated", f"{update['existing_customers']:,}"),
            (icon_svg("swap"), "Changed segment", f"{update['moved']:,}"),
            (icon_svg("users"), "Total customers now", f"{update['total_customers']:,}"),
        ])
        if update["already_stored"]:
            st.info(f"{update['already_stored']} line(s) in the file were already in the system, "
                    "so they were not counted twice.")
        st.caption(f"Reference date ('today' for Recency): {update['reference_date']:%Y-%m-%d}. "
                   "Recommendations are not recalculated by an upload -- run main.py to refresh those.")

        affected = update["affected"].copy()
        for column in ["Recency", "Frequency", "Monetary"]:
            affected[column] = affected[column].astype(float)

        left, right = st.columns(2, gap="large")
        with left:
            chart_header("Where the uploaded customers landed",
                         "How many customers from this file went into each segment.")
            counts = affected["Segment"].value_counts().reset_index()
            counts.columns = ["Segment", "Customers"]
            st.altair_chart(
                with_bar_labels(alt.Chart(counts).mark_bar(cornerRadiusTopLeft=8, cornerRadiusTopRight=8).encode(
                    x=alt.X("Segment:N", sort="-y", title=None, axis=alt.Axis(labelAngle=0, labelLimit=140)),
                    y="Customers:Q",
                    color=alt.Color("Segment:N", scale=seg_scale(counts["Segment"]), legend=None),
                    tooltip=["Segment", "Customers"],
                ), "Customers").properties(height=340),
                width="stretch",
            )
        with right:
            chart_header("Uploaded customers among everyone",
                         "The big markers are the customers from this file. The faint dots are all other customers.")
            st.altair_chart(scatter_highlight(customers, affected), width="stretch")

        with st.expander("Cleaning log"):
            st.dataframe(update["cleaning_log"], hide_index=True)
        st.subheader("Customers in this file")
        customer_table(update["affected"], key="upload_table")

    if st.button("Reset to original data", icon=":material/restore:"):
        confirm_reset_dialog()


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

st.html(
    f"<div class='cc-brand'><img src='{LOGO_URI}' alt='ClusterCart logo'><span>Cluster<b>Cart</b></span></div>"
    "<div class='cc-kicker'>Customer Segmentation and Targeted Marketing Recommendation System</div>"
)

tab_dashboard, tab_new, tab_table = st.tabs(
    ["Dashboard", "New Customers", "Customer Table"], key="main_tabs", on_change="rerun",
)

# ----- Tab 1: overview of the existing customers -----
with tab_dashboard:
    totals_row(customers)
    st.divider()
    segment_overview(customers, recommendations)
    recommendation_evidence(key="main")

# ----- Tab 2: new customers (one at a time, or upload a file that updates the dashboard) -----
with tab_new:
    assign_one_customer(customers, recommendations)
    st.divider()
    upload_section(customers)

# ----- Tab 3: browse the existing customers -----
with tab_table:
    filtered = customer_table(customers, key="table")
    if len(filtered) == 1:
        st.divider()
        customer_details(filtered.iloc[0])
    else:
        st.caption("Tip: type a full Customer ID in the search box to see that customer's details here.")

# ----- Footer (outside the tabs, so it shows on every tab) -----
st.html(
    "<div class='cc-footer'>"
    "<span><b>ClusterCart</b> · Flores, Ambrocio, Diocares · Elective 4</span>"
    "<span>Data: Online Retail II (2010–2011)</span>"
    "</div>"
)

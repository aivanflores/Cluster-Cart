"""
Step 6: K-Means clustering (find K, cluster, name the segments, plot).
"""
import matplotlib.pyplot as plt
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

from config import RANDOM_STATE, OUTPUT_DIR, SHOW_PLOTS, RFM_COLUMNS, MANUAL_LABELS


def _save_plot(fig, filename):
    """Save the chart as a PNG (for the report). Open it in a window only if SHOW_PLOTS is True."""
    fig.savefig(OUTPUT_DIR / filename, dpi=150, bbox_inches="tight")
    if SHOW_PLOTS:
        plt.show()
    plt.close(fig)


# ---------- Step 6a and 6b: choose K ----------
def evaluate_k_values(X_scaled, k_values=range(2, 11)):
    """Try several K values and record the inertia (elbow) and silhouette score of each."""
    rows = []
    for k in k_values:
        model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit(X_scaled)
        rows.append({"K": k,
                     "Inertia": model.inertia_,
                     "Silhouette": silhouette_score(X_scaled, model.labels_)})
    return pd.DataFrame(rows).round(4)


def plot_elbow_silhouette(k_table):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    ax1.plot(k_table["K"], k_table["Inertia"], marker="o")
    ax1.set(title="Elbow Method", xlabel="Number of clusters (K)", ylabel="Inertia")
    ax2.plot(k_table["K"], k_table["Silhouette"], marker="o", color="green")
    ax2.set(title="Silhouette Score", xlabel="Number of clusters (K)", ylabel="Score")
    fig.tight_layout()
    _save_plot(fig, "elbow_silhouette.png")


# ---------- Step 6c: final clustering ----------
def run_kmeans(X_scaled, k):
    """Fit K-Means with the chosen K. Returns the cluster number of each customer and the silhouette score."""
    model = KMeans(n_clusters=k, random_state=RANDOM_STATE, n_init=10).fit(X_scaled)
    return model.labels_, silhouette_score(X_scaled, model.labels_)


# ---------- Step 6d: name the clusters ----------
def name_clusters(profile):
    """
    Give each cluster a business name based on its average R, F, M, in this order:
      1. highest Recency (longest since last purchase)  -> Inactive
      2. highest Monetary of the remaining clusters     -> High-Spending
      3. highest Frequency of the remaining clusters    -> Loyal
      4. everything else                                -> Regular
    """
    names = {}
    remaining = profile.copy()
    for column, label in [("Recency", "Inactive Customers"),
                          ("Monetary", "High-Spending Customers"),
                          ("Frequency", "Loyal Customers")]:
        if remaining.empty:
            break
        winner = remaining[column].idxmax()
        names[winner] = label
        remaining = remaining.drop(winner)
    for cluster in remaining.index:
        names[cluster] = "Regular Customers"
    return names


def add_segments(rfm, labels):
    """
    Add 'Cluster' and 'Segment' columns to the RFM table.
    Returns the table and the cluster profile (average R, F, M and size of each cluster).
    """
    rfm = rfm.copy()
    rfm["Cluster"] = labels

    profile = rfm.groupby("Cluster")[RFM_COLUMNS].mean()
    profile["Customers"] = rfm.groupby("Cluster").size()

    cluster_names = MANUAL_LABELS or name_clusters(profile)
    profile["Segment"] = profile.index.map(cluster_names)
    rfm["Segment"] = rfm["Cluster"].map(cluster_names)
    return rfm, profile.round(1)


def plot_segments(rfm):
    """Scatter plot of the segments (log axes because a few customers spend a lot)."""
    fig, ax = plt.subplots(figsize=(8, 5))
    for segment, group in rfm.groupby("Segment"):
        ax.scatter(group["Frequency"], group["Monetary"], s=12, alpha=0.6,
                   label=f"{segment} ({len(group)})")
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set(title="Customer Segments", xlabel="Frequency (orders, log scale)",
           ylabel="Monetary (GBP, log scale)")
    ax.legend()
    _save_plot(fig, "segments_scatter.png")

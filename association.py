"""
Step 8 (updated): Association Rule Mining for campaign recommendations.

Instead of a fixed if-else lookup, this looks at what customers in each segment
actually buy together (the Apriori idea -- run here with FP-Growth, a faster
algorithm that finds the same rules) and turns the strongest pattern into a
plain-English recommendation.
"""
import pandas as pd
from mlxtend.frequent_patterns import association_rules, fpgrowth
from mlxtend.preprocessing import TransactionEncoder

from config import MIN_CONFIDENCE, MIN_SUPPORT, RULES_PER_SEGMENT, TOP_N_ITEMS


def _baskets(transactions):
    """One list of product names per invoice, kept to the best-selling products (for speed)."""
    top_items = transactions["description"].value_counts().nlargest(TOP_N_ITEMS).index
    lines = transactions[transactions["description"].isin(top_items)]
    baskets = lines.groupby("invoice")["description"].apply(lambda names: sorted(set(names)))
    return [basket for basket in baskets if len(basket) >= 2]      # need 2+ items to find a pattern


def _mine(baskets):
    """Run FP-Growth and return the rules it finds, best (highest lift) first."""
    if len(baskets) < 10:
        return pd.DataFrame()

    encoder = TransactionEncoder()
    onehot = pd.DataFrame(encoder.fit(baskets).transform(baskets), columns=encoder.columns_)

    frequent_sets = fpgrowth(onehot, min_support=MIN_SUPPORT, use_colnames=True)
    if frequent_sets.empty:
        return pd.DataFrame()

    rules = association_rules(frequent_sets, metric="confidence", min_threshold=MIN_CONFIDENCE,
                              num_itemsets=len(onehot))
    if rules.empty:
        return rules
    return rules.sort_values(["lift", "confidence"], ascending=False).reset_index(drop=True)


def _describe(antecedents, consequents, confidence, lift):
    items_a = ", ".join(sorted(antecedents))
    items_b = ", ".join(sorted(consequents))
    return (f"Customers who buy {items_a} also buy {items_b} {confidence * 100:.0f}% of the time "
           f"(lift {lift:.2f}). Bundle or cross-promote these items for this segment.")


def build_segment_rules(transactions, customers):
    """
    Run association rule mining separately for each segment's orders.

    transactions: the `transactions` table (invoice, description, customer_id, ...)
    customers:    a table with customer_id and segment

    Returns one row per kept rule, ready to save with db.replace_segment_rules(). A segment
    with no strong pattern (usually because it has very few customers) gets one fallback row.
    """
    with_segment = transactions.merge(customers[["customer_id", "segment"]], on="customer_id")

    rows = []
    for segment, group in with_segment.groupby("segment"):
        rules = _mine(_baskets(group)).head(RULES_PER_SEGMENT)

        if rules.empty:
            rows.append({
                "segment": segment, "rank_in_segment": 1, "antecedents": "", "consequents": "",
                "support": 0.0, "confidence": 0.0, "lift": 0.0,
                "recommendation": (f"Not enough repeat item combinations were found for {segment} yet "
                                   "(too few orders). Send a general seasonal promotion instead."),
            })
            continue

        for rank, rule in enumerate(rules.itertuples(index=False), start=1):
            rows.append({
                "segment": segment, "rank_in_segment": rank,
                "antecedents": ", ".join(sorted(rule.antecedents)),
                "consequents": ", ".join(sorted(rule.consequents)),
                "support": round(rule.support, 4), "confidence": round(rule.confidence, 4),
                "lift": round(rule.lift, 4),
                "recommendation": _describe(rule.antecedents, rule.consequents, rule.confidence, rule.lift),
            })

    return pd.DataFrame(rows)

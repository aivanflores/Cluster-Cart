"""
ClusterCart: run the whole pipeline (Steps 3-8) with:   python main.py
Start MySQL in the XAMPP Control Panel first. Results are saved in MySQL (database
"clustercart"), which the dashboard (app.py) reads. Charts and the trained model are
saved in the outputs/ folder.
"""
import db
from association import build_segment_rules
from classification import save_classifier, train_and_compare
from cleaning import clean_data, load_data
from clustering import add_segments, evaluate_k_values, plot_elbow_silhouette, plot_segments, run_kmeans
from config import CHOSEN_K, OUTPUT_DIR
from rfm import compute_rfm, make_invoice_table, scale_rfm


def main():
    OUTPUT_DIR.mkdir(exist_ok=True)

    print("Connecting to MySQL and preparing the database...")
    db.init_database()

    # Step 3: load and clean
    print("Loading data (the first run reads Excel and can take 1-3 minutes)...")
    raw = load_data()
    df, cleaning_log = clean_data(raw)

    transactions = db.to_transactions_table(df)
    print(f"Saving {len(transactions):,} transaction lines to MySQL...")
    db.replace_transactions(transactions)

    # Steps 4-5: RFM and scaling
    invoices = make_invoice_table(df)
    rfm, reference_date = compute_rfm(invoices)
    scaler, X_scaled = scale_rfm(rfm)
    print(f"Reference date: {reference_date} | Customers: {len(rfm)}")

    # Step 6: K-Means
    k_table = evaluate_k_values(X_scaled)                       # 6a + 6b: elbow and silhouette
    plot_elbow_silhouette(k_table)
    labels, final_silhouette = run_kmeans(X_scaled, CHOSEN_K)   # 6c
    rfm, profile = add_segments(rfm, labels)                    # 6d
    plot_segments(rfm)

    # Step 7: classification
    results, best_name, best_model = train_and_compare(X_scaled, rfm["Segment"])
    save_classifier(best_model, scaler, best_name)

    # Step 8: Association Rule Mining (replaces the old fixed lookup table)
    print("Finding frequently-bought-together products per segment (this can take a minute)...")
    customers_for_arm = (rfm.reset_index()[["Customer ID", "Segment"]]
                        .rename(columns={"Customer ID": "customer_id", "Segment": "segment"}))
    segment_rules = build_segment_rules(transactions, customers_for_arm)
    db.replace_segment_rules(segment_rules)
    recommendations = segment_rules[segment_rules["rank_in_segment"] == 1].set_index("segment")["recommendation"]

    # Save the customer table to MySQL
    customers_table = (rfm.reset_index()
                       .rename(columns={"Customer ID": "customer_id", "Recency": "recency",
                                       "Frequency": "frequency", "Monetary": "monetary",
                                       "Segment": "segment"})[["customer_id", "recency", "frequency",
                                                                "monetary", "segment"]])
    db.replace_customers(customers_table)
    db.save_snapshot()      # lets the dashboard's "Undo uploads" button come back to this exact state

    # A CSV copy too, for Power BI (Get Data -> Text/CSV) if you would rather not connect it to MySQL
    export = customers_table.merge(recommendations.rename("recommendation"), left_on="segment",
                                   right_index=True, how="left")
    export.to_csv(OUTPUT_DIR / "customer_segments.csv", index=False)
    cleaning_log.to_csv(OUTPUT_DIR / "cleaning_log.csv", index=False)
    k_table.to_csv(OUTPUT_DIR / "elbow_silhouette_table.csv", index=False)
    results.to_csv(OUTPUT_DIR / "classification_results.csv")

    # Evaluation summary (Section 11 of the documentation) - copy into the report
    print(f"\nFinal K: {CHOSEN_K}   |   Final Silhouette Score: {final_silhouette:.4f}")
    print(f"Classifier selected: {best_name} (higher F1-score)")
    print("\nCleaning log:\n", cleaning_log.to_string(index=False))
    print("\nElbow / Silhouette by K:\n", k_table.to_string(index=False))
    print("\nCluster profiles (check that the names make sense!):\n", profile.to_string())
    print("\nClassification comparison:\n", results)
    print("\nCustomers per segment:\n", rfm["Segment"].value_counts().to_string())
    print("\nTop recommendation per segment (Association Rule Mining):")
    for segment, text in recommendations.items():
        print(f"  {segment}: {text}")

    print(f"\nDone. Data saved to the '{db.DB_CONFIG['database']}' MySQL database.")
    print(f"Charts and the model are saved in: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()

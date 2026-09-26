"""
Step 7: classify new customers into the existing segments.
"""
import joblib
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.neighbors import KNeighborsClassifier
from sklearn.tree import DecisionTreeClassifier

from config import OUTPUT_DIR, RANDOM_STATE, RFM_COLUMNS

MODEL_FILE = OUTPUT_DIR / "best_classifier.joblib"


def train_and_compare(X_scaled, segments):
    """
    Train a Decision Tree and a KNN to predict the segment from the scaled RFM values.
    Precision, Recall and F1 use average="weighted" so big and small segments count fairly.
    Returns the results table, the name of the winner (higher F1) and the winning model.
    """
    can_stratify = segments.value_counts().min() >= 2     # keeps segment proportions equal in train/test
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, segments, test_size=0.2, random_state=RANDOM_STATE,
        stratify=segments if can_stratify else None)

    models = {
        "Decision Tree": DecisionTreeClassifier(random_state=RANDOM_STATE),
        "KNN":           KNeighborsClassifier(n_neighbors=5),
    }

    results = []
    for name, model in models.items():
        model.fit(X_train, y_train)
        predicted = model.predict(X_test)
        results.append({
            "Model":     name,
            "Accuracy":  accuracy_score(y_test, predicted),
            "Precision": precision_score(y_test, predicted, average="weighted", zero_division=0),
            "Recall":    recall_score(y_test, predicted, average="weighted", zero_division=0),
            "F1-score":  f1_score(y_test, predicted, average="weighted", zero_division=0),
        })

    results = pd.DataFrame(results).set_index("Model").round(4)
    best_name = results["F1-score"].idxmax()
    return results, best_name, models[best_name]


def save_classifier(model, scaler, model_name):
    """Save the scaler together with the model, because new customers must be scaled the same way."""
    joblib.dump({"model": model, "scaler": scaler, "model_name": model_name}, MODEL_FILE)


def assign_segments(rfm):
    """
    Predict a segment for every customer in an RFM table, using the saved model.
    Returns Customer ID, Recency, Frequency, Monetary, Segment (no recommendation --
    that is looked up separately from the segment_rules table; see db.top_recommendations()).
    """
    saved = joblib.load(MODEL_FILE)
    result = rfm[RFM_COLUMNS].copy()
    result["Segment"] = saved["model"].predict(saved["scaler"].transform(result))
    return result.reset_index()


def assign_new_customer(recency, frequency, monetary):
    """Return the predicted segment for one new customer."""
    one_customer = pd.DataFrame([[recency, frequency, monetary]], columns=RFM_COLUMNS)
    return assign_segments(one_customer).iloc[0]["Segment"]

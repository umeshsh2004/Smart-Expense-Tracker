"""
Next-month spending prediction using simple linear regression.

Limitation: months are encoded as sequential integers (1, 2, 3, ...) rather than
actual calendar dates. Months with zero expenses are omitted from the series, so
gaps in the timeline are not represented and the model treats consecutive data
points as adjacent months even when calendar months were skipped.
"""

import numpy as np

class SimpleLinearRegression:
    def fit(self, X, y):
        X_arr = np.array(X, dtype=float).reshape(-1, 1)
        y_arr = np.array(y, dtype=float)
        A = np.hstack([X_arr, np.ones((len(X_arr), 1))])
        coef, intercept = np.linalg.lstsq(A, y_arr, rcond=None)[0]
        self.coef_ = np.array([coef])
        self.intercept_ = intercept

    def predict(self, X):
        X_arr = np.array(X, dtype=float).reshape(-1, 1)
        return (self.coef_ * X_arr + self.intercept_).flatten()

    def score(self, X, y):
        y_pred = self.predict(X)
        u = ((y - y_pred) ** 2).sum()
        v = ((y - y.mean()) ** 2).sum()
        return 1 - (u / v)

from database import get_monthly_totals


def predict_next_month(user_id: int):
    monthly_data = get_monthly_totals(user_id)

    if len(monthly_data) < 3:
        return {
            "prediction": None,
            "message": "Need at least 3 months of data for prediction",
            "data_points": len(monthly_data),
            "month_labels": [row["month"] for row in monthly_data],
            "month_amounts": [float(row["total"] or 0) for row in monthly_data],
            "regression_line": [],
            "r_squared": None,
            "slope": None,
            "trend": "",
            "trend_color": "#3498db",
        }

    months = np.array(range(1, len(monthly_data) + 1), dtype=float).reshape(-1, 1)
    amounts = np.array([float(row["total"]) for row in monthly_data], dtype=float)

    model = SimpleLinearRegression()
    model.fit(months, amounts)

    next_month_num = len(monthly_data) + 1
    prediction = float(model.predict([next_month_num])[0])

    r_squared = float(model.score(months, amounts))
    slope = float(model.coef_[0])

    if slope > 50:
        trend = "Spending is increasing significantly"
        trend_color = "#e74c3c"
    elif slope > 0:
        trend = "Spending is slightly increasing"
        trend_color = "#e67e22"
    elif slope > -50:
        trend = "Spending is slightly decreasing"
        trend_color = "#2ecc71"
    else:
        trend = "Spending is decreasing significantly"
        trend_color = "#27ae60"

    month_labels = [row["month"] for row in monthly_data]
    month_amounts = [float(row["total"]) for row in monthly_data]
    regression_line = [
        round(float(model.predict([[i]])[0]), 2) for i in range(1, next_month_num + 1)
    ]

    return {
        "prediction": round(max(0.0, prediction), 2),
        "r_squared": round(r_squared, 3),
        "trend": trend,
        "trend_color": trend_color,
        "slope": round(slope, 2),
        "month_labels": month_labels,
        "month_amounts": [round(x, 2) for x in month_amounts],
        "regression_line": regression_line,
        "data_points": len(monthly_data),
        "message": "Prediction successful",
    }


def get_spending_stats(user_id: int):
    monthly_data = get_monthly_totals(user_id)
    if not monthly_data:
        return {"average": 0.0, "maximum": 0.0, "minimum": 0.0, "months_tracked": 0}

    amounts = [float(row["total"] or 0) for row in monthly_data]
    return {
        "average": round(sum(amounts) / len(amounts), 2),
        "maximum": round(max(amounts), 2),
        "minimum": round(min(amounts), 2),
        "months_tracked": len(amounts),
    }

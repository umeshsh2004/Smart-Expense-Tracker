"""Generate in-app notifications from spending signals."""

from datetime import datetime

import database as db
import ml_model as ml


def refresh(user_id: int) -> None:
    now = datetime.now()
    year, month = now.year, now.month
    month_str = now.strftime("%Y-%m")
    today = now.strftime("%Y-%m-%d")

    budget_rows = db.get_budget_vs_actual(user_id, year, month)
    for row in budget_rows:
        budget = float(row["budget"])
        actual = float(row["actual"])
        if budget > 0 and actual >= budget:
            db.upsert_notification(
                user_id,
                title="Budget exceeded",
                message=f"{row['category']}: ₹{actual:.2f} spent (budget ₹{budget:.2f}).",
                kind="warning",
                dedupe_key=f"budget_exceeded_{month_str}_{row['category_id']}",
            )
        elif budget > 0 and actual >= budget * 0.8:
            db.upsert_notification(
                user_id,
                title="Approaching budget limit",
                message=f"{row['category']} is at {actual / budget * 100:.0f}% of budget.",
                kind="info",
                dedupe_key=f"budget_warn_{month_str}_{row['category_id']}",
            )

    prediction = ml.predict_next_month(user_id)
    if prediction.get("prediction"):
        avg = ml.get_spending_stats(user_id)["average"]
        if avg > 0 and prediction["prediction"] > avg * 1.15:
            db.upsert_notification(
                user_id,
                title="Prediction increased",
                message=(
                    f"Next month forecast ₹{prediction['prediction']:.2f} "
                    f"is above your average ₹{avg:.2f}."
                ),
                kind="info",
                dedupe_key=f"prediction_up_{month_str}",
            )

    daily = db.get_daily_spending(user_id, year, month)
    today_total = 0.0
    for d in daily:
        if d["date"] == today:
            today_total = float(d["total"])
            break
    if today_total >= 2000:
        db.upsert_notification(
            user_id,
            title="High spending today",
            message=f"You've spent ₹{today_total:.2f} today.",
            kind="warning",
            dedupe_key=f"high_today_{today}",
        )

    goals = db.get_savings_goals(user_id)
    for g in goals:
        target = float(g["target_amount"])
        current = float(g["current_amount"])
        if target > 0 and current >= target:
            db.upsert_notification(
                user_id,
                title="Savings goal reached!",
                message=f"Goal “{g['name']}” hit ₹{current:.2f}.",
                kind="success",
                dedupe_key=f"goal_done_{g['id']}",
            )

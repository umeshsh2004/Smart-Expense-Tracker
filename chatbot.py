"""Expense insights chatbot — rule-based with optional OpenAI."""

import os

import database as db
import ml_model as ml


def _rule_based_answer(user_id: int, question: str) -> str:
    q = (question or "").lower()
    now_year = __import__("datetime").datetime.now().year
    now_month = __import__("datetime").datetime.now().month

    if "more" in q and "month" in q:
        totals = db.get_monthly_totals(user_id)
        if len(totals) < 2:
            return "Add expenses in at least two months so I can compare spending."
        last = float(totals[-1]["total"])
        prev = float(totals[-2]["total"])
        diff = last - prev
        direction = "more" if diff > 0 else "less"
        return (
            f"Last recorded month ({totals[-1]['month']}): ₹{last:.2f}. "
            f"Previous ({totals[-2]['month']}): ₹{prev:.2f}. "
            f"You spent ₹{abs(diff):.2f} {direction}."
        )

    if "top" in q or "category" in q or "most" in q:
        cat = db.get_highest_category(user_id, now_year, now_month)
        if not cat:
            return "No category spending this month yet."
        return f"Top category this month: {cat['category']} at ₹{float(cat['total']):.2f}."

    if "predict" in q or "next month" in q:
        p = ml.predict_next_month(user_id)
        if not p.get("prediction"):
            return p.get("message", "Not enough data to predict.")
        return (
            f"Predicted next month: ₹{p['prediction']:.2f}. "
            f"{p.get('trend', '')} (R²={p.get('r_squared')})."
        )

    if "budget" in q:
        rows = db.get_budget_vs_actual(user_id, now_year, now_month)
        over = [r for r in rows if float(r["budget"]) > 0 and float(r["actual"]) >= float(r["budget"])]
        if not over:
            return "No categories have exceeded budget this month."
        names = ", ".join(r["category"] for r in over[:5])
        return f"Budget exceeded for: {names}."

    if "save" in q or "savings" in q:
        income = db.get_monthly_income_total(user_id, now_year, now_month)
        expense = db.get_monthly_expense_total(user_id, now_year, now_month)
        return f"This month: income ₹{income:.2f}, expenses ₹{expense:.2f}, savings ₹{income - expense:.2f}."

    stats = ml.get_spending_stats(user_id)
    return (
        "Try asking: Why did I spend more this month? "
        "What is my top category? What is next month's prediction? "
        "Any budget exceeded? How are my savings? "
        f"(You track {stats['months_tracked']} months; avg ₹{stats['average']:.2f}/month.)"
    )


def answer(user_id: int, question: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        try:
            return _openai_answer(user_id, question, api_key)
        except Exception:
            pass
    return _rule_based_answer(user_id, question)


def _openai_answer(user_id: int, question: str, api_key: str) -> str:
    try:
        from openai import OpenAI
    except ImportError:
        return _rule_based_answer(user_id, question)

    now = __import__("datetime").datetime.now()
    stats = ml.get_spending_stats(user_id)
    prediction = ml.predict_next_month(user_id)
    context = (
        f"User stats: {stats}. Prediction: {prediction.get('prediction')}. "
        f"Month: {now.strftime('%Y-%m')}."
    )
    client = OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {
                "role": "system",
                "content": "You are a concise personal finance assistant. Use only the context given.",
            },
            {"role": "user", "content": f"Context: {context}\n\nQuestion: {question}"},
        ],
        max_tokens=300,
    )
    return resp.choices[0].message.content or _rule_based_answer(user_id, question)

import csv
import io
import os
import secrets
import time
from datetime import datetime, timedelta
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for, make_response
from flask_login import LoginManager, current_user, login_required, login_user, logout_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

import auth as auth_module
import chatbot
import database as db
import exports as exp_export
import ml_model as ml
import notifications_service as notify_svc
import ocr as receipt_ocr
import recurring as recurring_svc
from validators import validate_expense_form, validate_month_str

# Simple in-memory login rate limiting: {ip: [(timestamp, ...)]}
_login_attempts: dict[str, list[float]] = {}
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 900  # 15 minutes


def create_app():
    app = Flask(__name__)
    is_production = os.environ.get("FLASK_ENV") == "production"

    secret_key = os.environ.get("FLASK_SECRET_KEY")
    if is_production and not secret_key:
        raise RuntimeError("FLASK_SECRET_KEY must be set in production.")
    app.secret_key = secret_key or "dev-secret-key-change-me"

    app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(hours=12)
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = is_production
    app.config["WTF_CSRF_TIME_LIMIT"] = None

    csrf = CSRFProtect(app)

    login_manager = LoginManager(app)
    login_manager.login_view = "login"
    login_manager.login_message_category = "info"
    login_manager.user_loader(auth_module.load_user)

    db.init_db()

    @app.before_request
    def user_maintenance():
        if current_user.is_authenticated and request.endpoint != "static":
            recurring_svc.process_due(current_user.id)
            notify_svc.refresh(current_user.id)

    @app.context_processor
    def inject_globals():
        if current_user.is_authenticated:
            return {"unread_notifications": db.count_unread_notifications(current_user.id)}
        return {"unread_notifications": 0}

    def _check_login_rate_limit() -> bool:
        ip = request.remote_addr or "unknown"
        now = time.time()
        attempts = _login_attempts.get(ip, [])
        attempts = [t for t in attempts if now - t < LOGIN_WINDOW_SECONDS]
        _login_attempts[ip] = attempts
        return len(attempts) < MAX_LOGIN_ATTEMPTS

    def _record_login_failure():
        ip = request.remote_addr or "unknown"
        _login_attempts.setdefault(ip, []).append(time.time())

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        if request.method == "POST":
            if not _check_login_rate_limit():
                flash("Too many login attempts. Try again in 15 minutes.", "error")
                return render_template("login.html"), 429

            username = request.form.get("username", "").strip()
            password = request.form.get("password", "")

            if not username or not password:
                flash("Username and password are required.", "error")
            else:
                user_row = db.get_user_by_username(username)
                if user_row and check_password_hash(user_row["password_hash"], password):
                    user = auth_module.User(user_row["id"], user_row["username"], user_row["email"])
                    login_user(user, remember=bool(request.form.get("remember")))
                    next_page = request.args.get("next")
                    if next_page and next_page.startswith("/"):
                        return redirect(next_page)
                    return redirect(url_for("index"))
                _record_login_failure()
                flash("Invalid username or password.", "error")

        return render_template("login.html")

    @app.route("/forgot-password", methods=["GET", "POST"])
    def forgot_password():
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user_row = db.get_user_by_email(email) if email else None
            if user_row:
                token = secrets.token_urlsafe(32)
                expires_at = (datetime.utcnow() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
                db.create_password_reset_token(user_row["id"], token, expires_at)
                reset_url = url_for("reset_password", token=token, _external=True)
                if os.environ.get("FLASK_ENV") == "production":
                    flash("If that email exists, a reset link was sent.", "info")
                else:
                    flash(f"Dev reset link: {reset_url}", "info")
            else:
                flash("If that email exists, a reset link was sent.", "info")
            return redirect(url_for("login"))

        return render_template("forgot_password.html")

    @app.route("/reset-password/<token>", methods=["GET", "POST"])
    def reset_password(token: str):
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        reset_row = db.get_valid_reset_token(token)
        if not reset_row:
            flash("Invalid or expired reset link.", "error")
            return redirect(url_for("login"))

        if request.method == "POST":
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            if len(password) < 6:
                flash("Password must be at least 6 characters.", "error")
            elif password != confirm:
                flash("Passwords do not match.", "error")
            else:
                db.update_user_password(reset_row["user_id"], generate_password_hash(password))
                db.mark_reset_token_used(token)
                flash("Password reset successfully. Please log in.", "success")
                return redirect(url_for("login"))

        return render_template("reset_password.html", token=token)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for("index"))

        if request.method == "POST":
            username = request.form.get("username", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")

            errors = []
            if len(username) < 3:
                errors.append("Username must be at least 3 characters.")
            if "@" not in email or len(email) < 5:
                errors.append("Enter a valid email address.")
            if len(password) < 6:
                errors.append("Password must be at least 6 characters.")
            if password != confirm:
                errors.append("Passwords do not match.")
            if db.get_user_by_username(username):
                errors.append("Username already taken.")
            if db.get_user_by_email(email):
                errors.append("Email already registered.")

            if errors:
                for e in errors:
                    flash(e, "error")
            else:
                user_id = db.create_user(username, email, generate_password_hash(password))
                login_user(auth_module.User(user_id, username, email))
                flash("Account created successfully!", "success")
                return redirect(url_for("index"))

        return render_template("register.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        flash("You have been logged out.", "info")
        return redirect(url_for("login"))

    @app.route("/profile", methods=["GET", "POST"])
    @login_required
    def profile():
        if request.method == "POST":
            action = request.form.get("action", "update_profile")
            if action == "update_profile":
                email = request.form.get("email", "").strip().lower()
                if "@" not in email:
                    flash("Enter a valid email address.", "error")
                else:
                    existing = db.get_user_by_email(email)
                    if existing and existing["id"] != current_user.id:
                        flash("Email already in use.", "error")
                    else:
                        db.update_user_profile(current_user.id, email)
                        current_user.email = email
                        flash("Profile updated.", "success")
            elif action == "change_password":
                current_pw = request.form.get("current_password", "")
                new_pw = request.form.get("new_password", "")
                confirm_pw = request.form.get("confirm_password", "")
                user_row = db.get_user_by_id(current_user.id)
                if not user_row or not check_password_hash(user_row["password_hash"], current_pw):
                    flash("Current password is incorrect.", "error")
                elif len(new_pw) < 6:
                    flash("New password must be at least 6 characters.", "error")
                elif new_pw != confirm_pw:
                    flash("New passwords do not match.", "error")
                else:
                    db.update_user_password(current_user.id, generate_password_hash(new_pw))
                    flash("Password changed successfully.", "success")
            return redirect(url_for("profile"))

        user_row = db.get_user_by_id(current_user.id)
        return render_template("profile.html", user=user_row)

    @app.route("/", methods=["GET", "POST"])
    @login_required
    def index():
        ocr_prefill = {}

        if request.method == "POST":
            action = request.form.get("action", "add_expense")
            if action == "scan_receipt":
                file = request.files.get("receipt")
                pasted = request.form.get("receipt_text", "").strip()
                if file and file.filename:
                    ocr_prefill = receipt_ocr.extract_from_image(file)
                elif pasted:
                    ocr_prefill = receipt_ocr.parse_receipt_text(pasted)
                    ocr_prefill["message"] = "Parsed from pasted text. Review before saving."
                else:
                    flash("Upload an image or paste receipt text.", "error")
                categories = db.get_all_categories()
                recent_expenses = db.get_all_expenses(current_user.id, limit=10)
                today = datetime.now().strftime("%Y-%m-%d")
                return render_template(
                    "index.html",
                    categories=categories,
                    recent_expenses=recent_expenses,
                    today=today,
                    ocr_prefill=ocr_prefill,
                )

            errors, cleaned = validate_expense_form(
                request.form.get("amount", ""),
                request.form.get("description", ""),
                request.form.get("category_id", ""),
                request.form.get("date", ""),
            )
            if errors:
                for e in errors:
                    flash(e, "error")
            else:
                db.add_expense(
                    user_id=current_user.id,
                    amount=cleaned["amount"],
                    description=cleaned["description"],
                    category_id=cleaned["category_id"],
                    date=cleaned["date"],
                )
                flash("Expense added successfully!", "success")
                return redirect(url_for("index"))

        categories = db.get_all_categories()
        recent_expenses = db.get_all_expenses(current_user.id, limit=10)
        today = datetime.now().strftime("%Y-%m-%d")
        return render_template(
            "index.html",
            categories=categories,
            recent_expenses=recent_expenses,
            today=today,
            ocr_prefill=ocr_prefill,
        )

    @app.route("/expenses")
    @login_required
    def expenses():
        page = max(1, request.args.get("page", 1, type=int))
        per_page = 20
        search = request.args.get("q", "").strip()
        category_id = request.args.get("category_id", type=int)
        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()

        total_count = db.count_expenses(
            current_user.id, search, category_id, date_from, date_to
        )
        total_pages = max(1, (total_count + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page

        expense_rows = db.search_expenses(
            current_user.id, search, category_id, date_from, date_to, per_page, offset
        )
        total_amount = sum(float(e["amount"]) for e in expense_rows)

        categories = db.get_all_categories()
        return render_template(
            "expenses.html",
            expenses=expense_rows,
            total=total_amount,
            total_count=total_count,
            page=page,
            total_pages=total_pages,
            search=search,
            category_id=category_id,
            date_from=date_from,
            date_to=date_to,
            categories=categories,
        )

    @app.route("/expenses/export")
    @login_required
    def export_expenses():
        search = request.args.get("q", "").strip()
        category_id = request.args.get("category_id", type=int)
        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()

        rows = db.get_expenses_for_export(
            current_user.id, search, category_id, date_from, date_to
        )

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Category", "Description", "Amount"])
        for row in rows:
            writer.writerow([row["date"], row["category"], row["description"], row["amount"]])

        response = make_response(output.getvalue())
        response.headers["Content-Type"] = "text/csv"
        response.headers["Content-Disposition"] = (
            f'attachment; filename=expenses_{datetime.now().strftime("%Y%m%d")}.csv'
        )
        return response

    @app.route("/expenses/export/excel")
    @login_required
    def export_expenses_excel():
        search = request.args.get("q", "").strip()
        category_id = request.args.get("category_id", type=int)
        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        rows = db.get_expenses_for_export(
            current_user.id, search, category_id, date_from, date_to
        )
        buf = exp_export.build_excel(rows)
        response = make_response(buf.read())
        response.headers["Content-Type"] = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response.headers["Content-Disposition"] = (
            f'attachment; filename=expenses_{datetime.now().strftime("%Y%m%d")}.xlsx'
        )
        return response

    @app.route("/expenses/export/pdf")
    @login_required
    def export_expenses_pdf():
        search = request.args.get("q", "").strip()
        category_id = request.args.get("category_id", type=int)
        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        rows = db.get_expenses_for_export(
            current_user.id, search, category_id, date_from, date_to
        )
        pdf_bytes = exp_export.build_pdf(rows)
        response = make_response(pdf_bytes)
        response.headers["Content-Type"] = "application/pdf"
        response.headers["Content-Disposition"] = (
            f'attachment; filename=expenses_{datetime.now().strftime("%Y%m%d")}.pdf'
        )
        return response

    @app.route("/recurring", methods=["GET", "POST"])
    @login_required
    def recurring_page():
        if request.method == "POST":
            errors, cleaned = validate_expense_form(
                request.form.get("amount", ""),
                request.form.get("description", ""),
                request.form.get("category_id", ""),
                request.form.get("next_due_date", ""),
            )
            if errors:
                for e in errors:
                    flash(e, "error")
            else:
                db.add_recurring(
                    current_user.id,
                    cleaned["amount"],
                    cleaned["description"],
                    cleaned["category_id"],
                    cleaned["date"],
                )
                flash("Recurring expense created.", "success")
            return redirect(url_for("recurring_page"))

        items = db.get_recurring_list(current_user.id)
        categories = db.get_all_categories()
        today = datetime.now().strftime("%Y-%m-%d")
        return render_template(
            "recurring.html", items=items, categories=categories, today=today
        )

    @app.route("/recurring/<int:rid>/toggle", methods=["POST"])
    @login_required
    def toggle_recurring(rid: int):
        active = request.form.get("active") == "1"
        db.toggle_recurring(rid, current_user.id, active)
        return redirect(url_for("recurring_page"))

    @app.route("/recurring/<int:rid>/delete", methods=["POST"])
    @login_required
    def delete_recurring_route(rid: int):
        db.delete_recurring(rid, current_user.id)
        flash("Recurring expense removed.", "info")
        return redirect(url_for("recurring_page"))

    @app.route("/savings", methods=["GET", "POST"])
    @login_required
    def savings():
        if request.method == "POST":
            action = request.form.get("action", "create")
            if action == "create":
                name = request.form.get("name", "").strip()
                try:
                    target = float(request.form.get("target_amount", ""))
                except ValueError:
                    target = -1
                deadline = request.form.get("deadline", "").strip()
                if not name or target <= 0:
                    flash("Enter a valid goal name and target amount.", "error")
                else:
                    db.add_savings_goal(current_user.id, name, target, deadline)
                    flash("Savings goal created.", "success")
            elif action == "contribute":
                try:
                    gid = int(request.form.get("goal_id", ""))
                    amount = float(request.form.get("amount", ""))
                except ValueError:
                    gid, amount = 0, -1
                if gid and amount > 0:
                    db.add_to_savings_goal(current_user.id, gid, amount)
                    flash("Contribution added.", "success")
                else:
                    flash("Invalid contribution.", "error")
            return redirect(url_for("savings"))

        goals = db.get_savings_goals(current_user.id)
        return render_template("savings.html", goals=goals)

    @app.route("/savings/<int:goal_id>/delete", methods=["POST"])
    @login_required
    def delete_savings_goal(goal_id: int):
        db.delete_savings_goal(current_user.id, goal_id)
        flash("Goal deleted.", "info")
        return redirect(url_for("savings"))

    @app.route("/notifications")
    @login_required
    def notifications():
        items = db.get_notifications(current_user.id)
        return render_template("notifications.html", items=items)

    @app.route("/notifications/read/<int:nid>", methods=["POST"])
    @login_required
    def read_notification(nid: int):
        db.mark_notification_read(current_user.id, nid)
        return redirect(url_for("notifications"))

    @app.route("/notifications/read-all", methods=["POST"])
    @login_required
    def read_all_notifications():
        db.mark_all_notifications_read(current_user.id)
        flash("All notifications marked read.", "info")
        return redirect(url_for("notifications"))

    @app.route("/analytics")
    @login_required
    def analytics():
        now = datetime.now()
        year = request.args.get("year", now.year, type=int)
        month = request.args.get("month", now.month, type=int)
        if month < 1:
            month, year = 12, year - 1
        if month > 12:
            month, year = 1, year + 1

        import calendar as cal

        cal_data = db.get_calendar_spending(current_user.id, year, month)
        max_spend = max(cal_data.values()) if cal_data else 1.0
        if max_spend <= 0:
            max_spend = 1.0

        first_weekday, days_in_month = cal.monthrange(year, month)
        month_name = datetime(year, month, 1).strftime("%B %Y")
        prev_y, prev_m = (year - 1, 12) if month == 1 else (year, month - 1)
        next_y, next_m = (year + 1, 1) if month == 12 else (year, month + 1)

        return render_template(
            "analytics.html",
            year=year,
            month=month,
            month_name=month_name,
            prev_year=prev_y,
            prev_month=prev_m,
            next_year=next_y,
            next_month=next_m,
            cal_data=cal_data,
            max_spend=max_spend,
            first_weekday=first_weekday,
            days_in_month=days_in_month,
        )

    @app.route("/chat", methods=["GET", "POST"])
    @login_required
    def chat():
        answer_text = None
        question = ""
        if request.method == "POST":
            question = request.form.get("question", "").strip()
            if question:
                answer_text = chatbot.answer(current_user.id, question)
        return render_template("chat.html", question=question, answer=answer_text)

    @app.route("/api/chat", methods=["POST"])
    @csrf.exempt
    @login_required
    def api_chat():
        data = request.get_json(silent=True) or {}
        question = (data.get("question") or "").strip()
        if not question:
            return jsonify({"error": "question required"}), 400
        return jsonify({"answer": chatbot.answer(current_user.id, question)})

    @app.route("/expenses/<int:expense_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_expense(expense_id: int):
        expense = db.get_expense_by_id(current_user.id, expense_id)
        if not expense:
            flash("Expense not found.", "error")
            return redirect(url_for("expenses"))

        if request.method == "POST":
            errors, cleaned = validate_expense_form(
                request.form.get("amount", ""),
                request.form.get("description", ""),
                request.form.get("category_id", ""),
                request.form.get("date", ""),
            )
            if errors:
                for e in errors:
                    flash(e, "error")
            elif db.update_expense(
                current_user.id,
                expense_id,
                cleaned["amount"],
                cleaned["description"],
                cleaned["category_id"],
                cleaned["date"],
            ):
                flash("Expense updated successfully.", "success")
                return redirect(url_for("expenses"))
            else:
                flash("Could not update expense.", "error")

        categories = db.get_all_categories()
        return render_template("edit_expense.html", expense=expense, categories=categories)

    @app.route("/delete/<int:expense_id>", methods=["POST"])
    @login_required
    def delete_expense(expense_id: int):
        if db.delete_expense(current_user.id, expense_id):
            flash("Expense deleted.", "info")
        else:
            flash("Expense not found or access denied.", "error")
        return redirect(url_for("expenses"))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        now = datetime.now()
        year = request.args.get("year", now.year, type=int)
        month = request.args.get("month", now.month, type=int)

        if month < 1:
            month = 12
            year -= 1
        if month > 12:
            month = 1
            year += 1

        category_data = db.get_spending_by_category(current_user.id, year, month)
        daily_data = db.get_daily_spending(current_user.id, year, month)
        weekly_data = db.get_weekly_spending(current_user.id, year, month)
        monthly_total = sum(float(r["total"]) for r in category_data) if category_data else 0.0
        monthly_income = db.get_monthly_income_total(current_user.id, year, month)
        monthly_savings = round(monthly_income - monthly_total, 2)

        prediction = ml.predict_next_month(current_user.id)
        stats = ml.get_spending_stats(current_user.id)
        total_expenses = db.count_user_expenses(current_user.id)
        highest_category = db.get_highest_category(current_user.id, year, month)
        budget_remaining = db.get_budget_remaining(current_user.id, year, month)

        pie_labels = [r["category"] for r in category_data]
        pie_values = [float(r["total"]) for r in category_data]
        pie_colors = [r["color"] for r in category_data]

        bar_labels = [r["date"] for r in daily_data]
        bar_values = [float(r["total"]) for r in daily_data]

        week_labels = [f"Week {int(r['week_num'])}" for r in weekly_data]
        week_values = [float(r["total"]) for r in weekly_data]

        month_name = datetime(year, month, 1).strftime("%B %Y")
        prev_year, prev_month = (year - 1, 12) if month == 1 else (year, month - 1)
        next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)

        return render_template(
            "dashboard.html",
            year=year,
            month=month,
            prev_year=prev_year,
            prev_month=prev_month,
            next_year=next_year,
            next_month=next_month,
            monthly_total=monthly_total,
            pie_labels=pie_labels,
            pie_values=pie_values,
            pie_colors=pie_colors,
            bar_labels=bar_labels,
            bar_values=bar_values,
            week_labels=week_labels,
            week_values=week_values,
            monthly_income=monthly_income,
            monthly_savings=monthly_savings,
            prediction=prediction,
            stats=stats,
            total_expenses=total_expenses,
            highest_category=highest_category,
            budget_remaining=budget_remaining,
            month_name=month_name,
        )

    @app.route("/budget", methods=["GET", "POST"])
    @login_required
    def budget():
        now = datetime.now()
        month_str_default = now.strftime("%Y-%m")

        if request.method == "POST":
            category_id = request.form.get("category_id", "").strip()
            amount = request.form.get("amount", "").strip()
            month_raw = request.form.get("month", month_str_default).strip()

            valid_month, month_result = validate_month_str(month_raw)
            try:
                amount_val = float(amount)
            except ValueError:
                amount_val = -1

            if not valid_month:
                flash(month_result, "error")
            elif not category_id:
                flash("Please select a category.", "error")
            elif amount_val <= 0:
                flash("Budget amount must be greater than 0.", "error")
            else:
                db.set_budget(current_user.id, int(category_id), month_result, amount_val)
                flash("Budget set successfully!", "success")

            return redirect(url_for("budget"))

        categories = db.get_all_categories()
        budget_data = db.get_budget_vs_actual(current_user.id, now.year, now.month)
        return render_template(
            "budget.html",
            categories=categories,
            budget_data=budget_data,
            month_str=month_str_default,
            month_name=now.strftime("%B %Y"),
        )

    @app.route("/income", methods=["GET", "POST"])
    @login_required
    def income():
        if request.method == "POST":
            amount = request.form.get("amount", "").strip()
            source = request.form.get("source", "").strip()
            description = request.form.get("description", "").strip()
            date = request.form.get("date", "").strip()

            errors = []
            try:
                amount_val = float(amount)
                if amount_val <= 0:
                    errors.append("Amount must be greater than 0.")
            except ValueError:
                errors.append("Amount must be a valid number.")
            if not source:
                errors.append("Source is required (e.g. Salary).")
            if not date:
                errors.append("Date is required.")
            else:
                try:
                    datetime.strptime(date, "%Y-%m-%d")
                except ValueError:
                    errors.append("Date must be YYYY-MM-DD.")

            if errors:
                for e in errors:
                    flash(e, "error")
            else:
                db.add_income(current_user.id, amount_val, source, date, description)
                flash("Income added successfully!", "success")
            return redirect(url_for("income"))

        entries = db.get_income_entries(current_user.id)
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now()
        month_income = db.get_monthly_income_total(current_user.id, now.year, now.month)
        month_expense = db.get_monthly_expense_total(current_user.id, now.year, now.month)
        return render_template(
            "income.html",
            entries=entries,
            today=today,
            month_income=month_income,
            month_expense=month_expense,
            month_savings=round(month_income - month_expense, 2),
        )

    @app.route("/income/delete/<int:income_id>", methods=["POST"])
    @login_required
    def delete_income(income_id: int):
        if db.delete_income(current_user.id, income_id):
            flash("Income entry deleted.", "info")
        else:
            flash("Income entry not found.", "error")
        return redirect(url_for("income"))

    @app.route("/predictions")
    @login_required
    def predictions():
        prediction = ml.predict_next_month(current_user.id)
        stats = ml.get_spending_stats(current_user.id)
        return render_template("predictions.html", prediction=prediction, stats=stats)

    @app.route("/api/expenses", methods=["GET"])
    @csrf.exempt
    @login_required
    def api_list_expenses():
        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))
        search = request.args.get("q", "").strip()
        category_id = request.args.get("category_id", type=int)
        date_from = request.args.get("date_from", "").strip()
        date_to = request.args.get("date_to", "").strip()
        offset = (page - 1) * per_page

        rows = db.search_expenses(
            current_user.id, search, category_id, date_from, date_to, per_page, offset
        )
        total = db.count_expenses(current_user.id, search, category_id, date_from, date_to)
        return jsonify({
            "page": page,
            "per_page": per_page,
            "total": total,
            "expenses": [db.expense_row_to_dict(r) for r in rows],
        })

    @app.route("/api/expense", methods=["POST"])
    @csrf.exempt
    @login_required
    def api_create_expense():
        data = request.get_json(silent=True) or {}
        errors, cleaned = validate_expense_form(
            str(data.get("amount", "")),
            str(data.get("description", "")),
            str(data.get("category_id", "")),
            str(data.get("date", "")),
        )
        if errors:
            return jsonify({"errors": errors}), 400

        expense_id = db.add_expense(
            current_user.id,
            cleaned["amount"],
            cleaned["description"],
            cleaned["category_id"],
            cleaned["date"],
        )
        expense = db.get_expense_by_id(current_user.id, expense_id)
        return jsonify({"expense": db.expense_row_to_dict(expense)}), 201

    @app.route("/api/expense/<int:expense_id>", methods=["PUT"])
    @csrf.exempt
    @login_required
    def api_update_expense(expense_id: int):
        if not db.get_expense_by_id(current_user.id, expense_id):
            return jsonify({"error": "Not found"}), 404

        data = request.get_json(silent=True) or {}
        errors, cleaned = validate_expense_form(
            str(data.get("amount", "")),
            str(data.get("description", "")),
            str(data.get("category_id", "")),
            str(data.get("date", "")),
        )
        if errors:
            return jsonify({"errors": errors}), 400

        db.update_expense(
            current_user.id,
            expense_id,
            cleaned["amount"],
            cleaned["description"],
            cleaned["category_id"],
            cleaned["date"],
        )
        expense = db.get_expense_by_id(current_user.id, expense_id)
        return jsonify({"expense": db.expense_row_to_dict(expense)})

    @app.route("/api/expense/<int:expense_id>", methods=["DELETE"])
    @csrf.exempt
    @login_required
    def api_delete_expense(expense_id: int):
        if db.delete_expense(current_user.id, expense_id):
            return jsonify({"message": "Deleted"})
        return jsonify({"error": "Not found or access denied"}), 404

    @app.route("/api/monthly-data")
    @login_required
    def api_monthly_data():
        prediction = ml.predict_next_month(current_user.id)
        return jsonify(
            {
                "labels": prediction.get("month_labels", []),
                "amounts": prediction.get("month_amounts", []),
                "regression": prediction.get("regression_line", []),
                "prediction": prediction.get("prediction", 0),
                "trend": prediction.get("trend", ""),
            }
        )

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(_error):
        return render_template("errors/500.html"), 500

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=os.environ.get("FLASK_ENV") != "production", port=int(os.environ.get("PORT", "5000")))

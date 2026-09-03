import sqlite3
from pathlib import Path

DATABASE_PATH = Path(__file__).with_name("expense_tracker.db")


def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _table_columns(conn, table: str) -> set[str]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}


def _migrate_schema(conn) -> None:
    """Add user-scoped columns to existing databases."""
    cur = conn.cursor()
    tables = {row[0] for row in cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    if "expenses" in tables and "user_id" not in _table_columns(conn, "expenses"):
        cur.execute(
            "ALTER TABLE expenses ADD COLUMN user_id INTEGER REFERENCES users(id)"
        )

    if "budgets" in tables and "user_id" not in _table_columns(conn, "budgets"):
        cur.execute("""
            CREATE TABLE budgets_new (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                month       TEXT    NOT NULL,
                amount      REAL    NOT NULL CHECK(amount > 0),
                UNIQUE(user_id, category_id, month),
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (category_id) REFERENCES categories(id)
            )
        """)
        cur.execute("DROP TABLE budgets")
        cur.execute("ALTER TABLE budgets_new RENAME TO budgets")


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT    NOT NULL UNIQUE,
            email         TEXT    NOT NULL UNIQUE,
            password_hash TEXT    NOT NULL,
            created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS categories (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT    NOT NULL UNIQUE,
            color       TEXT    NOT NULL DEFAULT '#3498db',
            icon        TEXT    NOT NULL DEFAULT '💰',
            created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS expenses (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            amount        REAL    NOT NULL CHECK(amount > 0),
            description   TEXT    NOT NULL,
            category_id   INTEGER NOT NULL,
            date          TEXT    NOT NULL,
            created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS budgets (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            month       TEXT    NOT NULL,
            amount      REAL    NOT NULL CHECK(amount > 0),
            UNIQUE(user_id, category_id, month),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS income (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id     INTEGER NOT NULL,
            amount      REAL    NOT NULL CHECK(amount > 0),
            source      TEXT    NOT NULL,
            description TEXT    NOT NULL DEFAULT '',
            date        TEXT    NOT NULL,
            created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            token      TEXT    NOT NULL UNIQUE,
            expires_at TEXT    NOT NULL,
            used       INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS recurring_expenses (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id       INTEGER NOT NULL,
            amount        REAL    NOT NULL CHECK(amount > 0),
            description   TEXT    NOT NULL,
            category_id   INTEGER NOT NULL,
            next_due_date TEXT    NOT NULL,
            active        INTEGER NOT NULL DEFAULT 1,
            created_at    TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (category_id) REFERENCES categories(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS savings_goals (
            id             INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id        INTEGER NOT NULL,
            name           TEXT    NOT NULL,
            target_amount  REAL    NOT NULL CHECK(target_amount > 0),
            current_amount REAL    NOT NULL DEFAULT 0,
            deadline       TEXT,
            created_at     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
        """
    )

    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    INTEGER NOT NULL,
            title      TEXT    NOT NULL,
            message    TEXT    NOT NULL,
            kind       TEXT    NOT NULL DEFAULT 'info',
            dedupe_key TEXT,
            is_read    INTEGER NOT NULL DEFAULT 0,
            created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            UNIQUE(user_id, dedupe_key)
        )
        """
    )

    _migrate_schema(conn)

    cur.execute("SELECT COUNT(*) AS cnt FROM categories")
    if cur.fetchone()["cnt"] == 0:
        default_categories = [
            ("Food & Dining", "#e74c3c", "🍕"),
            ("Transportation", "#3498db", "🚗"),
            ("Entertainment", "#9b59b6", "🎬"),
            ("Shopping", "#e67e22", "🛍️"),
            ("Health & Medical", "#2ecc71", "🏥"),
            ("Education", "#1abc9c", "📚"),
            ("Utilities", "#95a5a6", "💡"),
            ("Rent & Housing", "#34495e", "🏠"),
            ("Other", "#7f8c8d", "📌"),
        ]
        cur.executemany(
            "INSERT INTO categories (name, color, icon) VALUES (?, ?, ?)",
            default_categories,
        )

    conn.commit()
    conn.close()


# ────────────────────────────────────────────────────────────────
# Users
# ────────────────────────────────────────────────────────────────


def create_user(username: str, email: str, password_hash: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (username, email, password_hash)
        VALUES (?, ?, ?)
        """,
        (username.strip(), email.strip().lower(), password_hash),
    )
    user_id = cur.lastrowid
    conn.commit()
    conn.close()
    return int(user_id)


def get_user_by_id(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (int(user_id),))
    row = cur.fetchone()
    conn.close()
    return row


def get_user_by_username(username: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username = ?", (username.strip(),))
    row = cur.fetchone()
    conn.close()
    return row


def get_user_by_email(email: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    row = cur.fetchone()
    conn.close()
    return row


def update_user_profile(user_id: int, email: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET email = ? WHERE id = ?",
        (email.strip().lower(), int(user_id)),
    )
    conn.commit()
    conn.close()


def update_user_password(user_id: int, password_hash: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (password_hash, int(user_id)),
    )
    conn.commit()
    conn.close()


# ────────────────────────────────────────────────────────────────
# Expenses
# ────────────────────────────────────────────────────────────────


def add_expense(user_id: int, amount: float, description: str, category_id: int, date: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO expenses (user_id, amount, description, category_id, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (int(user_id), float(amount), description, int(category_id), date),
    )
    expense_id = cur.lastrowid
    conn.commit()
    conn.close()
    return int(expense_id)


def get_expense_by_id(user_id: int, expense_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            e.id,
            e.user_id,
            e.amount,
            e.description,
            e.date,
            e.category_id,
            c.name  AS category_name,
            c.color AS category_color,
            c.icon  AS category_icon
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        WHERE e.id = ? AND e.user_id = ?
        """,
        (int(expense_id), int(user_id)),
    )
    row = cur.fetchone()
    conn.close()
    return row


def update_expense(
    user_id: int,
    expense_id: int,
    amount: float,
    description: str,
    category_id: int,
    date: str,
) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE expenses
        SET amount = ?, description = ?, category_id = ?, date = ?
        WHERE id = ? AND user_id = ?
        """,
        (float(amount), description, int(category_id), date, int(expense_id), int(user_id)),
    )
    updated = cur.rowcount > 0
    conn.commit()
    conn.close()
    return updated


def get_all_expenses(user_id: int, limit: int | None = None, offset: int = 0):
    conn = get_connection()
    cur = conn.cursor()
    query = """
        SELECT
            e.id,
            e.amount,
            e.description,
            e.date,
            e.category_id,
            c.name  AS category_name,
            c.color AS category_color,
            c.icon  AS category_icon
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = ?
        ORDER BY e.date DESC, e.created_at DESC
    """
    params: list = [int(user_id)]
    if limit is not None:
        query += " LIMIT ? OFFSET ?"
        params.extend([int(limit), int(offset)])
    cur.execute(query, params)
    rows = cur.fetchall()
    conn.close()
    return rows


def count_expenses(
    user_id: int,
    search: str = "",
    category_id: int | None = None,
    date_from: str = "",
    date_to: str = "",
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    where, params = _expense_filter_clause(user_id, search, category_id, date_from, date_to)
    cur.execute(f"SELECT COUNT(*) AS cnt FROM expenses e {where}", params)
    count = int(cur.fetchone()["cnt"])
    conn.close()
    return count


def search_expenses(
    user_id: int,
    search: str = "",
    category_id: int | None = None,
    date_from: str = "",
    date_to: str = "",
    limit: int = 20,
    offset: int = 0,
):
    conn = get_connection()
    cur = conn.cursor()
    where, params = _expense_filter_clause(user_id, search, category_id, date_from, date_to)
    params.extend([int(limit), int(offset)])
    cur.execute(
        f"""
        SELECT
            e.id,
            e.amount,
            e.description,
            e.date,
            e.category_id,
            c.name  AS category_name,
            c.color AS category_color,
            c.icon  AS category_icon
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        {where}
        ORDER BY e.date DESC, e.created_at DESC
        LIMIT ? OFFSET ?
        """,
        params,
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def _expense_filter_clause(
    user_id: int,
    search: str,
    category_id: int | None,
    date_from: str,
    date_to: str,
) -> tuple[str, list]:
    clauses = ["e.user_id = ?"]
    params: list = [int(user_id)]

    if search.strip():
        clauses.append("e.description LIKE ?")
        params.append(f"%{search.strip()}%")

    if category_id:
        clauses.append("e.category_id = ?")
        params.append(int(category_id))

    if date_from:
        clauses.append("e.date >= ?")
        params.append(date_from)

    if date_to:
        clauses.append("e.date <= ?")
        params.append(date_to)

    return "WHERE " + " AND ".join(clauses), params


def delete_expense(user_id: int, expense_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?",
        (int(expense_id), int(user_id)),
    )
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_expenses_for_export(
    user_id: int,
    search: str = "",
    category_id: int | None = None,
    date_from: str = "",
    date_to: str = "",
):
    conn = get_connection()
    cur = conn.cursor()
    where, params = _expense_filter_clause(user_id, search, category_id, date_from, date_to)
    cur.execute(
        f"""
        SELECT
            e.date,
            c.name AS category,
            e.description,
            e.amount
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        {where}
        ORDER BY e.date DESC, e.created_at DESC
        """,
        params,
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_monthly_totals(user_id: int, limit: int = 12):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            strftime('%Y-%m', date) AS month,
            SUM(amount)             AS total
        FROM expenses
        WHERE user_id = ?
        GROUP BY strftime('%Y-%m', date)
        ORDER BY month ASC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_spending_by_category(user_id: int, year: int, month: int):
    conn = get_connection()
    cur = conn.cursor()
    month_str = f"{int(year)}-{int(month):02d}"
    cur.execute(
        """
        SELECT
            c.name  AS category,
            c.color AS color,
            SUM(e.amount) AS total
        FROM expenses e
        JOIN categories c ON e.category_id = c.id
        WHERE e.user_id = ? AND e.date LIKE ?
        GROUP BY c.id
        ORDER BY total DESC
        """,
        (int(user_id), f"{month_str}%"),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_daily_spending(user_id: int, year: int, month: int):
    conn = get_connection()
    cur = conn.cursor()
    month_str = f"{int(year)}-{int(month):02d}"
    cur.execute(
        """
        SELECT
            date,
            SUM(amount) AS total
        FROM expenses
        WHERE user_id = ? AND date LIKE ?
        GROUP BY date
        ORDER BY date
        """,
        (int(user_id), f"{month_str}%"),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def count_user_expenses(user_id: int) -> int:
    return count_expenses(user_id)


def get_highest_category(user_id: int, year: int, month: int):
    rows = get_spending_by_category(user_id, year, month)
    if not rows:
        return None
    return rows[0]


def get_budget_remaining(user_id: int, year: int, month: int) -> float:
    budget_data = get_budget_vs_actual(user_id, year, month)
    total_budget = sum(float(r["budget"]) for r in budget_data)
    total_actual = sum(float(r["actual"]) for r in budget_data)
    return round(max(0.0, total_budget - total_actual), 2)


def get_monthly_expense_total(user_id: int, year: int, month: int) -> float:
    rows = get_spending_by_category(user_id, year, month)
    return round(sum(float(r["total"]) for r in rows), 2)


def get_weekly_spending(user_id: int, year: int, month: int):
    conn = get_connection()
    cur = conn.cursor()
    month_str = f"{int(year)}-{int(month):02d}"
    cur.execute(
        """
        SELECT
            CAST((CAST(strftime('%d', date) AS INTEGER) - 1) / 7 + 1 AS INTEGER) AS week_num,
            SUM(amount) AS total
        FROM expenses
        WHERE user_id = ? AND date LIKE ?
        GROUP BY week_num
        ORDER BY week_num
        """,
        (int(user_id), f"{month_str}%"),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def expense_row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "amount": float(row["amount"]),
        "description": row["description"],
        "date": row["date"],
        "category": row["category_name"],
        "category_id": row["category_id"],
        "category_color": row["category_color"],
        "category_icon": row["category_icon"],
    }


# ────────────────────────────────────────────────────────────────
# Categories
# ────────────────────────────────────────────────────────────────


def get_all_categories():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM categories ORDER BY name")
    rows = cur.fetchall()
    conn.close()
    return rows


# ────────────────────────────────────────────────────────────────
# Budgets
# ────────────────────────────────────────────────────────────────


def set_budget(user_id: int, category_id: int, month: str, amount: float) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO budgets (user_id, category_id, month, amount)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_id, category_id, month)
        DO UPDATE SET amount = excluded.amount
        """,
        (int(user_id), int(category_id), month, float(amount)),
    )
    conn.commit()
    conn.close()


def get_budget_vs_actual(user_id: int, year: int, month: int):
    conn = get_connection()
    cur = conn.cursor()
    month_str = f"{int(year)}-{int(month):02d}"
    cur.execute(
        """
        SELECT
            c.id                                AS category_id,
            c.name                              AS category,
            c.color                             AS color,
            c.icon                              AS icon,
            COALESCE(b.amount, 0)               AS budget,
            COALESCE(SUM(e.amount), 0)          AS actual,
            CASE
                WHEN COALESCE(b.amount, 0) = 0 THEN 0
                ELSE ROUND(COALESCE(SUM(e.amount), 0) / b.amount * 100, 1)
            END                                 AS percentage
        FROM categories c
        LEFT JOIN budgets b
            ON c.id = b.category_id AND b.month = ? AND b.user_id = ?
        LEFT JOIN expenses e
            ON c.id = e.category_id AND e.date LIKE ? AND e.user_id = ?
        GROUP BY c.id
        ORDER BY actual DESC
        """,
        (month_str, int(user_id), f"{month_str}%", int(user_id)),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# ────────────────────────────────────────────────────────────────
# Password reset
# ────────────────────────────────────────────────────────────────


def create_password_reset_token(user_id: int, token: str, expires_at: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO password_reset_tokens (user_id, token, expires_at)
        VALUES (?, ?, ?)
        """,
        (int(user_id), token, expires_at),
    )
    conn.commit()
    conn.close()


def get_valid_reset_token(token: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM password_reset_tokens
        WHERE token = ? AND used = 0 AND expires_at > datetime('now')
        """,
        (token,),
    )
    row = cur.fetchone()
    conn.close()
    return row


def mark_reset_token_used(token: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE token = ?",
        (token,),
    )
    conn.commit()
    conn.close()


# ────────────────────────────────────────────────────────────────
# Income
# ────────────────────────────────────────────────────────────────


def add_income(user_id: int, amount: float, source: str, date: str, description: str = "") -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO income (user_id, amount, source, description, date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (int(user_id), float(amount), source.strip(), description.strip(), date),
    )
    income_id = cur.lastrowid
    conn.commit()
    conn.close()
    return int(income_id)


def get_income_entries(user_id: int, limit: int = 50):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM income
        WHERE user_id = ?
        ORDER BY date DESC, created_at DESC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_monthly_income_total(user_id: int, year: int, month: int) -> float:
    conn = get_connection()
    cur = conn.cursor()
    month_str = f"{int(year)}-{int(month):02d}"
    cur.execute(
        """
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM income
        WHERE user_id = ? AND date LIKE ?
        """,
        (int(user_id), f"{month_str}%"),
    )
    total = float(cur.fetchone()["total"])
    conn.close()
    return round(total, 2)


def delete_income(user_id: int, income_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM income WHERE id = ? AND user_id = ?",
        (int(income_id), int(user_id)),
    )
    deleted = cur.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


# ────────────────────────────────────────────────────────────────
# Recurring expenses
# ────────────────────────────────────────────────────────────────


def add_recurring(user_id: int, amount: float, description: str, category_id: int, next_due_date: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO recurring_expenses (user_id, amount, description, category_id, next_due_date)
        VALUES (?, ?, ?, ?, ?)
        """,
        (int(user_id), float(amount), description, int(category_id), next_due_date),
    )
    rid = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return rid


def get_recurring_list(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT r.*, c.name AS category_name, c.icon AS category_icon
        FROM recurring_expenses r
        JOIN categories c ON c.id = r.category_id
        WHERE r.user_id = ?
        ORDER BY r.next_due_date
        """,
        (int(user_id),),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_due_recurring(user_id: int, as_of_date: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM recurring_expenses
        WHERE user_id = ? AND active = 1 AND next_due_date <= ?
        """,
        (int(user_id), as_of_date),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def update_recurring_next_due(recurring_id: int, user_id: int, next_due_date: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE recurring_expenses SET next_due_date = ? WHERE id = ? AND user_id = ?",
        (next_due_date, int(recurring_id), int(user_id)),
    )
    conn.commit()
    conn.close()


def toggle_recurring(recurring_id: int, user_id: int, active: bool) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE recurring_expenses SET active = ? WHERE id = ? AND user_id = ?",
        (1 if active else 0, int(recurring_id), int(user_id)),
    )
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def delete_recurring(recurring_id: int, user_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM recurring_expenses WHERE id = ? AND user_id = ?",
        (int(recurring_id), int(user_id)),
    )
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


# ────────────────────────────────────────────────────────────────
# Savings goals
# ────────────────────────────────────────────────────────────────


def add_savings_goal(user_id: int, name: str, target_amount: float, deadline: str = "") -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO savings_goals (user_id, name, target_amount, deadline)
        VALUES (?, ?, ?, ?)
        """,
        (int(user_id), name.strip(), float(target_amount), deadline or None),
    )
    gid = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return gid


def get_savings_goals(user_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM savings_goals WHERE user_id = ? ORDER BY created_at DESC",
        (int(user_id),),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def add_to_savings_goal(user_id: int, goal_id: int, amount: float) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE savings_goals SET current_amount = current_amount + ?
        WHERE id = ? AND user_id = ?
        """,
        (float(amount), int(goal_id), int(user_id)),
    )
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def delete_savings_goal(user_id: int, goal_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM savings_goals WHERE id = ? AND user_id = ?",
        (int(goal_id), int(user_id)),
    )
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


# ────────────────────────────────────────────────────────────────
# Notifications
# ────────────────────────────────────────────────────────────────


def upsert_notification(
    user_id: int,
    title: str,
    message: str,
    kind: str = "info",
    dedupe_key: str | None = None,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    if dedupe_key:
        cur.execute(
            """
            INSERT INTO notifications (user_id, title, message, kind, dedupe_key)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, dedupe_key) DO UPDATE SET
                title = excluded.title,
                message = excluded.message,
                kind = excluded.kind,
                is_read = 0,
                created_at = CURRENT_TIMESTAMP
            """,
            (int(user_id), title, message, kind, dedupe_key),
        )
    else:
        cur.execute(
            "INSERT INTO notifications (user_id, title, message, kind) VALUES (?, ?, ?, ?)",
            (int(user_id), title, message, kind),
        )
    conn.commit()
    conn.close()


def get_notifications(user_id: int, limit: int = 30):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM notifications
        WHERE user_id = ?
        ORDER BY is_read ASC, created_at DESC
        LIMIT ?
        """,
        (int(user_id), int(limit)),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def count_unread_notifications(user_id: int) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0",
        (int(user_id),),
    )
    n = int(cur.fetchone()["c"])
    conn.close()
    return n


def mark_notification_read(user_id: int, notification_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
        (int(notification_id), int(user_id)),
    )
    ok = cur.rowcount > 0
    conn.commit()
    conn.close()
    return ok


def mark_all_notifications_read(user_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (int(user_id),))
    conn.commit()
    conn.close()


def get_calendar_spending(user_id: int, year: int, month: int) -> dict[str, float]:
    import calendar as cal

    month_str = f"{int(year)}-{int(month):02d}"
    days_in_month = cal.monthrange(year, month)[1]
    result = {f"{month_str}-{d:02d}": 0.0 for d in range(1, days_in_month + 1)}
    for row in get_daily_spending(user_id, year, month):
        result[row["date"]] = float(row["total"])
    return result

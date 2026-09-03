# Smart Expense Tracker

Full-stack expense tracker with auth, analytics, ML predictions, and smart features.

## Features

### Security
- Registration, login, logout, profile, forgot/reset password
- Per-user data with ownership checks on edit/delete
- CSRF protection, secure session cookies, login rate limiting
- Set `FLASK_SECRET_KEY` in production

### Expenses
- Add, edit, delete, search, pagination
- **Voice input** (browser Web Speech API on Add Expense page)
- **Receipt scan** — paste bill text or upload image (optional Tesseract OCR)
- Export **CSV**, **Excel**, **PDF**

### Recurring & goals
- **Recurring expenses** — Netflix, rent, gym (auto-posted monthly)
- **Savings goals** — target amount, contributions, progress bars

### Notifications
- Budget exceeded / approaching limit
- Prediction increased vs average
- High spending today
- Savings goal reached

### Analytics
- Dashboard charts (daily, weekly, category, trend + regression)
- **Analytics page** — calendar view + spending heatmap
- **Budget page** — progress bars + doughnut progress circles
- Predictions page with documented ML limitations

### AI chat
- Rule-based finance assistant (built-in)
- Optional GPT answers when `OPENAI_API_KEY` is set

### Income & savings
- Track income sources; monthly savings = income − expenses

### REST API (session auth)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/expenses` | List expenses |
| POST | `/api/expense` | Create expense |
| PUT | `/api/expense/<id>` | Update expense |
| DELETE | `/api/expense/<id>` | Delete expense |
| POST | `/api/chat` | JSON `{ "question": "..." }` |
| GET | `/api/monthly-data` | Chart trend data |

### UI
- Sidebar navigation, dark/light theme, glassmorphism cards, responsive mobile layout

## Setup (Windows)

```powershell
cd "f:\Smart Expense Tracker"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000/** and register.

### Optional: receipt OCR

Install [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) and:

```powershell
pip install pytesseract
```

Without Tesseract, paste receipt text manually — regex parsing still works.

### Optional: GPT chat

```powershell
$env:OPENAI_API_KEY="sk-..."
python app.py
```

## Production

```powershell
$env:FLASK_ENV="production"
$env:FLASK_SECRET_KEY="your-long-random-secret"
python app.py
```

## Pages

| Route | Description |
|-------|-------------|
| `/` | Add expense + receipt scan + voice |
| `/expenses` | List, search, export |
| `/recurring` | Recurring templates |
| `/income` | Income tracking |
| `/budget` | Budgets + circle charts |
| `/savings` | Savings goals |
| `/analytics` | Calendar + heatmap |
| `/predictions` | ML forecast |
| `/chat` | AI assistant |
| `/notifications` | Alerts |

## ML note

Linear regression uses sequential month indices; months with zero spend are skipped. See `ml_model.py`.

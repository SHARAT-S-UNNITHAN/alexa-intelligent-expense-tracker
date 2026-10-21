# 💸 Expense Tracker V2 — with ML Integration & Alexa+ Voice Command Support

> **A full-stack personal finance management system** built with Django, SQLite, Scikit-learn, and NLTK — now featuring a simulated **Alexa+ Voice Command API** for the **Amazon Developer Hackathon ("Build, Ship, Shape")**.

---

## 📋 Table of Contents

- [✨ Features Overview](#-features-overview)
- [🆕 Alexa+ Hackathon Update](#-alexa-hackathon-update-new)
- [🗂 Project Structure](#-project-structure)
- [🛠 Tech Stack](#-tech-stack)
- [⚙️ Setup & Installation](#️-setup--installation)
- [🚀 Running the App](#-running-the-app)
- [🔌 API Reference](#-api-reference)
- [🎙 Alexa Voice Command API](#-alexa-voice-command-api)
- [📦 Dependencies](#-dependencies)

---

## ✨ Features Overview

### 1. 💰 Expense Management
- **Add, Edit, Delete** expenses with amount, date, description, and category
- **Paginated expense listing** with multi-column sort (amount ↑↓, date ↑↓)
- **Full-text search** across amount, date, description, and category
- **Daily expense limit** — set a per-user daily cap; exceeding it triggers an automatic **email alert** via Gmail SMTP
- **Future-date validation** — prevents logging expenses with future dates

### 2. 🤖 ML-Powered Category Prediction
- Automatically predicts the category of a new expense from its **description text**
- Pipeline: **NLTK tokenization + stop-word removal → TF-IDF vectorization → RandomForestClassifier**
- Trained on a curated `dataset.csv` of labeled expense descriptions
- **Online learning**: if a user corrects the predicted category, the new label is appended to the dataset and the model retrains via `POST /api/update-dataset/`
- Cosine-similarity search used for closest-match category lookup

### 3. 💵 Income Tracking
- Log income entries with **amount, date, description, and source**
- Custom income **source management** per user (add your own sources)
- Full CRUD with pagination and search
- Category summary view for income analytics

### 4. 📈 Expense Forecasting (ARIMA / ML)
- Uses **ARIMA(5,1,0)** time-series model (via `statsmodels`) on the last 30 expenses
- Forecasts the **next 30 days** of spending
- Generates and saves a **Matplotlib chart** (`static/img/forecast_plot.png`)
- Displays per-category spending totals alongside the forecast
- Requires at least 10 historical data points to run

### 5. 🎯 Savings Goals
- Create savings goals with a **name, start/end date, and target amount**
- Track **current saved amount** against the target
- Auto-calculates:
  - % progress (`saved_percentage`)
  - **Daily savings required** to hit the goal on time
- Full goal CRUD per user

### 6. 📊 Visual Analytics & Stats
- **Doughnut / bar charts** showing expense breakdown by category (last 6 months)
- Income vs. expense comparison view
- Interactive stats dashboard page at `/stats/`

### 7. 📧 Automated Email Reports (Celery + Redis)
- **Weekly reports** — sent every Sunday as an Excel (`.xlsx`) attachment
- **Monthly reports** — sent on the 1st of each month
- Reports cover income entries per user, generated with `pandas` + `openpyxl`
- Celery worker + Redis broker handles background scheduling
- Gmail SMTP integration for delivery

### 8. 🌍 Multi-Currency Support
- Users can set their preferred currency from a comprehensive `currencies.json` list
- Currency symbol displayed throughout the UI

### 9. 👤 User Authentication & Profiles
- Full **register / login / logout** flow with Django's auth system
- User profile management
- Per-user data isolation — every model is owner-scoped

### 10. 🔌 REST API (Django REST Framework)
| Endpoint | Method | Description |
|---|---|---|
| `/api/predict-category/` | `POST` | Predict expense category from description text |
| `/api/update-dataset/` | `POST` | Append a corrected label and retrain the model |

---

## 🆕 Alexa+ Hackathon Update *(NEW)*

> **Amazon Developer Hackathon — "Build, Ship, Shape" · Alexa+ Track**

A production-ready **simulated Alexa voice intent API** has been integrated into the project. It accepts a plain-text voice command, classifies the intent using NLP, interacts with the expense database and ML pipeline, and returns a structured JSON response with a **speech output string** — exactly what a real Alexa skill would send back.

### Endpoint

```
POST /alexa/voice-command/
```

### Authentication
Pass your Django username in the header — no login page, no cookies, curl-ready:
```
X-Alexa-Session-Token: <your_username>
```

### Supported Intents

| Intent | Trigger Phrases | What it does |
|---|---|---|
| `LogExpenseIntent` | *"log 500 rupees for groceries"*, *"add 200 for transport"* | Predicts category via ML → **saves to DB** |
| `GetBudgetSummaryIntent` | *"budget summary"*, *"how much left"* | Queries current-month total & top category |
| `GetSpendingInsightIntent` | *"show my spending"*, *"total expenses"* | Full category-wise breakdown for the month |
| `GetTopCategoryIntent` | *"top category"*, *"biggest expense"* | Identifies where you spent the most |
| `GetMLPredictionIntent` | *"predict my budget"*, *"forecast next month"* | Weighted 6-month rolling-average ML forecast |

### Sample Request & Response

**Request:**
```bash
curl -s -X POST http://127.0.0.1:8000/alexa/voice-command/ \
  -H "Content-Type: application/json" \
  -H "X-Alexa-Session-Token: sharat" \
  -d "{\"voice_command\": \"Alexa, log 500 rupees for groceries\"}" | python -m json.tool
```

**Response:**
```json
{
    "alexa_speech_output": "Got it! I have logged an expense of Rs.500.00 for groceries, categorized as Food using our machine learning model. The record has been saved to your expense tracker.",
    "tracker_metadata": {
        "action": "expense_logged",
        "expense_id": 42,
        "amount": 500.0,
        "currency": "INR",
        "description": "groceries",
        "ml_predicted_category": "Food",
        "persisted_to_db": true,
        "logged_at": "2026-10-21T15:32:10.123456+00:00",
        "intent_detected": "LogExpenseIntent",
        "parsed_slots": { "amount": 500.0, "currency": "INR", "description": "groceries" },
        "raw_command": "Alexa, log 500 rupees for groceries",
        "user": "sharat"
    },
    "alexa_intent": "LogExpenseIntent",
    "alexa_version": "1.0",
    "request_id": "a3f1c2d4-7e89-...",
    "status": "success"
}
```

### All Demo curl Commands

```bash
# 1. Log an expense (saves to DB + ML category prediction)
curl -s -X POST http://127.0.0.1:8000/alexa/voice-command/ \
  -H "Content-Type: application/json" -H "X-Alexa-Session-Token: sharat" \
  -d "{\"voice_command\": \"Alexa, log 500 rupees for groceries\"}" | python -m json.tool

# 2. Budget summary for current month
curl -s -X POST http://127.0.0.1:8000/alexa/voice-command/ \
  -H "Content-Type: application/json" -H "X-Alexa-Session-Token: sharat" \
  -d "{\"voice_command\": \"Alexa, what is my budget summary\"}" | python -m json.tool

# 3. Category-wise spending breakdown
curl -s -X POST http://127.0.0.1:8000/alexa/voice-command/ \
  -H "Content-Type: application/json" -H "X-Alexa-Session-Token: sharat" \
  -d "{\"voice_command\": \"Alexa, show me my spending insights\"}" | python -m json.tool

# 4. Top spending category
curl -s -X POST http://127.0.0.1:8000/alexa/voice-command/ \
  -H "Content-Type: application/json" -H "X-Alexa-Session-Token: sharat" \
  -d "{\"voice_command\": \"Alexa, what is my top spending category\"}" | python -m json.tool

# 5. ML budget prediction for next month
curl -s -X POST http://127.0.0.1:8000/alexa/voice-command/ \
  -H "Content-Type: application/json" -H "X-Alexa-Session-Token: sharat" \
  -d "{\"voice_command\": \"Alexa, predict my budget for next month\"}" | python -m json.tool
```

### How it integrates with the existing ML pipeline

```
voice_command (text)
       |
       v
 _parse_intent()  <-- regex NLU / intent router
       |
       |-- LogExpenseIntent  -->  tfidf_vectorizer  (from expenses/views.py)
       |                          RandomForestClassifier (from expenses/views.py)
       |                          Expense.objects.create(...)  <-- writes to SQLite
       |
       |-- GetBudgetSummaryIntent / GetSpendingInsightIntent / GetTopCategoryIntent
       |                    -->  Expense.objects.filter(owner, month) <-- reads from SQLite
       |
       +-- GetMLPredictionIntent -->  Weighted 6-month rolling average forecast
```

> The Alexa layer **imports** the already-fitted `tfidf_vectorizer` and `RandomForestClassifier`
> from `expenses/views.py` — zero re-training cost, the exact same model the app uses.

### Files Added/Modified

| File | Change | Purpose |
|---|---|---|
| `alexa_voice/views.py` | **Created** | NLU parser, 5 intent handlers, DB writes, ML inference |
| `alexa_voice/urls.py` | **Created** | Registers `POST /alexa/voice-command/` |
| `expensetracker/urls.py` | **Modified** | Added `path('alexa/', include('alexa_voice.urls'))` |

---

## 🗂 Project Structure

```
EXPENSE_TRACKER_V2_BY_SHA/
|
|-- expensetracker/         # Django project config (settings, root URLs)
|   |-- settings.py
|   |-- urls.py
|   +-- celery.py           # Celery app config
|
|-- expenses/               # Core expense tracking app
|   |-- models.py           # Expense, Category, ExpenseLimit
|   +-- views.py            # CRUD + ML pipeline (TF-IDF + RandomForest)
|
|-- userincome/             # Income tracking app
|   |-- models.py           # UserIncome, Source
|   +-- views.py
|
|-- expense_forecast/       # ARIMA forecasting app
|   +-- views.py            # ARIMA(5,1,0) + Matplotlib chart generation
|
|-- goals/                  # Savings goals app
|   |-- models.py           # Goal (name, target, progress calculator)
|   +-- views.py
|
|-- report_generation/      # Celery background task for email reports
|   +-- tasks.py            # Weekly + monthly Excel reports via email
|
|-- api/                    # Django REST Framework API
|   |-- views.py            # PredictCategory, UpdateDataset
|   +-- serializers.py
|
|-- alexa_voice/            # NEW: Alexa+ Hackathon integration
|   |-- views.py            # Voice intent handler (5 intents + ML + DB)
|   +-- urls.py             # POST /alexa/voice-command/
|
|-- authentication/         # Register / Login / Logout
|-- userpreferences/        # Currency preference per user
|-- userprofile/            # User profile management
|
|-- templates/              # HTML templates (per-app subdirectories)
|-- static/                 # CSS, JS, images
|-- dataset.csv             # Labeled training data for ML categoriser
|-- manage.py
+-- requirements.txt
```

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| **Backend Framework** | Django 5.1.5 |
| **Database** | SQLite (via Django ORM) |
| **REST API** | Django REST Framework 3.15.2 |
| **Machine Learning** | Scikit-learn 1.6.1 (TF-IDF + RandomForest) |
| **NLP** | NLTK 3.9.1 (tokenization, stop-word removal) |
| **Time-Series Forecasting** | Statsmodels 0.14.4 (ARIMA) |
| **Data Processing** | Pandas 2.2.3, NumPy 2.2.2 |
| **Visualisation** | Matplotlib 3.10.0 |
| **Background Tasks** | Celery + Redis |
| **Email** | Django SMTP (Gmail) |
| **Excel Reports** | OpenPyXL 3.1.5 |
| **PDF Generation** | ReportLab, xhtml2pdf |
| **Voice Integration** | Custom NLU layer -- Alexa+ simulated intent API |

---

## ⚙️ Setup & Installation

### Prerequisites
- Python 3.10+
- Redis (for Celery — optional, only needed for automated email reports)
- Git

### 1. Clone the repository
```bash
git clone <repo-url>
cd "EXPENSE_TRACKER_V2_BY_SHA - Copy"
```

### 2. Create and activate a virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

### 3. Install all dependencies
```bash
pip install -r requirements.txt
```

### 4. Download NLTK data
```bash
python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords')"
```

### 5. Apply migrations
```bash
python manage.py migrate
```

### 6. Create a superuser / admin account
```bash
python manage.py createsuperuser
```

---

## 🚀 Running the App

### Development server
```bash
python manage.py runserver
```

Visit: **http://127.0.0.1:8000/**

### Celery worker (for automated email reports — optional)
```bash
# Requires Redis to be running
celery -A expensetracker worker --loglevel=info
```

---

## 🔌 API Reference

### `POST /api/predict-category/`
Predict the expense category for a given description.

**Body:** `{ "description": "bought vegetables from market" }`  
**Response:** `{ "predicted_category": "Groceries" }`

---

### `POST /api/update-dataset/`
Append a corrected description→category pair and retrain the ML model.

**Body:** `{ "new_data": { "description": "netflix subscription", "category": "Entertainment" } }`

---

## 🎙 Alexa Voice Command API

See the **Alexa+ Hackathon Update** section above for the full reference.

**Quick test:**
```bash
curl -s -X POST http://127.0.0.1:8000/alexa/voice-command/ \
  -H "Content-Type: application/json" \
  -H "X-Alexa-Session-Token: YOUR_USERNAME" \
  -d "{\"voice_command\": \"Alexa, log 200 rupees for transport\"}" | python -m json.tool
```

---

## 📦 Key Dependencies

```
Django==5.1.5
djangorestframework==3.15.2
scikit-learn==1.6.1
nltk==3.9.1
statsmodels==0.14.4
pandas==2.2.3
numpy==2.2.2
matplotlib==3.10.0
openpyxl==3.1.5
reportlab==4.2.5
xhtml2pdf==0.2.16
requests==2.32.3
```

Install everything:
```bash
pip install -r requirements.txt
```

---

## 👨‍💻 Author

**Sharat S Unnithan**  
Minor Project — Expense Tracker V2 with ML Integration  
Amazon Developer Hackathon Submission — Alexa+ Track · October 2026

---

> *Built with Django · Scikit-learn · NLTK · Statsmodels · Celery · and a little bit of Alexa magic ✨*

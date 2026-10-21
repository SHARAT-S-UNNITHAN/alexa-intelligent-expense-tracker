"""
alexa_voice/views.py
────────────────────────────────────────────────────────────────────────────────
Alexa+ Simulated Voice Intent Handler
Amazon Developer Hackathon – "Build, Ship, Shape"

Endpoint : POST /alexa/voice-command/
Auth     : Header  X-Alexa-Session-Token: <django_username>
           Falls back to the active Django session cookie automatically.
Payload  : { "voice_command": "Alexa, log 500 rupees for groceries" }

Supported intents
─────────────────
  LogExpenseIntent          – log / add / spend  <amount> [currency] for <desc>
  GetBudgetSummaryIntent    – what is my budget / budget summary / how much left
  GetSpendingInsightIntent  – how much did I spend / total expenses / insights
  GetTopCategoryIntent      – top category / biggest expense / most spent
  GetMLPredictionIntent     – predict / forecast / ml prediction / next month
────────────────────────────────────────────────────────────────────────────────
"""

import re
import json
import uuid
import logging
import datetime

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.models import User
from django.utils.timezone import now

# ── Re-use the project's already-fitted ML artefacts (zero extra training cost)
from expenses.models import Expense
from expenses.views import (
    tfidf_vectorizer,
    model as category_classifier,
    preprocess_text,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

SUPPORTED_INTENTS = [
    "LogExpenseIntent",
    "GetBudgetSummaryIntent",
    "GetSpendingInsightIntent",
    "GetTopCategoryIntent",
    "GetMLPredictionIntent",
]

CURRENCY_ALIASES = {
    "rupee": "INR", "rupees": "INR", "rs": "INR", "inr": "INR",
    "dollar": "USD", "dollars": "USD", "usd": "USD",
    "pound": "GBP",  "pounds": "GBP",  "gbp": "GBP",
    "euro": "EUR",   "euros": "EUR",   "eur": "EUR",
}

CURRENCY_SYMBOLS = {"INR": "₹", "USD": "$", "GBP": "£", "EUR": "€"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_user(request):
    """
    Resolve the acting user.
    Priority: X-Alexa-Session-Token header → active Django session.
    Returns a User instance or None.
    """
    token = request.headers.get("X-Alexa-Session-Token", "").strip()
    if token:
        try:
            return User.objects.get(username=token)
        except User.DoesNotExist:
            return None
    if hasattr(request, "user") and request.user.is_authenticated:
        return request.user
    return None


def _parse_intent(raw_command: str) -> dict:
    """
    Lightweight NLU: maps a free-text voice command to an Alexa-style intent
    + slot dictionary.
    """
    cmd = raw_command.lower().strip()
    # Strip Alexa wake-word prefixes
    cmd = re.sub(
        r"^(alexa[,\s]+|hey\s+alexa[,\s]+|ok\s+alexa[,\s]+)", "", cmd
    ).strip()

    # ── LogExpenseIntent ──────────────────────────────────────────────────────
    log_re = re.compile(
        r"(?:log|add|record|spend|spent|track)\s+"
        r"(?P<amount>[\d,]+(?:\.\d{1,2})?)\s*"
        r"(?P<currency_word>[a-z]+)?\s*"
        r"(?:rupees?|inr|dollars?|usd|pounds?|euros?)?\s*"
        r"(?:for|on|in|towards?)?\s*"
        r"(?P<description>.+)?",
        re.IGNORECASE,
    )
    m = log_re.match(cmd)
    if m:
        raw_amt = m.group("amount").replace(",", "")
        cword = (m.group("currency_word") or "").lower()
        description = (m.group("description") or "miscellaneous").strip()
        currency = CURRENCY_ALIASES.get(cword, "INR")
        try:
            amount = float(raw_amt)
        except ValueError:
            amount = 0.0
        return {
            "intent": "LogExpenseIntent",
            "slots": {"amount": amount, "currency": currency, "description": description},
        }

    # ── GetMLPredictionIntent (check before spending-insight to avoid overlap) ─
    if any(kw in cmd for kw in ("predict", "forecast", "next month", "ml prediction", "machine learning")):
        return {"intent": "GetMLPredictionIntent", "slots": {}}

    # ── GetBudgetSummaryIntent ────────────────────────────────────────────────
    if any(kw in cmd for kw in ("budget", "how much left", "remaining", "budget summary")):
        return {"intent": "GetBudgetSummaryIntent", "slots": {}}

    # ── GetTopCategoryIntent ──────────────────────────────────────────────────
    if any(kw in cmd for kw in ("top category", "biggest expense", "most spent", "where did i spend")):
        return {"intent": "GetTopCategoryIntent", "slots": {}}

    # ── GetSpendingInsightIntent ──────────────────────────────────────────────
    if any(kw in cmd for kw in ("how much", "spend", "spent", "total", "expense", "summary", "insight")):
        return {"intent": "GetSpendingInsightIntent", "slots": {}}

    return {"intent": "UnknownIntent", "slots": {}}


def _ml_predict_category(description: str) -> str:
    """Use the project's existing TF-IDF + RandomForest pipeline."""
    try:
        cleaned = preprocess_text(description)
        vec = tfidf_vectorizer.transform([cleaned])
        return str(category_classifier.predict(vec)[0])
    except Exception as exc:
        logger.warning("ML category prediction failed: %s", exc)
        return "Miscellaneous"


def _monthly_stats(user: User) -> dict:
    """Aggregate expenses for the current calendar month."""
    today = datetime.date.today()
    qs = Expense.objects.filter(
        owner=user, date__year=today.year, date__month=today.month
    )
    total = 0.0
    by_category: dict = {}
    for exp in qs:
        total += exp.amount
        by_category[exp.category] = round(
            by_category.get(exp.category, 0.0) + exp.amount, 2
        )
    top_cat = max(by_category, key=by_category.get) if by_category else "N/A"
    return {
        "total_this_month": round(total, 2),
        "by_category": by_category,
        "top_category": top_cat,
        "expense_count": qs.count(),
        "month": today.strftime("%B %Y"),
    }


def _ml_forecast_next_month(user: User) -> dict:
    """
    Weighted 6-month moving-average forecast.
    (Lightweight alternative to ARIMA – works even with < 10 data points.)
    """
    today = datetime.date.today()
    monthly_totals = []
    for delta in range(1, 7):
        ref = today.replace(day=1) - datetime.timedelta(days=delta * 28)
        total = sum(
            e.amount for e in Expense.objects.filter(
                owner=user, date__year=ref.year, date__month=ref.month
            )
        )
        monthly_totals.append(total)

    if not any(monthly_totals):
        return {
            "predicted_next_month_total": 0.0,
            "trend": "unknown",
            "confidence": "low",
            "basis": "no_historical_data",
        }

    weights = list(range(len(monthly_totals), 0, -1))   # [6,5,4,3,2,1]
    predicted = round(
        sum(t * w for t, w in zip(monthly_totals, weights)) / sum(weights), 2
    )
    trend = "increasing" if monthly_totals[0] > monthly_totals[-1] else "decreasing"
    return {
        "predicted_next_month_total": predicted,
        "trend": trend,
        "confidence": "medium",
        "basis": "weighted_6_month_average",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Intent handlers  →  each returns (speech: str, metadata: dict, http_code: int)
# ─────────────────────────────────────────────────────────────────────────────

def _handle_log_expense(slots, user):
    amount: float = slots.get("amount", 0.0)
    currency: str = slots.get("currency", "INR")
    description: str = slots.get("description", "miscellaneous")

    if amount <= 0:
        speech = (
            "Sorry, I couldn't determine a valid amount from your command. "
            "Please say something like: Alexa, log 500 rupees for groceries."
        )
        return speech, {"error": "invalid_amount", "raw_slots": slots}, 400

    predicted_category = _ml_predict_category(description)
    symbol = CURRENCY_SYMBOLS.get(currency, currency)

    saved, expense_id = False, None
    if user:
        exp = Expense.objects.create(
            owner=user,
            amount=amount,
            date=datetime.date.today(),
            category=predicted_category,
            description=description,
        )
        saved, expense_id = True, exp.pk

    speech = (
        f"Got it! I've logged an expense of {symbol}{amount:,.2f} "
        f"for {description}, categorized as {predicted_category} "
        f"using our machine learning model."
        + (" The record has been saved to your expense tracker." if saved
           else " Note: expense was not saved — no authenticated user found.")
    )
    metadata = {
        "action": "expense_logged",
        "expense_id": expense_id,
        "amount": amount,
        "currency": currency,
        "description": description,
        "ml_predicted_category": predicted_category,
        "persisted_to_db": saved,
        "logged_at": now().isoformat(),
    }
    return speech, metadata, 200 if saved else 206


def _handle_budget_summary(user):
    if not user:
        return (
            "I need you to be logged in to retrieve your budget summary.",
            {"error": "unauthenticated"},
            401,
        )
    stats = _monthly_stats(user)
    speech = (
        f"Here's your budget summary for {stats['month']}. "
        f"You've spent a total of ₹{stats['total_this_month']:,.2f} "
        f"across {stats['expense_count']} expenses. "
        f"Your top spending category this month is {stats['top_category']}."
    )
    return speech, {"action": "budget_summary", **stats}, 200


def _handle_spending_insight(user):
    if not user:
        return (
            "Please authenticate first so I can retrieve your spending insights.",
            {"error": "unauthenticated"},
            401,
        )
    stats = _monthly_stats(user)
    breakdown = ", ".join(
        f"{cat}: ₹{amt:,.2f}" for cat, amt in stats["by_category"].items()
    ) or "no expenses recorded yet"
    speech = (
        f"In {stats['month']} you've recorded {stats['expense_count']} expenses "
        f"totalling ₹{stats['total_this_month']:,.2f}. "
        f"Category breakdown — {breakdown}."
    )
    return speech, {"action": "spending_insight", **stats}, 200


def _handle_top_category(user):
    if not user:
        return ("Authentication required.", {"error": "unauthenticated"}, 401)
    stats = _monthly_stats(user)
    top = stats["top_category"]
    top_amount = stats["by_category"].get(top, 0.0)
    speech = (
        f"Your biggest spending category this month is {top}, "
        f"with ₹{top_amount:,.2f} spent so far in {stats['month']}."
    )
    return speech, {"action": "top_category", "top_category": top, "amount": top_amount}, 200


def _handle_ml_prediction(user):
    if not user:
        return ("Authentication required for ML predictions.", {"error": "unauthenticated"}, 401)
    forecast = _ml_forecast_next_month(user)
    predicted = forecast["predicted_next_month_total"]
    trend = forecast.get("trend", "stable")
    speech = (
        f"Based on your last six months of spending, our machine learning model "
        f"predicts you will spend approximately ₹{predicted:,.2f} next month. "
        f"Your spending trend is currently {trend}. "
        f"Consider reviewing your {_monthly_stats(user)['top_category']} expenses to stay on budget."
    )
    return speech, {"action": "ml_budget_prediction", **forecast}, 200


def _handle_unknown():
    speech = (
        "I'm sorry, I didn't understand that command. "
        "You can ask me to log an expense, get a budget summary, "
        "check spending insights, find your top category, "
        "or predict next month's budget using machine learning."
    )
    return speech, {"error": "unknown_intent", "supported_intents": SUPPORTED_INTENTS}, 422


# ─────────────────────────────────────────────────────────────────────────────
# Main view
# ─────────────────────────────────────────────────────────────────────────────

@csrf_exempt
@require_http_methods(["POST"])
def alexa_voice_command(request):
    """
    POST /alexa/voice-command/

    Headers (optional but recommended for demo)
    ────────────────────────────────────────────
    Content-Type          : application/json
    X-Alexa-Session-Token : <django_username>

    Request body
    ────────────
    {
        "voice_command": "Alexa, log 500 rupees for groceries"
    }

    Response schema
    ───────────────
    {
        "alexa_speech_output"  : "Got it! I've logged ...",
        "tracker_metadata"     : { ... },
        "alexa_intent"         : "LogExpenseIntent",
        "alexa_version"        : "1.0",
        "request_id"           : "<uuid4>",
        "status"               : "success" | "partial" | "error"
    }
    """
    # ── Parse body ────────────────────────────────────────────────────────────
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse(
            {
                "alexa_speech_output": "Invalid request. Please send a valid JSON body.",
                "tracker_metadata": {"error": "malformed_json"},
                "alexa_intent": None,
                "alexa_version": "1.0",
                "request_id": str(uuid.uuid4()),
                "status": "error",
            },
            status=400,
        )

    raw_command: str = body.get("voice_command", "").strip()
    if not raw_command:
        return JsonResponse(
            {
                "alexa_speech_output": "No voice command received. Please include a 'voice_command' field.",
                "tracker_metadata": {"error": "missing_voice_command"},
                "alexa_intent": None,
                "alexa_version": "1.0",
                "request_id": str(uuid.uuid4()),
                "status": "error",
            },
            status=400,
        )

    # ── Resolve user & parse intent ───────────────────────────────────────────
    user = _resolve_user(request)
    parsed = _parse_intent(raw_command)
    intent: str = parsed["intent"]
    slots: dict = parsed["slots"]

    # ── Dispatch ──────────────────────────────────────────────────────────────
    dispatch = {
        "LogExpenseIntent":         lambda: _handle_log_expense(slots, user),
        "GetBudgetSummaryIntent":   lambda: _handle_budget_summary(user),
        "GetSpendingInsightIntent": lambda: _handle_spending_insight(user),
        "GetTopCategoryIntent":     lambda: _handle_top_category(user),
        "GetMLPredictionIntent":    lambda: _handle_ml_prediction(user),
    }
    speech, metadata, http_status = dispatch.get(intent, _handle_unknown)()

    # ── Build response ────────────────────────────────────────────────────────
    status_label = {200: "success", 201: "success", 206: "partial"}.get(
        http_status, "error"
    )
    payload = {
        "alexa_speech_output": speech,
        "tracker_metadata": {
            **metadata,
            "intent_detected": intent,
            "parsed_slots": slots,
            "raw_command": raw_command,
            "user": user.username if user else "anonymous",
        },
        "alexa_intent": intent,
        "alexa_version": "1.0",
        "request_id": str(uuid.uuid4()),
        "status": status_label,
    }

    logger.info(
        "AlexaVoice | intent=%s | user=%s | http=%s",
        intent,
        user.username if user else "anonymous",
        http_status,
    )
    return JsonResponse(payload, status=http_status, json_dumps_params={"ensure_ascii": False})

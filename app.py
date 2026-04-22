"""
MBANK hackathon MVP - Stage 3.
Flask backend for the MBANK-style demo app.
Run: python app.py
"""

from __future__ import annotations

import json as _json
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS

BASE_DIR = Path(__file__).resolve().parent


def load_local_env() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip().lstrip("\ufeff")] = value.strip().strip('"').strip("'")


load_local_env()

DATABASE_PATH = os.getenv("MBANK_DB_PATH", str(BASE_DIR / "mbank_state.sqlite3"))
GROQ_API_KEY_RAW = os.getenv("GROQ_API_KEY", "").strip()
GROQ_API_KEY = "" if GROQ_API_KEY_RAW.lower() in {"", "your_groq_key_here", "your_key_here"} else GROQ_API_KEY_RAW
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
ASSISTANT_NAME = "Sezim AI"
ALLOWED_AI_ACTIONS = {
    "transfer",
    "bill",
    "add_goal",
    "deposit_goal",
    "apply_plan",
    "offer",
    "streak_checkin",
    "complete_mission",
    "open_screen",
}
AI_CAPABILITIES_PROMPT = """
Sezim AI has full app context and can prepare actions for every important MBANK demo workflow.
Never execute state-changing operations directly in text. For money movement, bills, goals, missions,
autopilot, or offers, explain briefly and return exactly one JSON action. The frontend will ask the user
to confirm before execution.

Allowed JSON actions:
{"action":"transfer","contact":"Name","amount":1000,"tag":"family|debt|food|taxi|service|gift|travel|rent|health|shared|savings"}
{"action":"bill","bill":"gas|electric|water|kino","amount":890}
{"action":"add_goal","name":"Goal name","target":30000}
{"action":"deposit_goal","goal_id":1,"amount":5000}
{"action":"apply_plan"}
{"action":"offer","offer_id":"reserve|autopay|savings_boost|travel_goal"}
{"action":"streak_checkin"}
{"action":"complete_mission","mission_id":"autopilot|budget_day|save_goal|autopay|tagged_transfer|streak_5"}
{"action":"open_screen","screen":"screen-home|screen-autopilot|screen-risk|screen-missions|screen-goals|screen-history|screen-bills|screen-profile"}
"""
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("MBANK_CORS_ORIGINS", "http://localhost:5000,http://127.0.0.1:5000").split(",")
    if origin.strip()
]

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": CORS_ORIGINS}})

EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\uFE0F]+", re.UNICODE)


def initial_db() -> dict[str, Any]:
    return {
        "user": {
            "name": "Айдар Бекторов",
            "phone": "+996 700 123 456",
            "avatar": "АБ",
            "verified": True,
            "health_score": 78,
            "personality": "Импульсивный оптимист",
            "safe_daily_budget": 1627,
            "monthly_focus": "Накопить на ноутбук без кассового разрыва",
            "reserve_limit_active": False,
            "reserve_limit": 35000,
        },
        "products": {
            "m_plus": {"available": True, "preapproved_limit": 35000, "active": False},
            "reserve": {"available": True, "active": False, "limit": 25000},
            "savings_boost": {"active": True},
        },
        "autopilot": {
            "cycle": "Апрель 2026",
            "applied": False,
            "applied_at": None,
            "last_salary_amount": 65000,
            "last_salary_date": "Сегодня, 09:00",
        },
        "tags": [
            {"id": "family", "label": "Семья", "icon": "СМ", "color": "#0EA5E9", "logic_hint": "family_support"},
            {"id": "debt", "label": "Долг", "icon": "ДЛ", "color": "#F97316", "logic_hint": "cash_pressure"},
            {"id": "food", "label": "Еда", "icon": "ЕД", "color": "#F59E0B", "logic_hint": "daily_spend"},
            {"id": "taxi", "label": "Такси", "icon": "ТК", "color": "#3B82F6", "logic_hint": "transport_spend"},
            {"id": "service", "label": "Услуга", "icon": "УС", "color": "#14B8A6", "logic_hint": "service_payment"},
            {"id": "gift", "label": "Подарок", "icon": "ПД", "color": "#EC4899", "logic_hint": "seasonal"},
            {"id": "travel", "label": "Поездка", "icon": "ПТ", "color": "#8B5CF6", "logic_hint": "future_goal"},
            {"id": "rent", "label": "Квартира", "icon": "КВ", "color": "#14B8A6", "logic_hint": "fixed_cost"},
            {"id": "health", "label": "Здоровье", "icon": "ЗД", "color": "#06B6D4", "logic_hint": "essential"},
            {"id": "shared", "label": "Совместные", "icon": "СВ", "color": "#84CC16", "logic_hint": "shared_spend"},
            {"id": "savings", "label": "Накопления", "icon": "НК", "color": "#009E60", "logic_hint": "healthy"},
        ],
        "accounts": [
            {"id": "main", "label": "Основной счёт", "balance": 48750, "card_number": "•••• 4521", "type": "VISA", "color": "main"},
            {"id": "save", "label": "Накопительный", "balance": 120000, "card_number": "•••• 8833", "type": "GOLD", "color": "gold"},
        ],
        "contacts": [
            {"id": 1, "name": "Адиль Сейткали", "phone": "+996700111222", "initials": "АС", "color": "#1DB954", "default_tag": "shared"},
            {"id": 2, "name": "Марат Джакыпов", "phone": "+996555333444", "initials": "МД", "color": "#5AABFF", "default_tag": "debt"},
            {"id": 3, "name": "Айгуль Токтосунова", "phone": "+996700555666", "initials": "АТ", "color": "#B57BFF", "default_tag": "family"},
            {"id": 4, "name": "Бакыт Осмонов", "phone": "+996555777888", "initials": "БО", "color": "#F96060", "default_tag": "gift"},
            {"id": 5, "name": "Нурия Асанова", "phone": "+996700999000", "initials": "НА", "color": "#FF9D3A", "default_tag": "family"},
            {"id": 6, "name": "Чингиз Бердиев", "phone": "+996555123456", "initials": "ЧБ", "color": "#FFCA3A", "default_tag": "travel"},
        ],
        "transactions": [
            {"id": 1, "name": "Зарплата", "category": "income", "amount": 65000, "icon": "ЗП", "bg": "#0E3A1C", "date": "Сегодня, 09:00", "dir": "in", "account": "main", "tag": "savings", "kind": "salary"},
            {"id": 2, "name": "Globus", "category": "groceries", "amount": 1240, "icon": "ПР", "bg": "#2A1E00", "date": "Сегодня, 14:23", "dir": "out", "account": "main", "tag": "shared", "kind": "merchant"},
            {"id": 3, "name": "Яндекс Такси", "category": "transport", "amount": 350, "icon": "ТР", "bg": "#0A2040", "date": "Вчера, 21:15", "dir": "out", "account": "main", "tag": None, "kind": "merchant"},
            {"id": 4, "name": "Coffee House", "category": "restaurants", "amount": 280, "icon": "КФ", "bg": "#2A0A18", "date": "Вчера, 10:30", "dir": "out", "account": "main", "tag": None, "kind": "merchant"},
            {"id": 5, "name": "→ Айгуль", "category": "transfer", "amount": 2800, "icon": "ПН", "bg": "#0A2040", "date": "24 мар, 20:12", "dir": "out", "account": "main", "tag": "family", "kind": "phone_transfer", "phone": "+996700555666"},
            {"id": 6, "name": "→ Марат", "category": "transfer", "amount": 3200, "icon": "ПН", "bg": "#0A2040", "date": "22 мар, 18:08", "dir": "out", "account": "main", "tag": "debt", "kind": "phone_transfer", "phone": "+996555333444"},
            {"id": 7, "name": "Азия Маркет", "category": "groceries", "amount": 890, "icon": "ПР", "bg": "#2A1E00", "date": "20 мар, 18:40", "dir": "out", "account": "main", "tag": "shared", "kind": "merchant"},
            {"id": 8, "name": "Cineman", "category": "entertainment", "amount": 600, "icon": "ДС", "bg": "#1A0A2E", "date": "19 мар, 20:00", "dir": "out", "account": "main", "tag": "gift", "kind": "merchant"},
            {"id": 9, "name": "Аптека 36.6", "category": "health", "amount": 420, "icon": "ЗД", "bg": "#0A2040", "date": "18 мар, 11:00", "dir": "out", "account": "main", "tag": "health", "kind": "merchant"},
            {"id": 10, "name": "Перевод от Марата", "category": "income", "amount": 2000, "icon": "ПР", "bg": "#0E3A1C", "date": "17 мар, 15:30", "dir": "in", "account": "main", "tag": "debt", "kind": "transfer_in"},
            {"id": 11, "name": "Dodo Pizza", "category": "restaurants", "amount": 780, "icon": "ЕД", "bg": "#2A0A18", "date": "16 мар, 19:45", "dir": "out", "account": "main", "tag": None, "kind": "merchant"},
        ],
        "goals": [
            {"id": 1, "name": "Ноутбук", "icon": "НБ", "bg": "#0A2040", "target": 80000, "saved": 48350, "deadline": "Август 2026"},
            {"id": 2, "name": "Стамбул", "icon": "ПТ", "bg": "#2A1E00", "target": 120000, "saved": 33600, "deadline": "Декабрь 2026"},
            {"id": 3, "name": "Подушка", "icon": "РЗ", "bg": "#0E3A1C", "target": 195000, "saved": 168750, "deadline": "Рекомендуемый резерв"},
        ],
        "bills": [
            {"id": "internet", "name": "Beeline — Интернет", "icon": "ИН", "amount": 499, "due": "Оплачено 21 мар", "status": "paid", "tip": "Автоплатёж активен", "recurring": True, "autopay_enabled": True, "autopay_eligible": True},
            {"id": "electric", "name": "Электроэнергия", "icon": "ЭС", "amount": 1240, "due": "До 25 марта", "status": "due", "tip": "Обычно платёж проходит за 2 дня до срока", "recurring": True, "autopay_enabled": False, "autopay_eligible": True},
            {"id": "gas", "name": "Газ", "icon": "ГЗ", "amount": 890, "due": "До 25 марта", "status": "due", "tip": "Сумма выше обычной на 120 с", "recurring": True, "autopay_enabled": False, "autopay_eligible": True},
            {"id": "kino", "name": "Кинопоиск", "icon": "КН", "amount": 399, "due": "1 апреля", "status": "auto", "tip": "Сервис используется редко. Можно отключить автоплатёж", "recurring": True, "autopay_enabled": True, "autopay_eligible": True, "underused": True},
            {"id": "water", "name": "Вода", "icon": "ВД", "amount": 450, "due": "Просрочено!", "status": "overdue", "tip": "Возможны пени", "recurring": True, "autopay_enabled": False, "autopay_eligible": True},
        ],
        "chat_history": [],
        "gamification": {
            "points": 1450, "level": 3, "level_name": "Финансовый мастер", "streak_days": 7, "streak_best": 12, "discipline_score": 74, "this_month_actions": 9, "autopilot_applied": False,
            "missions": [
                {"id": "autopilot", "icon": "АП", "title": "Применить план месяца", "desc": "Подтверди готовый план после зарплаты", "points": 500, "xp": 200, "completed": False, "progress": 0, "total": 1, "category": "autopilot"},
                {"id": "budget_day", "icon": "📅", "title": "Не превышай бюджет 7 дней", "desc": "Трать не больше 1 627 сом/день", "points": 300, "xp": 150, "completed": False, "progress": 4, "total": 7, "category": "discipline"},
                {"id": "save_goal", "icon": "💻", "title": "Пополняй цель «Ноутбук»", "desc": "Отложи минимум 5 000 сом", "points": 200, "xp": 100, "completed": False, "progress": 0, "total": 5000, "progress_type": "amount", "category": "savings"},
                {"id": "autopay", "icon": "🔁", "title": "Подключи автоплатёж", "desc": "Включи автоплатёж для 2 счетов", "points": 250, "xp": 100, "completed": False, "progress": 1, "total": 2, "category": "autopay"},
                {"id": "tagged_transfer", "icon": "ТГ", "title": "Указывай теги переводов", "desc": "Сделай 3 перевода с тегом назначения", "points": 180, "xp": 90, "completed": False, "progress": 2, "total": 3, "category": "discipline"},
                {"id": "streak_5", "icon": "🔥", "title": "Стрик 10 дней", "desc": "Открывай приложение 10 дней подряд", "points": 400, "xp": 200, "completed": False, "progress": 7, "total": 10, "category": "engagement"},
            ],
            "levels": [
                {"level": 1, "name": "Новичок", "min_points": 0, "icon": "🌱"},
                {"level": 2, "name": "Финансовый старт", "min_points": 500, "icon": "📈"},
                {"level": 3, "name": "Финансовый мастер", "min_points": 1000, "icon": "🏆"},
                {"level": 4, "name": "Финансовый эксперт", "min_points": 2500, "icon": "💎"},
                {"level": 5, "name": "Финансовый гуру", "min_points": 5000, "icon": "🦅"},
            ],
        },
    }

def _connect_state_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    return conn


def save_state() -> None:
    payload = _json.dumps(DB, ensure_ascii=False)
    with _connect_state_db() as conn:
        conn.execute(
            """
            INSERT INTO app_state (key, payload, updated_at)
            VALUES ('main', ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (payload, datetime.now().isoformat(timespec="seconds")),
        )


def load_state() -> dict[str, Any]:
    with _connect_state_db() as conn:
        row = conn.execute("SELECT payload FROM app_state WHERE key = 'main'").fetchone()
        if row:
            try:
                state = _json.loads(row[0])
                if isinstance(state, dict):
                    return state
            except _json.JSONDecodeError:
                pass
    return initial_db()


DB = load_state()

ICON_TEXT_MAP = {
    "👨‍👩‍👧": "СМ",
    "🧾": "ДЛ",
    "🎁": "ПД",
    "✈️": "ПТ",
    "🏠": "КВ",
    "💊": "ЗД",
    "🤝": "СВ",
    "🏦": "НК",
    "💰": "ЗП",
    "🛒": "ПР",
    "🚕": "ТР",
    "☕": "КФ",
    "📲": "ПН",
    "🛍️": "ПР",
    "🎬": "КН",
    "📥": "ПР",
    "🍕": "ЕД",
    "💸": "СП",
    "💻": "НБ",
    "🛡️": "РЗ",
    "📶": "ИН",
    "⚡": "ЭС",
    "🔥": "ГЗ",
    "🚰": "ВД",
    "🔁": "АП",
    "🏷️": "ТГ",
    "📅": "ДН",
    "🌱": "1",
    "📈": "2",
    "🏆": "3",
    "💎": "4",
    "🦾": "5",
    "✅": "OK",
    "⚠️": "ВН",
    "📉": "СР",
    "🧩": "НЗ",
    "🤖": "ПЛ",
    "📋": "СЧ",
    "💚": "ОК",
}

TEXT_REPLACEMENTS = [
    ("FinAI", "MBANK"),
    ("AI Salary Autopilot", "Автоплан"),
    ("Salary Autopilot", "Автоплан"),
    ("AI-план", "план месяца"),
    ("AI-подсказка", "рекомендуемый срок"),
    ("AI-рекомендация", "рекомендуемый срок"),
    ("AI-логике", "логике приложения"),
    ("Risk Radar", "Контроль месяца"),
    ("Smart Offer", "Подходящее предложение"),
    ("Smart Offers", "Подходящие предложения"),
    ("safe-to-spend", "лимит трат"),
    ("Safe to spend", "Лимит трат"),
    ("risk score", "уровень контроля"),
    ("AI dialogue fallback", "Диалог"),
    ("AI dialogue", "Диалог"),
    ("Success state", "План применён"),
]


def sanitize_ui_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sanitize_ui_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_ui_payload(item) for item in value]
    if isinstance(value, str):
        cleaned = value
        for source, target in ICON_TEXT_MAP.items():
            cleaned = cleaned.replace(source, target)
        for source, target in TEXT_REPLACEMENTS:
            cleaned = cleaned.replace(source, target)
        cleaned = EMOJI_RE.sub("", cleaned)
        cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
        return cleaned
    return value


@app.after_request
def sanitize_json_response(response):
    if response.content_type and response.content_type.startswith("application/json"):
        try:
            payload = response.get_json(silent=True)
            if payload is not None:
                response.set_data(_json.dumps(sanitize_ui_payload(payload), ensure_ascii=False))
        except Exception:
            return response
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and response.status_code < 500:
        try:
            save_state()
        except Exception as error:
            app.logger.warning("SQLite state save failed: %s", error)
    return response


def get_account(acc_id: str) -> dict[str, Any] | None:
    return next((a for a in DB["accounts"] if a["id"] == acc_id), None)


def get_contact_by_id(contact_id: int | None) -> dict[str, Any] | None:
    return next((c for c in DB["contacts"] if c["id"] == contact_id), None)


def normalize_phone(phone: str | None) -> str:
    if not phone:
        return ""
    digits = re.sub(r"\D", "", phone)
    if not digits:
        return ""
    if digits.startswith("996"):
        return f"+{digits}"
    if digits.startswith("0"):
        return f"+996{digits[1:]}"
    if digits.startswith("7") and len(digits) == 9:
        return f"+996{digits}"
    if phone.startswith("+"):
        return f"+{digits}"
    return f"+{digits}"


def get_contact_by_phone(phone: str | None) -> dict[str, Any] | None:
    normalized = normalize_phone(phone)
    return next((c for c in DB["contacts"] if normalize_phone(c["phone"]) == normalized), None)


def get_tag(tag_id: str | None) -> dict[str, Any] | None:
    return next((t for t in DB["tags"] if t["id"] == tag_id), None)


def default_bill_tag(bill_id: str) -> str:
    if bill_id in {"electric", "gas", "water", "internet"}:
        return "service"
    if bill_id == "kino":
        return "gift"
    return "service"


def is_sensitive_request(message: str) -> bool:
    lowered = message.lower()
    risky_patterns = [
        "pin",
        "cvv",
        "cvc",
        "парол",
        "код подтверждения",
        "смс код",
        "otp",
        "секрет",
        "токен",
        "закрой счет",
        "удали историю",
        "обойди",
        "обход",
        "взлом",
        "скрой перевод",
        "поддел",
        "фальш",
        "переведи все деньги",
        "отправь все деньги",
    ]
    return any(pattern in lowered for pattern in risky_patterns)


def safety_refusal() -> str:
    return (
        f"{ASSISTANT_NAME} не выполняет опасные или чувствительные запросы. "
        "Я не раскрываю секреты карты и доступа, не отключаю защиту и не делаю действия без явного безопасного подтверждения. "
        "Могу помочь только с разрешёнными банковыми функциями внутри приложения."
    )


def total_balance() -> int:
    return sum(a["balance"] for a in DB["accounts"])


def days_left_in_cycle() -> int:
    today = datetime.now().day
    return max(1, 30 - today + 1)


def now_label() -> str:
    return f"Только что, {datetime.now().strftime('%H:%M')}"


def create_transaction(
    *,
    name: str,
    category: str,
    amount: int,
    direction: str,
    account_id: str = "main",
    icon: str = "СП",
    bg: str = "#0A2040",
    tag: str | None = None,
    kind: str = "manual",
    phone: str | None = None,
) -> dict[str, Any]:
    transaction = {
        "id": len(DB["transactions"]) + 1,
        "name": name,
        "category": category,
        "amount": amount,
        "icon": icon,
        "bg": bg,
        "date": now_label(),
        "dir": direction,
        "account": account_id,
        "tag": tag,
        "kind": kind,
    }
    if phone:
        transaction["phone"] = normalize_phone(phone)
    DB["transactions"].insert(0, transaction)
    return transaction


def parse_positive_int(value: Any, field_name: str) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{field_name} должно быть числом")
    if number <= 0:
        raise ValueError(f"{field_name} должно быть больше 0")
    return number


def spending_by_category() -> dict[str, int]:
    categories: dict[str, int] = {}
    for tx in DB["transactions"]:
        if tx["dir"] != "out":
            continue
        categories[tx["category"]] = categories.get(tx["category"], 0) + tx["amount"]
    return categories


def merchant_spending_by_category() -> dict[str, int]:
    categories: dict[str, int] = {}
    for tx in DB["transactions"]:
        if tx["dir"] != "out" or tx["category"] == "transfer":
            continue
        categories[tx["category"]] = categories.get(tx["category"], 0) + tx["amount"]
    return categories


def transfer_tag_analytics() -> dict[str, Any]:
    buckets: dict[str, dict[str, Any]] = {}
    total_tagged_amount = 0
    total_tagged_count = 0
    for tx in DB["transactions"]:
        if tx["dir"] != "out" or not tx.get("tag"):
            continue
        tag = get_tag(tx["tag"])
        if not tag:
            continue
        bucket = buckets.setdefault(
            tag["id"],
            {
                "id": tag["id"],
                "label": tag["label"],
                "icon": tag["icon"],
                "color": tag["color"],
                "amount": 0,
                "count": 0,
            },
        )
        bucket["amount"] += tx["amount"]
        bucket["count"] += 1
        total_tagged_amount += tx["amount"]
        total_tagged_count += 1
    tags = sorted(buckets.values(), key=lambda item: item["amount"], reverse=True)
    for tag in tags:
        tag["share"] = round((tag["amount"] / max(total_tagged_amount, 1)) * 100)
    top_tag = tags[0] if tags else None
    insight = "Теги пока не влияют на выводы — добавь их в переводы."
    if top_tag:
        if top_tag["id"] == "debt":
            insight = "Переводы по тегу «Долг» заметно давят на денежный поток."
        elif top_tag["id"] == "family":
            insight = "Поддержка семьи — главный паттерн переводов в этом месяце."
        elif top_tag["id"] == "shared":
            insight = "Совместные расходы хорошо подходят для сплит-логики и контроля лимитов."
        elif top_tag["id"] == "travel":
            insight = "Переводы на поездки можно быстро конвертировать в накопительную цель."
        elif top_tag["id"] == "food":
            insight = "Траты с тегом «Еда» уже заметны. Это хороший кандидат на отдельный недельный лимит."
        elif top_tag["id"] == "taxi":
            insight = "Такси стало ощутимой статьёй расходов. Аналитика советует следить за частотой поездок."
        elif top_tag["id"] == "service":
            insight = "Платежи за услуги влияют на свободный остаток. Их лучше держать в отдельной категории."
    return {
        "tags": tags,
        "top_tag": top_tag,
        "total_tagged_amount": total_tagged_amount,
        "total_tagged_count": total_tagged_count,
        "concentration": top_tag["share"] if top_tag else 0,
        "insight": insight,
    }


def get_level_info(points: int) -> tuple[dict[str, Any], dict[str, Any] | None, int]:
    levels = DB["gamification"]["levels"]
    current = levels[0]
    next_level = None
    for idx, level in enumerate(levels):
        if points >= level["min_points"]:
            current = level
            next_level = levels[idx + 1] if idx + 1 < len(levels) else None
    if next_level:
        in_level = points - current["min_points"]
        span = next_level["min_points"] - current["min_points"]
        progress = round((in_level / max(span, 1)) * 100)
    else:
        progress = 100
    return current, next_level, progress


def _award_points(points: int, reason: str = "") -> int:
    gamification = DB["gamification"]
    gamification["points"] += points
    current, _, _ = get_level_info(gamification["points"])
    gamification["level"] = current["level"]
    gamification["level_name"] = current["name"]
    gamification["this_month_actions"] += 1
    return gamification["points"]


def get_mission(mission_id: str) -> dict[str, Any] | None:
    return next((m for m in DB["gamification"]["missions"] if m["id"] == mission_id), None)


def update_mission_progress(mission_id: str, *, delta: int = 0, absolute: int | None = None) -> None:
    mission = get_mission(mission_id)
    if not mission or mission["completed"]:
        return
    if absolute is not None:
        mission["progress"] = absolute
    else:
        mission["progress"] = min(mission["progress"] + delta, mission["total"])
    if mission["progress"] >= mission["total"]:
        mission["completed"] = True
        _award_points(mission["points"], f"Mission completed: {mission['title']}")


def refresh_scores() -> None:
    due_count = sum(1 for bill in DB["bills"] if bill["status"] in ("due", "overdue"))
    autopay_enabled = sum(1 for bill in DB["bills"] if bill.get("autopay_enabled"))
    tagged = transfer_tag_analytics()
    savings_ratio = round((get_account("save")["balance"] / max(total_balance(), 1)) * 100)
    score = 56
    if DB["autopilot"]["applied"]:
        score += 8
    score += autopay_enabled * 5
    score += 6 if tagged["total_tagged_count"] >= 3 else 2
    score += 6 if savings_ratio >= 60 else 2
    score -= due_count * 7
    score = max(42, min(score, 96))
    DB["gamification"]["discipline_score"] = score
    DB["user"]["health_score"] = max(55, min(97, score + 4))


def compute_safe_to_spend() -> dict[str, Any]:
    main_balance = get_account("main")["balance"]
    due_bills = [bill for bill in DB["bills"] if bill["status"] in ("due", "overdue")]
    bills_total = sum(bill["amount"] for bill in due_bills)
    reserve_floor = 5000
    safe_amount = max(0, main_balance - bills_total - reserve_floor)
    days_left = days_left_in_cycle()
    daily_safe = round(safe_amount / max(days_left, 1))
    return {
        "safe_to_spend": safe_amount,
        "days_left": days_left,
        "daily_safe": daily_safe,
        "bills_pending": bills_total,
        "overdue_count": sum(1 for bill in due_bills if bill["status"] == "overdue"),
        "reserve_floor": reserve_floor,
    }


def compute_risk_radar() -> dict[str, Any]:
    safe = compute_safe_to_spend()
    categories = merchant_spending_by_category()
    tags = transfer_tag_analytics()
    restaurants = categories.get("restaurants", 0)
    entertainment = categories.get("entertainment", 0)
    fun_spend = restaurants + entertainment
    projected_cash_gap = max(0, safe["bills_pending"] + fun_spend + 5000 - get_account("main")["balance"])
    recurring_manual = [bill for bill in DB["bills"] if bill.get("recurring") and not bill.get("autopay_enabled")]
    items: list[dict[str, Any]] = []
    if projected_cash_gap > 0 or safe["safe_to_spend"] < 6000:
        items.append(
            {
                "id": "cash_gap",
                "severity": "high",
                "title": "Риск кассового разрыва",
                "desc": f"До конца месяца запас всего {safe['safe_to_spend']:,} с. Под рукой нужен резерв.",
                "cta_label": "Посмотреть M+",
                "cta_action": "offer:reserve",
            }
        )
    if safe["overdue_count"] > 0:
        items.append(
            {
                "id": "overdue",
                "severity": "high",
                "title": "Есть просроченный платёж",
                "desc": "Оплати воду сейчас, чтобы избежать пеней и просадки health score.",
                "cta_label": "Оплатить воду",
                "cta_action": "bill:water",
            }
        )
    if fun_spend >= 1400:
        items.append(
            {
                "id": "spike",
                "severity": "medium",
                "title": "Скачок необязательных трат",
                "desc": f"Кафе и развлечения уже заняли {fun_spend:,} с. Это главный источник просадки бюджета.",
                "cta_label": "Ограничить бюджет",
                "cta_action": "autopilot",
            }
        )
    if tags["top_tag"] and tags["top_tag"]["amount"] >= 1800:
        items.append(
            {
                "id": "tag_pressure",
                "severity": "medium",
                "title": f"Тег «{tags['top_tag']['label']}» давит на кэшфлоу",
                "desc": f"{tags['top_tag']['amount']:,} с уже ушло в эту цель. Это учитывается в аналитике и продуктовых сценариях.",
                "cta_label": "Смотреть аналитику",
                "cta_action": "analytics",
            }
        )
    underused = next((bill for bill in DB["bills"] if bill.get("underused")), None)
    if underused:
        items.append(
            {
                "id": "subscription",
                "severity": "low",
                "title": "Подписка с низкой полезностью",
                "desc": f"{underused['name']} включён, но сервис редко используется.",
                "cta_label": "Оставить пока",
                "cta_action": "none",
            }
        )
    score = 92
    score -= len([item for item in items if item["severity"] == "high"]) * 18
    score -= len([item for item in items if item["severity"] == "medium"]) * 9
    score -= len(recurring_manual) * 4
    score = max(44, min(score, 96))
    summary = "Ситуация контролируема, но есть сигналы для автоплатежей и резерва."
    if score >= 80:
        summary = "Радар зелёный. Главная задача — закрепить автоплатежи и накопления."
    elif score < 60:
        summary = "Радар жёлтый. Лучше включить резерв и закрыть обязательства одним действием."
    return {
        "score": score,
        "summary": summary,
        "items": items,
        "cash_gap_amount": projected_cash_gap,
        "manual_recurring_count": len(recurring_manual),
        "fun_spend": fun_spend,
        "tag_pressure": tags["top_tag"],
        "safe_to_spend": safe,
    }


def compute_smart_offers() -> list[dict[str, Any]]:
    risk = compute_risk_radar()
    safe = risk["safe_to_spend"]
    offers: list[dict[str, Any]] = []
    if risk["cash_gap_amount"] > 0 or safe["safe_to_spend"] < 6000:
        offers.append(
            {
                "id": "reserve",
                "priority": 100,
                "type": "liquidity",
                "title": "M+ резерв под риск месяца",
                "desc": f"Предодобрен лимит {DB['products']['m_plus']['preapproved_limit']:,} с. Предложение появилось, потому что есть риск кассового разрыва.",
                "benefit": "Сохраняет платёжную дисциплину без ручного поиска денег.",
                "cta_label": "Активировать лимит",
                "action": "activate_reserve",
            }
        )
    if risk["manual_recurring_count"] > 0:
        offers.append(
            {
                "id": "autopay",
                "priority": 90,
                "type": "retention",
                "title": "Подключить автоплатёж для регулярных счетов",
                "desc": f"{risk['manual_recurring_count']} счёта ещё не поставлены на автоплатёж.",
                "benefit": "Меньше просрочек и выше возврат в приложение.",
                "cta_label": "Включить автоплатёж",
                "action": "enable_autopay",
            }
        )
    if DB["gamification"]["discipline_score"] >= 72 and get_account("main")["balance"] >= 10000:
        offers.append(
            {
                "id": "savings_boost",
                "priority": 70,
                "type": "savings",
                "title": "Усилить накопления внутри банка",
                "desc": "По текущей дисциплине можно безопасно добавить ещё 3 000 с в накопления.",
                "benefit": "Ускоряет цель и удерживает деньги внутри экосистемы банка.",
                "cta_label": "Перевести 3 000 с",
                "action": "boost_savings",
            }
        )
    tags = transfer_tag_analytics()
    if tags["top_tag"] and tags["top_tag"]["id"] == "travel":
        offers.append(
            {
                "id": "travel_goal",
                "priority": 55,
                "type": "goal",
                "title": "Оформить отдельную цель под поездку",
                "desc": "Тег «Поездка» уже проявился в переводах. Логично конвертировать это в цель.",
                "benefit": "Следующий план месяца сможет учитывать поездку как отдельную цель.",
                "cta_label": "Создать цель",
                "action": "focus_travel_goal",
            }
        )
    offers.sort(key=lambda item: item["priority"], reverse=True)
    return offers[:3]


def compute_next_best_action() -> dict[str, Any]:
    risk = compute_risk_radar()
    offers = compute_smart_offers()
    if not DB["autopilot"]["applied"]:
        return {
            "type": "autopilot",
            "tag": "План месяца",
            "title": "Применить автоплан",
            "desc": "Один тап, чтобы закрыть обязательства, включить автоплатёж и выделить накопления.",
            "cta": "Открыть план",
            "screen": "screen-autopilot",
        }
    if risk["items"]:
        top_item = risk["items"][0]
        return {
            "type": "risk",
            "tag": "Контроль месяца",
            "title": top_item["title"],
            "desc": top_item["desc"],
            "cta": top_item["cta_label"],
            "action": top_item["cta_action"],
        }
    if offers:
        offer = offers[0]
        return {
            "type": "offer",
            "tag": "Подходящее предложение",
            "title": offer["title"],
            "desc": offer["desc"],
            "cta": offer["cta_label"],
            "offer_id": offer["id"],
        }
    return {
        "type": "discipline",
        "tag": "Фокус месяца",
        "title": "Держать дневной лимит без просадки",
        "desc": "Красных флагов сейчас нет. Лучший следующий шаг — удержать темп и закрыть миссии.",
        "cta": "Открыть миссии",
        "screen": "screen-missions",
    }


def build_notifications() -> list[dict[str, Any]]:
    risk = compute_risk_radar()
    offers = compute_smart_offers()
    notifications = [
        {
            "id": 1,
            "icon": "💰",
            "title": "Зарплата получена",
            "body": f"{DB['autopilot']['last_salary_amount']:,} с уже на основном счёте",
            "time": "2 ч назад",
            "type": "income",
            "read": False,
        }
    ]
    if risk["items"]:
        top = risk["items"][0]
        notifications.append(
            {
                "id": 2,
                "icon": "⚠️",
                "title": top["title"],
                "body": top["desc"],
                "time": "1 ч назад",
                "type": "warning",
                "read": False,
            }
        )
    if offers:
        offer = offers[0]
        notifications.append(
            {
                "id": 3,
                "icon": "🏦",
                "title": offer["title"],
                "body": offer["benefit"],
                "time": "Сегодня",
                "type": "offer",
                "read": True,
            }
        )
    notifications.append(
        {
            "id": 4,
            "icon": "🏷️",
            "title": "Теги влияют на аналитику",
            "body": transfer_tag_analytics()["insight"],
            "time": "Сегодня",
            "type": "analytics",
            "read": True,
        }
    )
    notifications.append(
        {
            "id": 5,
            "icon": "🔥",
            "title": f"Стрик {DB['gamification']['streak_days']} дней",
            "body": "Ещё один день — и дисциплина поднимется выше 80/100.",
            "time": "Сегодня",
            "type": "streak",
            "read": False,
        }
    )
    return notifications


def compute_salary_plan(salary: int | None = None) -> dict[str, Any]:
    safe = compute_safe_to_spend()
    risk = compute_risk_radar()
    offers = compute_smart_offers()
    salary_amount = salary or DB["autopilot"]["last_salary_amount"]
    due_bills = [bill for bill in DB["bills"] if bill["status"] in ("due", "overdue")]
    bills_total = sum(bill["amount"] for bill in due_bills)
    savings_pct = 0.20 if risk["cash_gap_amount"] == 0 else 0.12
    savings_amount = round(salary_amount * savings_pct)
    free_after = salary_amount - bills_total - savings_amount
    days_left = max(1, days_left_in_cycle())
    daily_budget = max(0, round(free_after / days_left))
    reserve_offer = next((offer for offer in offers if offer["id"] == "reserve"), None)
    recurring_manual = [bill for bill in DB["bills"] if bill.get("recurring") and not bill.get("autopay_enabled")]
    return {
        "salary": salary_amount,
        "salary_date": DB["autopilot"]["last_salary_date"],
        "bills_total": bills_total,
        "savings_amount": savings_amount,
        "daily_budget": daily_budget,
        "free": free_after,
        "days_left": days_left,
        "safe_to_spend": safe["safe_to_spend"],
        "risk_warning": risk["items"][0] if risk["items"] else None,
        "reserve_offer": reserve_offer,
        "autopay_targets": [bill["name"] for bill in recurring_manual],
        "breakdown": [
            {"label": "Обязательные счета", "amount": bills_total, "icon": "📋", "tone": "warning"},
            {"label": "Накопления", "amount": savings_amount, "icon": "🏦", "tone": "positive"},
            {"label": "Дневной лимит", "amount": daily_budget, "icon": "📅", "tone": "neutral"},
            {"label": "Свободный остаток", "amount": free_after, "icon": "💚", "tone": "positive"},
        ],
        "actions": [
            {"label": "Закрыть срочные счета", "value": f"{len(due_bills)} шт.", "done": len(due_bills) == 0},
            {"label": "Отложить в накопления", "value": f"{savings_amount:,} с", "done": False},
            {"label": "Включить автоплатёж", "value": f"{len(recurring_manual)} сч.", "done": len(recurring_manual) == 0},
            {"label": "Зафиксировать safe-to-spend", "value": f"{daily_budget:,} с/день", "done": False},
        ],
    }


def serialize_offer_outcome(offer_id: str, points: int, message: str) -> dict[str, Any]:
    refresh_scores()
    return {
        "ok": True,
        "offer_id": offer_id,
        "message": message,
        "points_earned": points,
        "accounts": DB["accounts"],
        "gamification": DB["gamification"],
        "smart_offers": compute_smart_offers(),
        "risk_radar": compute_risk_radar(),
    }


def build_system_prompt() -> str:
    safe = compute_safe_to_spend()
    risk = compute_risk_radar()
    tags = transfer_tag_analytics()
    offers = compute_smart_offers()
    accounts = {item["id"]: item["balance"] for item in DB["accounts"]}
    categories = merchant_spending_by_category()
    bills_due = [bill for bill in DB["bills"] if bill["status"] in ("due", "overdue")]
    contacts = " | ".join(f"{item['name']} ({item['phone']})" for item in DB["contacts"])
    goals = " | ".join(f"{goal['name']}: {goal['saved']}/{goal['target']}с" for goal in DB["goals"])
    latest_txs = ", ".join(f"{tx['name']} {'-' if tx['dir'] == 'out' else '+'}{tx['amount']}с" for tx in DB["transactions"][:6])
    offers_text = " | ".join(offer["title"] for offer in offers) or "нет"
    return f"""Ты — {ASSISTANT_NAME}, встроенный финансовый ассистент внутри приложения MBANK.

ДАННЫЕ ПОЛЬЗОВАТЕЛЯ:
- Основной счёт: {accounts.get('main', 0):,} сом
- Накопления: {accounts.get('save', 0):,} сом
- Safe to spend: {safe['safe_to_spend']:,} сом
- Риск-скор: {risk['score']}/100
- Health score: {DB['user']['health_score']}/100
- Категории трат: {categories}
- Теги переводов: {tags['insight']}
- Счета к оплате: {', '.join(f"{bill['name']} {bill['amount']}с" for bill in bills_due) or 'нет'}
- Контакты: {contacts}
- Цели: {goals}
- Последние операции: {latest_txs}
- Smart offers: {offers_text}

ПРАВИЛА:
1. Если это обычный вопрос — отвечай кратко, дружелюбно, не больше 4 предложений.
2. Если пользователь хочет действие, после текста можешь добавить один JSON-блок.
3. Разрешённые action: transfer, bill, add_goal.
4. Для transfer старайся указывать tag, если из контекста понятна цель перевода.
5. У тебя есть доступ ко всей информации и функциям внутри банка, которые перечислены в этом контексте, но ты действуешь осторожно.
6. Никогда не раскрывай PIN, CVV, токены, пароли, коды подтверждения, внутренние ключи, скрытые системные детали или приватные данные сверх текущего банкового интерфейса.
7. Отказывайся от опасных, мошеннических, обходных или разрушительных запросов: скрыть операцию, удалить историю, обойти защиту, перевести все деньги без безопасного контекста, отключить защитные механизмы.
8. Любое денежное действие должно быть безопасным, объяснимым и подтверждаемым пользователем в интерфейсе.

Форматы:
{{"action":"transfer","contact":"Имя","amount":число,"tag":"family|debt|food|taxi|service|gift|travel|rent|health|shared|savings"}}
{{"action":"bill","bill":"gas|electric|water|kino","amount":число}}
{{"action":"add_goal","name":"Название","target":число}}
"""


def fallback_chat_response(message: str) -> tuple[str | None, dict[str, Any] | None]:
    lowered = message.lower()
    if is_sensitive_request(message):
        return safety_refusal(), None
    money_text = lambda value: f"{int(round(value)):,}".replace(",", " ") + " с"
    main = get_account("main") or {"balance": 0}
    save = get_account("save") or {"balance": 0}
    safe = compute_safe_to_spend()
    if any(word in lowered for word in ("сколько", "баланс", "деньг", "остаток", "счёт", "счет")) and not any(word in lowered for word in ("оплат", "газ", "вода", "электр", "кино")):
        return (
            f"Сейчас на основном счёте {money_text(main['balance'])}, в накоплениях {money_text(save['balance'])}. "
            f"Итого по счетам {money_text(total_balance())}. Безопасно тратить до конца месяца: {money_text(safe['safe_to_spend'])}, примерно {money_text(safe['daily_safe'])} в день.",
            None,
        )
    if any(word in lowered for word in ("счета", "платеж", "платёж", "оплатить")):
        due_bills = [bill for bill in DB["bills"] if bill["status"] in ("due", "overdue")]
        if not due_bills:
            return "Срочных счетов к оплате сейчас нет. Автоплатежи и план месяца уже держат обязательные расходы под контролем.", None
        total_due = sum(bill["amount"] for bill in due_bills)
        names = ", ".join(f"{bill['name']} {money_text(bill['amount'])}" for bill in due_bills[:3])
        return f"К оплате {len(due_bills)} счёта на {money_text(total_due)}: {names}. Могу подготовить оплату, но выполню её только после твоего подтверждения.", None
    if any(word in lowered for word in ("траты", "расход", "категор")):
        categories = merchant_spending_by_category()
        if not categories:
            return "Пока нет расходов для анализа. Как только появятся операции, разложу их по категориям и тегам.", None
        top_name, top_amount = max(categories.items(), key=lambda item: item[1])
        return f"Главная категория расходов сейчас: {top_name} — {money_text(top_amount)}. Я бы держал её под недельным лимитом и помечал переводы тегами, чтобы прогноз был точнее.", None
    if any(word in lowered for word in ("цели", "цель", "накопления", "коплю")):
        goals = DB["goals"]
        if goals:
            top_goal = max(goals, key=lambda goal: goal["target"] - goal["saved"])
            left = max(top_goal["target"] - top_goal["saved"], 0)
            return f"Главная цель: {top_goal['name']}. Накоплено {money_text(top_goal['saved'])} из {money_text(top_goal['target'])}, осталось {money_text(left)}. Могу предложить безопасное пополнение из свободного остатка.", None
        return "Целей пока нет. Могу создать новую цель и встроить её в план месяца после подтверждения.", {"action": "add_goal", "name": "Новая цель", "target": 30000}
    if any(word in lowered for word in ("автоплан", "план месяца", "зарплат")):
        return "Могу применить план месяца: закрыть срочные счета, включить автоплатежи и отложить часть зарплаты. Покажу подтверждение перед действием.", {"action": "apply_plan"}
    if "автоплат" in lowered:
        return "Могу включить автоплатежи для регулярных счетов. Это снизит риск просрочек.", {"action": "offer", "offer_id": "autopay"}
    if "резерв" in lowered or "лимит" in lowered:
        return "Могу активировать M+ резерв как страховку на случай кассового разрыва. Сначала нужно подтверждение.", {"action": "offer", "offer_id": "reserve"}
    if "отмет" in lowered or "стрик" in lowered:
        return "Могу отметить сегодняшний день и обновить серию финансовой дисциплины.", {"action": "streak_checkin"}
    if "перев" in lowered:
        amount_match = re.search(r"(\d{3,6})", lowered)
        contact = next((item for item in DB["contacts"] if item["name"].split()[0].lower() in lowered), None)
        if amount_match and contact:
            return (
                "Подготовил перевод. Проверь сумму и тег перед подтверждением.",
                {"action": "transfer", "contact": contact["name"], "amount": int(amount_match.group(1)), "tag": contact.get("default_tag", "shared")},
            )
    if "газ" in lowered:
        return "Газ можно оплатить сразу, это снимет один риск из радара.", {"action": "bill", "bill": "gas", "amount": 890}
    offers = compute_smart_offers()
    if offers:
        return f"Сейчас лучший шаг — {offers[0]['title'].lower()}. {offers[0]['benefit']}", None
    risk = compute_risk_radar()
    return f"Сейчас у тебя уровень контроля {risk['score']}/100. Если хочешь, помогу разобрать траты, цели или переводы по тегам.", None


def parse_action_from_reply(reply: str) -> tuple[str | None, dict[str, Any] | None]:
    action_result = None
    clean_reply = reply
    try:
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", reply, re.DOTALL)
        json_text = json_match.group(1) if json_match else None
        if not json_text:
            json_match = re.search(r"\{.*?\}", reply, re.DOTALL)
            json_text = json_match.group(0) if json_match else None
        if json_match:
            parsed = _json.loads(json_text)
            if isinstance(parsed, dict) and parsed.get("action") in ALLOWED_AI_ACTIONS:
                action_result = parsed
                clean_reply = (reply[: json_match.start()] + reply[json_match.end() :]).strip()
                clean_reply = clean_reply.replace("```json", "").replace("```", "").strip() or None
    except Exception:
        action_result = None
    return clean_reply, action_result


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/dashboard")
def api_dashboard():
    refresh_scores()
    safe = compute_safe_to_spend()
    risk = compute_risk_radar()
    return jsonify(
        {
            "user": DB["user"],
            "accounts": DB["accounts"],
            "autopilot": DB["autopilot"],
            "total_balance": total_balance(),
            "transactions": DB["transactions"][:6],
            "spending_by_category": merchant_spending_by_category(),
            "total_spent": sum(merchant_spending_by_category().values()),
            "health_score": DB["user"]["health_score"],
            "goals_count": len(DB["goals"]),
            "bills_due": sum(1 for bill in DB["bills"] if bill["status"] in ("due", "overdue")),
            "gamification": DB["gamification"],
            "safe_to_spend": safe,
            "risk_summary": {"score": risk["score"], "summary": risk["summary"], "items_count": len(risk["items"])},
            "smart_offers": compute_smart_offers(),
            "next_best_action": compute_next_best_action(),
            "tag_analytics": transfer_tag_analytics(),
        }
    )


@app.route("/api/transactions")
def api_transactions():
    category = request.args.get("category", "all")
    tag = request.args.get("tag", "all")
    txs = DB["transactions"]
    if category != "all":
        txs = [tx for tx in txs if tx["category"] == category]
    if tag != "all":
        txs = [tx for tx in txs if tx.get("tag") == tag]
    return jsonify({"transactions": txs, "total": len(txs)})


@app.route("/api/tags")
def api_tags():
    return jsonify({"tags": DB["tags"]})


@app.route("/api/tag-analytics")
def api_tag_analytics():
    return jsonify(transfer_tag_analytics())


@app.route("/api/transfer", methods=["POST"])
def api_transfer():
    data = request.get_json(silent=True) or {}
    try:
        amount = parse_positive_int(data.get("amount"), "Сумма")
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    account = get_account(data.get("account_id", "main"))
    if not account:
        return jsonify({"ok": False, "error": "Счёт не найден"}), 404
    if amount > account["balance"]:
        return jsonify({"ok": False, "error": f"Недостаточно средств. Баланс: {account['balance']:,} с"}), 400
    contact = get_contact_by_id(data.get("contact_id")) or get_contact_by_phone(data.get("phone"))
    if not contact:
        return jsonify({"ok": False, "error": "Контакт по этому номеру не найден"}), 404
    explicit_tag = data.get("tag")
    tag_id = explicit_tag or contact.get("default_tag")
    if data.get("phone") and not explicit_tag:
        return jsonify({"ok": False, "error": "Укажи тег перевода"}), 400
    if tag_id and not get_tag(tag_id):
        return jsonify({"ok": False, "error": "Неизвестный тег"}), 400
    account["balance"] -= amount
    transaction = create_transaction(
        name=f"→ {contact['name'].split()[0]}",
        category="transfer",
        amount=amount,
        direction="out",
        account_id=data.get("account_id", "main"),
        icon="ПН",
        bg="#0A2040",
        tag=tag_id,
        kind="phone_transfer" if data.get("phone") else "transfer",
        phone=contact["phone"],
    )
    update_mission_progress("tagged_transfer", delta=1 if tag_id else 0)
    points = 50 if tag_id else 35
    _award_points(points, "Tagged transfer" if tag_id else "Transfer")
    refresh_scores()
    return jsonify(
        {
            "ok": True,
            "new_balance": account["balance"],
            "transaction": transaction,
            "message": f"Перевёл {amount:,} с → {contact['name']}",
            "points_earned": points,
            "tag": get_tag(tag_id),
            "tag_analytics": transfer_tag_analytics(),
            "risk_radar": compute_risk_radar(),
        }
    )


@app.route("/api/pay-bill", methods=["POST"])
def api_pay_bill():
    data = request.get_json(silent=True) or {}
    bill = next((item for item in DB["bills"] if item["id"] == data.get("bill_id")), None)
    if not bill:
        return jsonify({"ok": False, "error": "Счёт не найден"}), 404
    if bill["status"] == "paid":
        return jsonify({"ok": False, "error": "Уже оплачено"}), 400
    account = get_account(data.get("account_id", "main"))
    if not account:
        return jsonify({"ok": False, "error": "Счёт не найден"}), 404
    if bill["amount"] > account["balance"]:
        return jsonify({"ok": False, "error": f"Недостаточно средств. Нужно {bill['amount']:,} с"}), 400
    tag_id = data.get("tag") or default_bill_tag(bill["id"])
    if tag_id and not get_tag(tag_id):
        return jsonify({"ok": False, "error": "Неизвестный тег"}), 400
    account["balance"] -= bill["amount"]
    bill["status"] = "paid"
    bill["due"] = f"Оплачено {datetime.now().strftime('%d.%m')}"
    create_transaction(
        name=bill["name"],
        category="bills",
        amount=bill["amount"],
        direction="out",
        account_id=data.get("account_id", "main"),
        icon=bill["icon"],
        bg="#0E3A1C",
        tag=tag_id,
        kind="bill_payment",
    )
    _award_points(75, "Bill paid")
    refresh_scores()
    return jsonify({"ok": True, "new_balance": account["balance"], "message": f"{bill['name']} оплачен — {bill['amount']:,} с", "points_earned": 75, "tag": get_tag(tag_id), "tag_analytics": transfer_tag_analytics(), "risk_radar": compute_risk_radar()})


@app.route("/api/bills")
def api_bills():
    due_count = sum(1 for bill in DB["bills"] if bill["status"] in ("due", "overdue"))
    total_due = sum(bill["amount"] for bill in DB["bills"] if bill["status"] in ("due", "overdue"))
    return jsonify({"bills": DB["bills"], "due_count": due_count, "total_due": total_due})


@app.route("/api/goals")
def api_goals():
    return jsonify({"goals": DB["goals"]})


@app.route("/api/goals/add", methods=["POST"])
def api_add_goal():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "Новая цель").strip()
    try:
        target = parse_positive_int(data.get("target", 10000), "Сумма цели")
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    icons = {"iphone": "ТЛ", "ноутбук": "НБ", "машин": "АВ", "отпуск": "ПТ", "путеш": "ПТ", "телефон": "ТЛ"}
    lowered = name.lower()
    icon = next((emoji for key, emoji in icons.items() if key in lowered), "ЦЛ")
    goal = {"id": len(DB["goals"]) + 1, "name": name, "icon": icon, "bg": "#0A2040", "target": target, "saved": 0, "deadline": "Рекомендуемый срок"}
    DB["goals"].append(goal)
    _award_points(100, "New goal")
    refresh_scores()
    return jsonify({"ok": True, "goal": goal, "points_earned": 100})


@app.route("/api/goals/<int:goal_id>/deposit", methods=["POST"])
def api_deposit_goal(goal_id: int):
    data = request.get_json(silent=True) or {}
    try:
        amount = parse_positive_int(data.get("amount"), "Сумма пополнения")
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    goal = next((item for item in DB["goals"] if item["id"] == goal_id), None)
    if not goal:
        return jsonify({"ok": False, "error": "Цель не найдена"}), 404
    account = get_account("main")
    if amount > account["balance"]:
        return jsonify({"ok": False, "error": "Недостаточно средств"}), 400
    account["balance"] -= amount
    goal["saved"] += amount
    get_account("save")["balance"] += amount
    update_mission_progress("save_goal", delta=amount)
    _award_points(50, "Goal deposit")
    create_transaction(name=f"В цель «{goal['name']}»", category="savings", amount=amount, direction="out", account_id="main", icon=goal["icon"], bg="#0E3A1C", tag="savings", kind="goal_deposit")
    refresh_scores()
    return jsonify({"ok": True, "goal": goal, "new_balance": account["balance"], "points_earned": 50})


@app.route("/api/insights")
def api_insights():
    categories = merchant_spending_by_category()
    total_spent = sum(categories.values())
    main_balance = get_account("main")["balance"]
    daily_avg = round(total_spent / max(22, 1))
    days_until_empty = round(main_balance / max(daily_avg, 1))
    return jsonify(
        {
            "health_score": DB["user"]["health_score"],
            "personality": DB["user"]["personality"],
            "spending_by_category": categories,
            "total_spent": total_spent,
            "daily_avg": daily_avg,
            "days_until_empty": days_until_empty,
            "prediction": f"При текущих тратах деньги закончатся через ~{days_until_empty} дней",
            "tips": [
                "Тегированный перевод помогает точнее оценивать риск кассового разрыва.",
                "Автопилот закрывает счета и включает автоплатежи в один шаг.",
                transfer_tag_analytics()["insight"],
            ],
        }
    )


@app.route("/api/contacts")
def api_contacts():
    return jsonify({"contacts": DB["contacts"]})


@app.route("/api/notifications")
def api_notifications():
    return jsonify({"notifications": build_notifications()})


@app.route("/api/rates")
def api_rates():
    return jsonify({"rates": [{"code": "USD", "buy": 87.30, "sell": 88.10, "flag": "🇺🇸"}, {"code": "EUR", "buy": 94.50, "sell": 95.80, "flag": "🇪🇺"}, {"code": "RUB", "buy": 0.96, "sell": 1.02, "flag": "🇷🇺"}, {"code": "KZT", "buy": 0.185, "sell": 0.195, "flag": "🇰🇿"}], "updated": datetime.now().strftime("%d.%m.%Y %H:%M")})


@app.route("/api/ai-status")
def api_ai_status():
    online = bool(GROQ_API_KEY)
    return jsonify(
        {
            "enabled": online,
            "mode": "online" if online else "local",
            "model": ASSISTANT_NAME,
            "message": f"{ASSISTANT_NAME} онлайн" if online else f"{ASSISTANT_NAME} работает в локальном режиме",
        }
    )


@app.route("/api/safe-to-spend")
def api_safe_to_spend():
    return jsonify(compute_safe_to_spend())


@app.route("/api/autopilot-status")
def api_autopilot_status():
    salary_tx = next((tx for tx in DB["transactions"] if tx["kind"] == "salary"), None)
    due_bills = [bill for bill in DB["bills"] if bill["status"] in ("due", "overdue")]
    bills_total = sum(bill["amount"] for bill in due_bills)
    return jsonify({"salary_detected": salary_tx is not None, "salary_amount": salary_tx["amount"] if salary_tx else 0, "salary_date": salary_tx["date"] if salary_tx else "", "bills_due_count": len(due_bills), "bills_total": bills_total, "savings_recommended": round(DB["autopilot"]["last_salary_amount"] * 0.20), "plan_ready": not DB["autopilot"]["applied"], "cycle": DB["autopilot"]["cycle"]})


@app.route("/api/salary-plan", methods=["POST"])
def api_salary_plan():
    data = request.get_json(silent=True) or {}
    try:
        salary = parse_positive_int(data.get("salary", DB["autopilot"]["last_salary_amount"]), "Зарплата")
    except ValueError as error:
        return jsonify({"ok": False, "error": str(error)}), 400
    return jsonify({"ok": True, "plan": compute_salary_plan(salary)})


@app.route("/api/salary-plan/apply", methods=["POST"])
def api_apply_salary_plan():
    if DB["autopilot"]["applied"]:
        return jsonify({"ok": False, "error": "План уже применён для текущего цикла"}), 400
    plan = compute_salary_plan()
    account = get_account("main")
    paid: list[str] = []
    autopay_enabled_now: list[str] = []
    for bill in DB["bills"]:
        if bill["status"] in ("due", "overdue") and bill["amount"] <= account["balance"]:
            account["balance"] -= bill["amount"]
            bill["status"] = "paid"
            bill["due"] = "Оплачено (план месяца)"
            paid.append(bill["name"])
        if bill.get("recurring") and bill.get("autopay_eligible") and not bill.get("autopay_enabled"):
            bill["autopay_enabled"] = True
            autopay_enabled_now.append(bill["name"])
    savings = plan["savings_amount"]
    if savings > 0 and savings <= account["balance"]:
        account["balance"] -= savings
        get_account("save")["balance"] += savings
        update_mission_progress("save_goal", delta=savings)
    update_mission_progress("autopilot", absolute=1)
    update_mission_progress("autopay", delta=len(autopay_enabled_now))
    create_transaction(name="План месяца применён", category="autopilot", amount=plan["bills_total"] + savings, direction="out", account_id="main", icon="ПЛ", bg="#0E3A1C", tag="savings", kind="autopilot")
    DB["autopilot"]["applied"] = True
    DB["autopilot"]["applied_at"] = datetime.now().isoformat()
    DB["user"]["safe_daily_budget"] = plan["daily_budget"]
    DB["gamification"]["autopilot_applied"] = True
    DB["gamification"]["streak_days"] = min(DB["gamification"]["streak_days"] + 1, 365)
    if DB["gamification"]["streak_days"] > DB["gamification"]["streak_best"]:
        DB["gamification"]["streak_best"] = DB["gamification"]["streak_days"]
    _award_points(500, "План месяца")
    refresh_scores()
    reserve_offer = next((offer for offer in compute_smart_offers() if offer["id"] == "reserve"), None)
    return jsonify({"ok": True, "message": f"Оплачено {len(paid)} счетов, {savings:,} с → накопления", "paid_bills": paid, "autopay_enabled": autopay_enabled_now, "new_main_balance": account["balance"], "new_save_balance": get_account("save")["balance"], "points_earned": 500, "gamification": DB["gamification"], "forecast": compute_safe_to_spend(), "risk_radar": compute_risk_radar(), "followup_offer": reserve_offer})


@app.route("/api/risk-radar")
def api_risk_radar():
    return jsonify(compute_risk_radar())


@app.route("/api/smart-offers")
def api_smart_offers():
    return jsonify({"offers": compute_smart_offers()})


@app.route("/api/offer-action", methods=["POST"])
def api_offer_action():
    offer_id = (request.get_json(silent=True) or {}).get("offer_id")
    if offer_id == "autopay":
        enabled: list[str] = []
        for bill in DB["bills"]:
            if bill.get("recurring") and not bill.get("autopay_enabled") and bill.get("autopay_eligible"):
                bill["autopay_enabled"] = True
                enabled.append(bill["name"])
        update_mission_progress("autopay", delta=len(enabled))
        _award_points(90, "Autopay enabled")
        return jsonify(serialize_offer_outcome("autopay", 90, f"Автоплатёж включён для {len(enabled)} счетов"))
    if offer_id == "reserve":
        DB["products"]["m_plus"]["active"] = True
        DB["user"]["reserve_limit_active"] = True
        _award_points(75, "Reserve activated")
        return jsonify(serialize_offer_outcome("reserve", 75, "M+ резерв активирован. Лимит доступен на случай кассового разрыва"))
    if offer_id == "savings_boost":
        account = get_account("main")
        amount = 3000
        if account["balance"] < amount:
            return jsonify({"ok": False, "error": "Недостаточно средств для усиления накоплений"}), 400
        account["balance"] -= amount
        get_account("save")["balance"] += amount
        create_transaction(name="Пополнение накоплений", category="savings", amount=amount, direction="out", account_id="main", icon="НК", bg="#0E3A1C", tag="savings", kind="offer_savings")
        update_mission_progress("save_goal", delta=amount)
        _award_points(60, "Savings boost")
        return jsonify(serialize_offer_outcome("savings_boost", 60, "3 000 с переведены в накопления по smart offer"))
    if offer_id == "travel_goal":
        DB["goals"].append({"id": len(DB["goals"]) + 1, "name": "Поездка", "icon": "ПТ", "bg": "#2A1E00", "target": 50000, "saved": 0, "deadline": "Рекомендуемый срок"})
        _award_points(40, "Travel goal")
        return jsonify(serialize_offer_outcome("travel_goal", 40, "Создали отдельную цель для поездки и включили её в логику приложения"))
    return jsonify({"ok": False, "error": "Неизвестное действие"}), 400


@app.route("/api/gamification")
def api_gamification():
    refresh_scores()
    gamification = DB["gamification"]
    level, next_level, progress = get_level_info(gamification["points"])
    completed_count = sum(1 for mission in gamification["missions"] if mission["completed"])
    return jsonify({"points": gamification["points"], "level": level, "next_level": next_level, "level_progress_pct": progress, "streak_days": gamification["streak_days"], "streak_best": gamification["streak_best"], "discipline_score": gamification["discipline_score"], "missions": gamification["missions"], "completed_count": completed_count, "total_missions": len(gamification["missions"]), "this_month_actions": gamification["this_month_actions"], "autopilot_applied": gamification["autopilot_applied"]})


@app.route("/api/gamification/complete-mission", methods=["POST"])
def api_complete_mission():
    mission = get_mission((request.get_json(silent=True) or {}).get("mission_id"))
    if not mission:
        return jsonify({"ok": False, "error": "Миссия не найдена"}), 404
    if mission["completed"]:
        return jsonify({"ok": False, "error": "Уже выполнена"}), 400
    if mission["progress"] < mission["total"]:
        return jsonify({"ok": False, "error": "Миссия ещё не готова к завершению"}), 400
    mission["completed"] = True
    new_points = _award_points(mission["points"], f"Mission: {mission['title']}")
    refresh_scores()
    level, _, progress = get_level_info(new_points)
    return jsonify({"ok": True, "points_earned": mission["points"], "total_points": new_points, "level": level, "level_progress_pct": progress, "mission": mission})


@app.route("/api/gamification/streak-checkin", methods=["POST"])
def api_streak_checkin():
    gamification = DB["gamification"]
    gamification["streak_days"] = min(gamification["streak_days"] + 1, 365)
    if gamification["streak_days"] > gamification["streak_best"]:
        gamification["streak_best"] = gamification["streak_days"]
    points = 100 if gamification["streak_days"] % 7 == 0 else 20
    new_points = _award_points(points, "Daily check-in")
    update_mission_progress("streak_5", absolute=gamification["streak_days"])
    refresh_scores()
    return jsonify({"ok": True, "streak_days": gamification["streak_days"], "points_earned": points, "total_points": new_points, "is_milestone": gamification["streak_days"] % 7 == 0})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    user_message = (data.get("message") or "").strip()
    history = data.get("history", [])
    if not user_message:
        return jsonify({"ok": False, "error": "Сообщение пустое"}), 400
    if is_sensitive_request(user_message):
        reply = safety_refusal()
        DB["chat_history"].append({"role": "assistant", "content": reply})
        return jsonify({"ok": True, "reply": reply, "action": None, "guarded": True})
    if not GROQ_API_KEY:
        reply, action = fallback_chat_response(user_message)
        DB["chat_history"].append({"role": "assistant", "content": reply or str(action)})
        _award_points(10, "Диалог")
        refresh_scores()
        return jsonify({"ok": True, "reply": reply, "action": action, "local": True})
    messages = [
        {"role": "system", "content": build_system_prompt()},
        {"role": "system", "content": AI_CAPABILITIES_PROMPT},
    ]
    for item in history[-10:]:
        if item.get("role") in ("user", "assistant") and item.get("content"):
            messages.append({"role": item["role"], "content": str(item["content"])})
    messages.append({"role": "user", "content": user_message})
    try:
        response = requests.post(GROQ_URL, headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}, json={"model": GROQ_MODEL, "messages": messages, "max_tokens": 600, "temperature": 0.7}, timeout=20)
        if response.status_code == 401:
            reply, action = fallback_chat_response(user_message)
            return jsonify({"ok": True, "reply": reply, "action": action, "local": True})
        if response.status_code == 400:
            reply, action = fallback_chat_response(user_message)
            return jsonify({"ok": True, "reply": reply, "action": action, "local": True})
        if response.status_code == 429:
            reply, action = fallback_chat_response(user_message)
            return jsonify({"ok": True, "reply": reply, "action": action, "local": True})
        response.raise_for_status()
        result = response.json()
        reply = result["choices"][0]["message"]["content"].strip()
        clean_reply, action_result = parse_action_from_reply(reply)
        DB["chat_history"].append({"role": "assistant", "content": clean_reply or str(action_result)})
        _award_points(10, "Диалог")
        refresh_scores()
        return jsonify({"ok": True, "reply": clean_reply, "action": action_result})
    except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
        reply, action = fallback_chat_response(user_message)
        DB["chat_history"].append({"role": "assistant", "content": reply or str(action)})
        _award_points(10, "Диалог")
        refresh_scores()
        return jsonify({"ok": True, "reply": reply, "action": action, "local": True})
    except Exception as error:
        return jsonify({"ok": False, "error": f"Ошибка: {error}"}), 500


if __name__ == "__main__":
    debug_enabled = os.getenv("FLASK_DEBUG", "0").lower() in {"1", "true", "yes", "on"}
    port = int(os.getenv("PORT", "5000"))
    print("=" * 60)
    print("  MBANK Stage 3 backend запущен")
    print(f"  Открой: http://localhost:{port}")
    print(f"  SQLite: {DATABASE_PATH}")
    print("=" * 60)
<<<<<<< HEAD
    app.run(debug=debug_enabled, port=port)
=======
    app.run(host="0.0.0.0", port=5000, debug=True)
>>>>>>> 2935c8f01a17472c7840f314e71e813d2b4e42fc

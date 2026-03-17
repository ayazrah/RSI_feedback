"""
Telegram Inline Feedback Bot → SQLite
"""

import os
import sqlite3
import logging
import uuid
from datetime import datetime, timedelta, timezone

from telegram import (
    Update,
    InlineQueryResultArticle,
    InputTextMessageContent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ── Настройки ──────────────────────────────────────────────────────────────────
BOT_TOKEN      = os.getenv("BOT_TOKEN", "ВСТАВЬТЕ_ВАШ_ТОКЕН_СЮДА")
BOT_USERNAME   = os.getenv("BOT_USERNAME", "ВСТАВЬТЕ_USERNAME_БОТА")
DB_PATH        = "feedback.db"
NOTIFY_CHAT_ID = -1003820171858
MSK            = timezone(timedelta(hours=3))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Доступ ─────────────────────────────────────────────────────────────────────
ALLOWED_USERS = {
    108667940,    # Менеджер ayazayaz
    5808377858,   # Менеджер nikita_garant
    7205308109,   # Менеджер ZULFAT_GARANT
    6655733699,   # Менеджер Andrei_garant
    6138623597,   # Менеджер Kem_garant
    7664718647,   # Менеджер leisan_garant
    7993132246,   # Менеджер Shvartsman_GARANT
    6872667947,   # Менеджер AZAT_GRNT
    6263705985,   # Менеджер rustam_garant
    5942862179,   # Менеджер ZAGarant
    8480026847,   # Менеджер elnara_garant
    8748818704,   # Менеджер garant_keeper
    5268473829,   # Менеджер rs_garant
    7781558647,   # Менеджер rr16main
    153163996,    # Менеджер salamonovalexey
    7830114802,   # Менеджер Marty_Garant
    321931103,    # Менеджер Maxinvestman
    1723384169,   # Менеджер rsi_garant
    7739441098,   # Менеджер trade_aam
    572594467,    # Менеджер azat_garant
    175983565,    # Менеджер Sabirov_Airat
    68015989,     # Менеджер saleevya
    203219055,    # Менеджер dicheri
    100835492,    # Менеджер grenat
    5950933923,   # Менеджер albertf116
    8580932423,   # Менеджер Rashid_Garant
    8415301378,   # Менеджер TIM_GARANTRSI
}

ADMIN_USERS = {
    108667940,    # Администратор ayazayaz
    5808377858,   # Администратор nikita_garant
}

# ── Шаблоны опросов ────────────────────────────────────────────────────────────
SURVEYS = [
    {
        "id": "speed",
        "title": "Скорость выполнения",
        "description": "Как вам скорость выполнения заявки?",
        "question": "⚡ Как вам скорость выполнения заявки?",
        "buttons": [
            ("s1", "🚀 Быстро, всё устроило", False),
            ("s2", "🕐 Дольше чем ожидал", False),
            ("s3", "😤 Очень долго", True),
        ],
    },
    {
        "id": "communication",
        "title": "Коммуникация",
        "description": "Держали ли вас в курсе по ходу заявки?",
        "question": "📞 Держали ли вас в курсе по ходу заявки?",
        "buttons": [
            ("c1", "👍 Да, всё понятно", False),
            ("c2", "😐 Иногда уточнял сам", False),
            ("c3", "👎 Приходилось спрашивать", True),
        ],
    },
    {
        "id": "return",
        "title": "Готовность вернуться",
        "description": "Планируете обратиться к нам снова?",
        "question": "🔄 Планируете обратиться к нам снова?",
        "buttons": [
            ("r1", "✅ Да, буду обращаться", False),
            ("r2", "🤔 Зависит от условий", False),
            ("r3", "❌ Нет", True),
        ],
    },
    {
        "id": "declined",
        "title": "Почему не совершил обмен",
        "description": "Для клиентов которые отказались от сделки",
        "question": "🤔 Почему вы решили не продолжать?",
        "buttons": [
            ("d1", "💰 Курс не устроил", True),
            ("d2", "⏳ Долго ждать", True),
            ("d3", "😕 Мало информации", True),
            ("d4", "🔒 Безопасность", True),
            ("d5", "🏦 Другой сервис", True),
        ],
    },
    {
        "id": "impression",
        "title": "Общее впечатление",
        "description": "Эмоции и впечатления от работы с нами",
        "question": "😊 Как вам общее впечатление от работы с нами?",
        "buttons": [
            ("i1", "😊 Всё понравилось", False),
            ("i2", "😐 Нормально, есть что улучшить", False),
            ("i3", "😟 Неприятный осадок", True),
        ],
    },
]

SURVEY_MAP = {s["id"]: s for s in SURVEYS}

BUTTON_MAP = {}
for s in SURVEYS:
    for code, text, is_negative in s["buttons"]:
        BUTTON_MAP[code] = (text, is_negative, s["id"])


# ── База данных ────────────────────────────────────────────────────────────────
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS feedback (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at      TEXT NOT NULL,
                survey_title    TEXT NOT NULL,
                survey_question TEXT NOT NULL,
                rating          TEXT NOT NULL,
                comment         TEXT,
                client_name     TEXT,
                client_id       INTEGER NOT NULL,
                manager_name    TEXT,
                manager_id      INTEGER NOT NULL
            )
        """)
        conn.commit()


def save_feedback(survey_title, survey_question, rating,
                  client_name, client_id, manager_name, manager_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute(
            """INSERT INTO feedback
               (created_at, survey_title, survey_question, rating,
                client_name, client_id, manager_name, manager_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (datetime.now(MSK).isoformat(), survey_title, survey_question,
             rating, client_name, client_id, manager_name, manager_id),
        )
        conn.commit()
        return cursor.lastrowid


def save_comment(feedback_id, comment):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE feedback SET comment = ? WHERE id = ?", (comment, feedback_id))
        conn.commit()


def get_feedback_by_id(feedback_id):
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute(
            "SELECT survey_title, rating, client_name, manager_name FROM feedback WHERE id = ?",
            (feedback_id,)
        ).fetchone()


def get_stats():
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT rating, COUNT(*) as cnt
            FROM feedback
            GROUP BY rating
            ORDER BY cnt DESC
        """).fetchall()
        total = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
    return rows, total


# ── Inline query ───────────────────────────────────────────────────────────────
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    manager = query.from_user

    if manager.id not in ALLOWED_USERS:
        await query.answer([], switch_pm_text="⛔ У вас нет доступа", switch_pm_parameter="no_access")
        return

    search = query.query.lower().strip()
    results = []

    for survey in SURVEYS:
        if search and search not in survey["title"].lower() and search not in survey["description"].lower():
            continue

        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(
                text,
                callback_data=f"fb|{code}|{manager.id}"
            )]
            for code, text, _ in survey["buttons"]
        ])

        results.append(
            InlineQueryResultArticle(
                id=str(uuid.uuid4()),
                title=survey["title"],
                description=survey["description"],
                input_message_content=InputTextMessageContent(survey["question"]),
                reply_markup=keyboard,
            )
        )

    await query.answer(results, cache_time=10)


# ── Callback — клиент нажал кнопку ────────────────────────────────────────────
async def handle_feedback_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Спасибо за ответ! 🙏")

    parts = query.data.split("|")
    if len(parts) != 3 or parts[0] != "fb":
        return

    _, btn_code, manager_id_str = parts
    manager_id = int(manager_id_str)
    client = query.from_user

    if btn_code not in BUTTON_MAP:
        return

    rating_text, is_negative, survey_id = BUTTON_MAP[btn_code]
    survey = SURVEY_MAP.get(survey_id, {})

    manager_chat = await context.bot.get_chat(manager_id)
    manager_name = manager_chat.full_name if manager_chat else str(manager_id)

    feedback_id = save_feedback(
        survey_title=survey.get("title", survey_id),
        survey_question=survey.get("question", ""),
        rating=rating_text,
        client_name=client.full_name,
        client_id=client.id,
        manager_name=manager_name,
        manager_id=manager_id,
    )

    needs_comment = is_negative or survey_id == "declined"

    if needs_comment:
        deep_link = f"https://t.me/{BOT_USERNAME}?start=comment_{feedback_id}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Оставить комментарий", url=deep_link)]
        ])
        await query.edit_message_text(
            f"{survey.get('question', 'Оценка сервиса')}\n\n"
            f"Ваш ответ: {rating_text}\n\n"
            "Если хотите оставить комментарий — нажмите кнопку ниже,\n"
            "запустите бота и напишите одним сообщением:",
            reply_markup=keyboard,
        )
    else:
        await query.edit_message_text(
            f"{survey.get('question', 'Оценка сервиса')}\n\n"
            f"Ваш ответ: {rating_text}\n\n"
            "Спасибо! Мы ценим ваше мнение 🙏"
        )

    try:
        await context.bot.send_message(
            chat_id=NOTIFY_CHAT_ID,
            text=(
                f"📊 Новая обратная связь!\n\n"
                f"📋 Опрос: {survey.get('title', survey_id)}\n"
                f"👤 Клиент: {client.full_name}\n"
                f"🆔 ID клиента: {client.id}\n"
                f"👨‍💼 Менеджер: {manager_name}\n"
                f"⭐ Ответ: {rating_text}\n"
                f"🕐 Время: {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')}"
                + ("\n⏳ Ожидаем комментарий..." if needs_comment else "")
            ),
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление в группу: {e}")


# ── /start ─────────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Deep link — клиент хочет оставить комментарий
    if context.args and context.args[0].startswith("comment_"):
        try:
            feedback_id = int(context.args[0].split("_")[1])
            row = get_feedback_by_id(feedback_id)
            if row:
                survey_title, rating, client_name, manager_name = row
                context.user_data["awaiting_comment"] = {
                    "feedback_id": feedback_id,
                    "rating": rating,
                    "survey_title": survey_title,
                    "client_name": client_name,
                    "manager_name": manager_name,
                }
                await update.message.reply_text(
                    "Спасибо что решили написать! 🙏\n\n"
                    "Напишите пожалуйста одним сообщением что именно произошло — "
                    "мы обязательно разберёмся и исправим.\n\n"
                    "⚠️ Напишите всё одним сообщением, после отправки комментарий будет сохранён."
                )
                return
        except Exception as e:
            logger.warning(f"Ошибка deep link: {e}")

    # Обычный /start — для клиента
    await update.message.reply_text(
        "👋 Здравствуйте!\n\n"
        "Мы ценим ваше мнение и хотим становиться лучше.\n\n"
        "Если вы здесь — значит наш менеджер попросил вас "
        "оставить короткую оценку нашей работы.\n\n"
        "Это займёт 10 секунд — просто нажмите одну кнопку в диалоге с менеджером.\n\n"
        "Спасибо что помогаете нам улучшаться! 🙏"
    )


# ── Комментарий ────────────────────────────────────────────────────────────────
async def handle_comment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "awaiting_comment" not in context.user_data:
        return

    data = context.user_data.pop("awaiting_comment")
    comment = update.message.text
    save_comment(data["feedback_id"], comment)

    await update.message.reply_text(
        "Спасибо за ваш комментарий! 🙏\n"
        "Мы обязательно разберёмся и улучшим нашу работу."
    )

    try:
        await context.bot.send_message(
            chat_id=NOTIFY_CHAT_ID,
            text=(
                f"💬 Комментарий к оценке!\n\n"
                f"📋 Опрос: {data['survey_title']}\n"
                f"👤 Клиент: {data['client_name']}\n"
                f"⭐ Оценка: {data['rating']}\n"
                f"👨‍💼 Менеджер: {data['manager_name']}\n\n"
                f"📝 Комментарий:\n{comment}"
            ),
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить комментарий в группу: {e}")


# ── Команды ────────────────────────────────────────────────────────────────────
async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USERS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    rows, total = get_stats()
    if total == 0:
        await update.message.reply_text("📊 Пока нет ни одного ответа.")
        return
    lines = [f"📊 Статистика обратной связи (всего: {total})\n"]
    for rating, cnt in rows:
        pct = round(cnt / total * 100)
        bar = "█" * (pct // 5) or "▏"
        lines.append(f"{rating}: {cnt} ({pct}%) {bar}")
    await update.message.reply_text("\n".join(lines))


async def cmd_export(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_USERS:
        await update.message.reply_text("⛔ У вас нет доступа.")
        return
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT created_at, survey_title, rating, comment,
                   client_name, client_id, manager_name, manager_id
            FROM feedback ORDER BY created_at DESC
        """).fetchall()
    if not rows:
        await update.message.reply_text("📊 Пока нет ни одного ответа.")
        return
    lines = ["Дата;Опрос;Ответ;Комментарий;Клиент;ID клиента;Менеджер;ID менеджера"]
    for row in rows:
        lines.append(";".join(str(x) if x is not None else "" for x in row))
    csv_bytes = "\n".join(lines).encode("utf-8-sig")
    await update.message.reply_document(
        document=csv_bytes,
        filename=f"feedback_{datetime.now(MSK).strftime('%d%m%Y_%H%M')}.csv",
        caption="📊 Выгрузка обратной связи"
    )


# ── Запуск ─────────────────────────────────────────────────────────────────────
def main():
    init_db()
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("export", cmd_export))
    app.add_handler(InlineQueryHandler(handle_inline_query))
    app.add_handler(CallbackQueryHandler(handle_feedback_button, pattern=r"^fb\|"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_comment))
    logger.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()

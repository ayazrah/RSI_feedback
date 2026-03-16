"""
Telegram Inline Feedback Bot → SQLite
======================================
Менеджер в диалоге с клиентом пишет @ваш_бот — появляется список шаблонов.
Клиент нажимает кнопку — ответ сохраняется в feedback.db (SQLite).
При негативной оценке появляется кнопка "Оставить комментарий".
Уведомления приходят в одну группу.
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
BOT_USERNAME   = os.getenv("BOT_USERNAME", "ВСТАВЬТЕ_USERNAME_БОТА")  # без @
DB_PATH        = "feedback.db"
NOTIFY_CHAT_ID = -1003820171858
MSK            = timezone(timedelta(hours=3))

NEGATIVE_RATINGS = {"👎 Плохо", "❌ Нет", "🐢 Медленно", "👎 Нет"}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ── Whitelist ──────────────────────────────────────────────────────────────────
ALLOWED_USERS = {
    108667940,   # Менеджер Ayaz
    5808377858,   # Менеджер Nikita_garant
}


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
        conn.execute(
            "UPDATE feedback SET comment = ? WHERE id = ?",
            (comment, feedback_id)
        )
        conn.commit()


def get_feedback_by_id(feedback_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT survey_title, rating, client_name, manager_name FROM feedback WHERE id = ?",
            (feedback_id,)
        ).fetchone()
    return row


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


# ── Шаблоны опросов ────────────────────────────────────────────────────────────
SURVEYS = [
    {
        "id": "general",
        "title": "Общая оценка сервиса",
        "description": "Как вам наш сервис в целом?",
        "question": "👋 Оцените, пожалуйста, качество нашего сервиса:",
        "buttons": ["👍 Отлично", "😐 Нормально", "👎 Плохо"],
    },
    {
        "id": "support",
        "title": "Оценка поддержки",
        "description": "Помогли ли мы решить ваш вопрос?",
        "question": "🎧 Мы решили ваш вопрос?",
        "buttons": ["✅ Да, полностью", "⚠️ Частично", "❌ Нет"],
    },
    {
        "id": "speed",
        "title": "Скорость обслуживания",
        "description": "Насколько быстро мы ответили?",
        "question": "⚡ Оцените скорость нашего ответа:",
        "buttons": ["🚀 Быстро", "🕐 Приемлемо", "🐢 Медленно"],
    },
    {
        "id": "recommend",
        "title": "Рекомендация",
        "description": "Порекомендуете ли нас друзьям?",
        "question": "🤝 Вы бы порекомендовали нас друзьям или коллегам?",
        "buttons": ["👍 Да, конечно", "🤔 Возможно", "👎 Нет"],
    },
]

SURVEY_MAP = {s["id"]: s for s in SURVEYS}


# ── Inline query ───────────────────────────────────────────────────────────────
async def handle_inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.inline_query
    manager = query.from_user

    if manager.id not in ALLOWED_USERS:
        await query.answer(
            [],
            switch_pm_text="⛔ У вас нет доступа",
            switch_pm_parameter="no_access",
        )
        return

    search = query.query.lower().strip()
    results = []

    for survey in SURVEYS:
        if search and search not in survey["title"].lower() and search not in survey["description"].lower():
            continue

        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton(
                    btn,
                    callback_data=f"fb|{survey['id']}|{btn}|{manager.id}|{manager.full_name}"
                )
            ]
            for btn in survey["buttons"]
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


# ── Callback — клиент нажал кнопку оценки ─────────────────────────────────────
async def handle_feedback_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Спасибо за ответ! 🙏")

    parts = query.data.split("|")
    if len(parts) != 5 or parts[0] != "fb":
        return

    _, survey_id, rating, manager_id_str, manager_name = parts
    manager_id = int(manager_id_str)
    client = query.from_user
    survey = SURVEY_MAP.get(survey_id, {})

    # Сохраняем в SQLite
    feedback_id = save_feedback(
        survey_title=survey.get("title", survey_id),
        survey_question=survey.get("question", ""),
        rating=rating,
        client_name=client.full_name,
        client_id=client.id,
        manager_name=manager_name,
        manager_id=manager_id,
    )

    # Если негативная — показываем кнопку "Оставить комментарий" с deep link
    if rating in NEGATIVE_RATINGS:
        deep_link = f"https://t.me/{BOT_USERNAME}?start=comment_{feedback_id}"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Оставить комментарий", url=deep_link)]
        ])
        await query.edit_message_text(
            f"{survey.get('question', 'Оценка сервиса')}\n\n"
            f"Ваш ответ: {rating}\n\n"
            "Жаль, что что-то пошло не так 😔\n"
            "Если хотите оставить комментарий — нажмите кнопку ниже,\n"
            "запустите бота и напишите одним сообщением что пошло не так:",
            reply_markup=keyboard,
        )
    else:
        await query.edit_message_text(
            f"{survey.get('question', 'Оценка сервиса')}\n\n"
            f"Ваш ответ: {rating}\n\n"
            "Спасибо! Мы ценим ваше мнение 🙏"
        )

    # Уведомляем группу
    try:
        await context.bot.send_message(
            chat_id=NOTIFY_CHAT_ID,
            text=(
                f"📊 Новая обратная связь!\n\n"
                f"📋 Опрос: {survey.get('title', survey_id)}\n"
                f"👤 Клиент: {client.full_name}\n"
                f"🆔 ID клиента: {client.id}\n"
                f"👨‍💼 Менеджер: {manager_name}\n"
                f"⭐ Ответ: {rating}\n"
                f"🕐 Время: {datetime.now(MSK).strftime('%d.%m.%Y %H:%M')}"
                + ("\n⏳ Ожидаем комментарий..." if rating in NEGATIVE_RATINGS else "")
            ),
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление в группу: {e}")


# ── /start — обычный и с deep link ────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем есть ли параметр comment_ID
    if context.args and context.args[0].startswith("comment_"):
        try:
            feedback_id = int(context.args[0].split("_")[1])
            row = get_feedback_by_id(feedback_id)
            if row:
                survey_title, rating, client_name, manager_name = row
                # Сохраняем в контексте что ждём комментарий
                context.user_data["awaiting_comment"] = {
                    "feedback_id": feedback_id,
                    "rating": rating,
                    "survey_title": survey_title,
                    "client_name": client_name,
                    "manager_name": manager_name,
                }
                await update.message.reply_text(
                    "Спасибо что решили написать! 🙏\n\n"
                    "Напишите пожалуйста одним сообщением что именно пошло не так — "
                    "мы обязательно разберёмся и исправим.\n\n"
                )
                return
        except Exception as e:
            logger.warning(f"Ошибка deep link: {e}")

    await update.message.reply_text(
        "👋 Привет!\n\n"
        "Я бот для сбора обратной связи.\n\n"
        "📌 Как использовать:\n"
        "В диалоге с клиентом напишите @RSI_feedback_bot — "
        "появится список шаблонов опросов.\n"
        "Выберите нужный — я отправлю вопрос с кнопками прямо в чат.\n"
        "Как только клиент ответит — уведомление придёт в группу.\n\n"
        "📊 /stats — статистика\n"
        "📥 /export — выгрузка в CSV"
    )


# ── Обработка текстового комментария ──────────────────────────────────────────
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
                f"💬 Комментарий к негативной оценке!\n\n"
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
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("""
            SELECT created_at, survey_title, rating, comment,
                   client_name, client_id, manager_name, manager_id
            FROM feedback
            ORDER BY created_at DESC
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

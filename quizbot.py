import random
import sqlite3
from datetime import datetime
from docx import Document

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton
)

from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters
)

# =========================
# SOZLAMALAR
# =========================

TOKEN = "TOKENINGIZNI_QOYING"
ADMIN_ID = 5183129765

# =========================
# DATABASE
# =========================

def init_db():
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        full_name TEXT,
        username TEXT,
        tests_count INTEGER DEFAULT 0,
        correct_answers INTEGER DEFAULT 0,
        wrong_answers INTEGER DEFAULT 0,
        best_score INTEGER DEFAULT 0,
        last_activity TEXT
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS allowed_users(
        user_id INTEGER PRIMARY KEY
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS blocked_users(
        user_id INTEGER PRIMARY KEY
    )
    """)

    conn.commit()
    conn.close()


# =========================
# TESTLARNI YUKLASH
# =========================

questions = []

def load_questions():
    global questions
    questions.clear()

    try:
        doc = Document("testlar.docx")

        q = {}
        opts = []

        for p in doc.paragraphs:
            text = p.text.strip()

            if not text:
                continue

            if text.startswith(("A)", "B)", "C)", "D)")):
                opts.append(text)

            elif text.startswith("ANSWER:"):
                ans = text.replace("ANSWER:", "").strip()

                q["options"] = opts.copy()
                q["answer"] = ans[0].upper()

                questions.append(q.copy())

                q = {}
                opts = []

            else:
                q["question"] = text

        print(f"✅ {len(questions)} savol yuklandi")

    except Exception as e:
        print("❌ Savol yuklash xatosi:", e)


# =========================
# USER TEKSHIRUV
# =========================

def is_allowed(user_id):
    if user_id == ADMIN_ID:
        return True

    conn = sqlite3.connect("bot.db")
    c = conn.cursor()

    c.execute(
        "SELECT user_id FROM allowed_users WHERE user_id=?",
        (user_id,)
    )

    result = c.fetchone()
    conn.close()

    return result is not None


def is_blocked(user_id):
    if user_id == ADMIN_ID:
        return False

    conn = sqlite3.connect("bot.db")
    c = conn.cursor()

    c.execute(
        "SELECT user_id FROM blocked_users WHERE user_id=?",
        (user_id,)
    )

    result = c.fetchone()
    conn.close()

    return result is not None


# =========================
# USER UPDATE
# =========================

def update_stats(user, score, correct, wrong):
    conn = sqlite3.connect("bot.db")
    c = conn.cursor()

    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    c.execute("""
    INSERT OR IGNORE INTO users(
        user_id,
        full_name,
        username
    )
    VALUES (?, ?, ?)
    """, (
        user.id,
        user.full_name,
        user.username
    ))

    c.execute("""
    UPDATE users
    SET
        full_name=?,
        username=?,
        tests_count=tests_count+1,
        correct_answers=correct_answers+?,
        wrong_answers=wrong_answers+?,
        best_score=CASE
            WHEN ? > best_score THEN ?
            ELSE best_score
        END,
        last_activity=?
    WHERE user_id=?
    """, (
        user.full_name,
        user.username,
        correct,
        wrong,
        score,
        score,
        now,
        user.id
    ))

    conn.commit()
    conn.close()


# =========================
# MENULAR
# =========================

def user_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📝 Test ishlash")],
            [KeyboardButton("📊 Statistika")]
        ],
        resize_keyboard=True
    )


def admin_menu():
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("📝 Test ishlash")],
            [KeyboardButton("📊 Statistika")],
            [KeyboardButton("👑 Admin Panel")]
        ],
        resize_keyboard=True
    )


def admin_panel_buttons():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Ruxsat berish", callback_data="add_user")
        ],
        [
            InlineKeyboardButton("🚫 Block qilish", callback_data="block_user")
        ],
        [
            InlineKeyboardButton("✅ Blockdan chiqarish", callback_data="unblock_user")
        ],
        [
            InlineKeyboardButton("📋 Block list", callback_data="block_list")
        ],
        [
            InlineKeyboardButton("👥 Aktiv userlar", callback_data="active_users")
        ]
    ])


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if is_blocked(user.id):
        await update.message.reply_text(
            "🚫 Siz bloklangansiz."
        )
        return

    if not is_allowed(user.id):
        await update.message.reply_text(
            "⛔ Sizga botdan foydalanish uchun ruxsat berilmagan."
        )
        return

    text = (
        "✅ Botga xush kelibsiz\n\n"
        f"👤 {user.full_name}\n"
        f"🆔 {user.id}"
    )

    if user.id == ADMIN_ID:
        await update.message.reply_text(
            text,
            reply_markup=admin_menu()
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=user_menu()
        )


# =========================
# TEST
# =========================

async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if is_blocked(user.id):
        await update.message.reply_text("🚫 Siz bloklangansiz.")
        return

    if not is_allowed(user.id):
        await update.message.reply_text(
            "⛔ Sizga botdan foydalanish uchun ruxsat berilmagan."
        )
        return

    quiz = random.sample(
        questions,
        min(30, len(questions))
    )

    context.user_data["quiz"] = quiz
    context.user_data["index"] = 0
    context.user_data["correct"] = 0
    context.user_data["wrong"] = 0

    await send_question(update, context)


async def send_question(update, context):
    idx = context.user_data["index"]
    quiz = context.user_data["quiz"]

    if idx >= len(quiz):
        correct = context.user_data["correct"]
        wrong = context.user_data["wrong"]

        user = update.effective_user

        update_stats(
            user,
            correct,
            correct,
            wrong
        )

        percent = (correct / 30) * 100

        await update.effective_message.reply_text(
            f"🏁 Test tugadi\n\n"
            f"✅ To'g'ri: {correct}\n"
            f"❌ Noto'g'ri: {wrong}\n"
            f"📈 Foiz: {percent:.1f}%"
        )
        return

    q = quiz[idx]

    context.user_data["current"] = q

    text = (
        f"❓ {idx+1}-savol\n\n"
        f"{q['question']}\n\n"
        + "\n".join(q["options"])
    )

    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("A", callback_data="A"),
            InlineKeyboardButton("B", callback_data="B"),
            InlineKeyboardButton("C", callback_data="C"),
            InlineKeyboardButton("D", callback_data="D")
        ]
    ])

    await update.effective_message.reply_text(
        text,
        reply_markup=kb
    )


# =========================
# CALLBACK
# =========================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user = update.effective_user

    # =====================
    # ADMIN PANEL
    # =====================

    if query.data == "add_user":
        context.user_data["mode"] = "add"
        await query.message.reply_text(
            "➕ ID yuboring:\n\nMisol:\n7155734904"
        )
        return

    if query.data == "block_user":
        context.user_data["mode"] = "block"
        await query.message.reply_text(
            "🚫 Block qilish uchun ID yuboring"
        )
        return

    if query.data == "unblock_user":
        context.user_data["mode"] = "unblock"
        await query.message.reply_text(
            "✅ Blockdan chiqarish uchun ID yuboring"
        )
        return

    if query.data == "block_list":
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()

        c.execute("""
        SELECT users.full_name, users.username, blocked_users.user_id
        FROM blocked_users
        LEFT JOIN users
        ON users.user_id = blocked_users.user_id
        """)

        rows = c.fetchall()
        conn.close()

        if not rows:
            await query.message.reply_text(
                "📭 Block list bo'sh"
            )
            return

        msg = "🚫 BLOCK LIST:\n\n"

        for row in rows:
            name = row[0] or "Noma'lum"
            username = row[1] or "-"
            uid = row[2]

            msg += (
                f"👤 {name}\n"
                f"📛 @{username}\n"
                f"🆔 {uid}\n\n"
            )

        await query.message.reply_text(msg)
        return

    if query.data == "active_users":
        conn = sqlite3.connect("bot.db")
        c = conn.cursor()

        c.execute("""
        SELECT full_name, username, tests_count, last_activity
        FROM users
        ORDER BY last_activity DESC
        LIMIT 20
        """)

        rows = c.fetchall()
        conn.close()

        if not rows:
            await query.message.reply_text(
                "Userlar topilmadi"
            )
            return

        msg = "🧑‍🤝‍🧑 Aktiv userlar:\n\n"

        for i, row in enumerate(rows, start=1):
            msg += (
                f"{i}. {row[0]}\n"
                f"@{row[1]}\n"
                f"📝 Testlar: {row[2]}\n"
                f"⏰ {row[3]}\n\n"
            )

        await query.message.reply_text(msg)
        return

    # =====================
    # TEST
    # =====================

    q = context.user_data.get("current")

    if not q:
        return

    if query.data == q["answer"]:
        context.user_data["correct"] += 1

        await query.message.reply_text(
            f"✅ To'g'ri ({q['answer']})"
        )

    else:
        context.user_data["wrong"] += 1

        await query.message.reply_text(
            f"❌ Noto'g'ri ({q['answer']})"
        )

    context.user_data["index"] += 1

    await send_question(update, context)


# =========================
# TEXT
# =========================

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user = update.effective_user

    if user.id == ADMIN_ID:

        mode = context.user_data.get("mode")

        # ADD USER
        if mode == "add":
            try:
                uid = int(text)

                conn = sqlite3.connect("bot.db")
                c = conn.cursor()

                c.execute("""
                INSERT OR IGNORE INTO allowed_users(user_id)
                VALUES(?)
                """, (uid,))

                conn.commit()
                conn.close()

                context.user_data["mode"] = None

                await update.message.reply_text(
                    f"✅ Ruxsat berildi:\n{uid}"
                )

            except:
                await update.message.reply_text(
                    "❌ Noto'g'ri ID"
                )

            return

        # BLOCK USER
        if mode == "block":
            try:
                uid = int(text)

                conn = sqlite3.connect("bot.db")
                c = conn.cursor()

                c.execute("""
                INSERT OR IGNORE INTO blocked_users(user_id)
                VALUES(?)
                """, (uid,))

                conn.commit()
                conn.close()

                context.user_data["mode"] = None

                await update.message.reply_text(
                    f"🚫 Block qilindi:\n{uid}"
                )

            except:
                await update.message.reply_text(
                    "❌ Noto'g'ri ID"
                )

            return

        # UNBLOCK
        if mode == "unblock":
            try:
                uid = int(text)

                conn = sqlite3.connect("bot.db")
                c = conn.cursor()

                c.execute("""
                DELETE FROM blocked_users
                WHERE user_id=?
                """, (uid,))

                conn.commit()
                conn.close()

                context.user_data["mode"] = None

                await update.message.reply_text(
                    f"✅ Blockdan chiqarildi:\n{uid}"
                )

            except:
                await update.message.reply_text(
                    "❌ Noto'g'ri ID"
                )

            return

    # =====================
    # MENULAR
    # =====================

    if text == "📝 Test ishlash":
        await start_test(update, context)

    elif text == "📊 Statistika":

        conn = sqlite3.connect("bot.db")
        c = conn.cursor()

        c.execute("""
        SELECT
            tests_count,
            correct_answers,
            wrong_answers,
            best_score
        FROM users
        WHERE user_id=?
        """, (user.id,))

        row = c.fetchone()
        conn.close()

        if not row:
            await update.message.reply_text(
                "📭 Statistika mavjud emas"
            )
            return

        tests = row[0]
        correct = row[1]
        wrong = row[2]
        best = row[3]

        total = correct + wrong

        percent = 0

        if total > 0:
            percent = (correct / total) * 100

        msg = (
            f"📊 Sizning statistikangiz\n\n"
            f"📝 Ishlangan testlar: {tests}\n"
            f"✅ To'g'ri javoblar: {correct}\n"
            f"❌ Noto'g'ri javoblar: {wrong}\n"
            f"🏆 Eng yaxshi natija: {best}/30\n"
            f"📈 O'zlashtirish: {percent:.1f}%"
        )

        await update.message.reply_text(msg)

    elif text == "👑 Admin Panel":

        if user.id != ADMIN_ID:
            return

        await update.message.reply_text(
            "👑 ADMIN PANEL",
            reply_markup=admin_panel_buttons()
        )


# =========================
# MAIN
# =========================

if __name__ == "__main__":

    init_db()
    load_questions()

    print("🚀 Bot ishlayapti")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CallbackQueryHandler(callback_handler))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            text_handler
        )
    )

    app.run_polling()

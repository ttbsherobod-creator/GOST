import random
import sqlite3
import asyncio
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

TOKEN = "8712005526:AAH-5esSoHp4E5HxrUZKFljEPO7MmWsKysM"
ADMIN_ID = 5183129765

# =========================
# DATABASE
# =========================

def db():
    return sqlite3.connect("bot_data.db")


def init_db():
    conn = db()
    cur = conn.cursor()

    # users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        full_name TEXT,
        username TEXT,
        tests_count INTEGER DEFAULT 0,
        total_score INTEGER DEFAULT 0,
        best_score INTEGER DEFAULT 0,
        last_active TEXT
    )
    """)

    # allowed users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS allowed_users (
        user_id INTEGER PRIMARY KEY
    )
    """)

    # blocked users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blocked_users (
        user_id INTEGER PRIMARY KEY
    )
    """)

    conn.commit()

    # adminni avtomatik ruxsat berish
    cur.execute(
        "INSERT OR IGNORE INTO allowed_users (user_id) VALUES (?)",
        (ADMIN_ID,)
    )

    conn.commit()
    conn.close()


# =========================
# TESTLAR
# =========================

questions = []


def load_questions():
    global questions

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
                answer = text.replace("ANSWER:", "").strip()

                q["options"] = opts.copy()
                q["answer"] = answer[0]

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

def is_admin(user_id):
    return user_id == ADMIN_ID


def is_blocked(user_id):
    if is_admin(user_id):
        return False

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM blocked_users WHERE user_id=?",
        (user_id,)
    )

    user = cur.fetchone()

    conn.close()

    return bool(user)


def is_allowed(user_id):
    if is_admin(user_id):
        return True

    if is_blocked(user_id):
        return False

    conn = db()
    cur = conn.cursor()

    cur.execute(
        "SELECT * FROM allowed_users WHERE user_id=?",
        (user_id,)
    )

    user = cur.fetchone()

    conn.close()

    return bool(user)


# =========================
# USER SAVE
# =========================

def save_user(user):
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    INSERT OR IGNORE INTO users
    (user_id, full_name, username)
    VALUES (?, ?, ?)
    """, (
        user.id,
        user.full_name,
        user.username
    ))

    conn.commit()
    conn.close()


# =========================
# STATISTIKA
# =========================

def update_stats(user_id, score):
    conn = db()
    cur = conn.cursor()

    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    cur.execute("""
    UPDATE users
    SET
        tests_count = tests_count + 1,
        total_score = total_score + ?,
        best_score = CASE
            WHEN ? > best_score THEN ?
            ELSE best_score
        END,
        last_active = ?
    WHERE user_id = ?
    """, (
        score,
        score,
        score,
        now,
        user_id
    ))

    conn.commit()
    conn.close()


# =========================
# TUGMALAR
# =========================

def main_menu(user_id):
    buttons = [
        [KeyboardButton("📝 Test ishlash")],
        [KeyboardButton("📊 Natijam")]
    ]

    if is_admin(user_id):
        buttons.append([KeyboardButton("👑 Admin Panel")])

    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True
    )


def admin_panel():
    return ReplyKeyboardMarkup([
        [KeyboardButton("👥 Aktiv userlar")],
        [KeyboardButton("🚫 Block userlar")],
        [KeyboardButton("✅ Allow user")],
        [KeyboardButton("❌ Unblock user")],
        [KeyboardButton("📋 Block list")],
        [KeyboardButton("🔍 Search username")],
        [KeyboardButton("🏠 Menu")]
    ], resize_keyboard=True)


# =========================
# START
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    save_user(user)

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
        "✅ Xush kelibsiz\n\n"
        "🆔 ID: {}\n"
        "👤 {}\n"
    ).format(user.id, user.full_name)

    await update.message.reply_text(
        text,
        reply_markup=main_menu(user.id)
    )


# =========================
# TEST BOSHLASH
# =========================

async def start_test(update, context):
    user_id = update.effective_user.id

    if not is_allowed(user_id):
        return

    if len(questions) == 0:
        await update.message.reply_text(
            "❌ Savollar topilmadi."
        )
        return

    context.user_data["quiz"] = random.sample(
        questions,
        min(30, len(questions))
    )

    context.user_data["index"] = 0
    context.user_data["score"] = 0

    await send_question(update, context)


# =========================
# SAVOL
# =========================

async def send_question(update, context):
    idx = context.user_data["index"]
    quiz = context.user_data["quiz"]

    if idx >= len(quiz):
        score = context.user_data["score"]

        update_stats(
            update.effective_user.id,
            score
        )

        text = (
            f"🏁 Test tugadi\n\n"
            f"✅ Natija: {score}/30"
        )

        await update.effective_message.reply_text(text)
        return

    q = quiz[idx]

    context.user_data["current"] = q

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("A", callback_data="A"),
            InlineKeyboardButton("B", callback_data="B"),
            InlineKeyboardButton("C", callback_data="C"),
            InlineKeyboardButton("D", callback_data="D")
        ]
    ])

    text = (
        f"❓ {idx+1}-savol\n\n"
        f"{q['question']}\n\n"
        + "\n".join(q["options"])
    )

    await update.effective_message.reply_text(
        text,
        reply_markup=keyboard
    )


# =========================
# CALLBACK
# =========================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id

    if not is_allowed(user_id):
        return

    q = context.user_data.get("current")

    if not q:
        return

    answer = query.data

    if answer == q["answer"]:
        context.user_data["score"] += 1

        await query.message.reply_text(
            f"✅ To'g'ri ({q['answer']})"
        )

    else:
        await query.message.reply_text(
            f"❌ Noto'g'ri ({q['answer']})"
        )

    context.user_data["index"] += 1

    await send_question(update, context)


# =========================
# TEXT HANDLER
# =========================

async def texts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    if is_blocked(user_id):
        return

    # admin panel
    if text == "👑 Admin Panel":
        if not is_admin(user_id):
            return

        await update.message.reply_text(
            "👑 Admin Panel",
            reply_markup=admin_panel()
        )
        return

    # menu
    if text == "🏠 Menu":
        await update.message.reply_text(
            "🏠 Menu",
            reply_markup=main_menu(user_id)
        )
        return

    # test
    if text == "📝 Test ishlash":
        await start_test(update, context)
        return

    # natija
    if text == "📊 Natijam":
        conn = db()
        cur = conn.cursor()

        cur.execute("""
        SELECT tests_count,
               total_score,
               best_score
        FROM users
        WHERE user_id=?
        """, (user_id,))

        row = cur.fetchone()

        conn.close()

        if not row:
            return

        tests, total, best = row

        avg = 0

        if tests > 0:
            avg = round((total / (tests * 30)) * 100, 1)

        msg = (
            f"📊 Natijangiz\n\n"
            f"🧪 Testlar: {tests}\n"
            f"🏆 Eng yaxshi: {best}\n"
            f"📈 O'rtacha: {avg}%"
        )

        await update.message.reply_text(msg)
        return

    # ======================
    # ADMIN FUNKSIYALAR
    # ======================

    if not is_admin(user_id):
        return

    # aktiv users
    if text == "👥 Aktiv userlar":
        conn = db()
        cur = conn.cursor()

        cur.execute("""
        SELECT full_name,
               username,
               user_id,
               tests_count
        FROM users
        ORDER BY tests_count DESC
        LIMIT 30
        """)

        rows = cur.fetchall()

        conn.close()

        if not rows:
            await update.message.reply_text(
                "Userlar yo'q"
            )
            return

        msg = "👥 Aktiv userlar\n\n"

        for i, r in enumerate(rows, start=1):
            msg += (
                f"{i}. {r[0]}\n"
                f"@{r[1]}\n"
                f"ID: {r[2]}\n"
                f"Testlar: {r[3]}\n\n"
            )

        await update.message.reply_text(msg)
        return

    # allow user
    if text.startswith("/allow"):
        try:
            ids = text.replace("/allow", "").strip().split()

            conn = db()
            cur = conn.cursor()

            added = 0

            for uid in ids:
                cur.execute("""
                INSERT OR IGNORE INTO allowed_users
                (user_id)
                VALUES (?)
                """, (int(uid),))

                added += 1

            conn.commit()
            conn.close()

            await update.message.reply_text(
                f"✅ {added} ta user qo'shildi"
            )

        except:
            await update.message.reply_text(
                "❌ Format:\n/allow 123456789"
            )

        return

    # block
    if text.startswith("/block"):
        try:
            ids = text.replace("/block", "").strip().split()

            conn = db()
            cur = conn.cursor()

            blocked = 0

            for uid in ids:
                uid = int(uid)

                if uid == ADMIN_ID:
                    continue

                cur.execute("""
                INSERT OR IGNORE INTO blocked_users
                (user_id)
                VALUES (?)
                """, (uid,))

                blocked += 1

            conn.commit()
            conn.close()

            await update.message.reply_text(
                f"🚫 {blocked} ta user block qilindi"
            )

        except:
            await update.message.reply_text(
                "❌ Format:\n/block 123 456"
            )

        return

    # unblock
    if text.startswith("/unblock"):
        try:
            ids = text.replace("/unblock", "").strip().split()

            conn = db()
            cur = conn.cursor()

            count = 0

            for uid in ids:
                cur.execute("""
                DELETE FROM blocked_users
                WHERE user_id=?
                """, (int(uid),))

                count += 1

            conn.commit()
            conn.close()

            await update.message.reply_text(
                f"✅ {count} ta user unblock qilindi"
            )

        except:
            await update.message.reply_text(
                "❌ Format:\n/unblock 123"
            )

        return

    # block list
    if text == "📋 Block list":
        conn = db()
        cur = conn.cursor()

        cur.execute("""
        SELECT user_id
        FROM blocked_users
        """)

        rows = cur.fetchall()

        conn.close()

        if not rows:
            await update.message.reply_text(
                "🚫 Block list bo'sh"
            )
            return

        msg = "🚫 Block list\n\n"

        for r in rows:
            msg += f"{r[0]}\n"

        await update.message.reply_text(msg)
        return

    # search
    if text.startswith("/search"):
        username = text.replace("/search", "").strip()

        conn = db()
        cur = conn.cursor()

        cur.execute("""
        SELECT full_name,
               username,
               user_id
        FROM users
        WHERE username LIKE ?
        """, (f"%{username}%",))

        rows = cur.fetchall()

        conn.close()

        if not rows:
            await update.message.reply_text(
                "❌ Topilmadi"
            )
            return

        msg = "🔍 Natijalar\n\n"

        for r in rows:
            msg += (
                f"{r[0]}\n"
                f"@{r[1]}\n"
                f"ID: {r[2]}\n\n"
            )

        await update.message.reply_text(msg)
        return


# =========================
# MAIN
# =========================

if __name__ == "__main__":
    init_db()
    load_questions()

    print("🚀 Bot ishlayapti")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(
        CallbackQueryHandler(callbacks)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            texts
        )
    )

    app.run_polling(drop_pending_updates=True)

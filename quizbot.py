import random
import sqlite3
from datetime import datetime, timedelta
from docx import Document

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

TOKEN = "8712005526:AAH-5esSoHp4E5HxrUZKFljEPO7MmWsKysM"
ADMIN_ID = 5183129765


# ================= DB =================
def init_db():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        username TEXT,
        tests INTEGER DEFAULT 0,
        correct INTEGER DEFAULT 0,
        last_active TEXT,
        blocked INTEGER DEFAULT 0,
        allowed INTEGER DEFAULT 0
    )
    """)

    conn.commit()
    conn.close()


def save_user(user):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()

    cur.execute("""
    INSERT OR IGNORE INTO users(user_id,name,username,allowed)
    VALUES(?,?,?,0)
    """, (user.id, user.full_name, user.username))

    conn.commit()
    conn.close()


def check_access(uid):
    if uid == ADMIN_ID:
        return True, ""

    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()

    row = cur.execute(
        "SELECT blocked, allowed FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()
    conn.close()

    if not row:
        return False, "❌ Ruxsat yo‘q"

    blocked, allowed = row

    if blocked:
        return False, "🚫 Blocklangansiz"

    if not allowed:
        return False, "❌ Ruxsat yo‘q"

    return True, ""


# ================= QUESTIONS =================
QUESTIONS = []

def load_questions():
    doc = Document("testlar.docx")
    q, opts = {}, []

    for p in doc.paragraphs:
        t = p.text.strip()
        if not t:
            continue

        if t.startswith("ANSWER:"):
            q["answer"] = t[-1]
            q["opts"] = opts.copy()
            QUESTIONS.append(q.copy())
            q, opts = {}, []
        elif t.startswith(("A)", "B)", "C)", "D)")):
            opts.append(t)
        else:
            q["q"] = t

    print(f"✅ {len(QUESTIONS)} savol yuklandi")


# ================= MENU =================
def menu(uid):
    m = [
        [KeyboardButton("📝 Test boshlash")],
        [KeyboardButton("📊 Natijam")]
    ]

    if uid == ADMIN_ID:
        m.append([KeyboardButton("👑 Admin panel")])

    return ReplyKeyboardMarkup(m, resize_keyboard=True)


# ================= ADMIN DASHBOARD =================
def admin_panel_ui():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Userlar", callback_data="ad_users"),
         InlineKeyboardButton("📊 Statistika", callback_data="ad_stats")],

        [InlineKeyboardButton("🏆 Top 10", callback_data="ad_top"),
         InlineKeyboardButton("📋 Barchasi", callback_data="ad_all")],

        [InlineKeyboardButton("🟢 Aktiv 24h", callback_data="ad_24h"),
         InlineKeyboardButton("🚫 Block list", callback_data="ad_blocklist")],

        [InlineKeyboardButton("🚫 Block", callback_data="ad_block"),
         InlineKeyboardButton("🔓 Unblock", callback_data="ad_unblock")],

        [InlineKeyboardButton("📢 Broadcast", callback_data="ad_broadcast")]
    ])


# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    save_user(user)

    ok, msg = check_access(user.id)
    if not ok:
        await update.message.reply_text(msg)
        return

    await update.message.reply_text("👋 Xush kelibsiz", reply_markup=menu(user.id))


# ================= TEST =================
async def start_test(update: Update, context):
    ok, msg = check_access(update.effective_user.id)
    if not ok:
        await update.message.reply_text(msg)
        return

    context.user_data["quiz"] = random.sample(QUESTIONS, min(30, len(QUESTIONS)))
    context.user_data["i"] = 0
    context.user_data["score"] = 0

    await send_q(update, context)


async def send_q(update, context):
    i = context.user_data["i"]
    quiz = context.user_data["quiz"]

    if i >= len(quiz):
        score = context.user_data["score"]
        uid = update.effective_user.id

        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()

        cur.execute("""
        UPDATE users SET
        tests = tests + 1,
        correct = correct + ?,
        last_active = ?
        WHERE user_id=?
        """, (score, datetime.now().strftime("%Y-%m-%d %H:%M"), uid))

        conn.commit()
        conn.close()

        await update.effective_chat.send_message(f"🏁 Natija: {score}/{len(quiz)}")
        return

    q = quiz[i]
    context.user_data["cur"] = q

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("A", callback_data="A"),
         InlineKeyboardButton("B", callback_data="B")],
        [InlineKeyboardButton("C", callback_data="C"),
         InlineKeyboardButton("D", callback_data="D")]
    ])

    await update.effective_chat.send_message(
        f"{i+1}) {q['q']}\n\n" + "\n".join(q["opts"]),
        reply_markup=kb
    )


# ================= ANSWER =================
async def answer(update: Update, context):
    q = update.callback_query
    await q.answer()

    cur = context.user_data.get("cur")
    if not cur:
        return

    if q.data == cur["answer"]:
        context.user_data["score"] += 1
        await q.message.reply_text("✅ To‘g‘ri")
    else:
        await q.message.reply_text(f"❌ Noto‘g‘ri ({cur['answer']})")

    context.user_data["i"] += 1
    await send_q(update, context)


# ================= STATS =================
async def stats(update: Update, context):
    uid = update.effective_user.id

    conn = sqlite3.connect("bot.db")
    row = conn.execute(
        "SELECT tests, correct, last_active FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("Yo‘q")
        return

    tests, correct, last = row
    foiz = (correct / (tests * 30)) * 100 if tests else 0

    await update.message.reply_text(
        f"📊 Testlar: {tests}\n"
        f"✅ To‘g‘ri: {correct}\n"
        f"📈 {foiz:.1f}%\n"
        f"🕒 {last}"
    )


# ================= ADMIN PANEL =================
async def admin(update: Update, context):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text("👑 Panel", reply_markup=admin_panel_ui())


async def admin_callback(update: Update, context):
    q = update.callback_query
    await q.answer()

    if q.from_user.id != ADMIN_ID:
        return

    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()

    if q.data == "ad_users":
        c = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        await q.message.reply_text(f"👥 Users: {c}")

    elif q.data == "ad_stats":
        total = cur.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        block = cur.execute("SELECT COUNT(*) FROM users WHERE blocked=1").fetchone()[0]
        await q.message.reply_text(f"📊 Total: {total}\n🚫 Block: {block}")

    elif q.data == "ad_top":
        rows = cur.execute("""
            SELECT name, correct FROM users
            ORDER BY correct DESC LIMIT 10
        """).fetchall()

        txt = "🏆 Top 10:\n"
        for i, r in enumerate(rows, 1):
            txt += f"{i}. {r[0]} - {r[1]}\n"

        await q.message.reply_text(txt)

    elif q.data == "ad_all":
        rows = cur.execute("SELECT user_id,name FROM users").fetchall()
        txt = "\n".join([f"{r[0]} - {r[1]}" for r in rows])
        await q.message.reply_text(txt)

    elif q.data == "ad_blocklist":
        rows = cur.execute("SELECT user_id,name FROM users WHERE blocked=1").fetchall()
        txt = "\n".join([f"{r[0]} - {r[1]}" for r in rows])
        await q.message.reply_text(txt or "Bo‘sh")

    elif q.data == "ad_24h":
        rows = cur.execute("""
            SELECT COUNT(*) FROM users
            WHERE last_active >= datetime('now','-1 day')
        """).fetchone()[0]

        await q.message.reply_text(f"🟢 24h: {rows}")


# ================= TEXT =================
async def text(update: Update, context):
    t = update.message.text
    uid = update.effective_user.id

    if t == "📝 Test boshlash":
        await start_test(update, context)

    elif t == "📊 Natijam":
        await stats(update, context)

    elif t == "👑 Admin panel":
        await admin(update, context)


# ================= RUN =================
init_db()
load_questions()

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("admin", admin))
app.add_handler(CallbackQueryHandler(answer, pattern="^[ABCD]$"))
app.add_handler(CallbackQueryHandler(admin_callback, pattern="^ad_"))
app.add_handler(MessageHandler(filters.TEXT, text))

print("🚀 BOT ISHGA TUSHDI")
app.run_polling()

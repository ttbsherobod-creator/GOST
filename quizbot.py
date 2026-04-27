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
    ContextTypes, MessageHandler, filters
)

# ===== SOZLAMALAR =====
TOKEN = "8712005526:AAH-5esSoHp4E5HxrUZKFljEPO7MmWsKysM"
ADMIN_ID = 5183129765

# ===== DB =====
def init_db():
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        name TEXT,
        tests INTEGER DEFAULT 0,
        correct INTEGER DEFAULT 0,
        last_active TEXT,
        blocked INTEGER DEFAULT 0
    )
    """)
    conn.commit()
    conn.close()

def update_user(uid, name, score):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    cur.execute("INSERT OR IGNORE INTO users(user_id,name) VALUES(?,?)",(uid,name))
    cur.execute("""
    UPDATE users SET
    tests = tests+1,
    correct = correct+?,
    last_active=?
    WHERE user_id=?
    """,(score,now,uid))

    conn.commit()
    conn.close()

# ===== SAVOLLAR =====
QUESTIONS = []

def load_questions():
    doc = Document("testlar.docx")
    q, opts = {}, []

    for p in doc.paragraphs:
        t = p.text.strip()
        if not t: continue

        if t.startswith("ANSWER:"):
            q["answer"] = t.replace("ANSWER:","").strip()[0]
            q["opts"] = opts.copy()
            QUESTIONS.append(q.copy())
            q, opts = {}, []
            continue

        if t.startswith(("A)","B)","C)","D)")):
            opts.append(t)
        else:
            q["q"] = t

    print(f"✅ {len(QUESTIONS)} savol yuklandi")

# ===== MENYU =====
def main_menu(uid):
    menu = [
        [KeyboardButton("📝 Test boshlash")],
        [KeyboardButton("📊 Natijalar")]
    ]

    if uid == ADMIN_ID:
        menu.append([KeyboardButton("👑 Admin panel")])

    return ReplyKeyboardMarkup(menu, resize_keyboard=True, is_persistent=True)

# ===== ADMIN PANEL =====
def admin_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Userlar", callback_data="users")],
        [InlineKeyboardButton("📊 Statistika", callback_data="stats")],
        [InlineKeyboardButton("🏆 Top 10", callback_data="top")],
        [InlineKeyboardButton("📁 Barchasi", callback_data="all")],
        [InlineKeyboardButton("🧑‍🤝‍🧑 Aktiv 24h", callback_data="active24")],
        [InlineKeyboardButton("⏰ 7 kun", callback_data="active7")],
        [InlineKeyboardButton("🚫 Block", callback_data="block")],
        [InlineKeyboardButton("📢 Broadcast", callback_data="broadcast")]
    ])

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    await update.message.reply_text("Xush kelibsiz!", reply_markup=main_menu(uid))

# ===== TEST =====
async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    conn = sqlite3.connect("bot.db")
    row = conn.execute("SELECT blocked FROM users WHERE user_id=?", (uid,)).fetchone()
    conn.close()

    if row and row[0] == 1:
        await update.message.reply_text("❌ Siz bloklangansiz")
        return

    context.user_data["quiz"] = random.sample(QUESTIONS, 30)
    context.user_data["i"] = 0
    context.user_data["score"] = 0

    await send_q(update, context)

async def send_q(update, context):
    i = context.user_data["i"]

    if i >= 30:
        score = context.user_data["score"]
        user = update.effective_user
        update_user(user.id, user.full_name, score)

        await update.effective_chat.send_message(
            f"🏁 Natija: {score}/30",
            reply_markup=main_menu(user.id)
        )
        return

    q = context.user_data["quiz"][i]
    context.user_data["cur"] = q

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("A", callback_data="A"),
         InlineKeyboardButton("B", callback_data="B")],
        [InlineKeyboardButton("C", callback_data="C"),
         InlineKeyboardButton("D", callback_data="D")]
    ])

    txt = f"{i+1}) {q['q']}\n\n" + "\n".join(q["opts"])

    await update.effective_chat.send_message(txt, reply_markup=kb)

# ===== JAVOB =====
async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    q = context.user_data.get("cur")
    if not q: return

    await query.edit_message_reply_markup(None)

    if query.data == q["answer"]:
        context.user_data["score"] += 1
        await query.message.reply_text(f"✅ To‘g‘ri ({q['answer']})")
    else:
        await query.message.reply_text(f"❌ Noto‘g‘ri ({q['answer']})")

    context.user_data["i"] += 1
    await send_q(update, context)

# ===== ADMIN =====
async def admin_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    conn = sqlite3.connect("bot.db")

    if q.data == "users":
        c = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        await q.message.reply_text(f"👥 {c} ta user")

    elif q.data == "stats":
        d = conn.execute("SELECT SUM(tests), SUM(correct) FROM users").fetchone()
        await q.message.reply_text(f"📊 Test: {d[0]}\nTo‘g‘ri: {d[1]}")

    elif q.data == "top":
        rows = conn.execute("SELECT name, correct FROM users ORDER BY correct DESC LIMIT 10").fetchall()
        txt = "🏆 TOP 10\n\n"
        for i, r in enumerate(rows, 1):
            txt += f"{i}. {r[0]} - {r[1]}\n"
        await q.message.reply_text(txt)

    elif q.data == "all":
        rows = conn.execute("SELECT name, tests, correct FROM users").fetchall()
        txt = ""
        for r in rows:
            foiz = (r[2]/(r[1]*30))*100 if r[1] > 0 else 0
            txt += f"{r[0]} | {foiz:.1f}%\n"
        await q.message.reply_text(txt[:4000])

    elif q.data == "active24":
        t = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
        rows = conn.execute("SELECT name FROM users WHERE last_active >= ?", (t,)).fetchall()
        await q.message.reply_text(f"🧑‍🤝‍🧑 {len(rows)} aktiv (24h)")

    elif q.data == "active7":
        t = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M")
        rows = conn.execute("SELECT name FROM users WHERE last_active >= ?", (t,)).fetchall()
        await q.message.reply_text(f"⏰ {len(rows)} aktiv (7 kun)")

    elif q.data == "block":
        context.user_data["block"] = True
        await q.message.reply_text("User ID yubor:")

    elif q.data == "broadcast":
        context.user_data["broadcast"] = True
        await q.message.reply_text("Xabar yoz:")

    conn.close()

# ===== TEXT =====
async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    uid = update.effective_user.id

    if t == "📝 Test boshlash":
        await start_test(update, context)

    elif t == "👑 Admin panel" and uid == ADMIN_ID:
        await update.message.reply_text("👑 Panel", reply_markup=admin_menu())

    elif context.user_data.get("block") and uid == ADMIN_ID:
        conn = sqlite3.connect("bot.db")
        conn.execute("UPDATE users SET blocked=1 WHERE user_id=?", (int(t),))
        conn.commit()
        conn.close()
        context.user_data["block"] = False
        await update.message.reply_text("🚫 Block qilindi")

    elif context.user_data.get("broadcast") and uid == ADMIN_ID:
        conn = sqlite3.connect("bot.db")
        users = conn.execute("SELECT user_id FROM users").fetchall()
        conn.close()

        for u in users:
            try:
                await context.bot.send_message(u[0], t)
            except:
                pass

        context.user_data["broadcast"] = False
        await update.message.reply_text("✅ Yuborildi")

# ===== RUN =====
init_db()
load_questions()

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(answer, pattern="^[ABCD]$"))
app.add_handler(CallbackQueryHandler(admin_cb))
app.add_handler(MessageHandler(filters.TEXT, text))

print("🚀 Bot ishlayapti")
app.run_polling()

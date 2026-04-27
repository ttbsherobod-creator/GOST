import random
import sqlite3
from datetime import datetime
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

# ================= DATABASE =================
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


# ================= ACCESS =================
def check_access(uid):
    conn = sqlite3.connect("bot.db")
    cur = conn.cursor()

    row = cur.execute(
        "SELECT blocked, allowed FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()
    conn.close()

    if not row:
        return False, "❌ Siz ro‘yxatdan o‘tmagansiz"

    blocked, allowed = row

    if blocked == 1:
        return False, "🚫 Siz bloklangansiz"

    if allowed != 1 and uid != ADMIN_ID:
        return False, "❌ Sizga ruxsat berilmagan"

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
            q["answer"] = t.replace("ANSWER:", "").strip()[0]
            q["opts"] = opts.copy()
            QUESTIONS.append(q.copy())
            q, opts = {}, []
            continue

        if t.startswith(("A)", "B)", "C)", "D)")):
            opts.append(t)
        else:
            q["q"] = t

    print(f"✅ {len(QUESTIONS)} savol yuklandi")


# ================= MENU =================
def main_menu(uid):
    menu = [
        [KeyboardButton("📝 Test boshlash")],
        [KeyboardButton("📊 Mening natijalarim")]
    ]

    if uid == ADMIN_ID:
        menu.append([KeyboardButton("👑 Admin panel")])

    return ReplyKeyboardMarkup(menu, resize_keyboard=True)


def admin_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("➕ Ruxsat berish")],
        [KeyboardButton("🚫 Block")],
        [KeyboardButton("🔓 Unblock")],
        [KeyboardButton("⬅️ Orqaga")]
    ], resize_keyboard=True)


# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    save_user(user)

    ok, msg = check_access(user.id)
    if not ok and user.id != ADMIN_ID:
        await update.message.reply_text(msg)
        return

    await update.message.reply_text(
        "👋 Xush kelibsiz!",
        reply_markup=main_menu(user.id)
    )


# ================= TEST =================
async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    ok, msg = check_access(update.effective_user.id)
    if not ok:
        await update.message.reply_text(msg)
        return

    if len(QUESTIONS) == 0:
        await update.message.reply_text("❌ Savollar yo‘q")
        return

    context.user_data["quiz"] = random.sample(
        QUESTIONS,
        min(30, len(QUESTIONS))
    )
    context.user_data["i"] = 0
    context.user_data["score"] = 0

    await send_q(update, context)


async def send_q(update, context):
    i = context.user_data["i"]

    if i >= len(context.user_data["quiz"]):
        score = context.user_data["score"]
        user = update.effective_user

        conn = sqlite3.connect("bot.db")
        cur = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        cur.execute("""
        UPDATE users SET
        tests = tests + 1,
        correct = correct + ?,
        last_active = ?
        WHERE user_id = ?
        """, (score, now, user.id))

        conn.commit()
        conn.close()

        await update.effective_chat.send_message(f"🏁 Yakuniy natija: {score}/{len(context.user_data['quiz'])}")
        return

    q = context.user_data["quiz"][i]
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
async def answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    q = context.user_data.get("cur")
    if not q:
        return

    await query.edit_message_reply_markup(None)

    if query.data == q["answer"]:
        context.user_data["score"] += 1
        await query.message.reply_text("✅ To‘g‘ri")
    else:
        await query.message.reply_text(f"❌ Noto‘g‘ri (javob: {q['answer']})")

    context.user_data["i"] += 1
    await send_q(update, context)


# ================= STATS =================
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    conn = sqlite3.connect("bot.db")
    row = conn.execute(
        "SELECT tests, correct, last_active FROM users WHERE user_id=?",
        (uid,)
    ).fetchone()
    conn.close()

    if not row:
        await update.message.reply_text("Statistika yo‘q")
        return

    tests, correct, last = row
    foiz = (correct / (tests * 30)) * 100 if tests else 0

    await update.message.reply_text(
        f"📊 Natijalar:\n\n"
        f"📝 Testlar: {tests}\n"
        f"✅ To‘g‘ri: {correct}\n"
        f"📈 Foiz: {foiz:.1f}%\n"
        f"🕒 Oxirgi: {last}"
    )


# ================= ADMIN =================
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    await update.message.reply_text(
        "👑 Admin panel",
        reply_markup=admin_menu()
    )


async def allow_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    for i in context.args:
        if i.isdigit():
            conn = sqlite3.connect("bot.db")
            conn.execute(
                "UPDATE users SET allowed=1 WHERE user_id=?",
                (int(i),)
            )
            conn.commit()
            conn.close()

    await update.message.reply_text("✅ Ruxsat berildi")


async def block_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    for i in context.args:
        if i.isdigit():
            conn = sqlite3.connect("bot.db")
            conn.execute(
                "UPDATE users SET blocked=1 WHERE user_id=?",
                (int(i),)
            )
            conn.commit()
            conn.close()

    await update.message.reply_text("🚫 Block qilindi")


async def unblock_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    for i in context.args:
        if i.isdigit():
            conn = sqlite3.connect("bot.db")
            conn.execute(
                "UPDATE users SET blocked=0 WHERE user_id=?",
                (int(i),)
            )
            conn.commit()
            conn.close()

    await update.message.reply_text("🔓 Unblock qilindi")


# ================= TEXT HANDLER =================
async def text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    uid = update.effective_user.id

    if t == "📝 Test boshlash":
        await start_test(update, context)

    elif t == "📊 Mening natijalarim":
        await stats(update, context)

    elif t == "👑 Admin panel":
        await admin_panel(update, context)

    elif t == "⬅️ Orqaga":
        await start(update, context)


# ================= RUN =================
init_db()
load_questions()

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("allow", allow_cmd))
app.add_handler(CommandHandler("block", block_cmd))
app.add_handler(CommandHandler("unblock", unblock_cmd))

app.add_handler(CallbackQueryHandler(answer, pattern="^[ABCD]$"))
app.add_handler(MessageHandler(filters.TEXT, text))

print("🚀 Bot ishlayapti")
app.run_polling()

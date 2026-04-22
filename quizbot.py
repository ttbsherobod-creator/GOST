import random
import sqlite3
import asyncio
from datetime import datetime
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

# ===== MA'LUMOTLAR BAZASI =====
def init_db():
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            tests_count INTEGER DEFAULT 0,
            total_score INTEGER DEFAULT 0,
            best_score INTEGER DEFAULT 0,
            last_test TEXT
        )
    """)
    conn.commit()
    conn.close()

def update_user_stats(user_id, username, score):
    conn = sqlite3.connect("bot_data.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%d.%m.%Y %H:%M")

    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username))
    cursor.execute("""
        UPDATE users SET 
        tests_count = tests_count + 1, 
        total_score = total_score + ?, 
        best_score = CASE WHEN ? > best_score THEN ? ELSE best_score END,
        last_test = ? 
        WHERE user_id = ?
    """, (score, score, score, now, user_id))

    conn.commit()
    conn.close()

# ===== TESTLARNI YUKLASH =====
questions = []

def load_questions():
    global questions
    questions.clear()

    try:
        doc = Document("testlar.docx")
        q, opts = {}, []

        for p in doc.paragraphs:
            t = p.text.strip()
            if not t:
                continue

            if t.startswith("ANSWER:"):
                q["answer"] = t.replace("ANSWER:", "").strip()[0]
                q["options"] = opts.copy()
                questions.append(q.copy())
                q, opts = {}, []
                continue

            if t.startswith(("A)", "B)", "C)", "D)")):
                opts.append(t)
            else:
                q["question"] = t

        print(f"✅ Jami {len(questions)} ta savol yuklandi.")

    except Exception as e:
        print(f"❌ Fayl xatosi: {e}")

# ===== TUGMALAR =====
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📝 Test ishlash")],
        [KeyboardButton("📊 Natijalar"), KeyboardButton("💡 Taklif / Savol")]
    ], resize_keyboard=True)

def post_test_buttons(user_id):
    btns = [
        [InlineKeyboardButton("🔄 Yangi test ishlash", callback_data="restart")],
        [InlineKeyboardButton("📊 Mening statistikam", callback_data="my_stats")],
        [InlineKeyboardButton("🏆 Top 10 reyting", callback_data="top_10")]
    ]
    if user_id == ADMIN_ID:
        btns.append([InlineKeyboardButton("👑 Admin panel", callback_data="admin_all")])
    return InlineKeyboardMarkup(btns)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Xush kelibsiz!", reply_markup=main_menu())

# ===== TEST =====
async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(questions) < 1:
        await update.message.reply_text("Savollar topilmadi!")
        return

    context.user_data["quiz"] = random.sample(questions, min(30, len(questions)))
    context.user_data["index"] = 0
    context.user_data["score"] = 0

    await send_next_question(update, context)

async def send_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data["index"]
    quiz = context.user_data["quiz"]

    if idx >= len(quiz):
        score = context.user_data["score"]
        user = update.effective_user

        update_user_stats(user.id, user.full_name, score)

        await update.effective_chat.send_message(
            f"🏁 Test tugadi\nNatija: {score}/30",
            reply_markup=post_test_buttons(user.id)
        )
        return

    q = quiz[idx]
    context.user_data["current"] = q

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("A", callback_data="A"),
         InlineKeyboardButton("B", callback_data="B")],
        [InlineKeyboardButton("C", callback_data="C"),
         InlineKeyboardButton("D", callback_data="D")]
    ])

    text = f"{idx+1}-savol:\n{q['question']}\n\n" + "\n".join(q["options"])

    await update.effective_chat.send_message(text, reply_markup=kb)

# ===== JAVOB =====
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    data = query.data

    if data == "restart":
        await start_test(update, context)
        return

    if data == "my_stats":
        conn = sqlite3.connect("bot_data.db")
        u = conn.execute("SELECT * FROM users WHERE user_id=?", (query.from_user.id,)).fetchone()
        conn.close()

        if u:
            foiz = (u[3] / (u[2] * 30)) * 100 if u[2] else 0
            await query.message.reply_text(f"{u[1]}\nTest: {u[2]}\nFoiz: {foiz:.1f}%")
        return

    if data == "top_10":
        conn = sqlite3.connect("bot_data.db")
        rows = conn.execute("SELECT username,best_score FROM users ORDER BY best_score DESC LIMIT 10").fetchall()
        conn.close()

        text = "TOP 10:\n"
        for i, r in enumerate(rows, 1):
            text += f"{i}. {r[0]} - {r[1]}\n"

        await query.message.reply_text(text)
        return

    if data == "admin_all" and query.from_user.id == ADMIN_ID:
        conn = sqlite3.connect("bot_data.db")
        users = conn.execute("SELECT username,tests_count,total_score FROM users").fetchall()
        conn.close()

        text = "BARCHA FOYDALANUVCHILAR:\n\n"
        for u in users:
            foiz = (u[2] / (u[1] * 30)) * 100 if u[1] else 0
            text += f"{u[0]} | {u[1]} ta | {foiz:.1f}%\n"

        await query.message.reply_text(text)
        return

    # JAVOB TEKSHIRISH
    q = context.user_data.get("current")

    if not q:
        return

    if data == q["answer"]:
        context.user_data["score"] += 1
        await query.message.reply_text("✅ To'g'ri")
    else:
        await query.message.reply_text(f"❌ Noto'g'ri ({q['answer']})")

    context.user_data["index"] += 1
    await send_next_question(update, context)

# ===== TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text

    if t == "📝 Test ishlash":
        await start_test(update, context)

    elif t == "📊 Natijalar":
        await start(update, context)

# ===== RUN =====
if __name__ == "__main__":
    init_db()
    load_questions()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("Bot ishladi")
    app.run_polling()

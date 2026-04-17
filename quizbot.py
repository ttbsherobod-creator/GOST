import random
import sqlite3
import asyncio
import os
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
TOKEN = os.getenv("8499982960:AAH2flAPVGydaRIBbhy_QkWGii0xT3BeM0s")  # ✅ Railway uchun
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
    doc = Document("testlar.docx")
    q, opts = {}, []

    for p in doc.paragraphs:
        t = p.text.strip()
        if not t:
            continue

        if t.startswith("ANSWER:"):
            if "question" in q:
                q["answer"] = t.replace("ANSWER:", "").strip()[0]
                q["options"] = opts.copy()
                questions.append(q.copy())
            q, opts = {}, []
            continue

        if t.startswith(("A)", "B)", "C)", "D)")):
            opts.append(t)
        else:
            q["question"] = t

    print(f"✅ {len(questions)} ta savol yuklandi")

# ===== TUGMALAR =====
def main_menu():
    return ReplyKeyboardMarkup([
        [KeyboardButton("📝 Test ishlash")],
        [KeyboardButton("📊 Natijalar"), KeyboardButton("💡 Taklif / Savol")]
    ], resize_keyboard=True)

def post_test_buttons(user_id):
    btns = [
        [InlineKeyboardButton("🔄 Yangi test", callback_data="restart")],
        [InlineKeyboardButton("📊 Statistika", callback_data="my_stats")],
        [InlineKeyboardButton("🏆 Reyting", callback_data="top_10")]
    ]
    if user_id == ADMIN_ID:
        btns.append([InlineKeyboardButton("👑 Admin Panel", callback_data="admin_all")])
    return InlineKeyboardMarkup(btns)

# ===== START =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Xush kelibsiz!", reply_markup=main_menu())

# ===== TEST BOSHLASH =====
async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["score"] = 0
    context.user_data["index"] = 0
    context.user_data["quiz"] = random.sample(questions, min(30, len(questions)))
    await send_next_question(update, context)

# ===== SAVOL =====
async def send_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data["index"]
    quiz = context.user_data["quiz"]
    target = update.callback_query.message if update.callback_query else update.message

    if idx >= len(quiz):
        score = context.user_data["score"]
        user = update.effective_user
        update_user_stats(user.id, user.full_name, score)

        text = f"🏁 Test tugadi\nNatija: {score}/30"
        await target.reply_text(text, reply_markup=post_test_buttons(user.id))
        return

    q = quiz[idx]
    context.user_data["current"] = q

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("A", callback_data="A"),
         InlineKeyboardButton("B", callback_data="B"),
         InlineKeyboardButton("C", callback_data="C"),
         InlineKeyboardButton("D", callback_data="D")]
    ])

    text = f"{idx+1}-savol:\n{q['question']}\n\n" + "\n".join(q["options"])
    await target.reply_text(text, reply_markup=kb)

# ===== JAVOB =====
async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except:
        pass

    data = query.data
    user_id = update.effective_user.id

    # MENU
    if data == "restart":
        await start_test(update, context)
        return

    conn = sqlite3.connect("bot_data.db")

    if data == "my_stats":
        u = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not u:
            await query.message.reply_text("Hali test ishlamadingiz")
        else:
            foiz = (u[3] / (u[2]*30))*100 if u[2] else 0
            await query.message.reply_text(f"📊 {u[1]}\nTestlar: {u[2]}\nFoiz: {foiz:.1f}%")

        conn.close()
        return

    if data == "top_10":
        rows = conn.execute("SELECT username, best_score FROM users ORDER BY best_score DESC LIMIT 10").fetchall()
        text = "🏆 TOP 10\n\n" + "\n".join([f"{i+1}. {r[0]} — {r[1]}" for i,r in enumerate(rows)])
        await query.message.reply_text(text)
        conn.close()
        return

    if data == "admin_all" and user_id == ADMIN_ID:
        rows = conn.execute("SELECT username, tests_count, total_score FROM users").fetchall()
        text = "👑 ADMIN PANEL\n\n"
        for r in rows:
            foiz = (r[2]/(r[1]*30))*100 if r[1] else 0
            text += f"{r[0]} | {r[1]} test | {foiz:.1f}%\n"

        # uzun bo‘lsa bo‘lib yuboradi
        for i in range(0, len(text), 4000):
            await query.message.reply_text(text[i:i+4000])

        conn.close()
        return

    conn.close()

    # TEST JAVOB
    q = context.user_data.get("current")
    if not q:
        return

    await query.edit_message_reply_markup(None)

    if data == q["answer"]:
        context.user_data["score"] += 1
        await query.message.reply_text("✅ To‘g‘ri")
    else:
        await query.message.reply_text(f"❌ Noto‘g‘ri\nTo‘g‘ri: {q['answer']}")

    context.user_data["index"] += 1
    await send_next_question(update, context)

# ===== TEXT =====
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text

    if t == "📝 Test ishlash":
        await start_test(update, context)

    elif t == "📊 Natijalar":
        await update.message.reply_text("Test tugagach statistika chiqadi")

    elif "Taklif" in t:
        context.user_data["waiting"] = True
        await update.message.reply_text("Yozing:")

    elif context.user_data.get("waiting"):
        await context.bot.send_message(ADMIN_ID, f"{update.effective_user.full_name}:\n{t}")
        await update.message.reply_text("Yuborildi")
        context.user_data["waiting"] = False

# ===== RUN =====
if __name__ == "__main__":
    init_db()
    load_questions()

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("✅ Bot ishga tushdi")
    app.run_polling(drop_pending_updates=True)

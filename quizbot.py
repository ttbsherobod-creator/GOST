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
TOKEN = "8499982960:AAE-a2viqoPFFa-hJzZsU98aj-IKc9yUnWM"
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
    try:
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
    except Exception as e:
        print(f"Baza xatosi: {e}")

# ===== TESTLARNI YUKLASH =====
questions = []
def load_questions():
    try:
        doc = Document("testlar.docx")
        q, opts = {}, []
        for p in doc.paragraphs:
            t = p.text.strip()
            if not t: continue
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
        btns.append([InlineKeyboardButton("👑 Admin: Barcha foydalanuvchilar", callback_data="admin_all")])
    return InlineKeyboardMarkup(btns)

# ===== ASOSIY FUNKSIYALAR =====
async def send_with_retry(func, *args, **kwargs):
    for i in range(3):
        try: return await func(*args, **kwargs)
        except:
            if i == 2: raise
            await asyncio.sleep(1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Xush kelibsiz! Testni boshlash uchun pastdagi tugmani bosing.", reply_markup=main_menu())

async def start_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.update({"score": 0, "index": 0, "quiz": random.sample(questions, min(30, len(questions)))})
    await send_next_question(update, context)

async def send_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data["index"]
    quiz = context.user_data["quiz"]
    target = update.callback_query.message if update.callback_query else update.message

    if idx >= len(quiz):
        score = context.user_data["score"]
        user = update.effective_user
        update_user_stats(user.id, user.full_name, score)
        
        status = "✅ Natija yaxshi" if score >= 20 else "❌ Natija past"
        await send_with_retry(target.reply_text, f"{status}\nSiz 30 tadan {score} ta to'g'ri topdingiz.", reply_markup=post_test_buttons(user.id))
        return

    q = quiz[idx]
    context.user_data["current"] = q
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(ch, callback_data=ch) for ch in ["A", "B", "C", "D"]]])
    txt = f"❓ {idx+1}-savol:\n{q['question']}\n\n" + "\n".join(q["options"])
    await send_with_retry(target.reply_text, txt, reply_markup=kb)

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = update.effective_user.id
    await query.answer()

    if query.data == "restart":
        await start_test(update, context)
        return
    
    conn = sqlite3.connect("bot_data.db")
    if query.data == "my_stats":
        u = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        foiz = (u[3] / (u[2] * 30)) * 100 if u[2] > 0 else 0
        msg = f"📊 Statistika:\n👤 {u[1]}\n🔢 Urinishlar: {u[2]}\n🏆 Jami ball: {u[3]}\n🌟 Rekord: {u[4]}\n📈 O'rtacha: {foiz:.1f}%"
        await query.message.reply_text(msg)
    
    elif query.data == "top_10":
        top = conn.execute("SELECT username, best_score FROM users ORDER BY best_score DESC LIMIT 10").fetchall()
        msg = "🏆 TOP 10 REYTING:\n\n" + "\n".join([f"{i+1}. {r[0]} — {r[1]} ball" for i, r in enumerate(top)])
        await query.message.reply_text(msg)

    elif query.data == "admin_all" and user_id == ADMIN_ID:
        users = conn.execute("SELECT username, tests_count, total_score, best_score, last_test FROM users").fetchall()
        if not users:
            msg = "Foydalanuvchilar hali mavjud emas."
        else:
            msg = "👥 BARCHA FOYDALANUVCHILAR HISOBOTI:\n\n"
            for r in users:
                # Har bir foydalanuvchi uchun foiz hisoblash (jami to'plangan / jami imkoniyat)
                foiz = (r[2] / (r[1] * 30)) * 100 if r[1] > 0 else 0
                msg += (f"👤 {r[0]}\n"
                        f"🔢 Testlar: {r[1]} ta\n"
                        f"📊 O'rtacha natija: {foiz:.1f}%\n"
                        f"🌟 Eng yaxshi ball: {r[3]}\n"
                        f"🕒 Oxirgi faollik: {r[4]}\n"
                        f"----------------------------\n")
        await query.message.reply_text(msg)
    conn.close()

    # Test javoblarini boshqarish
    q = context.user_data.get("current")
    if not q or query.data in ["restart", "my_stats", "top_10", "admin_all"]: return
    
    await query.edit_message_reply_markup(reply_markup=None)
    if query.data == q["answer"]:
        context.user_data["score"] += 1
        await query.message.reply_text(f"✅ To'g'ri (Javob: {q['answer']})")
    else:
        await query.message.reply_text(f"❌ Noto'g'ri (To'g'ri: {q['answer']})")

    context.user_data["index"] += 1
    await send_next_question(update, context)

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    t = update.message.text
    if t == "📝 Test ishlash": await start_test(update, context)
    elif t == "📊 Natijalar":
        await start(update, context) # Menyuni qayta ko'rsatish yoki qisqa info
    elif "Taklif" in t:
        context.user_data["waiting"] = True
        await update.message.reply_text("Xabaringizni yozing:")

if __name__ == "__main__":
    init_db()
    load_questions()
    app = ApplicationBuilder().token(TOKEN).connect_timeout(30).read_timeout(30).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    print("Bot tayyor. Admin panel yangilandi.")
    app.run_polling(drop_pending_updates=True)
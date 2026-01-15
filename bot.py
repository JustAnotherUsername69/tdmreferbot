import sqlite3, datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

# ================= CONFIG =================
BOT_TOKEN = "8566082138:AAGQNIak_kCYaOgchdKZPaDUahpT8In9wJE"
ADMIN_ID = 577188267

CHANNEL_ID = -1001267968308
CHANNEL_INVITE = "https://t.me/+s3SQO0QOY_wwZDQ1"

REDEEM_INSTRUCTIONS = (
    "📌 Coupon Usage Instructions\n"
    "• Minimum order value: ₹100\n"
    "• Valid for NEW BigBasket accounts only\n"
    "• Coupons may show INVALID for old users\n"
    "• One coupon per order\n"
    "• Non-transferable & non-refundable"
)

# ================= DATABASE =================
db = sqlite3.connect("bot.db", check_same_thread=False)
cur = db.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    joined_at TEXT,
    referred_by INTEGER,
    referrals INTEGER DEFAULT 0,
    points INTEGER DEFAULT 0
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE,
    used INTEGER DEFAULT 0,
    used_by INTEGER,
    used_at TEXT
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS coupon_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    code TEXT,
    redeemed_at TEXT
)
""")

db.commit()

# ================= KEYBOARDS =================
def join_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔗 Join Channel", url=CHANNEL_INVITE)],
        [InlineKeyboardButton("✅ I’ve Joined / Refresh", callback_data="refresh")]
    ])

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
        [InlineKeyboardButton("🔗 Refer & Earn", callback_data="refer")],
        [InlineKeyboardButton("💰 Redeem Points", callback_data="redeem")],
        [InlineKeyboardButton("🎁 My Coupons", callback_data="coupons")]
    ])

# ================= HELPERS =================
async def is_subscribed(bot, user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ("member", "administrator", "creator")
    except:
        return False

def reset_mode(context):
    context.user_data.clear()

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    ref = int(args[0]) if args and args[0].isdigit() else None

    if not await is_subscribed(context.bot, user.id):
        await update.message.reply_text(
            "❌ You must join our channel to use this bot.\n\n"
            "After joining, click **I’ve Joined / Refresh**.",
            reply_markup=join_keyboard(),
            parse_mode="Markdown"
        )
        return

    cur.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    exists = cur.fetchone()

    if not exists:
        cur.execute(
            "INSERT INTO users VALUES (?,?,?,?,?,?)",
            (user.id, user.username, datetime.datetime.now(), None, 0, 0)
        )

        if ref and ref != user.id:
            cur.execute("SELECT user_id FROM users WHERE user_id=?", (ref,))
            if cur.fetchone():
                cur.execute(
                    "UPDATE users SET referrals = referrals + 1, points = points + 1 WHERE user_id=?",
                    (ref,)
                )
                cur.execute(
                    "UPDATE users SET referred_by=? WHERE user_id=?",
                    (ref, user.id)
                )

        db.commit()

    reset_mode(context)
    await update.message.reply_text(
        "✅ Welcome to *TDM Referral Rewards Bot*",
        reply_markup=main_menu(),
        parse_mode="Markdown"
    )

# ================= CALLBACKS =================
async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if q.data == "refresh":
        if await is_subscribed(context.bot, uid):
            await q.message.reply_text(
                "✅ Subscription verified!",
                reply_markup=main_menu()
            )
        else:
            await q.message.reply_text(
                "❌ Still not subscribed.",
                reply_markup=join_keyboard()
            )
        return

    if not await is_subscribed(context.bot, uid):
        await q.message.reply_text(
            "❌ You must join our channel to continue.",
            reply_markup=join_keyboard()
        )
        return

    if q.data == "stats":
        reset_mode(context)
        cur.execute("SELECT referrals, points FROM users WHERE user_id=?", (uid,))
        r, p = cur.fetchone()
        await q.message.reply_text(
            f"📊 *Your Stats*\n\n👥 Referrals: {r}\n⭐ Points: {p}",
            parse_mode="Markdown"
        )

    elif q.data == "refer":
        reset_mode(context)
        await q.message.reply_text(
            f"🔗 *Your Referral Link*\n\n"
            f"https://t.me/TDMReferralRewardsBot?start={uid}",
            parse_mode="Markdown"
        )

    elif q.data == "redeem":
        reset_mode(context)
        context.user_data["mode"] = "redeem"
        await q.message.reply_text("Enter number of points you want to redeem:")

    elif q.data == "coupons":
        reset_mode(context)
        cur.execute(
            "SELECT code, redeemed_at FROM coupon_history WHERE user_id=?",
            (uid,)
        )
        rows = cur.fetchall()
        if not rows:
            await q.message.reply_text("❌ No coupons redeemed yet.")
        else:
            msg = "🎁 *Your Coupons*\n\n"
            for c, d in rows:
                msg += f"`{c}` — {d}\n"
            await q.message.reply_text(msg, parse_mode="Markdown")

# ================= TEXT HANDLER (MODE BASED) =================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data or "mode" not in context.user_data:
        return

    uid = update.effective_user.id
    mode = context.user_data.get("mode")
    text = update.message.text.strip()

    # ---------- REDEEM ----------
    if mode == "redeem":
        try:
            pts = int(text)
        except:
            await update.message.reply_text("❌ Please enter a valid number.")
            return

        cur.execute("SELECT points FROM users WHERE user_id=?", (uid,))
        balance = cur.fetchone()[0]

        if pts <= 0 or pts > balance:
            await update.message.reply_text("❌ Invalid points amount.")
            return

        coupons_needed = 12 if pts == 10 else 6 if pts == 5 else pts

        cur.execute("SELECT code FROM coupons WHERE used=0 LIMIT ?", (coupons_needed,))
        codes = cur.fetchall()

        if len(codes) < coupons_needed:
            await update.message.reply_text("❌ Coupons are currently out of stock.")
            reset_mode(context)
            return

        for (code,) in codes:
            cur.execute(
                "UPDATE coupons SET used=1, used_by=?, used_at=? WHERE code=?",
                (uid, datetime.datetime.now(), code)
            )
            cur.execute(
                "INSERT INTO coupon_history VALUES (NULL,?,?,?)",
                (uid, code, datetime.datetime.now())
            )

        cur.execute("UPDATE users SET points = points - ? WHERE user_id=?", (pts, uid))
        db.commit()

        msg = "🎉 *Your Coupons*\n\n"
        for (c,) in codes:
            msg += f"`{c}`\n"
        msg += f"\n\n{REDEEM_INSTRUCTIONS}"

        await update.message.reply_text(msg, parse_mode="Markdown")
        reset_mode(context)

    # ---------- ADD COUPONS (TEXT MODE) ----------
    elif mode == "add_coupons" and uid == ADMIN_ID:
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        added = 0
        for code in lines:
            try:
                cur.execute("INSERT INTO coupons(code) VALUES (?)", (code,))
                added += 1
            except:
                pass
        db.commit()
        await update.message.reply_text(f"✅ Added {added} coupons.")
        reset_mode(context)

# ================= ADMIN COMMANDS =================
async def add_coupons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    reset_mode(context)
    context.user_data["mode"] = "add_coupons"

    if update.message.document:
        file = await update.message.document.get_file()
        content = (await file.download_as_bytearray()).decode()
        lines = [l.strip() for l in content.splitlines() if l.strip()]
        added = 0
        for code in lines:
            try:
                cur.execute("INSERT INTO coupons(code) VALUES (?)", (code,))
                added += 1
            except:
                pass
        db.commit()
        reset_mode(context)
        await update.message.reply_text(f"✅ Added {added} coupons.")
    else:
        await update.message.reply_text(
            "Send coupon codes as text (one per line)\nOR upload a TXT file."
        )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    reset_mode(context)
    context.user_data["mode"] = "broadcast"
    await update.message.reply_text("📣 Send message or media to broadcast.")

async def broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("mode") != "broadcast":
        return

    cur.execute("SELECT user_id FROM users")
    users = cur.fetchall()

    sent, failed = 0, 0
    for (uid,) in users:
        try:
            await update.message.copy(chat_id=uid)
            sent += 1
        except:
            failed += 1

    reset_mode(context)
    await update.message.reply_text(
        f"📣 Broadcast completed\n\n✅ Sent: {sent}\n❌ Failed: {failed}"
    )

# ================= MAIN =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("addcoupons", add_coupons))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CallbackQueryHandler(callbacks))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.ALL, broadcast_send))

app.run_polling()

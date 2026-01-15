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

COUPON_LOG_CHANNEL = -1003516164058
BROADCAST_LOG_CHANNEL = -1003536597909
USER_LOG_CHANNEL = -1003477822786

REDEEM_INSTRUCTIONS = (
    "📌 Coupon Usage Instructions\n"
    "• Minimum order value: ₹100\n"
    "• Valid for NEW BigBasket accounts only\n"
    "• Coupons may show INVALID for old users\n"
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

# ================= HELPERS =================
def reset_mode(context):
    context.user_data.clear()

async def is_subscribed(bot, uid):
    try:
        m = await bot.get_chat_member(CHANNEL_ID, uid)
        return m.status in ("member", "administrator", "creator")
    except:
        return False

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

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    args = context.args
    ref = int(args[0]) if args and args[0].isdigit() else None

    # ✅ ALWAYS REGISTER USER (IMPORTANT FIX)
    cur.execute("SELECT user_id, referred_by FROM users WHERE user_id=?", (user.id,))
    row = cur.fetchone()

    if not row:
        cur.execute(
            "INSERT INTO users VALUES (?,?,?,?,?,?)",
            (user.id, user.username, datetime.datetime.now(), None, 0, 0)
        )
        db.commit()

    # ✅ HANDLE REFERRAL ONLY ON FIRST START
    if ref and ref != user.id:
        cur.execute("SELECT referred_by FROM users WHERE user_id=?", (user.id,))
        already = cur.fetchone()[0]
        if already is None:
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

    # 🔒 SUBSCRIPTION CHECK FOR FEATURES ONLY
    if not await is_subscribed(context.bot, user.id):
        await update.message.reply_text(
            "❌ You must join our channel to use this bot.\n\n"
            "After joining, click **I’ve Joined / Refresh**.",
            reply_markup=join_keyboard(),
            parse_mode="Markdown"
        )
        return

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
            await q.message.reply_text("✅ Subscription verified!", reply_markup=main_menu())
        else:
            await q.message.reply_text("❌ Still not subscribed.", reply_markup=join_keyboard())
        return

    if not await is_subscribed(context.bot, uid):
        await q.message.reply_text("❌ Join channel to continue.", reply_markup=join_keyboard())
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
        cur.execute("SELECT code, redeemed_at FROM coupon_history WHERE user_id=?", (uid,))
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
    text = update.message.text.strip()
    mode = context.user_data.get("mode")

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
            await update.message.reply_text("❌ Invalid points.")
            return

        coupons_needed = 12 if pts == 10 else 6 if pts == 5 else pts
        cur.execute("SELECT code FROM coupons WHERE used=0 LIMIT ?", (coupons_needed,))
        codes = cur.fetchall()

        if len(codes) < coupons_needed:
            await update.message.reply_text("❌ Coupons out of stock.")
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

# ================= ADMIN =================
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM coupons WHERE used=0")
    available = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM coupons WHERE used=1")
    used = cur.fetchone()[0]

    await update.message.reply_text(
        f"📊 *Admin Stats*\n\n"
        f"👥 Users: {users}\n"
        f"🎟 Available Coupons: {available}\n"
        f"✅ Used Coupons: {used}",
        parse_mode="Markdown"
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

    sent = failed = 0
    for (uid,) in users:
        try:
            await update.message.copy(chat_id=uid)
            sent += 1
        except:
            failed += 1

    report = f"📣 Broadcast Done\nSent: {sent}\nFailed: {failed}"
    await update.message.reply_text(report)
    await context.bot.send_message(BROADCAST_LOG_CHANNEL, report)

    reset_mode(context)

# ================= MAIN =================
app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("stats", admin_stats))
app.add_handler(CommandHandler("broadcast", broadcast))
app.add_handler(CallbackQueryHandler(callbacks))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))
app.add_handler(MessageHandler(filters.ALL, broadcast_send))

app.run_polling()

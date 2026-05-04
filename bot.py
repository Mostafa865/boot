# v8.0 - النسخة الاحترافية الكاملة (قوائم منظمة + إحالات متقدمة + مسابقة أسبوعية + مكافأة أول سحب)
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from pymongo import MongoClient
from datetime import datetime, timedelta
import openai
import random
from bson.objectid import ObjectId

TELEGRAM_TOKEN = "8545099923:AAH9ggxKf-BsjiNRpfe0lMouf68Kf0JhWP8"
OPENROUTER_API_KEY = "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"
MONGO_URI = "mongodb+srv://orabiabosenna_db_user:mostafahbn0@cluster0.cwl2dvz.mongodb.net/botdb?appName=Cluster0"
ADMIN_ID = 7825923320
CHANNEL_USERNAME = "@easy_free_1"

# ========== الثوابت ==========
POINTS_PER_USE = 50
POINTS_PER_AD = 100
MAX_ADS_PER_DAY = 10
REFERRAL_WITHDRAWABLE = 3000       # مكافأة مباشر
REFERRAL_LEVEL2 = 500              # مكافأة غير مباشر
REFERRAL_COMMISSION_PERCENT = 10   # عمولة 10% لمدة 30 يوم
POINTS_PER_DOLLAR = 50000
MIN_WITHDRAW_POINTS = 150000
STREAK_MAX_MULTIPLIER = 2.0
STREAK_STEP = 0.05

AD_URL = "https://mostafa865.github.io/boot/ad.html"
BOX_AD_URL = "https://mostafa865.github.io/boot/box_ad.html"

MYSTERY_BOX_PRIZES = [
    (50, "😐 حظك عادي", 50),
    (100, "🙂 مش بطال", 25),
    (200, "😊 كويس", 15),
    (500, "🔥 حظك حلو", 8),
    (1000, "🎉 جاكبوت", 2),
]

mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo["botdb"]
users_col = db["users"]
withdrawals_col = db["withdrawals"]

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

TOPIC, TONE, WEEKLY_TOPIC, BROADCAST_MSG = range(4)

# ========== دوال قاعدة البيانات المتطورة ==========
def get_user(user_id):
    uid = str(user_id)
    user = users_col.find_one({"_id": uid})
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if not user:
        user = {
            "_id": uid,
            "points": 300,
            "withdrawable_points": 0,
            "uses": 0,
            "referrals": 0,
            "referrer_id": None,
            "referral_level2_count": 0,
            "total_commission_earned": 0,
            "has_withdrawn_before": False,
            "first_withdrawal_date": None,
            "tasks": {"ad": False, "used": False, "bonus": False},
            "last_task_date": today,
            "last_box_date": "",
            "ad_watch_today": 0,
            "last_ad_date": "",
            "ad_streak": 0,
            "ad_multiplier": 1.0,
            "last_ad_streak_date": "",
            "weekly_ad_count": 0,
            "last_contest_week": datetime.utcnow().strftime("%Y-%W"),
            "referred_users": [],
            "referral_date": None
        }
        users_col.insert_one(user)
    else:
        updated = False
        for field in ["withdrawable_points", "ad_watch_today", "last_ad_date", "ad_streak", "ad_multiplier", "last_ad_streak_date"]:
            if field not in user:
                user[field] = 0 if field in ["withdrawable_points","ad_watch_today","ad_streak"] else (1.0 if field=="ad_multiplier" else "")
                updated = True
        for field in ["referrer_id", "referral_level2_count", "total_commission_earned", "has_withdrawn_before", "first_withdrawal_date", "weekly_ad_count", "last_contest_week", "referred_users", "referral_date"]:
            if field not in user:
                user[field] = None if field in ["referrer_id","first_withdrawal_date","referral_date"] else (0 if field in ["referral_level2_count","total_commission_earned","weekly_ad_count"] else ([] if field=="referred_users" else False))
                updated = True
        if updated:
            users_col.update_one({"_id": uid}, {"$set": {k: user[k] for k in ["withdrawable_points","ad_watch_today","last_ad_date","ad_streak","ad_multiplier","last_ad_streak_date","referrer_id","referral_level2_count","total_commission_earned","has_withdrawn_before","first_withdrawal_date","weekly_ad_count","last_contest_week","referred_users","referral_date"]}})
    return user

def update_user(user_id, data):
    try:
        uid = str(user_id)
        users_col.update_one({"_id": uid}, {"$set": data}, upsert=True)
    except Exception as e:
        print("Mongo Update Error:", e)

def check_daily_tasks(user):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if "last_task_date" not in user or user["last_task_date"] != today:
        user["tasks"] = {"ad": False, "used": False, "bonus": False}
        user["last_task_date"] = today
    return user

def update_ad_streak(user_id, today):
    user = get_user(user_id)
    last_streak_date = user.get("last_ad_streak_date", "")
    current_streak = user.get("ad_streak", 0)
    if last_streak_date == today:
        return user.get("ad_multiplier", 1.0)
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    if last_streak_date == yesterday:
        current_streak += 1
        if current_streak > 20:
            current_streak = 20
        new_multiplier = min(STREAK_MAX_MULTIPLIER, 1.0 + (current_streak - 1) * STREAK_STEP)
        new_multiplier = round(new_multiplier, 2)
    else:
        current_streak = 1
        new_multiplier = 1.0
    update_user(user_id, {
        "ad_streak": current_streak,
        "ad_multiplier": new_multiplier,
        "last_ad_streak_date": today
    })
    return new_multiplier

def spin_mystery_box():
    total = sum(w for _, _, w in MYSTERY_BOX_PRIZES)
    r = random.randint(1, total)
    current = 0
    for points, msg, weight in MYSTERY_BOX_PRIZES:
        current += weight
        if r <= current:
            return points, msg

# ========== القوائم المنظمة ==========
def main_menu():
    keyboard = [
        [InlineKeyboardButton("✍️ كتابة محتوى", callback_data="content_menu")],
        [InlineKeyboardButton("💰 كسب النقاط", callback_data="earn_menu")],
        [InlineKeyboardButton("👤 حسابي", callback_data="account_menu")],
        [InlineKeyboardButton("🏆 المتصدرين", callback_data="leaderboard")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def content_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📘 بوست فيسبوك", callback_data="facebook"),
         InlineKeyboardButton("📸 كابشن انستجرام", callback_data="instagram")],
        [InlineKeyboardButton("🐦 تويت تويتر", callback_data="twitter"),
         InlineKeyboardButton("💼 بوست لينكدإن", callback_data="linkedin")],
        [InlineKeyboardButton("📧 إيميل احترافي", callback_data="email"),
         InlineKeyboardButton("🎯 إعلان تسويقي", callback_data="ad")],
        [InlineKeyboardButton("✍️ مقال قصير", callback_data="article"),
         InlineKeyboardButton("💡 أفكار محتوى", callback_data="ideas")],
        [InlineKeyboardButton("📅 جدولة محتوى أسبوعي", callback_data="weekly")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]
    ]
    await query.edit_message_text("✍️ *اختر نوع المحتوى:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def earn_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad")],
        [InlineKeyboardButton("🎲 صندوق الحظ", callback_data="mystery_box")],
        [InlineKeyboardButton("📋 مهام اليوم", callback_data="daily_tasks")],
        [InlineKeyboardButton("🎁 دعوة صديق", callback_data="referral")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]
    ]
    await query.edit_message_text("💰 *كسب النقاط*\nاختر طريقة:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def account_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = check_daily_tasks(get_user(user_id))
    withdrawable = user_data.get("withdrawable_points", 0)
    streak = user_data.get("ad_streak", 0)
    multiplier = user_data.get("ad_multiplier", 1.0)
    text = (
        f"👤 *حسابي*\n\n"
        f"✨ نقاط عادية: *{user_data['points']}*\n"
        f"💰 نقاط قابلة للسحب: *{withdrawable}*\n"
        f"✍️ استخدامات: *{user_data['uses']}*\n"
        f"🎁 دعوات مباشرة: *{user_data['referrals']}*\n"
        f"🎁 دعوات غير مباشرة: *{user_data.get('referral_level2_count',0)}*\n"
        f"🔥 Streak: *{streak} يوم* (مضاعف {multiplier}x)\n\n"
        f"📺 كل إعلان: +{POINTS_PER_AD} نقطة × المضاعف (حد {MAX_ADS_PER_DAY}/يوم)\n"
        f"🎁 كل دعوة مباشرة: +{REFERRAL_WITHDRAWABLE} نقطة\n"
        f"🎁 كل دعوة غير مباشرة: +{REFERRAL_LEVEL2} نقطة\n"
        f"💰 عمولة إحالات: {REFERRAL_COMMISSION_PERCENT}% من أرباح المدعو لمدة 30 يوم\n"
        f"💰 التحويل: {POINTS_PER_DOLLAR} نقطة = $1\n"
        f"🏧 الحد الأدنى للسحب: {MIN_WITHDRAW_POINTS} نقطة (${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR})"
    )
    keyboard = [
        [InlineKeyboardButton("💰 سحب النقاط", callback_data="withdraw")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]
    ]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def main_back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = get_user(user_id)
    await query.edit_message_text(
        f"👋 أهلاً *{query.from_user.first_name}*!\n\n"
        f"✨ نقاط عادية: *{user_data['points']}*\n"
        f"💰 نقاط قابلة للسحب: *{user_data.get('withdrawable_points', 0)}*\n\n"
        "👇 اختر من القائمة:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

def tone_menu():
    keyboard = [
        [InlineKeyboardButton("👔 رسمي واحترافي", callback_data="tone_formal"),
         InlineKeyboardButton("😄 مرح وعامي", callback_data="tone_casual")],
        [InlineKeyboardButton("🔥 تسويقي مقنع", callback_data="tone_marketing"),
         InlineKeyboardButton("💬 بسيط ومباشر", callback_data="tone_simple")],
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_menu():
    keyboard = [
        [InlineKeyboardButton("👥 المستخدمون", callback_data="admin_users"),
         InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
        [InlineKeyboardButton("💰 طلبات السحب", callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📢 رسالة جماعية", callback_data="admin_broadcast")],
    ]
    return InlineKeyboardMarkup(keyboard)

# ========== دوال البوت الأساسية ==========
async def check_subscription(user_id, bot):
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    name = user.first_name

    # نظام إحالات متقدم (مستويين)
    if context.args and context.args[0].startswith("ref_"):
        ref_id = context.args[0].replace("ref_", "")
        if ref_id != str(user_id):
            referrer = get_user(int(ref_id))
            new_user = get_user(user_id)
            if new_user.get("referrer_id") is None:
                # حفظ المحيل المباشر
                update_user(user_id, {"referrer_id": int(ref_id), "referral_date": datetime.utcnow().isoformat()})
                # مكافأة المحيل المباشر
                new_withdrawable = referrer["withdrawable_points"] + REFERRAL_WITHDRAWABLE
                update_user(int(ref_id), {
                    "withdrawable_points": new_withdrawable,
                    "referrals": referrer["referrals"] + 1,
                    "referred_users": referrer.get("referred_users", []) + [user_id]
                })
                # إشعار للمحيل المباشر
                try:
                    await context.bot.send_message(
                        int(ref_id),
                        f"🎉 صديق جديد انضم عن طريقك!\nتم إضافة *{REFERRAL_WITHDRAWABLE} نقطة قابلة للسحب* إلى حسابك 💎",
                        parse_mode="Markdown"
                    )
                except:
                    pass
                # معالجة المستوى الثاني (مدعو المحيل)
                upline_id = referrer.get("referrer_id")
                if upline_id:
                    upline = get_user(upline_id)
                    new_withdrawable_upline = upline["withdrawable_points"] + REFERRAL_LEVEL2
                    update_user(upline_id, {
                        "withdrawable_points": new_withdrawable_upline,
                        "referral_level2_count": upline.get("referral_level2_count", 0) + 1
                    })
                    try:
                        await context.bot.send_message(
                            upline_id,
                            f"🎉 مستخدم جديد (غير مباشر) انضم عن طريق أحد المدعوين لديك!\nتم إضافة *{REFERRAL_LEVEL2} نقطة قابلة للسحب*.",
                            parse_mode="Markdown"
                        )
                    except:
                        pass

    if user_id == ADMIN_ID:
        await update.message.reply_text(
            f"👋 أهلاً *{name}* — لوحة الأدمن 🔧",
            parse_mode="Markdown",
            reply_markup=admin_menu()
        )
        return

    user_data = get_user(user_id)
    await update.message.reply_text(
        f"👋 أهلاً *{name}*!\n\n"
        "🤖 أنا بوت كتابة المحتوى الاحترافي\n"
        "بساعدك تكتب محتوى جذاب لأي منصة في ثوانٍ ✨\n\n"
        f"✨ نقاط عادية: *{user_data['points']}*\n"
        f"💰 نقاط قابلة للسحب: *{user_data.get('withdrawable_points', 0)}*\n\n"
        "👇 اختر من القائمة:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

# ========== دوال المكافآت والمحتوى (مع عمولة الإحالات) ==========
async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.message.web_app_data.data
    user_id = update.effective_user.id

    if data == "ad_watched":
        user_data = get_user(user_id)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if user_data.get("last_ad_date") != today:
            update_user(user_id, {"ad_watch_today": 0, "last_ad_date": today})
            user_data["ad_watch_today"] = 0
        if user_data.get("ad_watch_today", 0) >= MAX_ADS_PER_DAY:
            await update.message.reply_text("❌ تجاوزت الحد اليومي للإعلانات.")
            return
        multiplier = update_ad_streak(user_id, today)
        points_earned = int(POINTS_PER_AD * multiplier)
        new_withdrawable = user_data["withdrawable_points"] + points_earned
        new_ad_count = user_data["ad_watch_today"] + 1
        update_user(user_id, {
            "withdrawable_points": new_withdrawable,
            "ad_watch_today": new_ad_count,
            "last_ad_date": today
        })
        # تحديث عداد المسابقة الأسبوعية
        current_week = datetime.utcnow().strftime("%Y-%W")
        if user_data.get("last_contest_week") != current_week:
            update_user(user_id, {"weekly_ad_count": 0, "last_contest_week": current_week})
            user_data["weekly_ad_count"] = 0
        update_user(user_id, {"weekly_ad_count": user_data.get("weekly_ad_count", 0) + 1})
        # عمولة الإحالة للمحيل المباشر (10% لمدة 30 يوم)
        referrer_id = user_data.get("referrer_id")
        if referrer_id:
            referral_date = user_data.get("referral_date")
            if referral_date:
                days_since = (datetime.utcnow() - datetime.fromisoformat(referral_date)).days
                if days_since <= 30:
                    commission = int(points_earned * REFERRAL_COMMISSION_PERCENT / 100)
                    if commission > 0:
                        referrer = get_user(referrer_id)
                        new_commission = referrer["withdrawable_points"] + commission
                        update_user(referrer_id, {
                            "withdrawable_points": new_commission,
                            "total_commission_earned": referrer.get("total_commission_earned", 0) + commission
                        })
                        try:
                            await context.bot.send_message(
                                referrer_id,
                                f"🎁 عمولة إحالة: صديقك شاهد إعلاناً وربحت *{commission} نقطة قابلة للسحب*!",
                                parse_mode="Markdown"
                            )
                        except:
                            pass
        # تحديث المهمة اليومية
        user_data2 = check_daily_tasks(get_user(user_id))
        user_data2["tasks"]["ad"] = True
        update_user(user_id, {"tasks": user_data2["tasks"]})
        await update.message.reply_text(
            f"✅ *تم إضافة {points_earned} نقطة قابلة للسحب!*\n\n"
            f"💎 رصيدك القابل للسحب: *{new_withdrawable}*\n"
            f"🔥 مضاعف اليوم: *{multiplier}x*\n"
            f"📊 إعلانات اليوم: *{new_ad_count}/{MAX_ADS_PER_DAY}*\n"
            f"✨ رصيدك العادي: *{user_data2['points']}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]])
        )
    elif data == "box_ad_watched":
        user_data = get_user(user_id)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if user_data.get("last_box_date") == today:
            await update.message.reply_text("❌ لقد فتحت الصندوق اليوم بالفعل!")
            return
        prize_points, prize_msg = spin_mystery_box()
        new_points = user_data["points"] + prize_points
        update_user(user_id, {"points": new_points, "last_box_date": today})
        await update.message.reply_text(
            f"🎁 *نتيجة صندوق الحظ*\n\n{prize_msg}\n\n🎊 ربحت *{prize_points} نقطة عادية*!\n💎 رصيدك العادي: *{new_points}*\n\nارجع غداً 🔄",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]])
        )

# دوال المحتوى (كما هي من الكود القديم، لم تتغير)
async def handle_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = check_daily_tasks(get_user(user_id))
    update_user(user_id, {"tasks": user_data["tasks"], "last_task_date": user_data["last_task_date"]})
    if user_data["points"] < POINTS_PER_USE:
        await query.message.reply_text(
            f"❌ *نقاطك مش كافية!*\n\nرصيدك: *{user_data['points']}*\nمحتاج: *{POINTS_PER_USE}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad")]])
        )
        return ConversationHandler.END
    platforms = {
        "facebook": "📘 بوست فيسبوك", "instagram": "📸 كابشن انستجرام", "twitter": "🐦 تويت تويتر",
        "linkedin": "💼 بوست لينكدإن", "email": "📧 إيميل احترافي", "ad": "🎯 إعلان تسويقي",
        "article": "✍️ مقال قصير", "ideas": "💡 أفكار محتوى"
    }
    context.user_data['platform'] = platforms[query.data]
    context.user_data['platform_key'] = query.data
    await query.edit_message_text(f"✅ اخترت: *{platforms[query.data]}*\n\n📝 اكتب موضوع المحتوى:", parse_mode="Markdown")
    return TOPIC

async def weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = check_daily_tasks(get_user(user_id))
    if user_data["points"] < POINTS_PER_USE:
        await query.message.reply_text("❌ نقاطك مش كافية!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad")]]))
        return ConversationHandler.END
    await query.edit_message_text("📅 *جدولة أسبوعية*\nاكتب موضوع قناتك:", parse_mode="Markdown")
    return WEEKLY_TOPIC

async def get_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['topic'] = update.message.text
    await update.message.reply_text("🎨 اختار أسلوب الكتابة:", parse_mode="Markdown", reply_markup=tone_menu())
    return TONE

async def get_tone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tones = {"tone_formal": "رسمي", "tone_casual": "عامي", "tone_marketing": "تسويقي", "tone_simple": "مباشر"}
    tone = tones[query.data]
    topic = context.user_data['topic']
    platform_key = context.user_data['platform_key']
    await query.edit_message_text("⏳ بكتبلك المحتوى...")
    user_id = query.from_user.id
    user_data = check_daily_tasks(get_user(user_id))
    user_data["tasks"]["used"] = True
    new_points = user_data["points"] - POINTS_PER_USE
    update_user(user_id, {"points": new_points, "uses": user_data["uses"] + 1, "tasks": user_data["tasks"], "last_task_date": user_data["last_task_date"]})
    prompts = {
        "facebook": f"اكتب بوست فيسبوك عن '{topic}' بأسلوب {tone}.", "instagram": f"اكتب كابشن انستجرام عن '{topic}' بأسلوب {tone}.", "twitter": f"اكتب تويت عن '{topic}' بأسلوب {tone}.",
        "linkedin": f"اكتب بوست لينكدإن عن '{topic}' بأسلوب {tone}.", "email": f"اكتب إيميل عن '{topic}' بأسلوب {tone}.", "ad": f"اكتب إعلان عن '{topic}' بأسلوب {tone}.",
        "article": f"اكتب مقال قصير عن '{topic}' بأسلوب {tone}.", "ideas": f"أعطني 5 أفكار محتوى عن '{topic}'."
    }
    prompt = prompts.get(platform_key, f"اكتب محتوى عن '{topic}' بأسلوب {tone}.")
    try:
        response = client.chat.completions.create(model="gpt-oss-120b", messages=[{"role":"system","content":"أنت كاتب محتوى محترف."},{"role":"user","content":prompt}])
        content = response.choices[0].message.content
        await query.message.reply_text(f"✅ *المحتوى جاهز:*\n\n{content}\n\n━━━━━━━━━━━━━━━\n💎 رصيدك المتبقي: *{new_points}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 محتوى جديد", callback_data="new"), InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    except:
        await query.message.reply_text("❌ حصل خطأ، حاول تاني.")
    return ConversationHandler.END

async def get_weekly_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = update.message.text
    await update.message.reply_text("⏳ جاري الكتابة...")
    user_data = get_user(update.effective_user.id)
    new_points = user_data["points"] - POINTS_PER_USE
    update_user(update.effective_user.id, {"points": new_points, "uses": user_data["uses"] + 1})
    try:
        response = client.chat.completions.create(model="gpt-oss-120b", messages=[{"role":"system","content":"كاتب محتوى محترف."},{"role":"user","content":f"اكتب 7 بوستات تيليجرام مختلفة عن '{topic}'، واحد لكل يوم."}])
        content = response.choices[0].message.content
        await update.message.reply_text(f"✅ *بوستات الأسبوع:*\n\n{content}\n\n💎 رصيدك المتبقي: *{new_points}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 أسبوع جديد", callback_data="weekly"), InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    except:
        await update.message.reply_text("❌ خطأ، حاول تاني.")
    return ConversationHandler.END

# ========== دوال المهام والسحب والمتصدرين والأدمن ==========
async def mystery_box(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = get_user(user_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if user_data.get("last_box_date") == today:
        await query.message.reply_text("❌ فتحت الصندوق اليوم!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
        return
    await query.message.reply_text("🎲 *صندوق الحظ*\n⚠️ شاهد الإعلان أولاً:", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎁 شاهد الإعلان وافتح الصندوق", web_app=WebAppInfo(url=BOX_AD_URL))]]))

async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # تم الاستغناء عنها لوجود account_menu، لكن للحفاظ على التوافق نوجه للـ account_menu
    await account_menu(update, context)

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_username = "easy_free1bot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{query.from_user.id}"
    await query.message.reply_text(f"🎁 *رابط دعوتك:*\n`{ref_link}`\n\nكل صديق يدخل يكسبك {REFERRAL_WITHDRAWABLE} نقطة قابلة للسحب + عمولة 10% لمدة 30 يوم.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="earn_menu")]]))

async def watch_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = get_user(user_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if user_data.get("last_ad_date") != today:
        update_user(user_id, {"ad_watch_today": 0, "last_ad_date": today})
    if user_data.get("ad_watch_today", 0) >= MAX_ADS_PER_DAY:
        await query.message.reply_text(f"❌ الحد اليومي {MAX_ADS_PER_DAY}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
        return
    multiplier = update_ad_streak(user_id, today)
    earn_points = int(POINTS_PER_AD * multiplier)
    await query.message.reply_text(
        f"📺 *شاهد الإعلان*\n🔥 مضاعف اليوم: {multiplier}x\n💰 ستربح: {earn_points} نقطة\n📊 تبقى لك: {MAX_ADS_PER_DAY - user_data['ad_watch_today']} إعلان.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد الإعلان", web_app=WebAppInfo(url=AD_URL))]])
    )

async def daily_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = check_daily_tasks(get_user(query.from_user.id))
    tasks = user_data["tasks"]
    text = f"📋 *مهام اليوم*\n{'✅' if tasks['ad'] else '❌'} شاهد إعلان\n{'✅' if tasks['used'] else '❌'} استخدم البوت\n"
    if tasks["ad"] and tasks["used"] and not tasks["bonus"]:
        text += "\n🎁 يمكنك استلام 300 نقطة بونص!"
        keyboard = [[InlineKeyboardButton("🎁 استلام البونص", callback_data="claim_bonus")]]
    elif tasks["bonus"]:
        text += "\n✅ استلمت البونص!"
        keyboard = [[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]
    else:
        text += "\n🎯 أكمل المهام لتحصل على 300 نقطة!"
        keyboard = [[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def claim_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = check_daily_tasks(get_user(query.from_user.id))
    tasks = user_data["tasks"]
    if tasks["ad"] and tasks["used"] and not tasks["bonus"]:
        new_points = user_data["points"] + 300
        tasks["bonus"] = True
        update_user(query.from_user.id, {"points": new_points, "tasks": tasks})
        await query.message.reply_text(f"🎉 تم إضافة 300 نقطة بونص! رصيدك العادي: {new_points}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
    else:
        await query.message.reply_text("❌ لم تكمل المهام أو استلمت البونص مسبقاً!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))

async def withdraw_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = get_user(user_id)
    withdrawable = user_data.get("withdrawable_points", 0)
    if withdrawable < MIN_WITHDRAW_POINTS:
        need = MIN_WITHDRAW_POINTS - withdrawable
        await query.message.reply_text(f"💰 *السحب*\nرصيدك القابل للسحب: {withdrawable}\nالحد الأدنى: {MIN_WITHDRAW_POINTS} نقطة (${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR})\nتحتاج {need} نقطة إضافية.", parse_mode="Markdown")
        return
    amount_dollars = withdrawable // POINTS_PER_DOLLAR
    points_to_deduct = amount_dollars * POINTS_PER_DOLLAR
    new_withdrawable = withdrawable - points_to_deduct
    update_user(user_id, {"withdrawable_points": new_withdrawable})
    # مكافأة أول سحب
    if not user_data.get("has_withdrawn_before", False):
        update_user(user_id, {"has_withdrawn_before": True, "first_withdrawal_date": datetime.utcnow().isoformat()})
        new_withdrawable += 1000
        update_user(user_id, {"withdrawable_points": new_withdrawable})
        await query.message.reply_text("🎁 هدية أول سحب! +1000 نقطة قابلة للسحب.", parse_mode="Markdown")
    # تسجيل الطلب
    withdrawal_req = {"user_id": user_id, "points_deducted": points_to_deduct, "amount_usd": amount_dollars, "status": "pending", "date": datetime.utcnow().isoformat()}
    db["withdrawals"].insert_one(withdrawal_req)
    await context.bot.send_message(ADMIN_ID, f"💰 *طلب سحب جديد*\nالمستخدم: {query.from_user.first_name}\nID: {user_id}\nالمبلغ: {amount_dollars}$", parse_mode="Markdown")
    await query.message.reply_text(f"💰 تم إرسال طلب سحب {amount_dollars}$. سيتم المراجعة خلال 24-48 ساعة.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))

def get_leaderboard(limit=10):
    cursor = users_col.find({}, {"_id": 1, "points": 1, "withdrawable_points": 1}).sort("points", -1).limit(limit)
    leaderboard = []
    rank = 1
    for user in cursor:
        total = user.get("points", 0) + user.get("withdrawable_points", 0)
        leaderboard.append({"rank": rank, "user_id": user["_id"], "total_points": total})
        rank += 1
    return leaderboard

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = get_leaderboard(10)
    if not data:
        text = "🏆 لا يوجد مستخدمون بعد."
    else:
        text = "🏆 *أفضل 10 مستخدمين*\n"
        for entry in data:
            try:
                user = await context.bot.get_chat(int(entry["user_id"]))
                name = user.first_name
            except:
                name = f"مستخدم {entry['user_id'][-4:]}"
            text += f"{entry['rank']}. {name} — 💎 {entry['total_points']} نقطة\n"
    keyboard = [[InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]
    await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

# ========== دوال الأدمن (طلبات السحب) ==========
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID: return
    total_users = users_col.count_documents({})
    total_uses = sum(u.get("uses",0) for u in users_col.find())
    await query.message.reply_text(f"📊 إجمالي المستخدمين: {total_users}\n✍️ إجمالي الاستخدامات: {total_uses}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]))

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID: return
    total_users = users_col.count_documents({})
    await query.message.reply_text(f"👥 إجمالي المستخدمين: {total_users}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]))

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID: return
    await query.message.reply_text("📢 اكتب الرسالة:")
    return BROADCAST_MSG

async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return ConversationHandler.END
    msg = update.message.text
    success = 0
    for user in users_col.find():
        try:
            await context.bot.send_message(int(user["_id"]), f"📢 *رسالة من الإدارة:*\n\n{msg}", parse_mode="Markdown")
            success += 1
        except:
            pass
    await update.message.reply_text(f"✅ تم الإرسال لـ {success} مستخدم.")
    return ConversationHandler.END

async def admin_withdrawals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID: return
    pending = list(db["withdrawals"].find({"status": "pending"}))
    if not pending:
        await query.message.reply_text("✅ لا توجد طلبات معلقة.")
        return
    text = "💰 *طلبات السحب المعلقة*\n\n"
    keyboard = []
    for req in pending:
        try:
            user = await context.bot.get_chat(req["user_id"])
            name = user.first_name
        except:
            name = f"ID:{req['user_id']}"
        text += f"👤 {name}\n💵 {req['amount_usd']}$ ({req['points_deducted']} نقطة)\n\n"
        req_id = str(req["_id"])
        keyboard.append([InlineKeyboardButton(f"✅ قبول {req['amount_usd']}$", callback_data=f"approve_{req_id}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_{req_id}")])
    keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")])
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def approve_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID: return
    req_id = query.data.split("_")[1]
    withdrawal = db["withdrawals"].find_one({"_id": ObjectId(req_id), "status": "pending"})
    if not withdrawal:
        await query.message.reply_text("الطلب غير موجود.")
        return
    db["withdrawals"].update_one({"_id": ObjectId(req_id)}, {"$set": {"status": "approved"}})
    try:
        await context.bot.send_message(withdrawal["user_id"], f"✅ تمت الموافقة على سحب {withdrawal['amount_usd']}$. سيتم التحويل خلال 24 ساعة.", parse_mode="Markdown")
    except:
        pass
    await query.message.reply_text(f"✅ تمت الموافقة على سحب {withdrawal['amount_usd']}$ وإشعار المستخدم.")
    await query.message.delete()
    await admin_withdrawals(update, context)

async def reject_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID: return
    req_id = query.data.split("_")[1]
    withdrawal = db["withdrawals"].find_one({"_id": ObjectId(req_id), "status": "pending"})
    if not withdrawal:
        await query.message.reply_text("الطلب غير موجود.")
        return
    # إعادة النقاط للمستخدم
    user_data = get_user(withdrawal["user_id"])
    new_withdrawable = user_data.get("withdrawable_points",0) + withdrawal["points_deducted"]
    update_user(withdrawal["user_id"], {"withdrawable_points": new_withdrawable})
    db["withdrawals"].update_one({"_id": ObjectId(req_id)}, {"$set": {"status": "rejected"}})
    try:
        await context.bot.send_message(withdrawal["user_id"], f"❌ تم رفض طلب السحب. تم إعادة {withdrawal['points_deducted']} نقطة إلى رصيدك.", parse_mode="Markdown")
    except:
        pass
    await query.message.reply_text(f"❌ تم رفض الطلب وإعادة {withdrawal['points_deducted']} نقطة.")
    await query.message.delete()
    await admin_withdrawals(update, context)

async def handle_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "admin_back":
        await query.message.reply_text("🔧 لوحة الأدمن:", reply_markup=admin_menu())
    elif query.data in ("home", "new"):
        await main_back(update, context)

# ========== المسابقة الأسبوعية (Job) ==========
async def weekly_contest(context: ContextTypes.DEFAULT_TYPE):
    all_users = users_col.find({})
    stats = []
    for user in all_users:
        count = user.get("weekly_ad_count", 0)
        if count > 0:
            stats.append({"user_id": user["_id"], "count": count})
    stats.sort(key=lambda x: x["count"], reverse=True)
    top10 = stats[:10]
    prizes = [5000, 3000, 1500, 500, 500, 500, 500, 500, 500, 500]
    for idx, entry in enumerate(top10):
        prize = prizes[idx] if idx < len(prizes) else 500
        user_id = int(entry["user_id"])
        user_data = get_user(user_id)
        new_withdrawable = user_data["withdrawable_points"] + prize
        update_user(user_id, {"withdrawable_points": new_withdrawable})
        try:
            await context.bot.send_message(user_id, f"🏆 *المسابقة الأسبوعية*\nالمركز {idx+1} بعدد {entry['count']} إعلان!\n✅ تم إضافة {prize} نقطة قابلة للسحب.", parse_mode="Markdown")
        except:
            pass
    users_col.update_many({}, {"$set": {"weekly_ad_count": 0, "last_contest_week": datetime.utcnow().strftime("%Y-%W")}})
    await context.bot.send_message(ADMIN_ID, "✅ تم توزيع جوائز المسابقة الأسبوعية.")

# ========== تشغيل البوت ==========
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    # إضافة Job للمسابقة (كل إثنين 00:00)
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(weekly_contest, time=datetime.time(hour=0, minute=0), days=(0,))  # 0 = Monday

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_platform, pattern="^(facebook|instagram|twitter|linkedin|email|ad|article|ideas)$"), CallbackQueryHandler(weekly, pattern="^weekly$"), CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")],
        states={TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic)], TONE: [CallbackQueryHandler(get_tone, pattern="^tone_")], WEEKLY_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weekly_topic)], BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)]},
        fallbacks=[CommandHandler('start', start)]
    )
    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(CallbackQueryHandler(content_menu, pattern="^content_menu$"))
    app.add_handler(CallbackQueryHandler(earn_menu, pattern="^earn_menu$"))
    app.add_handler(CallbackQueryHandler(account_menu, pattern="^account_menu$"))
    app.add_handler(CallbackQueryHandler(main_back, pattern="^main_back$"))
    app.add_handler(CallbackQueryHandler(my_account, pattern="^myaccount$"))
    app.add_handler(CallbackQueryHandler(referral, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(watch_ad, pattern="^watch_ad$"))
    app.add_handler(CallbackQueryHandler(mystery_box, pattern="^mystery_box$"))
    app.add_handler(CallbackQueryHandler(daily_tasks, pattern="^daily_tasks$"))
    app.add_handler(CallbackQueryHandler(claim_bonus, pattern="^claim_bonus$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(handle_nav, pattern="^(home|new|admin_back)$"))
    app.add_handler(CallbackQueryHandler(leaderboard, pattern="^leaderboard$"))
    app.add_handler(CallbackQueryHandler(withdraw_request, pattern="^withdraw$"))
    app.add_handler(CallbackQueryHandler(admin_withdrawals, pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(approve_withdraw, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(reject_withdraw, pattern="^reject_"))
    app.run_polling()

if __name__ == '__main__':
    main()

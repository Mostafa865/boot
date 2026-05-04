# v7
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
from pymongo import MongoClient
from datetime import datetime
import openai
import random

TELEGRAM_TOKEN = "8545099923:AAH9ggxKf-BsjiNRpfe0lMouf68Kf0JhWP8"
OPENROUTER_API_KEY = "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"
MONGO_URI = "mongodb+srv://orabiabosenna_db_user:mostafahbn0@cluster0.cwl2dvz.mongodb.net/botdb?appName=Cluster0"
ADMIN_ID = 7825923320
CHANNEL_USERNAME = "@easy_free_1"
POINTS_PER_AD = 200
POINTS_PER_USE = 50
REFERRAL_POINTS = 500
AD_URL = "https://mostafa865.github.io/boot/ad.html"
BOX_AD_URL = "https://mostafa865.github.io/boot/box_ad.html"
# ========== نظام النقاط المزدوج والتحويل ==========
POINTS_PER_AD = 100                # لكل إعلان (نقاط قابلة للسحب)
MAX_ADS_PER_DAY = 10
REFERRAL_WITHDRAWABLE = 3000       # لكل صديق (نقاط قابلة للسحب)
POINTS_PER_DOLLAR = 50000
MIN_WITHDRAW_POINTS = 150000
STREAK_MAX_MULTIPLIER = 2.0
STREAK_STEP = 0.05                 # 5% يومياً



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

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

TOPIC, TONE, WEEKLY_TOPIC, BROADCAST_MSG = range(4)

def get_user(user_id):
    uid = str(user_id)
    user = users_col.find_one({"_id": uid})
    if not user:
        user = {
            "_id": uid,
            "points": 300,
            "withdrawable_points": 0,
            "uses": 0,
            "referrals": 0,
            "tasks": {"ad": False, "used": False, "bonus": False},
            "last_task_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "last_box_date": "",
            "ad_watch_today": 0,
            "last_ad_date": "",
            "ad_streak": 0,
            "ad_multiplier": 1.0,
            "last_ad_streak_date": ""
        }
        users_col.insert_one(user)
    else:
        # التأكد من وجود الحقول الجديدة (للمستخدمين القدامى)
        updated = False
        if "withdrawable_points" not in user:
            user["withdrawable_points"] = 0
            updated = True
        if "ad_watch_today" not in user:
            user["ad_watch_today"] = 0
            updated = True
        if "last_ad_date" not in user:
            user["last_ad_date"] = ""
            updated = True
        if "ad_streak" not in user:
            user["ad_streak"] = 0
            updated = True
        if "ad_multiplier" not in user:
            user["ad_multiplier"] = 1.0
            updated = True
        if "last_ad_streak_date" not in user:
            user["last_ad_streak_date"] = ""
            updated = True
        if updated:
            users_col.update_one({"_id": uid}, {"$set": {
                "withdrawable_points": user["withdrawable_points"],
                "ad_watch_today": user["ad_watch_today"],
                "last_ad_date": user["last_ad_date"],
                "ad_streak": user["ad_streak"],
                "ad_multiplier": user["ad_multiplier"],
                "last_ad_streak_date": user["last_ad_streak_date"]
            }})
    return user


def update_ad_streak(user_id, today):
    """تحديث streak اليومي للمستخدم وإرجاع المضاعف الجديد"""
    user = get_user(user_id)
    last_streak_date = user.get("last_ad_streak_date", "")
    current_streak = user.get("ad_streak", 0)
    
    if last_streak_date == today:
        # شاهد بالفعل اليوم (لا نحدث)
        return user.get("ad_multiplier", 1.0)
    
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    if last_streak_date == yesterday:
        # يوم متتالي
        current_streak += 1
        if current_streak > 20:  # 20 يوم أقصى
            current_streak = 20
        new_multiplier = min(STREAK_MAX_MULTIPLIER, 1.0 + (current_streak - 1) * STREAK_STEP)
        new_multiplier = round(new_multiplier, 2)
    else:
        # بدأ streak جديد
        current_streak = 1
        new_multiplier = 1.0
    
    update_user(user_id, {
        "ad_streak": current_streak,
        "ad_multiplier": new_multiplier,
        "last_ad_streak_date": today
    })
    return new_multiplier



def check_daily_tasks(user):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if "last_task_date" not in user or user["last_task_date"] != today:
        user["tasks"] = {"ad": False, "used": False, "bonus": False}
        user["last_task_date"] = today
    return user

def update_user(user_id, data):
    try:
        uid = str(user_id)
        users_col.update_one({"_id": uid}, {"$set": data}, upsert=True)
    except Exception as e:
        print("Mongo Update Error:", e)

def spin_mystery_box():
    total = sum(w for _, _, w in MYSTERY_BOX_PRIZES)
    r = random.randint(1, total)
    current = 0
    for points, msg, weight in MYSTERY_BOX_PRIZES:
        current += weight
        if r <= current:
            return points, msg

def main_menu():
    keyboard = [
        [InlineKeyboardButton("📘 بوست فيسبوك", callback_data="facebook"),
         InlineKeyboardButton("📸 كابشن انستجرام", callback_data="instagram")],
        [InlineKeyboardButton("🐦 تويت تويتر", callback_data="twitter"),
         InlineKeyboardButton("💼 بوست لينكدإن", callback_data="linkedin")],
        [InlineKeyboardButton("📧 إيميل احترافي", callback_data="email"),
         InlineKeyboardButton("🎯 إعلان تسويقي", callback_data="ad")],
        [InlineKeyboardButton("✍️ مقال قصير", callback_data="article"),
         InlineKeyboardButton("💡 أفكار محتوى", callback_data="ideas")],
        [InlineKeyboardButton("📅 جدولة محتوى أسبوعي 🗓", callback_data="weekly")],
        [InlineKeyboardButton("👤 حسابي", callback_data="myaccount"),
         InlineKeyboardButton("🎁 دعوة صديق", callback_data="referral")],
        [InlineKeyboardButton("📺 شاهد إعلان للنقاط", callback_data="watch_ad"),
         InlineKeyboardButton("🎲 صندوق الحظ", callback_data="mystery_box")],
        [InlineKeyboardButton("📋 مهام اليوم", callback_data="daily_tasks")],
        [InlineKeyboardButton("🏆 المتصدرين", callback_data="leaderboard")],
    ]
    return InlineKeyboardMarkup(keyboard)

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
        [InlineKeyboardButton("📢 رسالة جماعية", callback_data="admin_broadcast")],
    ]
    return InlineKeyboardMarkup(keyboard)

async def check_subscription(user_id, bot):
    return True

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    name = user.first_name

   if context.args and context.args[0].startswith("ref_"):
    ref_id = context.args[0].replace("ref_", "")
    if ref_id != str(user_id):
        ref_data = get_user(int(ref_id))
        new_withdrawable = ref_data["withdrawable_points"] + REFERRAL_WITHDRAWABLE
        update_user(int(ref_id), {
            "withdrawable_points": new_withdrawable,
            "referrals": ref_data["referrals"] + 1
        })
        try:
            await context.bot.send_message(
                int(ref_id),
                f"🎉 صديق جديد انضم عن طريقك!\nتم إضافة *{REFERRAL_WITHDRAWABLE} نقطة قابلة للسحب* إلى حسابك 💎",
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

    is_subscribed = await check_subscription(user_id, context.bot)
    if not is_subscribed:
        await update.message.reply_text(
            f"👋 أهلاً *{name}*!\n\n"
            "⚠️ لازم تشترك في قناتنا الأول عشان تستخدم البوت:\n\n"
            f"📢 {CHANNEL_USERNAME}\n\n"
            "بعد الاشتراك اضغط ✅ تحقق",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📢 اشترك في القناة", url=f"https://t.me/{CHANNEL_USERNAME.replace('@', '')}")],
                [InlineKeyboardButton("✅ تحققت من الاشتراك", callback_data="check_sub")]
            ])
        )
        return

    user_data = get_user(user_id)
    try:
        await context.bot.send_message(
            ADMIN_ID,
            f"👤 مستخدم جديد دخل البوت:\nالاسم: {name}\nID: {user_id}"
        )
    except:
        pass

    await update.message.reply_text(
        f"👋 أهلاً *{name}*!\n\n"
        "🤖 أنا بوت كتابة المحتوى الاحترافي\n"
        "بساعدك تكتب محتوى جذاب لأي منصة في ثوانٍ ✨\n\n"
        f"💎 رصيد نقاطك: *{user_data['points']} نقطة*\n\n"
        "👇 اختار نوع المحتوى اللي عايزه:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

async def check_sub_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = query.from_user
    is_subscribed = await check_subscription(user.id, context.bot)
    if is_subscribed:
        user_data = get_user(user.id)
        await query.edit_message_text(
            f"✅ تم التحقق!\n\n"
            "🤖 أنا بوت كتابة المحتوى الاحترافي\n"
            "بساعدك تكتب محتوى جذاب لأي منصة في ثوانٍ ✨\n\n"
            f"💎 رصيد نقاطك: *{user_data['points']} نقطة*\n\n"
            "👇 اختار نوع المحتوى اللي عايزه:",
            parse_mode="Markdown",
            reply_markup=main_menu()
        )
    else:
        await query.answer("❌ لسه مشتركتش في القناة!", show_alert=True)

async def mystery_box(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = get_user(user_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # منع التكرار في نفس اليوم
    if user_data.get("last_box_date") == today:
        await query.message.reply_text(
            "🎲 *صندوق الحظ*\n\n"
            "❌ فتحت الصندوق النهارده بالفعل!\n"
            "ارجع بكره عشان تفتحه تاني 😊",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 القائمة", callback_data="home")]
            ])
        )
        return

    # عرض زر فتح الصندوق عبر WebApp (الإعلان)
    await query.message.reply_text(
        "🎲 *صندوق الحظ*\n\n"
        "⚠️ شاهد الإعلان أولاً، ثم سيتم فتح الصندوق تلقائياً.\n"
        "اضغط الزر أدناه 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🎁 شاهد الإعلان وافتح الصندوق", web_app=WebAppInfo(url=BOX_AD_URL))]
        ])
    )

async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = check_daily_tasks(get_user(query.from_user.id))
    update_user(query.from_user.id, {"tasks": user_data["tasks"], "last_task_date": user_data["last_task_date"]})
    
    withdrawable = user_data.get("withdrawable_points", 0)
    streak = user_data.get("ad_streak", 0)
    multiplier = user_data.get("ad_multiplier", 1.0)
    
    await query.message.reply_text(
        f"👤 *حسابي*\n\n"
        f"✨ نقاط عادية (للاستخدام): *{user_data['points']} نقطة*\n"
        f"💰 نقاط قابلة للسحب: *{withdrawable} نقطة*\n"
        f"✍️ الاستخدامات: *{user_data['uses']} مرة*\n"
        f"🎁 الدعوات: *{user_data['referrals']} صديق*\n"
        f"🔥 Streek: *{streak} يوم* (مضاعف {multiplier}x)\n\n"
        f"📺 كل إعلان: +{POINTS_PER_AD} نقطة قابلة للسحب × المضاعف (حد {MAX_ADS_PER_DAY}/يوم)\n"
        f"🎁 كل دعوة: +{REFERRAL_WITHDRAWABLE} نقطة قابلة للسحب\n"
        f"🎲 صندوق الحظ والمهام: نقاط عادية فقط\n\n"
        f"💰 التحويل: {POINTS_PER_DOLLAR} نقطة قابلة للسحب = $1\n"
        f"🏧 الحد الأدنى للسحب: {MIN_WITHDRAW_POINTS} نقطة (${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR})",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💰 سحب النقاط", callback_data="withdraw")],
            [InlineKeyboardButton("🏠 القائمة", callback_data="home")]
        ])
    )


async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    bot_username = "easy_free1bot"
    ref_link = f"https://t.me/{bot_username}?start=ref_{query.from_user.id}"
    await query.message.reply_text(
        "🎁 *دعوة صديق*\n\n"
        "شارك الرابط ده مع أصحابك:\n\n"
        f"`{ref_link}`\n\n"
        f"كل صديق بيدخل عن طريقك بتكسب *{REFERRAL_POINTS} نقطة* 🎉",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 القائمة", callback_data="home")]
        ])
    )

async def watch_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = get_user(user_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    # إعادة ضبط عداد اليوم إذا تغير اليوم
    if user_data.get("last_ad_date") != today:
        update_user(user_id, {"ad_watch_today": 0, "last_ad_date": today})
        user_data["ad_watch_today"] = 0
    
    if user_data.get("ad_watch_today", 0) >= MAX_ADS_PER_DAY:
        await query.message.reply_text(
            f"📺 *شاهد إعلان*\n\n"
            f"❌ لقد شاهدت *{MAX_ADS_PER_DAY}* إعلاناً اليوم، الحد الأقصى.\n"
            "ارجع غداً لمشاهدة المزيد وكسب نقاط قابلة للسحب.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 القائمة", callback_data="home")]
            ])
        )
        return
    
    # حساب المضاعف الحالي
    multiplier = update_ad_streak(user_id, today)
    earn_points = int(POINTS_PER_AD * multiplier)
    
    await query.message.reply_text(
        f"📺 *شاهد الإعلان عشان تكسب نقاط قابلة للسحب!*\n\n"
        f"🔥 مضاعف اليوم: *{multiplier}x*\n"
        f"💰 ستربح: *{earn_points} نقطة*\n"
        f"📊 تبقى لك اليوم: *{MAX_ADS_PER_DAY - user_data['ad_watch_today']}* إعلاناً.\n\n"
        "اضغط الزر وشوف الإعلان كامل.\n"
        "النقاط هتتضاف تلقائياً بعد المشاهدة ✅",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 شاهد الإعلان", web_app=WebAppInfo(url=AD_URL))],
        ])
    )

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = update.message.web_app_data.data
    print(f"📨 WebApp data received: {data}")
    user_id = update.effective_user.id

   if data == "ad_watched":
    user_data = get_user(user_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    
    # إعادة ضبط العداد إذا تغير اليوم
    if user_data.get("last_ad_date") != today:
        update_user(user_id, {"ad_watch_today": 0, "last_ad_date": today})
        user_data["ad_watch_today"] = 0
    
    # التحقق من الحد الأقصى
    if user_data.get("ad_watch_today", 0) >= MAX_ADS_PER_DAY:
        await update.message.reply_text("❌ تجاوزت الحد اليومي للإعلانات.")
        return
    
    # تحديث الـ streak والمضاعف
    multiplier = update_ad_streak(user_id, today)
    points_earned = int(POINTS_PER_AD * multiplier)
    
    new_withdrawable = user_data["withdrawable_points"] + points_earned
    new_ad_count = user_data["ad_watch_today"] + 1
    
    update_user(user_id, {
        "withdrawable_points": new_withdrawable,
        "ad_watch_today": new_ad_count,
        "last_ad_date": today
    })
    
    # تحديث المهمة اليومية (نقاط عادية)
    user_data = check_daily_tasks(get_user(user_id))
    user_data["tasks"]["ad"] = True
    update_user(user_id, {"tasks": user_data["tasks"]})
    
    await update.message.reply_text(
        f"✅ *تم إضافة {points_earned} نقطة قابلة للسحب!*\n\n"
        f"💎 رصيدك القابل للسحب: *{new_withdrawable} نقطة*\n"
        f"🔥 مضاعف اليوم: *{multiplier}x*\n"
        f"📊 عدد إعلانات اليوم: *{new_ad_count}/{MAX_ADS_PER_DAY}*\n\n"
        f"✨ رصيدك العادي (للاستخدام): *{user_data['points']} نقطة*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 القائمة", callback_data="home")]
        ])
    )

    elif data == "box_ad_watched":
        user_data = get_user(user_id)
        today = datetime.utcnow().strftime("%Y-%m-%d")

        if user_data.get("last_box_date") == today:
            await update.message.reply_text("❌ لقد فتحت الصندوق اليوم بالفعل!")
            return

        prize_points, prize_msg = spin_mystery_box()
        new_points = user_data["points"] + prize_points

        update_user(user_id, {
            "points": new_points,
            "last_box_date": today
        })

        await update.message.reply_text(
            f"🎁 *نتيجة صندوق الحظ*\n\n"
            f"{prize_msg}\n\n"
            f"🎊 ربحت *{prize_points} نقطة*!\n"
            f"💎 رصيدك الحالي: *{new_points} نقطة*\n\n"
            f"ارجع بكره عشان تفتح الصندوق تاني! 🔄",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 القائمة", callback_data="home")]
            ])
        )
async def handle_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = check_daily_tasks(get_user(user_id))
    update_user(user_id, {"tasks": user_data["tasks"], "last_task_date": user_data["last_task_date"]})

    if user_data["points"] < POINTS_PER_USE:
        await query.message.reply_text(
            f"❌ *نقاطك مش كافية!*\n\n"
            f"💎 رصيدك: *{user_data['points']} نقطة*\n"
            f"محتاج: *{POINTS_PER_USE} نقطة*\n\n"
            "📺 شاهد إعلان واكسب نقاط عشان تكمل!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad"),
                 InlineKeyboardButton("🎲 صندوق الحظ", callback_data="mystery_box")]
            ])
        )
        return ConversationHandler.END

    platforms = {
        "facebook": "📘 بوست فيسبوك",
        "instagram": "📸 كابشن انستجرام",
        "twitter": "🐦 تويت تويتر",
        "linkedin": "💼 بوست لينكدإن",
        "email": "📧 إيميل احترافي",
        "ad": "🎯 إعلان تسويقي",
        "article": "✍️ مقال قصير",
        "ideas": "💡 أفكار محتوى",
    }

    context.user_data['platform'] = platforms[query.data]
    context.user_data['platform_key'] = query.data

    await query.edit_message_text(
        f"✅ اخترت: *{platforms[query.data]}*\n\n"
        "📝 دلوقتي اكتبلي *موضوع أو فكرة* المحتوى:",
        parse_mode="Markdown"
    )
    return TOPIC

async def weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = check_daily_tasks(get_user(user_id))
    update_user(user_id, {"tasks": user_data["tasks"], "last_task_date": user_data["last_task_date"]})

    if user_data["points"] < POINTS_PER_USE:
        await query.message.reply_text(
            f"❌ *نقاطك مش كافية!*\n\n"
            f"💎 رصيدك: *{user_data['points']} نقطة*\n\n"
            "📺 شاهد إعلان واكسب نقاط!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad")]
            ])
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "📅 *جدولة أسبوعية*\n\n"
        "اكتبلي موضوع قناتك وهطلعلك 7 بوستات جاهزة لأسبوع كامل:",
        parse_mode="Markdown"
    )
    return WEEKLY_TOPIC

async def get_weekly_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic = update.message.text
    await update.message.reply_text("⏳ بكتبلك 7 بوستات... انتظر شوية!")
    user_data = get_user(update.effective_user.id)
    new_points = user_data["points"] - POINTS_PER_USE
    update_user(update.effective_user.id, {"points": new_points, "uses": user_data["uses"] + 1})
    try:
        response = client.chat.completions.create(
            model="gpt-oss-120b",
            messages=[
                {"role": "system", "content": "أنت كاتب محتوى محترف. اكتب باللغة العربية فقط."},
                {"role": "user", "content": f"اكتبلي 7 بوستات تيليجرام مختلفة عن موضوع '{topic}' — واحد لكل يوم في الأسبوع. كل بوست يكون جذاب ومختلف عن التاني مع إيموجي مناسبة."}
            ]
        )
        content = response.choices[0].message.content
        await update.message.reply_text(
            f"✅ *بوستات الأسبوع جاهزة:*\n\n{content}\n\n"
            f"💎 رصيد نقاطك المتبقي: *{new_points} نقطة*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 أسبوع جديد", callback_data="weekly"),
                 InlineKeyboardButton("🏠 القائمة", callback_data="home")]
            ])
        )
    except Exception:
        await update.message.reply_text(
            "❌ حصل خطأ، حاول تاني بعد شوية.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 حاول تاني", callback_data="home")]
            ])
        )
    return ConversationHandler.END

async def get_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['topic'] = update.message.text
    await update.message.reply_text(
        "🎨 اختار *أسلوب* الكتابة:",
        parse_mode="Markdown",
        reply_markup=tone_menu()
    )
    return TONE

async def get_tone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    tones = {
        "tone_formal": "رسمي واحترافي",
        "tone_casual": "مرح وعامي",
        "tone_marketing": "تسويقي مقنع",
        "tone_simple": "بسيط ومباشر",
    }

    tone = tones[query.data]
    topic = context.user_data['topic']
    platform_key = context.user_data['platform_key']

    await query.edit_message_text("⏳ بكتبلك المحتوى... انتظر ثانية!")

    user_id = query.from_user.id
    user_data = check_daily_tasks(get_user(user_id))
    user_data["tasks"]["used"] = True
    new_points = user_data["points"] - POINTS_PER_USE
    update_user(user_id, {
        "points": new_points,
        "uses": user_data["uses"] + 1,
        "tasks": user_data["tasks"],
        "last_task_date": user_data["last_task_date"]
    })

    prompts = {
        "facebook": f"اكتب بوست فيسبوك احترافي عن '{topic}' بأسلوب {tone}. يكون جذاب ومحفز على التفاعل مع إيموجي مناسبة.",
        "instagram": f"اكتب كابشن انستجرام مميز عن '{topic}' بأسلوب {tone}. يشمل هاشتاقات مناسبة وإيموجي.",
        "twitter": f"اكتب تويت مختصر وجذاب عن '{topic}' بأسلوب {tone}. في حدود 280 حرف.",
        "linkedin": f"اكتب بوست لينكدإن احترافي عن '{topic}' بأسلوب {tone}. يكون مفيد ويبرز الخبرة.",
        "email": f"اكتب إيميل احترافي عن '{topic}' بأسلوب {tone}. يشمل subject line وجسم الإيميل.",
        "ad": f"اكتب إعلان تسويقي مقنع عن '{topic}' بأسلوب {tone}. يشمل headline وbody وcall to action.",
        "article": f"اكتب مقال قصير ومفيد عن '{topic}' بأسلوب {tone}. يشمل مقدمة ونقاط رئيسية وخاتمة.",
        "ideas": f"قدملي 5 أفكار محتوى مميزة ومختلفة عن موضوع '{topic}' مناسبة لسوشيال ميديا.",
    }

    prompt = prompts.get(platform_key, f"اكتب محتوى عن '{topic}' بأسلوب {tone}.")

    try:
        response = client.chat.completions.create(
            model="gpt-oss-120b",
            messages=[
                {"role": "system", "content": "أنت كاتب محتوى محترف ومتخصص في السوشيال ميديا. اكتب محتوى باللغة العربية فقط."},
                {"role": "user", "content": prompt}
            ]
        )
        content = response.choices[0].message.content
        await query.message.reply_text(
            f"✅ *المحتوى جاهز:*\n\n{content}\n\n"
            "━━━━━━━━━━━━━━━\n"
            f"💎 رصيد نقاطك المتبقي: *{new_points} نقطة*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 محتوى جديد", callback_data="new"),
                 InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")]
            ])
        )
    except Exception:
        await query.message.reply_text(
            "❌ حصل خطأ، حاول تاني بعد شوية.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 حاول تاني", callback_data="home")]
            ])
        )

    return ConversationHandler.END

async def daily_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = check_daily_tasks(get_user(user_id))
    tasks = user_data["tasks"]

    ad_status = "✅" if tasks["ad"] else "❌"
    used_status = "✅" if tasks["used"] else "❌"

    text = (
        "📋 *مهام اليوم*\n\n"
        f"{ad_status} شاهد إعلان (+200 نقطة)\n"
        f"{used_status} استخدم البوت مرة\n\n"
    )

    if tasks["ad"] and tasks["used"] and not tasks["bonus"]:
        text += "🎁 يمكنك استلام 300 نقطة بونص!"
        keyboard = [[InlineKeyboardButton("🎁 استلام البونص", callback_data="claim_bonus")]]
    elif tasks["bonus"]:
        text += "✅ استلمت البونص النهارده!"
        keyboard = [[InlineKeyboardButton("🏠 القائمة", callback_data="home")]]
    else:
        text += "🎯 أكمل المهام وخد 300 نقطة بونص!"
        keyboard = [[InlineKeyboardButton("🏠 القائمة", callback_data="home")]]

    await query.message.reply_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def claim_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = check_daily_tasks(get_user(user_id))
    tasks = user_data["tasks"]

    if tasks["ad"] and tasks["used"] and not tasks["bonus"]:
        new_points = user_data["points"] + 300
        tasks["bonus"] = True
        update_user(user_id, {"points": new_points, "tasks": tasks})
        await query.message.reply_text(
            f"🎉 *مبروك! تم إضافة 300 نقطة بونص!*\n\n"
            f"💎 رصيدك الحالي: *{new_points} نقطة*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏠 القائمة", callback_data="home")]
            ])
        )
    else:
        await query.message.reply_text("❌ لازم تكمل المهام الأول أو استلمت البونص قبل كده!")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    total_users = users_col.count_documents({})
    total_uses = sum(u.get("uses", 0) for u in users_col.find())
    await query.message.reply_text(
        f"📊 *الإحصائيات*\n\n"
        f"👥 إجمالي المستخدمين: *{total_users}*\n"
        f"✍️ إجمالي الاستخدامات: *{total_uses}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
        ])
    )

async def admin_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    total_users = users_col.count_documents({})
    await query.message.reply_text(
        f"👥 *المستخدمون*\n\n"
        f"إجمالي: *{total_users} مستخدم*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]
        ])
    )

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    await query.message.reply_text("📢 اكتب الرسالة اللي عايز تبعتها لكل المستخدمين:")
    return BROADCAST_MSG

async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
    msg = update.message.text
    success = 0
    for user in users_col.find():
        try:
            await context.bot.send_message(int(user["_id"]), f"📢 *رسالة من الإدارة:*\n\n{msg}", parse_mode="Markdown")
            success += 1
        except:
            pass
    await update.message.reply_text(f"✅ تم إرسال الرسالة لـ *{success}* مستخدم!", parse_mode="Markdown")
    return ConversationHandler.END

async def handle_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "admin_back":
        await query.message.reply_text("🔧 لوحة الأدمن:", reply_markup=admin_menu())
    else:
        await query.message.reply_text(
            "👇 اختار نوع المحتوى اللي عايزه:",
            reply_markup=main_menu()
        )

def get_leaderboard(limit=10):
    """جلب أفضل المستخدمين حسب النقاط من قاعدة البيانات"""
    cursor = users_col.find({}, {"_id": 1, "points": 1}).sort("points", -1).limit(limit)
    leaderboard = []
    rank = 1
    for user in cursor:
        leaderboard.append({
            "rank": rank,
            "user_id": user["_id"],
            "points": user.get("points", 0)
        })
        rank += 1
    return leaderboard

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    leaderboard_data = get_leaderboard(10)
    
    if not leaderboard_data:
        text = "🏆 *الترتيب*\n\nلا يوجد مستخدمون بعد. ابدأ باستخدام البوت لتظهر هنا! 🚀"
    else:
        text = "🏆 *أفضل 10 مستخدمين*\n\n"
        for entry in leaderboard_data:
            user_id = int(entry["user_id"])
            # حاول جلب اسم المستخدم
            try:
                user = await context.bot.get_chat(user_id)
                name = user.first_name
            except Exception:
                name = f"مستخدم {entry['user_id'][-4:]}"
            
            text += f"{entry['rank']}. {name} — 💎 {entry['points']} نقطة\n"
    
    keyboard = [[InlineKeyboardButton("🏠 القائمة", callback_data="home")]]
    await query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))



async def withdraw_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_data = get_user(user_id)
    withdrawable = user_data.get("withdrawable_points", 0)
    
    if withdrawable < MIN_WITHDRAW_POINTS:
        need = MIN_WITHDRAW_POINTS - withdrawable
        await query.message.reply_text(
            f"💰 *تحويل النقاط لفلوس*\n\n"
            f"رصيدك القابل للسحب: *{withdrawable} نقطة*\n"
            f"الحد الأدنى للسحب: *{MIN_WITHDRAW_POINTS} نقطة* (يعني {MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR}$)\n\n"
            f"تحتاج *{need} نقطة* إضافية.\n"
            f"شاهد إعلانات أو ادعو أصدقاء لتجميع نقاط السحب.",
            parse_mode="Markdown"
        )
        return
    
    amount_dollars = withdrawable // POINTS_PER_DOLLAR
    points_to_deduct = amount_dollars * POINTS_PER_DOLLAR
    new_withdrawable = withdrawable - points_to_deduct
    update_user(user_id, {"withdrawable_points": new_withdrawable})
    
    withdrawal_req = {
        "user_id": user_id,
        "points_deducted": points_to_deduct,
        "amount_usd": amount_dollars,
        "status": "pending",
        "date": datetime.utcnow().isoformat()
    }
    db["withdrawals"].insert_one(withdrawal_req)
    
    await context.bot.send_message(
        ADMIN_ID,
        f"💰 *طلب سحب جديد*\n\n"
        f"المستخدم: {query.from_user.first_name}\nID: `{user_id}`\n"
        f"المبلغ: {amount_dollars}$\n"
        f"التاريخ: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        parse_mode="Markdown"
    )
    
    await query.message.reply_text(
        f"💰 *تم إرسال طلب السحب بنجاح!*\n\n"
        f"المبلغ المطلوب: *{amount_dollars}$*\n"
        f"تم خصم {points_to_deduct} نقطة من رصيدك القابل للسحب.\n"
        f"سيتم المراجعة خلال 24-48 ساعة.\n\n"
        f"شكراً لك!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 القائمة", callback_data="home")]
        ])
    )


def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(handle_platform, pattern="^(facebook|instagram|twitter|linkedin|email|ad|article|ideas)$"),
            CallbackQueryHandler(weekly, pattern="^weekly$"),
            CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$"),
        ],
        states={
            TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic)],
            TONE: [CallbackQueryHandler(get_tone, pattern="^tone_")],
            WEEKLY_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weekly_topic)],
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
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

    app.run_polling()

if __name__ == '__main__':
    main()

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
            "uses": 0,
            "referrals": 0,
            "tasks": {"ad": False, "used": False, "bonus": False},
            "last_task_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "last_box_date": ""
        }
        users_col.insert_one(user)
    return user

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
            new_points = ref_data["points"] + REFERRAL_POINTS
            update_user(int(ref_id), {"points": new_points, "referrals": ref_data["referrals"] + 1})
            try:
                await context.bot.send_message(
                    int(ref_id),
                    f"🎉 صديق جديد انضم عن طريقك!\nتم إضافة *{REFERRAL_POINTS} نقطة* لحسابك 💎",
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
    await query.message.reply_text(
        f"👤 *حسابي*\n\n"
        f"💎 النقاط: *{user_data['points']} نقطة*\n"
        f"✍️ الاستخدامات: *{user_data['uses']} مرة*\n"
        f"🎁 الدعوات: *{user_data['referrals']} صديق*\n\n"
        f"كل استخدام بيتخصم {POINTS_PER_USE} نقطة\n"
        f"شاهد إعلان واكسب {POINTS_PER_AD} نقطة 📺\n"
        f"دعوة صديق واكسب {REFERRAL_POINTS} نقطة 🎁\n"
        f"صندوق الحظ يومياً 🎲",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
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
    await query.message.reply_text(
        "📺 *شاهد الإعلان عشان تكسب نقاط!*\n\n"
        "اضغط الزر وشوف الإعلان كامل\n"
        "النقاط هتتضاف تلقائي بعد المشاهدة ✅",
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
        # ... الكود الموجود بالفعل ...
        pass

    elif data == "box_ad_watched":
        user_data = get_user(user_id)
        today = datetime.utcnow().strftime("%Y-%m-%d")

        # منع التكرار (أمان إضافي)
        if user_data.get("last_box_date") == today:
            await update.message.reply_text("❌ لقد فتحت الصندوق اليوم بالفعل!")
            return

        # حساب الجائزة العشوائية
        prize_points, prize_msg = spin_mystery_box()
        new_points = user_data["points"] + prize_points

        # تحديث الرصيد وتسجيل التاريخ
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

    app.run_polling()

if __name__ == '__main__':
    main()

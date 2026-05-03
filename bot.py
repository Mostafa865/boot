# v2
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
import openai
import json
import os

TELEGRAM_TOKEN = "8545099923:AAH9ggxKf-BsjiNRpfe0lMouf68Kf0JhWP8"
OPENROUTER_API_KEY = "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"
ADMIN_ID = 7825923320
CHANNEL_USERNAME = "@easy_free_1"
POINTS_PER_AD = 100
POINTS_PER_USE = 50
DB_FILE = "users.json"

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

TOPIC, TONE, WEEKLY_TOPIC, BROADCAST_MSG = range(4)

def load_db():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "r") as f:
            return json.load(f)
    return {}

def save_db(db):
    with open(DB_FILE, "w") as f:
        json.dump(db, f)

def get_user(user_id):
    db = load_db()
    uid = str(user_id)
    if uid not in db:
        db[uid] = {"points": 300, "uses": 0, "referrals": 0}
        save_db(db)
    return db[uid]

def update_user(user_id, data):
    db = load_db()
    uid = str(user_id)
    db[uid] = data
    save_db(db)

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
        [InlineKeyboardButton("📺 شاهد إعلان للنقاط", callback_data="watch_ad")],
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
    await context.bot.send_message(
        ADMIN_ID,
        f"👤 مستخدم جديد دخل البوت:\n"
        f"الاسم: {name}\n"
        f"ID: {user_id}"
    )

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

async def my_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = get_user(query.from_user.id)
    await query.message.reply_text(
        f"👤 *حسابي*\n\n"
        f"💎 النقاط: *{user_data['points']} نقطة*\n"
        f"✍️ الاستخدامات: *{user_data['uses']} مرة*\n"
        f"🎁 الدعوات: *{user_data['referrals']} صديق*\n\n"
        f"كل استخدام بيتخصم {POINTS_PER_USE} نقطة\n"
        f"شاهد إعلان واكسب {POINTS_PER_AD} نقطة 📺",
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
        "كل صديق بيدخل عن طريقك بتكسب *100 نقطة* 🎉",
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
        "اضغط على الرابط وشوف الإعلان:\n"
        "بعد المشاهدة اضغط ✅ تأكيد المشاهدة",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📺 شاهد الإعلان", url="https://omg10.com/4/10955644")],
            [InlineKeyboardButton("✅ تأكيد المشاهدة", callback_data="confirm_ad")],
        ])
    )

async def confirm_ad(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_data = get_user(query.from_user.id)
    user_data["points"] += POINTS_PER_AD
    update_user(query.from_user.id, user_data)
    await query.message.reply_text(
        f"✅ *تم تأكيد المشاهدة!*\n\n"
        f"تم إضافة *{POINTS_PER_AD} نقطة* لحسابك 🎉\n"
        f"💎 رصيدك الحالي: *{user_data['points']} نقطة*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 القائمة", callback_data="home")]
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

    user_data = get_user(query.from_user.id)
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
    user_data["points"] -= POINTS_PER_USE
    user_data["uses"] += 1
    update_user(update.effective_user.id, user_data)

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
            f"💎 رصيد نقاطك المتبقي: *{user_data['points']} نقطة*",
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
    platform = context.user_data['platform']
    topic = context.user_data['topic']

    await query.edit_message_text("⏳ بكتبلك المحتوى... انتظر ثانية!")

    user_data = get_user(query.from_user.id)
    user_data["points"] -= POINTS_PER_USE
    user_data["uses"] += 1
    update_user(query.from_user.id, user_data)

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

    platform_key = context.user_data['platform_key']
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
            f"💎 رصيد نقاطك المتبقي: *{user_data['points']} نقطة*",
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

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        return
    db = load_db()
    total_users = len(db)
    total_uses = sum(u.get("uses", 0) for u in db.values())
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
    db = load_db()
    total_users = len(db)
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
    db = load_db()
    success = 0
    for uid in db:
        try:
            await context.bot.send_message(int(uid), f"📢 *رسالة من الإدارة:*\n\n{msg}", parse_mode="Markdown")
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
    app.add_handler(CallbackQueryHandler(check_sub_callback, pattern="^check_sub$"))
    app.add_handler(CallbackQueryHandler(my_account, pattern="^myaccount$"))
    app.add_handler(CallbackQueryHandler(referral, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(watch_ad, pattern="^watch_ad$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(handle_nav, pattern="^(home|new|admin_back)$"))

    app.run_polling()

if __name__ == '__main__':
    main()

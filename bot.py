from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes, ConversationHandler
import openai

TELEGRAM_TOKEN = "8545099923:AAFA5UI18858JHifhVv4HvuNsyyU5v8jiRQ"
OPENROUTER_API_KEY = "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"

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

TOPIC, TONE = range(2)

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name
    await update.message.reply_text(
        f"👋 أهلاً *{name}*!\n\n"
        "🤖 أنا بوت كتابة المحتوى الاحترافي\n"
        "بساعدك تكتب محتوى جذاب لأي منصة في ثوانٍ ✨\n\n"
        "👇 اختار نوع المحتوى اللي عايزه:",
        parse_mode="Markdown",
        reply_markup=main_menu()
    )

async def handle_platform(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

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
            model="openai/gpt-oss-120b",
            messages=[
                {"role": "system", "content": "أنت كاتب محتوى محترف ومتخصص في السوشيال ميديا. اكتب محتوى باللغة العربية فقط."},
                {"role": "user", "content": prompt}
            ]
        )
        content = response.choices[0].message.content
        await query.message.reply_text(
            f"✅ *المحتوى جاهز:*\n\n{content}\n\n"
            "━━━━━━━━━━━━━━━\n"
            "🔄 عايز محتوى تاني؟",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 محتوى جديد", callback_data="new"),
                 InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="home")]
            ])
        )
    except Exception as e:
        await query.message.reply_text(
            "❌ حصل خطأ، حاول تاني بعد شوية.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 حاول تاني", callback_data="home")]
            ])
        )

    return ConversationHandler.END

async def handle_nav(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "👇 اختار نوع المحتوى اللي عايزه:",
        reply_markup=main_menu()
    )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_platform, pattern="^(facebook|instagram|twitter|linkedin|email|ad|article|ideas)$")],
        states={
            TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic)],
            TONE: [CallbackQueryHandler(get_tone, pattern="^tone_")],
        },
        fallbacks=[CommandHandler('start', start)]
    )

    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(handle_nav, pattern="^(home|new)$"))

    app.run_polling()

if __name__ == '__main__':
    main()

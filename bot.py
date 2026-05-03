from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
import openai

TELEGRAM_TOKEN = "8545099923:AAFA5UI18858JHifhVv4HvuNsyyU5v8jiRQ"
OPENROUTER_API_KEY = "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"

client = openai.OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

PLATFORM, TOPIC, TONE = range(3)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 أهلاً بيك في بوت كتابة المحتوى!\n\n"
        "اختار الأمر اللي تحتاجه:\n"
        "/facebook — بوست فيسبوك\n"
        "/instagram — كابشن انستجرام\n"
        "/twitter — تويت تويتر"
    )

async def facebook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['platform'] = 'فيسبوك'
    await update.message.reply_text("✍️ اكتبلي موضوع البوست:")
    return TOPIC

async def instagram(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['platform'] = 'انستجرام'
    await update.message.reply_text("✍️ اكتبلي موضوع الكابشن:")
    return TOPIC

async def twitter(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['platform'] = 'تويتر'
    await update.message.reply_text("✍️ اكتبلي موضوع التويت:")
    return TOPIC

async def get_topic(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['topic'] = update.message.text
    await update.message.reply_text(
        "🎨 اختار التون:\n"
        "1 — رسمي واحترافي\n"
        "2 — مرح وعامي"
    )
    return TONE

async def get_tone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tone = "رسمي واحترافي" if update.message.text == "1" else "مرح وعامي"
    platform = context.user_data['platform']
    topic = context.user_data['topic']

    await update.message.reply_text("⏳ بكتبلك المحتوى...")

    response = client.chat.completions.create(
        model="gpt-oss-120b",
        messages=[
            {
                "role": "user",
                "content": f"اكتبلي {platform} عن '{topic}' بأسلوب {tone}. المحتوى يكون جذاب ومناسب للمنصة."
            }
        ]
    )

    content = response.choices[0].message.content
    await update.message.reply_text(f"✅ المحتوى جاهز:\n\n{content}")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("تم الإلغاء. ابدأ من أول بـ /start")
    return ConversationHandler.END

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler('facebook', facebook),
            CommandHandler('instagram', instagram),
            CommandHandler('twitter', twitter),
        ],
        states={
            TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic)],
            TONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_tone)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == '__main__':
    main()
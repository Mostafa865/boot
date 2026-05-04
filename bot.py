# v14.0 - النسخة النهائية المستقرة
import logging, random, csv, io
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (Application, CommandHandler, MessageHandler, CallbackQueryHandler,
                          filters, ContextTypes, ConversationHandler)
from pymongo import MongoClient
import openai

# ========== إعدادات البوت ==========
TELEGRAM_TOKEN = "8545099923:AAH9ggxKf-BsjiNRpfe0lMouf68Kf0JhWP8"
OPENROUTER_API_KEY = "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"
MONGO_URI = "mongodb+srv://orabiabosenna_db_user:mostafahbn0@cluster0.cwl2dvz.mongodb.net/botdb?appName=Cluster0"
ADMIN_ID = 7825923320
CHANNEL_USERNAME = "@easy_free_1"

# ========== الثوابت ==========
POINTS_PER_USE = 50
POINTS_PER_AD = 100
MAX_ADS_PER_DAY = 15
REFERRAL_WITHDRAWABLE = 3000
REFERRAL_LEVEL2 = 500
REFERRAL_COMMISSION_PERCENT = 10
POINTS_PER_DOLLAR = 40000
MIN_WITHDRAW_POINTS = 120000
STREAK_MAX_MULTIPLIER = 2.0
STREAK_STEP = 0.05
WEEKLY_MISSION_TARGET = 50
WEEKLY_MISSION_REWARD = 5000
AMBASSADOR_THRESHOLD = 10
MAX_DAILY_COMMISSION = 5000
EARLY_BIRD_POINTS = 5000
EARLY_BIRD_LIMIT = 100

BOX_LEVELS = {
    "فضة": {"streak_range": (1,5), "prizes": [(50, "😐 حظك عادي", 50), (100, "🙂 مش بطال", 25), (200, "😊 كويس", 25)]},
    "ذهب": {"streak_range": (6,10), "prizes": [(200, "😊 كويس", 40), (350, "🙂 حلو", 35), (500, "🔥 ممتاز", 25)]},
    "ألماس": {"streak_range": (11,100), "prizes": [(500, "🔥 ممتاز", 40), (1000, "🎉 رائع", 35), (2000, "🏆 جاكبوت", 25)]}
}

AD_URL = "https://mostafa865.github.io/boot/ad.html"
BOX_AD_URL = "https://mostafa865.github.io/boot/box_ad.html"

mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo["botdb"]
users_col = db["users"]
withdrawals_col = db["withdrawals"]

client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

TOPIC, TONE, WEEKLY_TOPIC, BROADCAST_MSG = range(4)

# ========== دوال قاعدة البيانات ==========
def get_user(user_id):
    uid = str(user_id)
    user = users_col.find_one({"_id": uid})
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if not user:
        total_before = users_col.count_documents({})
        early_bird = total_before < EARLY_BIRD_LIMIT
        user = {
            "_id": uid, "points": 300, "withdrawable_points": 0, "early_bird_rewarded": early_bird, "early_bird_notified": False,
            "uses": 0, "referrals": 0, "referrer_id": None, "referral_date": None, "total_commission_today": 0,
            "last_commission_date": "", "referred_users": [], "referral_level2_count": 0, "total_commission_earned": 0,
            "has_withdrawn_before": False, "first_withdrawal_date": None, "tasks": {"ad": False, "used": False, "bonus": False},
            "last_task_date": today, "last_box_date": "", "ad_watch_today": 0, "last_ad_date": "", "ad_streak": 0,
            "ad_multiplier": 1.0, "last_ad_streak_date": "", "weekly_ad_count": 0, "last_contest_week": datetime.utcnow().strftime("%Y-%W"),
            "weekly_mission_claimed": False, "ambassador_badge": False, "last_daily_report_date": "", "total_ads_watched": 0, "badges": [], "pending_action": None
        }
        users_col.insert_one(user)
    else:
        updated = False
        for field in ["withdrawable_points","ad_watch_today","last_ad_date","ad_streak","ad_multiplier","last_ad_streak_date",
                      "referrer_id","referral_date","total_commission_today","last_commission_date","referred_users",
                      "referral_level2_count","total_commission_earned","has_withdrawn_before","first_withdrawal_date",
                      "weekly_mission_claimed","ambassador_badge","last_daily_report_date","total_ads_watched","badges",
                      "pending_action","early_bird_rewarded","early_bird_notified"]:
            if field not in user:
                user[field] = None if field in ["referrer_id","referral_date","first_withdrawal_date","last_daily_report_date","pending_action"] else (0 if field in ["total_commission_today","referral_level2_count","total_commission_earned","total_ads_watched"] else ([] if field=="badges" else False))
                updated = True
        if updated:
            update_user(user_id, {k: user[k] for k in required_fields})
    return user

def update_user(user_id, data):
    try:
        users_col.update_one({"_id": str(user_id)}, {"$set": data}, upsert=True)
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
    last = user.get("last_ad_streak_date","")
    cur = user.get("ad_streak",0)
    if last == today:
        return user.get("ad_multiplier",1.0)
    yesterday = (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d")
    if last == yesterday:
        cur += 1
        if cur > 20: cur = 20
        mul = min(STREAK_MAX_MULTIPLIER, 1.0 + (cur-1)*STREAK_STEP)
        mul = round(mul,2)
    else:
        cur = 1
        mul = 1.0
    update_user(user_id, {"ad_streak":cur, "ad_multiplier":mul, "last_ad_streak_date":today})
    if cur >= 30 and "الأسطورة" not in user.get("badges",[]):
        add_badge(user_id, "الأسطورة")
    return mul

def spin_mystery_box(streak):
    for level, data in BOX_LEVELS.items():
        min_s, max_s = data["streak_range"]
        if min_s <= streak <= max_s:
            prizes = data["prizes"]
            total = sum(w for _, _, w in prizes)
            r = random.randint(1, total)
            cur = 0
            for points, msg, weight in prizes:
                cur += weight
                if r <= cur:
                    return points, msg, level
    return 50, "😐 حظك عادي", "فضة"

def add_badge(user_id, badge_name):
    u = get_user(user_id)
    if badge_name not in u.get("badges", []):
        u["badges"].append(badge_name)
        update_user(user_id, {"badges": u["badges"]})
        return True
    return False

def can_add_commission(user_id, amount):
    user = get_user(user_id)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if user.get("last_commission_date") != today:
        user["total_commission_today"] = 0
        user["last_commission_date"] = today
        update_user(user_id, {"total_commission_today": 0, "last_commission_date": today})
    if user.get("total_commission_today",0) + amount <= MAX_DAILY_COMMISSION:
        update_user(user_id, {"total_commission_today": user.get("total_commission_today",0) + amount})
        return True
    return False

# ========== القوائم ==========
def main_menu():
    kb = [
        [InlineKeyboardButton("✍️ كتابة محتوى", callback_data="content_menu")],
        [InlineKeyboardButton("💰 كسب النقاط", callback_data="earn_menu")],
        [InlineKeyboardButton("👤 حسابي", callback_data="account_menu")],
        [InlineKeyboardButton("🏆 المتصدرين", callback_data="leaderboard")],
        [InlineKeyboardButton("ℹ️ تعليمات", callback_data="help")]
    ]
    return InlineKeyboardMarkup(kb)

async def content_menu(update, context):
    q = update.callback_query
    await q.answer()
    kb = [[InlineKeyboardButton("📘 بوست فيسبوك", callback_data="facebook"), InlineKeyboardButton("📸 كابشن انستجرام", callback_data="instagram")],
          [InlineKeyboardButton("🐦 تويت تويتر", callback_data="twitter"), InlineKeyboardButton("💼 بوست لينكدإن", callback_data="linkedin")],
          [InlineKeyboardButton("📧 إيميل احترافي", callback_data="email"), InlineKeyboardButton("🎯 إعلان تسويقي", callback_data="ad")],
          [InlineKeyboardButton("✍️ مقال قصير", callback_data="article"), InlineKeyboardButton("💡 أفكار محتوى", callback_data="ideas")],
          [InlineKeyboardButton("📅 جدولة محتوى أسبوعي", callback_data="weekly")],
          [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]
    await q.edit_message_text("✍️ *اختر نوع المحتوى:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def earn_menu(update, context):
    q = update.callback_query
    await q.answer()
    kb = [[InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad")],
          [InlineKeyboardButton("🎲 صندوق الحظ", callback_data="mystery_box")],
          [InlineKeyboardButton("📋 مهام اليوم", callback_data="daily_tasks")],
          [InlineKeyboardButton("🎁 دعوة صديق", callback_data="referral")],
          [InlineKeyboardButton("🎁 عروض خاصة", callback_data="special_offers")],
          [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]
    await q.edit_message_text("💰 *كسب النقاط*\nاختر طريقة:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def account_menu(update, context):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)
    ambassador = "🏅 *سفير البوت* 🏅\n" if u.get("ambassador_badge") else ""
    badges_text = "🏅 *الشارات:* " + ", ".join(u.get("badges", [])) if u.get("badges") else "🏅 *الشارات:* لا توجد شارات بعد"
    next_streak = u.get("ad_streak",0)+1
    next_level = "فضة"
    for lvl, data in BOX_LEVELS.items():
        if data["streak_range"][0] <= next_streak <= data["streak_range"][1]:
            next_level = lvl
            break
    text = (f"👤 *حسابي*\n\n{ambassador}"
            f"✨ نقاط عادية: *{u['points']}*\n💰 نقاط قابلة للسحب: *{u.get('withdrawable_points',0)}*\n"
            f"✍️ استخدامات: *{u['uses']}*\n🎁 دعوات مباشرة: *{u['referrals']}*\n"
            f"🎁 دعوات غير مباشرة: *{u.get('referral_level2_count',0)}*\n🔥 Streak: *{u.get('ad_streak',0)} يوم* (مضاعف {u.get('ad_multiplier',1.0)}x)\n"
            f"📊 إجمالي الإعلانات: *{u.get('total_ads_watched',0)}*\n🎲 غداً سيكون صندوقك: *{next_level}*\n\n{badges_text}\n\n"
            f"📺 كل إعلان: +{POINTS_PER_AD} نقطة × المضاعف (حد {MAX_ADS_PER_DAY}/يوم)\n"
            f"🎁 كل دعوة مباشرة: +{REFERRAL_WITHDRAWABLE} نقطة + {REFERRAL_COMMISSION_PERCENT}% عمولة شهرية\n"
            f"🎁 كل دعوة غير مباشرة: +{REFERRAL_LEVEL2} نقطة\n"
            f"💰 التحويل: {POINTS_PER_DOLLAR} نقطة = $1\n🏧 حد السحب: {MIN_WITHDRAW_POINTS} نقطة (${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR})")
    kb = [[InlineKeyboardButton("💰 سحب النقاط", callback_data="withdraw")], [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def help_callback(update, context):
    q = update.callback_query
    await q.answer()
    text = (f"ℹ️ *تعليمات البوت*\n\n"
            f"1️⃣ *كسب النقاط*: شاهد إعلانات يومياً (حد {MAX_ADS_PER_DAY}) واحصل على نقاط قابلة للسحب.\n"
            f"2️⃣ *Streak*: كل يوم تشاهد إعلان يزيد المضاعف 5% حتى 2x.\n"
            f"3️⃣ *صندوق الحظ المتطور*: حسب الـ Streak تحصل على صندوق فضة/ذهب/ألماس، جوائز تصل إلى 2000 نقطة عادية.\n"
            f"4️⃣ *المهام اليومية*: شاهد إعلان + استخدم البوت = 300 نقطة عادية بونص (يتطلب إعلاناً لصرفه).\n"
            f"5️⃣ *الإحالات المتقدمة*: ادعو أصدقاءك – مكافأة {REFERRAL_WITHDRAWABLE} نقطة لكل مدعو مباشر، وعمولة {REFERRAL_COMMISSION_PERCENT}% من أرباح إعلانات مدعويك.\n"
            f"6️⃣ *المسابقة الأسبوعية*: كل إثنين، أفضل 10 مستخدمين في عدد الإعلانات يحصلون على جوائز تصل إلى 5000 نقطة.\n"
            f"7️⃣ *مهمة أسبوعية*: شاهد {WEEKLY_MISSION_TARGET} إعلاناً في الأسبوع ↔ {WEEKLY_MISSION_REWARD} نقطة قابلة للسحب.\n"
            f"8️⃣ *السحب*: تجميع {MIN_WITHDRAW_POINTS} نقطة = ${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR}، اطلب السحب وتراجع إدارياً.\n"
            f"9️⃣ *شارات*: احصل على شارات (المدعو الأول، السفير، 100 إعلان، السبوعي، الأسطورة) تظهر في حسابك.\n"
            f"🔟 *مكافأة التسجيل المبكر*: أول {EARLY_BIRD_LIMIT} مستخدم يحصلون على {EARLY_BIRD_POINTS} نقطة قابلة للسحب (تتطلب إعلاناً).")
    kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def main_back(update, context):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)
    await q.edit_message_text(f"👋 أهلاً *{q.from_user.first_name}*!\n\n✨ نقاط عادية: *{u['points']}*\n💰 نقاط قابلة للسحب: *{u.get('withdrawable_points',0)}*\n\n👇 اختر من القائمة:", parse_mode="Markdown", reply_markup=main_menu())

async def special_offers(update, context):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)
    if u.get("early_bird_rewarded") and not u.get("early_bird_notified"):
        if not u.get("pending_action"):
            update_user(q.from_user.id, {"pending_action": {"type": "early_bird", "points": EARLY_BIRD_POINTS}})
        text = f"🎁 *العروض الخاصة*\n\n✅ *أنت من أوائل المستخدمين!*\nلديك {EARLY_BIRD_POINTS} نقطة قابلة للسحب في انتظارك.\nشاهد إعلاناً لاستلامها."
    else:
        text = "🎁 *العروض الخاصة*\n\n❌ لا توجد عروض خاصة حالياً.\nالعرض متاح لأول 100 مستخدم فقط."
    kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="earn_menu")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

def tone_menu():
    kb = [[InlineKeyboardButton("👔 رسمي", callback_data="tone_formal"), InlineKeyboardButton("😄 عامي", callback_data="tone_casual")],
          [InlineKeyboardButton("🔥 تسويقي", callback_data="tone_marketing"), InlineKeyboardButton("💬 مباشر", callback_data="tone_simple")]]
    return InlineKeyboardMarkup(kb)

def admin_menu():
    kb = [[InlineKeyboardButton("👥 المستخدمون", callback_data="admin_users"), InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
          [InlineKeyboardButton("💰 طلبات السحب", callback_data="admin_withdrawals")],
          [InlineKeyboardButton("📢 رسالة جماعية", callback_data="admin_broadcast")],
          [InlineKeyboardButton("📁 تصدير Excel", callback_data="admin_export")]]
    return InlineKeyboardMarkup(kb)

# ========== دوال البوت الأساسية ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = user.id
    name = user.first_name

    if context.args and context.args[0].startswith("ref_"):
        ref_id = context.args[0].replace("ref_", "")
        if ref_id != str(uid):
            referrer = get_user(int(ref_id))
            new_user = get_user(uid)
            if new_user.get("referrer_id") is None:
                update_user(uid, {"referrer_id": int(ref_id), "referral_date": datetime.utcnow().isoformat()})
                update_user(int(ref_id), {"withdrawable_points": referrer["withdrawable_points"] + REFERRAL_WITHDRAWABLE, "referrals": referrer["referrals"] + 1})
                try: await context.bot.send_message(int(ref_id), f"🎉 صديق جديد! +{REFERRAL_WITHDRAWABLE} نقطة.", parse_mode="Markdown")
                except: pass
                if referrer["referrals"] == 0: add_badge(int(ref_id), "المدعو الأول")
                upline = referrer.get("referrer_id")
                if upline:
                    up = get_user(upline)
                    update_user(upline, {"withdrawable_points": up["withdrawable_points"] + REFERRAL_LEVEL2, "referral_level2_count": up.get("referral_level2_count",0)+1})
                    try: await context.bot.send_message(upline, f"🎉 مدعو غير مباشر! +{REFERRAL_LEVEL2} نقطة.", parse_mode="Markdown")
                    except: pass
                if referrer["referrals"] + 1 >= AMBASSADOR_THRESHOLD and not referrer.get("ambassador_badge"):
                    update_user(int(ref_id), {"ambassador_badge": True})
                    add_badge(int(ref_id), "سفير")
                    try: await context.bot.send_message(int(ref_id), "🏅 مبروك! حصلت على شارة سفير البوت!", parse_mode="Markdown")
                    except: pass

    if uid == ADMIN_ID:
        await update.message.reply_text(f"👋 أهلاً *{name}* — لوحة الأدمن 🔧", parse_mode="Markdown", reply_markup=admin_menu())
        return

    u = get_user(uid)
    if u.get("early_bird_rewarded") and not u.get("early_bird_notified") and not u.get("pending_action"):
        update_user(uid, {"pending_action": {"type": "early_bird", "points": EARLY_BIRD_POINTS}})
        await update.message.reply_text(
            f"🎉 *تهانينا! أنت من أوائل مستخدمي البوت!* 🎉\nلديك *{EARLY_BIRD_POINTS} نقطة قابلة للسحب*.\nشاهد إعلاناً لاستلام الهدية 👇",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎁 استلام الهدية", web_app=WebAppInfo(url=AD_URL))]])
        )
    else:
        await update.message.reply_text(
            f"👋 أهلاً *{name}*!\n🤖 بوت كتابة المحتوى الاحترافي 🚀\n✨ نقاط عادية: *{u['points']}*\n💰 نقاط قابلة للسحب: *{u.get('withdrawable_points',0)}*\n\n👇 اختر من القائمة:",
            parse_mode="Markdown", reply_markup=main_menu()
        )

# دوال المحتوى
async def handle_platform(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = check_daily_tasks(get_user(uid))
    update_user(uid, {"tasks": u["tasks"], "last_task_date": u["last_task_date"]})
    if u["points"] < POINTS_PER_USE:
        await q.message.reply_text(f"❌ نقاطك مش كافية! رصيدك: {u['points']}، تحتاج {POINTS_PER_USE}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad")]]))
        return ConversationHandler.END
    platforms = {"facebook":"📘 بوست فيسبوك","instagram":"📸 كابشن انستجرام","twitter":"🐦 تويت تويتر","linkedin":"💼 بوست لينكدإن","email":"📧 إيميل","ad":"🎯 إعلان","article":"✍️ مقال","ideas":"💡 أفكار"}
    context.user_data['platform'] = platforms[q.data]
    context.user_data['platform_key'] = q.data
    await q.edit_message_text(f"✅ اخترت: *{platforms[q.data]}*\n\n📝 اكتب موضوع أو فكرة المحتوى:", parse_mode="Markdown")
    return TOPIC

async def weekly(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = check_daily_tasks(get_user(uid))
    if u["points"] < POINTS_PER_USE:
        await q.message.reply_text("❌ نقاطك مش كافية!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad")]]))
        return ConversationHandler.END
    await q.edit_message_text("📅 *جدولة أسبوعية*\nاكتب موضوع قناتك:", parse_mode="Markdown")
    return WEEKLY_TOPIC

async def get_topic(update, context):
    context.user_data['topic'] = update.message.text
    await update.message.reply_text("🎨 اختار أسلوب الكتابة:", parse_mode="Markdown", reply_markup=tone_menu())
    return TONE

async def get_tone(update, context):
    q = update.callback_query
    await q.answer()
    tones = {"tone_formal":"رسمي","tone_casual":"عامي","tone_marketing":"تسويقي","tone_simple":"مباشر"}
    tone = tones[q.data]
    topic = context.user_data['topic']
    key = context.user_data['platform_key']
    await q.edit_message_text("⏳ بكتبلك المحتوى...")
    uid = q.from_user.id
    u = check_daily_tasks(get_user(uid))
    u["tasks"]["used"] = True
    new_pts = u["points"] - POINTS_PER_USE
    update_user(uid, {"points": new_pts, "uses": u["uses"]+1, "tasks": u["tasks"], "last_task_date": u["last_task_date"]})
    prompts = {
        "facebook": f"اكتب بوست فيسبوك عن '{topic}' بأسلوب {tone}.",
        "instagram": f"اكتب كابشن انستجرام عن '{topic}' بأسلوب {tone} مع هاشتاقات.",
        "twitter": f"اكتب تويت مختصر عن '{topic}' بأسلوب {tone}.",
        "linkedin": f"اكتب بوست لينكدإن عن '{topic}' بأسلوب {tone}.",
        "email": f"اكتب إيميل عن '{topic}' بأسلوب {tone}.",
        "ad": f"اكتب إعلان تسويقي عن '{topic}' بأسلوب {tone}.",
        "article": f"اكتب مقال قصير عن '{topic}' بأسلوب {tone}.",
        "ideas": f"أعطني 5 أفكار محتوى عن '{topic}'."
    }
    prompt = prompts.get(key, f"اكتب محتوى عن '{topic}'.")
    try:
        r = client.chat.completions.create(model="gpt-oss-120b", messages=[{"role":"system","content":"أنت كاتب محتوى محترف."},{"role":"user","content":prompt}])
        content = r.choices[0].message.content
        await q.message.reply_text(f"✅ *المحتوى جاهز:*\n\n{content}\n\n━━━━━━━━━━━━━━━\n💎 رصيدك المتبقي: *{new_pts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 محتوى جديد", callback_data="new"), InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    except Exception as e:
        await q.message.reply_text(f"❌ خطأ: {str(e)[:100]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    return ConversationHandler.END

async def get_weekly_topic(update, context):
    topic = update.message.text
    await update.message.reply_text("⏳ جاري كتابة 7 بوستات...")
    uid = update.effective_user.id
    u = get_user(uid)
    new_pts = u["points"] - POINTS_PER_USE
    update_user(uid, {"points": new_pts, "uses": u["uses"]+1})
    try:
        r = client.chat.completions.create(model="gpt-oss-120b", messages=[{"role":"system","content":"كاتب محتوى محترف."},{"role":"user","content":f"اكتب 7 بوستات تيليجرام مختلفة عن '{topic}'."}])
        content = r.choices[0].message.content
        await update.message.reply_text(f"✅ *بوستات الأسبوع:*\n\n{content}\n\n💎 رصيدك المتبقي: *{new_pts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 أسبوع جديد", callback_data="weekly"), InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)[:100]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    return ConversationHandler.END

# دوال الإعلانات والمكافآت
async def handle_web_app_data(update, context):
    data = update.message.web_app_data.data
    uid = update.effective_user.id
    if data == "ad_watched":
        u = get_user(uid)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if u.get("last_ad_date") != today:
            update_user(uid, {"ad_watch_today": 0, "last_ad_date": today})
            u["ad_watch_today"] = 0
        if u.get("ad_watch_today",0) >= MAX_ADS_PER_DAY:
            await update.message.reply_text(f"❌ تجاوزت الحد اليومي ({MAX_ADS_PER_DAY})", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
            return
        mul = update_ad_streak(uid, today)
        earned = int(POINTS_PER_AD * mul)
        new_w = u["withdrawable_points"] + earned
        new_cnt = u["ad_watch_today"] + 1
        new_total = u.get("total_ads_watched",0) + 1
        update_user(uid, {"withdrawable_points": new_w, "ad_watch_today": new_cnt, "last_ad_date": today, "total_ads_watched": new_total})
        if new_total >= 100 and "100 إعلان" not in u.get("badges",[]):
            add_badge(uid, "100 إعلان")
            try: await context.bot.send_message(uid, "🏅 شارة 100 إعلان!", parse_mode="Markdown")
            except: pass
        cweek = datetime.utcnow().strftime("%Y-%W")
        if u.get("last_contest_week") != cweek:
            update_user(uid, {"weekly_ad_count": 0, "last_contest_week": cweek, "weekly_mission_claimed": False})
            u["weekly_ad_count"] = 0
        new_weekly = u.get("weekly_ad_count",0) + 1
        update_user(uid, {"weekly_ad_count": new_weekly})
        if new_weekly >= WEEKLY_MISSION_TARGET and not u.get("weekly_mission_claimed"):
            update_user(uid, {"withdrawable_points": u["withdrawable_points"] + WEEKLY_MISSION_REWARD, "weekly_mission_claimed": True})
            await update.message.reply_text(f"🎉 مهمة أسبوعية مكتملة! +{WEEKLY_MISSION_REWARD} نقطة.", parse_mode="Markdown")
        rid = u.get("referrer_id")
        if rid and u.get("referral_date"):
            if (datetime.utcnow() - datetime.fromisoformat(u["referral_date"])).days <= 30:
                commission = int(earned * REFERRAL_COMMISSION_PERCENT / 100)
                if commission > 0 and can_add_commission(rid, commission):
                    ref = get_user(rid)
                    update_user(rid, {"withdrawable_points": ref["withdrawable_points"] + commission, "total_commission_earned": ref.get("total_commission_earned",0) + commission})
                    try: await context.bot.send_message(rid, f"🎁 عمولة إحالة: +{commission} نقطة!", parse_mode="Markdown")
                    except: pass
        u2 = check_daily_tasks(get_user(uid))
        u2["tasks"]["ad"] = True
        update_user(uid, {"tasks": u2["tasks"]})
        await update.message.reply_text(
            f"✅ *تم إضافة {earned} نقطة!*\n💎 رصيدك القابل للسحب: *{new_w}*\n🔥 مضاعف اليوم: *{mul}x*\n📊 إعلانات اليوم: *{new_cnt}/{MAX_ADS_PER_DAY}*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]])
        )
        pending = u.get("pending_action")
        if pending:
            if pending["type"] == "early_bird":
                update_user(uid, {"withdrawable_points": u["withdrawable_points"] + pending["points"], "early_bird_notified": True, "pending_action": None})
                await update.message.reply_text(f"🎉 تم استلام هدية التسجيل المبكر! +{pending['points']} نقطة.", parse_mode="Markdown")
            elif pending["type"] == "claim_bonus":
                u3 = check_daily_tasks(get_user(uid))
                if not u3["tasks"].get("bonus",False):
                    new_pts = u3["points"] + 300
                    u3["tasks"]["bonus"] = True
                    update_user(uid, {"points": new_pts, "tasks": u3["tasks"], "pending_action": None})
                    await update.message.reply_text(f"🎉 بونص المهام اليومية! +300 نقطة عادية.", parse_mode="Markdown")
                else:
                    update_user(uid, {"pending_action": None})
    elif data == "box_ad_watched":
        u = get_user(uid)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if u.get("last_box_date") == today:
            await update.message.reply_text("❌ فتحت الصندوق اليوم!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
            return
        streak = u.get("ad_streak",0)
        prize, msg, level = spin_mystery_box(streak)
        new_pts = u["points"] + prize
        update_user(uid, {"points": new_pts, "last_box_date": today})
        await update.message.reply_text(f"🎁 *نتيجة صندوق {level}*\n{msg}\n🎊 ربحت *{prize} نقطة عادية*!\n💎 رصيدك العادي: *{new_pts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))

async def mystery_box(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    if u.get("last_box_date") == datetime.utcnow().strftime("%Y-%m-%d"):
        await q.message.reply_text("❌ فتحت الصندوق اليوم!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
        return
    streak = u.get("ad_streak",0)
    level = "فضة"
    for lvl, data in BOX_LEVELS.items():
        if data["streak_range"][0] <= streak <= data["streak_range"][1]:
            level = lvl
            break
    await q.message.reply_text(f"🎲 *صندوق الحظ - مستوى {level}* 🎲\n🔥 Streak: {streak}\n⚠️ شاهد الإعلان أولاً:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"🎁 افتح صندوق {level}", web_app=WebAppInfo(url=BOX_AD_URL))]]))

async def watch_ad(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if u.get("last_ad_date") != today:
        update_user(uid, {"ad_watch_today": 0, "last_ad_date": today})
    if u.get("ad_watch_today",0) >= MAX_ADS_PER_DAY:
        await q.message.reply_text(f"❌ الحد اليومي {MAX_ADS_PER_DAY}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
        return
    mul = update_ad_streak(uid, today)
    earn = int(POINTS_PER_AD * mul)
    remaining = MAX_ADS_PER_DAY - u["ad_watch_today"]
    await q.message.reply_text(f"📺 *شاهد الإعلان*\n🔥 مضاعف: {mul}x\n💰 ستربح: {earn} نقطة\n📊 تبقى لك: {remaining} إعلان.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد", web_app=WebAppInfo(url=AD_URL))]]))

async def daily_tasks(update, context):
    q = update.callback_query
    await q.answer()
    u = check_daily_tasks(get_user(q.from_user.id))
    tasks = u["tasks"]
    text = f"📋 *مهام اليوم*\n{'✅' if tasks['ad'] else '❌'} شاهد إعلان\n{'✅' if tasks['used'] else '❌'} استخدم البوت"
    if tasks["ad"] and tasks["used"] and not tasks["bonus"]:
        text += "\n\n🎁 يمكنك استلام 300 نقطة بونص! (يتطلب إعلاناً)"
        kb = [[InlineKeyboardButton("🎁 استلام البونص", callback_data="claim_bonus")]]
    elif tasks["bonus"]:
        text += "\n✅ استلمت البونص!"
        kb = [[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]
    else:
        text += "\n🎯 أكمل المهام لتحصل على 300 نقطة!"
        kb = [[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def claim_bonus(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = check_daily_tasks(get_user(uid))
    if u["tasks"]["ad"] and u["tasks"]["used"] and not u["tasks"]["bonus"]:
        update_user(uid, {"pending_action": {"type": "claim_bonus"}})
        await q.message.reply_text("🎁 *مكافأة المهام اليومية*\nشاهد إعلاناً لاستلام 300 نقطة 👇", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد واستلم", web_app=WebAppInfo(url=AD_URL))]]))
    else:
        await q.message.reply_text("❌ لم تكمل المهام أو استلمت البونص!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))

async def referral(update, context):
    q = update.callback_query
    await q.answer()
    link = f"https://t.me/easy_free1bot?start=ref_{q.from_user.id}"
    await q.message.reply_text(f"🎁 *رابط دعوتك:*\n`{link}`\n\nكل صديق يدخل يكسبك {REFERRAL_WITHDRAWABLE} نقطة + {REFERRAL_COMMISSION_PERCENT}% عمولة.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="earn_menu")]]))

async def withdraw_request(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    w = u.get("withdrawable_points",0)
    if w < MIN_WITHDRAW_POINTS:
        need = MIN_WITHDRAW_POINTS - w
        await q.message.reply_text(f"💰 *السحب*\nرصيدك: {w}\nالحد الأدنى: {MIN_WITHDRAW_POINTS} (${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR})\nتحتاج {need} نقطة.", parse_mode="Markdown")
        return
    amt = w // POINTS_PER_DOLLAR
    deduct = amt * POINTS_PER_DOLLAR
    new_w = w - deduct
    update_user(uid, {"withdrawable_points": new_w})
    if not u.get("has_withdrawn_before"):
        update_user(uid, {"has_withdrawn_before": True, "first_withdrawal_date": datetime.utcnow().isoformat()})
        new_w += 1000
        update_user(uid, {"withdrawable_points": new_w})
        await q.message.reply_text("🎁 هدية أول سحب! +1000 نقطة.", parse_mode="Markdown")
    withdrawal_req = {"user_id": uid, "points_deducted": deduct, "amount_usd": amt, "status": "pending", "date": datetime.utcnow().isoformat()}
    db["withdrawals"].insert_one(withdrawal_req)
    await context.bot.send_message(ADMIN_ID, f"💰 طلب سحب: {q.from_user.first_name} - {amt}$", parse_mode="Markdown")
    await q.message.reply_text(f"💰 تم إرسال طلب سحب {amt}$. سيتم المراجعة خلال 24 ساعة.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))

# دوال المتصدرين والأدمن
def get_leaderboard(limit=10):
    cursor = users_col.find({}, {"_id":1,"points":1,"withdrawable_points":1}).sort("points",-1).limit(limit)
    res = []
    for i,u in enumerate(cursor):
        total = u.get("points",0) + u.get("withdrawable_points",0)
        res.append({"rank":i+1, "user_id":u["_id"], "total_points":total})
    return res

async def leaderboard(update, context):
    q = update.callback_query
    await q.answer()
    data = get_leaderboard(10)
    if not data:
        text = "🏆 لا يوجد مستخدمون بعد."
    else:
        text = "🏆 *أفضل 10 مستخدمين*\n"
        for e in data:
            try:
                name = (await context.bot.get_chat(int(e["user_id"]))).first_name
            except:
                name = f"مستخدم {e['user_id'][-4:]}"
            text += f"{e['rank']}. {name} — 💎 {e['total_points']} نقطة\n"
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]))

async def admin_stats(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    total = users_col.count_documents({})
    uses = sum(u.get("uses",0) for u in users_col.find())
    active = sum(1 for u in users_col.find() if u.get("ad_watch_today",0)>0)
    withdrawn = sum(w.get("amount_usd",0) for w in db["withdrawals"].find({"status":"approved"}))
    await q.message.reply_text(f"📊 *الإحصائيات*\n👥 المستخدمين: {total}\n📈 نشطاء اليوم: {active}\n✍️ الاستخدامات: {uses}\n💵 المسحوبات: {withdrawn}$", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]))

async def admin_users(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    total = users_col.count_documents({})
    await q.message.reply_text(f"👥 *المستخدمون*\nإجمالي: {total}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]))

async def admin_broadcast_start(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    await q.message.reply_text("📢 اكتب الرسالة:")
    return BROADCAST_MSG

async def admin_broadcast_send(update, context):
    if update.effective_user.id != ADMIN_ID: return ConversationHandler.END
    msg = update.message.text
    success = 0
    for user in users_col.find():
        try:
            await context.bot.send_message(int(user["_id"]), f"📢 *رسالة من الإدارة:*\n\n{msg}", parse_mode="Markdown")
            success+=1
        except: pass
    await update.message.reply_text(f"✅ تم الإرسال لـ {success} مستخدم.")
    return ConversationHandler.END

async def admin_withdrawals(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    pending = list(db["withdrawals"].find({"status":"pending"}))
    if not pending:
        await q.message.reply_text("✅ لا توجد طلبات معلقة.")
        return
    text = "💰 *طلبات السحب*\n\n"
    kb = []
    for req in pending:
        try:
            name = (await context.bot.get_chat(req["user_id"])).first_name
        except:
            name = f"ID:{req['user_id']}"
        text += f"👤 {name}\n💵 {req['amount_usd']}$\n\n"
        rid = str(req["_id"])
        kb.append([InlineKeyboardButton(f"✅ قبول {req['amount_usd']}$", callback_data=f"approve_{rid}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_{rid}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")])
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def approve_withdraw(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    rid = q.data.split("_")[1]
    withdrawal = db["withdrawals"].find_one({"_id":ObjectId(rid), "status":"pending"})
    if not withdrawal:
        await q.message.reply_text("الطلب غير موجود.")
        return
    db["withdrawals"].update_one({"_id":ObjectId(rid)}, {"$set":{"status":"approved"}})
    try: await context.bot.send_message(withdrawal["user_id"], f"✅ تمت الموافقة على سحب {withdrawal['amount_usd']}$.", parse_mode="Markdown")
    except: pass
    await q.message.reply_text(f"✅ تمت الموافقة على سحب {withdrawal['amount_usd']}$.")
    await q.message.delete()
    await admin_withdrawals(update, context)

async def reject_withdraw(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    rid = q.data.split("_")[1]
    withdrawal = db["withdrawals"].find_one({"_id":ObjectId(rid), "status":"pending"})
    if not withdrawal:
        await q.message.reply_text("الطلب غير موجود.")
        return
    u = get_user(withdrawal["user_id"])
    update_user(withdrawal["user_id"], {"withdrawable_points": u.get("withdrawable_points",0) + withdrawal["points_deducted"]})
    db["withdrawals"].update_one({"_id":ObjectId(rid)}, {"$set":{"status":"rejected"}})
    try: await context.bot.send_message(withdrawal["user_id"], f"❌ تم رفض السحب. تم إعادة {withdrawal['points_deducted']} نقطة.", parse_mode="Markdown")
    except: pass
    await q.message.reply_text(f"❌ تم رفض الطلب وإعادة {withdrawal['points_deducted']} نقطة.")
    await q.message.delete()
    await admin_withdrawals(update, context)

async def admin_export(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Name","Points","Withdrawable","Uses","Referrals","Has Withdrawn","Join Date","Ads","Badges"])
    for user in users_col.find():
        try:
            name = (await context.bot.get_chat(int(user["_id"]))).first_name
        except:
            name = "Unknown"
        writer.writerow([user["_id"], name, user.get("points",0), user.get("withdrawable_points",0), user.get("uses",0), user.get("referrals",0), user.get("has_withdrawn_before",False), user.get("last_task_date",""), user.get("total_ads_watched",0), ", ".join(user.get("badges",[]))])
    output.seek(0)
    await q.message.reply_document(document=io.BytesIO(output.getvalue().encode()), filename="users_export.csv", caption="📊 تصدير البيانات")
    await q.message.reply_text("✅ تم التصدير.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]))

async def handle_nav(update, context):
    q = update.callback_query
    await q.answer()
    if q.data == "admin_back":
        await q.message.reply_text("🔧 لوحة الأدمن:", reply_markup=admin_menu())
    elif q.data in ("home","new"):
        await main_back(update, context)

# ========== تشغيل البوت ==========
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_platform, pattern="^(facebook|instagram|twitter|linkedin|email|ad|article|ideas)$"),
                      CallbackQueryHandler(weekly, pattern="^weekly$"),
                      CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")],
        states={TOPIC:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic)],
                TONE:[CallbackQueryHandler(get_tone, pattern="^tone_")],
                WEEKLY_TOPIC:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_weekly_topic)],
                BROADCAST_MSG:[MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)]},
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(CallbackQueryHandler(content_menu, pattern="^content_menu$"))
    app.add_handler(CallbackQueryHandler(earn_menu, pattern="^earn_menu$"))
    app.add_handler(CallbackQueryHandler(account_menu, pattern="^account_menu$"))
    app.add_handler(CallbackQueryHandler(main_back, pattern="^main_back$"))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(special_offers, pattern="^special_offers$"))
    app.add_handler(CallbackQueryHandler(referral, pattern="^referral$"))
    app.add_handler(CallbackQueryHandler(watch_ad, pattern="^watch_ad$"))
    app.add_handler(CallbackQueryHandler(mystery_box, pattern="^mystery_box$"))
    app.add_handler(CallbackQueryHandler(daily_tasks, pattern="^daily_tasks$"))
    app.add_handler(CallbackQueryHandler(claim_bonus, pattern="^claim_bonus$"))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern="^admin_stats$"))
    app.add_handler(CallbackQueryHandler(admin_users, pattern="^admin_users$"))
    app.add_handler(CallbackQueryHandler(admin_withdrawals, pattern="^admin_withdrawals$"))
    app.add_handler(CallbackQueryHandler(admin_export, pattern="^admin_export$"))
    app.add_handler(CallbackQueryHandler(approve_withdraw, pattern="^approve_"))
    app.add_handler(CallbackQueryHandler(reject_withdraw, pattern="^reject_"))
    app.add_handler(CallbackQueryHandler(handle_nav, pattern="^(home|new|admin_back)$"))
    app.add_handler(CallbackQueryHandler(leaderboard, pattern="^leaderboard$"))
    app.add_handler(CallbackQueryHandler(withdraw_request, pattern="^withdraw$"))
    app.run_polling()

if __name__ == "__main__":
    main()

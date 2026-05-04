# v15.0 - البوت الاحترافي الكامل (جميع الميزات + إصلاح JobQueue)
import logging, random, csv, io, asyncio
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

# URLs for different ad types (ensure these are correct)
AD_URL = "https://mostafa865.github.io/boot/ad.html"
BOX_AD_URL = "https://mostafa865.github.io/boot/box_ad.html"
BONUS_AD_URL = "https://mostafa865.github.io/boot/bonus_ad.html"
REFERRAL_AD_URL = "https://mostafa865.github.io/boot/referral_ad.html"
EARLY_AD_URL = "https://mostafa865.github.io/boot/early_ad.html"
CHALLENGE_AD_URL = "https://mostafa865.github.io/boot/challenge_ad.html"
MONTHLY_AD_URL = "https://mostafa865.github.io/boot/monthly_ad.html"


mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo["botdb"]
users_col = db["users"]
withdrawals_col = db["withdrawals"]
offers_col = db["flash_offers"]
challenges_col = db["challenges"]

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
            "weekly_mission_claimed": False, "ambassador_badge": False, "last_daily_report_date": "", "total_ads_watched": 0,
            "badges": [], "pending_action": None, "challenge_active": None, "challenge_points": 0, "last_challenge_reset": today
        }
        users_col.insert_one(user)
    else:
        updated = False
        fields = ["withdrawable_points","ad_watch_today","last_ad_date","ad_streak","ad_multiplier","last_ad_streak_date",
                  "referrer_id","referral_date","total_commission_today","last_commission_date","referred_users",
                  "referral_level2_count","total_commission_earned","has_withdrawn_before","first_withdrawal_date",
                  "weekly_mission_claimed","ambassador_badge","last_daily_report_date","total_ads_watched","badges",
                  "pending_action","early_bird_rewarded","early_bird_notified","challenge_active","challenge_points","last_challenge_reset"]
        for field in fields:
            if field not in user:
                user[field] = None if field in ["referrer_id","referral_date","first_withdrawal_date","last_daily_report_date","pending_action","challenge_active"] else (0 if field in ["total_commission_today","referral_level2_count","total_commission_earned","total_ads_watched","challenge_points"] else ([] if field=="badges" else False))
                updated = True
        if updated:
            update_user(user_id, {k: user[k] for k in fields})
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
        if data["streak_range"][0] <= streak <= data["streak_range"][1]:
            prizes = data["prizes"]
            total = sum(w for _, _, w in prizes)
            r = random.randint(1, total)
            cur = 0
            for pts, msg, w in prizes:
                cur += w
                if r <= cur:
                    return pts, msg, level
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

# ========== العروض الموقوتة ==========
def get_active_flash_offer():
    now = datetime.utcnow()
    offer = offers_col.find_one({"active": True, "start_time": {"$lte": now}, "end_time": {"$gte": now}})
    return offer

async def admin_flash_offer(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        multiplier = int(context.args[0])
        duration = int(context.args[1])
        start = datetime.utcnow()
        end = start + timedelta(minutes=duration)
        offers_col.update_one({}, {"$set": {"active": True, "multiplier": multiplier, "start_time": start, "end_time": end}}, upsert=True)
        await update.message.reply_text(f"✅ عرض موقوت: ×{multiplier} لمدة {duration} دقيقة.")
    except:
        await update.message.reply_text("استخدام: /offer <مضاعف> <مدة_دقائق>")

async def admin_stop_offer(update, context):
    if update.effective_user.id != ADMIN_ID: return
    offers_col.update_one({}, {"$set": {"active": False}})
    await update.message.reply_text("✅ تم إيقاف العرض.")

# ========== تحديات الأصدقاء ==========
async def challenge_friend(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    if u.get("challenge_active"):
        await q.message.reply_text("⚠️ لديك تحدي نشط بالفعل.")
        return
    await q.message.reply_text("أرسل معرف (@username) لصديقك:")
    context.user_data['awaiting_challenge'] = True

async def challenge_target(update, context):
    if not context.user_data.get('awaiting_challenge'):
        return
    uid = update.effective_user.id
    target_input = update.message.text.strip().lstrip('@')
    try:
        target = await context.bot.get_chat(target_input)
        target_id = target.id
    except:
        await update.message.reply_text("❌ لم أجد المستخدم.")
        return
    if target_id == uid:
        await update.message.reply_text("لا يمكنك تحدي نفسك.")
        return
    update_user(uid, {"challenge_active": target_id, "challenge_points": 0, "last_challenge_reset": datetime.utcnow().isoformat()})
    update_user(target_id, {"challenge_active": uid, "challenge_points": 0, "last_challenge_reset": datetime.utcnow().isoformat()})
    await context.bot.send_message(target_id, f"🔥 تم تحديّك من {update.effective_user.first_name}! اجمع أكبر عدد نقاط من الإعلانات خلال أسبوع. الفائز يحصل على 1000 نقطة.")
    await update.message.reply_text("✅ تم إرسال التحدي!")
    context.user_data['awaiting_challenge'] = False

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
    kb = [
        [InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad")],
        [InlineKeyboardButton("🎲 صندوق الحظ", callback_data="mystery_box")],
        [InlineKeyboardButton("📋 مهام اليوم", callback_data="daily_tasks")],
        [InlineKeyboardButton("🎁 دعوة صديق", callback_data="referral_share")],
        [InlineKeyboardButton("⚔️ تحدي صديق", callback_data="challenge_friend")],
        [InlineKeyboardButton("🎁 عروض خاصة", callback_data="special_offers")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]
    ]
    await q.edit_message_text("💰 *كسب النقاط*\nاختر طريقة:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def account_menu(update, context):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)
    ambassador = "🏅 *سفير البوت* 🏅\n" if u.get("ambassador_badge") else ""
    badges_text = "🏅 *الشارات:* " + ", ".join(u.get("badges", [])) if u.get("badges") else "🏅 *الشارات:* لا توجد"
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
            f"📊 إجمالي الإعلانات: *{u.get('total_ads_watched',0)}*\n🎲 غداً صندوقك: *{next_level}*\n\n{badges_text}\n\n"
            f"📺 كل إعلان: +{POINTS_PER_AD} نقطة × المضاعف (حد {MAX_ADS_PER_DAY}/يوم)\n"
            f"🎁 كل دعوة مباشرة: +{REFERRAL_WITHDRAWABLE} نقطة + {REFERRAL_COMMISSION_PERCENT}% عمولة\n"
            f"🎁 كل دعوة غير مباشرة: +{REFERRAL_LEVEL2} نقطة\n"
            f"💰 التحويل: {POINTS_PER_DOLLAR} نقطة = $1\n🏧 حد السحب: {MIN_WITHDRAW_POINTS} نقطة (${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR})")
    kb = [[InlineKeyboardButton("💰 سحب النقاط", callback_data="withdraw")], [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def help_callback(update, context):
    q = update.callback_query
    await q.answer()
    text = (f"ℹ️ *تعليمات البوت*\n\n"
            f"1️⃣ شاهد إعلانات يومياً (حد {MAX_ADS_PER_DAY}).\n"
            f"2️⃣ Streak: كل يوم يزيد المضاعف 5% حتى 2x.\n"
            f"3️⃣ صندوق الحظ المتطور (فضة/ذهب/ألماس) حسب Streak.\n"
            f"4️⃣ المهام اليومية: إعلان + استخدام = 300 نقطة بونص (يتطلب إعلاناً).\n"
            f"5️⃣ الإحالات: مكافأة {REFERRAL_WITHDRAWABLE} لكل مدعو مباشر، وعمولة {REFERRAL_COMMISSION_PERCENT}% من أرباح إعلاناته.\n"
            f"6️⃣ المسابقة الأسبوعية: كل إثنين جوائز لأكثر 10.\n"
            f"7️⃣ مهمة أسبوعية: {WEEKLY_MISSION_TARGET} إعلان ↔ {WEEKLY_MISSION_REWARD} نقطة.\n"
            f"8️⃣ تحدي الأصدقاء: تحدَّ صديقاً والفائز يحصل على 1000 نقطة.\n"
            f"9️⃣ شارات: المدعو الأول، سفير، 100 إعلان، السبوعي، الأسطورة.\n"
            f"🔟 مكافأة التسجيل المبكر: أول {EARLY_BIRD_LIMIT} مستخدم يحصلون على {EARLY_BIRD_POINTS} نقطة (إعلان).\n"
            f"1️⃣1️⃣ العروض الموقوتة: يعلن الأدمن عن مضاعفات محدودة.\n"
            f"1️⃣2️⃣ مسابقة شهرية: أعلى رصيد يحصل على 50$.")
    kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def main_back(update, context):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)
    await q.edit_message_text(f"👋 أهلاً *{q.from_user.first_name}*!\n✨ نقاط عادية: *{u['points']}*\n💰 نقاط قابلة للسحب: *{u.get('withdrawable_points',0)}*\n\n👇 اختر من القائمة:", parse_mode="Markdown", reply_markup=main_menu())

async def special_offers(update, context):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)
    flash = get_active_flash_offer()
    text = "🎁 *العروض الخاصة*\n\n"
    if u.get("early_bird_rewarded") and not u.get("early_bird_notified"):
        if not u.get("pending_action"):
            update_user(q.from_user.id, {"pending_action": {"type": "early_bird", "points": EARLY_BIRD_POINTS}})
        text += f"✅ *أنت من أوائل المستخدمين!* لديك {EARLY_BIRD_POINTS} نقطة.\nشاهد إعلاناً.\n\n"
    if flash:
        text += f"🔥 *عرض موقوت نشط!* مضاعف ×{flash['multiplier']} لمدة {int((flash['end_time']-datetime.utcnow()).total_seconds()/60)} دقيقة.\n"
    if not text.strip():
        text += "لا توجد عروض حالياً."
    kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="earn_menu")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# روابط دعوات مخصصة
async def referral_share(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    link = f"https://t.me/easy_free1bot?start=ref_{uid}"
    whatsapp = f"https://wa.me/?text=اشترك في هذا البوت واكسب نقاطاً: {link}"
    telegram = f"https://t.me/share/url?url={link}&text=انضم إلي"
    facebook = f"https://www.facebook.com/sharer/sharer.php?u={link}"
    twitter = f"https://twitter.com/intent/tweet?text=اكسب نقاطاً مع هذا البوت&url={link}"
    kb = [
        [InlineKeyboardButton("📱 واتساب", url=whatsapp), InlineKeyboardButton("✈️ تليجرام", url=telegram)],
        [InlineKeyboardButton("📘 فيسبوك", url=facebook), InlineKeyboardButton("🐦 تويتر", url=twitter)],
        [InlineKeyboardButton("📋 نسخ الرابط", callback_data="copy_link")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="earn_menu")]
    ]
    await q.edit_message_text(f"🎁 *رابط دعوتك:*\n`{link}`\n\nاختر المنصة:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def copy_link(update, context):
    q = update.callback_query
    await q.answer()
    link = f"https://t.me/easy_free1bot?start=ref_{q.from_user.id}"
    await q.message.reply_text(f"✅ تم نسخ الرابط:\n`{link}`", parse_mode="Markdown")

# دوال المحتوى (مبسطة)
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

# دوال البوت الأساسية
async def start(update, context):
    user = update.effective_user
    uid = user.id
    name = user.first_name

    # معالجة الإحالات
    if context.args and context.args[0].startswith("ref_"):
        ref_id = context.args[0].replace("ref_", "")
        if ref_id != str(uid):
            referrer = get_user(int(ref_id))
            if get_user(uid).get("referrer_id") is None:
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
                    try: await context.bot.send_message(int(ref_id), "🏅 شارة سفير البوت!", parse_mode="Markdown")
                    except: pass

    if uid == ADMIN_ID:
        await update.message.reply_text(f"👋 أهلاً *{name}* — لوحة الأدمن 🔧", parse_mode="Markdown", reply_markup=admin_menu())
        return

    u = get_user(uid)
    if u.get("early_bird_rewarded") and not u.get("early_bird_notified") and not u.get("pending_action"):
        update_user(uid, {"pending_action": {"type": "early_bird", "points": EARLY_BIRD_POINTS}})
        await update.message.reply_text(f"🎉 *أنت من أوائل المستخدمين!* لديك {EARLY_BIRD_POINTS} نقطة.\nشاهد إعلاناً لاستلامها 👇", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎁 استلام", web_app=WebAppInfo(url=AD_URL))]]))
    else:
        await update.message.reply_text(f"👋 أهلاً *{name}*!\n✨ نقاط عادية: *{u['points']}*\n💰 نقاط قابلة للسحب: *{u.get('withdrawable_points',0)}*\n\n👇 اختر من القائمة:", parse_mode="Markdown", reply_markup=main_menu())

# دوال المحتوى (AI)
async def handle_platform(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = check_daily_tasks(get_user(uid))
    update_user(uid, {"tasks": u["tasks"], "last_task_date": u["last_task_date"]})
    if u["points"] < POINTS_PER_USE:
        await q.message.reply_text(f"❌ نقاطك مش كافية! رصيدك: {u['points']}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad")]]))
        return ConversationHandler.END
    platforms = {"facebook":"📘 بوست فيسبوك","instagram":"📸 كابشن انستجرام","twitter":"🐦 تويت تويتر","linkedin":"💼 بوست لينكدإن","email":"📧 إيميل","ad":"🎯 إعلان","article":"✍️ مقال","ideas":"💡 أفكار"}
    context.user_data['platform'] = platforms[q.data]
    context.user_data['platform_key'] = q.data
    await q.edit_message_text(f"✅ اخترت: *{platforms[q.data]}*\n\n📝 اكتب موضوع المحتوى:", parse_mode="Markdown")
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
    await q.edit_message_text("⏳ جاري الكتابة...")
    uid = q.from_user.id
    u = check_daily_tasks(get_user(uid))
    u["tasks"]["used"] = True
    new_pts = u["points"] - POINTS_PER_USE
    update_user(uid, {"points": new_pts, "uses": u["uses"]+1, "tasks": u["tasks"], "last_task_date": u["last_task_date"]})
    prompts = {
        "facebook": f"بوست فيسبوك عن '{topic}' بأسلوب {tone}.",
        "instagram": f"كابشن انستجرام عن '{topic}' بأسلوب {tone}.",
        "twitter": f"تويت عن '{topic}' بأسلوب {tone}.",
        "linkedin": f"بوست لينكدإن عن '{topic}' بأسلوب {tone}.",
        "email": f"إيميل عن '{topic}' بأسلوب {tone}.",
        "ad": f"إعلان عن '{topic}' بأسلوب {tone}.",
        "article": f"مقال قصير عن '{topic}' بأسلوب {tone}.",
        "ideas": f"5 أفكار محتوى عن '{topic}'."
    }
    prompt = prompts.get(key, f"محتوى عن '{topic}'.")
    try:
        r = client.chat.completions.create(model="gpt-oss-120b", messages=[{"role":"system","content":"كاتب محتوى محترف"},{"role":"user","content":prompt}])
        content = r.choices[0].message.content
        await q.message.reply_text(f"✅ *المحتوى جاهز:*\n\n{content}\n\n━━━━━━━━━━\n💎 رصيدك المتبقي: *{new_pts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
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
        r = client.chat.completions.create(model="gpt-oss-120b", messages=[{"role":"system","content":"كاتب محتوى"},{"role":"user","content":f"7 بوستات تيليجرام عن '{topic}'"}]),
        content = r.choices[0].message.content
        await update.message.reply_text(f"✅ *بوستات الأسبوع:*\n\n{content}\n💎 رصيدك المتبقي: *{new_pts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)[:100]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    return ConversationHandler.END

# دوال الإعلانات والمكافآت
    async def handle_web_app_data(update, context):
    print("🔥🔥🔥 WebApp data received! 🔥🔥🔥")
    data = update.message.web_app_data.data
    print(f"Data: {data}")
    data = update.message.web_app_data.data
    uid = update.effective_user.id
    if data == "ad_watched":
        u = get_user(uid)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if u.get("last_ad_date") != today:
            update_user(uid, {"ad_watch_today": 0, "last_ad_date": today})
            u["ad_watch_today"] = 0
        if u.get("ad_watch_today",0) >= MAX_ADS_PER_DAY:
            await update.message.reply_text(f"❌ الحد اليومي {MAX_ADS_PER_DAY}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
            return
        flash = get_active_flash_offer()
        mul = update_ad_streak(uid, today)
        multiplier = flash["multiplier"] if flash else 1
        earned = int(POINTS_PER_AD * mul * multiplier)
        new_w = u["withdrawable_points"] + earned
        new_cnt = u["ad_watch_today"] + 1
        new_total = u.get("total_ads_watched",0) + 1
        update_user(uid, {"withdrawable_points": new_w, "ad_watch_today": new_cnt, "last_ad_date": today, "total_ads_watched": new_total})
        if new_total >= 100 and "100 إعلان" not in u.get("badges",[]):
            add_badge(uid, "100 إعلان")
            try: await context.bot.send_message(uid, "🏅 شارة 100 إعلان!", parse_mode="Markdown")
            except: pass
        # تحديث تحدي الأصدقاء
        if u.get("challenge_active"):
            update_user(uid, {"challenge_points": u.get("challenge_points",0) + earned})
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
                comm = int(earned * REFERRAL_COMMISSION_PERCENT / 100)
                if comm > 0 and can_add_commission(rid, comm):
                    ref = get_user(rid)
                    update_user(rid, {"withdrawable_points": ref["withdrawable_points"] + comm, "total_commission_earned": ref.get("total_commission_earned",0) + comm})
                    try: await context.bot.send_message(rid, f"🎁 عمولة إحالة: +{comm} نقطة!", parse_mode="Markdown")
                    except: pass
        u2 = check_daily_tasks(get_user(uid))
        u2["tasks"]["ad"] = True
        update_user(uid, {"tasks": u2["tasks"]})
        await update.message.reply_text(f"✅ *+{earned} نقطة!*\n💎 رصيدك: *{new_w}*\n🔥 مضاعف: {mul}x\n📊 اليوم: {new_cnt}/{MAX_ADS_PER_DAY}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
        # معالجة الإجراءات المعلقة
        pending = u.get("pending_action")
        if pending:
            if pending["type"] == "early_bird":
                update_user(uid, {"withdrawable_points": u["withdrawable_points"] + pending["points"], "early_bird_notified": True, "pending_action": None})
                await update.message.reply_text(f"🎉 هدية التسجيل المبكر! +{pending['points']} نقطة.", parse_mode="Markdown")
            elif pending["type"] == "claim_bonus":
                u3 = check_daily_tasks(get_user(uid))
                if not u3["tasks"].get("bonus"):
                    update_user(uid, {"points": u3["points"] + 300, "tasks": {**u3["tasks"], "bonus": True}, "pending_action": None})
                    await update.message.reply_text("🎉 بونص المهام اليومية! +300 نقطة.", parse_mode="Markdown")
                else:
                    update_user(uid, {"pending_action": None})
      
    
    elif data == "bonus_ad_watched":
        u = get_user(uid)
        pending = u.get("pending_action")
        if pending and pending.get("type") == "claim_bonus":
            u2 = check_daily_tasks(u)
            if not u2["tasks"].get("bonus", False):
                new_pts = u2["points"] + 300
                u2["tasks"]["bonus"] = True
                update_user(uid, {"points": new_pts, "tasks": u2["tasks"], "pending_action": None})
                await update.message.reply_text("🎉 تم إضافة 300 نقطة بونص!", parse_mode="Markdown")
            else:
                update_user(uid, {"pending_action": None})
                await update.message.reply_text("⚠️ تم استلام البونص مسبقاً.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ لا يوجد بونص معلق.", parse_mode="Markdown")

    elif data == "referral_ad_watched":
        u = get_user(uid)
        pending = u.get("pending_action")
        if pending and pending.get("type") == "referral_reward":
            points = pending.get("points", REFERRAL_WITHDRAWABLE)
            new_w = u["withdrawable_points"] + points
            update_user(uid, {"withdrawable_points": new_w, "pending_action": None})
            await update.message.reply_text(f"🎉 تم إضافة {points} نقطة قابلة للسحب (مكافأة إحالة)!", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ لا توجد مكافأة إحالة معلقة.", parse_mode="Markdown")

    elif data == "early_ad_watched":
        u = get_user(uid)
        pending = u.get("pending_action")
        if pending and pending.get("type") == "early_bird":
            points = pending.get("points", EARLY_BIRD_POINTS)
            new_w = u["withdrawable_points"] + points
            update_user(uid, {"withdrawable_points": new_w, "early_bird_notified": True, "pending_action": None})
            await update.message.reply_text(f"🎉 تم استلام هدية التسجيل المبكر! +{points} نقطة قابلة للسحب.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ لا توجد هدية معلقة.", parse_mode="Markdown")

    elif data == "challenge_ad_watched":
        u = get_user(uid)
        pending = u.get("pending_action")
        if pending and pending.get("type") == "challenge_reward":
            points = pending.get("points", 1000)
            new_w = u["withdrawable_points"] + points
            update_user(uid, {"withdrawable_points": new_w, "pending_action": None})
            await update.message.reply_text(f"🏆 فزت في التحدي! +{points} نقطة قابلة للسحب.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ لا توجد جائزة تحدٍ معلقة.", parse_mode="Markdown")

    elif data == "monthly_ad_watched":
        u = get_user(uid)
        pending = u.get("pending_action")
        if pending and pending.get("type") == "monthly_contest":
            points = pending.get("points", 50 * POINTS_PER_DOLLAR)
            new_w = u["withdrawable_points"] + points
            update_user(uid, {"withdrawable_points": new_w, "pending_action": None})
            await update.message.reply_text(f"🏆 فزت في المسابقة الشهرية! +{points} نقطة قابلة للسحب.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ لا توجد جائزة شهرية معلقة.", parse_mode="Markdown")


async def mystery_box(update, context):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)
    if u.get("last_box_date") == datetime.utcnow().strftime("%Y-%m-%d"):
        await q.message.reply_text("❌ فتحت الصندوق اليوم!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
        return
    streak = u.get("ad_streak",0)
    level = "فضة"
    for lvl, data in BOX_LEVELS.items():
        if data["streak_range"][0] <= streak <= data["streak_range"][1]:
            level = lvl
            break
    await q.message.reply_text(f"🎲 *صندوق {level}* 🎲\n🔥 Streak: {streak}\n⚠️ شاهد الإعلان أولاً:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"🎁 افتح صندوق {level}", web_app=WebAppInfo(url=BOX_AD_URL))]]))

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
        text += "\n\n🎁 *300 نقطة بونص* (يتطلب إعلاناً)"
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
        # تخزين إجراء معلق
        update_user(uid, {"pending_action": {"type": "claim_bonus"}})
        await q.message.reply_text(
            "🎁 *بونص يومي*\nشاهد إعلاناً لاستلام 300 نقطة عادية 👇",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📺 شاهد الإعلان واستلم البونص", web_app=WebAppInfo(url=BONUS_AD_URL))]
            ])
        )
    else:
        await q.message.reply_text("❌ لم تكمل المهام أو استلمت البونص مسبقاً!")
      
async def withdraw_request(update, context):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)
    w = u.get("withdrawable_points",0)
    if w < MIN_WITHDRAW_POINTS:
        need = MIN_WITHDRAW_POINTS - w
        await q.message.reply_text(f"💰 *السحب*\nرصيدك: {w}\nتحتاج {need} نقطة.", parse_mode="Markdown")
        return
    amt = w // POINTS_PER_DOLLAR
    deduct = amt * POINTS_PER_DOLLAR
    new_w = w - deduct
    update_user(q.from_user.id, {"withdrawable_points": new_w})
    if not u.get("has_withdrawn_before"):
        update_user(q.from_user.id, {"has_withdrawn_before": True, "first_withdrawal_date": datetime.utcnow().isoformat()})
        new_w += 1000
        update_user(q.from_user.id, {"withdrawable_points": new_w})
        await q.message.reply_text("🎁 هدية أول سحب! +1000 نقطة.", parse_mode="Markdown")
    req = {"user_id": q.from_user.id, "points_deducted": deduct, "amount_usd": amt, "status": "pending", "date": datetime.utcnow().isoformat()}
    db["withdrawals"].insert_one(req)
    await context.bot.send_message(ADMIN_ID, f"💰 طلب سحب: {q.from_user.first_name} - {amt}$", parse_mode="Markdown")
    await q.message.reply_text(f"💰 تم إرسال طلب {amt}$. سيتم مراجعته.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))

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
        kb.append([InlineKeyboardButton(f"✅ قبول", callback_data=f"approve_{rid}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_{rid}")])
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
    writer.writerow(["ID","Name","Points","Withdrawable","Uses","Referrals","Withdrawn","Join Date","Ads","Badges"])
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

# ========== المهام المجدولة (باستخدام asyncio sleep لتجنب JobQueue) ==========
async def scheduled_tasks(app):
    while True:
        now = datetime.utcnow()
        # إشعار يومي الساعة 9 صباحاً
        if now.hour == 9 and now.minute == 0:
            for user in users_col.find():
                try:
                    uid = int(user["_id"])
                    u = get_user(uid)
                    await app.bot.send_message(uid, f"🔥 *تذكير يومي*\nStreak: {u.get('ad_streak',0)} يوم\nشاهد إعلانك الأول اليوم!", parse_mode="Markdown")
                except: pass
        # تقرير يومي الساعة 11 مساءً
        if now.hour == 23 and now.minute == 0:
            for user in users_col.find():
                try:
                    uid = int(user["_id"])
                    u = get_user(uid)
                    if u.get("last_daily_report_date") != now.strftime("%Y-%m-%d"):
                        await app.bot.send_message(uid, f"📊 *تقرير يومي*\nرصيدك القابل للسحب: {u.get('withdrawable_points',0)}\nإعلانات اليوم السابق: {u.get('ad_watch_today',0)}", parse_mode="Markdown")
                        update_user(uid, {"last_daily_report_date": now.strftime("%Y-%m-%d")})
                except: pass
        # إعلان فوز المتصدر الساعة 8 مساءً
        if now.hour == 20 and now.minute == 0:
            users = list(users_col.find({}, {"_id":1,"points":1,"withdrawable_points":1}))
            if users:
                for u in users: u["total"] = u.get("points",0)+u.get("withdrawable_points",0)
                users.sort(key=lambda x: x["total"], reverse=True)
                top = users[0]
                try:
                    name = (await app.bot.get_chat(int(top["_id"]))).first_name
                except:
                    name = "مستخدم"
                for user in users_col.find():
                    try:
                        await app.bot.send_message(int(user["_id"]), f"🏆 *فوز اليوم*\nالمتصدر: {name} بـ {top['total']} نقطة!", parse_mode="Markdown")
                    except: pass
        # المسابقة الأسبوعية يوم الاثنين الساعة 00:00
        if now.weekday() == 0 and now.hour == 0 and now.minute == 0:
            stats = []
            for user in users_col.find():
                cnt = user.get("weekly_ad_count",0)
                if cnt > 0:
                    stats.append({"user_id": user["_id"], "count": cnt})
            stats.sort(key=lambda x: x["count"], reverse=True)
            prizes = [5000,3000,1500,500,500,500,500,500,500,500]
            for idx, entry in enumerate(stats[:10]):
                prize = prizes[idx] if idx < len(prizes) else 500
                update_user(entry["user_id"], {"withdrawable_points": get_user(entry["user_id"])["withdrawable_points"] + prize})
                add_badge(entry["user_id"], "السبوعي")
                try:
                    await app.bot.send_message(int(entry["user_id"]), f"🏆 المسابقة الأسبوعية: المركز {idx+1} +{prize} نقطة!", parse_mode="Markdown")
                except: pass
            users_col.update_many({}, {"$set": {"weekly_ad_count": 0, "last_contest_week": now.strftime("%Y-%W"), "weekly_mission_claimed": False}})
        # مسابقة شهرية في أول يوم من الشهر
        if now.day == 1 and now.hour == 0 and now.minute == 0:
            top_user = None
            top_points = 0
            for user in users_col.find():
                wp = user.get("withdrawable_points",0)
                if wp > top_points:
                    top_points = wp
                    top_user = user["_id"]
            if top_user:
                update_user(top_user, {"pending_action": {"type": "monthly_contest", "points": 50 * POINTS_PER_DOLLAR}})
                try:
                    await app.bot.send_message(int(top_user), f"🏆 مسابقة الشهر: أعلى رصيد {top_points} نقطة. شاهد إعلاناً لاستلام 50$.", parse_mode="Markdown")
                except: pass
        # تحديات الأصدقاء (كل ساعة)
        for user in users_col.find({"challenge_active": {"$ne": None}}):
            u = user
            last = u.get("last_challenge_reset")
            if last and (now - datetime.fromisoformat(last)).days >= 7:
                partner_id = u["challenge_active"]
                u_points = u.get("challenge_points",0)
                partner = get_user(partner_id)
                p_points = partner.get("challenge_points",0)
                winner = u["_id"] if u_points > p_points else (partner_id if p_points > u_points else None)
                if winner:
                    update_user(winner, {"pending_action": {"type": "challenge_reward", "points": 1000}})
                    try:
                        await app.bot.send_message(int(winner), f"🎉 فزت في تحدي الأصدقاء! شاهد إعلاناً لاستلام 1000 نقطة.", parse_mode="Markdown")
                    except: pass
                update_user(u["_id"], {"challenge_active": None, "challenge_points": 0, "last_challenge_reset": now.isoformat()})
                update_user(partner_id, {"challenge_active": None, "challenge_points": 0, "last_challenge_reset": now.isoformat()})
        await asyncio.sleep(60)  # فحص كل دقيقة

# ========== تشغيل البوت ==========
def main():
   app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
   app = Application.builder().token(TELEGRAM_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_platform, pattern="^(facebook|instagram|twitter|linkedin|email|ad|article|ideas)$"),
                      CallbackQueryHandler(weekly, pattern="^weekly$"),
                      CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$"),
                      MessageHandler(filters.TEXT & ~filters.COMMAND, challenge_target)],
        states={TOPIC:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic)],
                TONE:[CallbackQueryHandler(get_tone, pattern="^tone_")],
                WEEKLY_TOPIC:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_weekly_topic)],
                BROADCAST_MSG:[MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)]},
        fallbacks=[CommandHandler("start", start)]
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("offer", admin_flash_offer))
    app.add_handler(CommandHandler("stopoffer", admin_stop_offer))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(CallbackQueryHandler(content_menu, pattern="^content_menu$"))
    app.add_handler(CallbackQueryHandler(earn_menu, pattern="^earn_menu$"))
    app.add_handler(CallbackQueryHandler(account_menu, pattern="^account_menu$"))
    app.add_handler(CallbackQueryHandler(main_back, pattern="^main_back$"))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^help$"))
    app.add_handler(CallbackQueryHandler(special_offers, pattern="^special_offers$"))
    app.add_handler(CallbackQueryHandler(referral_share, pattern="^referral_share$"))
    app.add_handler(CallbackQueryHandler(copy_link, pattern="^copy_link$"))
    app.add_handler(CallbackQueryHandler(challenge_friend, pattern="^challenge_friend$"))
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

    # تشغيل المهام المجدولة في الخلفية (بدلاً من JobQueue)
    loop = asyncio.get_event_loop()
    loop.create_task(scheduled_tasks(app))

    app.run_polling()

if __name__ == "__main__":
    main()

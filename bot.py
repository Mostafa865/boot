# v12.0 - البوت الاحترافي الكامل (قوائم منظمة + إحالات متقدمة + صندوق متطور + شارات + كوبونات أوائل + كل المكاسب بإعلانات)
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

# ========== الثوابت الأساسية ==========
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

# ========== صندوق الحظ المتطور (حسب الـ streak) ==========
BOX_LEVELS = {
    "فضة": {"streak_range": (1,5), "prizes": [(50, "😐 حظك عادي", 50), (100, "🙂 مش بطال", 25), (200, "😊 كويس", 25)]},
    "ذهب": {"streak_range": (6,10), "prizes": [(200, "😊 كويس", 40), (350, "🙂 حلو", 35), (500, "🔥 ممتاز", 25)]},
    "ألماس": {"streak_range": (11,100), "prizes": [(500, "🔥 ممتاز", 40), (1000, "🎉 رائع", 35), (2000, "🏆 جاكبوت", 25)]}
}

AD_URL = "https://mostafa865.github.io/boot/ad.html"
BOX_AD_URL = "https://mostafa865.github.io/boot/box_ad.html"

MYSTERY_BOX_PRIZES = [(50,"😐 حظك عادي",50),(100,"🙂 مش بطال",25),(200,"😊 كويس",15),(500,"🔥 حظك حلو",8),(1000,"🎉 جاكبوت",2)]  # للاحتفاظ بالتوافق القديم

mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo["botdb"]
users_col = db["users"]
withdrawals_col = db["withdrawals"]

client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

TOPIC, TONE, WEEKLY_TOPIC, BROADCAST_MSG = range(4)

# ========== دوال قاعدة البيانات المتطورة ==========
def get_user(user_id):
    uid = str(user_id)
    user = users_col.find_one({"_id": uid})
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if not user:
        # تحديد ما إذا كان من أوائل المستخدمين
        total_before = users_col.count_documents({})
        early_bird = total_before < EARLY_BIRD_LIMIT
        user = {
            "_id": uid,
            "points": 300,
            "withdrawable_points": 0,          # لن نضيف المكافأة فوراً، بل عبر إعلان
            "early_bird_rewarded": early_bird,   # سيتم صرفها لاحقاً بإعلان
            "early_bird_notified": False,
            "uses": 0,
            "referrals": 0,
            "referrer_id": None,
            "referral_date": None,
            "total_commission_today": 0,
            "last_commission_date": "",
            "referred_users": [],
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
            "weekly_mission_claimed": False,
            "ambassador_badge": False,
            "last_daily_report_date": "",
            "total_ads_watched": 0,            # إجمالي الإعلانات لمشاهدة 100 إعلان
            "badges": [],                       # قائمة بالشارات
            "pending_action": None              # إجراء معلق (مكافأة تحتاج إعلان)
        }
        users_col.insert_one(user)
    else:
        updated = False
        for field in ["withdrawable_points","ad_watch_today","last_ad_date","ad_streak","ad_multiplier","last_ad_streak_date"]:
            if field not in user:
                user[field] = 0 if field in ["withdrawable_points","ad_watch_today","ad_streak"] else (1.0 if field=="ad_multiplier" else "")
                updated = True
        for field in ["referrer_id","referral_date","total_commission_today","last_commission_date","referred_users","referral_level2_count","total_commission_earned","has_withdrawn_before","first_withdrawal_date","weekly_mission_claimed","ambassador_badge","last_daily_report_date","total_ads_watched","badges","pending_action","early_bird_rewarded","early_bird_notified"]:
            if field not in user:
                user[field] = None if field in ["referrer_id","referral_date","first_withdrawal_date","last_daily_report_date","pending_action"] else (0 if field in ["total_commission_today","referral_level2_count","total_commission_earned","total_ads_watched"] else ([] if field=="badges" else False))
                updated = True
        if updated:
            update_user(user_id, {k: user[k] for k in ["withdrawable_points","ad_watch_today","last_ad_date","ad_streak","ad_multiplier","last_ad_streak_date","referrer_id","referral_date","total_commission_today","last_commission_date","referred_users","referral_level2_count","total_commission_earned","has_withdrawn_before","first_withdrawal_date","weekly_mission_claimed","ambassador_badge","last_daily_report_date","total_ads_watched","badges","pending_action","early_bird_rewarded","early_bird_notified"]})
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
    # شارة الأسطورة (Streak 30)
    if cur >= 30 and "الأسطورة" not in user.get("badges",[]):
        add_badge(user_id, "الأسطورة")
    return mul

def spin_mystery_box(streak):
    """تحديد مستوى الصندوق وسحب جائزة عشوائية حسب الـ streak"""
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
    # افتراضي (فضة)
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

# ========== القوائم المنظمة ==========
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
    kb = [
        [InlineKeyboardButton("📘 بوست فيسبوك", callback_data="facebook"), InlineKeyboardButton("📸 كابشن انستجرام", callback_data="instagram")],
        [InlineKeyboardButton("🐦 تويت تويتر", callback_data="twitter"), InlineKeyboardButton("💼 بوست لينكدإن", callback_data="linkedin")],
        [InlineKeyboardButton("📧 إيميل احترافي", callback_data="email"), InlineKeyboardButton("🎯 إعلان تسويقي", callback_data="ad")],
        [InlineKeyboardButton("✍️ مقال قصير", callback_data="article"), InlineKeyboardButton("💡 أفكار محتوى", callback_data="ideas")],
        [InlineKeyboardButton("📅 جدولة محتوى أسبوعي", callback_data="weekly")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]
    ]
    await q.edit_message_text("✍️ *اختر نوع المحتوى:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def earn_menu(update, context):
    q = update.callback_query
    await q.answer()
    kb = [
        [InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad")],
        [InlineKeyboardButton("🎲 صندوق الحظ", callback_data="mystery_box")],
        [InlineKeyboardButton("📋 مهام اليوم", callback_data="daily_tasks")],
        [InlineKeyboardButton("🎁 دعوة صديق", callback_data="referral")],
        [InlineKeyboardButton("🎁 عروض خاصة", callback_data="special_offers")],
        [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]
    ]
    await q.edit_message_text("💰 *كسب النقاط*\nاختر طريقة:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def account_menu(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    ambassador = "🏅 *سفير البوت* 🏅\n" if u.get("ambassador_badge") else ""
    badges_text = "🏅 *الشارات:* " + ", ".join(u.get("badges", [])) if u.get("badges") else "🏅 *الشارات:* لا توجد شارات بعد"
    # تحديد مستوى الصندوق ليوم غد بناءً على streak+1
    next_streak = u.get("ad_streak",0) + 1
    next_level = "فضة"
    for lvl, data in BOX_LEVELS.items():
        min_s, max_s = data["streak_range"]
        if min_s <= next_streak <= max_s:
            next_level = lvl
            break
    text = (f"👤 *حسابي*\n\n{ambassador}"
            f"✨ نقاط عادية: *{u['points']}*\n💰 نقاط قابلة للسحب: *{u.get('withdrawable_points',0)}*\n"
            f"✍️ استخدامات: *{u['uses']}*\n🎁 دعوات مباشرة: *{u['referrals']}*\n"
            f"🎁 دعوات غير مباشرة: *{u.get('referral_level2_count',0)}*\n🔥 Streak: *{u.get('ad_streak',0)} يوم* (مضاعف {u.get('ad_multiplier',1.0)}x)\n"
            f"📊 إجمالي الإعلانات: *{u.get('total_ads_watched',0)}*\n"
            f"🎲 غداً سيكون صندوقك: *{next_level}*\n\n"
            f"{badges_text}\n\n"
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
            f"5️⃣ *الإحالات المتقدمة*: ادعو أصدقاءك – مكافأة فورية {REFERRAL_WITHDRAWABLE} نقطة لكل مدعو مباشر (تتطلب إعلاناً)، و{REFERRAL_LEVEL2} لكل مدعو غير مباشر، و{REFERRAL_COMMISSION_PERCENT}% من أرباح إعلانات مدعويك لمدة 30 يوم.\n"
            f"6️⃣ *المسابقة الأسبوعية*: كل إثنين، أفضل 10 مستخدمين في عدد الإعلانات يحصلون على جوائز تصل إلى 5000 نقطة.\n"
            f"7️⃣ *مهمة أسبوعية*: شاهد {WEEKLY_MISSION_TARGET} إعلاناً في الأسبوع ↔ {WEEKLY_MISSION_REWARD} نقطة قابلة للسحب (تتطلب إعلاناً؟ لا، نصرف فوراً).\n"
            f"8️⃣ *السحب*: تجميع {MIN_WITHDRAW_POINTS} نقطة = ${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR}، اطلب السحب وتراجع إدارياً.\n"
            f"9️⃣ *شارات*: احصل على شارات (المدعو الأول، السفير، 100 إعلان، السبوعي، الأسطورة) تظهر في حسابك.\n"
            f"🔟 *مكافأة التسجيل المبكر*: أول {EARLY_BIRD_LIMIT} مستخدم يحصلون على {EARLY_BIRD_POINTS} نقطة قابلة للسحب (تتطلب إعلاناً لصرفها).\n\n"
            f"*استمر في جمع النقاط وادعُ أصدقاءك لتربح أكثر!*")
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
    uid = q.from_user.id
    u = get_user(uid)
    early_bird = u.get("early_bird_rewarded", False) and not u.get("early_bird_notified", False)
    text = "🎁 *العروض الخاصة*\n\n"
    if early_bird:
        text += f"✅ *أنت من أوائل المستخدمين!*\nلديك {EARLY_BIRD_POINTS} نقطة قابلة للسحب في انتظارك.\nشاهد إعلاناً لاستلامها.\n\n"
        # هنا نضع إجراء معلق
        if not u.get("pending_action"):
            update_user(uid, {"pending_action": {"type": "early_bird", "points": EARLY_BIRD_POINTS}})
            text += "👇 اضغط الزر أدناه لاستلام هديتك."
            kb = [[InlineKeyboardButton("🎁 استلام هدية التسجيل المبكر", web_app=WebAppInfo(url=AD_URL))]]
        else:
            kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="earn_menu")]]
    else:
        text += "❌ *عذراً، لم تكن من أوائل المستخدمين.*\nالعرض متاح لأول 100 مستخدم فقط.\n"
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

# ========== أوامر البوت الأساسية ==========
async def check_subscription(user_id, bot):
    return True  # يمكن تفعيل التحقق لاحقاً

async def start(update, context):
    user = update.effective_user
    uid = user.id
    name = user.first_name

    # معالجة الإحالات المتقدمة
    if context.args and context.args[0].startswith("ref_"):
        ref_id = context.args[0].replace("ref_", "")
        if ref_id != str(uid):
            referrer = get_user(int(ref_id))
            new_user = get_user(uid)
            if new_user.get("referrer_id") is None:
                # ربط المستخدم الجديد بالمُحيل
                update_user(uid, {"referrer_id": int(ref_id), "referral_date": datetime.utcnow().isoformat()})
                # مكافأة المستوى الأول (تتطلب إعلاناً) – نضع إجراء معلق
                update_user(int(ref_id), {"pending_action": {"type": "referral_reward", "points": REFERRAL_WITHDRAWABLE}})
                # إشعار للمُحيل المباشر
                try:
                    await context.bot.send_message(int(ref_id), f"🎉 صديق جديد انضم عن طريقك!\nلديك *{REFERRAL_WITHDRAWABLE} نقطة قابلة للسحب* في انتظارك.\nشاهد إعلاناً لاستلامها.", parse_mode="Markdown")
                except: pass
                # تحديث قائمة المدعوين
                update_user(int(ref_id), {"referrals": referrer["referrals"] + 1, "referred_users": referrer.get("referred_users", []) + [uid]})
                # شارة المدعو الأول
                if referrer["referrals"] == 0:
                    if add_badge(int(ref_id), "المدعو الأول"):
                        try:
                            await context.bot.send_message(int(ref_id), "🏅 *مبروك! حصلت على شارة المدعو الأول!* 🏅", parse_mode="Markdown")
                        except: pass
                # مكافأة المستوى الثاني (تتطلب إعلاناً أيضاً)
                upline_id = referrer.get("referrer_id")
                if upline_id:
                    update_user(upline_id, {"pending_action": {"type": "referral_level2_reward", "points": REFERRAL_LEVEL2}})
                    update_user(upline_id, {"referral_level2_count": referrer.get("referral_level2_count", 0) + 1})
                    try:
                        await context.bot.send_message(upline_id, f"🎉 مدعو غير مباشر (من شخص دعوته) انضم!\nلديك *{REFERRAL_LEVEL2} نقطة قابلة للسحب* في انتظارك.\nشاهد إعلاناً لاستلامها.", parse_mode="Markdown")
                    except: pass
                # شارة السفير (إذا وصل إلى 10 دعوات مباشرة)
                if referrer["referrals"] + 1 >= AMBASSADOR_THRESHOLD and not referrer.get("ambassador_badge"):
                    update_user(int(ref_id), {"ambassador_badge": True})
                    add_badge(int(ref_id), "سفير")
                    try:
                        await context.bot.send_message(int(ref_id), f"🏅 *مبروك! حصلت على شارة سفير البوت!* 🏅\nلقد دعوت {AMBASSADOR_THRESHOLD} شخصاً.", parse_mode="Markdown")
                    except: pass

    if uid == ADMIN_ID:
        await update.message.reply_text(f"👋 أهلاً *{name}* — لوحة الأدمن 🔧", parse_mode="Markdown", reply_markup=admin_menu())
        return

    u = get_user(uid)
    # معالجة هدية التسجيل المبكر (إذا كانت معلقة)
    early_bird = u.get("early_bird_rewarded", False) and not u.get("early_bird_notified", False)
    if early_bird and not u.get("pending_action"):
        update_user(uid, {"pending_action": {"type": "early_bird", "points": EARLY_BIRD_POINTS}})
        await update.message.reply_text(
            f"🎉 *تهانينا! أنت من أوائل مستخدمي البوت!* 🎉\n"
            f"لديك *{EARLY_BIRD_POINTS} نقطة قابلة للسحب* كهدية ترحيبية خاصة.\n"
            f"شاهد إعلاناً لاستلام الهدية.\n\n"
            f"👇 اضغط الزر أدناه.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎁 استلام الهدية", web_app=WebAppInfo(url=AD_URL))]])
        )
    else:
        await update.message.reply_text(
            f"👋 أهلاً *{name}*!\n\n🤖 أنا بوت كتابة المحتوى الاحترافي وزيادة الأرباح 🚀\n\n✨ نقاط عادية: *{u['points']}*\n💰 نقاط قابلة للسحب: *{u.get('withdrawable_points',0)}*\n\n👇 اختر من القائمة:",
            parse_mode="Markdown", reply_markup=main_menu()
        )

# ========== دوال المحتوى (AI) ==========
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
    await q.edit_message_text("📅 *جدولة أسبوعية*\nاكتب موضوع قناتك (وهطلعلك 7 بوستات للأسبوع):", parse_mode="Markdown")
    return WEEKLY_TOPIC

async def get_topic(update, context):
    context.user_data['topic'] = update.message.text
    await update.message.reply_text("🎨 اختار أسلوب الكتابة:", parse_mode="Markdown", reply_markup=tone_menu())
    return TONE

async def get_tone(update, context):
    q = update.callback_query
    await q.answer()
    tones = {"tone_formal":"رسمي", "tone_casual":"عامي", "tone_marketing":"تسويقي", "tone_simple":"مباشر"}
    tone = tones[q.data]
    topic = context.user_data['topic']
    key = context.user_data['platform_key']
    await q.edit_message_text("⏳ بكتبلك المحتوى... انتظر شوية!")
    uid = q.from_user.id
    u = check_daily_tasks(get_user(uid))
    u["tasks"]["used"] = True
    new_pts = u["points"] - POINTS_PER_USE
    update_user(uid, {"points": new_pts, "uses": u["uses"] + 1, "tasks": u["tasks"], "last_task_date": u["last_task_date"]})
    prompts = {
        "facebook": f"اكتب بوست فيسبوك احترافي عن '{topic}' بأسلوب {tone}.",
        "instagram": f"اكتب كابشن انستجرام مميز عن '{topic}' بأسلوب {tone} مع هاشتاقات.",
        "twitter": f"اكتب تويت مختصر وجذاب عن '{topic}' بأسلوب {tone} (280 حرف).",
        "linkedin": f"اكتب بوست لينكدإن احترافي عن '{topic}' بأسلوب {tone}.",
        "email": f"اكتب إيميل احترافي عن '{topic}' بأسلوب {tone}.",
        "ad": f"اكتب إعلان تسويقي مقنع عن '{topic}' بأسلوب {tone} مع CTA.",
        "article": f"اكتب مقال قصير عن '{topic}' بأسلوب {tone} (مقدمة + نقاط + خاتمة).",
        "ideas": f"أعطني 5 أفكار محتوى مبتكرة عن '{topic}' مناسبة للسوشيال ميديا."
    }
    prompt = prompts.get(key, f"اكتب محتوى عن '{topic}' بأسلوب {tone}.")
    try:
        r = client.chat.completions.create(model="gpt-oss-120b", messages=[{"role":"system","content":"أنت كاتب محتوى محترف ومتخصص في التسويق."},{"role":"user","content":prompt}])
        content = r.choices[0].message.content
        await q.message.reply_text(f"✅ *المحتوى جاهز:*\n\n{content}\n\n━━━━━━━━━━━━━━━\n💎 رصيدك المتبقي: *{new_pts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 محتوى جديد", callback_data="new"), InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    except Exception as e:
        await q.message.reply_text(f"❌ حصل خطأ: {str(e)[:100]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    return ConversationHandler.END

async def get_weekly_topic(update, context):
    topic = update.message.text
    await update.message.reply_text("⏳ جاري كتابة 7 بوستات... انتظر قليلاً.")
    uid = update.effective_user.id
    u = get_user(uid)
    new_pts = u["points"] - POINTS_PER_USE
    update_user(uid, {"points": new_pts, "uses": u["uses"] + 1})
    try:
        r = client.chat.completions.create(model="gpt-oss-120b", messages=[{"role":"system","content":"كاتب محتوى محترف."},{"role":"user","content":f"اكتب 7 بوستات تيليجرام مختلفة عن موضوع '{topic}' — واحد لكل يوم في الأسبوع. كل بوست يكون جذاب ومختلف مع إيموجي."}])
        content = r.choices[0].message.content
        await update.message.reply_text(f"✅ *بوستات الأسبوع جاهزة:*\n\n{content}\n\n💎 رصيدك المتبقي: *{new_pts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 أسبوع جديد", callback_data="weekly"), InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)[:100]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    return ConversationHandler.END

# ========== دوال الإعلانات والمكافآت (كل المكاسب تحتاج إعلان) ==========
async def handle_web_app_data(update, context):
    data = update.message.web_app_data.data
    uid = update.effective_user.id
    if data == "ad_watched":
        u = get_user(uid)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        # إعادة ضبط العداد اليومي
        if u.get("last_ad_date") != today:
            update_user(uid, {"ad_watch_today": 0, "last_ad_date": today})
            u["ad_watch_today"] = 0
        if u.get("ad_watch_today", 0) >= MAX_ADS_PER_DAY:
            await update.message.reply_text(f"❌ تجاوزت الحد اليومي ({MAX_ADS_PER_DAY}) إعلاناً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
            return
        # Streak والمضاعف
        mul = update_ad_streak(uid, today)
        earned = int(POINTS_PER_AD * mul)
        new_w = u["withdrawable_points"] + earned
        new_cnt = u["ad_watch_today"] + 1
        new_total_ads = u.get("total_ads_watched",0) + 1
        update_user(uid, {"withdrawable_points": new_w, "ad_watch_today": new_cnt, "last_ad_date": today, "total_ads_watched": new_total_ads})
        # شارة 100 إعلان
        if new_total_ads >= 100 and "100 إعلان" not in u.get("badges",[]):
            add_badge(uid, "100 إعلان")
            try:
                await context.bot.send_message(uid, "🏅 *مبروك! حصلت على شارة 100 إعلان!* 🏅", parse_mode="Markdown")
            except: pass
        # تحديث عداد المسابقة والمهمة الأسبوعية
        cweek = datetime.utcnow().strftime("%Y-%W")
        if u.get("last_contest_week") != cweek:
            update_user(uid, {"weekly_ad_count": 0, "last_contest_week": cweek, "weekly_mission_claimed": False})
            u["weekly_ad_count"] = 0
        new_weekly = u.get("weekly_ad_count", 0) + 1
        update_user(uid, {"weekly_ad_count": new_weekly})
        # مكافأة المهمة الأسبوعية (تُصرف فوراً بدون إعلان إضافي)
        if new_weekly >= WEEKLY_MISSION_TARGET and not u.get("weekly_mission_claimed"):
            update_user(uid, {"withdrawable_points": u["withdrawable_points"] + WEEKLY_MISSION_REWARD, "weekly_mission_claimed": True})
            await update.message.reply_text(f"🎉 *مهمة أسبوعية مكتملة!* شاهدت {WEEKLY_MISSION_TARGET} إعلاناً.\n✅ +{WEEKLY_MISSION_REWARD} نقطة قابلة للسحب.", parse_mode="Markdown")
        # عمولة الإحالة للمُحيل المباشر (10% لمدة 30 يوم)
        rid = u.get("referrer_id")
        if rid and u.get("referral_date"):
            days = (datetime.utcnow() - datetime.fromisoformat(u["referral_date"])).days
            if days <= 30:
                commission = int(earned * REFERRAL_COMMISSION_PERCENT / 100)
                if commission > 0 and can_add_commission(rid, commission):
                    ref = get_user(rid)
                    new_ref_w = ref["withdrawable_points"] + commission
                    update_user(rid, {"withdrawable_points": new_ref_w, "total_commission_earned": ref.get("total_commission_earned",0) + commission})
                    try:
                        await context.bot.send_message(rid, f"🎁 عمولة إحالة: صديقك شاهد إعلاناً، ربحت +{commission} نقطة قابلة للسحب!", parse_mode="Markdown")
                    except: pass
        # تحديث المهام اليومية
        u2 = check_daily_tasks(get_user(uid))
        u2["tasks"]["ad"] = True
        update_user(uid, {"tasks": u2["tasks"]})
        await update.message.reply_text(
            f"✅ *تم إضافة {earned} نقطة قابلة للسحب!*\n\n"
            f"💎 رصيدك القابل للسحب: *{new_w}*\n🔥 مضاعف اليوم: *{mul}x*\n📊 إعلانات اليوم: *{new_cnt}/{MAX_ADS_PER_DAY}*\n✨ رصيدك العادي: *{u2['points']}*",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]])
        )
        # معالجة الإجراءات المعلقة (إن وجدت) – بعد إضافة النقاط الأساسية
        pending = u.get("pending_action")
        if pending:
            action_type = pending.get("type")
            if action_type == "early_bird":
                points = pending.get("points", EARLY_BIRD_POINTS)
                update_user(uid, {"withdrawable_points": u["withdrawable_points"] + points, "early_bird_notified": True, "pending_action": None})
                await update.message.reply_text(f"🎉 *تم استلام هدية التسجيل المبكر!* +{points} نقطة قابلة للسحب.", parse_mode="Markdown")
            elif action_type == "referral_reward":
                points = pending.get("points", REFERRAL_WITHDRAWABLE)
                update_user(uid, {"withdrawable_points": u["withdrawable_points"] + points, "pending_action": None})
                await update.message.reply_text(f"🎉 *تم استلام مكافأة الإحالة!* +{points} نقطة قابلة للسحب.", parse_mode="Markdown")
            elif action_type == "referral_level2_reward":
                points = pending.get("points", REFERRAL_LEVEL2)
                update_user(uid, {"withdrawable_points": u["withdrawable_points"] + points, "pending_action": None})
                await update.message.reply_text(f"🎉 *تم استلام مكافأة الإحالة غير المباشرة!* +{points} نقطة قابلة للسحب.", parse_mode="Markdown")
            elif action_type == "claim_bonus":
                # بونص المهام اليومية
                u3 = check_daily_tasks(get_user(uid))
                if not u3["tasks"].get("bonus", False):
                    new_pts = u3["points"] + 300
                    u3["tasks"]["bonus"] = True
                    update_user(uid, {"points": new_pts, "tasks": u3["tasks"], "pending_action": None})
                    await update.message.reply_text(f"🎉 *تم استلام بونص المهام اليومية!* +300 نقطة عادية.", parse_mode="Markdown")
                else:
                    update_user(uid, {"pending_action": None})
                    await update.message.reply_text("⚠️ لقد استلمت البونص مسبقاً.", parse_mode="Markdown")

    elif data == "box_ad_watched":
        u = get_user(uid)
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if u.get("last_box_date") == today:
            await update.message.reply_text("❌ لقد فتحت الصندوق اليوم بالفعل!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
            return
        streak = u.get("ad_streak",0)
        prize, msg, level = spin_mystery_box(streak)
        new_pts = u["points"] + prize
        update_user(uid, {"points": new_pts, "last_box_date": today})
        await update.message.reply_text(
            f"🎁 *نتيجة صندوق {level}*\n{msg}\n\n🎊 ربحت *{prize} نقطة عادية*!\n💎 رصيدك العادي: *{new_pts}*\n\n📈 Streak الحالي: {streak} يوم\nارجع غداً لصندوق جديد!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]])
        )

async def mystery_box(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if u.get("last_box_date") == today:
        await q.message.reply_text("❌ فتحت الصندوق اليوم بالفعل!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
        return
    streak = u.get("ad_streak",0)
    level = "فضة"
    for lvl, data in BOX_LEVELS.items():
        min_s, max_s = data["streak_range"]
        if min_s <= streak <= max_s:
            level = lvl
            break
    await q.message.reply_text(
        f"🎲 *صندوق الحظ - مستوى {level}* 🎲\n"
        f"🔥 Streak الحالي: {streak} يوم\n"
        f"⚠️ شاهد الإعلان أولاً لفتح الصندوق واكتشاف مكافأتك!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"🎁 افتح صندوق {level}", web_app=WebAppInfo(url=BOX_AD_URL))]])
    )

async def watch_ad(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if u.get("last_ad_date") != today:
        update_user(uid, {"ad_watch_today": 0, "last_ad_date": today})
        u["ad_watch_today"] = 0
    if u.get("ad_watch_today",0) >= MAX_ADS_PER_DAY:
        await q.message.reply_text(f"❌ الحد اليومي {MAX_ADS_PER_DAY} إعلاناً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
        return
    mul = update_ad_streak(uid, today)
    earn = int(POINTS_PER_AD * mul)
    remaining = MAX_ADS_PER_DAY - u["ad_watch_today"]
    await q.message.reply_text(
        f"📺 *شاهد الإعلان عشان تكسب نقاط قابلة للسحب!*\n\n"
        f"🔥 مضاعف اليوم: *{mul}x*\n💰 ستربح: *{earn} نقطة*\n📊 تبقى لك اليوم: *{remaining}* إعلاناً.\n\n"
        "اضغط الزر وشاهد الإعلان كامل – النقاط ستضاف تلقائياً بعد المشاهدة ✅",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد الإعلان", web_app=WebAppInfo(url=AD_URL))]])
    )

async def daily_tasks(update, context):
    q = update.callback_query
    await q.answer()
    u = check_daily_tasks(get_user(q.from_user.id))
    tasks = u["tasks"]
    text = f"📋 *مهام اليوم*\n\n{'✅' if tasks['ad'] else '❌'} شاهد إعلان (+{POINTS_PER_AD} نقطة عادية للمهمة)\n{'✅' if tasks['used'] else '❌'} استخدم البوت مرة\n\n"
    if tasks["ad"] and tasks["used"] and not tasks["bonus"]:
        text += "🎁 يمكنك استلام 300 نقطة بونص!\n⚠️ سيطلب منك مشاهدة إعلان لاستلام البونص."
        kb = [[InlineKeyboardButton("🎁 استلام البونص (بعد الإعلان)", callback_data="claim_bonus")]]
    elif tasks["bonus"]:
        text += "✅ استلمت البونص النهارده!"
        kb = [[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]
    else:
        text += "🎯 أكمل المهام وخد 300 نقطة بونص!"
        kb = [[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def claim_bonus(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = check_daily_tasks(get_user(uid))
    if u["tasks"]["ad"] and u["tasks"]["used"] and not u["tasks"]["bonus"]:
        # نضع إجراء معلق بدلاً من الإضافة فوراً
        update_user(uid, {"pending_action": {"type": "claim_bonus"}})
        await q.message.reply_text(
            "🎁 *مكافأة المهام اليومية*\n"
            f"لديك 300 نقطة عادية في انتظارك.\n"
            "شاهد إعلاناً لاستلام البونص 👇",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد الإعلان واستلم البونص", web_app=WebAppInfo(url=AD_URL))]])
        )
    else:
        await q.message.reply_text("❌ لم تكمل المهام أو استلمت البونص مسبقاً!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))

async def referral(update, context):
    q = update.callback_query
    await q.answer()
    bot_username = "easy_free1bot"
    link = f"https://t.me/{bot_username}?start=ref_{q.from_user.id}"
    await q.message.reply_text(
        f"🎁 *نظام الإحالات المتقدم*\n\n"
        f"رابط دعوتك الشخصي:\n`{link}`\n\n"
        f"🌟 *المكافآت:*\n"
        f"• مدعو مباشر: +{REFERRAL_WITHDRAWABLE} نقطة قابلة للسحب (تتطلب إعلاناً) + {REFERRAL_COMMISSION_PERCENT}% من أرباح إعلاناته لمدة 30 يوم.\n"
        f"• مدعو غير مباشر (صديق صديقك): +{REFERRAL_LEVEL2} نقطة (تتطلب إعلاناً).\n\n"
        f"كلما زاد نشاط مدعويك، زادت أرباحك! ادعُ أصدقاءك الآن 🚀",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="earn_menu")]])
    )

async def withdraw_request(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    w = u.get("withdrawable_points",0)
    if w < MIN_WITHDRAW_POINTS:
        need = MIN_WITHDRAW_POINTS - w
        await q.message.reply_text(
            f"💰 *تحويل النقاط لفلوس*\n\n"
            f"رصيدك القابل للسحب: *{w} نقطة*\n"
            f"الحد الأدنى للسحب: *{MIN_WITHDRAW_POINTS} نقطة* (${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR})\n\n"
            f"تحتاج *{need} نقطة* إضافية.\nشاهد إعلانات أو ادعُ أصدقاء لتجميعها.",
            parse_mode="Markdown"
        )
        return
    amt = w // POINTS_PER_DOLLAR
    deduct = amt * POINTS_PER_DOLLAR
    new_w = w - deduct
    update_user(uid, {"withdrawable_points": new_w})
    # مكافأة أول سحب (تُضاف فوراً، بدون إعلان لأنها ليست مكافأة مستقلة بل هي بونص تحفيزي)
    if not u.get("has_withdrawn_before"):
        update_user(uid, {"has_withdrawn_before": True, "first_withdrawal_date": datetime.utcnow().isoformat()})
        new_w += 1000
        update_user(uid, {"withdrawable_points": new_w})
        await q.message.reply_text("🎁 *هدية أول سحب!* تم إضافة 1000 نقطة قابلة للسحب كتحفيز! 🎉", parse_mode="Markdown")
    # تسجيل الطلب
    withdrawal_req = {"user_id": uid, "points_deducted": deduct, "amount_usd": amt, "status": "pending", "date": datetime.utcnow().isoformat()}
    db["withdrawals"].insert_one(withdrawal_req)
    await context.bot.send_message(
        ADMIN_ID, f"💰 *طلب سحب جديد*\nالمستخدم: {q.from_user.first_name}\nID: `{uid}`\nالمبلغ: {amt}$\nالتاريخ: {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
        parse_mode="Markdown"
    )
    await q.message.reply_text(
        f"💰 *تم إرسال طلب السحب بنجاح!*\n\nالمبلغ المطلوب: *{amt}$*\nتم خصم {deduct} نقطة من رصيدك القابل للسحب.\nسيتم المراجعة خلال 24-48 ساعة.\nشكراً لك!",
        parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]])
    )

# ========== دوال المتصدرين والأدمن ==========
def get_leaderboard(limit=10):
    cursor = users_col.find({}, {"_id":1,"points":1,"withdrawable_points":1}).sort("points",-1).limit(limit)
    res = []
    r = 1
    for u in cursor:
        total = u.get("points",0) + u.get("withdrawable_points",0)
        res.append({"rank":r, "user_id":u["_id"], "total_points":total})
        r += 1
    return res

async def leaderboard(update, context):
    q = update.callback_query
    await q.answer()
    data = get_leaderboard(10)
    if not data:
        text = "🏆 *الترتيب*\n\nلا يوجد مستخدمون بعد. ابدأ باستخدام البوت لتظهر هنا! 🚀"
    else:
        text = "🏆 *أفضل 10 مستخدمين*\n\n"
        for e in data:
            try:
                user = await context.bot.get_chat(int(e["user_id"]))
                name = user.first_name
            except:
                name = f"مستخدم {e['user_id'][-4:]}"
            text += f"{e['rank']}. {name} — 💎 {e['total_points']} نقطة (إجمالي)\n"
    kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# دوال الأدمن
async def admin_stats(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    total = users_col.count_documents({})
    uses = sum(u.get("uses",0) for u in users_col.find())
    await q.message.reply_text(f"📊 *الإحصائيات*\n👥 إجمالي المستخدمين: *{total}*\n✍️ إجمالي الاستخدامات: *{uses}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]))

async def admin_users(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    total = users_col.count_documents({})
    await q.message.reply_text(f"👥 *المستخدمون*\nإجمالي: *{total}* مستخدم", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]))

async def admin_broadcast_start(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    await q.message.reply_text("📢 اكتب الرسالة التي تريد إرسالها لجميع المستخدمين:")
    return BROADCAST_MSG

async def admin_broadcast_send(update, context):
    if update.effective_user.id != ADMIN_ID: return ConversationHandler.END
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

async def admin_withdrawals(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    pending = list(db["withdrawals"].find({"status":"pending"}))
    if not pending:
        await q.message.reply_text("✅ لا توجد طلبات سحب معلقة حالياً.")
        return
    text = "💰 *طلبات السحب المعلقة*\n\n"
    kb = []
    for req in pending:
        try:
            user = await context.bot.get_chat(req["user_id"])
            name = user.first_name
        except:
            name = f"ID:{req['user_id']}"
        text += f"👤 {name}\n💵 {req['amount_usd']}$ ({req['points_deducted']} نقطة)\n\n"
        rid = str(req["_id"])
        kb.append([InlineKeyboardButton(f"✅ قبول {req['amount_usd']}$", callback_data=f"approve_{rid}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_{rid}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")])
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def approve_withdraw(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    req_id = q.data.split("_")[1]
    withdrawal = db["withdrawals"].find_one({"_id": ObjectId(req_id), "status":"pending"})
    if not withdrawal:
        await q.message.reply_text("❌ هذا الطلب غير موجود أو تمت معالجته مسبقاً.")
        return
    db["withdrawals"].update_one({"_id": ObjectId(req_id)}, {"$set":{"status":"approved"}})
    try:
        await context.bot.send_message(withdrawal["user_id"], f"✅ *تمت الموافقة على طلب السحب الخاص بك!*\nالمبلغ: *{withdrawal['amount_usd']}$*\nسيتم تحويله خلال 24 ساعة.", parse_mode="Markdown")
    except: pass
    await q.message.reply_text(f"✅ تمت الموافقة على سحب {withdrawal['amount_usd']}$ وإشعار المستخدم.")
    await q.message.delete()
    await admin_withdrawals(update, context)

async def reject_withdraw(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    req_id = q.data.split("_")[1]
    withdrawal = db["withdrawals"].find_one({"_id": ObjectId(req_id), "status":"pending"})
    if not withdrawal:
        await q.message.reply_text("❌ الطلب غير موجود.")
        return
    # إعادة النقاط للمستخدم
    u = get_user(withdrawal["user_id"])
    new_w = u.get("withdrawable_points",0) + withdrawal["points_deducted"]
    update_user(withdrawal["user_id"], {"withdrawable_points": new_w})
    db["withdrawals"].update_one({"_id": ObjectId(req_id)}, {"$set":{"status":"rejected"}})
    try:
        await context.bot.send_message(withdrawal["user_id"], f"❌ *للأسف، تم رفض طلب السحب الخاص بك.*\nتم إعادة {withdrawal['points_deducted']} نقطة إلى رصيدك القابل للسحب.", parse_mode="Markdown")
    except: pass
    await q.message.reply_text(f"❌ تم رفض الطلب وإعادة {withdrawal['points_deducted']} نقطة للمستخدم.")
    await q.message.delete()
    await admin_withdrawals(update, context)

async def admin_export(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["User ID", "First Name", "Points", "Withdrawable", "Uses", "Referrals", "Has Withdrawn", "Join Date", "Total Ads"])
    for user in users_col.find():
        try:
            u = await context.bot.get_chat(int(user["_id"]))
            name = u.first_name
        except:
            name = "Unknown"
        writer.writerow([user["_id"], name, user.get("points",0), user.get("withdrawable_points",0), user.get("uses",0), user.get("referrals",0), user.get("has_withdrawn_before",False), user.get("last_task_date",""), user.get("total_ads_watched",0)])
    output.seek(0)
    await q.message.reply_document(document=io.BytesIO(output.getvalue().encode()), filename="users_export.csv", caption="📊 تصدير بيانات المستخدمين")
    await q.message.reply_text("✅ تم التصدير.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]))

async def handle_nav(update, context):
    q = update.callback_query
    await q.answer()
    if q.data == "admin_back":
        await q.message.reply_text("🔧 لوحة الأدمن:", reply_markup=admin_menu())
    elif q.data in ("home","new"):
        await main_back(update, context)

# ========== المهام المجدولة (JobQueue) ==========
async def daily_notification(context: ContextTypes.DEFAULT_TYPE):
    for user in users_col.find():
        try:
            uid = int(user["_id"])
            u = get_user(uid)
            streak = u.get("ad_streak",0)
            mul = u.get("ad_multiplier",1.0)
            await context.bot.send_message(uid, f"🔥 *تذكير يومي*\nStreak الحالي: {streak} يوم (مضاعف {mul}x)\nشاهد إعلانك الأول اليوم واحصل على {int(POINTS_PER_AD*mul)} نقطة قابلة للسحب.\nلا تفوت الفرصة!", parse_mode="Markdown")
        except: pass

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.utcnow().strftime("%Y-%m-%d")
    for user in users_col.find():
        try:
            uid = int(user["_id"])
            u = get_user(uid)
            if u.get("last_daily_report_date") == today:
                continue
            await context.bot.send_message(uid, f"📊 *تقرير يومي*\nرصيدك القابل للسحب: *{u.get('withdrawable_points',0)} نقطة*\nعدد إعلانات اليوم السابق: *{u.get('ad_watch_today',0)}*\nاستمر في مشاهدة الإعلانات لزيادة أرباحك!", parse_mode="Markdown")
            update_user(uid, {"last_daily_report_date": today})
        except: pass

async def announce_top_daily(context: ContextTypes.DEFAULT_TYPE):
    users = list(users_col.find({}, {"_id":1,"points":1,"withdrawable_points":1}))
    if not users: return
    for u in users:
        u["total"] = u.get("points",0) + u.get("withdrawable_points",0)
    users.sort(key=lambda x: x["total"], reverse=True)
    top = users[0]
    try:
        name = (await context.bot.get_chat(int(top["_id"]))).first_name
    except:
        name = "مستخدم"
    for user in users_col.find():
        try:
            await context.bot.send_message(int(user["_id"]), f"🏆 *إعلان فوز اليوم*\nالمتصدر اليوم هو *{name}* بإجمالي {top['total']} نقطة!\nاستمر في جمع النقاط لتصبح أنت المتصدر غداً.", parse_mode="Markdown")
        except: pass

# المسابقة الأسبوعية
async def weekly_contest(context: ContextTypes.DEFAULT_TYPE):
    stats = []
    for user in users_col.find():
        cnt = user.get("weekly_ad_count",0)
        if cnt > 0:
            stats.append({"user_id": user["_id"], "count": cnt})
    stats.sort(key=lambda x: x["count"], reverse=True)
    top10 = stats[:10]
    prizes = [5000, 3000, 1500, 500, 500, 500, 500, 500, 500, 500]
    for idx, entry in enumerate(top10):
        prize = prizes[idx] if idx < len(prizes) else 500
        u = get_user(entry["user_id"])
        new_w = u["withdrawable_points"] + prize
        update_user(entry["user_id"], {"withdrawable_points": new_w})
        # منح شارة "السبوعي" لأول فوز
        if "السبوعي" not in u.get("badges", []):
            add_badge(entry["user_id"], "السبوعي")
        try:
            await context.bot.send_message(int(entry["user_id"]), f"🏆 *المسابقة الأسبوعية*\nالمركز {idx+1} بعدد {entry['count']} إعلان!\n✅ تم إضافة {prize} نقطة قابلة للسحب.", parse_mode="Markdown")
        except: pass
    users_col.update_many({}, {"$set": {"weekly_ad_count": 0, "last_contest_week": datetime.utcnow().strftime("%Y-%W"), "weekly_mission_claimed": False}})
    await context.bot.send_message(ADMIN_ID, "✅ تم توزيع جوائز المسابقة الأسبوعية.")

# ========== تشغيل البوت ==========
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    job_queue = app.job_queue
    if job_queue:
        job_queue.run_daily(daily_notification, time=datetime.time(hour=9, minute=0))
        job_queue.run_daily(daily_report, time=datetime.time(hour=23, minute=0))
        job_queue.run_daily(announce_top_daily, time=datetime.time(hour=20, minute=0))
        job_queue.run_daily(weekly_contest, time=datetime.time(hour=0, minute=0), days=(0,))  # كل إثنين

    conv_handler = ConversationHandler(
        entry_points = [
            CallbackQueryHandler(handle_platform, pattern="^(facebook|instagram|twitter|linkedin|email|ad|article|ideas)$"),
            CallbackQueryHandler(weekly, pattern="^weekly$"),
            CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")
        ],
        states = {
            TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic)],
            TONE: [CallbackQueryHandler(get_tone, pattern="^tone_")],
            WEEKLY_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weekly_topic)],
            BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)]
        },
        fallbacks = [CommandHandler("start", start)]
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
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

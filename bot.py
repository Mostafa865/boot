# v22.1 - النسخة النهائية مع إصلاح شامل للبث الجماعي وسجل التدقيق وجميع المهام المجدولة
import logging, random, csv, io, asyncio, traceback
from datetime import datetime, timedelta
from bson.objectid import ObjectId
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ReplyKeyboardMarkup, KeyboardButton
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
POINTS_PER_AD = 250
MAX_ADS_PER_DAY = 8
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
CONVERSION_RATE = 10
MAX_DAILY_CONVERSION = 5000
# ========== إعدادات كشف الغش ==========
ANTI_CHEAT_ENABLED = True
MAX_ADS_PER_SECOND = 1   # إعلان واحد كل 10 ثوانٍ (أي 6 في الدقيقة)
IP_CHECK_ENABLED = True
IP_API_URL = "https://ipapi.co/{ip}/json/"
MULTI_ACCOUNT_LIMIT = 3  # عدد الحسابات المسموحة من نفس الـ IP
# ========== إعدادات كشف الغش ==========
MAX_ADS_PER_HOUR = 30           # الحد الأقصى للإعلانات في الساعة
SUSPICIOUS_THRESHOLD = 3        # عدد مرات السلوك المشبوه قبل التحذير
AUTO_BAN_THRESHOLD = 5          # بعدها يحظر تلقائياً
CHEAT_LOG_COLLECTION = "cheat_logs"
# إعدادات أتمتة السحب
AUTO_WITHDRAWAL_ENABLED = True
USDT_ADDRESS_REGEX = r'^T[a-zA-Z0-9]{33}$'  # عنوان TRC20 بسيط
WITHDRAW_PHONE = 101   # قيمة جديدة بعيدة عن الأرقام المستخدمة الأخرى
FORCE_SUBSCRIBE_CHANNEL = "@bots_free1"  # أو معرف القناة بالرقمي
FORCE_SUBSCRIBE_CHANNEL_ID = -1001234567890  # الرقم الحقيقي للقناة

LEVELS = {
    "مبتدئ": {"points": 0, "unlock_ads": 0, "reward": 0, "multiplier": 1.0},
    "نشيط": {"points": 10000, "unlock_ads": 5, "reward": 2000, "multiplier": 1.05},
    "محترف": {"points": 50000, "unlock_ads": 10, "reward": 5000, "multiplier": 1.1},
    "VIP": {"points": 150000, "unlock_ads": 20, "reward": 10000, "multiplier": 1.2},
    "أسطورة": {"points": 500000, "unlock_ads": 50, "reward": 25000, "multiplier": 1.5}
}
LEVELS_LIST = ["مبتدئ", "نشيط", "محترف", "VIP", "أسطورة"]

WHEEL_PRIZES = [50, 100, 200, 500, 1000, 2000]
WHEEL_DAILY_LIMIT = 3
WHEEL_URL = "https://mostafa865.github.io/boot/wheel.html"

BOX_LEVELS = {
    "فضة": {"streak_range": (1,5), "prizes": [(50, "😐 حظك عادي", 50), (100, "🙂 مش بطال", 25), (200, "😊 كويس", 25)]},
    "ذهب": {"streak_range": (6,10), "prizes": [(200, "😊 كويس", 40), (350, "🙂 حلو", 35), (500, "🔥 ممتاز", 25)]},
    "ألماس": {"streak_range": (11,100), "prizes": [(500, "🔥 ممتاز", 40), (1000, "🎉 رائع", 35), (2000, "🏆 جاكبوت", 25)]}
}

AD_URL = "https://mostafa865.github.io/boot/ad.html"
BOX_AD_URL = "https://mostafa865.github.io/boot/box_ad.html"
BONUS_AD_URL = "https://mostafa865.github.io/boot/bonus_ad.html"
REFERRAL_AD_URL = "https://mostafa865.github.io/boot/referral_ad.html"
EARLY_AD_URL = "https://mostafa865.github.io/boot/early_ad.html"
CHALLENGE_AD_URL = "https://mostafa865.github.io/boot/challenge_ad.html"
MONTHLY_AD_URL = "https://mostafa865.github.io/boot/monthly_ad.html"

# اتصال MongoDB مع فحص أولي
mongo = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
db = mongo["botdb"]
users_col = db["users"]
withdrawals_col = db["withdrawals"]
offers_col = db["flash_offers"]
challenges_col = db["challenges"]
coupons_col = db["coupons"]
global_challenges_col = db["global_challenges"]
audit_col = db["audit_log"]
cheat_logs_col = db["cheat_logs"]


try:
    mongo.admin.command('ping')
    audit_col.insert_one({"test": True, "timestamp": datetime.utcnow()})
    audit_col.delete_one({"test": True})
    print("✅ MongoDB connection successful and audit_log writable.")
except Exception as e:
    print(f"❌ MongoDB connection error: {e}")

client = openai.OpenAI(base_url="https://openrouter.ai/api/v1", api_key=OPENROUTER_API_KEY)

TOPIC, TONE, WEEKLY_TOPIC = range(3)
BROADCAST_MSG = 99

# ========== دوال قاعدة البيانات ==========
def get_user(user_id):
    uid = str(user_id)
    user = users_col.find_one({"_id": uid})
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if not user:
        total_before = users_col.count_documents({})
        early_bird = total_before < EARLY_BIRD_LIMIT
        user = {
            "_id": uid, "points": 300, "withdrawable_points": 0, "early_bird_rewarded": early_bird,
            "early_bird_notified": False, "uses": 0, "referrals": 0, "referrer_id": None,
            "referral_date": None, "total_commission_today": 0, "last_commission_date": "",
            "referred_users": [], "referral_level2_count": 0, "total_commission_earned": 0,
            "has_withdrawn_before": False, "first_withdrawal_date": None,
            "tasks": {"ad": False, "used": False, "bonus": False}, "last_task_date": today,
            "last_box_date": "", "ad_watch_today": 0, "last_ad_date": "", "ad_streak": 0,
            "last_ad_time": 0, "usdt_address": None, "usdt_verified": False,
            "ad_multiplier": 1.0, "last_ad_streak_date": "", "weekly_ad_count": 0,
            "last_contest_week": datetime.utcnow().strftime("%Y-%W"), "weekly_mission_claimed": False,
            "ambassador_badge": False, "last_daily_report_date": "", "total_ads_watched": 0,
            "badges": [], "pending_action": None, "challenge_active": None, "challenge_points": 0,
            "last_challenge_reset": today, "daily_converted": 0, "level": "مبتدئ",
            "level_reward_claimed": False, "pending_level_upgrade": None, "highest_total_points": 300,
            "wheel_spins_today": 0, "last_wheel_date": "", "banned": False,
            "phone": None, "payment_info": None,
            "global_challenge_ads": 0,
            "global_challenge_reward_claimed": False
        }
        users_col.insert_one(user)
    else:
        # تحديث الحقول المفقودة (اختصاراً)
        fields = ["withdrawable_points","ad_watch_today","last_ad_date","ad_streak","ad_multiplier","last_ad_streak_date",
                  "referrer_id","referral_date","total_commission_today","last_commission_date","referred_users",
                  "referral_level2_count","total_commission_earned","has_withdrawn_before","first_withdrawal_date",
                  "weekly_mission_claimed","ambassador_badge","last_daily_report_date","total_ads_watched","badges",
                  "pending_action","early_bird_rewarded","early_bird_notified","challenge_active","challenge_points",
                  "last_challenge_reset","daily_converted","level","level_reward_claimed","pending_level_upgrade",
                  "highest_total_points","wheel_spins_today","last_wheel_date","banned","global_challenge_ads",
                  "global_challenge_reward_claimed"]
        for field in fields:
            if field not in user:
                if field in ["wheel_spins_today","last_wheel_date","banned","global_challenge_ads","global_challenge_reward_claimed"]:
                    user[field] = 0 if field in ["wheel_spins_today","global_challenge_ads"] else ("" if field=="last_wheel_date" else False)
                elif field in ["level","level_reward_claimed","pending_level_upgrade","highest_total_points"]:
                    user[field] = "مبتدئ" if field=="level" else (False if field=="level_reward_claimed" else (None if field=="pending_level_upgrade" else 300))
                else:
                    user[field] = None if field in ["referrer_id","referral_date","first_withdrawal_date","last_daily_report_date","pending_action","challenge_active","pending_level_upgrade"] else (0 if field in ["total_commission_today","referral_level2_count","total_commission_earned","total_ads_watched","challenge_points","daily_converted","highest_total_points"] else ([] if field=="badges" else False))
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
        if user.get("daily_converted", 0) != 0:
            user["daily_converted"] = 0
            update_user(user["_id"], {"daily_converted": 0, "last_task_date": today, "tasks": user["tasks"]})
        else:
            update_user(user["_id"], {"last_task_date": today, "tasks": user["tasks"]})
        if user.get("last_wheel_date") != today:
            update_user(user["_id"], {"wheel_spins_today": 0, "last_wheel_date": today})
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

# ========== سجل التدقيق ==========
async def log_action(admin_id: int, action_type: str, target_user_id: int = None, details: str = ""):
    try:
        audit_col.insert_one({
            "timestamp": datetime.utcnow(),
            "admin_id": admin_id,
            "action_type": action_type,
            "target_user_id": target_user_id,
            "details": details
        })
        print(f"✅ سجل: {action_type}")
    except Exception as e:
        print(f"❌ خطأ في التسجيل: {e}")

async def admin_audit_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ غير مصرح.", show_alert=True)
        return
    # جلب آخر 10 سجلات
    logs = list(audit_col.find({}).sort("timestamp", -1).limit(10))
    if not logs:
        await query.message.reply_text("📋 لا توجد إجراءات مسجلة بعد.")
        return
    text = "📋 *آخر الإجراءات*\n\n"
    for log in logs:
        time_str = log["timestamp"].strftime("%Y-%m-%d %H:%M")
        action = log["action_type"]
        target = f" (← {log['target_user_id']})" if log.get("target_user_id") else ""
        details = f": {log['details']}" if log.get("details") else ""
        text += f"• `{time_str}`: {action}{target}{details}\n"
    await query.message.reply_text(text, parse_mode="Markdown")
# ========== تحليل التسرب ==========
async def get_inactive_users(days=7):
    cutoff = datetime.utcnow() - timedelta(days=days)
    return list(users_col.find({"$or": [{"last_ad_date": {"$lt": cutoff.strftime("%Y-%m-%d")}}, {"last_ad_date": {"$exists": False}}], "banned": False}).sort("last_ad_date", 1).limit(20))

async def admin_churn_analysis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    # تحقق من صلاحية الأدمن
    if q.from_user.id != ADMIN_ID:
        await q.answer("⛔ غير مصرح.", show_alert=True)
        return
    
    # جلب المستخدمين غير النشطين خلال 7 أيام
    cutoff = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    inactive_users = list(users_col.find({
        "$or": [
            {"last_ad_date": {"$lt": cutoff}},
            {"last_ad_date": {"$exists": False}}
        ],
        "banned": False
    }).limit(20))
    
    if not inactive_users:
        await q.message.reply_text("✅ لا يوجد مستخدمون غير نشطين خلال الأسبوع الماضي.")
        return
    
    text = "📉 *تحليل التسرب (غير نشطين لأكثر من 7 أيام)*\n\n"
    kb = []
    for user in inactive_users[:10]:
        uid = user["_id"]
        try:
            name = (await context.bot.get_chat(int(uid))).first_name
        except:
            name = f"مستخدم {uid[-4:]}"
        last_ad = user.get("last_ad_date", "غير معروف")
        total_ads = user.get("total_ads_watched", 0)
        text += f"• {name} (`{uid}`) - آخر نشاط: {last_ad} - إجمالي إعلانات: {total_ads}\n"
        kb.append([InlineKeyboardButton(f"📢 تذكير {name}", callback_data=f"churn_remind_{uid}"),
                   InlineKeyboardButton(f"🎁 هدية {name}", callback_data=f"churn_gift_{uid}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")])
    
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    await q.message.delete()  # حذف الرسالة الأصلية لتجنب الازدحام


async def churn_remind(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.answer("⛔ غير مصرح.", show_alert=True)
        return
    uid = int(q.data.split("_")[2])
    try:
        await context.bot.send_message(uid, "🔥 *تذكير عودة*\nنحن نفتقدك! اشترك مرة أخرى في البوت واحصل على *500 نقطة قابلة للسحب* عند مشاهدة إعلان اليوم. استخدم الكود `WELCOMEBACK` (صلاحية 24 ساعة).", parse_mode="Markdown")
        await log_action(ADMIN_ID, "إرسال تذكير تسرب", uid, "")
        await q.message.reply_text(f"✅ تم إرسال تذكير للمستخدم {uid}.")
    except Exception as e:
        await q.message.reply_text(f"❌ فشل الإرسال: {str(e)}")

async def churn_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.answer("⛔ غير مصرح.", show_alert=True)
        return
    uid = int(q.data.split("_")[2])
    try:
        user = get_user(uid)
        new_w = user.get("withdrawable_points", 0) + 500
        update_user(uid, {"withdrawable_points": new_w})
        await context.bot.send_message(uid, "🎁 *هدية عودة*!\nتم إضافة *500 نقطة قابلة للسحب* إلى رصيدك. تفضل بزيارتنا مرة أخرى!", parse_mode="Markdown")
        await log_action(ADMIN_ID, "إهداء نقاط للتسرب", uid, "500 نقطة")
        await q.message.reply_text(f"✅ تم إهداء 500 نقطة للمستخدم {uid}.")
    except Exception as e:
        await q.message.reply_text(f"❌ فشل الإهداء: {str(e)}")

# ========== عجلة الحظ ==========
def spin_wheel():
    return random.choice(WHEEL_PRIZES)

async def wheel_of_fortune(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user_data = get_user(uid)
    if user_data.get("banned", False):
        await query.answer("⛔ أنت محظور", show_alert=True)
        return
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if user_data.get("last_wheel_date") != today:
        update_user(uid, {"wheel_spins_today": 0, "last_wheel_date": today})
        user_data["wheel_spins_today"] = 0
    spins_today = user_data.get("wheel_spins_today", 0)
    if spins_today >= WHEEL_DAILY_LIMIT:
        await query.message.reply_text(f"⚠️ لقد استخدمت عجلة الحظ اليوم {WHEEL_DAILY_LIMIT} مرات بالفعل! عاود غداً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="earn_menu")]]))
        return
    update_user(uid, {"pending_action": {"type": "wheel"}})
    web_app_button = KeyboardButton("🎡 شاهد الإعلان واستدير (موبايل)", web_app=WebAppInfo(url=WHEEL_URL))
    reply_markup = ReplyKeyboardMarkup(keyboard=[[web_app_button]], resize_keyboard=True, one_time_keyboard=True)
    await query.message.reply_text(f"🎡 *عجلة الحظ* (المتبقي اليوم: {WHEEL_DAILY_LIMIT - spins_today})\n\n📱 *موبايل:* اضغط الزر أسفل الشاشة\n💻 *لاب:* اضغط الزر أدناه 👇", parse_mode="Markdown", reply_markup=reply_markup)
    await query.message.reply_text("💻 *للاب فقط:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎡 شاهد الإعلان واستدير (لاب)", web_app=WebAppInfo(url=WHEEL_URL))]]))

# ========== نظام الكوبونات ==========
async def create_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ غير مصرح.")
        return
    try:
        code = context.args[0].upper()
        points = int(context.args[1])
        days = int(context.args[2])
        max_uses = int(context.args[3])
        expires_at = datetime.utcnow() + timedelta(days=days)
        coupon = {"code": code, "points": points, "max_uses": max_uses, "used_count": 0, "expires_at": expires_at, "created_by": ADMIN_ID, "created_at": datetime.utcnow()}
        coupons_col.insert_one(coupon)
        await log_action(ADMIN_ID, "إنشاء كوبون", None, f"الكود: {code}, النقاط: {points}, المدة: {days} أيام, الحد: {max_uses}")
        await update.message.reply_text(f"✅ تم إنشاء الكوبون:\n• الكود: `{code}`\n• النقاط: {points}\n• الصلاحية: {days} يوم\n• الحد الأقصى للاستخدام: {max_uses}", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: استخدم `/createcoupon <كود> <نقاط> <أيام> <حد_الاستخدام>`\n{str(e)}")

async def redeem_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🎟️ *استخدام كود خصم*\nأرسل الكود الآن:", parse_mode="Markdown")
    context.user_data['awaiting_coupon'] = True

async def process_coupon(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_coupon'):
        return
    uid = update.effective_user.id
    user_data = get_user(uid)
    if user_data.get("banned", False):
        await update.message.reply_text("⛔ أنت محظور.")
        context.user_data['awaiting_coupon'] = False
        return
    code = update.message.text.strip().upper()
    coupon = coupons_col.find_one({"code": code})
    if not coupon:
        await update.message.reply_text("❌ الكود غير صحيح.")
        context.user_data['awaiting_coupon'] = False
        return
    if coupon.get("expires_at") < datetime.utcnow():
        await update.message.reply_text("❌ انتهت صلاحية هذا الكود.")
        context.user_data['awaiting_coupon'] = False
        return
    if coupon.get("used_count", 0) >= coupon.get("max_uses", 1):
        await update.message.reply_text("❌ تم استخدام هذا الكود بالحد الأقصى.")
        context.user_data['awaiting_coupon'] = False
        return
    update_user(uid, {"pending_action": {"type": "coupon", "code": code, "points": coupon["points"]}})
    web_app_button = KeyboardButton("📺 شاهد الإعلان واستلم الكوبون (موبايل)", web_app=WebAppInfo(url=AD_URL))
    reply_markup = ReplyKeyboardMarkup(keyboard=[[web_app_button]], resize_keyboard=True, one_time_keyboard=True)
    await update.message.reply_text(f"🎟️ *كود خصم `{code}`*\nلديك {coupon['points']} نقطة قابلة للسحب في انتظارك.\n📱 *موبايل:* اضغط الزر أسفل الشاشة\n💻 *لاب:* اضغط الزر أدناه 👇", parse_mode="Markdown", reply_markup=reply_markup)
    await update.message.reply_text("💻 *للاب فقط:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد الإعلان واستلم الكوبون (لاب)", web_app=WebAppInfo(url=AD_URL))]]))
    context.user_data['awaiting_coupon'] = False

# ========== العروض الموقوتة ==========
def get_active_flash_offer():
    now = datetime.utcnow()
    return offers_col.find_one({"active": True, "start_time": {"$lte": now}, "end_time": {"$gte": now}})

async def admin_flash_offer(update, context):
    if update.effective_user.id != ADMIN_ID: return
    try:
        multiplier = int(context.args[0])
        duration = int(context.args[1])
        start = datetime.utcnow()
        end = start + timedelta(minutes=duration)
        offers_col.update_one({}, {"$set": {"active": True, "multiplier": multiplier, "start_time": start, "end_time": end}}, upsert=True)
        await log_action(ADMIN_ID, "تفعيل عرض موقوت", None, f"مضاعف ×{multiplier} لمدة {duration} دقيقة")
        await update.message.reply_text(f"✅ عرض موقوت: ×{multiplier} لمدة {duration} دقيقة.")
    except:
        await update.message.reply_text("استخدام: /offer <مضاعف> <مدة_دقائق>")

async def admin_stop_offer(update, context):
    if update.effective_user.id != ADMIN_ID: return
    offers_col.update_one({}, {"$set": {"active": False}})
    await log_action(ADMIN_ID, "إيقاف عرض موقوت", None, "")
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
    user_data = get_user(uid)
    if user_data.get("banned", False):
        await update.message.reply_text("⛔ أنت محظور.")
        context.user_data['awaiting_challenge'] = False
        return
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
    kb = [[InlineKeyboardButton("✍️ كتابة محتوى", callback_data="content_menu"), InlineKeyboardButton("💰 كسب النقاط", callback_data="earn_menu")],
          [InlineKeyboardButton("👤 حسابي", callback_data="account_menu"), InlineKeyboardButton("🏆 المتصدرين", callback_data="leaderboard")],
          [InlineKeyboardButton("ℹ️ تعليمات", callback_data="help")]]
    return InlineKeyboardMarkup(kb)

async def content_menu(update, context):
    q = update.callback_query
    await q.answer()
    if get_user(q.from_user.id).get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
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
    if get_user(q.from_user.id).get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
    kb = [[InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad"), InlineKeyboardButton("🎲 صندوق الحظ", callback_data="mystery_box")],
          [InlineKeyboardButton("🎡 عجلة الحظ", callback_data="wheel"), InlineKeyboardButton("📋 مهام اليوم", callback_data="daily_tasks")],
          [InlineKeyboardButton("🎁 دعوة صديق", callback_data="referral_share"), InlineKeyboardButton("⚔️ تحدي صديق", callback_data="challenge_friend")],
          [InlineKeyboardButton("🎟️ كود خصم", callback_data="redeem_coupon"), InlineKeyboardButton("🎁 عروض خاصة", callback_data="special_offers")],
          [InlineKeyboardButton("🌍 التحدي العالمي", callback_data="global_challenge"), InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]
    await q.edit_message_text("💰 *كسب النقاط*\nاختر طريقة:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def account_menu(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    if u.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
    
    ambassador = "🏅 *سفير البوت* 🏅\n" if u.get("ambassador_badge") else ""
    badges_text = "🏅 *الشارات:* " + ", ".join(u.get("badges", [])) if u.get("badges") else "🏅 *الشارات:* لا توجد"
    next_streak = u.get("ad_streak",0)+1
    next_level = "فضة"
    for lvl, data in BOX_LEVELS.items():
        if data["streak_range"][0] <= next_streak <= data["streak_range"][1]:
            next_level = lvl
            break
    level_name = u.get("level", "مبتدئ")
    level_info = LEVELS.get(level_name, LEVELS["مبتدئ"])
    next_level_name = get_next_level(u)
    pending = u.get("pending_level_upgrade")
    next_level_text = ""
    if next_level_name:
        next_lvl = LEVELS[next_level_name]
        remaining_ads = pending.get("ads_remaining", next_lvl["unlock_ads"]) if pending else next_lvl["unlock_ads"]
        highest = u.get("highest_total_points", u["points"]+u["withdrawable_points"])
        points_needed = max(0, next_lvl["points"] - highest)
        next_level_text = f"\n🎯 *المستوى التالي:* {next_level_name}\n   • النقاط المتبقية: {points_needed}\n   • إعلانات متبقية لفتح المستوى: {remaining_ads}"
    else:
        next_level_text = "\n🏆 *أنت في أعلى مستوى (أسطورة)!* 🏆"
    
    spins_left = max(0, WHEEL_DAILY_LIMIT - u.get("wheel_spins_today", 0))
    
    # حساب الحد اليومي حسب مستوى المستخدم (للعرض فقط)
    user_level = u.get("level", "مبتدئ")
    max_ads_user = LEVELS.get(user_level, {}).get("unlock_ads", 8)  # 8 افتراضي للمبتدئ بدلاً من 0
    
    # بناء النص خارج أي شرط
    text = (f"👤 *حسابي*\n\n{ambassador}"
            f"✨ نقاط عادية: *{u['points']}*\n"
            f"💰 نقاط قابلة للسحب: *{u.get('withdrawable_points',0)}*\n"
            f"✍️ استخدامات: *{u['uses']}*\n"
            f"🎁 دعوات مباشرة: *{u['referrals']}*\n"
            f"🎁 دعوات غير مباشرة: *{u.get('referral_level2_count',0)}*\n"
            f"🔥 Streak: *{u.get('ad_streak',0)} يوم* (مضاعف {u.get('ad_multiplier',1.0)}x)\n"
            f"📊 إجمالي الإعلانات: *{u.get('total_ads_watched',0)}*\n"
            f"🎲 غداً صندوقك: *{next_level}*\n\n"
            f"{badges_text}\n"
            f"⭐ *مستواك:* {level_name} (مضاعف {level_info['multiplier']}x للإعلانات){next_level_text}\n\n"
            f"📺 كل إعلان: +{POINTS_PER_AD} نقطة × المضاعفات (حد {max_ads_user}/يوم حسب مستواك)\n"
            f"🎡 عجلة الحظ: متبقي اليوم *{spins_left}* من {WHEEL_DAILY_LIMIT} (جوائز تصل إلى 2000 نقطة)\n"
            f"🎁 كل دعوة مباشرة: +{REFERRAL_WITHDRAWABLE} نقطة + {REFERRAL_COMMISSION_PERCENT}% عمولة\n"
            f"🎁 كل دعوة غير مباشرة: +{REFERRAL_LEVEL2} نقطة\n"
            f"💰 التحويل: {POINTS_PER_DOLLAR} نقطة = $1\n"
            f"🏧 حد السحب: {MIN_WITHDRAW_POINTS} نقطة (${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR})\n\n"
            f"🔄 تحويل النقاط العادية إلى قابلة للسحب:\n  • نسبة التحويل: {CONVERSION_RATE}% (100 نقطة عادية → {CONVERSION_RATE} نقطة قابلة للسحب)\n  • الحد اليومي: {MAX_DAILY_CONVERSION} نقطة عادية")
    
    kb = [[InlineKeyboardButton("🔄 تحويل نقاطي", callback_data="convert_points"), InlineKeyboardButton("💰 سحب النقاط", callback_data="withdraw")],
          [InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def help_callback(update, context):
    q = update.callback_query
    await q.answer()
    if get_user(q.from_user.id).get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
    text = (f"ℹ️ *تعليمات البوت*\n\n1️⃣ شاهد إعلانات يومياً (حد {MAX_ADS_PER_DAY}).\n2️⃣ Streak: كل يوم يزيد المضاعف 5% حتى 2x.\n3️⃣ صندوق الحظ المتطور (فضة/ذهب/ألماس) حسب Streak.\n4️⃣ عجلة الحظ: تدور العجلة حتى {WHEEL_DAILY_LIMIT} مرات يومياً، تكسب نقاطاً قابلة للسحب.\n5️⃣ المهام اليومية: إعلان + استخدام = 300 نقطة بونص (يتطلب إعلاناً).\n6️⃣ الإحالات: مكافأة {REFERRAL_WITHDRAWABLE} لكل مدعو مباشر، وعمولة {REFERRAL_COMMISSION_PERCENT}% من أرباح إعلاناته.\n7️⃣ المسابقة الأسبوعية: كل إثنين جوائز لأكثر 10.\n8️⃣ مهمة أسبوعية: {WEEKLY_MISSION_TARGET} إعلان ↔ {WEEKLY_MISSION_REWARD} نقطة.\n9️⃣ تحدي الأصدقاء: تحدَّ صديقاً والفائز يحصل على 1000 نقطة.\n🔟 شارات: المدعو الأول، سفير، 100 إعلان، السبوعي، الأسطورة.\n1️⃣1️⃣ مكافأة التسجيل المبكر: أول {EARLY_BIRD_LIMIT} مستخدم يحصلون على {EARLY_BIRD_POINTS} نقطة (إعلان).\n1️⃣2️⃣ العروض الموقوتة: يعلن الأدمن عن مضاعفات محدودة.\n1️⃣3️⃣ مسابقة شهرية: أعلى رصيد يحصل على 50$.\n1️⃣4️⃣ تحويل النقاط: حوِّل نقاطك العادية إلى نقابلة للسحب بنسبة {CONVERSION_RATE}% (حد {MAX_DAILY_CONVERSION} نقطة عادية يومياً).\n1️⃣5️⃣ المستويات: تترقى إلى مستويات أعلى عند جمع النقاط ومشاهدة إعلانات محددة. كل مستوى يمنح مضاعفاً أكبر ومكافآت.\n1️⃣6️⃣ كوبونات الخصم: استخدم أكواد خصم للحصول على نقاط إضافية (تتطلب إعلاناً).\n1️⃣7️⃣ التحدي العالمي: يعلن الأدمن تحدياً جماعياً، وتوزع الجوائز حسب المشاركة.")
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]))

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
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="earn_menu")]]))

async def referral_share(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    if get_user(uid).get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
    link = f"https://t.me/easy_free1bot?start=ref_{uid}"
    whatsapp = f"https://wa.me/?text=اشترك في هذا البوت واكسب نقاطاً: {link}"
    telegram = f"https://t.me/share/url?url={link}&text=انضم إلي"
    facebook = f"https://www.facebook.com/sharer/sharer.php?u={link}"
    twitter = f"https://twitter.com/intent/tweet?text=اكسب نقاطاً مع هذا البوت&url={link}"
    kb = [[InlineKeyboardButton("📱 واتساب", url=whatsapp), InlineKeyboardButton("✈️ تليجرام", url=telegram)],
          [InlineKeyboardButton("📘 فيسبوك", url=facebook), InlineKeyboardButton("🐦 تويتر", url=twitter)],
          [InlineKeyboardButton("📋 نسخ الرابط", callback_data="copy_link")],
          [InlineKeyboardButton("🔙 رجوع", callback_data="earn_menu")]]
    await q.edit_message_text(f"🎁 *رابط دعوتك:*\n`{link}`\n\nاختر المنصة:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def copy_link(update, context):
    q = update.callback_query
    await q.answer()
    link = f"https://t.me/easy_free1bot?start=ref_{q.from_user.id}"
    await q.message.reply_text(f"✅ تم نسخ الرابط:\n`{link}`", parse_mode="Markdown")

def tone_menu():
    return InlineKeyboardMarkup([[InlineKeyboardButton("👔 رسمي", callback_data="tone_formal"), InlineKeyboardButton("😄 عامي", callback_data="tone_casual")],
                                 [InlineKeyboardButton("🔥 تسويقي", callback_data="tone_marketing"), InlineKeyboardButton("💬 مباشر", callback_data="tone_simple")]])

def admin_menu():
    kb = [[InlineKeyboardButton("👥 المستخدمون", callback_data="admin_users"), InlineKeyboardButton("📊 الإحصائيات", callback_data="admin_stats")],
          [InlineKeyboardButton("➕ إضافة نقاط", callback_data="admin_add_points_btn"), InlineKeyboardButton("➖ خصم نقاط", callback_data="admin_remove_points_btn")],
          [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="admin_ban_btn"), InlineKeyboardButton("✅ إلغاء حظر", callback_data="admin_unban_btn")],
          [InlineKeyboardButton("📋 المحظورين", callback_data="admin_list_banned_btn"), InlineKeyboardButton("🔍 معلومات مستخدم", callback_data="admin_userinfo_btn")],
          [InlineKeyboardButton("💰 طلبات السحب", callback_data="admin_withdrawals")],
          [InlineKeyboardButton("📢 رسالة جماعية", callback_data="admin_broadcast")],
          [InlineKeyboardButton("🌍 إدارة التحدي العالمي", callback_data="admin_global_challenge")],
          [InlineKeyboardButton("📋 سجل التدقيق", callback_data="admin_audit_log_0")],
          [InlineKeyboardButton("📉 تحليل التسرب", callback_data="admin_churn")],
          [InlineKeyboardButton("📁 تصدير Excel", callback_data="admin_export")]]
    return InlineKeyboardMarkup(kb)

# ========== التحدي العالمي ==========
async def get_active_global_challenge():
    return global_challenges_col.find_one({"active": True})

async def start_global_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ غير مصرح.")
        return
    try:
        target_ads = int(context.args[0])
        prize_pool = int(context.args[1])
        days = int(context.args[2]) if len(context.args) > 2 else 7
        end_date = datetime.utcnow() + timedelta(days=days)
        global_challenges_col.update_many({}, {"$set": {"active": False}})
        challenge = {"active": True, "target_ads": target_ads, "current_ads": 0, "prize_pool": prize_pool,
                     "start_date": datetime.utcnow(), "end_date": end_date, "created_by": ADMIN_ID}
        global_challenges_col.insert_one(challenge)
        users_col.update_many({}, {"$set": {"global_challenge_ads": 0, "global_challenge_reward_claimed": False}})
        await log_action(ADMIN_ID, "بدء تحدٍ عالمي", None, f"الهدف: {target_ads} إعلان, الجائزة: {prize_pool} نقطة, المدة: {days} يوم")
        await update.message.reply_text(f"✅ *تم بدء التحدي العالمي!*\n🎯 الهدف: {target_ads} إعلان جماعياً\n🏆 الجائزة الكلية: {prize_pool} نقطة قابلة للسحب\n⏳ المدة: {days} يوم (تنتهي {end_date.strftime('%Y-%m-%d %H:%M UTC')})\n\nشارك مع الجميع لتحقيق الهدف واحصل على حصتك من الجائزة!", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: استخدم `/start_challenge <هدف_الإعلانات> <جائزة_كلية> [أيام]`\n{str(e)}")



async def test_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("✅ الزر يعمل! الآن نصلح سجل التدقيق.")



async def end_global_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ غير مصرح.")
        return
    await process_global_challenge_end(context.bot, force=True)
    await log_action(ADMIN_ID, "إنهاء التحدي العالمي (يدوي)", None, "")
    await update.message.reply_text("✅ تم إنهاء التحدي العالمي وتوزيع الجوائز (إن تحقق الهدف).")

async def global_challenge_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    if user.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
    challenge = await get_active_global_challenge()
    if not challenge:
        await q.message.reply_text("🌍 *لا يوجد تحدٍ عالمي نشط حالياً.*\nانتظر إعلان الأدمن.", parse_mode="Markdown")
        return
    current_ads = challenge["current_ads"]
    target = challenge["target_ads"]
    percent = (current_ads / target) * 100 if target else 0
    remaining_seconds = (challenge["end_date"] - datetime.utcnow()).total_seconds()
    days_left = int(remaining_seconds // 86400)
    hours_left = int((remaining_seconds % 86400) // 3600)
    time_left = f"{days_left} يوماً و {hours_left} ساعة" if days_left > 0 else f"{hours_left} ساعة"
    top_users = users_col.find({"global_challenge_ads": {"$gt": 0}}).sort("global_challenge_ads", -1).limit(10)
    leaderboard_text = ""
    rank = 1
    for u in top_users:
        try:
            name = (await context.bot.get_chat(int(u["_id"]))).first_name
        except:
            name = f"مستخدم {u['_id'][-4:]}"
        leaderboard_text += f"{rank}. {name} — {u['global_challenge_ads']} إعلان\n"
        rank += 1
    text = (f"🌍 *التحدي العالمي*\n\n🎯 التقدم: {current_ads} / {target} إعلان ({percent:.1f}%)\n🏆 الجائزة الكلية: {challenge['prize_pool']} نقطة\n⏳ الوقت المتبقي: {time_left}\n\n🏅 *أفضل المساهمين:*\n{leaderboard_text if leaderboard_text else 'لا توجد مساهمات بعد.'}\n\nكل إعلان تشاهده يُضاف إلى الرصيد الجماعي. عند تحقيق الهدف، تُوزع الجائزة حسب نسبة مشاركتك!")
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="earn_menu")]]))

async def process_global_challenge_end(bot, force=False):
    challenge = await get_active_global_challenge()
    if not challenge:
        return
    if not force and datetime.utcnow() < challenge["end_date"]:
        return
    global_challenges_col.update_one({"_id": challenge["_id"]}, {"$set": {"active": False}})
    if challenge["current_ads"] >= challenge["target_ads"]:
        total_ads = challenge["current_ads"]
        prize_pool = challenge["prize_pool"]
        cursor = users_col.find({"global_challenge_ads": {"$gt": 0}})
        for user in cursor:
            ads = user["global_challenge_ads"]
            reward = int(prize_pool * ads / total_ads)
            if reward > 0:
                current_w = user.get("withdrawable_points", 0)
                update_user(user["_id"], {"withdrawable_points": current_w + reward, "global_challenge_reward_claimed": True})
                try:
                    await bot.send_message(int(user["_id"]), f"🏆 *التحدي العالمي*\nلقد حققنا الهدف! مساهمتك {ads} إعلان تمنحك *{reward} نقطة قابلة للسحب* كجائزة! 🎉", parse_mode="Markdown")
                except:
                    pass
        await bot.send_message(ADMIN_ID, f"✅ تم توزيع جوائز التحدي العالمي بنجاح. إجمالي المساهمين: {users_col.count_documents({'global_challenge_ads': {'$gt': 0}})}")
    else:
        await bot.send_message(ADMIN_ID, "⚠️ انتهى التحدي العالمي دون تحقيق الهدف. لم يتم توزيع الجوائز.")
    users_col.update_many({}, {"$set": {"global_challenge_ads": 0, "global_challenge_reward_claimed": False}})

async def admin_global_challenge_btn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🌍 *إدارة التحدي العالمي*\n\n• `/start_challenge <هدف> <جائزة> [أيام]` – بدء تحدٍ جديد\n• `/end_challenge` – إنهاء التحدي الحالي وتوزيع الجوائز\nمثال: `/start_challenge 1000000 50000 7`", parse_mode="Markdown")

# ========== أوامر الأدمن ==========
async def admin_add_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ غير مصرح.")
        return
    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
        point_type = context.args[2].lower() if len(context.args) > 2 else "normal"
        if point_type not in ["normal", "withdrawable"]:
            await update.message.reply_text("❌ نوع النقاط غير صحيح. استخدم `normal` أو `withdrawable`.")
            return
        user = get_user(user_id)
        if point_type == "normal":
            new_points = user["points"] + amount
            update_user(user_id, {"points": new_points})
            await log_action(ADMIN_ID, "إضافة نقاط عادية", user_id, f"{amount} نقطة")
            await update.message.reply_text(f"✅ تم إضافة {amount} نقطة عادية للمستخدم `{user_id}`. رصيده الآن: *{new_points}*", parse_mode="Markdown")
        else:
            new_w = user["withdrawable_points"] + amount
            update_user(user_id, {"withdrawable_points": new_w})
            await log_action(ADMIN_ID, "إضافة نقاط قابلة للسحب", user_id, f"{amount} نقطة")
            await update.message.reply_text(f"✅ تم إضافة {amount} نقطة قابلة للسحب للمستخدم `{user_id}`. رصيده الآن: *{new_w}*", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: استخدم `/addpoints <user_id> <amount> [normal|withdrawable]`\n{str(e)}")

async def admin_remove_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ غير مصرح.")
        return
    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
        point_type = context.args[2].lower() if len(context.args) > 2 else "normal"
        if point_type not in ["normal", "withdrawable"]:
            await update.message.reply_text("❌ نوع النقاط غير صحيح. استخدم `normal` أو `withdrawable`.")
            return
        user = get_user(user_id)
        if point_type == "normal":
            if user["points"] < amount:
                await update.message.reply_text(f"❌ رصيد المستخدم لا يكفي. رصيده {user['points']} نقطة.")
                return
            new_points = user["points"] - amount
            update_user(user_id, {"points": new_points})
            await log_action(ADMIN_ID, "خصم نقاط عادية", user_id, f"{amount} نقطة")
            await update.message.reply_text(f"✅ تم خصم {amount} نقطة عادية من المستخدم `{user_id}`. رصيده الآن: *{new_points}*", parse_mode="Markdown")
        else:
            if user["withdrawable_points"] < amount:
                await update.message.reply_text(f"❌ رصيد المستخدم القابل للسحب لا يكفي. رصيده {user['withdrawable_points']} نقطة.")
                return
            new_w = user["withdrawable_points"] - amount
            update_user(user_id, {"withdrawable_points": new_w})
            await log_action(ADMIN_ID, "خصم نقاط قابلة للسحب", user_id, f"{amount} نقطة")
            await update.message.reply_text(f"✅ تم خصم {amount} نقطة قابلة للسحب من المستخدم `{user_id}`. رصيده الآن: *{new_w}*", parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: استخدم `/removepoints <user_id> <amount> [normal|withdrawable]`\n{str(e)}")

async def admin_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ غير مصرح.")
        return
    try:
        user_id = int(context.args[0])
        user = get_user(user_id)
        if user.get("banned", False):
            await update.message.reply_text(f"⚠️ المستخدم `{user_id}` محظور بالفعل.")
            return
        update_user(user_id, {"banned": True})
        await log_action(ADMIN_ID, "حظر مستخدم", user_id, "")
        await update.message.reply_text(f"✅ تم حظر المستخدم `{user_id}`. لن يتمكن من استخدام البوت.")
        try:
            await context.bot.send_message(user_id, "⛔ لقد تم حظرك من استخدام هذا البوت. للمزيد من المعلومات، تواصل مع الإدارة.")
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: استخدم `/ban <user_id>`\n{str(e)}")

async def admin_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ غير مصرح.")
        return
    try:
        user_id = int(context.args[0])
        user = get_user(user_id)
        if not user.get("banned", False):
            await update.message.reply_text(f"⚠️ المستخدم `{user_id}` غير محظور.")
            return
        update_user(user_id, {"banned": False})
        await log_action(ADMIN_ID, "إلغاء حظر مستخدم", user_id, "")
        await update.message.reply_text(f"✅ تم إلغاء حظر المستخدم `{user_id}`. يمكنه الآن استخدام البوت.")
        try:
            await context.bot.send_message(user_id, "✅ تم إلغاء حظرك. يمكنك الآن استخدام البوت مجدداً.")
        except:
            pass
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: استخدم `/unban <user_id>`\n{str(e)}")
      

async def admin_list_banned(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID:
        await query.answer("⛔ غير مصرح.", show_alert=True)
        return

    banned_users = list(users_col.find({"banned": True}))
    if not banned_users:
        await query.message.reply_text("✅ لا يوجد مستخدمون محظورون حالياً.")
        return

    text = "🚫 *قائمة المحظورين*\n\n"
    for user in banned_users:
        uid = user["_id"]
        # نحاول جلب الاسم، وإذا فشل نضع الـ ID فقط
        try:
            chat = await context.bot.get_chat(int(uid))
            name = chat.first_name
        except Exception:
            name = f"مستخدم ({uid})"
        text += f"• {name}\n   🆔 `{uid}`\n\n"

    await query.message.reply_text(text, parse_mode="Markdown")


async def admin_user_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ غير مصرح.")
        return
    try:
        user_id = int(context.args[0])
        user = get_user(user_id)
        try:
            chat = await context.bot.get_chat(user_id)
            name = chat.first_name
            username = f"@{chat.username}" if chat.username else "لا يوجد"
        except:
            name = "غير معروف"
            username = "غير معروف"
        banned_status = "✅ محظور" if user.get("banned") else "🟢 غير محظور"
        text = (f"👤 *معلومات المستخدم*\n• الاسم: {name}\n• المعرف: {username}\n• ID: `{user_id}`\n• المستوى: {user.get('level', 'مبتدئ')}\n• النقاط العادية: {user['points']}\n• النقاط القابلة للسحب: {user.get('withdrawable_points',0)}\n• Streak: {user.get('ad_streak',0)} يوم\n• إجمالي الإعلانات: {user.get('total_ads_watched',0)}\n• الدعوات المباشرة: {user.get('referrals',0)}\n• الشارات: {', '.join(user.get('badges',[])) or 'لا توجد'}\n• الحالة: {banned_status}\n• مساهمة التحدي العالمي: {user.get('global_challenge_ads',0)} إعلان")
        await update.message.reply_text(text, parse_mode="Markdown")
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: استخدم `/userinfo <user_id>`\n{str(e)}")



async def log_cheat(user_id: int, cheat_type: str, details: str = ""):
    cheat_logs_col.insert_one({
        "user_id": user_id,
        "type": cheat_type,
        "details": details,
        "timestamp": datetime.utcnow()
    })




# ========== أزرار الأدمن ==========
async def admin_add_points_btn(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("➕ *إضافة نقاط*\nأرسل الأمر: `/addpoints <user_id> <العدد> [normal|withdrawable]`\n\nمثال: `/addpoints 123456789 500 normal`", parse_mode="Markdown")

async def admin_remove_points_btn(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("➖ *خصم نقاط*\nأرسل الأمر: `/removepoints <user_id> <العدد> [normal|withdrawable]`\n\nمثال: `/removepoints 123456789 200 normal`", parse_mode="Markdown")

async def admin_ban_btn(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🚫 *حظر مستخدم*\nأرسل الأمر: `/ban <user_id>`", parse_mode="Markdown")

async def admin_unban_btn(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("✅ *إلغاء حظر*\nأرسل الأمر: `/unban <user_id>`", parse_mode="Markdown")

async def admin_list_banned_btn(update, context):
    await admin_list_banned(update, context)

async def admin_userinfo_btn(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("🔍 *معلومات مستخدم*\nأرسل الأمر: `/userinfo <user_id>`", parse_mode="Markdown")



async def cheat_logs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ غير مصرح.")
        return
    logs = list(cheat_logs_col.find({}).sort("timestamp", -1).limit(10))
    if not logs:
        await update.message.reply_text("✅ لا توجد مخالفات.")
        return
    text = "🚨 *آخر المخالفات*\n\n"
    for log in logs:
        time_str = log["timestamp"].strftime("%H:%M:%S")
        text += f"• {time_str} - المستخدم {log['user_id']} - {log['type']}\n"
    await update.message.reply_text(text, parse_mode="Markdown")
  


# ========== تحويل النقاط ==========
async def convert_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user_data = get_user(uid)
    if user_data.get("banned", False):
        await query.answer("⛔ أنت محظور", show_alert=True)
        return
    user_data = check_daily_tasks(user_data)
    update_user(uid, {"last_task_date": user_data["last_task_date"], "daily_converted": user_data["daily_converted"]})
    remaining_today = MAX_DAILY_CONVERSION - user_data.get("daily_converted", 0)
    if remaining_today <= 0:
        await query.message.reply_text("⚠️ *لقد وصلت إلى الحد الأقصى للتحويل اليومي.*\nارجع غداً للمزيد.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="account_menu")]]))
        return
    max_convertible = min(user_data["points"], remaining_today)
    if max_convertible < 100:
        await query.message.reply_text(f"❌ *رصيدك العادي لا يكفي للتحويل.*\nالحد الأدنى للتحويل هو 100 نقطة عادية.\nرصيدك الحالي: {user_data['points']} نقطة.\nيمكنك تحويل حتى {remaining_today} نقطة اليوم.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="account_menu")]]))
        return
    await query.message.reply_text(f"💱 *تحويل النقاط*\n\nرصيدك العادي: *{user_data['points']}*\nالحد الأقصى للتحويل اليومي المتبقي: *{remaining_today}* نقطة\nنسبة التحويل: {CONVERSION_RATE}% (كل 100 نقطة عادية → {CONVERSION_RATE} نقطة قابلة للسحب)\n\nأرسل عدد النقاط العادية التي تريد تحويلها (مضاعفاً للـ 100، بحد أدنى 100).", parse_mode="Markdown")
    context.user_data['awaiting_conversion'] = True

async def process_conversion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_conversion'):
        return
    uid = update.effective_user.id
    user_data = get_user(uid)
    if user_data.get("banned", False):
        await update.message.reply_text("⛔ أنت محظور.")
        context.user_data['awaiting_conversion'] = False
        return
    try:
        amount = int(update.message.text.strip())
        if amount <= 0 or amount % 100 != 0:
            await update.message.reply_text("❌ يجب أن يكون المبلغ مضاعفاً للـ 100 وأكبر من 0.")
            return
    except ValueError:
        await update.message.reply_text("❌ يرجى إرسال رقم صحيح.")
        return
    user_data = get_user(uid)
    user_data = check_daily_tasks(user_data)
    remaining_today = MAX_DAILY_CONVERSION - user_data.get("daily_converted", 0)
    if amount > user_data["points"]:
        await update.message.reply_text(f"❌ ليس لديك {amount} نقطة عادية. رصيدك الحالي: {user_data['points']}.")
        return
    if amount > remaining_today:
        await update.message.reply_text(f"❌ يتجاوز المبلغ الحد اليومي المتبقي ({remaining_today} نقطة).")
        return
    withdrawable_gained = int(amount * CONVERSION_RATE / 100)
    new_points = user_data["points"] - amount
    new_withdrawable = user_data["withdrawable_points"] + withdrawable_gained
    new_daily_converted = user_data.get("daily_converted", 0) + amount
    update_user(uid, {"points": new_points, "withdrawable_points": new_withdrawable, "daily_converted": new_daily_converted})
    await update.message.reply_text(f"✅ *تم التحويل بنجاح!*\n\n🔄 حولت *{amount}* نقطة عادية → *{withdrawable_gained}* نقطة قابلة للسحب.\n✨ رصيدك العادي الآن: *{new_points}*\n💰 رصيدك القابل للسحب الآن: *{new_withdrawable}*\n📊 متبقي للتحويل اليوم: *{MAX_DAILY_CONVERSION - new_daily_converted}* نقطة.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
    context.user_data['awaiting_conversion'] = False

# ========== دوال البوت الأساسية ==========
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
    
    # لوحة الأدمن
    if uid == ADMIN_ID:
        await update.message.reply_text(f"👋 أهلاً *{name}* — لوحة الأدمن 🔧", parse_mode="Markdown", reply_markup=admin_menu())
        return
    
    # فحص الحظر
    u = get_user(uid)
    if u.get("banned", False):
        await update.message.reply_text("⛔ أنت محظور من استخدام هذا البوت. تواصل مع الإدارة.")
        return
    
    # الاشتراك الإجباري (للمستخدمين العاديين فقط)
    if not await is_subscribed(uid, context):
        await force_subscribe_message(update, context)
        return
    
    # هدية التسجيل المبكر
    if u.get("early_bird_rewarded") and not u.get("early_bird_notified") and not u.get("pending_action"):
        update_user(uid, {"pending_action": {"type": "early_bird", "points": EARLY_BIRD_POINTS}})
        web_app_button = KeyboardButton("🎁 استلام الهدية (موبايل)", web_app=WebAppInfo(url=EARLY_AD_URL))
        reply_markup = ReplyKeyboardMarkup(keyboard=[[web_app_button]], resize_keyboard=True, one_time_keyboard=True)
        await update.message.reply_text(f"🎉 *أنت من أوائل المستخدمين!* لديك {EARLY_BIRD_POINTS} نقطة.\n📱 *موبايل:* اضغط الزر أسفل الشاشة\n💻 *لاب:* اضغط الزر أدناه 👇", parse_mode="Markdown", reply_markup=reply_markup)
        await update.message.reply_text("💻 *للاب فقط:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎁 استلام الهدية (لاب)", web_app=WebAppInfo(url=EARLY_AD_URL))]]))
    else:
        await update.message.reply_text(f"👋 أهلاً *{name}*!\n✨ نقاط عادية: *{u['points']}*\n💰 نقاط قابلة للسحب: *{u.get('withdrawable_points',0)}*\n\n👇 اختر من القائمة:", parse_mode="Markdown", reply_markup=main_menu())


def check_ad_spam(user_id, context):
    last = context.user_data.get('last_ad_time', 0)
    now = datetime.utcnow().timestamp()
    if now - last < 10:
        return False
    context.user_data['last_ad_time'] = now
    return True


# ========== دوال المحتوى (AI) ==========
async def handle_platform(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = check_daily_tasks(get_user(uid))
    if u.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
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
    if u.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
    if u["points"] < POINTS_PER_USE:
        await q.message.reply_text("❌ نقاطك مش كافية!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد إعلان", callback_data="watch_ad")]]))
        return ConversationHandler.END
    await q.edit_message_text("📅 *جدولة محتوى أسبوعي*\nاكتب موضوع قناتك:", parse_mode="Markdown")
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
    if u.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
    u["tasks"]["used"] = True
    new_pts = u["points"] - POINTS_PER_USE
    update_user(uid, {"points": new_pts, "uses": u["uses"]+1, "tasks": u["tasks"], "last_task_date": u["last_task_date"]})
    prompts = {"facebook": f"بوست فيسبوك عن '{topic}' بأسلوب {tone}.", "instagram": f"كابشن انستجرام عن '{topic}' بأسلوب {tone}.", "twitter": f"تويت عن '{topic}' بأسلوب {tone}.", "linkedin": f"بوست لينكدإن عن '{topic}' بأسلوب {tone}.", "email": f"إيميل عن '{topic}' بأسلوب {tone}.", "ad": f"إعلان عن '{topic}' بأسلوب {tone}.", "article": f"مقال قصير عن '{topic}' بأسلوب {tone}.", "ideas": f"5 أفكار محتوى عن '{topic}'."}
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
    if u.get("banned", False):
        await update.message.reply_text("⛔ أنت محظور.")
        return ConversationHandler.END
    new_pts = u["points"] - POINTS_PER_USE
    update_user(uid, {"points": new_pts, "uses": u["uses"]+1})
    try:
        r = client.chat.completions.create(model="gpt-oss-120b", messages=[{"role":"system","content":"كاتب محتوى"},{"role":"user","content":f"7 بوستات تيليجرام عن '{topic}'"}])
        content = r.choices[0].message.content
        await update.message.reply_text(f"✅ *بوستات الأسبوع:*\n\n{content}\n💎 رصيدك المتبقي: *{new_pts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    except Exception as e:
        await update.message.reply_text(f"❌ خطأ: {str(e)[:100]}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 الرئيسية", callback_data="main_back")]]))
    return ConversationHandler.END

# ========== دوال الإعلانات والمكافآت ==========
async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("🔥 WebApp data received!")
    data = update.message.web_app_data.data
    print(f"Data: {data}")
    uid = update.effective_user.id

    # فحص السرعة: تخزين آخر وقت إعلان في user_data (ذاكرة مؤقتة)
    last_ad = context.user_data.get('last_ad_time', 0)
    now = datetime.utcnow().timestamp()
    if now - last_ad < 10:
        await update.message.reply_text("⚠️ يرجى الانتظار 10 ثوانٍ بين الإعلانات")
        return
    context.user_data['last_ad_time'] = now

    if data == "ad_watched":
        u = get_user(uid)
        if u.get("banned", False):
            await update.message.reply_text("⛔ أنت محظور.")
            return
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if u.get("last_ad_date") != today:
            update_user(uid, {"ad_watch_today": 0, "last_ad_date": today})
            u["ad_watch_today"] = 0
               # جلب الحد اليومي حسب مستوى المستخدم
        user_level = u.get("level", "مبتدئ")
        max_ads_user = LEVELS.get(user_level, {}).get("unlock_ads", 5)
        if u.get("ad_watch_today", 0) >= max_ads_user:
            await update.message.reply_text(f"❌ لقد استنفذت حدك اليومي ({max_ads_user} إعلان). مستواك: {user_level}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
            return
          
        flash = get_active_flash_offer()
        mul = update_ad_streak(uid, today)
        multiplier = flash["multiplier"] if flash else 1
        level_multiplier = LEVELS.get(u.get("level", "مبتدئ"), LEVELS["مبتدئ"])["multiplier"]
        earned = int(POINTS_PER_AD * mul * multiplier * level_multiplier)
        new_w = u["withdrawable_points"] + earned
        new_cnt = u["ad_watch_today"] + 1
        new_total = u.get("total_ads_watched", 0) + 1
        update_user(uid, {"withdrawable_points": new_w, "ad_watch_today": new_cnt, "last_ad_date": today, "total_ads_watched": new_total})
        current_total = u["points"] + u["withdrawable_points"]
        highest = u.get("highest_total_points", 0)
        if current_total > highest:
            update_user(uid, {"highest_total_points": current_total})
        if new_total >= 100 and "100 إعلان" not in u.get("badges", []):
            add_badge(uid, "100 إعلان")
            try: await context.bot.send_message(uid, "🏅 شارة 100 إعلان!", parse_mode="Markdown")
            except: pass
        if u.get("challenge_active"):
            update_user(uid, {"challenge_points": u.get("challenge_points", 0) + earned})
        cweek = datetime.utcnow().strftime("%Y-%W")
        if u.get("last_contest_week") != cweek:
            update_user(uid, {"weekly_ad_count": 0, "last_contest_week": cweek, "weekly_mission_claimed": False})
            u["weekly_ad_count"] = 0
        new_weekly = u.get("weekly_ad_count", 0) + 1
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
                    update_user(rid, {"withdrawable_points": ref["withdrawable_points"] + comm, "total_commission_earned": ref.get("total_commission_earned", 0) + comm})
                    try: await context.bot.send_message(rid, f"🎁 عمولة إحالة: +{comm} نقطة!", parse_mode="Markdown")
                    except: pass
        challenge = await get_active_global_challenge()
        if challenge:
            global_challenges_col.update_one({"_id": challenge["_id"]}, {"$inc": {"current_ads": 1}})
            update_user(uid, {"global_challenge_ads": u.get("global_challenge_ads", 0) + 1})
        u2 = check_daily_tasks(get_user(uid))
        u2["tasks"]["ad"] = True
        update_user(uid, {"tasks": u2["tasks"]})
        reduce_pending_level_ads(uid)
        upgrade_result = check_and_process_level_upgrade(uid)
        upgrade_msg = ""
        if upgrade_result:
            upgrade_msg = f"\n\n🎉 *تهانينا! لقد تم ترقيتك إلى مستوى {upgrade_result['new_level']}!* 🎉\n✅ مكافأة +{upgrade_result['reward']} نقطة قابلة للسحب."
        await update.message.reply_text(
            f"✅ *+{earned} نقطة!*\n💎 رصيدك: *{new_w}*\n🔥 مضاعف: {mul}x\n📊 اليوم: {new_cnt}/{max_ads_user}{upgrade_msg}",
            parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]])
        )
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
            elif pending["type"] == "coupon":
                code = pending.get("code")
                points = pending.get("points")
                coupon = coupons_col.find_one({"code": code})
                if coupon and coupon.get("used_count", 0) < coupon.get("max_uses", 1):
                    coupons_col.update_one({"_id": coupon["_id"]}, {"$inc": {"used_count": 1}})
                    new_withdrawable = u["withdrawable_points"] + points
                    update_user(uid, {"withdrawable_points": new_withdrawable, "pending_action": None})
                    await update.message.reply_text(f"🎟️ *تم تفعيل الكود بنجاح!* +{points} نقطة قابلة للسحب.", parse_mode="Markdown")
                else:
                    update_user(uid, {"pending_action": None})
                    await update.message.reply_text("❌ الكوبون غير صالح (انتهت صلاحيته أو تجاوز الحد الأقصى).", parse_mode="Markdown")

    elif data == "bonus_ad_watched":
        u = get_user(uid)
        if u.get("banned", False):
            await update.message.reply_text("⛔ أنت محظور.")
            return
        pending = u.get("pending_action")
        if pending and pending.get("type") == "claim_bonus":
            u2 = check_daily_tasks(u)
            if not u2["tasks"].get("bonus", False):
                update_user(uid, {"points": u2["points"] + 300, "tasks": {**u2["tasks"], "bonus": True}, "pending_action": None})
                await update.message.reply_text("🎉 تم إضافة 300 نقطة بونص!", parse_mode="Markdown")
            else:
                update_user(uid, {"pending_action": None})
                await update.message.reply_text("⚠️ تم استلام البونص مسبقاً.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ لا يوجد بونص معلق.", parse_mode="Markdown")



    elif data == "box_ad_watched":
        u = get_user(uid)
        if u.get("banned", False):
            await update.message.reply_text("⛔ أنت محظور.")
            return
        today = datetime.utcnow().strftime("%Y-%m-%d")
        if u.get("last_box_date") == today:
            await update.message.reply_text("❌ لقد فتحت الصندوق اليوم بالفعل!")
            return
        streak = u.get("ad_streak", 0)
        prize, msg, level = spin_mystery_box(streak)
        new_points = u["points"] + prize
        update_user(uid, {
            "points": new_points,
            "last_box_date": today,
            "pending_action": None
        })
        await update.message.reply_text(
            f"🎁 *صندوق {level}* 🎁\n{msg}!\n✨ ربحت *{prize} نقطة عادية*!\n💰 رصيدك العادي الآن: *{new_points}*",
            parse_mode="Markdown"
        )
        await log_action(uid, "فتح صندوق حظ", uid, f"{level} - {prize} نقطة")

 
  
    elif data == "referral_ad_watched":
        u = get_user(uid)
        if u.get("banned", False):
            await update.message.reply_text("⛔ أنت محظور.")
            return
        pending = u.get("pending_action")
        if pending and pending.get("type") == "referral_reward":
            points = pending.get("points", REFERRAL_WITHDRAWABLE)
            update_user(uid, {"withdrawable_points": u["withdrawable_points"] + points, "pending_action": None})
            await update.message.reply_text(f"🎉 تم إضافة {points} نقطة قابلة للسحب (مكافأة إحالة)!", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ لا توجد مكافأة إحالة معلقة.", parse_mode="Markdown")

    elif data == "early_ad_watched":
        u = get_user(uid)
        if u.get("banned", False):
            await update.message.reply_text("⛔ أنت محظور.")
            return
        pending = u.get("pending_action")
        if pending and pending.get("type") == "early_bird":
            points = pending.get("points", EARLY_BIRD_POINTS)
            update_user(uid, {"withdrawable_points": u["withdrawable_points"] + points, "early_bird_notified": True, "pending_action": None})
            await update.message.reply_text(f"🎉 تم استلام هدية التسجيل المبكر! +{points} نقطة قابلة للسحب.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ لا توجد هدية معلقة.", parse_mode="Markdown")

    elif data == "challenge_ad_watched":
        u = get_user(uid)
        if u.get("banned", False):
            await update.message.reply_text("⛔ أنت محظور.")
            return
        pending = u.get("pending_action")
        if pending and pending.get("type") == "challenge_reward":
            points = pending.get("points", 1000)
            update_user(uid, {"withdrawable_points": u["withdrawable_points"] + points, "pending_action": None})
            await update.message.reply_text(f"🏆 فزت في التحدي! +{points} نقطة قابلة للسحب.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ لا توجد جائزة تحدٍ معلقة.", parse_mode="Markdown")

    elif data == "monthly_ad_watched":
        u = get_user(uid)
        if u.get("banned", False):
            await update.message.reply_text("⛔ أنت محظور.")
            return
        pending = u.get("pending_action")
        if pending and pending.get("type") == "monthly_contest":
            points = pending.get("points", 50 * POINTS_PER_DOLLAR)
            update_user(uid, {"withdrawable_points": u["withdrawable_points"] + points, "pending_action": None})
            await update.message.reply_text(f"🏆 فزت في المسابقة الشهرية! +{points} نقطة قابلة للسحب.", parse_mode="Markdown")
        else:
            await update.message.reply_text("⚠️ لا توجد جائزة شهرية معلقة.", parse_mode="Markdown")

    elif data == "wheel_spun":
        u = get_user(uid)
        if u.get("banned", False):
            await update.message.reply_text("⛔ أنت محظور.")
            return
        pending = u.get("pending_action")
        if pending and pending.get("type") == "wheel":
            today = datetime.utcnow().strftime("%Y-%m-%d")
            if u.get("last_wheel_date") != today:
                update_user(uid, {"wheel_spins_today": 0, "last_wheel_date": today})
                spins_today = 0
            else:
                spins_today = u.get("wheel_spins_today", 0)
            if spins_today >= WHEEL_DAILY_LIMIT:
                await update.message.reply_text("⚠️ لقد استنفدت عدد مرات عجلة الحظ لهذا اليوم.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
                update_user(uid, {"pending_action": None})
                return
            prize = spin_wheel()
            new_w = u["withdrawable_points"] + prize
            new_spins = spins_today + 1
            update_user(uid, {"withdrawable_points": new_w, "wheel_spins_today": new_spins, "last_wheel_date": today, "pending_action": None})
            await update.message.reply_text(
                f"🎡 *عجلة الحظ* 🎡\nلقد ربحت *{prize} نقطة قابلة للسحب*!\n💰 رصيدك القابل للسحب الآن: *{new_w}*\n📊 متبقي اليوم: {WHEEL_DAILY_LIMIT - new_spins} من {WHEEL_DAILY_LIMIT}",
                parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]])
            )
        else:
            await update.message.reply_text("⚠️ لا يوجد طلب عجلة حظ معلق.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
          
async def mystery_box(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    u = get_user(q.from_user.id)
    if u.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
    if u.get("last_box_date") == datetime.utcnow().strftime("%Y-%m-%d"):
        await q.message.reply_text("❌ لقد فتحت الصندوق اليوم! عاود غداً.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]))
        return
    streak = u.get("ad_streak", 0)
    level = "فضة"
    for lvl, data in BOX_LEVELS.items():
        if data["streak_range"][0] <= streak <= data["streak_range"][1]:
            level = lvl
            break
    # زر للموبايل (ReplyKeyboardMarkup)
    web_app_button = KeyboardButton("🎁 شاهد الإعلان وافتح الصندوق (موبايل)", web_app=WebAppInfo(url=BOX_AD_URL))
    reply_markup = ReplyKeyboardMarkup(keyboard=[[web_app_button]], resize_keyboard=True, one_time_keyboard=True)
    await q.message.reply_text(
        f"🎲 *صندوق {level}* 🎲\n🔥 Streak: {streak}\n\n📱 *للموبايل:* اضغط الزر أسفل الشاشة\n💻 *للاب:* اضغط الزر أدناه",
        parse_mode="Markdown",
        reply_markup=reply_markup
    )
    # زر للاب (InlineKeyboardMarkup)
    await q.message.reply_text(
        "💻 *للاب فقط:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🎁 افتح صندوق {level} (لاب)", web_app=WebAppInfo(url=BOX_AD_URL))]
        ])
    )


async def watch_ad(update, context):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    if u.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
    today = datetime.utcnow().strftime("%Y-%m-%d")
    if u.get("last_ad_date") != today:
        update_user(uid, {"ad_watch_today": 0, "last_ad_date": today})
        u["ad_watch_today"] = 0
  # جلب الحد حسب مستوى المستخدم
    user_level = u.get("level", "مبتدئ")
    max_ads_user = LEVELS.get(user_level, {}).get("unlock_ads", 5)
    if u.get("ad_watch_today", 0) >= max_ads_user:
        await q.message.reply_text(f"❌ لقد استنفذت حدك اليومي ({max_ads_user} إعلان). مستواك: {user_level}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة", callback_data="main_back")]]))
        return
  
    level_multiplier = LEVELS.get(u.get("level", "مبتدئ"), LEVELS["مبتدئ"])["multiplier"]
    mul = update_ad_streak(uid, today)
    earn = int(POINTS_PER_AD * mul * level_multiplier)
    remaining = max_ads_user - u["ad_watch_today"]
    web_app_button = KeyboardButton("📺 شاهد الإعلان الآن (موبايل)", web_app=WebAppInfo(url=AD_URL))
    reply_markup = ReplyKeyboardMarkup(keyboard=[[web_app_button]], resize_keyboard=True, one_time_keyboard=True)
    await q.message.reply_text(f"📺 *شاهد الإعلان*\n🔥 مضاعف: {mul}x\n⭐ مستوى: {level_multiplier}x\n💰 ستربح: {earn} نقطة\n📊 تبقى: {remaining} إعلان.\n\n📱 *موبايل:* اضغط الزر أسفل الشاشة\n💻 *لاب:* اضغط الزر أدناه 👇", parse_mode="Markdown", reply_markup=reply_markup)
    await q.message.reply_text("💻 *للاب فقط:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد الإعلان (لاب)", web_app=WebAppInfo(url=AD_URL))]]))

async def daily_tasks(update, context):
    q = update.callback_query
    await q.answer()
    u = check_daily_tasks(get_user(q.from_user.id))
    if u.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
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
    if u.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
    if u["tasks"]["ad"] and u["tasks"]["used"] and not u["tasks"]["bonus"]:
        update_user(uid, {"pending_action": {"type": "claim_bonus"}})
        web_app_button = KeyboardButton("📺 شاهد الإعلان واستلم البونص (موبايل)", web_app=WebAppInfo(url=BONUS_AD_URL))
        reply_markup = ReplyKeyboardMarkup(keyboard=[[web_app_button]], resize_keyboard=True, one_time_keyboard=True)
        await q.message.reply_text("🎁 *بونص يومي*\nلديك 300 نقطة عادية في انتظارك.\n📱 *موبايل:* اضغط الزر أسفل الشاشة\n💻 *لاب:* اضغط الزر أدناه 👇", parse_mode="Markdown", reply_markup=reply_markup)
        await q.message.reply_text("💻 *للاب فقط:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد الإعلان واستلم البونص (لاب)", web_app=WebAppInfo(url=BONUS_AD_URL))]]))
    else:
        await q.message.reply_text("❌ لم تكمل المهام أو استلمت البونص مسبقاً!")

async def withdraw_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    u = get_user(uid)
    if u.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return

    w = u.get("withdrawable_points", 0)
    if w < MIN_WITHDRAW_POINTS:
        need = MIN_WITHDRAW_POINTS - w
        await q.message.reply_text(f"💰 *السحب*\nرصيدك القابل للسحب: {w} نقطة\nتحتاج {need} نقطة إضافية للحد الأدنى ({MIN_WITHDRAW_POINTS} نقطة).", parse_mode="Markdown")
        return

    max_usd = w // POINTS_PER_DOLLAR
    keyboard = [
        [InlineKeyboardButton("3$", callback_data="withdraw_3"),
         InlineKeyboardButton("5$", callback_data="withdraw_5"),
         InlineKeyboardButton("10$", callback_data="withdraw_10")],
        [InlineKeyboardButton("20$", callback_data="withdraw_20"),
         InlineKeyboardButton("50$", callback_data="withdraw_50"),
         InlineKeyboardButton("مبلغ مخصص 💸", callback_data="withdraw_custom")]
    ]
    await q.message.reply_text(
        f"💵 *اختر المبلغ المراد سحبه*\nالحد الأدنى: 3$\nأقصى مبلغ متاح: {max_usd}$",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )




async def withdraw_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_withdraw_amount'):
        return
    uid = update.effective_user.id
    user = get_user(uid)
    if user.get("banned", False):
        await update.message.reply_text("⛔ أنت محظور.")
        context.user_data.pop('awaiting_withdraw_amount', None)
        return
    try:
        amount_usd = float(update.message.text.strip())
        if amount_usd < 3:
            await update.message.reply_text("❌ الحد الأدنى للسحب هو 3 دولار.")
            return
        # تحويل من دولار إلى نقاط
        required_points = int(amount_usd * POINTS_PER_DOLLAR)
        w = user.get("withdrawable_points", 0)
        if required_points > w:
            await update.message.reply_text(f"❌ رصيدك لا يكفي. تحتاج {required_points} نقطة، لكن لديك {w} نقطة فقط.")
            return
        # تخزين المبلغ المطلوب في user_data مؤقتاً
        context.user_data['withdraw_amount_usd'] = amount_usd
        context.user_data['awaiting_withdraw_amount'] = False
        context.user_data['awaiting_withdraw_details'] = True
        await update.message.reply_text(
            "📝 *تفاصيل الدفع*\nأرسل الآن طريقة الدفع ومعلوماتك (مثال: `Vodafone Cash, 01012345678`):",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح (مثال: 5).")




async def withdraw_get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    phone = update.message.text.strip()
    if not phone:
        await update.message.reply_text("❌ لم ترسل أي معلومات. أعد المحاولة من البداية.")
        return ConversationHandler.END

    # استرجاع معلومات المستخدم
    u = get_user(uid)
    w = context.user_data.get("withdraw_amount", 0)
    amt = w // POINTS_PER_DOLLAR
    deduct = amt * POINTS_PER_DOLLAR
    new_w = u["withdrawable_points"] - deduct

    # تحديث الرصيد
    update_user(uid, {"withdrawable_points": new_w})

    # ت

# ========== دوال المتصدرين والأدمن القديمة ==========
def get_leaderboard(limit=10):
    cursor = users_col.find({}, {"_id": 1, "points": 1, "withdrawable_points": 1, "level": 1}).sort("points", -1).limit(limit)
    res = []
    for i, u in enumerate(cursor):
        total = u.get("points", 0) + u.get("withdrawable_points", 0)
        res.append({"rank": i+1, "user_id": u["_id"], "total_points": total, "level": u.get("level", "مبتدئ")})
    return res

async def leaderboard(update, context):
    q = update.callback_query
    await q.answer()
    if get_user(q.from_user.id).get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
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
            text += f"{e['rank']}. {name} — 💎 {e['total_points']} نقطة (مستوى {e['level']})\n"
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="main_back")]]))

async def admin_stats(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    total = users_col.count_documents({})
    uses = sum(u.get("uses", 0) for u in users_col.find())
    active = sum(1 for u in users_col.find() if u.get("ad_watch_today", 0) > 0)
    withdrawn = sum(w.get("amount_usd", 0) for w in withdrawals_col.find({"status": "approved"}))
    await q.message.reply_text(f"📊 *الإحصائيات*\n👥 المستخدمين: {total}\n📈 نشطاء اليوم: {active}\n✍️ الاستخدامات: {uses}\n💵 المسحوبات: {withdrawn}$", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]))

async def admin_users(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    total = users_col.count_documents({})
    await q.message.reply_text(f"👥 *المستخدمون*\nإجمالي: {total}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]))

# ========== البث الجماعي ==========
async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID:
        await q.answer("⛔ غير مصرح.", show_alert=True)
        return
    context.user_data['awaiting_broadcast'] = True
    await q.message.reply_text("📢 *رسالة جماعية*\nأرسل النص الذي تريد نشره:", parse_mode="Markdown")

async def admin_broadcast_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_broadcast'):
        return
    context.user_data['awaiting_broadcast'] = False
    msg = update.message.text
    status_msg = await update.message.reply_text("⏳ جاري الإرسال...")
    success = 0
    fail = 0
    all_users = list(users_col.find({}, {"_id": 1}))
    for user_doc in all_users:
        try:
            uid = int(user_doc["_id"])
            await context.bot.send_message(uid, f"📢 *رسالة من الإدارة:*\n\n{msg}", parse_mode="Markdown")
            success += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await log_action(ADMIN_ID, "بث جماعي", None, f"نجاح: {success}, فشل: {fail}")
    await status_msg.edit_text(
        f"✅ *تم البث*\n✓ نجاح: {success}\n✗ فشل: {fail}\n📊 إجمالي: {len(all_users)}",
        parse_mode="Markdown"
    )
    return ConversationHandler.END
  
    async def send_to_user(uid):
        try:
            await context.bot.send_message(uid, f"📢 *رسالة من الإدارة:*\n\n{msg}", parse_mode="Markdown")
            return True
        except Exception:
            return False
    all_users = list(users_col.find({}, {"_id": 1}))
    batch_size = 20
    for i in range(0, len(all_users), batch_size):
        batch = all_users[i:i+batch_size]
        tasks = []
        for user_doc in batch:
            try:
                uid = int(user_doc["_id"])
                tasks.append(send_to_user(uid))
            except:
                fail += 1
        if tasks:
            results = await asyncio.gather(*tasks)
            success += sum(results)
            fail += len(results) - sum(results)
        await asyncio.sleep(1)
    await log_action(ADMIN_ID, "بث جماعي", None, f"تم الإرسال لـ {success} مستخدم، فشل {fail} من {total_users}")
    await status_msg.edit_text(f"✅ *تم البث الجماعي*\n✓ نجاح: {success}\n✗ فشل: {fail}\n📊 إجمالي المستخدمين: {total_users}", parse_mode="Markdown")
    return ConversationHandler.END

# ========== طلبات السحب ==========
async def admin_withdrawals(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    pending = list(withdrawals_col.find({"status": "pending"}))
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
    withdrawal = withdrawals_col.find_one({"_id": ObjectId(rid), "status": "pending"})
    if not withdrawal:
        await q.message.reply_text("الطلب غير موجود.")
        return
    withdrawals_col.update_one({"_id": ObjectId(rid)}, {"$set": {"status": "approved"}})
    await log_action(ADMIN_ID, "قبول سحب", withdrawal["user_id"], f"{withdrawal['amount_usd']}$")
    try:
        await context.bot.send_message(withdrawal["user_id"], f"✅ تمت الموافقة على سحب {withdrawal['amount_usd']}$.", parse_mode="Markdown")
    except:
        pass
    await q.message.reply_text(f"✅ تمت الموافقة على سحب {withdrawal['amount_usd']}$.")
    await q.message.delete()
    await admin_withdrawals(update, context)

async def reject_withdraw(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    rid = q.data.split("_")[1]
    withdrawal = withdrawals_col.find_one({"_id": ObjectId(rid), "status": "pending"})
    if not withdrawal:
        await q.message.reply_text("الطلب غير موجود.")
        return
    u = get_user(withdrawal["user_id"])
    update_user(withdrawal["user_id"], {"withdrawable_points": u.get("withdrawable_points", 0) + withdrawal["points_deducted"]})
    withdrawals_col.update_one({"_id": ObjectId(rid)}, {"$set": {"status": "rejected"}})
    await log_action(ADMIN_ID, "رفض سحب", withdrawal["user_id"], f"{withdrawal['amount_usd']}$ تم إعادة {withdrawal['points_deducted']} نقطة")
    try:
        await context.bot.send_message(withdrawal["user_id"], f"❌ تم رفض السحب. تم إعادة {withdrawal['points_deducted']} نقطة.", parse_mode="Markdown")
    except:
        pass
    await q.message.reply_text(f"❌ تم رفض الطلب وإعادة {withdrawal['points_deducted']} نقطة.")
    await q.message.delete()
    await admin_withdrawals(update, context)

# ========== تصدير Excel ==========
async def admin_export(update, context):
    q = update.callback_query
    await q.answer()
    if q.from_user.id != ADMIN_ID: return
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Name","Points","Withdrawable","Uses","Referrals","Withdrawn","Join Date","Ads","Badges","Level","Banned","GlobalChallengeAds"])
    for user in users_col.find():
        try:
            name = (await context.bot.get_chat(int(user["_id"]))).first_name
        except:
            name = "Unknown"
        writer.writerow([user["_id"], name, user.get("points",0), user.get("withdrawable_points",0), user.get("uses",0), user.get("referrals",0), user.get("has_withdrawn_before",False), user.get("last_task_date",""), user.get("total_ads_watched",0), ", ".join(user.get("badges",[])), user.get("level","مبتدئ"), user.get("banned",False), user.get("global_challenge_ads",0)])
    output.seek(0)
    await log_action(ADMIN_ID, "تصدير بيانات", None, f"تم تصدير {users_col.count_documents({})} مستخدم")
    await q.message.reply_document(document=io.BytesIO(output.getvalue().encode()), filename="users_export.csv", caption="📊 تصدير البيانات")
    await q.message.reply_text("✅ تم التصدير.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")]]))

async def handle_nav(update, context):
    q = update.callback_query
    await q.answer()
    if q.data == "admin_back":
        await q.message.reply_text("🔧 لوحة الأدمن:", reply_markup=admin_menu())
    elif q.data in ("home", "new"):
        await main_back(update, context)

# ========== دوال المستويات ==========
def reduce_pending_level_ads(user_id):
    u = get_user(user_id)
    pending = u.get("pending_level_upgrade")
    if pending:
        remaining_ads = pending.get("ads_remaining", 0) - 1
        if remaining_ads <= 0:
            new_level = pending["target_level"]
            reward = LEVELS[new_level]["reward"]
            update_user(user_id, {"level": new_level, "pending_level_upgrade": None, "withdrawable_points": u.get("withdrawable_points", 0) + reward})
            add_badge(user_id, new_level)
        else:
            update_user(user_id, {"pending_level_upgrade": {"target_level": pending["target_level"], "ads_remaining": remaining_ads}})

def get_next_level(user):
    current = user.get("level", "مبتدئ")
    idx = LEVELS_LIST.index(current) if current in LEVELS_LIST else 0
    if idx + 1 < len(LEVELS_LIST):
        return LEVELS_LIST[idx + 1]
    return None

def check_and_process_level_upgrade(user_id):
    u = get_user(user_id)
    next_lvl = get_next_level(u)
    if not next_lvl:
        return None
    highest = u.get("highest_total_points", u["points"] + u["withdrawable_points"])
    required_points = LEVELS[next_lvl]["points"]
    required_ads = LEVELS[next_lvl]["unlock_ads"]
    if highest >= required_points:
        pending = u.get("pending_level_upgrade")
        if not pending or pending.get("target_level") != next_lvl:
            update_user(user_id, {"pending_level_upgrade": {"target_level": next_lvl, "ads_remaining": required_ads}})
            return None
        else:
            if pending.get("ads_remaining", required_ads) <= 0:
                new_level = next_lvl
                reward = LEVELS[new_level]["reward"]
                update_user(user_id, {"level": new_level, "pending_level_upgrade": None, "withdrawable_points": u.get("withdrawable_points", 0) + reward})
                add_badge(user_id, new_level)
                return {"new_level": new_level, "reward": reward}
    return None

# ========== المهام المجدولة الكاملة ==========
async def scheduled_tasks(app):
    while True:
        now = datetime.utcnow()
        # إنهاء التحدي العالمي إذا انتهى وقته
        challenge = await get_active_global_challenge()
        if challenge and now >= challenge["end_date"]:
            await process_global_challenge_end(app.bot, force=True)

        # تذكير يومي الساعة 9 صباحاً
        if now.hour == 9 and now.minute == 0:
            for user in users_col.find():
                try:
                    uid = int(user["_id"])
                    u = get_user(uid)
                    if u.get("banned", False): continue
                    await app.bot.send_message(uid, f"🔥 *تذكير يومي*\nStreak: {u.get('ad_streak',0)} يوم\nشاهد إعلانك الأول اليوم!", parse_mode="Markdown")
                except:
                    pass

        # تقرير يومي الساعة 11 مساءً
        if now.hour == 23 and now.minute == 0:
            for user in users_col.find():
                try:
                    uid = int(user["_id"])
                    u = get_user(uid)
                    if u.get("banned", False): continue
                    if u.get("last_daily_report_date") != now.strftime("%Y-%m-%d"):
                        await app.bot.send_message(uid, f"📊 *تقرير يومي*\nرصيدك القابل للسحب: {u.get('withdrawable_points',0)}\nإعلانات اليوم السابق: {u.get('ad_watch_today',0)}", parse_mode="Markdown")
                        update_user(uid, {"last_daily_report_date": now.strftime("%Y-%m-%d")})
                except:
                    pass

        # إعلان فائز اليوم الساعة 8 مساءً
        if now.hour == 20 and now.minute == 0:
            users = list(users_col.find({}, {"_id":1,"points":1,"withdrawable_points":1}))
            if users:
                for u in users:
                    u["total"] = u.get("points",0) + u.get("withdrawable_points",0)
                users.sort(key=lambda x: x["total"], reverse=True)
                top = users[0]
                try:
                    name = (await app.bot.get_chat(int(top["_id"]))).first_name
                except:
                    name = "مستخدم"
                for user in users_col.find():
                    try:
                        uid = int(user["_id"])
                        u = get_user(uid)
                        if u.get("banned", False): continue
                        await app.bot.send_message(uid, f"🏆 *فوز اليوم*\nالمتصدر: {name} بـ {top['total']} نقطة!", parse_mode="Markdown")
                    except:
                        pass

        # المسابقة الأسبوعية كل اثنين الساعة 12 صباحاً
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
                except:
                    pass
            users_col.update_many({}, {"$set": {"weekly_ad_count": 0, "last_contest_week": now.strftime("%Y-%W"), "weekly_mission_claimed": False}})

        # المسابقة الشهرية أول يوم في الشهر
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
                web_app_button = KeyboardButton("🏆 شاهد الإعلان لاستلام الجائزة (موبايل)", web_app=WebAppInfo(url=MONTHLY_AD_URL))
                reply_markup = ReplyKeyboardMarkup(keyboard=[[web_app_button]], resize_keyboard=True, one_time_keyboard=True)
                try:
                    await app.bot.send_message(int(top_user), f"🏆 *مسابقة الشهر*\nأعلى رصيد {top_points} نقطة. لديك 50$ في انتظارك.\n📱 *موبايل:* اضغط الزر أسفل الشاشة\n💻 *لاب:* اضغط الزر أدناه 👇", parse_mode="Markdown", reply_markup=reply_markup)
                    await app.bot.send_message(int(top_user), "💻 *للاب فقط:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏆 شاهد الإعلان لاستلام الجائزة (لاب)", web_app=WebAppInfo(url=MONTHLY_AD_URL))]]))
                except:
                    pass

        # إنهاء تحديات الأصدقاء القديمة (كل أسبوع)
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
                    web_app_button = KeyboardButton("🏆 شاهد الإعلان لاستلام جائزة التحدي (موبايل)", web_app=WebAppInfo(url=CHALLENGE_AD_URL))
                    reply_markup = ReplyKeyboardMarkup(keyboard=[[web_app_button]], resize_keyboard=True, one_time_keyboard=True)
                    try:
                        await app.bot.send_message(int(winner), f"🎉 *فزت في تحدي الأصدقاء!*\nلديك 1000 نقطة في انتظارك.\n📱 *موبايل:* اضغط الزر أسفل الشاشة\n💻 *لاب:* اضغط الزر أدناه 👇", parse_mode="Markdown", reply_markup=reply_markup)
                        await app.bot.send_message(int(winner), "💻 *للاب فقط:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏆 شاهد الإعلان لاستلام الجائزة (لاب)", web_app=WebAppInfo(url=CHALLENGE_AD_URL))]]))
                    except:
                        pass
                update_user(u["_id"], {"challenge_active": None, "challenge_points": 0, "last_challenge_reset": now.isoformat()})
                update_user(partner_id, {"challenge_active": None, "challenge_points": 0, "last_challenge_reset": now.isoformat()})

        await asyncio.sleep(60)
      

async def handle_all_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('awaiting_broadcast'):
        await admin_broadcast_send(update, context)
    elif context.user_data.get('awaiting_conversion'):
        await process_conversion(update, context)
    elif context.user_data.get('awaiting_coupon'):
        await process_coupon(update, context)
    elif context.user_data.get('awaiting_challenge'):
        await challenge_target(update, context)
    elif context.user_data.get('awaiting_withdraw_amount'):
        await withdraw_amount(update, context)
    elif context.user_data.get('awaiting_withdraw_details'):
        await withdraw_details(update, context)


import aiohttp
from collections import defaultdict

# قاموس لتتبع IP للمستخدمين
user_ip_map = defaultdict(set)  # ip -> set of user_ids
ip_blacklist = set()

async def get_ip_from_telegram(update: Update) -> str:
    """محاولة استخراج IP المستخدم من كائن update (إن وُجد)"""
    try:
        # محاولة الحصول من web_app_data (إن وجد)
        if update.message and update.message.web_app_data:
            # يمكنك إضافة منطق لاستخراج IP من هيدرز الطلب (صعب)
            pass
        # الحل البديل: استخدام خدمة خارجية لمعرفة IP البوت نفسه - لا يمكن معرفة IP المستخدم مباشرة.
        # لذلك سنعتمد على خدمة خارجية إذا قمنا بتوجيه المستخدم لزيارة رابط.
        # بدلاً من ذلك، سنستخدم آلية مبسطة: تتبع النقرات السريعة وعدد الحسابات فقط.
        return None
    except:
        return None

async def check_ad_spam(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """منع مشاهدة إعلانات متكررة بسرعة"""
    last_ad_time = context.user_data.get('last_ad_time', 0)
    now = datetime.utcnow().timestamp()
    if now - last_ad_time < 10:  # أقل من 10 ثواني
        return False
    context.user_data['last_ad_time'] = now
    return True

def check_multi_account(ip: str, user_id: int) -> bool:
    """إذا كان IP يظهر لأكثر من حد معين من الحسابات => إرجاع False (محظور)"""
    if not ip:
        return True
    user_ip_map[ip].add(user_id)
    if len(user_ip_map[ip]) > MULTI_ACCOUNT_LIMIT:
        return False
    return True




async def set_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """ربط محفظة USDT"""
    uid = update.effective_user.id
    user = get_user(uid)
    if user.get("banned", False):
        await update.message.reply_text("⛔ أنت محظور.")
        return
    try:
        address = context.args[0]
        # تحقق بسيط من شكل العنوان
        if not address.startswith('T') or len(address) != 34:
            await update.message.reply_text("❌ عنوان محفظة غير صالح (يرجى إدخال عنوان TRC20 صحيح).")
            return
        update_user(uid, {"usdt_address": address, "usdt_verified": True})
        await update.message.reply_text(f"✅ تم ربط محفظتك: `{address}`\nيمكنك الآن سحب النقاط تلقائياً.", parse_mode="Markdown")
    except:
        await update.message.reply_text("استخدم: `/setwallet <عنوان_المحفظة>`")

async def auto_withdraw(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """طلب سحب تلقائي"""
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    if user.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return
    if not user.get("usdt_address"):
        await q.message.reply_text("⚠️ يرجى ربط محفظتك أولاً باستخدام الأمر `/setwallet <عنوان TRC20>`", parse_mode="Markdown")
        return
    w = user.get("withdrawable_points", 0)
    if w < MIN_WITHDRAW_POINTS:
        need = MIN_WITHDRAW_POINTS - w
        await q.message.reply_text(f"💰 رصيدك القابل للسحب: {w}\nتحتاج {need} نقطة إضافية للحد الأدنى للسحب (120,000 نقطة = 3$).")
        return
    amt = w // POINTS_PER_DOLLAR
    deduct = amt * POINTS_PER_DOLLAR
    new_w = w - deduct
    update_user(uid, {"withdrawable_points": new_w})
    # تسجيل طلب السحب التلقائي
    withdrawal_req = {
        "user_id": uid,
        "amount_usd": amt,
        "points_deducted": deduct,
        "wallet_address": user["usdt_address"],
        "status": "auto_processed",
        "date": datetime.utcnow().isoformat()
    }
    db["auto_withdrawals"].insert_one(withdrawal_req)
    # هنا يمكنك إضافة كود الاتصال بـ API للتحويل الفعلي (مثلاً باستخدام NowPayments أو أي مزود)
    # لكن للاختبار، سنعتبرها محاكاة
    await q.message.reply_text(f"✅ تم طلب سحب تلقائي بقيمة {amt}$\nسيتم إرسال المبلغ إلى محفظتك خلال 24 ساعة.", parse_mode="Markdown")
    # إبلاغ الأدمن
    await context.bot.send_message(ADMIN_ID, f"💰 سحب تلقائي: المستخدم {uid} سحب {amt}$ إلى عنوان {user['usdt_address']}")



async def set_wallet_btn(update, context):
    q = update.callback_query
    await q.answer()
    await q.message.reply_text("أرسل الأمر: `/setwallet <عنوان محفظتك TRC20>`", parse_mode="Markdown")




async def withdraw_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_withdraw_details'):
        return
    uid = update.effective_user.id
    user = get_user(uid)
    if user.get("banned", False):
        await update.message.reply_text("⛔ أنت محظور.")
        context.user_data.pop('awaiting_withdraw_details', None)
        context.user_data.pop('withdraw_amount_usd', None)
        return

    details = update.message.text.strip()
    
    # التحقق من صحة بيانات الدفع الأساسية (اختياري)
    if "فودافون" in details.lower() or "vodafone" in details.lower():
        # يمكن إضافة تحقق لرقم الهاتف مثلاً
        if len(details) < 10:
            await update.message.reply_text("❌ يرجى إدخال رقم هاتف صالح مع طريقة الدفع.")
            return
    elif "انستا" in details.lower() or "instapay" in details.lower():
        if "@" not in details:
            await update.message.reply_text("❌ يرجى إدخال بريد إلكتروني صالح لـ InstaPay.")
            return
    elif "paypal" in details.lower():
        if "@" not in details:
            await update.message.reply_text("❌ يرجى إدخال بريد إلكتروني صالح لحساب PayPal.")
            return

    amount_usd = context.user_data.get('withdraw_amount_usd')
    if not amount_usd:
        await update.message.reply_text("❌ حدث خطأ: لم يتم تحديد المبلغ. ابدأ من جديد.")
        context.user_data.clear()
        return

    required_points = int(amount_usd * POINTS_PER_DOLLAR)
    w = user.get("withdrawable_points", 0)
    if required_points > w:
        await update.message.reply_text("❌ رصيدك لم يعد كافياً (تغير أثناء الإدخال).")
        context.user_data.pop('awaiting_withdraw_details', None)
        context.user_data.pop('withdraw_amount_usd', None)
        return

    # الخصم
    new_w = w - required_points
    update_user(uid, {"withdrawable_points": new_w})

    # حفظ الطلب
    req = {
        "user_id": uid,
        "points_deducted": required_points,
        "amount_usd": amount_usd,
        "payment_details": details,
        "status": "pending",
        "date": datetime.utcnow()
    }
    withdrawals_col.insert_one(req)
    await log_action(uid, "طلب سحب يدوي (مبلغ محدد)", uid, f"{amount_usd}$ - {details}")

    # إشعار للأدمن مع تفاصيل الطريقة
    await context.bot.send_message(
        ADMIN_ID,
        f"💰 *طلب سحب جديد*\n"
        f"👤 المستخدم: {update.effective_user.first_name} (ID: `{uid}`)\n"
        f"💵 المبلغ: {amount_usd}$\n"
        f"📝 طريقة الدفع: {details}\n"
        f"📅 الوقت: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')}",
        parse_mode="Markdown"
    )
    await update.message.reply_text(
        f"✅ تم طلب سحب {amount_usd}$ بنجاح.\n"
        f"سيتم مراجعة طلبك خلال 48 ساعة، وستصلك رسالة عند القبول أو الرفض.",
        parse_mode="Markdown"
    )
    context.user_data.pop('awaiting_withdraw_details', None)
    context.user_data.pop('withdraw_amount_usd', None)



async def withdraw_amount_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    user = get_user(uid)
    if user.get("banned", False):
        await q.answer("⛔ أنت محظور", show_alert=True)
        return

    data = q.data
    amount_usd = None
    if data == "withdraw_3":
        amount_usd = 3
    elif data == "withdraw_5":
        amount_usd = 5
    elif data == "withdraw_10":
        amount_usd = 10
    elif data == "withdraw_20":
        amount_usd = 20
    elif data == "withdraw_50":
        amount_usd = 50
    elif data == "withdraw_custom":
        await q.message.reply_text("✏️ أرسل المبلغ الذي تريد سحبه (بالدولار)، بحيث يكون أكبر من 3 وأقل من 1000:")
        context.user_data['awaiting_custom_amount'] = True
        return

    if amount_usd:
        required_points = int(amount_usd * POINTS_PER_DOLLAR)
        if user.get("withdrawable_points", 0) < required_points:
            await q.message.reply_text(f"❌ رصيدك لا يكفي لسحب {amount_usd}$. حاول اختيار مبلغ أقل.")
            return
        context.user_data['withdraw_amount_usd'] = amount_usd
        await q.message.reply_text(
            "📝 *تفاصيل الدفع*\nأرسل الآن طريقة الدفع ومعلوماتك على سطر واحد بالشكل التالي:\n\n"
            "🔹 `فودافون كاش, 01012345678`\n"
            "🔹 `انستا باي, user@example.com`\n"
            "🔹 `PayPal, your-email@example.com`\n"
            "🔹 `تحويل بنكي, IBAN: ...`",
            parse_mode="Markdown"
        )
        context.user_data['awaiting_withdraw_details'] = True




async def custom_amount_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.user_data.get('awaiting_custom_amount'):
        return
    try:
        amount_usd = float(update.message.text.strip())
        if amount_usd < 3:
            await update.message.reply_text("❌ الحد الأدنى للسحب هو 3 دولار.")
            return
        if amount_usd > 1000:
            await update.message.reply_text("❌ الحد الأقصى للسحب هو 1000 دولار في المرة الواحدة للأمان.")
            return
        required_points = int(amount_usd * POINTS_PER_DOLLAR)
        user = get_user(update.effective_user.id)
        if user.get("withdrawable_points", 0) < required_points:
            await update.message.reply_text(f"❌ رصيدك لا يكفي. لديك {user.get('withdrawable_points', 0) // POINTS_PER_DOLLAR}$ متاح.")
            return
        context.user_data['withdraw_amount_usd'] = amount_usd
        context.user_data['awaiting_custom_amount'] = False
        context.user_data['awaiting_withdraw_details'] = True
        await update.message.reply_text(
            "📝 *تفاصيل الدفع*\nأرسل الآن طريقة الدفع ومعلوماتك:",
            parse_mode="Markdown"
        )
    except ValueError:
        await update.message.reply_text("❌ يرجى إدخال رقم صحيح (مثال: 15).")




async def is_subscribed(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """التحقق من اشتراك المستخدم في القناة الإجبارية"""
    if not FORCE_SUBSCRIBE_CHANNEL:
        return True
    try:
        member = await context.bot.get_chat_member(chat_id=FORCE_SUBSCRIBE_CHANNEL, user_id=user_id)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False




async def force_subscribe_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """إرسال طلب اشتراك إجباري"""
    text = (
        f"🔒 *عذراً، يجب الاشتراك في قناتنا أولاً*\n\n"
        f"لا يمكنك استخدام البوت إلا بعد الانضمام إلى القناة:\n"
        f"➡️ `{FORCE_SUBSCRIBE_CHANNEL}`\n\n"
        f"📌 اضغط الزر أدناه للانضمام، ثم اضغط 'تحقق'."
    )
    keyboard = [
        [InlineKeyboardButton("🔗 انضمام للقناة", url="https://t.me/easy_free_1")],
        [InlineKeyboardButton("✅ تحقق من الاشتراك", callback_data="check_subscription")]
    ]
    if update.callback_query:
        await update.callback_query.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
      


async def check_subscription_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    user_id = q.from_user.id
    if await is_subscribed(user_id, context):
        await q.message.edit_text("✅ شكراً للاشتراك! يمكنك الآن استخدام البوت.", reply_markup=None)
        await main_back(update, context)  # يعيد عرض القائمة الرئيسية
    else:
        await q.answer("❌ لم تشترك بعد. يرجى الانضمام إلى القناة ثم الضغط على تحقق.", show_alert=True)





# ========== تشغيل البوت ==========
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

    main_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_platform, pattern="^(facebook|instagram|twitter|linkedin|email|ad|article|ideas)$"),
                      CallbackQueryHandler(weekly, pattern="^weekly$")],
        states={TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic)],
                TONE: [CallbackQueryHandler(get_tone, pattern="^tone_")],
                WEEKLY_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_weekly_topic)]},
        fallbacks=[CommandHandler("start", start)], per_chat=False, name="main_conv"
    )
    app.add_handler(main_conv)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("offer", admin_flash_offer))
    app.add_handler(CommandHandler("stopoffer", admin_stop_offer))
    app.add_handler(CommandHandler("createcoupon", create_coupon))
    app.add_handler(CommandHandler("addpoints", admin_add_points))
    app.add_handler(CommandHandler("removepoints", admin_remove_points))
    app.add_handler(CommandHandler("ban", admin_ban))
    app.add_handler(CommandHandler("unban", admin_unban))
    app.add_handler(CommandHandler("listbanned", admin_list_banned))
    app.add_handler(CommandHandler("userinfo", admin_user_info))
    app.add_handler(CommandHandler("start_challenge", start_global_challenge))
    app.add_handler(CommandHandler("end_challenge", end_global_challenge))
    app.add_handler(CommandHandler("cheatlogs", cheat_logs))
    app.add_handler(CommandHandler("setwallet", set_wallet))

    callbacks = [
        ("^content_menu$", content_menu), ("^earn_menu$", earn_menu), ("^account_menu$", account_menu),
        ("^main_back$", main_back), ("^help$", help_callback), ("^special_offers$", special_offers),
        ("^referral_share$", referral_share), ("^copy_link$", copy_link), ("^challenge_friend$", challenge_friend),
        ("^watch_ad$", watch_ad), ("^mystery_box$", mystery_box), ("^wheel$", wheel_of_fortune),
        ("^daily_tasks$", daily_tasks), ("^claim_bonus$", claim_bonus), ("^admin_stats$", admin_stats),
        ("^admin_users$", admin_users), ("^admin_withdrawals$", admin_withdrawals), ("^admin_export$", admin_export),
        ("^approve_", approve_withdraw), ("^reject_", reject_withdraw), ("^(home|new|admin_back)$", handle_nav),
        ("^leaderboard$", leaderboard), ("^withdraw$", withdraw_request), ("^global_challenge$", global_challenge_status),
        ("^admin_global_challenge$", admin_global_challenge_btn), ("^admin_audit_log_", admin_audit_log),
        ("^admin_churn$", admin_churn_analysis), ("^churn_remind_", churn_remind), ("^churn_gift_", churn_gift),
        ("^admin_add_points_btn$", admin_add_points_btn), ("^admin_remove_points_btn$", admin_remove_points_btn),
        ("^admin_ban_btn$", admin_ban_btn), ("^admin_unban_btn$", admin_unban_btn),
        ("^admin_list_banned_btn$", admin_list_banned_btn), ("^admin_userinfo_btn$", admin_userinfo_btn),
        ("^admin_broadcast$", admin_broadcast_start), ("^redeem_coupon$", redeem_coupon),
        ("^convert_points$", convert_points), ("^set_wallet_btn$", set_wallet_btn),
        ("^auto_withdraw$", auto_withdraw),
        ("^withdraw_(3|5|10|20|50|custom)$", withdraw_amount_callback),

    ]
    for pattern, handler in callbacks:
        app.add_handler(CallbackQueryHandler(handler, pattern=pattern))
        app.add_handler(CallbackQueryHandler(test_callback, pattern="^test_audit$"))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_all_text))
        app.add_handler(CallbackQueryHandler(admin_list_banned, pattern="^admin_list_banned_btn$"))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, custom_amount_handler))
        app.add_handler(CallbackQueryHandler(check_subscription_callback, pattern="^check_subscription$"))
        app.add_handler(CallbackQueryHandler(admin_churn_analysis, pattern="^admin_churn$"))
    loop = asyncio.get_event_loop()
    loop.create_task(scheduled_tasks(app))
    print("✅ Bot started successfully!")
    app.run_polling()


if __name__ == "__main__":
    main()

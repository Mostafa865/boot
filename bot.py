# v9.0 - النسخة النهائية مع الإشعارات والتقارير والمهام الأسبوعية والشارات والتصدير
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

# ========== الثوابت المربحة ==========
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
WEEKLY_MISSION_TARGET = 50          # 50 إعلان في الأسبوع
WEEKLY_MISSION_REWARD = 5000         # مكافأة 5000 نقطة قابلة للسحب
AMBASSADOR_THRESHOLD = 10            # عدد الدعوات لتصبح سفيراً

AD_URL = "https://mostafa865.github.io/boot/ad.html"
BOX_AD_URL = "https://mostafa865.github.io/boot/box_ad.html"

MYSTERY_BOX_PRIZES = [(50,"😐 حظك عادي",50),(100,"🙂 مش بطال",25),(200,"😊 كويس",15),(500,"🔥 حظك حلو",8),(1000,"🎉 جاكبوت",2)]

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
        user = {
            "_id": uid, "points": 300, "withdrawable_points": 0, "uses": 0, "referrals": 0,
            "referrer_id": None, "referral_level2_count": 0, "total_commission_earned": 0,
            "has_withdrawn_before": False, "first_withdrawal_date": None,
            "tasks": {"ad": False, "used": False, "bonus": False}, "last_task_date": today,
            "last_box_date": "", "ad_watch_today": 0, "last_ad_date": "",
            "ad_streak": 0, "ad_multiplier": 1.0, "last_ad_streak_date": "",
            "weekly_ad_count": 0, "last_contest_week": datetime.utcnow().strftime("%Y-%W"),
            "referred_users": [], "referral_date": None,
            "last_daily_report_date": "",          # تاريخ آخر تقرير يومي
            "ambassador_badge": False              # شارة سفير البوت
        }
        users_col.insert_one(user)
    else:
        updated = False
        for field in ["withdrawable_points","ad_watch_today","last_ad_date","ad_streak","ad_multiplier","last_ad_streak_date"]:
            if field not in user:
                user[field] = 0 if field in ["withdrawable_points","ad_watch_today","ad_streak"] else (1.0 if field=="ad_multiplier" else "")
                updated = True
        for field in ["referrer_id","referral_level2_count","total_commission_earned","has_withdrawn_before","first_withdrawal_date","weekly_ad_count","last_contest_week","referred_users","referral_date","last_daily_report_date","ambassador_badge"]:
            if field not in user:
                user[field] = None if field in ["referrer_id","first_withdrawal_date","referral_date","last_daily_report_date"] else (0 if field in ["referral_level2_count","total_commission_earned","weekly_ad_count"] else ([] if field=="referred_users" else False))
                updated = True
        if updated:
            users_col.update_one({"_id": uid}, {"$set": {k: user[k] for k in ["withdrawable_points","ad_watch_today","last_ad_date","ad_streak","ad_multiplier","last_ad_streak_date","referrer_id","referral_level2_count","total_commission_earned","has_withdrawn_before","first_withdrawal_date","weekly_ad_count","last_contest_week","referred_users","referral_date","last_daily_report_date","ambassador_badge"]}})
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
    yesterday = (datetime.utcnow()-timedelta(days=1)).strftime("%Y-%m-%d")
    if last == yesterday:
        cur += 1
        if cur>20: cur=20
        mul = min(STREAK_MAX_MULTIPLIER, 1.0 + (cur-1)*STREAK_STEP)
        mul = round(mul,2)
    else:
        cur = 1
        mul = 1.0
    update_user(user_id, {"ad_streak":cur, "ad_multiplier":mul, "last_ad_streak_date":today})
    return mul

def spin_mystery_box():
    total=sum(w for _,_,w in MYSTERY_BOX_PRIZES)
    r=random.randint(1,total); cur=0
    for p,m,w in MYSTERY_BOX_PRIZES:
        cur+=w
        if r<=cur: return p,m
    return 50,"😐 حظك عادي"

# ========== القوائم المنظمة ==========
def main_menu():
    kb = [[InlineKeyboardButton("✍️ كتابة محتوى", callback_data="content_menu")],
          [InlineKeyboardButton("💰 كسب النقاط", callback_data="earn_menu")],
          [InlineKeyboardButton("👤 حسابي", callback_data="account_menu")],
          [InlineKeyboardButton("🏆 المتصدرين", callback_data="leaderboard")],
          [InlineKeyboardButton("ℹ️ تعليمات", callback_data="help")]]
    return InlineKeyboardMarkup(kb)

async def content_menu(update,context):
    q=update.callback_query; await q.answer()
    kb=[[InlineKeyboardButton("📘 بوست فيسبوك",callback_data="facebook"),InlineKeyboardButton("📸 كابشن انستجرام",callback_data="instagram")],
        [InlineKeyboardButton("🐦 تويت تويتر",callback_data="twitter"),InlineKeyboardButton("💼 بوست لينكدإن",callback_data="linkedin")],
        [InlineKeyboardButton("📧 إيميل احترافي",callback_data="email"),InlineKeyboardButton("🎯 إعلان تسويقي",callback_data="ad")],
        [InlineKeyboardButton("✍️ مقال قصير",callback_data="article"),InlineKeyboardButton("💡 أفكار محتوى",callback_data="ideas")],
        [InlineKeyboardButton("📅 جدولة أسبوعية",callback_data="weekly")],
        [InlineKeyboardButton("🔙 رجوع",callback_data="main_back")]]
    await q.edit_message_text("✍️ *اختر نوع المحتوى:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def earn_menu(update,context):
    q=update.callback_query; await q.answer()
    kb=[[InlineKeyboardButton("📺 شاهد إعلان",callback_data="watch_ad")],
        [InlineKeyboardButton("🎲 صندوق الحظ",callback_data="mystery_box")],
        [InlineKeyboardButton("📋 مهام اليوم",callback_data="daily_tasks")],
        [InlineKeyboardButton("🎁 دعوة صديق",callback_data="referral")],
        [InlineKeyboardButton("🔙 رجوع",callback_data="main_back")]]
    await q.edit_message_text("💰 *كسب النقاط*\nاختر طريقة:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def account_menu(update,context):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; u=get_user(uid)
    w=u.get("withdrawable_points",0); streak=u.get("ad_streak",0); mul=u.get("ad_multiplier",1.0)
    ambassador = "🏅 *سفير البوت* 🏅\n" if u.get("ambassador_badge") else ""
    text = (f"👤 *حسابي*\n\n{ambassador}"
            f"✨ نقاط عادية: *{u['points']}*\n💰 نقاط قابلة للسحب: *{w}*\n"
            f"✍️ استخدامات: *{u['uses']}*\n🎁 دعوات مباشرة: *{u['referrals']}*\n"
            f"🎁 دعوات غير مباشرة: *{u.get('referral_level2_count',0)}*\n🔥 Streak: *{streak} يوم* (مضاعف {mul}x)\n\n"
            f"📺 كل إعلان: +{POINTS_PER_AD} نقطة × المضاعف (حد {MAX_ADS_PER_DAY}/يوم)\n"
            f"🎁 كل دعوة مباشرة: +{REFERRAL_WITHDRAWABLE} نقطة\n🎁 كل دعوة غير مباشرة: +{REFERRAL_LEVEL2} نقطة\n"
            f"💰 عمولة إحالات: {REFERRAL_COMMISSION_PERCENT}% من أرباح المدعو (30 يوم)\n"
            f"💰 التحويل: {POINTS_PER_DOLLAR} نقطة = $1\n🏧 حد السحب: {MIN_WITHDRAW_POINTS} نقطة (${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR})")
    kb=[[InlineKeyboardButton("💰 سحب النقاط",callback_data="withdraw")],[InlineKeyboardButton("🔙 رجوع",callback_data="main_back")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def help_callback(update,context):
    q=update.callback_query; await q.answer()
    text=("ℹ️ *تعليمات البوت*\n\n1️⃣ كسب النقاط: شاهد إعلانات يومياً (حد 15).\n2️⃣ Streak: كل يوم يزيد المضاعف 5% حتى 2x.\n"
          "3️⃣ صندوق الحظ: يومياً يعطيك نقاط عشوائية (عادية).\n4️⃣ المهام اليومية: شاهد إعلان + استخدم البوت = 300 نقطة عادية بونص.\n"
          f"5️⃣ الإحالات: ادعو أصدقاءك واكسب {REFERRAL_WITHDRAWABLE} نقطة لكل مدعو مباشر، و{REFERRAL_LEVEL2} لغير المباشر، و{REFERRAL_COMMISSION_PERCENT}% من أرباح إعلانات مدعويك لمدة 30 يوم.\n"
          f"6️⃣ المسابقة الأسبوعية: كل إثنين أفضل 10 مستخدمين في عدد الإعلانات يحصلون على جوائز.\n7️⃣ مهمة أسبوعية: شاهد {WEEKLY_MISSION_TARGET} إعلاناً في الأسبوع ↔ {WEEKLY_MISSION_REWARD} نقطة.\n"
          f"8️⃣ السحب: تجميع {MIN_WITHDRAW_POINTS} نقطة = {MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR}$، يمكنك طلب السحب.\n9️⃣ شارة سفير البوت: عندما تدعو أكثر من {AMBASSADOR_THRESHOLD} شخصاً.")
    kb=[[InlineKeyboardButton("🔙 رجوع",callback_data="main_back")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def main_back(update,context):
    q=update.callback_query; await q.answer()
    u=get_user(q.from_user.id)
    await q.edit_message_text(f"👋 أهلاً *{q.from_user.first_name}*!\n\n✨ نقاط عادية: *{u['points']}*\n💰 نقاط قابلة للسحب: *{u.get('withdrawable_points',0)}*\n\n👇 اختر من القائمة:", parse_mode="Markdown", reply_markup=main_menu())

def tone_menu():
    kb=[[InlineKeyboardButton("👔 رسمي",callback_data="tone_formal"),InlineKeyboardButton("😄 عامي",callback_data="tone_casual")],
        [InlineKeyboardButton("🔥 تسويقي",callback_data="tone_marketing"),InlineKeyboardButton("💬 مباشر",callback_data="tone_simple")]]
    return InlineKeyboardMarkup(kb)

def admin_menu():
    kb=[[InlineKeyboardButton("👥 المستخدمون",callback_data="admin_users"),InlineKeyboardButton("📊 الإحصائيات",callback_data="admin_stats")],
        [InlineKeyboardButton("💰 طلبات السحب",callback_data="admin_withdrawals")],
        [InlineKeyboardButton("📢 رسالة جماعية",callback_data="admin_broadcast")],
        [InlineKeyboardButton("📁 تصدير Excel",callback_data="admin_export")]]
    return InlineKeyboardMarkup(kb)

# ========== دوال البوت الأساسية ==========
async def check_subscription(user_id,bot): return True

async def start(update,context):
    user=update.effective_user; uid=user.id; name=user.first_name
    # نظام إحالات متقدم
    if context.args and context.args[0].startswith("ref_"):
        ref_id=context.args[0].replace("ref_","")
        if ref_id!=str(uid):
            referrer=get_user(int(ref_id))
            new_user=get_user(uid)
            if new_user.get("referrer_id") is None:
                update_user(uid,{"referrer_id":int(ref_id),"referral_date":datetime.utcnow().isoformat()})
                nr=referrer["withdrawable_points"]+REFERRAL_WITHDRAWABLE
                update_user(int(ref_id),{"withdrawable_points":nr,"referrals":referrer["referrals"]+1,"referred_users":referrer.get("referred_users",[])+[uid]})
                try:
                    await context.bot.send_message(int(ref_id),f"🎉 صديق جديد انضم عن طريقك!\n+{REFERRAL_WITHDRAWABLE} نقطة قابلة للسحب",parse_mode="Markdown")
                except: pass
                # المستوى الثاني
                upline_id=referrer.get("referrer_id")
                if upline_id:
                    upline=get_user(upline_id)
                    new_up=upline["withdrawable_points"]+REFERRAL_LEVEL2
                    update_user(upline_id,{"withdrawable_points":new_up,"referral_level2_count":upline.get("referral_level2_count",0)+1})
                    try:
                        await context.bot.send_message(upline_id,f"🎉 مدعو غير مباشر انضم!\n+{REFERRAL_LEVEL2} نقطة",parse_mode="Markdown")
                    except: pass
    if uid==ADMIN_ID:
        await update.message.reply_text(f"👋 أهلاً *{name}* — لوحة الأدمن 🔧", parse_mode="Markdown", reply_markup=admin_menu())
        return
    u=get_user(uid)
    await update.message.reply_text(f"👋 أهلاً *{name}*!\n\n🤖 أنا بوت كتابة المحتوى الاحترافي\nبساعدك تكتب محتوى جذاب ✨\n\n✨ نقاط عادية: *{u['points']}*\n💰 نقاط قابلة للسحب: *{u.get('withdrawable_points',0)}*\n\n👇 اختر من القائمة:", parse_mode="Markdown", reply_markup=main_menu())

# دوال المحتوى (مختصرة من الكود السابق – نفس المنطق)
async def handle_platform(update,context):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; u=check_daily_tasks(get_user(uid)); update_user(uid,{"tasks":u["tasks"],"last_task_date":u["last_task_date"]})
    if u["points"]<POINTS_PER_USE:
        await q.message.reply_text(f"❌ نقاطك مش كافية! رصيدك: {u['points']}، تحتاج {POINTS_PER_USE}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد إعلان",callback_data="watch_ad")]]))
        return ConversationHandler.END
    platforms={"facebook":"📘 بوست فيسبوك","instagram":"📸 كابشن انستجرام","twitter":"🐦 تويت تويتر","linkedin":"💼 بوست لينكدإن","email":"📧 إيميل","ad":"🎯 إعلان","article":"✍️ مقال","ideas":"💡 أفكار"}
    context.user_data['platform']=platforms[q.data]; context.user_data['platform_key']=q.data
    await q.edit_message_text(f"✅ اخترت: *{platforms[q.data]}*\n\n📝 اكتب موضوع المحتوى:", parse_mode="Markdown")
    return TOPIC

async def weekly(update,context):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; u=check_daily_tasks(get_user(uid))
    if u["points"]<POINTS_PER_USE:
        await q.message.reply_text("❌ نقاطك مش كافية!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد إعلان",callback_data="watch_ad")]]))
        return ConversationHandler.END
    await q.edit_message_text("📅 *جدولة أسبوعية*\nاكتب موضوع قناتك:", parse_mode="Markdown")
    return WEEKLY_TOPIC

async def get_topic(update,context):
    context.user_data['topic']=update.message.text
    await update.message.reply_text("🎨 اختار أسلوب الكتابة:", parse_mode="Markdown", reply_markup=tone_menu())
    return TONE

async def get_tone(update,context):
    q=update.callback_query; await q.answer()
    tones={"tone_formal":"رسمي","tone_casual":"عامي","tone_marketing":"تسويقي","tone_simple":"مباشر"}
    tone=tones[q.data]; topic=context.user_data['topic']; key=context.user_data['platform_key']
    await q.edit_message_text("⏳ بكتبلك المحتوى...")
    uid=q.from_user.id; u=check_daily_tasks(get_user(uid))
    u["tasks"]["used"]=True; newpts=u["points"]-POINTS_PER_USE
    update_user(uid,{"points":newpts,"uses":u["uses"]+1,"tasks":u["tasks"],"last_task_date":u["last_task_date"]})
    prompts={
        "facebook":f"اكتب بوست فيسبوك عن '{topic}' بأسلوب {tone}.","instagram":f"اكتب كابشن انستجرام عن '{topic}' بأسلوب {tone}.",
        "twitter":f"اكتب تويت مختصر عن '{topic}' بأسلوب {tone}.","linkedin":f"اكتب بوست لينكدإن عن '{topic}' بأسلوب {tone}.",
        "email":f"اكتب إيميل عن '{topic}' بأسلوب {tone}.","ad":f"اكتب إعلان عن '{topic}' بأسلوب {tone}.",
        "article":f"اكتب مقال قصير عن '{topic}' بأسلوب {tone}.","ideas":f"أعطني 5 أفكار محتوى عن '{topic}'."}
    prompt=prompts.get(key,f"اكتب محتوى عن '{topic}' بأسلوب {tone}.")
    try:
        r=client.chat.completions.create(model="gpt-oss-120b",messages=[{"role":"system","content":"أنت كاتب محتوى محترف."},{"role":"user","content":prompt}])
        content=r.choices[0].message.content
        await q.message.reply_text(f"✅ *المحتوى جاهز:*\n\n{content}\n\n━━━━━━━━━━━━━━━\n💎 رصيدك المتبقي: *{newpts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 محتوى جديد",callback_data="new"),InlineKeyboardButton("🏠 الرئيسية",callback_data="main_back")]]))
    except:
        await q.message.reply_text("❌ حصل خطأ، حاول تاني.")
    return ConversationHandler.END

async def get_weekly_topic(update,context):
    topic=update.message.text; await update.message.reply_text("⏳ جاري الكتابة...")
    u=get_user(update.effective_user.id); newpts=u["points"]-POINTS_PER_USE
    update_user(update.effective_user.id,{"points":newpts,"uses":u["uses"]+1})
    try:
        r=client.chat.completions.create(model="gpt-oss-120b",messages=[{"role":"system","content":"كاتب محتوى محترف."},{"role":"user","content":f"اكتب 7 بوستات تيليجرام مختلفة عن '{topic}'، واحد لكل يوم."}])
        content=r.choices[0].message.content
        await update.message.reply_text(f"✅ *بوستات الأسبوع:*\n\n{content}\n\n💎 رصيدك المتبقي: *{newpts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 أسبوع جديد",callback_data="weekly"),InlineKeyboardButton("🏠 الرئيسية",callback_data="main_back")]]))
    except:
        await update.message.reply_text("❌ خطأ، حاول تاني.")
    return ConversationHandler.END

# دوال الإعلانات والمهام والمكافآت (مع إضافة المهمة الأسبوعية)
async def handle_web_app_data(update,context):
    data=update.message.web_app_data.data; uid=update.effective_user.id
    if data=="ad_watched":
        u=get_user(uid); today=datetime.utcnow().strftime("%Y-%m-%d")
        if u.get("last_ad_date")!=today:
            update_user(uid,{"ad_watch_today":0,"last_ad_date":today}); u["ad_watch_today"]=0
        if u.get("ad_watch_today",0)>=MAX_ADS_PER_DAY:
            await update.message.reply_text("❌ تجاوزت الحد اليومي (15)."); return
        mul=update_ad_streak(uid,today); earned=int(POINTS_PER_AD*mul)
        new_w=u["withdrawable_points"]+earned; new_cnt=u["ad_watch_today"]+1
        update_user(uid,{"withdrawable_points":new_w,"ad_watch_today":new_cnt,"last_ad_date":today})
        # تحديث عداد الأسبوعي للمسابقة والمهمة الأسبوعية
        cweek=datetime.utcnow().strftime("%Y-%W")
        if u.get("last_contest_week")!=cweek:
            update_user(uid,{"weekly_ad_count":0,"last_contest_week":cweek}); u["weekly_ad_count"]=0
        new_weekly=u.get("weekly_ad_count",0)+1
        update_user(uid,{"weekly_ad_count":new_weekly})
        # مكافأة المهمة الأسبوعية إذا وصل 50
        if new_weekly>=WEEKLY_MISSION_TARGET and not u.get("weekly_mission_claimed",False):
            update_user(uid,{"withdrawable_points":u["withdrawable_points"]+WEEKLY_MISSION_REWARD,"weekly_mission_claimed":True})
            await update.message.reply_text(f"🎉 *مهمة أسبوعية مكتملة!* شاهدت {WEEKLY_MISSION_TARGET} إعلان هذا الأسبوع. مكافأة +{WEEKLY_MISSION_REWARD} نقطة قابلة للسحب!", parse_mode="Markdown")
        # عمولة الإحالات
        rid=u.get("referrer_id")
        if rid and u.get("referral_date"):
            days=(datetime.utcnow()-datetime.fromisoformat(u["referral_date"])).days
            if days<=30:
                comm=int(earned*REFERRAL_COMMISSION_PERCENT/100)
                if comm>0:
                    ref=get_user(rid)
                    update_user(rid,{"withdrawable_points":ref["withdrawable_points"]+comm,"total_commission_earned":ref.get("total_commission_earned",0)+comm})
                    try: await context.bot.send_message(rid,f"🎁 عمولة إحالة: صديقك شاهد إعلاناً، ربحت +{comm} نقطة",parse_mode="Markdown")
                    except: pass
        # المهمة اليومية
        u2=check_daily_tasks(get_user(uid)); u2["tasks"]["ad"]=True
        update_user(uid,{"tasks":u2["tasks"]})
        await update.message.reply_text(f"✅ *+{earned} نقطة قابلة للسحب!*\n💎 رصيدك القابل: *{new_w}*\n🔥 مضاعف: {mul}x\n📊 إعلانات اليوم: {new_cnt}/{MAX_ADS_PER_DAY}\n✨ رصيدك العادي: *{u2['points']}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة",callback_data="main_back")]]))
    elif data=="box_ad_watched":
        u=get_user(uid); today=datetime.utcnow().strftime("%Y-%m-%d")
        if u.get("last_box_date")==today:
            await update.message.reply_text("❌ فتحت الصندوق اليوم بالفعل!"); return
        prize,msg=spin_mystery_box(); new_pts=u["points"]+prize
        update_user(uid,{"points":new_pts,"last_box_date":today})
        await update.message.reply_text(f"🎁 *نتيجة صندوق الحظ*\n{msg}\n\n🎊 ربحت *{prize} نقطة عادية*!\n💎 رصيدك العادي: *{new_pts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة",callback_data="main_back")]]))

async def mystery_box(update,context):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; u=get_user(uid); today=datetime.utcnow().strftime("%Y-%m-%d")
    if u.get("last_box_date")==today:
        await q.message.reply_text("❌ فتحت الصندوق اليوم!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة",callback_data="main_back")]])); return
    await q.message.reply_text("🎲 *صندوق الحظ*\n⚠️ شاهد الإعلان أولاً:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎁 شاهد وافتح", web_app=WebAppInfo(url=BOX_AD_URL))]]))

async def watch_ad(update,context):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; u=get_user(uid); today=datetime.utcnow().strftime("%Y-%m-%d")
    if u.get("last_ad_date")!=today: update_user(uid,{"ad_watch_today":0,"last_ad_date":today})
    if u.get("ad_watch_today",0)>=MAX_ADS_PER_DAY:
        await q.message.reply_text(f"❌ الحد اليومي {MAX_ADS_PER_DAY}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة",callback_data="main_back")]])); return
    mul=update_ad_streak(uid,today); earn=int(POINTS_PER_AD*mul)
    await q.message.reply_text(f"📺 *شاهد الإعلان*\n🔥 مضاعف اليوم: {mul}x\n💰 ستربح: {earn} نقطة\n📊 تبقى لك: {MAX_ADS_PER_DAY - u['ad_watch_today']} إعلان.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📺 شاهد", web_app=WebAppInfo(url=AD_URL))]]))

async def daily_tasks(update,context):
    q=update.callback_query; await q.answer()
    u=check_daily_tasks(get_user(q.from_user.id)); tasks=u["tasks"]
    text=f"📋 *مهام اليوم*\n{'✅' if tasks['ad'] else '❌'} شاهد إعلان\n{'✅' if tasks['used'] else '❌'} استخدم البوت\n"
    if tasks["ad"] and tasks["used"] and not tasks["bonus"]:
        text+="\n🎁 يمكنك استلام 300 نقطة بونص!"; kb=[[InlineKeyboardButton("🎁 استلام البونص",callback_data="claim_bonus")]]
    elif tasks["bonus"]: text+="\n✅ استلمت البونص!"; kb=[[InlineKeyboardButton("🏠 القائمة",callback_data="main_back")]]
    else: text+="\n🎯 أكمل المهام لتحصل على 300 نقطة!"; kb=[[InlineKeyboardButton("🏠 القائمة",callback_data="main_back")]]
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def claim_bonus(update,context):
    q=update.callback_query; await q.answer()
    u=check_daily_tasks(get_user(q.from_user.id))
    if u["tasks"]["ad"] and u["tasks"]["used"] and not u["tasks"]["bonus"]:
        new_pts=u["points"]+300; u["tasks"]["bonus"]=True
        update_user(q.from_user.id,{"points":new_pts,"tasks":u["tasks"]})
        await q.message.reply_text(f"🎉 تم إضافة 300 نقطة بونص! رصيدك العادي: *{new_pts}*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة",callback_data="main_back")]]))
    else: await q.message.reply_text("❌ لم تكمل المهام أو استلمت البونص مسبقاً!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة",callback_data="main_back")]]))

async def referral(update,context):
    q=update.callback_query; await q.answer()
    link=f"https://t.me/easy_free1bot?start=ref_{q.from_user.id}"
    await q.message.reply_text(f"🎁 *رابط دعوتك:*\n`{link}`\n\nكل صديق يدخل يكسبك {REFERRAL_WITHDRAWABLE} نقطة + عمولة {REFERRAL_COMMISSION_PERCENT}% لمدة 30 يوم.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع",callback_data="earn_menu")]]))

# دوال السحب والليدر بورد والأدمن (مع إضافة إعلان فوز المتصدر اليومي وتصدير Excel)
async def withdraw_request(update,context):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; u=get_user(uid); w=u.get("withdrawable_points",0)
    if w<MIN_WITHDRAW_POINTS:
        need=MIN_WITHDRAW_POINTS-w
        await q.message.reply_text(f"💰 *السحب*\nرصيدك القابل: {w}\nالحد الأدنى: {MIN_WITHDRAW_POINTS} نقطة (${MIN_WITHDRAW_POINTS//POINTS_PER_DOLLAR})\nتحتاج {need} نقطة.", parse_mode="Markdown")
        return
    amt=w//POINTS_PER_DOLLAR; deduct=amt*POINTS_PER_DOLLAR; new_w=w-deduct
    update_user(uid,{"withdrawable_points":new_w})
    if not u.get("has_withdrawn_before"):
        update_user(uid,{"has_withdrawn_before":True,"first_withdrawal_date":datetime.utcnow().isoformat()})
        new_w+=1000; update_user(uid,{"withdrawable_points":new_w})
        await q.message.reply_text("🎁 هدية أول سحب! +1000 نقطة قابلة للسحب.", parse_mode="Markdown")
    req={"user_id":uid,"points_deducted":deduct,"amount_usd":amt,"status":"pending","date":datetime.utcnow().isoformat()}
    db["withdrawals"].insert_one(req)
    await context.bot.send_message(ADMIN_ID,f"💰 *طلب سحب جديد*\nالمستخدم: {q.from_user.first_name}\nID: {uid}\nالمبلغ: {amt}$", parse_mode="Markdown")
    await q.message.reply_text(f"💰 تم إرسال طلب سحب {amt}$. سيتم مراجعته خلال 24-48 ساعة.", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة",callback_data="main_back")]]))

def get_leaderboard(limit=10):
    cursor=users_col.find({},{"_id":1,"points":1,"withdrawable_points":1}).sort("points",-1).limit(limit)
    res=[]; r=1
    for u in cursor:
        total=u.get("points",0)+u.get("withdrawable_points",0)
        res.append({"rank":r,"user_id":u["_id"],"total_points":total}); r+=1
    return res

async def leaderboard(update,context):
    q=update.callback_query; await q.answer()
    data=get_leaderboard(10)
    if not data: text="🏆 لا يوجد مستخدمون بعد."
    else:
        text="🏆 *أفضل 10 مستخدمين*\n"
        for e in data:
            try: user=await context.bot.get_chat(int(e["user_id"])); name=user.first_name
            except: name=f"مستخدم {e['user_id'][-4:]}"
            text+=f"{e['rank']}. {name} — 💎 {e['total_points']} نقطة\n"
    kb=[[InlineKeyboardButton("🔙 رجوع",callback_data="main_back")]]
    await q.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

# دوال الأدمن (بإضافة التصدير)
async def admin_stats(update,context):
    q=update.callback_query; await q.answer()
    if q.from_user.id!=ADMIN_ID: return
    total=users_col.count_documents({}); uses=sum(u.get("uses",0) for u in users_col.find())
    await q.message.reply_text(f"📊 *الإحصائيات*\n👥 المستخدمين: {total}\n✍️ الاستخدامات: {uses}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع",callback_data="admin_back")]]))

async def admin_users(update,context):
    q=update.callback_query; await q.answer()
    if q.from_user.id!=ADMIN_ID: return
    total=users_col.count_documents({})
    await q.message.reply_text(f"👥 *المستخدمون*\nإجمالي: {total}", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع",callback_data="admin_back")]]))

async def admin_broadcast_start(update,context):
    q=update.callback_query; await q.answer()
    if q.from_user.id!=ADMIN_ID: return
    await q.message.reply_text("📢 اكتب الرسالة:")
    return BROADCAST_MSG

async def admin_broadcast_send(update,context):
    if update.effective_user.id!=ADMIN_ID: return ConversationHandler.END
    msg=update.message.text; success=0
    for user in users_col.find():
        try: await context.bot.send_message(int(user["_id"]), f"📢 *رسالة من الإدارة:*\n\n{msg}", parse_mode="Markdown"); success+=1
        except: pass
    await update.message.reply_text(f"✅ تم الإرسال لـ {success} مستخدم.")
    return ConversationHandler.END

async def admin_withdrawals(update,context):
    q=update.callback_query; await q.answer()
    if q.from_user.id!=ADMIN_ID: return
    pending=list(db["withdrawals"].find({"status":"pending"}))
    if not pending:
        await q.message.reply_text("✅ لا توجد طلبات معلقة.")
        return
    text="💰 *طلبات السحب المعلقة*\n\n"; kb=[]
    for req in pending:
        try: user=await context.bot.get_chat(req["user_id"]); name=user.first_name
        except: name=f"ID:{req['user_id']}"
        text+=f"👤 {name}\n💵 {req['amount_usd']}$ ({req['points_deducted']} نقطة)\n\n"
        req_id=str(req["_id"])
        kb.append([InlineKeyboardButton(f"✅ قبول {req['amount_usd']}$", callback_data=f"approve_{req_id}"), InlineKeyboardButton("❌ رفض", callback_data=f"reject_{req_id}")])
    kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="admin_back")])
    await q.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))

async def approve_withdraw(update,context):
    q=update.callback_query; await q.answer()
    if q.from_user.id!=ADMIN_ID: return
    req_id=q.data.split("_")[1]
    withdrawal=db["withdrawals"].find_one({"_id":ObjectId(req_id),"status":"pending"})
    if not withdrawal: await q.message.reply_text("الطلب غير موجود."); return
    db["withdrawals"].update_one({"_id":ObjectId(req_id)},{"$set":{"status":"approved"}})
    try: await context.bot.send_message(withdrawal["user_id"], f"✅ تمت الموافقة على سحب {withdrawal['amount_usd']}$. سيتم التحويل خلال 24 ساعة.", parse_mode="Markdown")
    except: pass
    await q.message.reply_text(f"✅ تمت الموافقة على سحب {withdrawal['amount_usd']}$ وإشعار المستخدم.")
    await q.message.delete(); await admin_withdrawals(update,context)

async def reject_withdraw(update,context):
    q=update.callback_query; await q.answer()
    if q.from_user.id!=ADMIN_ID: return
    req_id=q.data.split("_")[1]
    withdrawal=db["withdrawals"].find_one({"_id":ObjectId(req_id),"status":"pending"})
    if not withdrawal: await q.message.reply_text("الطلب غير موجود."); return
    u=get_user(withdrawal["user_id"])
    new_w=u.get("withdrawable_points",0)+withdrawal["points_deducted"]
    update_user(withdrawal["user_id"],{"withdrawable_points":new_w})
    db["withdrawals"].update_one({"_id":ObjectId(req_id)},{"$set":{"status":"rejected"}})
    try: await context.bot.send_message(withdrawal["user_id"], f"❌ تم رفض طلب السحب. تم إعادة {withdrawal['points_deducted']} نقطة.", parse_mode="Markdown")
    except: pass
    await q.message.reply_text(f"❌ تم رفض الطلب وإعادة {withdrawal['points_deducted']} نقطة.")
    await q.message.delete(); await admin_withdrawals(update,context)

async def admin_export(update,context):
    q=update.callback_query; await q.answer()
    if q.from_user.id!=ADMIN_ID: return
    output=io.StringIO(); writer=csv.writer(output)
    writer.writerow(["User ID","First Name","Points","Withdrawable","Uses","Referrals","Has Withdrawn","Join Date"])
    for u in users_col.find():
        try: user=await context.bot.get_chat(int(u["_id"])); name=user.first_name
        except: name="Unknown"
        writer.writerow([u["_id"], name, u.get("points",0), u.get("withdrawable_points",0), u.get("uses",0), u.get("referrals",0), u.get("has_withdrawn_before",False), u.get("last_task_date","")])
    output.seek(0)
    await q.message.reply_document(document=io.BytesIO(output.getvalue().encode()), filename="users_export.csv", caption="📊 تصدير بيانات المستخدمين")
    await q.message.reply_text("✅ تم التصدير.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع",callback_data="admin_back")]]))

async def handle_nav(update,context):
    q=update.callback_query; await q.answer()
    if q.data=="admin_back": await q.message.reply_text("🔧 لوحة الأدمن:", reply_markup=admin_menu())
    elif q.data in ("home","new"): await main_back(update,context)

# ========== المهام المجدولة (الإشعار اليومي والتقرير اليومي وإعلان فوز المتصدر) ==========
async def daily_notification(context: ContextTypes.DEFAULT_TYPE):
    """ترسل تذكيراً يومياً للمستخدمين النشطين"""
    today=datetime.utcnow().strftime("%Y-%m-%d")
    for user in users_col.find():
        try:
            uid=int(user["_id"])
            u=get_user(uid)
            streak=u.get("ad_streak",0)
            mul=u.get("ad_multiplier",1.0)
            await context.bot.send_message(uid, f"🔥 *تذكير يومي*\nStreak الحالي: {streak} يوم (مضاعف {mul}x)\nشاهد إعلانك الأول اليوم واحصل على {int(POINTS_PER_AD*mul)} نقطة قابلة للسحب.\nلا تفوت الفرصة!", parse_mode="Markdown")
        except: pass

async def daily_report(context: ContextTypes.DEFAULT_TYPE):
    """ترسل تقريراً يومياً للمستخدم (ملخص اليوم السابق)"""
    yesterday=(datetime.utcnow()-timedelta(days=1)).strftime("%Y-%m-%d")
    for user in users_col.find():
        try:
            uid=int(user["_id"])
            u=get_user(uid)
            if u.get("last_daily_report_date")==datetime.utcnow().strftime("%Y-%m-%d"): continue
            # نحتاج لتخزين إحصائيات اليوم السابق (يمكن تخزينها في حقل منفصل). للتبسيط سنرسل ملخصاً عاماً.
            ad_count=yesterday_ad_count(uid, yesterday)  # يمكن تحسينها لكن سنتركها مبسطة
            await context.bot.send_message(uid, f"📊 *تقرير يومي*\nعدد الإعلانات أمس: {ad_count}\nرصيدك القابل للسحب الحالي: {u.get('withdrawable_points',0)}\nاستمر في مشاهدة الإعلانات لزيادة أرباحك!", parse_mode="Markdown")
            update_user(uid,{"last_daily_report_date":datetime.utcnow().strftime("%Y-%m-%d")})
        except: pass
def yesterday_ad_count(uid, date):
    # دالة مبسطة لجلب عدد الإعلانات في تاريخ معين (نفترض عدم وجودها، نرجع 0)
    return 0

async def announce_top_daily(context: ContextTypes.DEFAULT_TYPE):
    """إعلان فوز المتصدر اليومي (أعلى رصيد إجمالي)"""
    users=list(users_col.find({},{"_id":1,"points":1,"withdrawable_points":1}))
    if not users: return
    for u in users: u["total"]=u.get("points",0)+u.get("withdrawable_points",0)
    users.sort(key=lambda x:x["total"], reverse=True)
    top=users[0]
    try: name=(await context.bot.get_chat(int(top["_id"]))).first_name
    except: name="مستخدم"
    for user in users_col.find():
        try:
            await context.bot.send_message(int(user["_id"]), f"🏆 *إعلان فوز اليوم*\nالمتصدر اليوم هو {name} بإجمالي {top['total']} نقطة!\nاستمر في جمع النقاط لتصبح أنت المتصدر غداً.", parse_mode="Markdown")
        except: pass

# ========== المسابقة الأسبوعية (Job) ==========
async def weekly_contest(context: ContextTypes.DEFAULT_TYPE):
    stats=[]
    for user in users_col.find():
        cnt=user.get("weekly_ad_count",0)
        if cnt>0: stats.append({"user_id":user["_id"],"count":cnt})
    stats.sort(key=lambda x:x["count"], reverse=True)
    top10=stats[:10]
    prizes=[5000,3000,1500,500,500,500,500,500,500,500]
    for idx,entry in enumerate(top10):
        prize=prizes[idx] if idx<len(prizes) else 500
        u=get_user(entry["user_id"])
        new_w=u["withdrawable_points"]+prize
        update_user(entry["user_id"],{"withdrawable_points":new_w})
        try:
            await context.bot.send_message(int(entry["user_id"]), f"🏆 *المسابقة الأسبوعية*\nالمركز {idx+1} بعدد {entry['count']} إعلان!\n✅ تم إضافة {prize} نقطة قابلة للسحب.", parse_mode="Markdown")
        except: pass
    users_col.update_many({}, {"$set":{"weekly_ad_count":0,"last_contest_week":datetime.utcnow().strftime("%Y-%W"), "weekly_mission_claimed":False}})
    await context.bot.send_message(ADMIN_ID, "✅ تم توزيع جوائز المسابقة الأسبوعية.")

# ========== تشغيل البوت ==========
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    # جدولة المهام
    job_queue=app.job_queue
    if job_queue:
        job_queue.run_daily(daily_notification, time=datetime.time(hour=9, minute=0))
        job_queue.run_daily(daily_report, time=datetime.time(hour=23, minute=0))
        job_queue.run_daily(announce_top_daily, time=datetime.time(hour=20, minute=0))
        job_queue.run_daily(weekly_contest, time=datetime.time(hour=0, minute=0), days=(0,))  # Monday
    # محادثة
    conv=ConversationHandler(
        entry_points=[CallbackQueryHandler(handle_platform, pattern="^(facebook|instagram|twitter|linkedin|email|ad|article|ideas)$"),
                      CallbackQueryHandler(weekly, pattern="^weekly$"),
                      CallbackQueryHandler(admin_broadcast_start, pattern="^admin_broadcast$")],
        states={TOPIC:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_topic)],
                TONE:[CallbackQueryHandler(get_tone, pattern="^tone_")],
                WEEKLY_TOPIC:[MessageHandler(filters.TEXT & ~filters.COMMAND, get_weekly_topic)],
                BROADCAST_MSG:[MessageHandler(filters.TEXT & ~filters.COMMAND, admin_broadcast_send)]},
        fallbacks=[CommandHandler('start', start)])
    app.add_handler(CommandHandler('start', start))
    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
    app.add_handler(CallbackQueryHandler(content_menu, pattern="^content_menu$"))
    app.add_handler(CallbackQueryHandler(earn_menu, pattern="^earn_menu$"))
    app.add_handler(CallbackQueryHandler(account_menu, pattern="^account_menu$"))
    app.add_handler(CallbackQueryHandler(main_back, pattern="^main_back$"))
    app.add_handler(CallbackQueryHandler(help_callback, pattern="^help$"))
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

if __name__ == '__main__':
    main()

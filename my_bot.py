import os
import html
import traceback
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import database

# ==========================================
# 1. إعداد المتغيرات والاتصال
# ==========================================
BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app').strip().rstrip('/')
PROOFS_CHANNEL_URL = os.environ.get('PROOFS_CHANNEL_URL', 'https://t.me/zngoxe_Proofs').strip()
OFFICIAL_CHANNEL_URL = os.environ.get('OFFICIAL_CHANNEL_URL', 'https://t.me/zngoxe').strip()

# التأكد من وجود https:// لضمان عمل WebApp بدون مشاكل
if not WEB_URL.startswith('http'):
    WEB_URL = f"https://{WEB_URL}"

if not BOT_TOKEN:
    print("❌ خطأ حرج: لم يتم العثور على BOT_TOKEN في متغيرات البيئة!")
    raise ValueError("BOT_TOKEN is required to run the bot.")

bot = telebot.TeleBot(BOT_TOKEN)

# تهيئة Firebase عند تشغيل البوت
try:
    database.initialize_firebase()
except Exception as e:
    print(f"⚠️ تنبيه Firebase أثناء تشغيل البوت: {e}")

# ==========================================
# 2. معالج أمر /start
# ==========================================
@bot.message_handler(commands=['start'])
def start_command(message):
    try:
        print(f"✅ تم استلام أمر /start من المستخدم: {message.from_user.id}")
        
        tg_id = str(message.from_user.id)
        raw_first_name = message.from_user.first_name or "صديقي"
        
        # حماية الاسم من كسر HTML في التليجرام
        first_name = html.escape(raw_first_name)
        
        # استخراج وتدقيق رابط الإحالة
        text_parts = message.text.split()
        ref_id = None
        if len(text_parts) > 1:
            raw_ref = text_parts[1].replace('ref_', '').strip()
            if raw_ref.isdigit() and raw_ref != tg_id:
                ref_id = raw_ref
                
        # ⚠️ التعامل مع قاعدة البيانات بشكل معزول لحماية أمر /start من التوقف
        try:
            # الفحص ضد الحظر في قاعدة البيانات
            if database.is_user_banned(tg_id):
                bot.send_message(
                    message.chat.id,
                    "🚫 <b>تم تقييد حسابك!</b>\n\nعذراً، لا يمكنك استخدام تطبيق ZN Goxe حالياً.",
                    parse_mode="HTML"
                )
                return
            
            # إنشاء أو تحديث المستخدم في قاعدة البيانات
            is_new = database.init_user(tg_id, ref_id=ref_id, first_name=raw_first_name)
            
            # إرسال إشعار للداعي
            if is_new and ref_id:
                try:
                    bot.send_message(
                        chat_id=int(ref_id), 
                        text=(
                            f"🎉 <b>إنجاز جديد في فريقك!</b>\n\n"
                            f"انضم صديقك <b>{first_name}</b> إلى عالم ZN Goxe عبر رابطك.\n"
                            f"🎁 ستستمتع بمكافآت نشاط جبارة و <b>10%</b> مشاركة أرباح دورية!"
                        ),
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"⚠️ تعذر إرسال الإشعار للمحيل ({ref_id}): {e}")
        except Exception as db_err:
            print(f"⚠️ خطأ في العمليات الخاصة بقاعدة البيانات (تم المتابعة لضمان الرد): {db_err}")
        
        # تجهيز رابط الـ Mini App
        web_app_url = f"{WEB_URL}?tg_id={tg_id}"
        if ref_id:
            web_app_url += f"&start_param=ref_{ref_id}"
            
        # بناء لوحة الأزرار
        markup = InlineKeyboardMarkup()
        btn_game = InlineKeyboardButton("🎮 انطلق للعب واجمع النقاط 🚀", web_app=WebAppInfo(url=web_app_url))
        btn_channel = InlineKeyboardButton("📢 القناة الرسمية", url=OFFICIAL_CHANNEL_URL)
        btn_proofs = InlineKeyboardButton("💳 قناة الإثباتات", url=PROOFS_CHANNEL_URL)
        btn_help = InlineKeyboardButton("❓ كيف تلعب؟", callback_data="how_to_play")
        
        # ترتيب الأزرار بشبكة متناسقة
        markup.row(btn_game)
        markup.row(btn_channel, btn_proofs)
        markup.row(btn_help)
        
        # رسالة الترحيب
        welcome_message = (
            f"⚡ <b>أهلاً بك يا {first_name} في عالم ZN Goxe الرقمي!</b> ⚡\n\n"
            f"استعد لخوض تجربة تفاعلية فريدة تجمع بين التسلية، التحدي، وجمع المكافآت! 🏆\n\n"
            f"✨ <b>ماذا ينتظرك داخل التطبيق؟</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🚜 <b>مزرعة ZN الرقمية:</b> طوّر أجهزتك ودع نقاطك تنمو باستمرار.\n"
            f"🎯 <b>المهام والتحديات:</b> أكمل المطبوعات اليومية واقتنص الكنوز.\n"
            f"🤝 <b>نظام التحالفات:</b> ادعُ أصدقاءك وابنِ إمبراطوريتك الخاصة.\n"
            f"⚔️ <b>المنافسات المباشرة:</b> نافس على صدارة القائمة واثبت وجودك!\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🔥 <b>محطتك الأولى تبدأ بضغطة زر واحدة.. هل أنت جاهز؟</b>"
        )
        
        bot.send_message(message.chat.id, welcome_message, reply_markup=markup, parse_mode="HTML")

    except Exception as e:
        print(f"❌ خطأ حرج في معالج start: {e}")
        traceback.print_exc()
        try:
            bot.send_message(
                message.chat.id,
                "⚠️ جاري إعادة تشغيل الخدمة، يرجى إعادة الضغط على /start بعد قليل."
            )
        except Exception:
            pass

# ==========================================
# 3. معالج زر "كيف تلعب؟" (Callback Query)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data == "how_to_play")
def how_to_play_callback(call):
    try:
        bot.answer_callback_query(call.id)
        
        help_text = (
            "📖 <b>دليل الشرح الشامل - منصة وتطبيق ZN Goxe:</b>\n\n"
            "مرحباً بك! إليك كافة التفاصيل حول آلية العمل، التجميع، والسحب المباشر داخل المنصة:\n\n"
            "⚡ <b>1️⃣ نظام التعدين التلقائي والمخزن:</b>\n"
            "• عند بدء اللعب يبدأ نظام التعدين الآلي بتجميع عملات ZN في <b>سعة التخزين المؤقت</b>.\n"
            "• اضغط على زر <b>(تجميع الرصيد)</b> لنقل النقاط إلى رصيدك الأساسي.\n"
            "• يمكنك ترقية <b>مستويات التعدين وسعة المخزن</b> لزيادة معدل الإنتاج وتوسيع سعة التجميع لتستمر في العمل لأوقات أطول تلقائياً.\n\n"
            "🎁 <b>2️⃣ المكافآت اليومية والمهام:</b>\n"
            "• احرص على تسجيل الدخول اليومي واستلام <b>المكافأة اليومية (30 يوم)</b> المتصاعدة.\n"
            "• تصفح قسم <b>المهام والزيارات</b> لإكمال المهام البسيطة وإدخال أكواد الهدايا (Promo Codes).\n\n"
            "🎮 <b>3️⃣ الألعاب التفاعلية والتحديات:</b>\n"
            "• يتضمن التطبيق ألعاباً مثل <b>Fogo Sweep</b> و <b>برج النيون Goxe</b> للمنافسة ومضاعفة رصيدك بناءً على المهارة والتحدي.\n\n"
            "🤝 <b>4️⃣ نظام دعوة الأصدقاء (الفريق):</b>\n"
            "• احصل على <b>10% مشاركة أرباح</b> من كافة الأنشطة التعدينية لأصدقائك المنضمين عبر رابطك.\n"
            "• فتح جوائز وإنجازات خاصة عند الوصول إلى مستويات دعوة متقدمة.\n\n"
            "💳 <b>5️⃣ عمليات السحب وإثباتات الدفع:</b>\n"
            "• يدعم التطبيق السحب السريع والمباشر عبر منصات السحب المعتمدة مثل <b>FaucetPay</b> والعملات المدعومة (DOGE, TRX, PEPE, LTC) بالإضافة لشبكة TON.\n"
            "• يمكنك الاطلاع على كافة عمليات التحويل والمصداقية الحية من خلال <b>قناة الإثباتات الرسمية</b>.\n\n"
            "⚠️ <b>تنبيه عام:</b> يُمنع استخدام الحسابات المتعددة أو أدوات التلاعب للحفاظ على سلامة الحساب والتمتع بكافة الميزات دون انقطاع."
        )
        
        markup = InlineKeyboardMarkup()
        btn_proofs = InlineKeyboardButton("💳 قناة إثباتات السحب الحية", url=PROOFS_CHANNEL_URL)
        markup.row(btn_proofs)
        
        bot.send_message(call.message.chat.id, help_text, reply_markup=markup, parse_mode="HTML")
    except Exception as e:
        print(f"❌ خطأ في callback: {e}")
        traceback.print_exc()

# ==========================================
# 4. معالج كافة الرسائل العادية (Fallback)
# ==========================================
@bot.message_handler(func=lambda message: True)
def default_message_handler(message):
    try:
        tg_id = str(message.from_user.id)
        web_app_url = f"{WEB_URL}?tg_id={tg_id}"
        
        markup = InlineKeyboardMarkup()
        btn_game = InlineKeyboardButton("🎮 فتح تطبيق ZN Goxe", web_app=WebAppInfo(url=web_app_url))
        markup.row(btn_game)
        
        bot.send_message(
            message.chat.id,
            "💡 <b>اضغط على الزر بالأسفل لفتح التطبيق ومتابعة لعبتك!</b>",
            reply_markup=markup,
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"❌ خطأ في المعالج العام: {e}")
        traceback.print_exc()

# ==========================================
# 5. تشغيل البوت والحماية من السقوط
# ==========================================
if __name__ == '__main__':
    # 🎯 الخطوة الحاسمة: مسح أي Webhook قديم وتصفية الرسائل المعلقة لإجبار التليجرام على الاستجابة
    try:
        bot.remove_webhook(drop_pending_updates=True)
        print("✅ تم حذف Webhook القديم وتنظيف الأوامر المعلقة بنجاح.")
    except Exception as e:
        print(f"⚠️ تنبيه أثناء إزالة الـ Webhook: {e}")
        
    print("🤖 ZN Goxe Bot is online and running safely via Long Polling...")
    bot.infinity_polling(timeout=20, long_polling_timeout=10, skip_pending=True)

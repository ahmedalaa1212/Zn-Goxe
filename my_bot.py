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
        # رسالة في الكونسول عشان تتأكد إن البوت استقبل الأمر وميهنجش في صمت
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
            
            # إنشاء أو تحديث المستخدم في قاعدة البيانات بأسماء الحقول الصريحة
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
        btn_channel = InlineKeyboardButton("📢 القناة الرسمية والتحديثات", url="https://t.me/zngoxe")
        btn_help = InlineKeyboardButton("❓ كيف تلعب؟", callback_data="how_to_play")
        
        markup.row(btn_game)
        markup.row(btn_channel, btn_help)
        
        # رسالة الترحيب المشوقة والأنيقة
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
        traceback.print_exc() # طباعة الخطأ بالكامل في الكونسول لتسهيل حله
        # إرسال رد طوارئ للمستخدم حتى لا يظل البوت صامتاً
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
        # إعطاء استجابة فورية لتليجرام لإلغاء مؤشر التحميل على الزر
        bot.answer_callback_query(call.id)
        
        help_text = (
            "📖 <b>دليل البدء السريع - ZN Goxe:</b>\n\n"
            "1️⃣ اضغط على زر <b>(انطلق للعب)</b> لفتح التطبيق.\n"
            "2️⃣ قم بتفعيل <b>المزرعة</b> وترقية المكونات لزيادة سرعة الإنتاج.\n"
            "3️⃣ انجز <b>المهام اليومية</b> للحصول على مكافآت فورية.\n"
            "4️⃣ شارك رابطك مع أصدقائك لتحصل على <b>10%</b> بونص إضافي دائماً!\n\n"
            "💡 <i>كلما زاد نشاطك داخل التطبيق، زادت رتبتك وجوائزك!</i>"
        )
        bot.send_message(call.message.chat.id, help_text, parse_mode="HTML")
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
    try:
        bot.remove_webhook()
    except Exception:
        pass
        
    print("🤖 ZN Goxe Bot is online and running safely...")
    # إضافة skip_pending=True لتجاهل الأوامر المتراكمة اللي بتخلي البوت يعلق
    bot.infinity_polling(timeout=20, long_polling_timeout=10, skip_pending=True)

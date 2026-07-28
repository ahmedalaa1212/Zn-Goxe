import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import database

BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app')

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start_command(message):
    tg_id = str(message.from_user.id)
    first_name = message.from_user.first_name or "صديقي"
    
    if database.is_user_banned(tg_id):
        bot.send_message(
            message.chat.id,
            "🚫 <b>تم تقييد حسابك!</b>\n\nعذراً، لا يمكنك استخدام التطبيق حالياً.",
            parse_mode="HTML"
        )
        return
    
    text_parts = message.text.split()
    ref_id = None
    if len(text_parts) > 1:
        ref_id = text_parts[1].replace('ref_', '').strip()
        
    # التحقق وتحديث/إنشاء المستخدم من خلال database.py لتوحيد العمليات
    is_new = database.init_user(tg_id, ref_id, first_name)
    
    # إرسال إشعار للداعي إذا كان اللاعب جديداً وجاء عبر رابط إحالة
    if is_new and ref_id and str(ref_id) != str(tg_id):
        try:
            bot.send_message(
                chat_id=int(ref_id), 
                text=f"🎉 <b>خبر مفرح!</b>\n\nلقد انضم صديقك <b>[{first_name}]</b> إلى اللعبة عبر رابطك.\nستحصل الآن على <b>10%</b> من أرباح تعدينه بشكل دائم! 💸",
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Could not send message to referrer: {e}")
    
    markup = InlineKeyboardMarkup()
    clean_web_url = WEB_URL.lower().strip()
    
    web_app_url = f"{clean_web_url}?tg_id={tg_id}"
    if ref_id:
        web_app_url += f"&start_param=ref_{ref_id}"
        
    btn_game = InlineKeyboardButton("🚀 العب الآن واجمع ثروتك", web_app=WebAppInfo(url=web_app_url))
    btn_channel = InlineKeyboardButton("📢 انضم لمجتمعنا", url="https://t.me/zngoxe")
    
    markup.row(btn_game)
    markup.row(btn_channel)
    
    # رسالة الترحيب الاحترافية والمحفزة
    welcome_message = (
        f"🌟 <b>مرحباً بك يا {first_name} في إمبراطورية Zn Goxe!</b> 🌟\n\n"
        f"هل أنت مستعد لتغيير قواعد اللعبة؟ 🚀 هنا، وقتك يُترجم إلى ثروة رقمية حقيقية.\n\n"
        f"💎 <b>ما يجعلك مميزاً هنا:</b>\n"
        f"⛏️ <b>تعدين لا يتوقف:</b> طور مزرعتك ودع الأرباح تتدفق إليك حتى وأنت نائم.\n"
        f"🤝 <b>شبكة الثروة:</b> ادعُ أصدقاءك، وابنِ فريقك، واحصل على <b>10%</b> من أرباحهم دائماً!\n"
        f"⚔️ <b>منافسات ملحمية:</b> ادخل الساحة، اهزم خصومك، واقتنص الجوائز الكبرى.\n\n"
        f"⚡ <b>لا تضيع الوقت، جهاز التعدين الخاص بك بانتظار إشارة البدء!</b>\n"
        f"👇 <b>اضغط على الزر بالأسفل وانطلق نحو القمة الآن!</b>"
    )
    
    bot.send_message(message.chat.id, welcome_message, reply_markup=markup, parse_mode="HTML")

if __name__ == '__main__':
    database.initialize_firebase()
    bot.remove_webhook()
    print("🤖 Bot is running smoothly...")
    bot.infinity_polling(allowed_updates=telebot.util.update_types)

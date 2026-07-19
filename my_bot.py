import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import database

BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEB_URL = os.environ.get('WEB_URL', 'https://zn-goxe-production.up.railway.app')

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start_command(message):
    tg_id = message.from_user.id
    first_name = message.from_user.first_name or "صديقي"
    
    # لقط كود الإحالة من التليجرام
    text_parts = message.text.split()
    ref_id = None
    if len(text_parts) > 1:
        ref_id = text_parts[1].replace('ref_', '').strip()
        
    # تسجيل الحساب في الداتابيز
    is_new_referral = database.init_user(str(tg_id), ref_id, first_name)
    
    # إرسال إشعار لصاحب الرابط
    if is_new_referral and ref_id:
        try:
            bot.send_message(
                chat_id=ref_id,
                text=f"🎉 **خبر مفرح!**\n\nلقد انضم صديقك [{first_name}] إلى اللعبة عن طريق رابط الإحالة الخاص بك.\nستحصل الآن على 10% من أرباح تعدينه للأبد! 💸",
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Could not send message to referrer: {e}")
    
    markup = InlineKeyboardMarkup()
    clean_web_url = WEB_URL.lower().strip()
    
    # تمرير البيانات للويب آب
    web_app_url = f"{clean_web_url}?tg_id={tg_id}"
    if ref_id:
        web_app_url += f"&start_param=ref_{ref_id}"
        
    btn_game = InlineKeyboardButton("🎮 دخول اللعبة وابدأ التجميع الآن", web_app=WebAppInfo(url=web_app_url))
    btn_channel = InlineKeyboardButton("📢 تابع قناة اللعبة الرسمية", url="https://t.me/zngoxe")
    markup.add(btn_game)
    markup.add(btn_channel)
    
    motivational_text = (
        f"🔥 أهلاً بك يا {first_name} في عالم الـ Zn Goxe المثير! 🔥\n\n"
        f"🚀 فرصة ذهبية مستنياك لتجميع العملات وتطوير إمبراطوريتك الرقمية من الصفر! "
        f"جهاز التعدين الخاص بك يعمل الآن في السحاب ويجمع لك الأرباح ثانية بثانية حتى وأنت مغلق للتطبيق!\n\n"
        f"👇 اضغط على الأزرار بالأسفل وانطلق فوراً!"
    )
    bot.send_message(message.chat.id, motivational_text, reply_markup=markup)

if __name__ == '__main__':
    database.initialize_firebase()
    bot.remove_webhook()
    print("🤖 Bot is running smoothly...")
    bot.infinity_polling(allowed_updates=telebot.util.update_types)

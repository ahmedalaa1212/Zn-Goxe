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
    
    # 🚨 فحص حالة الحظر قبل أي إجراء
    if database.is_user_banned(tg_id):
        bot.send_message(
            message.chat.id,
            "🚫 <b>تم تقييد حسابك!</b>\n\n"
            "عذراً، لا يمكنك استخدام التطبيق حالياً لمخالفة شروط الاستخدام.\n"
            "إذا كنت تعتقد أن هذا الإجراء تم بالخطأ، يرجى التواصل مع فريق الدعم.",
            parse_mode="HTML"
        )
        return
    
    text_parts = message.text.split()
    ref_id = None
    if len(text_parts) > 1:
        ref_id = text_parts[1].replace('ref_', '').strip()
        
    is_new_referral = database.init_user(str(tg_id), ref_id, first_name)
    
    if is_new_referral and ref_id:
        try:
            bot.send_message(
                chat_id=int(ref_id), 
                text=f"🎉 <b>خبر مفرح!</b>\n\nلقد انضم صديقك <b>[{first_name}]</b> إلى اللعبة عن طريق رابط الإحالة الخاص بك.\nستحصل الآن على 10% من أرباحه للأبد! 💸",
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Could not send message to referrer: {e}")
    
    markup = InlineKeyboardMarkup()
    clean_web_url = WEB_URL.lower().strip()
    
    web_app_url = f"{clean_web_url}?tg_id={tg_id}"
    if ref_id:
        web_app_url += f"&start_param=ref_{ref_id}"
        
    # أزرار احترافية وجذابة
    btn_game = InlineKeyboardButton("🎮 ابدأ اللعب واجمع الرصيد", web_app=WebAppInfo(url=web_app_url))
    btn_channel = InlineKeyboardButton("📢 مجتمع اللعبة (الأخبار والتحديثات)", url="https://t.me/zngoxe")
    
    # إضافة الأزرار فوق بعضها لشكل أفضل على الموبايل
    markup.row(btn_game)
    markup.row(btn_channel)
    
    # رسالة ترحيبية احترافية، آمنة، ومحفزة جداً
    welcome_message = (
        f"👋 <b>أهلاً بك يا {first_name} في عالم Zn Goxe!</b>\n\n"
        f"🚀 <b>استعد لبناء إمبراطوريتك الرقمية من الصفر!</b>\n"
        f"هنا، كل ثانية تمر تعمل لصالحك. جهاز التعدين الخاص بك جاهز للانطلاق لجمع عملات الـ <b>ZN</b> حتى وأنت بعيد عن هاتفك.\n\n"
        f"🔥 <b>ماذا ينتظرك بالداخل؟</b>\n"
        f"⛏️ <b>التعدين الذكي:</b> قم بترقية معداتك لزيادة دخلك التلقائي.\n"
        f"⚔️ <b>الساحة الكبرى:</b> نافس لاعبين آخرين واربح جوائز ضخمة كل 15 دقيقة.\n"
        f"🤝 <b>نظام الإحالة:</b> ادعُ أصدقاءك واستفد من 10% من أرباحهم للأبد!\n\n"
        f"👇 <b>اضغط على الزر بالأسفل وانطلق الآن!</b>"
    )
    
    bot.send_message(message.chat.id, welcome_message, reply_markup=markup, parse_mode="HTML")

if __name__ == '__main__':
    database.initialize_firebase()
    bot.remove_webhook()
    print("🤖 Bot is running smoothly...")
    bot.infinity_polling(allowed_updates=telebot.util.update_types)

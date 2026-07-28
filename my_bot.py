import os
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
import database
from google.cloud import firestore

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
        
    # التحقق المباشر من قاعدة البيانات لضمان دقة الدعوات
    user_ref = database.db.collection('users').document(tg_id)
    user_doc = user_ref.get()
    
    is_new_user = not user_doc.exists
    
    if is_new_user:
        # إنشاء المستخدم الجديد وربطه بالشخص الذي دعاه
        new_data = {
            'first_name': first_name,
            'balance': 0,
            'referred_by': ref_id if ref_id and ref_id != tg_id else None,
            'invited_friends_count': 0,
            'pending_ref_earnings': 0,
            'claimed_ref_tasks': [],
            'upgrades_count': 0,
            'ref_generated_amount': 0
        }
        user_ref.set(new_data)
        
        # إذا كان هناك شخص قام بدعوته، نقوم بزيادة العداد الخاص به
        if ref_id and ref_id != tg_id:
            referrer_ref = database.db.collection('users').document(ref_id)
            if referrer_ref.get().exists:
                # زيادة عداد الأصدقاء بواحد
                referrer_ref.update({
                    'invited_friends_count': firestore.Increment(1)
                })
                try:
                    bot.send_message(
                        chat_id=int(ref_id), 
                        text=f"🎉 <b>خبر مفرح!</b>\n\nلقد انضم صديقك <b>[{first_name}]</b> إلى اللعبة عن طريق رابط الإحالة الخاص بك.\nستحصل الآن على 10% من أرباحه للأبد! 💸",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"Could not send message to referrer: {e}")
    else:
        # إذا كان مستخدم قديم، نقوم بتحديث اسمه فقط (حفاظاً على باقي بياناته عبر database.py)
        database.init_user(tg_id, None, first_name)
    
    markup = InlineKeyboardMarkup()
    clean_web_url = WEB_URL.lower().strip()
    
    web_app_url = f"{clean_web_url}?tg_id={tg_id}"
    if ref_id:
        web_app_url += f"&start_param=ref_{ref_id}"
        
    btn_game = InlineKeyboardButton("🎮 ابدأ اللعب واجمع الرصيد", web_app=WebAppInfo(url=web_app_url))
    btn_channel = InlineKeyboardButton("📢 مجتمع اللعبة", url="https://t.me/zngoxe")
    
    markup.row(btn_game)
    markup.row(btn_channel)
    
    welcome_message = (
        f"👋 <b>أهلاً بك يا {first_name} في عالم Zn Goxe!</b>\n\n"
        f"🚀 <b>استعد لبناء إمبراطوريتك الرقمية من الصفر!</b>\n"
        f"هنا، كل ثانية تمر تعمل لصالحك. جهاز التعدين الخاص بك جاهز للانطلاق.\n\n"
        f"🔥 <b>ماذا ينتظرك بالداخل؟</b>\n"
        f"⛏️ <b>التعدين الذكي:</b> قم بترقية معداتك لزيادة دخلك التلقائي.\n"
        f"⚔️ <b>الساحة الكبرى:</b> نافس لاعبين آخرين واربح جوائز ضخمة.\n"
        f"🤝 <b>نظام الإحالة:</b> ادعُ أصدقاءك واستفد من أرباحهم للأبد!\n\n"
        f"👇 <b>اضغط على الزر بالأسفل وانطلق الآن!</b>"
    )
    
    bot.send_message(message.chat.id, welcome_message, reply_markup=markup, parse_mode="HTML")

if __name__ == '__main__':
    database.initialize_firebase()
    bot.remove_webhook()
    print("🤖 Bot is running smoothly...")
    bot.infinity_polling(allowed_updates=telebot.util.update_types)

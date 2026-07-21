import os
import json
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# 1. إعداد المتغيرات (Tokens & Keys)
# ==========================================
BOT_TOKEN = os.environ.get("BOT_TOKEN")
FIREBASE_JSON = os.environ.get("FIREBASE_SERVICE_ACCOUNT")

# ⚠️ هام جداً: ضع الـ Telegram ID الخاص بك هنا
# يمكنك معرفته من خلال التحدث مع البوت @userinfobot
ADMIN_ID = "اكتب_الاي_دي_بتاعك_هنا" 

bot = telebot.TeleBot(BOT_TOKEN)

# ==========================================
# 2. الاتصال بقاعدة بيانات Firebase
# ==========================================
if not firebase_admin._apps:
    try:
        cert_dict = json.loads(FIREBASE_JSON)
        cred = credentials.Certificate(cert_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ تم الاتصال بقاعدة البيانات بنجاح!")
    except Exception as e:
        print(f"❌ خطأ في الاتصال بـ Firebase: {e}")

# ==========================================
# 3. حماية البوت (للأدمن فقط)
# ==========================================
def is_admin(message):
    if str(message.from_user.id) != str(ADMIN_ID):
        bot.reply_to(message, "⛔ عذراً، هذا البوت مخصص للأدمن فقط.")
        return False
    return True

# ==========================================
# 4. قائمة الأدمن الرئيسية (أوامر البوت)
# ==========================================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    if not is_admin(message): return

    # إنشاء الأزرار الشفافة
    markup = InlineKeyboardMarkup(row_width=2)
    btn_search = InlineKeyboardButton("🔍 استعلام عن لاعب", callback_data="search_user")
    btn_add_balance = InlineKeyboardButton("💰 تعديل رصيد ZN", callback_data="edit_zn")
    btn_tasks = InlineKeyboardButton("📋 إدارة المهام", callback_data="manage_tasks")
    btn_shop = InlineKeyboardButton("🛒 إدارة المتجر", callback_data="manage_shop")
    
    markup.add(btn_search, btn_add_balance)
    markup.add(btn_tasks, btn_shop)

    bot.send_message(
        message.chat.id,
        "👑 **أهلاً بك في لوحة تحكم الأدمن!**\n\nاختر من القائمة أدناه ما تريد إدارته في اللعبة:",
        reply_markup=markup,
        parse_mode="Markdown"
    )

# ==========================================
# 5. التفاعل مع الأزرار (Callbacks)
# ==========================================
@bot.callback_query_handler(func=lambda call: True)
def handle_query(call):
    chat_id = call.message.chat.id
    
    if call.data == "search_user":
        msg = bot.send_message(chat_id, "يرجى إرسال الـ Telegram ID الخاص باللاعب:")
        bot.register_next_step_handler(msg, get_user_info)
        
    elif call.data == "edit_zn":
        msg = bot.send_message(chat_id, "يرجى إرسال الـ Telegram ID الخاص باللاعب لتعديل رصيده:")
        bot.register_next_step_handler(msg, ask_for_balance_amount)
        
    elif call.data in ["manage_tasks", "manage_shop"]:
        bot.answer_callback_query(call.id, "🛠️ جاري برمجة هذا القسم وسيكون متاحاً قريباً!", show_alert=True)

# --- دوال مساعدة لجلب وتعديل البيانات ---

def get_user_info(message):
    user_id = message.text.strip()
    try:
        doc_ref = db.collection('users').document(user_id)
        doc = doc_ref.get()
        if doc.exists():
            data = doc.to_dict()
            name = data.get('user_name', 'غير معروف')
            balance = data.get('balance', 0)
            usd = data.get('usd_balance', 0)
            
            text = f"👤 **بيانات اللاعب:**\n\n"
            text += f"🔹 الاسم: {name}\n"
            text += f"🔹 رصيد ZN: {balance}\n"
            text += f"🔹 رصيد الدولار: {usd}$"
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
        else:
            bot.send_message(message.chat.id, "❌ لم يتم العثور على لاعب بهذا الـ ID.")
    except Exception as e:
        bot.send_message(message.chat.id, "⚠️ حدث خطأ أثناء الاتصال بقاعدة البيانات.")

def ask_for_balance_amount(message):
    user_id = message.text.strip()
    msg = bot.send_message(message.chat.id, "اكتب القيمة المراد إضافتها (أو اكتب قيمة بالسالب للخصم):")
    bot.register_next_step_handler(msg, update_user_balance, user_id)

def update_user_balance(message, user_id):
    try:
        amount = float(message.text.strip())
        doc_ref = db.collection('users').document(user_id)
        doc = doc_ref.get()
        
        if doc.exists():
            current_balance = doc.to_dict().get('balance', 0)
            new_balance = current_balance + amount
            doc_ref.update({'balance': new_balance})
            bot.send_message(message.chat.id, f"✅ تم تحديث الرصيد بنجاح!\nالرصيد الجديد: {new_balance} ZN")
        else:
            bot.send_message(message.chat.id, "❌ لم يتم العثور على لاعب بهذا الـ ID.")
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ الرجاء إدخال أرقام فقط!")
    except Exception as e:
        bot.send_message(message.chat.id, "⚠️ حدث خطأ أثناء التحديث.")

# ==========================================
# 6. تشغيل البوت
# ==========================================
if __name__ == "__main__":
    print("🤖 بوت الأدمن قيد التشغيل الآن...")
    bot.infinity_polling()

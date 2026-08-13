import database
from firebase_admin import firestore

def get_firestore_db():
    return database.get_db()

def init_goxe_db():
    """
    تهيئة مستند إعدادات لعبة Goxe وإحصائيات الاقتصاد في Firebase Firestore عند أول تشغيل.
    """
    try:
        db = get_firestore_db()
        config_ref = db.collection('game_settings').document('goxe_config')
        doc = config_ref.get()
        
        if not doc.exists:
            # إنشاء البيانات الأولية مع رصيد واقي لبدء حساب نسبة الربح بـ 60%
            config_ref.set({
                'min_bet': 10.0,
                'max_bet': 10000.0,
                'target_bot_profit_pct': 60.0,
                'force_loss_threshold': 59.0,
                'total_wagered': 1000.0,
                'total_payout': 400.0,
                'force_loss_override': False,
                'game_name': 'Goxe - Neon Tower'
            })
            print("✅ تم إنشاء مستند إعدادات لعبة Goxe في Firebase بنجاح.")
        else:
            print("ℹ️ مستند إعدادات Goxe موجود بالفعل في Firebase.")
    except Exception as e:
        print(f"❌ خطأ أثناء تهيئة goxe_db في Firebase: {e}")

def get_goxe_config():
    """جلب إعدادات اللعبة من Firebase"""
    try:
        db = get_firestore_db()
        doc = db.collection('game_settings').document('goxe_config').get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        print(f"❌ خطأ في جلب إعدادات Goxe: {e}")
    
    # قيم افتراضية طارئة في حالة حدوث خلل في الاتصال
    return {
        'min_bet': 10.0,
        'max_bet': 10000.0,
        'target_bot_profit_pct': 60.0,
        'force_loss_threshold': 59.0,
        'total_wagered': 1000.0,
        'total_payout': 400.0,
        'force_loss_override': False
    }

def get_bot_profit_percentage():
    """حساب نسبة ربح البوت الحالية بدقة"""
    config = get_goxe_config()
    wagered = float(config.get('total_wagered', 1000.0))
    payout = float(config.get('total_payout', 400.0))
    
    if wagered <= 0:
        return 100.0
    
    profit = wagered - payout
    profit_pct = (profit / wagered) * 100.0
    return profit_pct

def update_goxe_economy_stats(wager_amount, payout_amount):
    """تحديث إجمالي الرهانات والمدفوعات في Firebase لتعديل نسبة الاقتصاد"""
    try:
        db = get_firestore_db()
        config_ref = db.collection('game_settings').document('goxe_config')
        config_ref.update({
            'total_wagered': firestore.Increment(float(wager_amount)),
            'total_payout': firestore.Increment(float(payout_amount))
        })
    except Exception as e:
        print(f"❌ خطأ أثناء تحديث اقتصاد Goxe: {e}")

def get_active_goxe_session(user_id):
    """جلب الجولة النشطة للاعب إن وجدت"""
    try:
        db = get_firestore_db()
        doc = db.collection('goxe_sessions').document(str(user_id)).get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        print(f"❌ خطأ في جلب جلسة اللعب للخدمة {user_id}: {e}")
    return None

def save_goxe_session(user_id, session_data):
    """حفظ جلسة اللعب النشطة في Firebase"""
    try:
        db = get_firestore_db()
        db.collection('goxe_sessions').document(str(user_id)).set(session_data)
    except Exception as e:
        print(f"❌ خطأ في حفظ جلسة Goxe: {e}")

def delete_goxe_session(user_id):
    """حذف جلسة اللعب بعد الخسارة أو الانسحاب"""
    try:
        db = get_firestore_db()
        db.collection('goxe_sessions').document(str(user_id)).delete()
    except Exception as e:
        print(f"❌ خطأ في حذف جلسة Goxe: {e}")

# تشغيل التهيئة التلقائية عند استيراد الملف
init_goxe_db()

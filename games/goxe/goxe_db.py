import time
import database
from firebase_admin import firestore

# ذاكرة مؤقتة فائقة السرعة لتوفير قراءات Firebase (تتحدث كل 15 ثانية)
_CONFIG_CACHE = None
_LAST_CACHE_TIME = 0
CACHE_TTL = 15  # ثوانٍ

def get_firestore_db():
    return database.get_db()

def init_goxe_db():
    """تهيئة مستند إعدادات goxe_config في Firebase عند أول تشغيل"""
    try:
        db = get_firestore_db()
        config_ref = db.collection('game_settings').document('goxe_config')
        doc = config_ref.get()
        
        if not doc.exists:
            config_ref.set({
                'game_name': 'Goxe - Neon Tower',
                'min_bet': 10.0,
                'max_bet': 10000.0,
                'target_bot_profit_pct': 60.0,      # نسبة ربح البوت (60%)
                'target_player_profit_pct': 40.0,   # نسبة أرباح المستخدمين (40%)
                'force_loss_threshold': 59.0,        # عتبة التدخل عند نزول ربح البوت عن 59%
                'total_wagered': 1000.0,
                'total_payout': 400.0,
                'force_loss_override': False,
                'allowed_bet_options': [10, 50, 100, 200, 500, 1000, 8000]
            })
            print("✅ تم إنشاء مستند goxe_config بنجاح.")
    except Exception as e:
        print(f"❌ خطأ أثناء تهيئة goxe_db: {e}")

def get_goxe_config(force_refresh=False):
    """جلب الإعدادات مع نظام Cache ممتاز لتوفير استهلاك Firebase"""
    global _CONFIG_CACHE, _LAST_CACHE_TIME
    current_time = time.time()

    if not force_refresh and _CONFIG_CACHE and (current_time - _LAST_CACHE_TIME < CACHE_TTL):
        return _CONFIG_CACHE

    try:
        db = get_firestore_db()
        doc = db.collection('game_settings').document('goxe_config').get()
        if doc.exists:
            _CONFIG_CACHE = doc.to_dict()
            _LAST_CACHE_TIME = current_time
            return _CONFIG_CACHE
    except Exception as e:
        print(f"❌ خطأ في جلب إعدادات Goxe: {e}")
    
    default_cfg = {
        'game_name': 'Goxe - Neon Tower',
        'min_bet': 10.0,
        'max_bet': 10000.0,
        'target_bot_profit_pct': 60.0,
        'force_loss_threshold': 59.0,
        'total_wagered': 1000.0,
        'total_payout': 400.0,
        'force_loss_override': False,
        'allowed_bet_options': [10, 50, 100, 200, 500, 1000, 8000]
    }
    return default_cfg

def get_bot_profit_percentage():
    """حساب نسبة ربح البوت الحالية بناءً على الإجمالي"""
    config = get_goxe_config()
    wagered = float(config.get('total_wagered', 1000.0))
    payout = float(config.get('total_payout', 400.0))
    
    if wagered <= 0:
        return 100.0
    
    profit = wagered - payout
    profit_pct = (profit / wagered) * 100.0
    return profit_pct

def update_goxe_economy_stats(wager_amount, payout_amount):
    """تحديث إحصائيات الرهان بأسلوب أتمتة (Increment) لتوفير القراءات"""
    global _CONFIG_CACHE
    try:
        db = get_firestore_db()
        config_ref = db.collection('game_settings').document('goxe_config')
        config_ref.update({
            'total_wagered': firestore.Increment(float(wager_amount)),
            'total_payout': firestore.Increment(float(payout_amount))
        })
        if _CONFIG_CACHE:
            _CONFIG_CACHE['total_wagered'] = float(_CONFIG_CACHE.get('total_wagered', 0)) + float(wager_amount)
            _CONFIG_CACHE['total_payout'] = float(_CONFIG_CACHE.get('total_payout', 0)) + float(payout_amount)
    except Exception as e:
        print(f"❌ خطأ أثناء تحديث اقتصاد Goxe: {e}")

def get_active_goxe_session(user_id):
    """جلب الجولة النشطة للاعب"""
    try:
        db = get_firestore_db()
        doc = db.collection('goxe_sessions').document(str(user_id)).get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        print(f"❌ خطأ في جلب جلسة Goxe للمستخدم {user_id}: {e}")
    return None

def save_goxe_session(user_id, session_data):
    """حفظ الجلسة النشطة"""
    try:
        db = get_firestore_db()
        db.collection('goxe_sessions').document(str(user_id)).set(session_data)
    except Exception as e:
        print(f"❌ خطأ في حفظ جلسة Goxe: {e}")

def delete_goxe_session(user_id):
    """حذف الجلسة بعد الخسارة أو الانسحاب"""
    try:
        db = get_firestore_db()
        db.collection('goxe_sessions').document(str(user_id)).delete()
    except Exception as e:
        print(f"❌ خطأ في حذف جلسة Goxe: {e}")

init_goxe_db()

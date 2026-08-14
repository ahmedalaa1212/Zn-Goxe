import time
import database
from firebase_admin import firestore

_CONFIG_CACHE = None
_LAST_CACHE_TIME = 0
CACHE_TTL = 15

def get_firestore_db():
    return database.get_db()

def init_fogo_db():
    """تهيئة إعدادات لعبة fogo في Firebase مع تفعيل اقتصاد 60% للبوت / 40% للاعبين ورسوم الدرع 25%"""
    try:
        db = get_firestore_db()
        config_ref = db.collection('game_settings').document('fogo_config')
        doc = config_ref.get()

        if not doc.exists:
            config_ref.set({
                'game_name': 'fogo - Cyber Sweep',
                'target_bot_profit_pct': 60.0,
                'target_player_profit_pct': 40.0,
                'force_loss_threshold': 59.0,
                'shield_fee_percentage': 25.0,
                'total_wagered': 1000.0,
                'total_payout': 400.0,
                'force_loss_override': False,
                'allowed_bet_options': [50, 100, 300, 500, 1000, 8000]
            })
            print("✅ تم إنشاء مستند fogo_config بنجاح.")
    except Exception as e:
        print(f"❌ خطأ أثناء تهيئة fogo_db: {e}")

def get_fogo_config(force_refresh=False):
    global _CONFIG_CACHE, _LAST_CACHE_TIME
    current_time = time.time()

    if not force_refresh and _CONFIG_CACHE and (current_time - _LAST_CACHE_TIME < CACHE_TTL):
        return _CONFIG_CACHE

    try:
        db = get_firestore_db()
        doc = db.collection('game_settings').document('fogo_config').get()
        if doc.exists:
            _CONFIG_CACHE = doc.to_dict()
            _LAST_CACHE_TIME = current_time
            return _CONFIG_CACHE
    except Exception as e:
        print(f"❌ خطأ في جلب إعدادات fogo: {e}")

    return {
        'game_name': 'fogo - Cyber Sweep',
        'target_bot_profit_pct': 60.0,
        'force_loss_threshold': 59.0,
        'shield_fee_percentage': 25.0,
        'total_wagered': 1000.0,
        'total_payout': 400.0,
        'force_loss_override': False,
        'allowed_bet_options': [50, 100, 300, 500, 1000, 8000]
    }

def get_bot_profit_percentage():
    config = get_fogo_config()
    wagered = float(config.get('total_wagered', 1000.0))
    payout = float(config.get('total_payout', 400.0))

    if wagered <= 0:
        return 100.0

    profit = wagered - payout
    return (profit / wagered) * 100.0

def update_fogo_economy_stats(wager_amount, payout_amount):
    global _CONFIG_CACHE
    try:
        db = get_firestore_db()
        config_ref = db.collection('game_settings').document('fogo_config')
        config_ref.update({
            'total_wagered': firestore.Increment(float(wager_amount)),
            'total_payout': firestore.Increment(float(payout_amount))
        })
        if _CONFIG_CACHE:
            _CONFIG_CACHE['total_wagered'] = float(_CONFIG_CACHE.get('total_wagered', 0)) + float(wager_amount)
            _CONFIG_CACHE['total_payout'] = float(_CONFIG_CACHE.get('total_payout', 0)) + float(payout_amount)
    except Exception as e:
        print(f"❌ خطأ أثناء تحديث اقتصاد fogo: {e}")

def get_active_fogo_session(user_id):
    try:
        db = get_firestore_db()
        doc = db.collection('fogo_sessions').document(str(user_id)).get()
        if doc.exists:
            return doc.to_dict()
    except Exception as e:
        print(f"❌ خطأ في جلب جلسة fogo للمستخدم {user_id}: {e}")
    return None

def save_fogo_session(user_id, session_data):
    try:
        db = get_firestore_db()
        db.collection('fogo_sessions').document(str(user_id)).set(session_data)
    except Exception as e:
        print(f"❌ خطأ في حفظ جلسة fogo: {e}")

def delete_fogo_session(user_id):
    try:
        db = get_firestore_db()
        db.collection('fogo_sessions').document(str(user_id)).delete()
    except Exception as e:
        print(f"❌ خطأ في حذف جلسة fogo: {e}")

init_fogo_db()

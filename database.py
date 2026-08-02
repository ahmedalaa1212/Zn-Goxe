import os
import json
import time
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, firestore

db = None

# ==================== Dynamic In-Memory Cache System ====================
_SETTINGS_CACHE = None
_SETTINGS_CACHE_TIME = 0
SETTINGS_CACHE_TTL = 600  # كاش إعدادات اللعبة (10 دقائق)

_BAN_CACHE = {}           # {tg_id: (is_banned, expire_time)}
BAN_CACHE_TTL = 120       # كاش فحص الحظر (دقيقتين لكل مستخدم)

_LEADERBOARD_CACHE = None
_LEADERBOARD_CACHE_TIME = 0
LEADERBOARD_CACHE_TTL = 180  # كاش لوحة الصدارة (3 دقائق)
# ========================================================================

def ensure_game_settings_exist():
    """تحديث وإعداد وثائق التحكم الأساسية في Firestore داخل مجموعة app_config"""
    global db
    if not db:
        return
    try:
        config_ref = db.collection('app_config').document('game_settings')
        doc = config_ref.get()

        if not doc.exists:
            initial_settings = {
                "usd_to_zn_rate": 10000000,
                "daily_rewards": {
                    "day_1": 100, "day_2": 150, "day_3": 200, "day_4": 250, "day_5": 300,
                    "day_6": 350, "day_7": 400, "day_8": 450, "day_9": 500, "day_10": 550,
                    "day_20": 800, "day_30": 1250
                },
                "speed_config": {
                    "1": {"price": 2000, "rate": 5},
                    "2": {"price": 7000, "rate": 15},
                    "3": {"price": 18000, "rate": 35},
                    "4": {"price": 45000, "rate": 80}
                },
                "storage_config": {
                    "0": {"capacity": 200, "price": 0},
                    "1": {"capacity": 600, "price": 3000},
                    "2": {"capacity": 1500, "price": 10000}
                },
                "friends_config": {
                    "commission_percent": 10,
                    "claim_fee_percent": 1.5
                },
                "arena_config": {
                    "entry_fee": 1000,
                    "min_participants": 20,
                    "prize_pool_percentage": 0.45
                }
            }
            config_ref.set(initial_settings, merge=True)
            print("✅ تم إنشاء تهيئة app_config/game_settings بنجاح!")
    except Exception as e:
        print(f"❌ خطأ أثناء تهيئة الإعدادات: {e}")

def initialize_firebase():
    global db
    if not firebase_admin._apps:
        firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
        try:
            if firebase_creds_json:
                try:
                    creds_dict = json.loads(firebase_creds_json)
                except Exception:
                    creds_dict = json.loads(firebase_creds_json.replace('\\n', '\n'))
                
                if isinstance(creds_dict, dict) and "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace('\\n', '\n')

                cred = credentials.Certificate(creds_dict)
            else:
                if os.path.exists("firebase-adminsdk.json"):
                    cred = credentials.Certificate("firebase-adminsdk.json")
                else:
                    raise FileNotFoundError("لم يتم العثور على بيانات اعتماد Firebase!")
            
            firebase_admin.initialize_app(cred)
            print("✅ Firebase Initialized Successfully!")
        except Exception as e:
            print(f"❌ Critical Firebase Initialization Error: {e}")
            raise e
            
    if db is None:
        db = firestore.client()
    return db

try:
    db = initialize_firebase()
    ensure_game_settings_exist()
except Exception as e:
    print(f"⚠️ تنبيه أثناء تهيئة DB تلقائياً: {e}")

def get_game_settings():
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    now = time.time()
    if _SETTINGS_CACHE is not None and (now - _SETTINGS_CACHE_TIME) < SETTINGS_CACHE_TTL:
        return _SETTINGS_CACHE

    try:
        doc = db.collection('app_config').document('game_settings').get()
        if doc.exists:
            _SETTINGS_CACHE = doc.to_dict() or {}
            _SETTINGS_CACHE_TIME = now
            return _SETTINGS_CACHE
        return {}
    except Exception as e:
        print(f"❌ Error getting game settings: {e}")
        return _SETTINGS_CACHE or {}

def is_user_banned(tg_id):
    if not tg_id: 
        return False
        
    tg_id_str = str(tg_id)
    now = time.time()

    if tg_id_str in _BAN_CACHE:
        is_banned, expire_time = _BAN_CACHE[tg_id_str]
        if now < expire_time:
            return is_banned

    try:
        doc = db.collection('users').document(tg_id_str).get()
        is_banned = bool((doc.to_dict() or {}).get('banned', False)) if doc.exists else False
        _BAN_CACHE[tg_id_str] = (is_banned, now + BAN_CACHE_TTL)
        return is_banned
    except Exception as e:
        print(f"❌ Error checking ban status: {e}")
        return False

def init_user(tg_id, ref_id=None, first_name="صديقي"):
    try:
        if not tg_id: return False
            
        tg_id_str = str(tg_id)
        user_ref = db.collection('users').document(tg_id_str)
        user_doc = user_ref.get()
        
        is_new_referral = False
        valid_ref_id = str(ref_id) if ref_id and str(ref_id) != tg_id_str else None
        now_iso = datetime.now(timezone.utc).isoformat()

        if not user_doc.exists:
            new_user_data = {
                "tg_id": tg_id_str,
                "first_name": first_name,
                "balance": 0.0,
                "ad_balance": 0.0,
                "usd_balance": 0.0,
                "hourly_rate": 0.0,
                "energy": 100.0,
                "storage_level": 0,
                "max_cap": 200.0,
                "last_claim_time": now_iso,
                "upgrades": {},
                "banned": False,
                "wallet_address": None,
                "referred_by": valid_ref_id,
                "invited_friends_count": 0,
                "last_active": firestore.SERVER_TIMESTAMP,
                "joined_at": firestore.SERVER_TIMESTAMP
            }
            user_ref.set(new_user_data)
            
            if valid_ref_id:
                referrer_ref = db.collection('users').document(valid_ref_id)
                if referrer_ref.get().exists:
                    is_new_referral = True
                    referrer_ref.update({"invited_friends_count": firestore.Increment(1)})
                    referrer_ref.collection('friends').document(tg_id_str).set({
                        "tg_id": tg_id_str,
                        "first_name": first_name,
                        "earned_from_him": 0.0,
                        "joined_at": firestore.SERVER_TIMESTAMP
                    }, merge=True)
        else:
            user_ref.update({
                "first_name": first_name,
                "last_active": firestore.SERVER_TIMESTAMP
            })
        
        return is_new_referral
    except Exception as e:
        print(f"❌ Error initializing user {tg_id}: {e}")
        return False

def get_user(tg_id):
    try:
        if not tg_id: return None
        doc = db.collection('users').document(str(tg_id)).get()
        if doc.exists:
            data = doc.to_dict() or {}
            data['id'] = doc.id
            return data
        return None
    except Exception as e:
        print(f"❌ Error getting user {tg_id}: {e}")
        return None

def update_user(tg_id, update_data):
    try:
        if not tg_id or not isinstance(update_data, dict): return False
        db.collection('users').document(str(tg_id)).update(update_data)
        return True
    except Exception as e:
        print(f"❌ Error updating user {tg_id}: {e}")
        return False

def update_user_balance(tg_id, amount, balance_type="balance"):
    try:
        if not tg_id: return False
        field_map = {
            "balance": "balance",
            "usd": "usd_balance",
            "usd_balance": "usd_balance",
            "ad": "ad_balance",
            "ad_balance": "ad_balance"
        }
        target_field = field_map.get(balance_type, "balance")
        db.collection('users').document(str(tg_id)).update({
            target_field: firestore.Increment(float(amount))
        })
        return True
    except Exception as e:
        print(f"❌ Error updating balance for {tg_id}: {e}")
        return False

def ban_user(tg_id, status=True):
    try:
        if not tg_id: return False
        tg_id_str = str(tg_id)
        db.collection('users').document(tg_id_str).update({"banned": bool(status)})
        _BAN_CACHE[tg_id_str] = (bool(status), time.time() + BAN_CACHE_TTL)
        return True
    except Exception as e:
        print(f"❌ Error changing ban status: {e}")
        return False

def get_top_users(limit=50):
    global _LEADERBOARD_CACHE, _LEADERBOARD_CACHE_TIME
    now = time.time()
    if _LEADERBOARD_CACHE is not None and (now - _LEADERBOARD_CACHE_TIME) < LEADERBOARD_CACHE_TTL:
        return _LEADERBOARD_CACHE

    try:
        users_ref = db.collection('users').order_by('balance', direction=firestore.Query.DESCENDING).limit(limit)
        docs = users_ref.stream()
        leaderboard = [{
            "tg_id": doc.id,
            "first_name": (doc.to_dict() or {}).get("first_name", "لاعب"),
            "balance": (doc.to_dict() or {}).get("balance", 0.0),
            "hourly_rate": (doc.to_dict() or {}).get("hourly_rate", 0.0)
        } for doc in docs]
        _LEADERBOARD_CACHE = leaderboard
        _LEADERBOARD_CACHE_TIME = now
        return leaderboard
    except Exception as e:
        print(f"❌ Error getting leaderboard: {e}")
        return _LEADERBOARD_CACHE or []

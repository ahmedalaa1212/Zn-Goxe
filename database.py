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
    """تحديث وإعداد وثائق التحكم الأساسية في Firestore داخل مجموعة app_config تلقائياً"""
    global db, _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    if not db:
        try:
            db = initialize_firebase()
        except Exception as e:
            print(f"❌ Error initializing firebase inside ensure_game_settings_exist: {e}")
            return None

    try:
        config_ref = db.collection('app_config').document('game_settings')
        
        daily_rewards_30_days = {
            f"day_{i}": val for i, val in enumerate([
                100, 150, 200, 250, 300, 350, 400, 500, 600, 700,
                800, 900, 1000, 1200, 1400, 1600, 1800, 2000, 2300, 2600,
                3000, 3500, 4000, 4500, 5000, 6000, 7000, 8000, 9000, 10000
            ], start=1)
        }

        initial_settings = {
            "usd_to_zn_rate": 10000000,
            "ad_reward_boost": 2.0,
            "daily_rewards": daily_rewards_30_days,
            "speed_config": {
                "1": {"price": 2000, "rate": 5, "rate_bonus": 5.0, "base_cost": 2000.0},
                "2": {"price": 7000, "rate": 15, "rate_bonus": 15.0, "base_cost": 7000.0},
                "3": {"price": 18000, "rate": 35, "rate_bonus": 35.0, "base_cost": 18000.0},
                "4": {"price": 45000, "rate": 80, "rate_bonus": 80.0, "base_cost": 45000.0},
                "5": {"price": 110000, "rate": 180, "rate_bonus": 180.0, "base_cost": 110000.0},
                "6": {"price": 260000, "rate": 400, "rate_bonus": 400.0, "base_cost": 260000.0},
                "7": {"price": 600000, "rate": 900, "rate_bonus": 900.0, "base_cost": 600000.0},
                "8": {"price": 1400000, "rate": 2000, "rate_bonus": 2000.0, "base_cost": 1400000.0},
                "9": {"price": 3200000, "rate": 4500, "rate_bonus": 4500.0, "base_cost": 3200000.0}
            },
            "storage_config": {
                "0": {"capacity": 200.0, "price": 0},
                "1": {"capacity": 600.0, "price": 3000},
                "2": {"capacity": 1500.0, "price": 10000},
                "3": {"capacity": 25000, "price": 25000},
                "4": {"capacity": 8000.0, "price": 60000},
                "5": {"capacity": 18000.0, "price": 150000},
                "6": {"capacity": 40000.0, "price": 350000},
                "7": {"capacity": 90000.0, "price": 800000},
                "8": {"capacity": 200000.0, "price": 1800000},
                "9": {"capacity": 450000.0, "price": 4000000},
                "10": {"capacity": 1000000.0, "price": 10000000}
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
        _SETTINGS_CACHE = initial_settings
        _SETTINGS_CACHE_TIME = time.time()
        print("✅ تم إنشاء وتحديث app_config/game_settings في Firestore بنجاح!")
        return initial_settings
    except Exception as e:
        print(f"❌ خطأ أثناء تهيئة الإعدادات: {e}")
        return None

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
        if not db:
            initialize_firebase()

        doc = db.collection('app_config').document('game_settings').get()
        if doc.exists:
            _SETTINGS_CACHE = doc.to_dict() or {}
            _SETTINGS_CACHE_TIME = now
            return _SETTINGS_CACHE
        else:
            print("⚠️ app_config/game_settings غير موجودة في Firestore، جاري إنشاؤها فوراً...")
            new_settings = ensure_game_settings_exist()
            if new_settings:
                return new_settings
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
                "daily_streak": 0,
                "daily_day": 1,
                "last_daily_claim_date": None,
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
            user_data = user_doc.to_dict() or {}
            updates = {
                "first_name": first_name,
                "last_active": firestore.SERVER_TIMESTAMP
            }
            if "max_cap" not in user_data:
                updates["max_cap"] = 200.0
            if "storage_level" not in user_data:
                updates["storage_level"] = 0
            if "upgrades" not in user_data:
                updates["upgrades"] = {}
            if "hourly_rate" not in user_data:
                updates["hourly_rate"] = 0.0
                
            user_ref.update(updates)
        
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

def update_user_storage_level(tg_id, target_level=None):
    """
    🚀 ترقية المخزن بالتراكم الديناميكي (Dynamic Storage Delta):
    - تحسب الفارق الصافي (capacity_boost) بين المستوى القديم والجديد.
    - تضيف هذا الفارق باستعمال firestore.Increment فوق max_cap الحالية.
    - تضمن عدم ضياع أي تغيير يدوي من الفايربيس أو باقة سعة مسبقة.
    """
    try:
        if not tg_id:
            return False, "معرف المستخدم غير صحيح", 0, 0

        tg_id_str = str(tg_id)
        user_ref = db.collection('users').document(tg_id_str)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0, 0

        user_data = user_doc.to_dict() or {}
        current_level = int(user_data.get("storage_level", 0))
        current_balance = float(user_data.get("balance", 0.0))
        current_max_cap = float(user_data.get("max_cap", 200.0))

        next_level = int(target_level) if target_level is not None else current_level + 1

        if next_level <= current_level:
            return False, "أنت بالفعل في هذا المستوى أو مستوى أعلى!", current_max_cap, current_balance

        settings = get_game_settings()
        storage_cfg = settings.get("storage_config", {})

        curr_cfg = storage_cfg.get(str(current_level)) or storage_cfg.get(current_level) or {"capacity": 200.0}
        next_cfg = storage_cfg.get(str(next_level)) or storage_cfg.get(next_level)

        if not next_cfg:
            return False, "لقد وصلت إلى الحد الأقصى لمستويات المخزن!", current_max_cap, current_balance

        price = float(next_cfg.get("price", 0))

        if current_balance < price:
            return False, "رصيدك غير كافٍ لإجراء الترقية!", current_max_cap, current_balance

        curr_base_cap = float(curr_cfg.get("capacity", 200.0))
        next_base_cap = float(next_cfg.get("capacity", 600.0))
        capacity_boost = next_base_cap - curr_base_cap

        user_ref.update({
            "balance": firestore.Increment(-price),
            "storage_level": next_level,
            "max_cap": firestore.Increment(capacity_boost)
        })

        new_max_cap = current_max_cap + capacity_boost
        new_balance = current_balance - price

        return True, "تمت ترقية المخزن بنجاح!", new_max_cap, new_balance

    except Exception as e:
        print(f"❌ Error in update_user_storage_level for {tg_id}: {e}")
        return False, "حدث خطأ أثناء تنفيذ ترقية المخزن", 0, 0

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

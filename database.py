# database.py
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
    """دالة الفحص والتحديث التلقائي لكافة إعدادات اللعبة في Firestore فقط عند الحاجة"""
    global db
    if not db:
        return
    try:
        settings_ref = db.collection('config').document('game_settings')
        doc = settings_ref.get()

        current_data = doc.to_dict() or {} if doc.exists else {}
        
        # إجراء التحديث فقط إذا كان المستند غير موجود أو يفتقر لإعدادات الساحة
        if not doc.exists or 'arena_config' not in current_data:
            exact_daily_rewards = {
                "day_1": 100,   "day_2": 150,   "day_3": 200,   "day_4": 250,   "day_5": 300,
                "day_6": 350,   "day_7": 400,   "day_8": 450,   "day_9": 500,   "day_10": 550,
                "day_11": 600,  "day_12": 600,  "day_13": 650,  "day_14": 650,  "day_15": 700,
                "day_16": 700,  "day_17": 750,  "day_18": 750,  "day_19": 800,  "day_20": 800,
                "day_21": 850,  "day_22": 850,  "day_23": 900,  "day_24": 900,  "day_25": 950,
                "day_26": 950,  "day_27": 1000, "day_28": 1000, "day_29": 1100, "day_30": 1250
            }

            exact_speed_config = {
                "1": {"price": 2000, "rate": 5, "max": 10},
                "2": {"price": 7000, "rate": 15, "max": 10},
                "3": {"price": 18000, "rate": 35, "max": 10},
                "4": {"price": 45000, "rate": 80, "max": 10},
                "5": {"price": 110000, "rate": 180, "max": 10},
                "6": {"price": 260000, "rate": 400, "max": 10},
                "7": {"price": 600000, "rate": 900, "max": 10},
                "8": {"price": 1400000, "rate": 2000, "max": 10},
                "9": {"price": 3200000, "rate": 4500, "max": 10}
            }

            exact_storage_config = {
                "0": {"capacity": 200, "price": 0},
                "1": {"capacity": 600, "price": 3000},
                "2": {"capacity": 1500, "price": 10000},
                "3": {"capacity": 3500, "price": 25000},
                "4": {"capacity": 8000, "price": 65000},
                "5": {"capacity": 18000, "price": 160000},
                "6": {"capacity": 40000, "price": 400000},
                "7": {"capacity": 90000, "price": 950000},
                "8": {"capacity": 220000, "price": 2200000},
                "9": {"capacity": 450000, "price": 5000000},
                "10": {"capacity": 1000000, "price": 12000000}
            }

            exact_friends_config = {
                "direct_reward_inviter": 0,
                "direct_reward_invitee": 0,
                "commission_percent": 10,
                "claim_fee_percent": 1.5,
                "min_upgrades_for_task": 3,
                "ref_tasks": {
                    "1": {"reqFriends": 1, "reward": 4000},
                    "2": {"reqFriends": 5, "reward": 25000},
                    "3": {"reqFriends": 10, "reward": 60000},
                    "4": {"reqFriends": 25, "reward": 160000},
                    "5": {"reqFriends": 50, "reward": 350000},
                    "6": {"reqFriends": 100, "reward": 800000},
                    "7": {"reqFriends": 500, "reward": 4500000}
                }
            }

            exact_arena_config = {
                "entry_fee": 1000,
                "min_participants": 20,
                "prize_pool_percentage": 0.45,
                "round_duration": 900,
                "lock_seconds": 15
            }

            friends_cfg = current_data.get("friends_config") or exact_friends_config
            friends_cfg["direct_reward_inviter"] = 0
            friends_cfg["direct_reward_invitee"] = 0

            update_payload = {
                "usd_to_zn_rate": current_data.get("usd_to_zn_rate", 10000000),
                "daily_rewards": current_data.get("daily_rewards", exact_daily_rewards),
                "speed_config": current_data.get("speed_config", exact_speed_config),
                "storage_config": current_data.get("storage_config", exact_storage_config),
                "daily_ad_boost_rate": current_data.get("daily_ad_boost_rate", 2),
                "friends_config": friends_cfg,
                "arena_config": current_data.get("arena_config", exact_arena_config)
            }

            settings_ref.set(update_payload, merge=True)
            print("✅ تم تحديث/تهيئة إعدادات اللعبة في Firestore بنجاح!")

    except Exception as e:
        print(f"❌ خطأ أثناء تحديث إعدادات اللعبة تلقائياً: {e}")

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
                print("✅ تم الاتصال بـ Firebase عبر متغيرات البيئة (Production).")
            else:
                if os.path.exists("firebase-adminsdk.json"):
                    cred = credentials.Certificate("firebase-adminsdk.json")
                    print("⚠️ تم الاتصال بـ Firebase عبر الملف المحلي (Development).")
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
        doc = db.collection('config').document('game_settings').get()
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
        print(f"❌ Error checking ban status for {tg_id}: {e}")
        if tg_id_str in _BAN_CACHE:
            return _BAN_CACHE[tg_id_str][0]
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
                "telegram_id": tg_id_str,
                "first_name": first_name,
                "balance": 0.0,
                "ad_balance": 0.0,
                "usd_balance": 0.0,
                "hourly_rate": 0.0,
                "unclaimed": 0.0,
                "storage_level": 0,
                "max_cap": 200.0,
                "daily_day": 1,
                "last_claim_time": now_iso,
                "last_daily_claim_date": None,
                "last_boost_date": None,
                "ads_watched": 0,
                "upgrades": {},
                "banned": False,
                "wallet_address": None,
                "referred_by": valid_ref_id,
                "invited_friends_count": 0,
                "pending_ref_earnings": 0.0,
                "total_ref_earnings": 0.0,
                "claimed_ref_tasks": [],
                "claimed_tasks": [],
                "last_active": firestore.SERVER_TIMESTAMP,
                "joined_at": firestore.SERVER_TIMESTAMP
            }
            user_ref.set(new_user_data)
            
            if valid_ref_id:
                referrer_ref = db.collection('users').document(valid_ref_id)
                if referrer_ref.get().exists:
                    is_new_referral = True
                    referrer_ref.update({
                        "invited_friends_count": firestore.Increment(1)
                    })
                    referrer_ref.collection('friends').document(tg_id_str).set({
                        "tg_id": tg_id_str,
                        "first_name": first_name,
                        "earned_from_him": 0.0,
                        "joined_at": firestore.SERVER_TIMESTAMP
                    }, merge=True)
        else:
            u_data = user_doc.to_dict() or {}
            current_ref = u_data.get('referred_by')
            
            if valid_ref_id and not current_ref:
                referrer_ref = db.collection('users').document(valid_ref_id)
                if referrer_ref.get().exists:
                    user_ref.update({"referred_by": valid_ref_id})
                    referrer_ref.update({"invited_friends_count": firestore.Increment(1)})
                    referrer_ref.collection('friends').document(tg_id_str).set({
                        "tg_id": tg_id_str,
                        "first_name": first_name,
                        "earned_from_him": 0.0,
                        "joined_at": firestore.SERVER_TIMESTAMP
                    }, merge=True)
            
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

def add_referral_earnings(referrer_id, friend_id, amount):
    try:
        if not referrer_id or not amount or float(amount) <= 0: return False
            
        ref_str = str(referrer_id)
        friend_str = str(friend_id)
        
        settings = get_game_settings()
        f_config = settings.get('friends_config', {})
        commission_percent = float(f_config.get('commission_percent', 10)) / 100.0

        ref_amount = float(amount) * commission_percent
        if ref_amount <= 0:
            return False
        
        db.collection('users').document(ref_str).update({
            "pending_ref_earnings": firestore.Increment(ref_amount),
            "total_ref_earnings": firestore.Increment(ref_amount)
        })
        
        friend_ref = db.collection('users').document(ref_str).collection('friends').document(friend_str)
        friend_doc = friend_ref.get()
        if friend_doc.exists:
            friend_ref.update({"earned_from_him": firestore.Increment(ref_amount)})
        else:
            f_user_doc = db.collection('users').document(friend_str).get()
            f_name = "صديق"
            if f_user_doc.exists:
                f_data = f_user_doc.to_dict() or {}
                f_name = f_data.get('first_name') or f_data.get('name') or "صديق"

            friend_ref.set({
                "tg_id": friend_str,
                "first_name": f_name,
                "earned_from_him": ref_amount,
                "joined_at": firestore.SERVER_TIMESTAMP
            }, merge=True)

        return True
    except Exception as e:
        print(f"❌ Error adding referral earnings: {e}")
        return False

def create_transaction(tg_id, tx_type, amount_usd, wallet_address=None, status="pending", details=None):
    try:
        if not tg_id: return False
        
        tx_data = {
            "tg_id": str(tg_id),
            "type": tx_type,
            "amount_usd": float(amount_usd),
            "wallet_address": wallet_address,
            "status": status,
            "details": details or {},
            "created_at": firestore.SERVER_TIMESTAMP
        }
        
        doc_ref = db.collection('transactions').add(tx_data)
        return doc_ref[1].id
    except Exception as e:
        print(f"❌ Error creating transaction: {e}")
        return False

def update_transaction_status(tx_id, status, extra_details=None):
    try:
        if not tx_id: return False
        data = {"status": status, "updated_at": firestore.SERVER_TIMESTAMP}
        if extra_details and isinstance(extra_details, dict):
            for k, v in extra_details.items():
                data[f"details.{k}"] = v
        db.collection('transactions').document(tx_id).update(data)
        return True
    except Exception as e:
        print(f"❌ Error updating transaction {tx_id}: {e}")
        return False

def get_user_transactions(tg_id, limit=30):
    try:
        if not tg_id: return []
        docs = db.collection('transactions').where('tg_id', '==', str(tg_id)).limit(limit).stream()
        
        history = []
        for doc in docs:
            item = doc.to_dict() or {}
            item['id'] = doc.id
            if item.get('created_at') and hasattr(item['created_at'], 'isoformat'):
                item['created_at'] = item['created_at'].isoformat()
            history.append(item)
            
        history.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
        return history
    except Exception as e:
        print(f"❌ Error fetching transactions for {tg_id}: {e}")
        return []

def ban_user(tg_id, status=True):
    try:
        if not tg_id: return False
        tg_id_str = str(tg_id)
        db.collection('users').document(tg_id_str).update({"banned": bool(status)})
        _BAN_CACHE[tg_id_str] = (bool(status), time.time() + BAN_CACHE_TTL)
        return True
    except Exception as e:
        print(f"❌ Error changing ban status for {tg_id}: {e}")
        return False

def get_top_users(limit=50):
    global _LEADERBOARD_CACHE, _LEADERBOARD_CACHE_TIME
    now = time.time()
    if _LEADERBOARD_CACHE is not None and (now - _LEADERBOARD_CACHE_TIME) < LEADERBOARD_CACHE_TTL:
        return _LEADERBOARD_CACHE

    try:
        users_ref = db.collection('users').order_by('balance', direction=firestore.Query.DESCENDING).limit(limit)
        docs = users_ref.stream()
        leaderboard = []
        for doc in docs:
            data = doc.to_dict() or {}
            leaderboard.append({
                "tg_id": doc.id,
                "first_name": data.get("first_name", "لاعب"),
                "balance": data.get("balance", 0.0),
                "hourly_rate": data.get("hourly_rate", 0.0)
            })
        _LEADERBOARD_CACHE = leaderboard
        _LEADERBOARD_CACHE_TIME = now
        return leaderboard
    except Exception as e:
        print(f"❌ Error getting leaderboard: {e}")
        return _LEADERBOARD_CACHE or []

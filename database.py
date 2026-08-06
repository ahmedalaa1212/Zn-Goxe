import os
import json
import time
from datetime import datetime, timezone, timedelta
import firebase_admin
from firebase_admin import credentials, firestore

db = None

# ==================== Dynamic In-Memory Cache System ====================
_SETTINGS_CACHE = None
_SETTINGS_CACHE_TIME = 0
SETTINGS_CACHE_TTL = 600  

_BAN_CACHE = {}           
BAN_CACHE_TTL = 120       

_LEADERBOARD_CACHE = None
_LEADERBOARD_CACHE_TIME = 0
LEADERBOARD_CACHE_TTL = 180  

_TREASURY_CACHE = None
_TREASURY_CACHE_TIME = 0
TREASURY_CACHE_TTL = 30  # كاش الخزينة يُحدث كل 30 ثانية لتسريع الجولات
# ========================================================================

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

def ensure_game_settings_exist():
    global db, _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    if not db:
        try:
            db = initialize_firebase()
        except Exception as e:
            print(f"❌ Error initializing firebase inside ensure_game_settings_exist: {e}")
            return None

    try:
        config_ref = db.collection('app_config').document('game_settings')
        doc_snap = config_ref.get()
        
        if doc_snap.exists:
            existing_data = doc_snap.to_dict() or {}
            
            # التأكد من وجود إعدادات لعبة شبكة العملات المكسورة
            if "grid_game_config" not in existing_data:
                grid_cfg = {
                    "min_bet": 250.0,
                    "target_margin": 0.80,
                    "default_broken_coins": 3
                }
                existing_data["grid_game_config"] = grid_cfg
                config_ref.update({"grid_game_config": grid_cfg})

            _SETTINGS_CACHE = existing_data
            _SETTINGS_CACHE_TIME = time.time()
            return existing_data

        daily_rewards_30_days = {
            f"day_{i}": val for i, val in enumerate([
                100, 150, 200, 250, 300, 350, 400, 450, 500, 550,
                600, 600, 650, 650, 700, 700, 750, 750, 800, 800,
                850, 850, 900, 900, 950, 950, 1000, 1000, 1100, 1250
            ], start=1)
        }

        mining_cfg = {
            "1": {"price": 3500.0, "rate": 5.0, "rate_bonus": 5.0, "base_cost": 3500.0, "max": 10},
            "2": {"price": 11500.0, "rate": 15.0, "rate_bonus": 15.0, "base_cost": 11500.0, "max": 10},
            "3": {"price": 28000.0, "rate": 35.0, "rate_bonus": 35.0, "base_cost": 28000.0, "max": 10},
            "4": {"price": 68000.0, "rate": 80.0, "rate_bonus": 80.0, "base_cost": 68000.0, "max": 10},
            "5": {"price": 165000.0, "rate": 180.0, "rate_bonus": 180.0, "base_cost": 165000.0, "max": 10},
            "6": {"price": 390000.0, "rate": 400.0, "rate_bonus": 400.0, "base_cost": 390000.0, "max": 10},
            "7": {"price": 950000.0, "rate": 900.0, "rate_bonus": 900.0, "base_cost": 950000.0, "max": 10},
            "8": {"price": 2300000.0, "rate": 2000.0, "rate_bonus": 2000.0, "base_cost": 2300000.0, "max": 10},
            "9": {"price": 5500000.0, "rate": 4500.0, "rate_bonus": 4500.0, "base_cost": 5500000.0, "max": 10}
        }

        storage_cfg = {
            "0": {"capacity": 100.0, "price": 0},
            "1": {"capacity": 300.0, "price": 3000},
            "2": {"capacity": 800.0, "price": 8500},
            "3": {"capacity": 2000.0, "price": 25000},
            "4": {"capacity": 5000.0, "price": 70000},
            "5": {"capacity": 12000.0, "price": 180000},
            "6": {"capacity": 28000.0, "price": 450000},
            "7": {"capacity": 65000.0, "price": 1100000},
            "8": {"capacity": 150000.0, "price": 2800000},
            "9": {"capacity": 350000.0, "price": 7000000},
            "10": {"capacity": 800000.0, "price": 18000000}
        }

        usdt_pkgs = {
            "pkg_0": {"usdt": 0.5, "rate_add": 70.0, "storage_add": 900.0, "zn_add": 13500.0, "title": "باقة التجربة"},
            "pkg_1": {"usdt": 1.0, "rate_add": 150.0, "storage_add": 2000.0, "zn_add": 30000.0, "title": "البرونزية"},
            "pkg_2": {"usdt": 3.0, "rate_add": 540.0, "storage_add": 7200.0, "zn_add": 108000.0, "title": "الفضية"},
            "pkg_3": {"usdt": 6.0, "rate_add": 1350.0, "storage_add": 18000.0, "zn_add": 270000.0, "title": "الذهبية"},
            "pkg_4": {"usdt": 10.0, "rate_add": 2850.0, "storage_add": 38000.0, "zn_add": 570000.0, "title": "باقة الحيتان"}
        }

        packages_cfg = [
            {"id": "pkg_starter", "title": "باقة المبتدئ", "price_usd": 1.0, "added_zn": 100000.0, "added_storage": 200.0, "active": True},
            {"id": "pkg_pro", "title": "باقة المحترف", "price_usd": 5.0, "added_zn": 600000.0, "added_storage": 1000.0, "active": True},
            {"id": "pkg_vip", "title": "باقة الحوت VIP", "price_usd": 15.0, "added_zn": 2000000.0, "added_storage": 5000.0, "active": True}
        ]

        initial_settings = {
            "usd_to_zn_rate": 1000000,
            "ad_reward_boost": 0.5,
            "daily_rewards": daily_rewards_30_days,
            "mining_config": mining_cfg,
            "storage_config": storage_cfg,
            "usdt_packages": usdt_pkgs,
            "packages_config": packages_cfg,
            "grid_game_config": {
                "min_bet": 250.0,
                "target_margin": 0.80,
                "default_broken_coins": 3
            },
            "friends_config": {
                "commission_percent": 10,
                "claim_fee_percent": 1.5,
                "min_upgrades_for_task": 3,
                "ref_tasks": {
                    "1": {"reqFriends": 1, "reward": 3000},
                    "2": {"reqFriends": 5, "reward": 18000},
                    "3": {"reqFriends": 10, "reward": 40000},
                    "4": {"reqFriends": 25, "reward": 110000},
                    "5": {"reqFriends": 50, "reward": 250000},
                    "6": {"reqFriends": 100, "reward": 600000},
                    "7": {"reqFriends": 500, "reward": 3500000}
                }
            },
            "arena_config": {
                "entry_fee": 1000,
                "min_participants": 20,
                "prize_pool_percentage": 0.45
            }
        }

        config_ref.set(initial_settings)
        _SETTINGS_CACHE = initial_settings
        _SETTINGS_CACHE_TIME = time.time()
        print("✅ تم إنشاء app_config/game_settings في Firestore بنجاح وبدون تكرارات!")
        return initial_settings
    except Exception as e:
        print(f"❌ خطأ أثناء تهيئة الإعدادات: {e}")
        return None

# ==================== Treasury & Safe Guard System ====================

def ensure_treasury_exist():
    global db, _TREASURY_CACHE, _TREASURY_CACHE_TIME
    if not db:
        try:
            db = initialize_firebase()
        except Exception as e:
            print(f"❌ Error initializing firebase inside ensure_treasury_exist: {e}")
            return None

    try:
        treasury_ref = db.collection('arena').document('current')
        doc_snap = treasury_ref.get()

        if doc_snap.exists:
            data = doc_snap.to_dict() or {}
            _TREASURY_CACHE = data
            _TREASURY_CACHE_TIME = time.time()
            return data

        initial_treasury = {
            "total_bets": 100000.0,
            "total_payouts": 10000.0,
            "prize_pool": 0.0,
            "fees_collected": 0.0,
            "last_updated": firestore.SERVER_TIMESTAMP
        }
        treasury_ref.set(initial_treasury)
        _TREASURY_CACHE = initial_treasury
        _TREASURY_CACHE_TIME = time.time()
        return initial_treasury
    except Exception as e:
        print(f"❌ Error initializing treasury: {e}")
        return None

def get_system_treasury():
    global _TREASURY_CACHE, _TREASURY_CACHE_TIME
    now = time.time()
    if _TREASURY_CACHE is not None and (now - _TREASURY_CACHE_TIME) < TREASURY_CACHE_TTL:
        return _TREASURY_CACHE

    try:
        if not db: initialize_firebase()
        doc = db.collection('arena').document('current').get()
        if doc.exists:
            data = doc.to_dict() or {}
            _TREASURY_CACHE = data
            _TREASURY_CACHE_TIME = now
            return _TREASURY_CACHE
        else:
            return ensure_treasury_exist() or {}
    except Exception as e:
        print(f"❌ Error getting system treasury: {e}")
        return _TREASURY_CACHE or {}

def get_system_profit_margin():
    treasury = get_system_treasury()
    total_bets = float(treasury.get("total_bets", 100000.0))
    total_payouts = float(treasury.get("total_payouts", 10000.0))

    if total_bets <= 0:
        return 1.0

    margin = (total_bets - total_payouts) / total_bets
    return margin

def update_system_treasury(bet_amount=0.0, payout_amount=0.0):
    global _TREASURY_CACHE, _TREASURY_CACHE_TIME
    try:
        if not db: initialize_firebase()
        treasury_ref = db.collection('arena').document('current')
        
        updates = {
            "last_updated": firestore.SERVER_TIMESTAMP
        }
        if bet_amount > 0:
            updates["total_bets"] = firestore.Increment(float(bet_amount))
        if payout_amount > 0:
            updates["total_payouts"] = firestore.Increment(float(payout_amount))

        treasury_ref.update(updates)

        if _TREASURY_CACHE is not None:
            _TREASURY_CACHE["total_bets"] = float(_TREASURY_CACHE.get("total_bets", 0.0)) + float(bet_amount)
            _TREASURY_CACHE["total_payouts"] = float(_TREASURY_CACHE.get("total_payouts", 0.0)) + float(payout_amount)
            _TREASURY_CACHE_TIME = time.time()

        return True
    except Exception as e:
        print(f"❌ Error updating system treasury: {e}")
        return False

# ========================================================================

try:
    db = initialize_firebase()
    ensure_game_settings_exist()
    ensure_treasury_exist()
except Exception as e:
    print(f"⚠️ تنبيه أثناء تهيئة DB تلقائياً: {e}")

def get_game_settings():
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    now = time.time()
    if _SETTINGS_CACHE is not None and (now - _SETTINGS_CACHE_TIME) < SETTINGS_CACHE_TTL:
        return _SETTINGS_CACHE

    try:
        if not db: initialize_firebase()
        doc = db.collection('app_config').document('game_settings').get()
        if doc.exists:
            data = doc.to_dict() or {}
            _SETTINGS_CACHE = data
            _SETTINGS_CACHE_TIME = now
            return _SETTINGS_CACHE
        else:
            new_settings = ensure_game_settings_exist()
            if new_settings: return new_settings
        return {}
    except Exception as e:
        print(f"❌ Error getting game settings: {e}")
        return _SETTINGS_CACHE or {}

def is_user_banned(tg_id):
    if not tg_id: return False
    tg_id_str = str(tg_id)
    now = time.time()

    if tg_id_str in _BAN_CACHE:
        is_banned, expire_time = _BAN_CACHE[tg_id_str]
        if now < expire_time: return is_banned

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
                "daily_boost_rate": 0.0,
                "ads_watched": 0,
                "energy": 100.0,
                "storage_level": 0,
                "extra_storage": 0.0,
                "max_cap": 100.0,
                "last_claim_time": now_iso,
                "daily_streak": 0,
                "daily_day": 1,
                "last_daily_claim_date": None,
                "upgrades": {},
                "completed_tasks": [],
                "banned": False,
                "wallet_address": None,
                "referred_by": valid_ref_id,
                "pending_ref_earnings": 0.0,
                "total_ref_earnings": 0.0,
                "invited_friends_count": 0,
                "claimed_ref_tasks": [],
                "boost_multiplier": 1,
                "boost_active": False,
                "boost_expires_at": None,
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
            if "balance" not in user_data: updates["balance"] = 0.0
            if "usd_balance" not in user_data: updates["usd_balance"] = 0.0
            if "max_cap" not in user_data: updates["max_cap"] = 100.0
            if "storage_level" not in user_data: updates["storage_level"] = 0
            if "extra_storage" not in user_data: updates["extra_storage"] = 0.0
            if "ad_balance" not in user_data: updates["ad_balance"] = 0.0
            if "completed_tasks" not in user_data: updates["completed_tasks"] = []
            if "upgrades" not in user_data: updates["upgrades"] = {}
            if "hourly_rate" not in user_data: updates["hourly_rate"] = 0.0
            if "daily_boost_rate" not in user_data: updates["daily_boost_rate"] = 0.0
            if "ads_watched" not in user_data: updates["ads_watched"] = 0
            if "pending_ref_earnings" not in user_data: updates["pending_ref_earnings"] = 0.0
            if "total_ref_earnings" not in user_data: updates["total_ref_earnings"] = 0.0
            if "claimed_ref_tasks" not in user_data: updates["claimed_ref_tasks"] = []
            if "boost_multiplier" not in user_data: updates["boost_multiplier"] = 1
            if "boost_active" not in user_data: updates["boost_active"] = False
            if "boost_expires_at" not in user_data: updates["boost_expires_at"] = None
                
            user_ref.update(updates)
        
        return is_new_referral
    except Exception as e:
        print(f"❌ Error initializing user {tg_id}: {e}")
        return False

def get_user(tg_id):
    try:
        if not tg_id: return None
        user_ref = db.collection('users').document(str(tg_id))
        doc = user_ref.get()
        if doc.exists:
            data = doc.to_dict() or {}
            data['id'] = doc.id
            
            auto_updates = {}

            if "balance" not in data or data["balance"] is None:
                auto_updates["balance"] = 0.0
                data["balance"] = 0.0
            else:
                try: data["balance"] = float(data["balance"])
                except Exception: data["balance"] = 0.0

            if "usd_balance" not in data or data["usd_balance"] is None:
                auto_updates["usd_balance"] = 0.0
                data["usd_balance"] = 0.0
            else:
                try: data["usd_balance"] = float(data["usd_balance"])
                except Exception: data["usd_balance"] = 0.0

            if "extra_storage" not in data or data["extra_storage"] is None:
                auto_updates["extra_storage"] = 0.0
                data["extra_storage"] = 0.0
            else:
                try: data["extra_storage"] = float(data["extra_storage"])
                except Exception: data["extra_storage"] = 0.0

            if "ad_balance" not in data:
                auto_updates["ad_balance"] = 0.0
                data["ad_balance"] = 0.0

            if "completed_tasks" not in data:
                auto_updates["completed_tasks"] = []
                data["completed_tasks"] = []

            if "storage_level" not in data:
                auto_updates["storage_level"] = 0
                data["storage_level"] = 0

            if "daily_boost_rate" not in data:
                auto_updates["daily_boost_rate"] = 0.0
                data["daily_boost_rate"] = 0.0

            if "ads_watched" not in data:
                auto_updates["ads_watched"] = 0
                data["ads_watched"] = 0

            if "boost_multiplier" not in data:
                auto_updates["boost_multiplier"] = 1
                data["boost_multiplier"] = 1

            if "boost_active" not in data:
                auto_updates["boost_active"] = False
                data["boost_active"] = False

            if "boost_expires_at" not in data:
                auto_updates["boost_expires_at"] = None
                data["boost_expires_at"] = None

            if "pending_ref_earnings" not in data:
                auto_updates["pending_ref_earnings"] = 0.0
                data["pending_ref_earnings"] = 0.0

            if "total_ref_earnings" not in data:
                auto_updates["total_ref_earnings"] = 0.0
                data["total_ref_earnings"] = 0.0

            stg_lvl = str(data.get("storage_level", 0))
            settings = get_game_settings()
            stg_cfg = settings.get("storage_config", {})
            
            base_cap = 100.0
            if stg_lvl in stg_cfg and isinstance(stg_cfg[stg_lvl], dict):
                base_cap = float(stg_cfg[stg_lvl].get("capacity", 100.0))

            current_extra = float(data.get("extra_storage", 0.0))
            expected_total_max = base_cap + current_extra

            if float(data.get("max_cap", 0.0)) != expected_total_max:
                auto_updates["max_cap"] = expected_total_max
                data["max_cap"] = expected_total_max

            if auto_updates:
                user_ref.update(auto_updates)

            return data
        return None
    except Exception as e:
        print(f"❌ Error getting user {tg_id}: {e}")
        return None

# ==================== Task & Campaign Database Functions ====================

def get_active_campaigns(tg_id):
    try:
        if not db: initialize_firebase()
        user_data = get_user(tg_id) or {}
        completed_list = [str(x) for x in user_data.get("completed_tasks", [])]

        campaigns_ref = db.collection('tasks').where('active', '==', True).limit(100)
        docs = campaigns_ref.stream()

        campaigns = []
        for doc in docs:
            d = doc.to_dict() or {}
            cid = doc.id
            comp_count = int(d.get('users_completed', 0))
            need_count = int(d.get('users_needed', 1))

            if comp_count >= need_count:
                continue

            campaigns.append({
                "id": cid,
                "creator_id": str(d.get("creator_id", "")),
                "platform": d.get("platform", "أخرى"),
                "description": d.get("description", ""),
                "url": d.get("url", ""),
                "reward": float(d.get("reward", 0)),
                "users_needed": need_count,
                "users_completed": comp_count,
                "is_completed": (cid in completed_list)
            })

        return campaigns, float(user_data.get("balance", 0.0)), float(user_data.get("ad_balance", 0.0))
    except Exception as e:
        print(f"❌ Error fetching active campaigns: {e}")
        return [], 0.0, 0.0

def complete_user_task(tg_id, task_id):
    try:
        if not tg_id or not task_id:
            return False, "بيانات غير صالحة", 0.0

        tg_id_str = str(tg_id)
        task_id_str = str(task_id)

        user_ref = db.collection('users').document(tg_id_str)
        task_ref = db.collection('tasks').document(task_id_str)

        user_doc = user_ref.get()
        task_doc = task_ref.get()

        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0.0
        if not task_doc.exists:
            return False, "المهمة غير موجودة أو انتهت", 0.0

        user_data = user_doc.to_dict() or {}
        task_data = task_doc.to_dict() or {}

        completed = [str(x) for x in user_data.get("completed_tasks", [])]
        if task_id_str in completed:
            return False, "لقد قمت بإكمال هذه المهمة من قبل!", float(user_data.get("balance", 0.0))

        reward = float(task_data.get("reward", 0.0))
        new_balance = round(float(user_data.get("balance", 0.0)) + reward, 2)

        task_ref.update({
            "users_completed": firestore.Increment(1)
        })

        user_ref.update({
            "balance": new_balance,
            "completed_tasks": firestore.ArrayUnion([task_id_str])
        })

        return True, "تم إكمال المهمة بنجاح!", new_balance
    except Exception as e:
        print(f"❌ Error completing task {task_id} for user {tg_id}: {e}")
        return False, "حدث خطأ أثناء معالجة المهمة", 0.0

def create_ad_campaign(tg_id, platform, description, url, reward, users_needed):
    try:
        if not tg_id: return False, "معرف غير صالح", 0.0
        tg_id_str = str(tg_id)
        
        reward = float(reward)
        users_needed = int(users_needed)
        total_cost = reward * users_needed

        if reward < 250 or total_cost < 250:
            return False, "الحد الأدنى لتكلفة الضغطة والميزانية هو 250 AdZN", 0.0

        user_ref = db.collection('users').document(tg_id_str)
        user_doc = user_ref.get()
        if not user_doc.exists: return False, "المستخدم غير موجود", 0.0

        user_data = user_doc.to_dict() or {}
        current_ad_bal = float(user_data.get("ad_balance", 0.0))

        if current_ad_bal < total_cost:
            return False, "رصيد الإعلانات غير كافٍ!", current_ad_bal

        new_ad_bal = round(current_ad_bal - total_cost, 2)
        user_ref.update({"ad_balance": new_ad_bal})

        campaign_doc = {
            "creator_id": tg_id_str,
            "platform": platform,
            "description": description,
            "url": url,
            "reward": reward,
            "users_needed": users_needed,
            "users_completed": 0,
            "active": True,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        db.collection('tasks').add(campaign_doc)

        return True, "تم إنشاء الحملة بنجاح!", new_ad_bal
    except Exception as e:
        print(f"❌ Error creating campaign: {e}")
        return False, f"حدث خطأ: {e}", 0.0

def cancel_ad_campaign(tg_id, task_id):
    try:
        if not tg_id or not task_id: return False, "بيانات غير صالحة", 0.0, 0.0
        tg_id_str = str(tg_id)
        task_id_str = str(task_id)

        task_ref = db.collection('tasks').document(task_id_str)
        task_doc = task_ref.get()

        if not task_doc.exists: return False, "الحملة غير موجودة", 0.0, 0.0

        task_data = task_doc.to_dict() or {}
        if str(task_data.get("creator_id")) != tg_id_str:
            return False, "غير مصرح لك بإلغاء هذه الحملة", 0.0, 0.0

        reward = float(task_data.get("reward", 0.0))
        needed = int(task_data.get("users_needed", 0))
        completed = int(task_data.get("users_completed", 0))

        remaining_count = max(0, needed - completed)
        refund_amount = round(remaining_count * reward, 2)

        user_ref = db.collection('users').document(tg_id_str)
        user_doc = user_ref.get()
        current_ad_bal = float((user_doc.to_dict() or {}).get("ad_balance", 0.0)) if user_doc.exists else 0.0

        new_ad_bal = round(current_ad_bal + refund_amount, 2)

        task_ref.update({"active": False})
        user_ref.update({"ad_balance": new_ad_bal})

        return True, "تم إلغاء الحملة واسترداد المتبقي!", new_ad_bal, refund_amount
    except Exception as e:
        print(f"❌ Error canceling campaign {task_id}: {e}")
        return False, f"حدث خطأ: {e}", 0.0, 0.0

def convert_balance_to_ad_balance(tg_id, amount):
    try:
        if not tg_id or amount <= 0: return False, "مبلغ غير صالح", 0.0, 0.0
        tg_id_str = str(tg_id)
        user_ref = db.collection('users').document(tg_id_str)
        user_doc = user_ref.get()

        if not user_doc.exists: return False, "المستخدم غير موجود", 0.0, 0.0

        user_data = user_doc.to_dict() or {}
        current_bal = float(user_data.get("balance", 0.0))
        current_ad_bal = float(user_data.get("ad_balance", 0.0))

        if current_bal < amount:
            return False, "رصيدك الأساسي غير كافٍ!", current_bal, current_ad_bal

        new_bal = round(current_bal - amount, 2)
        new_ad_bal = round(current_ad_bal + amount, 2)

        user_ref.update({
            "balance": new_bal,
            "ad_balance": new_ad_bal
        })

        return True, "تم التحويل بنجاح!", new_bal, new_ad_bal
    except Exception as e:
        print(f"❌ Error converting balance: {e}")
        return False, f"حدث خطأ: {e}", 0.0, 0.0

def apply_package_to_user(tg_id, added_storage=0.0, added_balance=0.0, added_hourly_rate=0.0):
    try:
        if not tg_id: return False, "معرف غير صالح"
        user_ref = db.collection('users').document(str(tg_id))
        doc = user_ref.get()
        if not doc.exists:
            return False, "المستخدم غير موجود"

        user_data = doc.to_dict() or {}
        stg_lvl = str(user_data.get("storage_level", 0))
        settings = get_game_settings()
        stg_cfg = settings.get("storage_config", {})
        
        base_cap = 100.0
        if stg_lvl in stg_cfg and isinstance(stg_cfg[stg_lvl], dict):
            base_cap = float(stg_cfg[stg_lvl].get("capacity", 100.0))

        current_extra = float(user_data.get("extra_storage", 0.0))
        new_extra = current_extra + float(added_storage)
        new_max_cap = round(base_cap + new_extra, 2)

        updates = {
            "extra_storage": new_extra,
            "max_cap": new_max_cap
        }
        if added_balance > 0:
            updates["balance"] = firestore.Increment(float(added_balance))
        if added_hourly_rate > 0:
            updates["hourly_rate"] = firestore.Increment(float(added_hourly_rate))

        user_ref.update(updates)
        return True, f"تمت إضافة الباقة بنجاح! السعة الجديدة: {new_max_cap}"
    except Exception as e:
        print(f"❌ Error applying package: {e}")
        return False, f"حدث خطأ: {e}"

def add_extra_storage(tg_id, extra_amount):
    return apply_package_to_user(tg_id, added_storage=extra_amount)

def update_user(tg_id, update_data):
    try:
        if not tg_id or not isinstance(update_data, dict): return False
        db.collection('users').document(str(tg_id)).update(update_data)
        return True
    except Exception as e:
        print(f"❌ Error updating user {tg_id}: {e}")
        return False

def update_user_storage_level(tg_id, target_level=None):
    try:
        if not tg_id: return False, "معرف المستخدم غير صحيح", 0, 0
        tg_id_str = str(tg_id)
        user_ref = db.collection('users').document(tg_id_str)
        user_doc = user_ref.get()
        
        if not user_doc.exists:
            return False, "المستخدم غير موجود", 0, 0

        settings = get_game_settings()
        storage_cfg = settings.get("storage_config", {})

        user_data = user_doc.to_dict() or {}
        current_level = int(user_data.get("storage_level", 0))
        current_balance = float(user_data.get("balance", 0.0))
        extra_cap = float(user_data.get("extra_storage", 0.0))

        next_level = int(target_level) if target_level is not None else current_level + 1

        if target_level is None and next_level <= current_level:
            return False, "أنت بالفعل في هذا المستوى أو مستوى أعلى!", user_data.get("max_cap", 100.0), current_balance

        next_cfg = storage_cfg.get(str(next_level)) or storage_cfg.get(next_level)
        if not next_cfg:
            return False, "لقد وصلت إلى الحد الأقصى لمستويات المخزن!", user_data.get("max_cap", 100.0), current_balance

        price = float(next_cfg.get("price", 0))

        if target_level is None and current_balance < price:
            return False, "رصيدك غير كافٍ لإجراء الترقية!", user_data.get("max_cap", 100.0), current_balance

        base_next_cap = float(next_cfg.get("capacity", 100.0))
        new_total_max_cap = round(base_next_cap + extra_cap, 2)
        update_payload = {"storage_level": next_level, "max_cap": new_total_max_cap}

        if target_level is None:
            new_balance = round(current_balance - price, 2)
            update_payload["balance"] = new_balance

        user_ref.update(update_payload)
        return True, "تمت الترقية بنجاح!", new_total_max_cap, update_payload.get("balance", current_balance)
    except Exception as e:
        print(f"❌ Error updating storage level for {tg_id}: {e}")
        return False, f"حدث خطأ: {e}", 0, 0

# ==================== Leaderboard & Extended Game Functions ====================

def get_leaderboard(limit=10):
    global _LEADERBOARD_CACHE, _LEADERBOARD_CACHE_TIME
    now = time.time()
    if _LEADERBOARD_CACHE is not None and (now - _LEADERBOARD_CACHE_TIME) < LEADERBOARD_CACHE_TTL:
        return _LEADERBOARD_CACHE

    try:
        if not db: initialize_firebase()
        users_ref = db.collection('users').order_by('balance', direction=firestore.Query.DESCENDING).limit(limit)
        docs = users_ref.stream()

        leaderboard = []
        for i, doc in enumerate(docs, start=1):
            d = doc.to_dict() or {}
            leaderboard.append({
                "rank": i,
                "tg_id": str(d.get("tg_id", doc.id)),
                "first_name": d.get("first_name", "صديقي"),
                "balance": float(d.get("balance", 0.0)),
                "hourly_rate": float(d.get("hourly_rate", 0.0))
            })

        _LEADERBOARD_CACHE = leaderboard
        _LEADERBOARD_CACHE_TIME = now
        return leaderboard
    except Exception as e:
        print(f"❌ Error fetching leaderboard: {e}")
        return _LEADERBOARD_CACHE or []

def claim_daily_reward(tg_id):
    try:
        if not tg_id: return False, "معرف غير صالح", 0.0, 0
        user_data = get_user(tg_id)
        if not user_data: return False, "المستخدم غير موجود", 0.0, 0

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        last_claim_date = user_data.get("last_daily_claim_date")

        if last_claim_date == today_str:
            return False, "لقد استلمت المكافأة اليومية بالفعل اليوم!", user_data.get("balance", 0.0), user_data.get("daily_streak", 0)

        current_streak = int(user_data.get("daily_streak", 0))
        
        # التأكد مما إذا كان الاستلام في اليوم التالي متتالياً أو انقطع
        if last_claim_date:
            last_dt = datetime.strptime(last_claim_date, "%Y-%m-%d")
            today_dt = datetime.strptime(today_str, "%Y-%m-%d")
            if (today_dt - last_dt).days == 1:
                current_streak += 1
            else:
                current_streak = 1
        else:
            current_streak = 1

        if current_streak > 30:
            current_streak = 1

        settings = get_game_settings()
        rewards_map = settings.get("daily_rewards", {})
        reward_amount = float(rewards_map.get(f"day_{current_streak}", 100))

        new_balance = round(float(user_data.get("balance", 0.0)) + reward_amount, 2)

        update_user(tg_id, {
            "balance": new_balance,
            "daily_streak": current_streak,
            "last_daily_claim_date": today_str
        })

        return True, f"تم استلام مكافأة اليوم {current_streak} بنجاح (+{reward_amount} ZN)!", new_balance, current_streak
    except Exception as e:
        print(f"❌ Error claiming daily reward for {tg_id}: {e}")
        return False, f"حدث خطأ: {e}", 0.0, 0

def claim_mining_farm(tg_id):
    try:
        if not tg_id: return False, "معرف غير صالح", 0.0, 0.0
        user_data = get_user(tg_id)
        if not user_data: return False, "المستخدم غير موجود", 0.0, 0.0

        hourly_rate = float(user_data.get("hourly_rate", 0.0))
        if hourly_rate <= 0:
            return False, "عدل سرعة التعدين أولاً لتتمكن من الجمع!", float(user_data.get("balance", 0.0)), 0.0

        last_claim_str = user_data.get("last_claim_time")
        now_dt = datetime.now(timezone.utc)

        if isinstance(last_claim_str, str):
            try:
                last_claim_dt = datetime.fromisoformat(last_claim_str.replace('Z', '+00:00'))
            except Exception:
                last_claim_dt = now_dt
        else:
            last_claim_dt = now_dt

        elapsed_hours = (now_dt - last_claim_dt).total_seconds() / 3600.0
        if elapsed_hours < (1 / 60.0): # أقل من دقيقة
            return False, "لا يوجد رصيد قابل للجمع بعد!", float(user_data.get("balance", 0.0)), 0.0

        produced = elapsed_hours * hourly_rate
        max_cap = float(user_data.get("max_cap", 100.0))

        if produced > max_cap:
            produced = max_cap

        produced = round(produced, 2)
        new_balance = round(float(user_data.get("balance", 0.0)) + produced, 2)

        update_user(tg_id, {
            "balance": new_balance,
            "last_claim_time": now_dt.isoformat()
        })

        return True, f"تم جمع {produced} ZN بنجاح!", new_balance, produced
    except Exception as e:
        print(f"❌ Error claiming mining farm for {tg_id}: {e}")
        return False, f"حدث خطأ: {e}", 0.0, 0.0

def upgrade_mining_card(tg_id, card_id):
    try:
        if not tg_id or not card_id: return False, "بيانات غير صالحة", 0.0, 0.0
        tg_id_str = str(tg_id)
        card_id_str = str(card_id)

        user_data = get_user(tg_id_str)
        if not user_data: return False, "المستخدم غير موجود", 0.0, 0.0

        settings = get_game_settings()
        mining_cfg = settings.get("mining_config", {})

        card_cfg = mining_cfg.get(card_id_str)
        if not card_cfg: return False, "كرت التعدين غير موجود", 0.0, 0.0

        upgrades = user_data.get("upgrades", {}) or {}
        current_card_lvl = int(upgrades.get(card_id_str, 0))
        max_lvl = int(card_cfg.get("max", 10))

        if current_card_lvl >= max_lvl:
            return False, "وصلت للحد الأقصى لمستوى هذا الكرت!", float(user_data.get("balance", 0.0)), float(user_data.get("hourly_rate", 0.0))

        base_cost = float(card_cfg.get("base_cost", card_cfg.get("price", 3500.0)))
        cost = base_cost * (1.5 ** current_card_lvl)
        cost = round(cost, 2)

        current_balance = float(user_data.get("balance", 0.0))
        if current_balance < cost:
            return False, f"رصيدك غير كافٍ! سعر الترقية {cost} ZN", current_balance, float(user_data.get("hourly_rate", 0.0))

        rate_bonus = float(card_cfg.get("rate_bonus", 5.0))

        new_balance = round(current_balance - cost, 2)
        new_hourly_rate = round(float(user_data.get("hourly_rate", 0.0)) + rate_bonus, 2)

        upgrades[card_id_str] = current_card_lvl + 1

        update_user(tg_id_str, {
            "balance": new_balance,
            "hourly_rate": new_hourly_rate,
            "upgrades": upgrades
        })

        return True, "تم ترقية كرت التعدين بنجاح!", new_balance, new_hourly_rate
    except Exception as e:
        print(f"❌ Error upgrading mining card {card_id} for {tg_id}: {e}")
        return False, f"حدث خطأ: {e}", 0.0, 0.0

def claim_referral_earnings(tg_id):
    try:
        if not tg_id: return False, "معرف غير صالح", 0.0
        user_data = get_user(tg_id)
        if not user_data: return False, "المستخدم غير موجود", 0.0

        pending = float(user_data.get("pending_ref_earnings", 0.0))
        if pending <= 0:
            return False, "لا توجد أرباح إحالات معلقة لجمعها!", float(user_data.get("balance", 0.0))

        current_bal = float(user_data.get("balance", 0.0))
        total_ref = float(user_data.get("total_ref_earnings", 0.0))

        new_bal = round(current_bal + pending, 2)
        new_total_ref = round(total_ref + pending, 2)

        update_user(tg_id, {
            "balance": new_bal,
            "pending_ref_earnings": 0.0,
            "total_ref_earnings": new_total_ref
        })

        return True, f"تم جمع أرباح الإحالة (+{pending} ZN) بنجاح!", new_bal
    except Exception as e:
        print(f"❌ Error claiming referral earnings for {tg_id}: {e}")
        return False, f"حدث خطأ: {e}", 0.0

def get_user_friends(tg_id, limit=50):
    try:
        if not db or not tg_id: return []
        friends_ref = db.collection('users').document(str(tg_id)).collection('friends').limit(limit)
        docs = friends_ref.stream()

        friends = []
        for doc in docs:
            d = doc.to_dict() or {}
            friends.append({
                "tg_id": str(d.get("tg_id", doc.id)),
                "first_name": d.get("first_name", "صديقي"),
                "earned_from_him": float(d.get("earned_from_him", 0.0))
            })

        return friends
    except Exception as e:
        print(f"❌ Error getting friends list for {tg_id}: {e}")
        return []

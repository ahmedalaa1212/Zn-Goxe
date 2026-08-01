# database.py
import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

db = None

def ensure_game_settings_exist():
    """دالة الفحص والتحديث التلقائي لكافة إعدادات اللعبة في Firestore حسب الخطة الاقتصادية"""
    global db
    if not db:
        return
    try:
        settings_ref = db.collection('config').document('game_settings')

        # 1. مكافآت الـ 30 يوم الدقيقة (إجمالي 20,000 ZN)
        exact_daily_rewards = {
            "day_1": 100,   "day_2": 150,   "day_3": 200,   "day_4": 250,   "day_5": 300,
            "day_6": 350,   "day_7": 400,   "day_8": 450,   "day_9": 500,   "day_10": 550,
            "day_11": 600,  "day_12": 600,  "day_13": 650,  "day_14": 650,  "day_15": 700,
            "day_16": 700,  "day_17": 750,  "day_18": 750,  "day_19": 800,  "day_20": 800,
            "day_21": 850,  "day_22": 850,  "day_23": 900,  "day_24": 900,  "day_25": 950,
            "day_26": 950,  "day_27": 1000, "day_28": 1000, "day_29": 1100, "day_30": 1250
        }

        # 2. ترقيات سرعة التعدين (9 مستويات - حد أقصى 10 شراء لكل مستوى)
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

        # 3. سعات وأسعار المخازن (المستوى الافتراضي + 10 مستويات)
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

        # 4. إعدادات نظام الأصدقاء والإحالة الديناميكية
        exact_friends_config = {
            "direct_reward_inviter": 2500,    # مكافأة الداعي المباشرة عند انضمام صديق
            "direct_reward_invitee": 1000,    # مكافأة الصديق الجديد فور تسجيله
            "commission_percent": 10,         # نسبة الربح المستمر من تعدين الصديق (%)
            "claim_fee_percent": 1.5,         # رسوم سحب أرباح الإحالة (%)
            "min_upgrades_for_task": 3,       # الحد الأدنى للترقيات لاحتساب الصديق مؤهلاً للمهام
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

        # جلب الإعدادات الحالية لعدم مسح تعديلاتك في الفايرستور إذا كانت موجودة
        doc = settings_ref.get()
        current_data = doc.to_dict() or {} if doc.exists else {}

        update_payload = {
            "daily_rewards": current_data.get("daily_rewards", exact_daily_rewards),
            "speed_config": current_data.get("speed_config", exact_speed_config),
            "storage_config": current_data.get("storage_config", exact_storage_config),
            "daily_ad_boost_rate": current_data.get("daily_ad_boost_rate", 2),
            "friends_config": current_data.get("friends_config", exact_friends_config)
        }

        settings_ref.set(update_payload, merge=True)
        print("✅ تم فحص وتحديث إعدادات اللعبة و system الأصدقاء في Firestore بنجاح!")

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
    try:
        doc = db.collection('config').document('game_settings').get()
        if doc.exists:
            return doc.to_dict() or {}
        return {}
    except Exception as e:
        print(f"❌ Error getting game settings: {e}")
        return {}

def is_user_banned(tg_id):
    try:
        if not tg_id: return False
        doc = db.collection('users').document(str(tg_id)).get()
        return bool(doc.to_dict().get('banned', False)) if doc.exists else False
    except Exception as e:
        print(f"❌ Error checking ban status for {tg_id}: {e}")
        return False

def init_user(tg_id, ref_id=None, first_name="صديقي"):
    try:
        if not tg_id: return False
            
        tg_id_str = str(tg_id)
        user_ref = db.collection('users').document(tg_id_str)
        user_doc = user_ref.get()
        
        is_new_referral = False
        
        if not user_doc.exists:
            valid_ref_id = str(ref_id) if ref_id and str(ref_id) != tg_id_str else None
            
            # جلب إعدادات المكافآت من الفايرستور
            settings = get_game_settings()
            f_config = settings.get('friends_config', {})
            inviter_bonus = float(f_config.get('direct_reward_inviter', 2500))
            invitee_bonus = float(f_config.get('direct_reward_invitee', 1000))

            initial_balance = invitee_bonus if valid_ref_id else 0.0

            new_user_data = {
                "tg_id": tg_id_str,
                "first_name": first_name,
                "balance": initial_balance,
                "ad_balance": 0.0,
                "usd_balance": 0.0,
                "hourly_rate": 0.0,
                "storage_level": 0,
                "max_cap": 200.0,
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
                    
                    # تحديث عدد الأصدقاء وإضافة مكافأة الداعي المباشرة للرصيد الأساسي (balance) وليس الأرباح المعلقة
                    update_payload = {
                        "invited_friends_count": firestore.Increment(1)
                    }
                    if inviter_bonus > 0:
                        update_payload["balance"] = firestore.Increment(inviter_bonus)

                    referrer_ref.update(update_payload)
                    
                    # إضافة الصديق للقائمة وتبدأ أرباح التعدين منه بـ 0.0
                    referrer_ref.collection('friends').document(tg_id_str).set({
                        "tg_id": tg_id_str,
                        "first_name": first_name,
                        "earned_from_him": 0.0,
                        "joined_at": firestore.SERVER_TIMESTAMP
                    })
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
            data = doc.to_dict()
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
    """
    تُستدعى حصرياً عند ضغط الصديق على زر تجميع المزرعة (Claim Farm).
    تحسب نسبة العمولة (10%) من الكمية المجمعة من التعدين وتضيفها إلى الأرباح المعلقة والسجل.
    """
    try:
        if not referrer_id or not amount or float(amount) <= 0: return False
            
        ref_str = str(referrer_id)
        friend_str = str(friend_id)
        
        # جلب نسبة العمولة ديناميكياً من الفايرستور (الافتراضي 10%)
        settings = get_game_settings()
        f_config = settings.get('friends_config', {})
        commission_percent = float(f_config.get('commission_percent', 10)) / 100.0

        ref_amount = float(amount) * commission_percent
        
        # إضافة العمولة للأرباح المعلقة الخاصة بالداعي
        db.collection('users').document(ref_str).update({
            "pending_ref_earnings": firestore.Increment(ref_amount)
        })
        
        # تحديث خانة المجمع منه داخل سجل الأصدقاء
        friend_ref = db.collection('users').document(ref_str).collection('friends').document(friend_str)
        if friend_ref.get().exists:
            friend_ref.update({"earned_from_him": firestore.Increment(ref_amount)})
        else:
            friend_ref.set({
                "tg_id": friend_str,
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
            item = doc.to_dict()
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
        db.collection('users').document(str(tg_id)).update({"banned": bool(status)})
        return True
    except Exception as e:
        print(f"❌ Error changing ban status for {tg_id}: {e}")
        return False

def get_top_users(limit=50):
    try:
        users_ref = db.collection('users').order_by('balance', direction=firestore.Query.DESCENDING).limit(limit)
        docs = users_ref.stream()
        leaderboard = []
        for doc in docs:
            data = doc.to_dict()
            leaderboard.append({
                "tg_id": doc.id,
                "first_name": data.get("first_name", "لاعب"),
                "balance": data.get("balance", 0.0),
                "hourly_rate": data.get("hourly_rate", 0.0)
            })
        return leaderboard
    except Exception as e:
        print(f"❌ Error getting leaderboard: {e}")
        return []

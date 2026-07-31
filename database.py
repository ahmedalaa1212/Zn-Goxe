import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

db = None

def ensure_game_settings_exist():


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
            "8": {"capacity": 200000, "price": 2200000},
            "9": {"capacity": 450000, "price": 5000000},
            "10": {"capacity": 1000000, "price": 12000000}
        }

        # تحديث المستند في الفايرستور وإعادة كتابة الخرائط بالبيانات الصحيحة
        settings_ref.set({
            "daily_rewards": exact_daily_rewards,
            "speed_config": exact_speed_config,
            "storage_config": exact_storage_config,
            "daily_ad_boost_rate": 2  # زيادة التعدين الدائمة عند مشاهدة إعلان مونيتاج (+2 ZN/ساعة)
        }, merge=True)

        print("✅ تم تحديث بيانات game_settings في Firestore بالقيم الاقتصادية الصحيحة!")

    except Exception as e:
        print(f"❌ خطأ أثناء تحديث إعدادات اللعبة تلقائياً: {e}")

            # لو المستند غير موجود أصلاً يتم إنشاؤه بالكامل
            settings_ref.set({
                "speed_config": default_speed_config,
                "daily_rewards": default_daily_rewards
            })
            print("✅ تم إنشاء game_settings والخرائط التلقائية بنجاح في Firestore!")
        else:
            # لو المستند موجود، يتم فحص الخرائط الناقصة فقط واستكمالها
            data = doc_snap.to_dict() or {}
            updates = {}

            if "speed_config" not in data:
                updates["speed_config"] = default_speed_config
            if "daily_rewards" not in data:
                updates["daily_rewards"] = default_daily_rewards

            if updates:
                settings_ref.set(updates, merge=True)
                print("✅ تم استكمال الخرائط الناقصة في Firestore تلقائياً!")
    except Exception as e:
        print(f"❌ خطأ أثناء التأكد من إعدادات اللعبة تلقائياً: {e}")

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

# تشغيل التهيئة وفحص الخرائط فور استدعاء الملف
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
            
            new_user_data = {
                "tg_id": tg_id_str,
                "first_name": first_name,
                "balance": 0.0,
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
                    referrer_ref.update({"invited_friends_count": firestore.Increment(1)})
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
    try:
        if not referrer_id or not amount or float(amount) <= 0: return False
            
        ref_str = str(referrer_id)
        friend_str = str(friend_id)
        ref_amount = float(amount) * 0.10
        
        db.collection('users').document(ref_str).update({
            "pending_ref_earnings": firestore.Increment(ref_amount)
        })
        
        friend_ref = db.collection('users').document(ref_str).collection('friends').document(friend_str)
        if friend_ref.get().exists:
            friend_ref.update({"earned_from_him": firestore.Increment(ref_amount)})
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

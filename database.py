import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

db = None

# 1. القيم الافتراضية للنظام (المكافآت اليومية 30 يوم)
DEFAULT_GAME_SETTINGS = {
    "daily_rewards": [
        100, 150, 200, 250, 300, 350, 400, 450, 500, 550,
        600, 600, 650, 650, 700, 700, 750, 750, 800, 800,
        850, 850, 900, 900, 950, 950, 1000, 1000, 1100, 1250
    ]
}

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

# 2. دالة التأكد من وجود الإعدادات الافتراضية وإنشائها إذا كانت محذوفة
def ensure_default_configs():
    try:
        config_ref = db.collection('config').document('game_settings')
        doc = config_ref.get()
        if not doc.exists:
            config_ref.set(DEFAULT_GAME_SETTINGS)
            print("⚙️ تم إنشاء مستند config/game_settings تلقائياً بالقيم الافتراضية.")
        else:
            print("✅ مستند إعدادات اللعبة موجود في قاعدة البيانات.")
    except Exception as e:
        print(f"❌ خطأ أثناء التأكد من وجود الإعدادات: {e}")

# تهيئة قاعدة البيانات والتأكد من وجود الجداول فور التشغيل
try:
    db = initialize_firebase()
    ensure_default_configs()
except Exception as e:
    print(f"⚠️ تنبيه أثناء تهيئة DB تلقائياً: {e}")

# ----------------------------------------------------
# 3. دوال لوحة التحكم وبوت الأدمن للقراءة والتعديل
# ----------------------------------------------------

def get_game_settings():
    """جلب إعدادات اللعبة للبوت أو الأدمن"""
    try:
        doc = db.collection('config').document('game_settings').get()
        if doc.exists:
            return doc.to_dict()
        else:
            ensure_default_configs()
            return DEFAULT_GAME_SETTINGS
    except Exception as e:
        print(f"❌ Error getting game settings: {e}")
        return DEFAULT_GAME_SETTINGS

def update_game_settings(new_settings):
    """تعديل إعدادات اللعبة من بوت الأدمن"""
    try:
        if not isinstance(new_settings, dict): return False
        db.collection('config').document('game_settings').set(new_settings, merge=True)
        print("✅ تم تحديث إعدادات اللعبة بنجاح من الأدمن!")
        return True
    except Exception as e:
        print(f"❌ Error updating game settings: {e}")
        return False

# ----------------------------------------------------
# باقي دوال المستخدمين والمعاملات كما هي
# ----------------------------------------------------

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

def create_transaction(tg_id, tx_type, amount_usd, wallet_address=None, status="pending"):
    try:
        if not tg_id: return False
        
        tx_data = {
            "tg_id": str(tg_id),
            "type": tx_type, 
            "amount_usd": float(amount_usd),
            "wallet_address": wallet_address,
            "status": status,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        
        db.collection('transactions').add(tx_data)
        return True
    except Exception as e:
        print(f"❌ Error creating transaction: {e}")
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

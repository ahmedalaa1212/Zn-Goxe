import os
import json
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================================
# 1. تهيئة فايربيس (Firebase Initialization)
# ==========================================
db = None

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
                print("✅ تم الاتصال بـ Firebase عبر متغيرات البيئة (Railway Production).")
            else:
                if os.path.exists("firebase-adminsdk.json"):
                    cred = credentials.Certificate("firebase-adminsdk.json")
                    print("⚠️ تم الاتصال بـ Firebase عبر الملف المحلي (Development).")
                else:
                    raise FileNotFoundError("لم يتم العثور على بيانات اعتماد Firebase في السيرفر أو الملف المحلي!")
            
            firebase_admin.initialize_app(cred)
            print("✅ Firebase Initialized Successfully!")
        except Exception as e:
            print(f"❌ Critical Firebase Initialization Error: {e}")
            raise e
            
    if db is None:
        db = firestore.client()
    return db

# تشغيل التهيئة عند استدعاء الملف
try:
    db = initialize_firebase()
except Exception as e:
    print(f"⚠️ تنبيه أثناء تهيئة DB تلقائياً: {e}")

# ==========================================
# 2. وظائف معالجة المستخدمين (User Operations)
# ==========================================
def is_user_banned(tg_id):
    """فحص حالة حظر المستخدم مباشرة من قاعدة البيانات"""
    try:
        if not tg_id: 
            return False
        tg_id_str = str(tg_id)
        doc = db.collection('users').document(tg_id_str).get()
        if doc.exists:
            return bool(doc.to_dict().get('banned', False))
        return False
    except Exception as e:
        print(f"❌ Error checking ban status for {tg_id}: {e}")
        return False

def init_user(tg_id, ref_id=None, first_name="صديقي"):
    """تهيئة بيانات اللاعب الجديد وتحديث القديم وتجهيز نظام الإحالة بالكامل"""
    try:
        if not tg_id:
            return False
            
        tg_id_str = str(tg_id)
        user_ref = db.collection('users').document(tg_id_str)
        user_doc = user_ref.get()
        
        is_new_referral = False
        
        if not user_doc.exists:
            valid_ref_id = str(ref_id) if ref_id and str(ref_id) != tg_id_str else None
            
            new_user_data = {
                "tg_id": tg_id_str,
                "first_name": first_name,
                "balance": 0.0,                  # نقاط التعدين / العملة الداخلية
                "ad_balance": 0.0,               # رصيد محفظة الإعلانات
                "usd_balance": 0.0,              # رصيد USD
                "hourly_rate": 0.0,              # معدل الإنتاج بالساعة
                "mining_level": 1,               # مستوى المزرعة
                "level_1_upgrades": 0,           # ترقيات المستوى
                "banned": False,                 # حالة الحظر
                "wallet_address": None,          # عنوان محفظة TON
                "referred_by": valid_ref_id,      # معرف الداعي
                "invited_friends_count": 0,      # عدد الأصدقاء المدعوين
                "pending_ref_earnings": 0.0,     # الأرباح المعلقة من الأصدقاء (10%)
                "total_ref_earnings": 0.0,       # إجمالي ما تم جمعه من الأصدقاء
                "claimed_ref_tasks": [],         # جوائز الإحالات المستلمة
                "claimed_tasks": [],             # المهام اليومية المكتملة
                "last_farm_claim": None,         # آخر وقت استلام للتعدين
                "last_active": firestore.SERVER_TIMESTAMP,
                "joined_at": firestore.SERVER_TIMESTAMP
            }
            user_ref.set(new_user_data)
            
            if valid_ref_id:
                referrer_ref = db.collection('users').document(valid_ref_id)
                referrer_doc = referrer_ref.get()
                
                if referrer_doc.exists:
                    is_new_referral = True
                    referrer_ref.update({
                        "invited_friends_count": firestore.Increment(1)
                    })
                    
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
    """جلب كافة بيانات المستخدم كـ Dict مع دعم المعرف النصي والعددي"""
    try:
        if not tg_id:
            return None
        tg_id_str = str(tg_id)
        doc = db.collection('users').document(tg_id_str).get()
        if doc.exists:
            data = doc.to_dict()
            data['id'] = doc.id
            return data
        return None
    except Exception as e:
        print(f"❌ Error getting user {tg_id}: {e}")
        return None

def update_user(tg_id, update_data):
    """تحديث حقول معينة للمستخدم بأمان"""
    try:
        if not tg_id or not isinstance(update_data, dict):
            return False
        db.collection('users').document(str(tg_id)).update(update_data)
        return True
    except Exception as e:
        print(f"❌ Error updating user {tg_id}: {e}")
        return False

# ==========================================
# 3. الوظائف المالية والإحالات (Financial Helpers)
# ==========================================
def update_user_balance(tg_id, amount, balance_type="balance"):
    """تحديث رصيد المستخدم بشكل آمن (إضافة أو خصم)"""
    try:
        if not tg_id:
            return False
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
    """إضافة نسبة 10% أرباح للداعي عند تعدين الصديق"""
    try:
        if not referrer_id or not amount or float(amount) <= 0:
            return False
            
        ref_str = str(referrer_id)
        friend_str = str(friend_id)
        ref_amount = float(amount) * 0.10
        
        db.collection('users').document(ref_str).update({
            "pending_ref_earnings": firestore.Increment(ref_amount)
        })
        
        friend_ref = db.collection('users').document(ref_str).collection('friends').document(friend_str)
        if friend_ref.get().exists:
            friend_ref.update({
                "earned_from_him": firestore.Increment(ref_amount)
            })
        return True
    except Exception as e:
        print(f"❌ Error adding referral earnings: {e}")
        return False

# ==========================================
# 4. وظائف السحوبات والسجلات (Transactions & Withdrawals)
# ==========================================
def create_transaction(tg_id, tx_type, amount_usd, wallet_address=None, status="pending"):
    """تسجيل عملية جديدة في قاعدة البيانات"""
    try:
        if not tg_id:
            return False
        
        tx_data = {
            "tg_id": str(tg_id),
            "type": tx_type,              # 'withdraw', 'deposit', 'convert'
            "amount_usd": float(amount_usd),
            "wallet_address": wallet_address,
            "status": status,            # 'pending', 'completed', 'rejected'
            "created_at": firestore.SERVER_TIMESTAMP
        }
        
        db.collection('transactions').add(tx_data)
        return True
    except Exception as e:
        print(f"❌ Error creating transaction: {e}")
        return False

def get_user_transactions(tg_id, limit=30):
    """جلب سجل عمليات المستخدم مرتبة من الأحدث للأقدم"""
    try:
        if not tg_id:
            return []
        
        user_ids = [str(tg_id)]
        try:
            num_id = int(tg_id)
            if num_id not in user_ids:
                user_ids.append(num_id)
        except (ValueError, TypeError):
            pass

        docs = db.collection('transactions')\
            .where('tg_id', 'in', user_ids)\
            .limit(limit)\
            .stream()
        
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

# ==========================================
# 5. وظائف الإدارة واللوحة (Admin Helpers)
# ==========================================
def ban_user(tg_id, status=True):
    """تغيير حالة حظر المستخدم"""
    try:
        if not tg_id:
            return False
        db.collection('users').document(str(tg_id)).update({"banned": bool(status)})
        return True
    except Exception as e:
        print(f"❌ Error changing ban status for {tg_id}: {e}")
        return False

def get_top_users(limit=50):
    """جلب أعلى المستخدمين رصيداً للوحة الصدارة (Leaderboard)"""
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

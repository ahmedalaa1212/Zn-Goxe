import json
import os
import firebase_admin
from firebase_admin import credentials, firestore

# ==================== Firebase Core Engine ====================
db = None

def initialize_firebase():
    """تهيئة الاتصال بقاعدة بيانات Firebase Firestore بشكل آمن"""
    global db
    if not firebase_admin._apps:
        firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")
        try:
            if firebase_creds_json:
                try:
                    creds_dict = json.loads(firebase_creds_json)
                except Exception:
                    cleaned_json = firebase_creds_json.replace("\\n", "\n")
                    creds_dict = json.loads(cleaned_json)

                if isinstance(creds_dict, dict) and "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

                cred = credentials.Certificate(creds_dict)
            else:
                if os.path.exists("firebase-adminsdk.json"):
                    cred = credentials.Certificate("firebase-adminsdk.json")
                else:
                    raise FileNotFoundError("❌ لم يتم العثور على بيانات اعتماد Firebase (سواء متغير بيئي أو ملف محلي)!")

            firebase_admin.initialize_app(cred)
            print("✅ تم الاتصال بـ Firebase بنجاح!")
        except Exception as e:
            print(f"❌ خطأ حرِج أثناء تهيئة Firebase: {e}")
            raise e

    if db is None:
        db = firestore.client()
    return db


def get_db():
    """الحصول على كائن قاعدة البيانات Firestore مع ضمان التهيئة"""
    global db
    if db is None:
        db = initialize_firebase()
    return db


# ==================== Initial Auto Connection ====================
try:
    initialize_firebase()
except Exception as e:
    print(f"⚠️ تنبيه أثناء التهيئة التلقائية لـ Firebase: {e}")


# ==================== Core User Operations ====================

def get_user(telegram_id):
    """جلب بيانات المستخدم مباشرة من Firestore"""
    if not telegram_id:
        return None
    try:
        firestore_db = get_db()
        doc_ref = firestore_db.collection('users').document(str(telegram_id).strip())
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        print(f"❌ خطأ قراءة بيانات المستخدم {telegram_id}: {e}")
        return None


def init_user(telegram_id, ref_id=None, first_name="لاعب"):
    """إنشاء مستند المستخدم قسرياً في Firestore إن لم يكن موجوداً"""
    if not telegram_id:
        return {}
    try:
        firestore_db = get_db()
        user_id_str = str(telegram_id).strip()
        doc_ref = firestore_db.collection('users').document(user_id_str)
        doc = doc_ref.get()

        if not doc.exists:
            new_user_data = {
                'user_id': user_id_str,
                'telegram_id': user_id_str,
                'first_name': str(first_name or 'لاعب'),
                'balance': 0.0,
                'usd_balance': 0.0,
                'ref_by': str(ref_id).strip() if ref_id else None,
                'referrals_count': 0,
                'created_at': firestore.SERVER_TIMESTAMP,
                'last_withdraw_date': None,
                'withdraw_count': 0,
                'is_banned': False,
                'farm_level': 1,
                'storage_level': 1,
                'last_harvest': firestore.SERVER_TIMESTAMP
            }
            doc_ref.set(new_user_data, merge=True)
            print(f"✅ تم إنشاء مستند جديد للمستخدم {user_id_str} بنجاح في Firebase!")
            doc = doc_ref.get()

        return doc.to_dict() if doc.exists else {}
    except Exception as e:
        print(f"❌ خطأ أثناء إنشاء/تهيئة حساب المستخدم {telegram_id}: {e}")
        return {}


def is_user_banned(telegram_id):
    """التحقق من حالة حظر المستخدم"""
    user_data = get_user(telegram_id)
    if user_data:
        return user_data.get('is_banned', False)
    return False


def update_user(telegram_id, updates_dict):
    """تحديث بيانات مستند المستخدم"""
    if not telegram_id or not isinstance(updates_dict, dict):
        return False
    try:
        firestore_db = get_db()
        doc_ref = firestore_db.collection('users').document(str(telegram_id).strip())
        doc_ref.update(updates_dict)
        return True
    except Exception as e:
        print(f"❌ خطأ تحديث مستند المستخدم {telegram_id}: {e}")
        return False


# ==================== Sub-Modules Re-exports ====================

# 1. Admin Chat Module
try:
    from admin_chat.admin_chat_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل admin_chat_db: {e}")

# 2. Farm Module
try:
    from farm.farm_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل farm_db: {e}")

# 3. Friends Module
try:
    from friends.friends_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل friends_db: {e}")

# 4. Games Module
try:
    from games.games_db import *
    if 'init_all_games_db' in locals():
        init_all_games_db()
except Exception as e:
    print(f"⚠️ خطأ في تحميل games_db: {e}")

# 5. Settings Module
try:
    from settings.settings_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل settings_db: {e}")

# 6. Shop Module
try:
    from shop.shop_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل shop_db: {e}")

# 7. Super Admin Module
try:
    from super_admin.super_admin_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل super_admin_db: {e}")

# 8. Support Module
try:
    from support.support_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل support_db: {e}")

# 9. Tasks Module
try:
    from tasks.tasks_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل tasks_db: {e}")

# 10. Users Module
try:
    from users.users_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل users_db: {e}")

# 11. Wallet Module
try:
    from wallet.wallet_db import *
    from wallet.deposit.deposit_db import *
    from wallet.history.history_db import *
    from wallet.withdraw.withdraw_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل wallet_db وموديولاتها الفرعية: {e}")

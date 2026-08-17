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
                    # معالجة الـ Escape Characters في البيئات السحابية مثل Railway
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


# ==================== Sub-Modules Re-exports ====================
# ربط كافة موديولات الـ Database الفرعية من المجلدات الـ 11 وتتبع الأخطاء

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
    # تشغيل تهيئة جداول/قواعد بيانات كافة الألعاب عند الإقلاع
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

# 11. Wallet Module (يشمل الموديولات الفرعية: deposit_db, history_db, withdraw_db)
try:
    from wallet.wallet_db import *
    from wallet.deposit.deposit_db import *
    from wallet.history.history_db import *
    from wallet.withdraw.withdraw_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل wallet_db وموديولاتها الفرعية: {e}")

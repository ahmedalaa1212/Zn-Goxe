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
                    creds_dict = json.loads(firebase_creds_json.replace("\\n", "\n"))

                if isinstance(creds_dict, dict) and "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

                cred = credentials.Certificate(creds_dict)
            else:
                if os.path.exists("firebase-adminsdk.json"):
                    cred = credentials.Certificate("firebase-adminsdk.json")
                else:
                    raise FileNotFoundError("❌ لم يتم العثور على بيانات اعتماد Firebase!")

            firebase_admin.initialize_app(cred)
            print("✅ تم الاتصال بـ Firebase بنجاح!")
        except Exception as e:
            print(f"❌ خطأ حرِج أثناء تهيئة Firebase: {e}")
            raise e

    if db is None:
        db = firestore.client()
    return db


def get_db():
    """الحصول على كائن قاعدة البيانات Firestore"""
    global db
    if db is None:
        db = initialize_firebase()
    return db


# ==================== Initial Auto Connection ====================
try:
    initialize_firebase()
except Exception as e:
    print(f"⚠️ تنبيه أثناء التهيئة التلقائية: {e}")


# ==================== Sub-Modules Re-exports ====================
# ربط كافة موديولات الـ Database الفرعية من المجلدات الـ 11

# 1. Admin Chat Module
try:
    from admin_chat.admin_chat_db import *
except ImportError:
    pass

# 2. Farm Module
try:
    from farm.farm_db import *
except ImportError:
    pass

# 3. Friends Module
try:
    from friends.friends_db import *
except ImportError:
    pass

# 4. Games Module
try:
    from games.games_db import *
except ImportError:
    pass

# 5. Settings Module
try:
    from settings.settings_db import *
except ImportError:
    pass

# 6. Shop Module
try:
    from shop.shop_db import *
except ImportError:
    pass

# 7. Super Admin Module
try:
    from super_admin.super_admin_db import *
except ImportError:
    pass

# 8. Support Module
try:
    from support.support_db import *
except ImportError:
    pass

# 9. Tasks Module
try:
    from tasks.tasks_db import *
except ImportError:
    pass

# 10. Users Module
try:
    from users.users_db import *
except ImportError:
    pass

# 11. Wallet Module
try:
    from wallet.wallet_db import *
except ImportError:
    pass

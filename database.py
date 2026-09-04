import json
import os
from datetime import datetime
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


# ==================== Data Serialization Helper (حل مشكلة SERVER_TIMESTAMP و JSON 500) ====================

def sanitize_firestore_data(data):
    """
    تحويل كافة عناصر Firestore غير القابلة للترميز بـ JSON (مثل DatetimeWithNanoseconds أو SERVER_TIMESTAMP)
    إلى صيغ نصوص ISO 8601 لمنع أخطاء 500 Internal Server Error في Flask.
    """
    if data is None:
        return None
    if isinstance(data, dict):
        return {k: sanitize_firestore_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_firestore_data(v) for v in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    elif hasattr(data, 'isoformat'):  # يشمل DatetimeWithNanoseconds في Firestore
        return data.isoformat()
    elif hasattr(data, '__dict__'):
        return str(data)
    else:
        return data


# ==================== Core User Operations (ضمان إنشاء وقراءة المستخدم) ====================

def get_user(telegram_id):
    """جلب بيانات المستخدم مباشرة من Firestore مع تنظيف التواريخ لتوافق JSON"""
    if not telegram_id:
        return None
    try:
        firestore_db = get_db()
        user_id_str = str(telegram_id).strip()
        doc_ref = firestore_db.collection('users').document(user_id_str)
        doc = doc_ref.get()
        if doc.exists:
            return sanitize_firestore_data(doc.to_dict())
        return None
    except Exception as e:
        print(f"❌ خطأ قراءة بيانات المستخدم {telegram_id}: {e}")
        return None


def init_user(telegram_id, ref_id=None, first_name="لاعب"):
    """
    إنشاء مستند المستخدم قسرياً في Firestore إن لم يكن موجوداً ومعالجة نظام الإحالات
    مع تحويل كافة التواريخ إلى صيغ آمنة تمنع انهيار السيرفر 500 عند إرجاع JSON.
    """
    if not telegram_id:
        return {}
    try:
        firestore_db = get_db()
        user_id_str = str(telegram_id).strip()
        if not user_id_str or user_id_str in ("None", "null", ""):
            return {}

        doc_ref = firestore_db.collection('users').document(user_id_str)
        doc = doc_ref.get()

        if not doc.exists:
            clean_ref = str(ref_id).strip() if ref_id and str(ref_id).strip() not in (user_id_str, "None", "null", "") else None
            
            new_user_data = {
                'user_id': user_id_str,
                'telegram_id': user_id_str,
                'first_name': str(first_name or 'لاعب'),
                'balance': 0.0,
                'usd_balance': 0.0,
                'ref_by': clean_ref,
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
            
            # زيادة عداد الإحالات للمُحيل إن وجد
            if clean_ref:
                try:
                    ref_doc_ref = firestore_db.collection('users').document(clean_ref)
                    if ref_doc_ref.get().exists:
                        ref_doc_ref.update({
                            'referrals_count': firestore.Increment(1)
                        })
                except Exception as ref_err:
                    print(f"⚠️ خطأ تحديث عداد الإحالة للمُحيل {clean_ref}: {ref_err}")

            doc = doc_ref.get()

        user_dict = doc.to_dict() if doc.exists else {}
        return sanitize_firestore_data(user_dict)
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


# ==================== Atomic Transactions (منع التزامن والثغرات المالية) ====================

def atomic_update_balance(telegram_id, amount_change, is_usd=False):
    """
    تحديث رصيد المستخدم معاملاتيًا (Atomic Transaction) لمنع ثغرات Race Condition والتلاعب بالرصيد.
    """
    if not telegram_id:
        return False, "المعرف غير صالح"

    firestore_db = get_db()
    user_id_str = str(telegram_id).strip()
    doc_ref = firestore_db.collection('users').document(user_id_str)

    @firestore.transactional
    def update_in_transaction(transaction, doc_ref):
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            return False, "المستخدم غير موجود"
        
        user_data = snapshot.to_dict()
        field_name = 'usd_balance' if is_usd else 'balance'
        current_balance = float(user_data.get(field_name, 0.0))
        new_balance = current_balance + float(amount_change)

        if new_balance < 0:
            return False, "الرصيد غير كافٍ"

        transaction.update(doc_ref, {field_name: new_balance})
        return True, new_balance

    try:
        transaction = firestore_db.transaction()
        success, result = update_in_transaction(transaction, doc_ref)
        return success, result
    except Exception as e:
        print(f"❌ خطأ في معاملة تحديث الرصيد للمستخدم {telegram_id}: {e}")
        return False, str(e)


# ==================== Leaderboard System (نظام المتصدرين الموثق) ====================

def get_leaderboard_data(limit=50, user_id=None):
    """
    جلب قائمة أعلى الحسابات رصيداً وحساب ترتيب المستخدم الحالي بدقة وأمان.
    """
    try:
        firestore_db = get_db()
        users_ref = firestore_db.collection('users')
        query = users_ref.order_by('balance', direction=firestore.Query.DESCENDING).limit(limit)
        docs = query.stream()

        leaderboard = []
        rank = 1
        user_rank = None
        user_in_top = False

        target_user_id = str(user_id).strip() if user_id else None

        for doc in docs:
            data = doc.to_dict()
            u_id = str(data.get('user_id') or doc.id)
            user_entry = {
                'rank': rank,
                'user_id': u_id,
                'first_name': data.get('first_name', 'لاعب'),
                'balance': float(data.get('balance', 0.0)),
                'usd_balance': float(data.get('usd_balance', 0.0)),
                'farm_level': data.get('farm_level', 1)
            }
            leaderboard.append(user_entry)

            if target_user_id and u_id == target_user_id:
                user_rank = rank
                user_in_top = True

            rank += 1

        # إذا لم يكن المستخدم في أول Limit لاعب، نحسب ترتيبه بدقة
        if target_user_id and not user_in_top:
            target_doc = users_ref.document(target_user_id).get()
            if target_doc.exists:
                target_data = target_doc.to_dict()
                target_balance = float(target_data.get('balance', 0.0))
                higher_docs = users_ref.where('balance', '>', target_balance).stream()
                higher_count = sum(1 for _ in higher_docs)
                user_rank = higher_count + 1

        return {
            'success': True,
            'leaderboard': leaderboard,
            'my_rank': user_rank or "غير مصنف"
        }
    except Exception as e:
        print(f"❌ خطأ أثناء جلب قائمة المتصدرين: {e}")
        return {
            'success': False,
            'error': str(e),
            'leaderboard': [],
            'my_rank': "غير مصنف"
        }


# ==================== Sub-Modules Re-exports ====================

# 0. Admin Database Module (أكواد المكافآت والإدارة العامة)
try:
    from admin_database import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل admin_database: {e}")

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

# 11. Wallet Module (يشمل المحفظة والأنشطة الفرعية)
try:
    from wallet.wallet_db import *
    from wallet.deposit.deposit_db import *
    from wallet.history.history_db import *
    from wallet.withdraw.withdraw_db import *
    from wallet.exchange.exchange_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل wallet_db وموديولاتها الفرعية: {e}")

# 12. Offers, Leaderboard & Ads Modules
try:
    from offers.offers_db import *
except Exception:
    pass

try:
    from leaderboard.leaderboard_db import *
except Exception:
    pass

try:
    from ads.ads_db import *
except Exception:
    pass

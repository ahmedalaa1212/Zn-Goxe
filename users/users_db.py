import time
from datetime import datetime
from firebase_admin import firestore
import database

def _serialize_firestore_val(val):
    """دالة تحويل شاملة لمنع خطأ JSON crash مع تواريخ وكائنات الفايربيس"""
    if val is None:
        return ""
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    elif isinstance(val, datetime):
        return val.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(val, dict):
        return {str(k): _serialize_firestore_val(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_serialize_firestore_val(v) for v in val]
    elif isinstance(val, (int, float, bool, str)):
        return val
    else:
        return str(val)


def get_all_users_admin(limit=5000):
    """جلب كافة بيانات المستخدمين الحية من الفايربيس وتوحيد حقول الإحالات والتواريخ"""
    try:
        db = database.get_db()
        users_ref = db.collection("users").limit(limit)
        docs = users_ref.stream()

        users_list = []
        for doc in docs:
            d = doc.to_dict() or {}
            
            # 1. تحويل ونقل كافة الحقول الموجودة داخل المستند بدون استثناء
            user_data = {"document_id": str(doc.id)}
            for k, v in d.items():
                user_data[k] = _serialize_firestore_val(v)

            # 2. ضمان توحيد معيار معرف المستخدم والاسم
            user_data["tg_id"] = str(d.get("tg_id", d.get("user_id", d.get("id", doc.id))))
            user_data["first_name"] = d.get("first_name", d.get("name", "مستخدم"))

            # 3. استخراج وتوحيد عدد الإحالات الحقيقي بغض النظر عن طريقة حفظه في قاعدة البيانات
            invited_count = 0
            if "invited_friends_count" in d and d["invited_friends_count"] is not None:
                invited_count = d["invited_friends_count"]
            elif "referrals_count" in d and d["referrals_count"] is not None:
                invited_count = d["referrals_count"]
            elif "referral_count" in d and d["referral_count"] is not None:
                invited_count = d["referral_count"]
            elif "invited_count" in d and d["invited_count"] is not None:
                invited_count = d["invited_count"]
            elif isinstance(d.get("invited_friends"), list):
                invited_count = len(d.get("invited_friends"))
            elif isinstance(d.get("referrals"), list):
                invited_count = len(d.get("referrals"))
            
            try:
                user_data["invited_friends_count"] = int(invited_count)
            except Exception:
                user_data["invited_friends_count"] = 0

            # 4. توحيد واستخراج تاريخ الانضمام الحقيقي
            joined_at = (
                d.get("joined_at") or 
                d.get("joinDate") or 
                d.get("created_at") or 
                d.get("createdAt") or 
                d.get("timestamp") or 
                ""
            )
            user_data["joined_at"] = _serialize_firestore_val(joined_at)

            # 5. توحيد واستخراج حالة نشاط البوت
            bot_active = d.get("bot_active")
            if bot_active is None:
                bot_active = d.get("is_active", d.get("active", True))
            user_data["bot_active"] = bool(bot_active)

            # 6. قيم الإحصائيات التراكمية مع القيم الافتراضية
            user_data["ads_watched"] = int(d.get("ads_watched", d.get("ads_count", 0)) or 0)
            user_data["daily_streak"] = int(d.get("daily_streak", 0) or 0)
            user_data["daily_boost_rate"] = float(d.get("daily_boost_rate", 0) or 0)
            user_data["banned"] = bool(d.get("banned", False))
            
            users_list.append(user_data)
            
        return users_list
    except Exception as e:
        print(f"❌ Error fetching all users from Firebase: {e}")
        return []


def get_user(tg_id):
    """جلب بيانات مستخدم واحد بجميع حقوله"""
    try:
        if not tg_id:
            return None
        db = database.get_db()
        user_ref = db.collection("users").document(str(tg_id))
        doc = user_ref.get()
        if doc.exists:
            d = doc.to_dict() or {}
            d["document_id"] = str(doc.id)
            return {k: _serialize_firestore_val(v) for k, v in d.items()}
        return None
    except Exception as e:
        print(f"❌ Error getting user {tg_id}: {e}")
        return None


def is_user_banned(tg_id):
    """التحقق من حظر المستخدم"""
    try:
        u = get_user(tg_id)
        return bool(u.get("banned", False)) if u else False
    except Exception:
        return False

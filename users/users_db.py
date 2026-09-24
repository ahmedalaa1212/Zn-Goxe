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
    """جلب كافة بيانات المستخدمين من مستندات users بالكامل وحساب الإحالات الحقيقية"""
    try:
        db = database.get_db()
        users_ref = db.collection("users").limit(limit)
        docs = users_ref.stream()

        users_list = []
        for doc in docs:
            d = doc.to_dict() or {}
            
            # تجهيز قاموس البيانات الشامل للمستخدم
            user_data = {"document_id": str(doc.id)}
            
            # تحويل كل حقل موجود داخل الفايربيس تلقائياً
            for k, v in d.items():
                user_data[k] = _serialize_firestore_val(v)

            # ضمان وجود المعرفات الأساسية مع القيم الافتراضية
            user_data["tg_id"] = str(d.get("tg_id", doc.id))
            user_data["first_name"] = d.get("first_name", d.get("name", "مستخدم"))
            
            # حساب الإحالات الحقيقية بدقة من كافة الحقول المحتملة
            ref_count = 0
            if "invited_friends_count" in d and d["invited_friends_count"] is not None:
                try:
                    ref_count = int(d["invited_friends_count"])
                except Exception:
                    ref_count = 0
            elif "referrals_count" in d and d["referrals_count"] is not None:
                try:
                    ref_count = int(d["referrals_count"])
                except Exception:
                    ref_count = 0
            elif isinstance(d.get("invited_friends"), list):
                ref_count = len(d["invited_friends"])
            elif isinstance(d.get("referrals"), list):
                ref_count = len(d["referrals"])

            user_data["invited_friends_count"] = ref_count
            user_data["ads_watched"] = int(d.get("ads_watched", d.get("total_ads", 0)) or 0)
            user_data["daily_streak"] = int(d.get("daily_streak", 0) or 0)
            user_data["daily_boost_rate"] = float(d.get("daily_boost_rate", 0) or 0)
            
            # ضمان وجود تاريخ الانضمام
            user_data["joined_at"] = _serialize_firestore_val(
                d.get("joined_at") or d.get("joinDate") or d.get("created_at") or d.get("timestamp") or ""
            )
            
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

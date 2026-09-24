import time
from datetime import datetime
from firebase_admin import firestore
import database

def _serialize_firestore_val(val):
    """دالة تحويل شاملة لمنع خطأ JSON crash مع تواريخ وكائنات الفايربيس وتحويلها إلى صياغة ISO قياسية"""
    if val is None:
        return ""
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    elif isinstance(val, datetime):
        return val.strftime('%Y-%m-%dT%H:%M:%S')
    elif hasattr(val, 'to_datetime'): # كائنات الفايربيس DatetimeWithNanoseconds
        try:
            return val.to_datetime().strftime('%Y-%m-%dT%H:%M:%S')
        except Exception:
            return str(val)
    elif isinstance(val, dict):
        return {str(k): _serialize_firestore_val(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_serialize_firestore_val(v) for v in val]
    elif isinstance(val, (int, float, bool, str)):
        return val
    else:
        return str(val)


def get_all_users_admin(limit=5000):
    """جلب كافة بيانات المستخدمين من مستندات users وحساب الإحالات الحقيقية المباشرة في الوقت الفعلي"""
    try:
        db = database.get_db()
        users_ref = db.collection("users").limit(limit)
        docs = users_ref.stream()

        users_map = {}
        doc_id_to_tg_id = {}
        referrals_by_inviter = {}

        # 1. تجميع البيانات وتجهيز المعرفات والتواريخ
        for doc in docs:
            d = doc.to_dict() or {}
            doc_id = str(doc.id)
            
            user_data = {"document_id": doc_id}
            
            for k, v in d.items():
                user_data[k] = _serialize_firestore_val(v)

            tg_id = str(d.get("tg_id") or d.get("telegram_id") or doc_id)
            user_data["tg_id"] = tg_id
            user_data["first_name"] = str(d.get("first_name") or d.get("name") or "مستخدم")
            
            # ربط المعرفات لضمان اكتشاف الإحالات سواء استخدم الداعي document_id أو tg_id
            doc_id_to_tg_id[doc_id] = tg_id
            doc_id_to_tg_id[tg_id] = tg_id

            # توحيد تاريخ الانضمام من كافة المسميات المحتملة
            joined_at = (
                d.get("joined_at") or 
                d.get("joinDate") or 
                d.get("created_at") or 
                d.get("createdAt") or 
                d.get("registered_at") or 
                d.get("timestamp") or 
                d.get("last_active_at") or 
                ""
            )
            user_data["joined_at"] = _serialize_firestore_val(joined_at)

            # تحويل القيم الرقمية لضمان عدم وجود أخطاء نصوص
            try:
                user_data["invited_friends_count"] = int(d.get("invited_friends_count") or 0)
            except (ValueError, TypeError):
                user_data["invited_friends_count"] = 0

            try:
                user_data["ads_watched"] = int(d.get("ads_watched") or 0)
            except (ValueError, TypeError):
                user_data["ads_watched"] = 0

            try:
                user_data["daily_streak"] = int(d.get("daily_streak") or 0)
            except (ValueError, TypeError):
                user_data["daily_streak"] = 0

            try:
                user_data["daily_boost_rate"] = float(d.get("daily_boost_rate") or 0)
            except (ValueError, TypeError):
                user_data["daily_boost_rate"] = 0.0

            referred_by = str(d.get("referred_by") or "").strip()
            user_data["referred_by"] = referred_by

            users_map[tg_id] = user_data

        # 2. بناء قائمة الإحالات لكل داعي بكل دقة
        for tg_id, u_data in users_map.items():
            ref_by_raw = u_data.get("referred_by", "")
            if ref_by_raw and ref_by_raw != "None":
                inviter_tg_id = doc_id_to_tg_id.get(ref_by_raw, ref_by_raw)
                if inviter_tg_id not in referrals_by_inviter:
                    referrals_by_inviter[inviter_tg_id] = []
                referrals_by_inviter[inviter_tg_id].append({
                    "tg_id": tg_id,
                    "joined_at": u_data["joined_at"]
                })

        # 3. اعتماد وتحديث الإحالات المباشرة
        users_list = []
        for tg_id, u_data in users_map.items():
            refs_details = referrals_by_inviter.get(tg_id, [])
            actual_count = len(refs_details)
            
            # إرفاق تفاصيل الإحالات المباشرة لاستخدامها في الفلترة الزمنية
            u_data["referrals_list"] = refs_details
            u_data["invited_friends_count"] = max(u_data["invited_friends_count"], actual_count)
            
            users_list.append(u_data)

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

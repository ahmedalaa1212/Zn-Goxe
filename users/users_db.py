import time
from datetime import datetime
from firebase_admin import firestore
import database

_BAN_CACHE = {}
BAN_CACHE_TTL = 120

def _serialize_firestore_val(val):
    """دالة مساعدة لتحويل التواريخ وكائنات الفايربيس لنصوص قابلة للإرسال JSON"""
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    elif isinstance(val, datetime):
        return val.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(val, dict):
        return {k: _serialize_firestore_val(v) for k, v in val.items()}
    elif isinstance(val, list):
        return [_serialize_firestore_val(v) for v in val]
    return val


def is_user_banned(tg_id):
    """التحقق السريع من حالة حظر المستخدم باستخدام الكاش"""
    if not tg_id:
        return False
    tg_id_str = str(tg_id)
    now = time.time()

    if tg_id_str in _BAN_CACHE:
        is_banned, expire_time = _BAN_CACHE[tg_id_str]
        if now < expire_time:
            return is_banned

    try:
        db = database.get_db()
        doc = db.collection("users").document(tg_id_str).get()
        is_banned = (
            bool((doc.to_dict() or {}).get("banned", False)) if doc.exists else False
        )
        _BAN_CACHE[tg_id_str] = (is_banned, now + BAN_CACHE_TTL)
        return is_banned
    except Exception as e:
        print(f"❌ Error checking ban status: {e}")
        return False


def ban_user(tg_id, ban_status=True):
    """حظر أو إلغاء حظر مستخدم وتحديث الكاش فوراً"""
    try:
        if not tg_id:
            return False, "معرف مستخدم غير صالح"
        db = database.get_db()
        tg_id_str = str(tg_id)

        db.collection("users").document(tg_id_str).update(
            {"banned": bool(ban_status)}
        )
        _BAN_CACHE[tg_id_str] = (bool(ban_status), time.time() + BAN_CACHE_TTL)
        
        if hasattr(database, 'log_admin_action'):
            database.log_admin_action(
                "المدير العام",
                f"{'حظر' if ban_status else 'إلغاء حظر'} المستخدم {tg_id_str}",
            )
        return True, (
            "تم حظر المستخدم بنجاح" if ban_status else "تم إلغاء الحظر بنجاح"
        )
    except Exception as e:
        print(f"❌ Error banning user {tg_id}: {e}")
        return False, f"حدث خطأ: {e}"


def init_user(tg_id, ref_id=None, first_name="صديقي"):
    """إنشاء أو تحديث حساب مستخدم جديد بالتكامل مع نظام الإحالات"""
    try:
        if not tg_id:
            return False
        db = database.get_db()

        tg_id_str = str(tg_id)
        user_ref = db.collection("users").document(tg_id_str)
        user_doc = user_ref.get()

        is_new_referral = False
        valid_ref_id = str(ref_id) if ref_id and str(ref_id) != tg_id_str else None

        if not user_doc.exists:
            from datetime import datetime, timezone
            now_iso = datetime.now(timezone.utc).isoformat()
            new_user_data = {
                "tg_id": tg_id_str,
                "first_name": first_name or "صديقي",
                "balance": 0.0,
                "znx_balance": 0.0,
                "ad_balance": 0.0,
                "usd_balance": 0.0,
                "hourly_rate": 0.0,
                "daily_boost_rate": 0.0,
                "ads_watched": 0,
                "energy": 100.0,
                "storage_level": 0,
                "extra_storage": 0.0,
                "max_cap": 100.0,
                "last_claim_time": now_iso,
                "daily_streak": 0,
                "daily_day": 1,
                "last_daily_claim_date": None,
                "upgrades": {},
                "completed_tasks": [],
                "banned": False,
                "wallet_address": None,
                "referred_by": valid_ref_id,
                "pending_ref_earnings": 0.0,
                "total_ref_earnings": 0.0,
                "invited_friends_count": 0,
                "total_bets": 0.0,
                "total_wins": 0.0,
                "total_losses": 0.0,
                "last_active": firestore.SERVER_TIMESTAMP,
                "joined_at": firestore.SERVER_TIMESTAMP,
            }
            user_ref.set(new_user_data)

            if valid_ref_id:
                referrer_ref = db.collection("users").document(valid_ref_id)
                if referrer_ref.get().exists:
                    is_new_referral = True
                    referrer_ref.update(
                        {"invited_friends_count": firestore.Increment(1)}
                    )
                    referrer_ref.collection("friends").document(tg_id_str).set({
                        "tg_id": tg_id_str,
                        "first_name": first_name or "صديقي",
                        "earned_from_him": 0.0,
                        "joined_at": firestore.SERVER_TIMESTAMP,
                    }, merge=True)
        else:
            user_ref.update(
                {"first_name": first_name or "صديقي", "last_active": firestore.SERVER_TIMESTAMP}
            )

        return is_new_referral
    except Exception as e:
        print(f"❌ Error initializing user {tg_id}: {e}")
        return False


def get_user(tg_id):
    """جلب كافة بيانات مستخدم محدد بالكامل"""
    try:
        if not tg_id:
            return None
        db = database.get_db()
        user_ref = db.collection("users").document(str(tg_id))
        doc = user_ref.get()
        if doc.exists:
            data = doc.to_dict() or {}
            data["id"] = str(doc.id)

            # معالجة التواريخ والكائنات لضمان التوافق مع JSON
            for k, v in data.items():
                data[k] = _serialize_firestore_val(v)

            return data
        return None
    except Exception as e:
        print(f"❌ Error getting user {tg_id}: {e}")
        return None


def get_all_users_admin(limit=1000):
    """جلب جميع حقول وقيم كافة المستخدمين للوحة التحكم"""
    try:
        db = database.get_db()
        users_ref = db.collection("users").limit(limit)
        docs = users_ref.stream()

        users_list = []
        for doc in docs:
            d = doc.to_dict() or {}
            user_data = {"id": str(doc.id)}
            
            # استخراج جميع الحقول وتنسيقها للفيو
            for k, v in d.items():
                user_data[k] = _serialize_firestore_val(v)

            # القيم الافتراضية المضمونة
            user_data["tg_id"] = str(d.get("tg_id", doc.id))
            user_data["first_name"] = d.get("first_name", "مستخدم")
            user_data["name"] = user_data["first_name"]
            user_data["balance"] = float(d.get("balance", 0.0) or 0.0)
            user_data["znx_balance"] = float(d.get("znx_balance", 0.0) or 0.0)
            user_data["usd_balance"] = float(d.get("usd_balance", 0.0) or 0.0)
            user_data["ad_balance"] = float(d.get("ad_balance", 0.0) or 0.0)
            user_data["banned"] = bool(d.get("banned", False))
            user_data["isBanned"] = user_data["banned"]
            
            # تنسيق تاريخ الانضمام للمشاهدة
            joined_at = d.get("joined_at")
            if hasattr(joined_at, 'strftime'):
                user_data["joinDate"] = joined_at.strftime('%Y-%m-%d')
            elif isinstance(joined_at, str):
                user_data["joinDate"] = joined_at.split('T')[0]
            else:
                user_data["joinDate"] = "غير معروف"

            users_list.append(user_data)
            
        return users_list
    except Exception as e:
        print(f"❌ Error fetching all users for admin: {e}")
        return []


def update_user(tg_id, update_data):
    """تحديث حقول حساب المستخدم"""
    try:
        if not tg_id or not isinstance(update_data, dict):
            return False
        db = database.get_db()
        db.collection("users").document(str(tg_id)).update(update_data)
        return True
    except Exception as e:
        print(f"❌ Error updating user {tg_id}: {e}")
        return False

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
    """
    جلب كافة بيانات المستخدمين والقيام بتدقيق وحساب حقيقي ديناميكي مستخدم بمستخدم (User-by-User Audit)
    لكافة الإحصائيات (الإحالات، الإعلانات، المهام، الألعاب، الأرصدة، وغيرها) لضمان أرقام حقيقية 100%
    """
    try:
        db = database.get_db()
        users_ref = db.collection("users")
        if limit and limit > 0:
            users_ref = users_ref.limit(limit)
            
        docs = users_ref.stream()

        users_map = {}
        doc_id_to_tg_id = {}
        referrals_by_inviter = {}

        # 1. التفتيش والدراسة الفردية لكل مستند مستخدم
        for doc in docs:
            d = doc.to_dict() or {}
            doc_id = str(doc.id)
            
            user_data = {"document_id": doc_id}
            
            # حفظ كافة الحقول الخام
            for k, v in d.items():
                user_data[k] = _serialize_firestore_val(v)

            # استخراج معرف التيليجرام بجميع الاحتمالات الممكنة
            tg_id = str(d.get("tg_id") or d.get("telegram_id") or d.get("telegramId") or doc_id).strip()
            user_data["tg_id"] = tg_id
            user_data["first_name"] = str(d.get("first_name") or d.get("name") or d.get("username") or "مستخدم").strip()
            
            # ربط المعرفات بين document_id و tg_id لمنع فقدان أي ارتباط
            doc_id_to_tg_id[doc_id] = tg_id
            doc_id_to_tg_id[tg_id] = tg_id

            # توحيد واستخراج تاريخ الانضمام وتاريخ آخر نشاط بدقة عالية للتصفية الزمنية
            joined_at = (
                d.get("joined_at") or 
                d.get("joinDate") or 
                d.get("created_at") or 
                d.get("createdAt") or 
                d.get("registered_at") or 
                d.get("timestamp") or 
                ""
            )
            user_data["joined_at"] = _serialize_firestore_val(joined_at)

            last_active = (
                d.get("last_active_at") or 
                d.get("last_active") or 
                d.get("lastActive") or 
                user_data["joined_at"]
            )
            user_data["last_active"] = _serialize_firestore_val(last_active)

            # === حساب وتحليل الأرقام والإحصائيات مباشرة لكل مستخدم ===
            
            # أ) الإحالات المخزنة (جمع كافة الحقول المترادفة مثل invited_friends_count + referrals_count)
            raw_invited = 0
            try:
                raw_invited = int(d.get("invited_friends_count") or d.get("invitedFriendsCount") or 0)
            except (ValueError, TypeError):
                raw_invited = 0

            raw_refs = 0
            try:
                raw_refs = int(d.get("referrals_count") or d.get("referralsCount") or d.get("ref_count") or 0)
            except (ValueError, TypeError):
                raw_refs = 0

            user_data["stored_refs_sum"] = raw_invited + raw_refs

            # ب) مشاهدات الإعلانات الإجمالية
            try:
                user_data["ads_watched"] = int(d.get("ads_watched") or d.get("adsWatched") or d.get("total_ads") or 0)
            except (ValueError, TypeError):
                user_data["ads_watched"] = 0

            # ج) الستريك اليومي
            try:
                user_data["daily_streak"] = int(d.get("daily_streak") or d.get("dailyStreak") or d.get("streak") or 0)
            except (ValueError, TypeError):
                user_data["daily_streak"] = 0

            # د) معدل التسريع / البوست
            try:
                user_data["daily_boost_rate"] = float(d.get("daily_boost_rate") or d.get("boost_rate") or d.get("hourly_rate") or 0.0)
            except (ValueError, TypeError):
                user_data["daily_boost_rate"] = 0.0

            # هـ) الرصيد الرئيسي ورصيد ZNX ورصيد USD
            try:
                user_data["balance"] = float(d.get("balance") or 0.0)
            except (ValueError, TypeError):
                user_data["balance"] = 0.0

            try:
                user_data["znx_balance"] = float(d.get("znx_balance") or d.get("znxBalance") or d.get("total_znx_earned") or 0.0)
            except (ValueError, TypeError):
                user_data["znx_balance"] = 0.0

            try:
                user_data["usd_balance"] = float(d.get("usd_balance") or d.get("usdBalance") or 0.0)
            except (ValueError, TypeError):
                user_data["usd_balance"] = 0.0

            # و) النقاط المعدنة
            try:
                user_data["mined_points"] = float(d.get("mined_points") or d.get("total_mined") or d.get("minedPoints") or 0.0)
            except (ValueError, TypeError):
                user_data["mined_points"] = 0.0

            # ز) المهام المكتملة (تحليل ديناميكي للمصفوفات أو الأعداد)
            completed_tasks_raw = d.get("completed_tasks") or d.get("completedTasks") or d.get("tasks")
            tasks_count = 0
            if isinstance(completed_tasks_raw, list):
                tasks_count = len(completed_tasks_raw)
            elif isinstance(completed_tasks_raw, dict):
                tasks_count = len(completed_tasks_raw)
            else:
                try:
                    tasks_count = int(d.get("tasks_completed_count") or d.get("completed_tasks_count") or d.get("total_tasks") or 0)
                except (ValueError, TypeError):
                    tasks_count = 0
            user_data["completed_tasks"] = tasks_count

            # ح) التفاعلات مع البوت
            try:
                user_data["interactions"] = int(d.get("interactions") or d.get("bot_interactions") or d.get("total_interactions") or 0)
            except (ValueError, TypeError):
                user_data["interactions"] = 0

            # ط) الفوز بالألعاب
            try:
                user_data["total_wins"] = int(d.get("total_wins") or d.get("game_wins") or d.get("wins") or 0)
            except (ValueError, TypeError):
                user_data["total_wins"] = 0

            # استخراج المعرف الداعي لهذا المستخدم (referred_by)
            referred_by = str(d.get("referred_by") or d.get("referredBy") or "").strip()
            user_data["referred_by"] = referred_by if referred_by not in ["None", "null", ""] else ""

            users_map[tg_id] = user_data

        # 2. الفحص العكسي الشامل لتتبع روابط الإحالة عبر كل مستخدم مستخدم
        for tg_id, u_data in users_map.items():
            ref_by_raw = u_data.get("referred_by", "")
            if ref_by_raw:
                inviter_tg_id = doc_id_to_tg_id.get(ref_by_raw, ref_by_raw)
                if inviter_tg_id not in referrals_by_inviter:
                    referrals_by_inviter[inviter_tg_id] = []
                
                referrals_by_inviter[inviter_tg_id].append({
                    "tg_id": tg_id,
                    "first_name": u_data.get("first_name", "مستخدم"),
                    "joined_at": u_data.get("joined_at", "")
                })

        # 3. توحيد النتائج واعتماد الرقم الأدق والأنسب بين القيم المكتشفة
        users_list = []
        for tg_id, u_data in users_map.items():
            actual_refs = referrals_by_inviter.get(tg_id, [])
            actual_ref_count = len(actual_refs)
            
            # تضمين قائمة الإحالات المكتشفة مع تواريخ انضمام كل صديق لغرض الفلترة الزمنية
            u_data["referrals_list"] = actual_refs
            
            # اعتماد النتيجة الكبرى بين التفتيش المباشر والحقول المجمعة
            u_data["invited_friends_count"] = max(u_data.get("stored_refs_sum", 0), actual_ref_count)
            
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

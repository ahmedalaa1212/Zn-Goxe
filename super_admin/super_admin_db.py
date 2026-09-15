from firebase_admin import firestore
import database
import time
from datetime import datetime

def _find_user_doc(db, tg_id):
    """دالة مساعدة للبحث عن مستند المستخدم بمرونة (سواء باستخدام المعرف كمفتاح أو كحقل وبمختلف الأنواع)"""
    if not db or not tg_id:
        return None, None

    tg_id_str = str(tg_id).strip()
    if not tg_id_str:
        return None, None

    # 1. البحث المباشر كمعرّف للمستند
    user_ref = db.collection("users").document(tg_id_str)
    user_doc = user_ref.get()
    if user_doc.exists:
        return user_ref, user_doc

    # 2. البحث كعدد صحيح إذا كان المعرف أرقاماً
    tg_id_int = None
    try:
        tg_id_int = int(tg_id_str)
        user_ref_int = db.collection("users").document(str(tg_id_int))
        user_doc_int = user_ref_int.get()
        if user_doc_int.exists:
            return user_ref_int, user_doc_int
    except (ValueError, TypeError):
        pass

    # 3. الاستعلام بحقول الحسابات الشائعة
    for field in ["telegram_id", "tg_id", "user_id", "id"]:
        try:
            docs = list(db.collection("users").where(field, "==", tg_id_str).limit(1).stream())
            if docs:
                return docs[0].reference, docs[0]
            if tg_id_int is not None:
                docs = list(db.collection("users").where(field, "==", tg_id_int).limit(1).stream())
                if docs:
                    return docs[0].reference, docs[0]
        except Exception:
            pass

    return None, None


def _find_associated_devices(db, user_doc, tg_id_str):
    """جمع كافة المعرفات والأجهزة المربوطة بالمستخدم من ملفه الشخصي ومن مجموعة devices ومجموعة banned_devices"""
    device_ids = set()
    if not tg_id_str:
        return device_ids

    tg_id_str = str(tg_id_str).strip()
    device_ids.add(tg_id_str)

    tg_id_int = None
    try:
        tg_id_int = int(tg_id_str)
    except ValueError:
        pass

    # 1. استخراج الأجهزة المسجلة داخل مستند المستخدم مباشرة
    if user_doc and user_doc.exists:
        u_data = user_doc.to_dict() or {}
        doc_id = str(user_doc.id).strip()
        if doc_id:
            device_ids.add(doc_id)

        for key in ["device_id", "hardware_id", "device_fingerprint", "last_device_id", "fingerprint_hash"]:
            val = u_data.get(key)
            if val:
                device_ids.add(str(val).strip())

        for key in ["device_ids", "devices", "known_devices"]:
            val_list = u_data.get(key)
            if isinstance(val_list, list):
                for dev in val_list:
                    if dev:
                        device_ids.add(str(dev).strip())
            elif isinstance(val_list, dict):
                for dev_k in val_list.keys():
                    if dev_k:
                        device_ids.add(str(dev_k).strip())

    # 2. البحث في مجموعة devices الشاملة عن أي جهاز مرتبط بهذا المستخدم
    search_vals = [tg_id_str]
    if tg_id_int is not None:
        search_vals.append(tg_id_int)

    if db:
        for s_val in search_vals:
            # البحث بـ primary_user_id
            try:
                dev_docs = db.collection("devices").where("primary_user_id", "==", s_val).stream()
                for ddoc in dev_docs:
                    device_ids.add(str(ddoc.id).strip())
                    d_data = ddoc.to_dict() or {}
                    if d_data.get("device_id"):
                        device_ids.add(str(d_data.get("device_id")).strip())
            except Exception as e:
                print(f"⚠️ Error querying devices by primary_user_id ({s_val}): {e}")

            # البحث داخل مصفوفة users
            try:
                dev_docs = db.collection("devices").where("users", "array_contains", s_val).stream()
                for ddoc in dev_docs:
                    device_ids.add(str(ddoc.id).strip())
                    d_data = ddoc.to_dict() or {}
                    if d_data.get("device_id"):
                        device_ids.add(str(d_data.get("device_id")).strip())
            except Exception as e:
                print(f"⚠️ Error querying devices by users array ({s_val}): {e}")

    return device_ids


def _parse_to_timestamp(val):
    """تحويل قيم التواريخ المختلفة إلى Timestamp بالثواني بأمان"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, datetime):
        try:
            return val.timestamp()
        except Exception:
            return None
    if isinstance(val, str):
        val_str = val.strip()
        if not val_str:
            return None
        try:
            return float(val_str)
        except ValueError:
            pass
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%d"
        ):
            try:
                dt = datetime.strptime(val_str.split('+')[0].replace('Z', ''), fmt)
                return dt.timestamp()
            except ValueError:
                pass
        try:
            dt = datetime.fromisoformat(val_str.replace('Z', '+00:00').replace(' ', 'T'))
            return dt.timestamp()
        except Exception:
            pass
    return None


def _safe_float(val, default=0.0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, str):
        try:
            return float(val.strip())
        except ValueError:
            return default
    return default


def _safe_int(val, default=0):
    if val is None:
        return default
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, list):
        return len(val)
    if isinstance(val, str):
        try:
            return int(float(val.strip()))
        except ValueError:
            return default
    return default


def modify_user_balance_admin(tg_id, amount, balance_type="balance", operation="add", admin_name="السوبر أدمن"):
    """تعديل رصيد مستخدم (إضافة / خصم / تعيين) بواسطة الأدمن الرئيسي"""
    try:
        if not tg_id:
            return False, "معرف مستخدم غير صالح", 0.0

        db = database.get_db()
        user_ref, user_doc = _find_user_doc(db, tg_id)

        if not user_doc or not user_doc.exists:
            return False, "المستخدم غير موجود", 0.0

        user_data = user_doc.to_dict() or {}
        tg_id_str = str(user_doc.id)
        field_key = balance_type if balance_type in ["balance", "ad_balance", "usd_balance"] else "balance"
        current_val = _safe_float(user_data.get(field_key, 0.0))
        amount = _safe_float(amount)

        if operation == "add":
            new_val = round(current_val + amount, 2)
        elif operation == "subtract":
            new_val = round(max(0.0, current_val - amount), 2)
        elif operation == "set":
            new_val = round(max(0.0, amount), 2)
        else:
            return False, "نوع العملية غير معروف", current_val

        user_ref.update({field_key: new_val})
        try:
            database.log_admin_action(admin_name, f"تعديل رصيد {field_key} للمستخدم {tg_id_str}: من {current_val} إلى {new_val}")
        except Exception:
            pass

        return True, f"تم تعديل رصيد {field_key} بنجاح إلى {new_val}", new_val
    except Exception as e:
        print(f"❌ Error modifying user balance: {e}")
        return False, f"حدث خطأ: {e}", 0.0


def reset_user_account_admin(tg_id, admin_name="السوبر أدمن"):
    """تصفير بيانات وحساب مستخدم بالكامل"""
    try:
        if not tg_id:
            return False, "معرف غير صالح"

        db = database.get_db()
        user_ref, user_doc = _find_user_doc(db, tg_id)

        if not user_doc or not user_doc.exists:
            return False, "المستخدم غير موجود"

        user_ref.update({
            "balance": 0.0,
            "ad_balance": 0.0,
            "usd_balance": 0.0,
            "hourly_rate": 0.0,
            "daily_boost_rate": 0.0,
            "upgrades": {},
            "storage_level": 0,
            "completed_tasks": [],
            "total_bets": 0.0,
            "total_wins": 0.0,
            "total_losses": 0.0
        })

        try:
            database.log_admin_action(admin_name, f"تصفير حساب المستخدم {user_doc.id} بالكامل")
        except Exception:
            pass

        return True, f"تم إعادة تصفير حساب المستخدم {user_doc.id} بنجاح!"
    except Exception as e:
        print(f"❌ Error resetting user account: {e}")
        return False, f"حدث خطأ: {e}"


# 🚫 دالة حظر مستخدم وحظر جهازه بالتوازي مع كافة مجموعات قاعدة البيانات
def ban_user_db(tg_id, reason="تم الحظر من قبل الإدارة العليا", admin_name="السوبر أدمن"):
    """حظر مستخدم وتحديث حقول الحظر وحظر كافة أجهزته المربوطة به في مجموعات users, devices, banned_devices"""
    try:
        if not tg_id:
            return False, "معرف المستخدم مطلوب"

        db = database.get_db()
        if not db:
            return False, "تعذر الاتصال بقاعدة البيانات"

        tg_id_str = str(tg_id).strip()
        user_ref, user_doc = _find_user_doc(db, tg_id_str)

        if not user_doc or not user_doc.exists:
            return False, f"المستخدم رقم ({tg_id_str}) غير مسجل في النظام"

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        # 1. تحديث كافة حقول الحظر في مستند المستخدم (users)
        user_ref.update({
            "banned": True,
            "is_banned": True,
            "ban": True,
            "status": "banned",
            "ban_reason": reason,
            "banned_at": now_str,
            "banned_by": admin_name
        })

        # 2. جمع كافة المعرفات والأجهزة المرتبطة به
        device_ids = _find_associated_devices(db, user_doc, tg_id_str)

        tg_id_int = None
        try:
            tg_id_int = int(tg_id_str)
        except ValueError:
            pass

        # 3. حظر كل جهاز في مجموعة devices ومجموعة banned_devices
        for dev_id in device_ids:
            if not dev_id:
                continue

            # أ) تحديث مستند الجهاز في مجموعة devices إن وجد
            try:
                dev_ref = db.collection("devices").document(str(dev_id))
                dev_doc = dev_ref.get()
                if dev_doc.exists:
                    dev_ref.update({
                        "is_banned": True,
                        "banned": True,
                        "ban_reason": reason,
                        "banned_at": now_str,
                        "banned_by": admin_name
                    })
            except Exception as de:
                print(f"⚠️ Error updating device doc in devices/{dev_id}: {de}")

            # ب) إضافة أو دمج سجل الحظر في مجموعة banned_devices
            ban_payload = {
                "device_id": str(dev_id),
                "telegram_id": tg_id_str,
                "tg_id": tg_id_str,
                "reason": reason,
                "banned_at": now_str,
                "banned_by": admin_name,
                "is_banned": True,
                "banned": True
            }
            if tg_id_int is not None:
                ban_payload["tg_id_int"] = tg_id_int
                ban_payload["telegram_id_int"] = tg_id_int

            try:
                db.collection("banned_devices").document(str(dev_id)).set(ban_payload, merge=True)
            except Exception as bde:
                print(f"⚠️ Error setting banned_devices/{dev_id}: {bde}")

        try:
            database.log_admin_action(admin_name, f"حظر المستخدم {tg_id_str} والأجهزة المربوطة ({len(device_ids)}) - السبب: {reason}")
        except Exception:
            pass

        return True, f"تم حظر المستخدم {tg_id_str} وجميع أجهزته المربوطة بنجاح"
    except Exception as e:
        print(f"❌ Error banning user {tg_id}: {e}")
        return False, f"حدث خطأ أثناء حظر المستخدم: {e}"


# 🟢 دالة فك الحظر عن مستخدم وإلغاء حظر كافة أجهزته المربوطة به
def unban_user_db(tg_id, admin_name="السوبر أدمن"):
    """فك الحظر عن مستخدم وتحديث حقول الحظر وحذف كافة أجهزته من مجموعة banned_devices وتحديث devices"""
    try:
        if not tg_id:
            return False, "معرف المستخدم مطلوب"

        db = database.get_db()
        if not db:
            return False, "تعذر الاتصال بقاعدة البيانات"

        tg_id_str = str(tg_id).strip()
        user_ref, user_doc = _find_user_doc(db, tg_id_str)

        if not user_doc or not user_doc.exists:
            return False, f"المستخدم رقم ({tg_id_str}) غير مسجل في النظام"

        now_str = time.strftime("%Y-%m-%d %H:%M:%S")

        # 1. إلغاء الحظر وتصفير حالة الحظر في كافة حقول ملف المستخدم
        user_ref.update({
            "banned": False,
            "is_banned": False,
            "ban": False,
            "status": "active",
            "ban_reason": "",
            "unbanned_at": now_str,
            "unbanned_by": admin_name
        })

        # 2. جمع كافة الأجهزة المرتبطة بملف المستخدم
        device_ids = _find_associated_devices(db, user_doc, tg_id_str)

        # 3. فك حظر الأجهزة في مجموعة devices وحذفها من banned_devices
        for dev_id in device_ids:
            if not dev_id:
                continue

            other_user_banned = False
            try:
                dev_ref = db.collection("devices").document(str(dev_id))
                dev_doc = dev_ref.get()
                if dev_doc.exists:
                    d_data = dev_doc.to_dict() or {}
                    linked_users = set()
                    p_user = d_data.get("primary_user_id")
                    if p_user:
                        linked_users.add(str(p_user).strip())
                    u_list = d_data.get("users") or []
                    if isinstance(u_list, list):
                        for u_item in u_list:
                            if u_item:
                                linked_users.add(str(u_item).strip())

                    # استبعاد المستخدم الحالي من الفحص
                    linked_users.discard(tg_id_str)

                    # التأكد إن كان يوجد حساب آخر محظور ما زال يستعمل نفس الجهاز
                    for l_uid in linked_users:
                        _, l_user_doc = _find_user_doc(db, l_uid)
                        if l_user_doc and l_user_doc.exists:
                            l_data = l_user_doc.to_dict() or {}
                            if l_data.get("banned") or l_data.get("is_banned") or l_data.get("ban") or l_data.get("status") == "banned":
                                other_user_banned = True
                                break

                    if not other_user_banned:
                        dev_ref.update({
                            "is_banned": False,
                            "banned": False,
                            "unbanned_at": now_str,
                            "unbanned_by": admin_name
                        })
            except Exception as de:
                print(f"⚠️ Error checking/updating device {dev_id}: {de}")

            # إذا لم يكن هناك حساب آخر محظور على هذا الجهاز، قم بحذفه من قائمة الأجهزة المحظورة
            if not other_user_banned:
                try:
                    db.collection("banned_devices").document(str(dev_id)).delete()
                except Exception as bde:
                    print(f"⚠️ Error deleting banned_devices/{dev_id}: {bde}")

        # 4. حذف أي مستندات متبقية في banned_devices مرتبطة بمعرّف التليجرام
        tg_id_int = None
        try:
            tg_id_int = int(tg_id_str)
        except ValueError:
            pass

        target_vals = [tg_id_str]
        if tg_id_int is not None:
            target_vals.append(tg_id_int)

        search_fields = ["telegram_id", "tg_id", "user_id", "device_id", "tg_id_int", "telegram_id_int"]

        for field in search_fields:
            for val in target_vals:
                try:
                    banned_docs = db.collection("banned_devices").where(field, "==", val).stream()
                    for bdoc in banned_docs:
                        try:
                            bdoc.reference.delete()
                        except Exception:
                            pass
                except Exception as qe:
                    print(f"⚠️ Error deleting leftover banned_devices field {field}={val}: {qe}")

        try:
            database.log_admin_action(admin_name, f"فك الحظر عن المستخدم {tg_id_str} وجميع الأجهزة المربوطة به")
        except Exception:
            pass

        return True, f"تم فك الحظر عن المستخدم {tg_id_str} وجميع أجهزته بنجاح"
    except Exception as e:
        print(f"❌ Error unbanning user {tg_id}: {e}")
        return False, f"حدث خطأ أثناء فك الحظر: {e}"


# 👤 دالة إضافة مشرف جديد
def add_moderator_db(tg_id, name, permissions=None, admin_name="السوبر أدمن"):
    """إضافة مشرف جديد وتسجيل صلاحياته"""
    try:
        if not tg_id or not name:
            return False, "معرف المشرف والاسم مطلوبان"

        db = database.get_db()
        tg_id_str = str(tg_id).strip()
        admin_ref = db.collection("admins").document(tg_id_str)

        perms = permissions if isinstance(permissions, dict) else {
            "perm_users": True,
            "perm_security": True,
            "perm_ads": False
        }

        admin_ref.set({
            "telegram_id": tg_id_str,
            "tg_id": tg_id_str,
            "name": name.strip(),
            "role": "moderator",
            "permissions": perms,
            "added_by": admin_name,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }, merge=True)

        try:
            database.log_admin_action(admin_name, f"إضافة المشرف {name} ({tg_id_str})")
        except Exception:
            pass

        return True, f"تمت إضافة المشرف {name} بنجاح"
    except Exception as e:
        print(f"❌ Error adding moderator: {e}")
        return False, f"حدث خطأ أثناء إضافة المشرف: {e}"


# 🛡️ دالة جلب قائمة المشرفين
def list_moderators_db():
    """جلب قائمة بكل المشرفين المسجلين بالنظام"""
    try:
        db = database.get_db()
        if not db:
            return []

        docs = db.collection("admins").stream()
        moderators = []
        for doc in docs:
            d = doc.to_dict() or {}
            moderators.append({
                "telegram_id": str(d.get("telegram_id") or d.get("tg_id") or doc.id),
                "name": d.get("name", "مشرف"),
                "role": d.get("role", "moderator"),
                "permissions": d.get("permissions", {}),
                "created_at": d.get("created_at", "غير معروف")
            })
        return moderators
    except Exception as e:
        print(f"❌ Error listing moderators: {e}")
        return []


# 🗑️ دالة حذف مشرف
def remove_moderator_db(tg_id, admin_name="السوبر أدمن"):
    """حذف مشرف من النظام"""
    try:
        if not tg_id:
            return False, "معرف المشرف مطلوب"

        db = database.get_db()
        tg_id_str = str(tg_id).strip()
        admin_ref = db.collection("admins").document(tg_id_str)

        if not admin_ref.get().exists:
            return False, "المشرف غير موجود"

        admin_ref.delete()

        try:
            database.log_admin_action(admin_name, f"حذف المشرف {tg_id_str}")
        except Exception:
            pass

        return True, f"تم حذف المشرف {tg_id_str} بنجاح"
    except Exception as e:
        print(f"❌ Error removing moderator: {e}")
        return False, f"حدث خطأ أثناء حذف المشرف: {e}"


# 📜 دالة جلب السجلات الإدارية
def get_admin_logs(limit=50):
    """جلب سجل الحركات الإدارية الأخير"""
    try:
        db = database.get_db()
        if not db:
            return []

        logs_ref = db.collection("admin_logs").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(limit).stream()
        logs = []
        for doc in logs_ref:
            d = doc.to_dict() or {}
            logs.append({
                "id": doc.id,
                "admin": d.get("admin") or d.get("admin_name") or "النظام",
                "action": d.get("action") or d.get("details") or "",
                "timestamp": d.get("created_at_str") or d.get("time") or d.get("timestamp") or ""
            })
        return logs
    except Exception as e:
        print(f"❌ Error getting admin logs: {e}")
        return []


# 📊 دالة التحليلات العامة المحدثة (إجمالي، متفاعلين اليوم، محظورين، والأكثر نشاطاً)
def get_system_global_analytics():
    """تحليلات النظام الكلية: حساب إجمالي المستخدمين، المتفاعلين اليوم، المحظورين، وأكثر المستخدمين نشاطاً"""
    try:
        db = database.get_db()
        if not db:
            return {
                "total_users": 0,
                "active_today": 0,
                "banned_users": 0,
                "total_circulating_zn": 0.0,
                "total_ad_balance_zn": 0.0,
                "top_users": [],
                "top_active_users": []
            }

        users_docs = db.collection("users").stream()

        total_users = 0
        active_today_count = 0
        banned_users_count = 0
        total_balance_zn = 0.0
        total_ad_balance = 0.0

        now_ts = time.time()
        one_day_seconds = 86400

        user_activity_list = []

        for u in users_docs:
            total_users += 1
            try:
                d = u.to_dict() or {}
                tg_id_str = str(d.get("telegram_id") or d.get("tg_id") or u.id)

                # تجميع الأرصدة المتداولة
                bal = _safe_float(d.get("balance"))
                ad_bal = _safe_float(d.get("ad_balance"))
                total_balance_zn += bal
                total_ad_balance += ad_bal

                # حساب المستخدمين المحظورين
                is_banned = bool(
                    d.get("banned") or 
                    d.get("is_banned") or 
                    d.get("ban") or 
                    d.get("status") == "banned"
                )
                if is_banned:
                    banned_users_count += 1

                # حساب المستخدمين النشطين خلال آخر 24 ساعة
                last_active_raw = (
                    d.get("last_active") or 
                    d.get("last_seen") or 
                    d.get("updated_at") or 
                    d.get("last_active_at") or 
                    d.get("last_login") or 
                    d.get("last_seen_at")
                )
                last_active_ts = _parse_to_timestamp(last_active_raw)
                is_active_today = False

                if last_active_ts is not None:
                    diff = now_ts - last_active_ts
                    if 0 <= diff <= one_day_seconds:
                        is_active_today = True

                if is_active_today:
                    active_today_count += 1

                # تجميع حجم تفاعلات المستخدم بمرونة
                act_cnt = _safe_int(d.get("activity_count")) or _safe_int(d.get("interactions")) or _safe_int(d.get("total_clicks")) or _safe_int(d.get("clicks")) or _safe_int(d.get("taps"))
                tasks_cnt = _safe_int(d.get("completed_tasks"))
                bets_cnt = _safe_int(d.get("total_bets"))
                refs_cnt = _safe_int(d.get("referrals")) or _safe_int(d.get("referrals_count"))

                interactions = act_cnt + tasks_cnt + bets_cnt
                if interactions == 0:
                    if is_active_today or bal > 0 or tasks_cnt > 0:
                        interactions = max(1, tasks_cnt, refs_cnt)

                name = d.get("first_name") or d.get("name") or d.get("username") or f"مستخدم ({tg_id_str})"
                username = d.get("username", "—")
                if username and username != "—" and not username.startswith("@"):
                    username = f"@{username}"

                last_active_disp = d.get("last_active_str") or d.get("last_seen_str") or ("نشط اليوم" if is_active_today else "سابقاً")

                user_activity_list.append({
                    "telegram_id": tg_id_str,
                    "user_id": tg_id_str,
                    "name": name,
                    "username": username,
                    "interactions": interactions,
                    "activity_count": interactions,
                    "balance": round(bal, 2),
                    "is_banned": is_banned,
                    "last_active": last_active_disp
                })
            except Exception as doc_e:
                print(f"⚠️ Error processing user doc {u.id}: {doc_e}")
                continue

        # ترتيب المستخدمين حسب حجم التفاعل تنازلياً واختيار أعلى 10
        user_activity_list.sort(key=lambda x: (x["interactions"], x["balance"]), reverse=True)
        top_active_users = user_activity_list[:10]

        return {
            "total_users": total_users,
            "active_today": active_today_count,
            "banned_users": banned_users_count,
            "total_circulating_zn": round(total_balance_zn, 2),
            "total_ad_balance_zn": round(total_ad_balance, 2),
            "top_users": top_active_users,
            "top_active_users": top_active_users
        }
    except Exception as e:
        print(f"❌ Error getting global analytics: {e}")
        return {
            "total_users": 0,
            "active_today": 0,
            "banned_users": 0,
            "total_circulating_zn": 0.0,
            "total_ad_balance_zn": 0.0,
            "top_users": [],
            "top_active_users": []
        }


# ------------------- وظائف نظام الإشعارات والبث الجماعي ------------------- #

def get_all_user_ids():
    """استخراج قائمة بكل معرفات المستخدمين غير المحظورين"""
    try:
        db = database.get_db()
        if not db:
            return []

        users_ref = db.collection("users").stream()
        user_ids = []

        for doc in users_ref:
            try:
                data = doc.to_dict() or {}
                if not (data.get("banned") or data.get("is_banned") or data.get("ban") or data.get("status") == "banned"):
                    user_ids.append(str(doc.id))
            except Exception:
                pass
        return user_ids
    except Exception as e:
        print(f"❌ Error fetching user IDs: {e}")
        return []


def get_user_by_id(tg_id):
    """فحص وجود مستخدم محدد وإرجاع بياناته"""
    try:
        db = database.get_db()
        if not db:
            return False, None

        user_ref, user_doc = _find_user_doc(db, tg_id)
        if user_doc and user_doc.exists:
            return True, user_doc.to_dict()
        return False, None
    except Exception as e:
        print(f"❌ Error checking user {tg_id}: {e}")
        return False, None


def log_broadcast_campaign(admin_name, message, total_targets, success_count, blocked_count):
    """أرشفة وتسجيل نتائج حملة الإرسال الجماعي"""
    try:
        db = database.get_db()
        if not db:
            return False

        campaign_data = {
            "admin_name": admin_name,
            "message_snippet": message[:100] + "..." if len(message) > 100 else message,
            "total_targets": total_targets,
            "success_count": success_count,
            "blocked_count": blocked_count,
            "failed_count": max(0, total_targets - (success_count + blocked_count)),
            "timestamp": firestore.SERVER_TIMESTAMP,
            "created_at_str": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        db.collection("broadcasts").add(campaign_data)

        try:
            database.log_admin_action(admin_name, f"حملة إرسال جماعي: تم {success_count}/{total_targets} | حظر {blocked_count}")
        except Exception:
            pass

        return True
    except Exception as e:
        print(f"❌ Error logging broadcast campaign: {e}")
        return False


def get_latest_broadcast_stats():
    """جلب بيانات أحدث حملة إرسال محفوظة"""
    try:
        db = database.get_db()
        if not db:
            return None

        docs = db.collection("broadcasts").order_by("timestamp", direction=firestore.Query.DESCENDING).limit(1).stream()
        for doc in docs:
            return doc.to_dict()
        return None
    except Exception as e:
        print(f"❌ Error fetching latest broadcast: {e}")
        return None

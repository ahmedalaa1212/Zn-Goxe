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


def _find_associated_devices_and_users(db, user_doc, tg_id_str):
    """جمع كافة الأجهزة وبصمات الأجهزة والحسابات المربوطة بالمستخدم بمرونة وشمولية"""
    device_ids = set()
    fingerprint_hashes = set()
    user_ids = set()
    user_refs = []

    if not tg_id_str or not db:
        return device_ids, fingerprint_hashes, user_refs, user_ids

    tg_id_str = str(tg_id_str).strip()
    user_ids.add(tg_id_str)

    tg_id_int = None
    try:
        tg_id_int = int(tg_id_str)
    except ValueError:
        pass

    # 1. استخراج البيانات المباشرة من مستند المستخدم
    if user_doc and user_doc.exists:
        user_refs.append(user_doc.reference)
        u_data = user_doc.to_dict() or {}

        for key in ["device_id", "hardware_id", "device_fingerprint", "last_device_id"]:
            val = u_data.get(key)
            if val:
                device_ids.add(str(val).strip())

        fp = u_data.get("fingerprint_hash")
        if fp:
            fingerprint_hashes.add(str(fp).strip())

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

    # 2. الاستعلام في مجموعة devices بواسطة معرف المستخدم
    search_vals = [tg_id_str]
    if tg_id_int is not None:
        search_vals.append(tg_id_int)

    for s_val in search_vals:
        try:
            dev_docs = db.collection("devices").where("primary_user_id", "==", s_val).stream()
            for ddoc in dev_docs:
                device_ids.add(str(ddoc.id).strip())
                d_data = ddoc.to_dict() or {}
                if d_data.get("device_id"):
                    device_ids.add(str(d_data.get("device_id")).strip())
                if d_data.get("fingerprint_hash"):
                    fingerprint_hashes.add(str(d_data.get("fingerprint_hash")).strip())
                for u in d_data.get("users", []):
                    if u:
                        user_ids.add(str(u).strip())
        except Exception as e:
            print(f"⚠️ Error querying devices by primary_user_id ({s_val}): {e}")

        try:
            dev_docs = db.collection("devices").where("users", "array_contains", s_val).stream()
            for ddoc in dev_docs:
                device_ids.add(str(ddoc.id).strip())
                d_data = ddoc.to_dict() or {}
                if d_data.get("device_id"):
                    device_ids.add(str(d_data.get("device_id")).strip())
                if d_data.get("fingerprint_hash"):
                    fingerprint_hashes.add(str(d_data.get("fingerprint_hash")).strip())
                for u in d_data.get("users", []):
                    if u:
                        user_ids.add(str(u).strip())
        except Exception as e:
            print(f"⚠️ Error querying devices by users array ({s_val}): {e}")

    # 3. جلب المستندات التكميلية من devices بواسطة device_id و fingerprint_hash
    for dev_id in list(device_ids):
        try:
            dev_doc = db.collection("devices").document(dev_id).get()
            if dev_doc.exists:
                d_data = dev_doc.to_dict() or {}
                if d_data.get("fingerprint_hash"):
                    fingerprint_hashes.add(str(d_data.get("fingerprint_hash")).strip())
                for u in d_data.get("users", []):
                    if u:
                        user_ids.add(str(u).strip())
        except Exception:
            pass

    for fp_hash in list(fingerprint_hashes):
        try:
            fp_docs = db.collection("devices").where("fingerprint_hash", "==", fp_hash).stream()
            for ddoc in fp_docs:
                device_ids.add(str(ddoc.id).strip())
                d_data = ddoc.to_dict() or {}
                for u in d_data.get("users", []):
                    if u:
                        user_ids.add(str(u).strip())
        except Exception:
            pass

    # 4. جمع كافة حسابات المستخدمين المرتبطة بـ devices أو fingerprint_hash في مجموعة users
    processed_uids = set()
    for uid in list(user_ids):
        if uid in processed_uids:
            continue
        processed_uids.add(uid)
        uref, udoc = _find_user_doc(db, uid)
        if udoc and udoc.exists:
            if not any(r.id == udoc.id for r in user_refs):
                user_refs.append(uref)

    for dev_id in list(device_ids):
        try:
            u_docs = db.collection("users").where("device_id", "==", dev_id).stream()
            for udoc in u_docs:
                if not any(r.id == udoc.id for r in user_refs):
                    user_refs.append(udoc.reference)
                    user_ids.add(str(udoc.id))
        except Exception:
            pass

    for fp_hash in list(fingerprint_hashes):
        try:
            u_docs = db.collection("users").where("fingerprint_hash", "==", fp_hash).stream()
            for udoc in u_docs:
                if not any(r.id == udoc.id for r in user_refs):
                    user_refs.append(udoc.reference)
                    user_ids.add(str(udoc.id))
        except Exception:
            pass

    return device_ids, fingerprint_hashes, user_refs, user_ids


def _find_associated_devices(db, user_doc, tg_id_str):
    """دالة مساعدة للتوافقية تقتصر على إرجاع مجموعة معرفات الأجهزة"""
    device_ids, _, _, _ = _find_associated_devices_and_users(db, user_doc, tg_id_str)
    return device_ids


def _parse_to_timestamp(val):
    """تحويل قيم التواريخ المختلفة إلى Timestamp بالثواني بأمان"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        if val > 1e11:
            return float(val / 1000.0)
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
            parsed_num = float(val_str)
            if parsed_num > 1e11:
                return parsed_num / 1000.0
            return parsed_num
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
    """حظر مستخدم وتحديث حقول الحظر وحظر كافة أجهزته المربوطة والحسابات المشتركة معها"""
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

        # 1. جمع كافة الأجهزة وبصمات الأصابع والحسابات المربوطة
        device_ids, fp_hashes, user_refs, user_ids = _find_associated_devices_and_users(db, user_doc, tg_id_str)

        # 2. تحديث جميع الحسابات المرتبطة في مجموعة users
        for uref in user_refs:
            try:
                uref.update({
                    "banned": True,
                    "is_banned": True,
                    "ban": True,
                    "status": "banned",
                    "ban_reason": reason,
                    "banned_at": now_str,
                    "banned_by": admin_name
                })
            except Exception as ue:
                print(f"⚠️ Error updating user ban status for {uref.id}: {ue}")

        # 3. تحديث كافة مستندات الأجهزة في مجموعة devices وفي banned_devices
        for dev_id in device_ids:
            if not dev_id:
                continue
            try:
                dev_ref = db.collection("devices").document(str(dev_id))
                dev_ref.set({
                    "is_banned": True,
                    "banned": True,
                    "ban_reason": reason,
                    "banned_at": now_str,
                    "banned_by": admin_name
                }, merge=True)
            except Exception as de:
                print(f"⚠️ Error setting device doc in devices/{dev_id}: {de}")

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
            try:
                db.collection("banned_devices").document(str(dev_id)).set(ban_payload, merge=True)
            except Exception as bde:
                print(f"⚠️ Error setting banned_devices/{dev_id}: {bde}")

        # 4. تسجيل بصمات الأجهزة المحظورة في banned_devices أيضاً
        for fp in fp_hashes:
            if not fp:
                continue
            try:
                db.collection("banned_devices").document(str(fp)).set({
                    "fingerprint_hash": str(fp),
                    "telegram_id": tg_id_str,
                    "reason": reason,
                    "banned_at": now_str,
                    "banned_by": admin_name,
                    "is_banned": True,
                    "banned": True
                }, merge=True)
            except Exception as fpe:
                print(f"⚠️ Error setting banned_devices fingerprint {fp}: {fpe}")

        try:
            database.log_admin_action(admin_name, f"حظر المستخدم {tg_id_str} والأجهزة المربوطة ({len(device_ids)}) - السبب: {reason}")
        except Exception:
            pass

        return True, f"تم حظر المستخدم {tg_id_str} وجميع أجهزته والحسابات المربوطة بها بنجاح"
    except Exception as e:
        print(f"❌ Error banning user {tg_id}: {e}")
        return False, f"حدث خطأ أثناء حظر المستخدم: {e}"


# 🟢 دالة فك الحظر الشاملة المحدثة
def unban_user_db(tg_id, admin_name="السوبر أدمن"):
    """فك الحظر الشامل عن المستخدم وجميع أجهزته وبصماتها والحسابات المربوطة بها"""
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

        # 1. جمع كافة الأجهزة وبصمات الأصابع والحسابات المربوطة
        device_ids, fp_hashes, user_refs, user_ids = _find_associated_devices_and_users(db, user_doc, tg_id_str)

        # 2. فك الحظر عن كافة الحسابات المربوطة في مجموعة users
        for uref in user_refs:
            try:
                uref.update({
                    "banned": False,
                    "is_banned": False,
                    "ban": False,
                    "status": "active",
                    "ban_reason": "",
                    "unbanned_at": now_str,
                    "unbanned_by": admin_name
                })
            except Exception as ue:
                print(f"⚠️ Error unbanning user doc {uref.id}: {ue}")

        # 3. فك الحظر عن كافة مستندات الأجهزة في مجموعة devices وحذف السجلات من banned_devices
        for dev_id in device_ids:
            if not dev_id:
                continue
            try:
                dev_ref = db.collection("devices").document(str(dev_id))
                dev_ref.set({
                    "is_banned": False,
                    "banned": False,
                    "unbanned_at": now_str,
                    "unbanned_by": admin_name
                }, merge=True)
            except Exception as de:
                print(f"⚠️ Error unbanning device doc in devices/{dev_id}: {de}")

            try:
                db.collection("banned_devices").document(str(dev_id)).delete()
            except Exception:
                pass

        # 4. فك حظر كافة بصمات الأجهزة من banned_devices
        for fp in fp_hashes:
            if not fp:
                continue
            try:
                db.collection("banned_devices").document(str(fp)).delete()
            except Exception:
                pass

        # 5. تنظيف أي سجلات تخص الحسابات نفسها في banned_devices
        for uid in user_ids:
            try:
                db.collection("banned_devices").document(str(uid)).delete()
            except Exception:
                pass

        try:
            database.log_admin_action(admin_name, f"فك الحظر الشامل عن المستخدم {tg_id_str} وجميع أجهزته المربوطة")
        except Exception:
            pass

        return True, f"تم فك الحظر الشامل عن المستخدم {tg_id_str} وجميع أجهزته بنجاح"
    except Exception as e:
        print(f"❌ Error unbanning user {tg_id}: {e}")
        return False, f"حدث خطأ أثناء فك الحظر: {e}"


# 🚫 دالة جلب كافة الحسابات والأجهزة المحظورة بالنظام بالتفاصيل
def get_banned_users_db():
    """جلب قائمة بكل المستخدمين المحظورة حساباتهم أو أجهزتهم بجميع بيانات التفاعل والتفاصيل"""
    try:
        db = database.get_db()
        if not db:
            return []

        banned_map = {}

        # 1. البحث في مجموعة users عن الحسابات المحظورة
        try:
            users_docs = db.collection("users").stream()
            for u in users_docs:
                d = u.to_dict() or {}
                tg_id_str = str(d.get("telegram_id") or d.get("tg_id") or u.id).strip()

                is_banned = bool(
                    d.get("banned") or 
                    d.get("is_banned") or 
                    d.get("ban") or 
                    d.get("status") == "banned"
                )

                if is_banned:
                    name = d.get("first_name") or d.get("name") or d.get("username") or f"مستخدم ({tg_id_str})"
                    username = d.get("username", "—")
                    if username and username != "—" and not username.startswith("@"):
                        username = f"@{username}"

                    reason = d.get("ban_reason") or d.get("reason") or "تم الحظر من قبل الإدارة العليا"
                    banned_at = d.get("banned_at") or d.get("ban_date") or d.get("created_at") or "غير محدد"
                    banned_by = d.get("banned_by") or "السوبر أدمن"

                    banned_map[tg_id_str] = {
                        "telegram_id": tg_id_str,
                        "tg_id": tg_id_str,
                        "name": name,
                        "username": username,
                        "ban_reason": reason,
                        "reason": reason,
                        "banned_at": str(banned_at),
                        "banned_by": str(banned_by)
                    }
        except Exception as e:
            print(f"⚠️ Error streaming users for banned list: {e}")

        # 2. جلب البيانات والتأكيدات من مجموعة banned_devices
        try:
            bd_docs = db.collection("banned_devices").stream()
            for bd in bd_docs:
                bd_data = bd.to_dict() or {}
                tg_id_str = str(bd_data.get("telegram_id") or bd_data.get("tg_id") or bd_data.get("user_id") or "").strip()

                if tg_id_str and tg_id_str not in banned_map:
                    _, u_doc = _find_user_doc(db, tg_id_str)
                    u_data = u_doc.to_dict() if (u_doc and u_doc.exists) else {}

                    name = u_data.get("first_name") or u_data.get("name") or u_data.get("username") or f"مستخدم ({tg_id_str})"
                    username = u_data.get("username", "—")
                    if username and username != "—" and not username.startswith("@"):
                        username = f"@{username}"

                    reason = bd_data.get("reason") or bd_data.get("ban_reason") or "حظر جهاز / حساب"
                    banned_at = bd_data.get("banned_at") or "غير محدد"
                    banned_by = bd_data.get("banned_by") or "السوبر أدمن"

                    banned_map[tg_id_str] = {
                        "telegram_id": tg_id_str,
                        "tg_id": tg_id_str,
                        "name": name,
                        "username": username,
                        "ban_reason": reason,
                        "reason": reason,
                        "banned_at": str(banned_at),
                        "banned_by": str(banned_by)
                    }
                elif tg_id_str and tg_id_str in banned_map:
                    if bd_data.get("reason") and banned_map[tg_id_str]["ban_reason"] == "تم الحظر من قبل الإدارة العليا":
                        banned_map[tg_id_str]["ban_reason"] = bd_data.get("reason")
                        banned_map[tg_id_str]["reason"] = bd_data.get("reason")
                    if bd_data.get("banned_at") and banned_map[tg_id_str]["banned_at"] == "غير محدد":
                        banned_map[tg_id_str]["banned_at"] = str(bd_data.get("banned_at"))
        except Exception as e:
            print(f"⚠️ Error streaming banned_devices for banned list: {e}")

        return list(banned_map.values())
    except Exception as e:
        print(f"❌ Error fetching banned users db: {e}")
        return []


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


# 📊 دالة التحليلات العامة المحدثة مع دعم الفلترة الزمنية والنشاط اليومي المتجدد
def get_system_global_analytics(limit=500, start_date=None, end_date=None):
    """تحليلات النظام الكلية مع تقييد الحجم ودعم المدى الزمني والاحتساب التلقائي للنشاط اليومي"""
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

        # 1. جلب المحظورين أولاً لمنع البطء
        banned_list = get_banned_users_db()
        banned_ids_set = {str(bu.get("telegram_id")).strip() for bu in banned_list if bu.get("telegram_id")}
        banned_users_count = len(banned_ids_set)

        # 2. احتساب بداية اليوم الحالي (ساعة 00:00:00 بتوقيت السيرفر) لتصفير وتجديد عداد النشاط اليومي تلقائياً
        now_dt = datetime.now()
        start_of_today_dt = now_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_today_ts = start_of_today_dt.timestamp()

        # 3. تحويل التاريخين (start_date و end_date) إلى Timestamp عند توفرهما للفلترة الزمنية
        filter_start_ts = None
        filter_end_ts = None

        if start_date:
            date_str = str(start_date).strip()
            filter_start_ts = _parse_to_timestamp(f"{date_str} 00:00:00") if len(date_str) == 10 else _parse_to_timestamp(date_str)
        if end_date:
            date_str = str(end_date).strip()
            filter_end_ts = _parse_to_timestamp(f"{date_str} 23:59:59") if len(date_str) == 10 else _parse_to_timestamp(date_str)

        # 4. استعلام محدد الحجم لمنع انتهاء وقت الاتصال (Timeout)
        users_docs = db.collection("users").limit(limit).stream()

        total_users = 0
        active_today_count = 0
        total_balance_zn = 0.0
        total_ad_balance = 0.0

        user_activity_list = []

        for u in users_docs:
            total_users += 1
            try:
                d = u.to_dict() or {}
                tg_id_str = str(d.get("telegram_id") or d.get("tg_id") or u.id).strip()

                # الأرصدة المتداولة ورصيد التعدين
                bal = _safe_float(d.get("balance") or d.get("zn_balance"))
                ad_bal = _safe_float(d.get("ad_balance"))
                total_balance_zn += bal
                total_ad_balance += ad_bal

                # فحص الحظر
                is_banned = (tg_id_str in banned_ids_set) or bool(
                    d.get("banned") or 
                    d.get("is_banned") or 
                    d.get("ban") or 
                    d.get("status") == "banned"
                )

                # قراءة التفاعل والنشاط
                last_active_raw = (
                    d.get("last_active_at") or
                    d.get("last_active") or 
                    d.get("last_seen") or 
                    d.get("updated_at") or 
                    d.get("last_login") or 
                    d.get("last_seen_at")
                )
                last_active_ts = _parse_to_timestamp(last_active_raw)
                
                # فحص النشاط اليومي المتجدد (إذا كان أحدث من أو يساوي منتصف ليل اليوم)
                is_active_today = False
                if last_active_ts is not None and last_active_ts >= start_of_today_ts:
                    is_active_today = True
                    active_today_count += 1

                # التحقق من وقوع نشاط المستخدم داخل النطاق الزمني المحدد للفلتر (إن وجد)
                in_time_range = True
                if filter_start_ts is not None and (last_active_ts is None or last_active_ts < filter_start_ts):
                    in_time_range = False
                if filter_end_ts is not None and (last_active_ts is None or last_active_ts > filter_end_ts):
                    in_time_range = False

                # قراءة حقول التعدين والضغط والمهام للتطبيق
                tap_cnt = _safe_int(d.get("tap_count")) or _safe_int(d.get("taps")) or _safe_int(d.get("clicks")) or _safe_int(d.get("total_clicks"))
                act_cnt = _safe_int(d.get("activity_count")) or _safe_int(d.get("interactions"))
                tasks_cnt = _safe_int(d.get("completed_tasks"))
                bets_cnt = _safe_int(d.get("total_bets"))
                refs_cnt = _safe_int(d.get("referrals")) or _safe_int(d.get("referrals_count"))
                mined_val = _safe_float(d.get("total_mined"))

                interactions = tap_cnt + act_cnt + tasks_cnt + bets_cnt + (1 if mined_val > 0 else 0)
                if interactions == 0:
                    if is_active_today or bal > 0 or tasks_cnt > 0:
                        interactions = max(1, tasks_cnt, refs_cnt)

                name = d.get("first_name") or d.get("name") or d.get("username") or f"مستخدم ({tg_id_str})"
                username = d.get("username", "—")
                if username and username != "—" and not username.startswith("@"):
                    username = f"@{username}"

                last_active_disp = d.get("last_active_str") or d.get("last_seen_str") or ("نشط اليوم" if is_active_today else "سابقاً")

                # إدراج المستخدم في قائمة الأكثر نشاطاً إذا كان يطابق الفلتر الزمني
                if in_time_range:
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

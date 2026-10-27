# -*- coding: utf-8 -*-
"""
super_admin/super_admin_db.py
المحرك الكامل لقاعدة بيانات الإدارة العليا والحظر والأمان والتحليلات على Supabase (PostgreSQL)
"""
import time
from datetime import datetime, timezone
from psycopg2.extras import RealDictCursor, Json
import database


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
                return dt.replace(tzinfo=timezone.utc).timestamp()
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


def _collect_associated_network(cur, clean_id):
    """
    جمع كافة معرفات الأجهزة (device_ids)، بصمات المتصفح/العتاد (fingerprint_hashes)،
    ومعرفات جميع الحسابات المشتركة والمرتبطة بالمستخدم داخل PostgreSQL.
    """
    device_ids = set()
    fp_hashes = set()
    user_ids = {clean_id}

    # 1. جلب بيانات المستخدم الأساسي
    cur.execute("""
        SELECT tg_id, device_id, fingerprint_hash
        FROM users
        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
    """, (clean_id, clean_id, clean_id))
    for r in cur.fetchall():
        if r.get("tg_id"):
            user_ids.add(str(r["tg_id"]).strip())
        if r.get("device_id"):
            device_ids.add(str(r["device_id"]).strip())
        if r.get("fingerprint_hash"):
            fp_hashes.add(str(r["fingerprint_hash"]).strip())

    # 2. البحث في جدول devices عن الأجهزة المربوطة بهذا المستخدم
    cur.execute("""
        SELECT device_id, primary_user_id, users, fingerprint_hash
        FROM devices
        WHERE primary_user_id = %s
           OR users @> %s::jsonb
    """, (clean_id, Json([clean_id])))
    for d in cur.fetchall():
        if d.get("device_id"):
            device_ids.add(str(d["device_id"]).strip())
        if d.get("fingerprint_hash"):
            fp_hashes.add(str(d["fingerprint_hash"]).strip())
        if d.get("primary_user_id"):
            user_ids.add(str(d["primary_user_id"]).strip())
        if isinstance(d.get("users"), list):
            for u in d["users"]:
                if u:
                    user_ids.add(str(u).strip())

    # 3. البحث في جدول banned_devices عن أي سجلات سابقة لهذا المستخدم
    cur.execute("""
        SELECT device_id, fingerprint_hash, banned_user_id
        FROM banned_devices
        WHERE banned_user_id = %s OR device_id = %s
    """, (clean_id, clean_id))
    for bd in cur.fetchall():
        if bd.get("device_id"):
            device_ids.add(str(bd["device_id"]).strip())
        if bd.get("fingerprint_hash"):
            fp_hashes.add(str(bd["fingerprint_hash"]).strip())
        if bd.get("banned_user_id"):
            user_ids.add(str(bd["banned_user_id"]).strip())

    # 4. توسيع البحث: جلب كل المستخدمين والأجهزة التي تشترك في نفس device_ids أو fp_hashes
    if device_ids or fp_hashes:
        dev_list = list(device_ids) if device_ids else ['__NONE__']
        fp_list = list(fp_hashes) if fp_hashes else ['__NONE__']

        cur.execute("""
            SELECT device_id, primary_user_id, users, fingerprint_hash
            FROM devices
            WHERE device_id = ANY(%s) OR fingerprint_hash = ANY(%s)
        """, (dev_list, fp_list))
        for d in cur.fetchall():
            if d.get("device_id"):
                device_ids.add(str(d["device_id"]).strip())
            if d.get("fingerprint_hash"):
                fp_hashes.add(str(d["fingerprint_hash"]).strip())
            if d.get("primary_user_id"):
                user_ids.add(str(d["primary_user_id"]).strip())
            if isinstance(d.get("users"), list):
                for u in d["users"]:
                    if u:
                        user_ids.add(str(u).strip())

        cur.execute("""
            SELECT tg_id, device_id, fingerprint_hash
            FROM users
            WHERE device_id = ANY(%s) OR fingerprint_hash = ANY(%s)
        """, (list(device_ids) if device_ids else ['__NONE__'], list(fp_hashes) if fp_hashes else ['__NONE__']))
        for u_row in cur.fetchall():
            if u_row.get("tg_id"):
                user_ids.add(str(u_row["tg_id"]).strip())
            if u_row.get("device_id"):
                device_ids.add(str(u_row["device_id"]).strip())
            if u_row.get("fingerprint_hash"):
                fp_hashes.add(str(u_row["fingerprint_hash"]).strip())

    # استثناء حساب الأدمن الرئيسي من شبكة الحظر
    user_ids = {u for u in user_ids if u and not database.is_admin_exempt(u)}
    device_ids = {d for d in device_ids if d}
    fp_hashes = {f for f in fp_hashes if f}

    return device_ids, fp_hashes, user_ids


# ==================== تعديل الأرصدة وتصفير الحسابات ====================

def modify_user_balance_admin(tg_id, amount, balance_type="balance", operation="add", admin_name="السوبر أدمن"):
    """تعديل رصيد مستخدم (إضافة / خصم / تعيين) في Supabase PostgreSQL"""
    clean_id = database._sanitize_id(tg_id)
    if not clean_id:
        return False, "معرف مستخدم غير صالح", 0.0

    col_map = {
        "balance": "balance",
        "zn": "balance",
        "zn_balance": "balance",
        "znx": "znx_balance",
        "znx_balance": "znx_balance",
        "usd": "usd_balance",
        "usdt": "usd_balance",
        "usd_balance": "usd_balance",
        "ad": "ad_balance",
        "ad_balance": "ad_balance"
    }
    col = col_map.get(str(balance_type).lower().strip(), "balance")
    amt = _safe_float(amount, 0.0)
    op = str(operation).lower().strip()

    try:
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(f"""
                    SELECT tg_id, COALESCE({col}, 0.0) AS current_val
                    FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                if not row:
                    return False, "المستخدم غير موجود في قاعدة البيانات", 0.0

                current_val = _safe_float(row.get("current_val"), 0.0)
                if op in ("add", "plus"):
                    new_val = round(current_val + abs(amt), 4)
                elif op in ("subtract", "sub", "minus"):
                    new_val = round(max(0.0, current_val - abs(amt)), 4)
                elif op == "set":
                    new_val = round(max(0.0, amt), 4)
                else:
                    return False, "نوع العملية غير معروف", current_val

                cur.execute(f"""
                    UPDATE users
                    SET {col} = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                """, (new_val, clean_id, clean_id, clean_id))

        database.log_admin_action(
            admin_name,
            f"تعديل رصيد ({col}) للمستخدم {clean_id}: من {current_val} إلى {new_val}",
            user_id=clean_id,
            action=f"modify_{col}_{op}",
            amount=amt
        )
        return True, f"تم تعديل رصيد {col} بنجاح إلى {new_val}", new_val
    except Exception as e:
        print(f"❌ Error modifying user balance: {e}")
        return False, f"حدث خطأ أثناء تعديل الرصيد: {e}", 0.0


def reset_user_account_admin(tg_id, admin_name="السوبر أدمن"):
    """تصفير بيانات وحساب مستخدم بالكامل في Supabase PostgreSQL"""
    clean_id = database._sanitize_id(tg_id)
    if not clean_id:
        return False, "معرف غير صالح"

    try:
        with database.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users
                    SET balance = 0.0,
                        ad_balance = 0.0,
                        usd_balance = 0.0,
                        znx_balance = 0.0,
                        hourly_rate = 0.10,
                        mined_points = 0.0,
                        total_mined = 0.0,
                        farm_level = 1,
                        storage_level = 0,
                        upgrades_count = 0,
                        upgrades = '{}'::jsonb,
                        total_bets = 0.0,
                        total_wins = 0.0,
                        total_losses = 0.0,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    RETURNING tg_id
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                if not row:
                    return False, "المستخدم غير موجود"

                cur.execute("DELETE FROM completed_tasks WHERE tg_id = %s", (clean_id,))

        database.log_admin_action(
            admin_name,
            f"تصفير حساب المستخدم {clean_id} بالكامل",
            user_id=clean_id,
            action="reset_account"
        )
        return True, f"تم إعادة تصفير حساب المستخدم {clean_id} بنجاح!"
    except Exception as e:
        print(f"❌ Error resetting user account: {e}")
        return False, f"حدث خطأ أثناء تصفير الحساب: {e}"


# ==================== نظام الحظر وفك الحظر الشامل ====================

def ban_user_db(tg_id, reason="تم الحظر من قبل الإدارة العليا", admin_name="السوبر أدمن"):
    """حظر مستخدم وحظر جميع أجهزته وبصماته والحسابات المشتركة معه في Supabase PostgreSQL"""
    clean_id = database._sanitize_id(tg_id)
    if not clean_id:
        return False, "معرف المستخدم مطلوب"

    if database.is_admin_exempt(clean_id):
        return False, "لا يمكن حظر حساب المدير العام للنظام!"

    clean_reason = str(reason or "تم الحظر من قبل الإدارة العليا").strip()
    clean_admin = str(admin_name or "السوبر أدمن").strip()

    try:
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT tg_id FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                if not cur.fetchone():
                    return False, f"المستخدم رقم ({clean_id}) غير مسجل في النظام"

                device_ids, fp_hashes, user_ids = _collect_associated_network(cur, clean_id)
                target_users = sorted(list(user_ids)) if user_ids else [clean_id]
                primary_fp = next(iter(fp_hashes), None)

                # 1. حظر كافة الحسابات المرتبطة في جدول users
                cur.execute("""
                    UPDATE users
                    SET is_banned = TRUE,
                        banned = TRUE,
                        status = 'banned',
                        ban_reason = %s,
                        banned_at = CURRENT_TIMESTAMP,
                        banned_by = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tg_id = ANY(%s) OR user_id = ANY(%s) OR telegram_id = ANY(%s)
                """, (clean_reason, clean_admin, target_users, target_users, target_users))

                # 2. تحديث وحظر كافة الأجهزة في جدول devices و banned_devices
                for dev_id in device_ids:
                    cur.execute("""
                        INSERT INTO devices (device_id, primary_user_id, users, fingerprint_hash, last_seen, is_banned, ban_reason, banned_at, banned_by)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP, TRUE, %s, CURRENT_TIMESTAMP, %s)
                        ON CONFLICT (device_id) DO UPDATE
                        SET is_banned = TRUE,
                            ban_reason = EXCLUDED.ban_reason,
                            banned_at = CURRENT_TIMESTAMP,
                            banned_by = EXCLUDED.banned_by
                    """, (dev_id, clean_id, Json(target_users), primary_fp, clean_reason, clean_admin))

                    cur.execute("""
                        INSERT INTO banned_devices (device_id, fingerprint_hash, banned_user_id, reason, banned_by, banned_at)
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (device_id) DO UPDATE
                        SET fingerprint_hash = COALESCE(EXCLUDED.fingerprint_hash, banned_devices.fingerprint_hash),
                            banned_user_id = EXCLUDED.banned_user_id,
                            reason = EXCLUDED.reason,
                            banned_by = EXCLUDED.banned_by,
                            banned_at = CURRENT_TIMESTAMP
                    """, (dev_id, primary_fp, clean_id, clean_reason, clean_admin))

                # 3. إدراج بصمات المتصفح/العتاد في banned_devices لمنع فتح متصفح آخر
                for fp in fp_hashes:
                    cur.execute("""
                        INSERT INTO banned_devices (device_id, fingerprint_hash, banned_user_id, reason, banned_by, banned_at)
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (device_id) DO UPDATE
                        SET fingerprint_hash = EXCLUDED.fingerprint_hash,
                            banned_user_id = EXCLUDED.banned_user_id,
                            reason = EXCLUDED.reason,
                            banned_by = EXCLUDED.banned_by,
                            banned_at = CURRENT_TIMESTAMP
                    """, (fp, fp, clean_id, clean_reason, clean_admin))

                # 4. إذا لم يكن للمستخدم جهاز مسجل بعد، نسجل معرفه في banned_devices لضمان التوثيق
                if not device_ids and not fp_hashes:
                    cur.execute("""
                        INSERT INTO banned_devices (device_id, banned_user_id, reason, banned_by, banned_at)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (device_id) DO UPDATE
                        SET banned_user_id = EXCLUDED.banned_user_id,
                            reason = EXCLUDED.reason,
                            banned_by = EXCLUDED.banned_by,
                            banned_at = CURRENT_TIMESTAMP
                    """, (f"user_ban_{clean_id}", clean_id, clean_reason, clean_admin))

        database.log_admin_action(
            clean_admin,
            f"حظر المستخدم {clean_id} والحسابات المشتركة ({len(target_users)}) والأجهزة ({len(device_ids)}) - السبب: {clean_reason}",
            user_id=clean_id,
            action="ban_user"
        )
        return True, f"تم حظر المستخدم {clean_id} وجميع أجهزته والحسابات المشتركة معه ({len(target_users)}) بنجاح"
    except Exception as e:
        print(f"❌ Error banning user {tg_id}: {e}")
        return False, f"حدث خطأ أثناء حظر المستخدم: {e}"


def unban_user_db(tg_id, admin_name="السوبر أدمن"):
    """
    فك الحظر الشامل عن المستخدم وجميع أجهزته وبصماته،
    وإعادة ضبط ملكية الجهاز للمستخدم المفكوك حظره حتى لا يحظره النظام التلقائي مرة أخرى.
    """
    clean_id = database._sanitize_id(tg_id)
    if not clean_id:
        return False, "معرف المستخدم مطلوب"

    clean_admin = str(admin_name or "السوبر أدمن").strip()

    try:
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                device_ids, fp_hashes, user_ids = _collect_associated_network(cur, clean_id)
                target_users = sorted(list(user_ids | {clean_id}))
                other_users = [u for u in target_users if u != clean_id]

                # 1. فك الحظر عن المستخدم وجميع الحسابات التي حُظرت معه في جدول users
                cur.execute("""
                    UPDATE users
                    SET is_banned = FALSE,
                        banned = FALSE,
                        status = 'active',
                        ban_reason = NULL,
                        unbanned_at = CURRENT_TIMESTAMP,
                        unbanned_by = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tg_id = ANY(%s) OR user_id = ANY(%s) OR telegram_id = ANY(%s)
                """, (clean_admin, target_users, target_users, target_users))

                # 2. فك ارتباط بصمة الجهاز عن الحسابات الثانوية الأخرى حتى لا تتصادم مع الحساب الأصلي فور دخوله
                if other_users:
                    cur.execute("""
                        UPDATE users
                        SET device_id = NULL,
                            fingerprint_hash = NULL
                        WHERE tg_id = ANY(%s) OR user_id = ANY(%s) OR telegram_id = ANY(%s)
                    """, (other_users, other_users, other_users))

                # 3. تحديث جدول devices لإلغاء الحظر وتخصيص الجهاز للمستخدم المفكوك حظره فقط
                if device_ids or fp_hashes:
                    dev_list = list(device_ids) if device_ids else ['__NONE__']
                    fp_list = list(fp_hashes) if fp_hashes else ['__NONE__']
                    cur.execute("""
                        UPDATE devices
                        SET is_banned = FALSE,
                            ban_reason = NULL,
                            primary_user_id = %s,
                            users = %s,
                            last_seen = CURRENT_TIMESTAMP
                        WHERE device_id = ANY(%s)
                           OR fingerprint_hash = ANY(%s)
                           OR primary_user_id = ANY(%s)
                    """, (clean_id, Json([clean_id]), dev_list, fp_list, target_users))

                # 4. مسح كافة قيود الحظر من جدول banned_devices
                all_keys_to_delete = list(device_ids | fp_hashes | set(target_users) | {f"user_ban_{u}" for u in target_users})
                if all_keys_to_delete:
                    cur.execute("""
                        DELETE FROM banned_devices
                        WHERE device_id = ANY(%s)
                           OR fingerprint_hash = ANY(%s)
                           OR banned_user_id = ANY(%s)
                    """, (all_keys_to_delete, all_keys_to_delete, target_users))

        database.log_admin_action(
            clean_admin,
            f"فك الحظر الشامل عن المستخدم {clean_id} وتنظيف الأجهزة المرتبطة ({len(device_ids)})",
            user_id=clean_id,
            action="unban_user"
        )
        return True, f"تم فك الحظر الشامل عن المستخدم {clean_id} وجميع أجهزته بنجاح"
    except Exception as e:
        print(f"❌ Error unbanning user {tg_id}: {e}")
        return False, f"حدث خطأ أثناء فك الحظر: {e}"


def get_banned_users_db():
    """جلب قائمة شاملة بكل المستخدمين المحظورين من Supabase PostgreSQL"""
    try:
        banned_map = {}
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. جلب المحظورين من جدول users
                cur.execute("""
                    SELECT tg_id, first_name, name, username, ban_reason, banned_at, updated_at, banned_by, device_id
                    FROM users
                    WHERE COALESCE(is_banned, FALSE) = TRUE
                       OR COALESCE(banned, FALSE) = TRUE
                       OR status = 'banned'
                    ORDER BY COALESCE(banned_at, updated_at) DESC NULLS LAST
                """)
                for r in cur.fetchall():
                    tg_id_str = str(r.get("tg_id") or "").strip()
                    if not tg_id_str:
                        continue
                    name = r.get("first_name") or r.get("name") or r.get("username") or f"مستخدم ({tg_id_str})"
                    username = r.get("username") or "—"
                    if username != "—" and not str(username).startswith("@"):
                        username = f"@{username}"
                    reason = r.get("ban_reason") or "حظر أمني / تعدد حسابات"
                    dt_val = r.get("banned_at") or r.get("updated_at")
                    banned_at_str = dt_val.strftime("%Y-%m-%d %H:%M:%S") if isinstance(dt_val, datetime) else str(dt_val or "غير محدد")
                    banned_by = r.get("banned_by") or "النظام الأمني"

                    banned_map[tg_id_str] = {
                        "telegram_id": tg_id_str,
                        "tg_id": tg_id_str,
                        "user_id": tg_id_str,
                        "name": name,
                        "username": username,
                        "ban_reason": reason,
                        "reason": reason,
                        "banned_at": banned_at_str,
                        "banned_by": banned_by,
                        "device_id": r.get("device_id") or ""
                    }

                # 2. استكمال أي سجلات إضافية من جدول banned_devices
                cur.execute("""
                    SELECT bd.device_id, bd.banned_user_id, bd.reason, bd.banned_by, bd.banned_at,
                           u.first_name, u.name, u.username
                    FROM banned_devices bd
                    LEFT JOIN users u ON u.tg_id = bd.banned_user_id
                    ORDER BY bd.banned_at DESC NULLS LAST
                """)
                for bd in cur.fetchall():
                    uid = str(bd.get("banned_user_id") or "").strip()
                    if not uid:
                        continue
                    dt_val = bd.get("banned_at")
                    banned_at_str = dt_val.strftime("%Y-%m-%d %H:%M:%S") if isinstance(dt_val, datetime) else str(dt_val or "غير محدد")
                    if uid not in banned_map:
                        name = bd.get("first_name") or bd.get("name") or bd.get("username") or f"مستخدم ({uid})"
                        username = bd.get("username") or "—"
                        if username != "—" and not str(username).startswith("@"):
                            username = f"@{username}"
                        reason = bd.get("reason") or "حظر جهاز / تعدد حسابات"
                        banned_map[uid] = {
                            "telegram_id": uid,
                            "tg_id": uid,
                            "user_id": uid,
                            "name": name,
                            "username": username,
                            "ban_reason": reason,
                            "reason": reason,
                            "banned_at": banned_at_str,
                            "banned_by": str(bd.get("banned_by") or "النظام الأمني"),
                            "device_id": str(bd.get("device_id") or "")
                        }
                    else:
                        if bd.get("reason") and banned_map[uid]["ban_reason"] == "حظر أمني / تعدد حسابات":
                            banned_map[uid]["ban_reason"] = bd.get("reason")
                            banned_map[uid]["reason"] = bd.get("reason")

        return list(banned_map.values())
    except Exception as e:
        print(f"❌ Error fetching banned users db: {e}")
        return []


def get_user_security_details_db(tg_id):
    """جلب تقرير أمني ومالي شامل عن المستخدم والأجهزة والحسابات المشتركة معه"""
    clean_id = database._sanitize_id(tg_id)
    if not clean_id:
        return None
    try:
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                user_row = cur.fetchone()
                if not user_row:
                    return None

                user_dict = dict(user_row)
                for k, v in list(user_dict.items()):
                    if isinstance(v, datetime):
                        user_dict[k] = database.format_iso(v)

                device_ids, fp_hashes, associated_users = _collect_associated_network(cur, clean_id)
                shared_accounts = [u for u in sorted(list(associated_users)) if u != clean_id]

                return {
                    "user": user_dict,
                    "is_banned": bool(user_dict.get("is_banned") or user_dict.get("banned") or user_dict.get("status") == "banned"),
                    "ban_reason": user_dict.get("ban_reason") or "",
                    "device_ids": list(device_ids),
                    "fingerprint_hashes": list(fp_hashes),
                    "shared_accounts": shared_accounts
                }
    except Exception as e:
        print(f"❌ Error fetching user security details: {e}")
        return None


# ==================== إدارة المشرفين والسجلات ====================

def add_moderator_db(tg_id, name, permissions=None, admin_name="السوبر أدمن"):
    """إضافة مشرف جديد وتسجيل صلاحياته في جدول moderators"""
    clean_id = database._sanitize_id(tg_id)
    if not clean_id or not name:
        return False, "معرف المشرف والاسم مطلوبان"

    perms = permissions if isinstance(permissions, dict) else {
        "perm_users": True,
        "perm_security": True,
        "perm_ads": False
    }
    ok = database.add_moderator(clean_id, str(name).strip(), perms, added_by=admin_name)
    if ok:
        return True, f"تمت إضافة المشرف {name} بنجاح"
    return False, "حدث خطأ أثناء إضافة المشرف"


def list_moderators_db():
    """جلب قائمة المشرفين المسجلين"""
    return database.get_moderators()


def remove_moderator_db(tg_id, admin_name="السوبر أدمن"):
    """حذف مشرف من النظام"""
    clean_id = database._sanitize_id(tg_id)
    if not clean_id:
        return False, "معرف المشرف مطلوب"
    ok = database.delete_moderator(clean_id, deleted_by=admin_name)
    if ok:
        return True, f"تم حذف المشرف {clean_id} بنجاح"
    return False, "حدث خطأ أثناء حذف المشرف"


def get_admin_logs(limit=50):
    """جلب سجل الحركات الإدارية الأخير"""
    return database.get_admin_logs(limit=limit)


# ==================== التحليلات العامة والفلترة الزمنية ====================

def get_system_global_analytics(limit=500, start_date=None, end_date=None):
    """تحليلات النظام الكلية من Supabase مع دعم الفلترة الزمنية والنشاط اليومي"""
    try:
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) AS total_users,
                        COUNT(*) FILTER (WHERE COALESCE(is_banned, FALSE) = TRUE OR COALESCE(banned, FALSE) = TRUE OR status = 'banned') AS banned_users,
                        COUNT(*) FILTER (WHERE last_active_at >= DATE_TRUNC('day', NOW())) AS active_today,
                        COALESCE(SUM(balance), 0.0) AS total_circulating_zn,
                        COALESCE(SUM(ad_balance), 0.0) AS total_ad_balance_zn,
                        COALESCE(SUM(znx_balance), 0.0) AS total_circulating_znx,
                        COALESCE(SUM(usd_balance), 0.0) AS total_circulating_usd
                    FROM users;
                """)
                stats = dict(cur.fetchone() or {})

                # إعداد شروط الفلترة الزمنية لقائمة الأكثر تفاعلاً
                where_clauses = ["COALESCE(is_banned, FALSE) = FALSE", "COALESCE(banned, FALSE) = FALSE"]
                params = []

                if start_date and str(start_date).strip():
                    s_str = str(start_date).strip()
                    if len(s_str) == 10:
                        s_str += " 00:00:00"
                    where_clauses.append("last_active_at >= %s::timestamptz")
                    params.append(s_str)

                if end_date and str(end_date).strip():
                    e_str = str(end_date).strip()
                    if len(e_str) == 10:
                        e_str += " 23:59:59"
                    where_clauses.append("last_active_at <= %s::timestamptz")
                    params.append(e_str)

                where_sql = " AND ".join(where_clauses)
                params.append(min(int(limit or 50), 100))

                cur.execute(f"""
                    SELECT
                        tg_id,
                        first_name,
                        name,
                        username,
                        COALESCE(balance, 0.0) AS balance,
                        COALESCE(znx_balance, 0.0) AS znx_balance,
                        COALESCE(interactions, 1) + COALESCE(tap_count, 0) + COALESCE(upgrades_count, 0) AS calc_interactions,
                        last_active_at
                    FROM users
                    WHERE {where_sql}
                    ORDER BY calc_interactions DESC, COALESCE(balance, 0.0) DESC
                    LIMIT %s
                """, tuple(params))

                top_active_users = []
                for r in cur.fetchall():
                    uid = str(r.get("tg_id") or "").strip()
                    u_name = r.get("first_name") or r.get("name") or r.get("username") or f"مستخدم ({uid})"
                    uname = r.get("username") or "—"
                    if uname != "—" and not str(uname).startswith("@"):
                        uname = f"@{uname}"
                    inter_cnt = max(1, int(r.get("calc_interactions") or 1))
                    dt_act = r.get("last_active_at")
                    last_act_str = dt_act.strftime("%Y-%m-%d %H:%M") if isinstance(dt_act, datetime) else "نشط"

                    top_active_users.append({
                        "telegram_id": uid,
                        "user_id": uid,
                        "tg_id": uid,
                        "name": u_name,
                        "username": uname,
                        "interactions": inter_cnt,
                        "activity_count": inter_cnt,
                        "balance": round(float(r.get("balance") or 0.0), 2),
                        "zn_balance": round(float(r.get("balance") or 0.0), 2),
                        "is_banned": False,
                        "last_active": last_act_str
                    })

                top_10 = top_active_users[:10]

                return {
                    "total_users": int(stats.get("total_users") or 0),
                    "active_today": int(stats.get("active_today") or 0),
                    "banned_users": int(stats.get("banned_users") or 0),
                    "total_circulating_zn": round(float(stats.get("total_circulating_zn") or 0.0), 2),
                    "total_ad_balance_zn": round(float(stats.get("total_ad_balance_zn") or 0.0), 2),
                    "total_circulating_znx": round(float(stats.get("total_circulating_znx") or 0.0), 2),
                    "total_circulating_usd": round(float(stats.get("total_circulating_usd") or 0.0), 2),
                    "top_users": top_10,
                    "top_active_users": top_10
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


# ==================== وظائف الإشعارات والبث الجماعي ====================

def get_all_user_ids():
    """استخراج قائمة بكل معرفات المستخدمين النشطين (غير المحظورين)"""
    try:
        with database.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT tg_id FROM users
                    WHERE COALESCE(is_banned, FALSE) = FALSE
                      AND COALESCE(banned, FALSE) = FALSE
                      AND COALESCE(status, 'active') != 'banned'
                      AND tg_id IS NOT NULL
                """)
                return [str(r[0]).strip() for r in cur.fetchall() if r and r[0]]
    except Exception as e:
        print(f"❌ Error fetching user IDs: {e}")
        return []


def get_user_by_id(tg_id):
    """فحص وجود مستخدم محدد وإرجاع بياناته"""
    clean_id = database._sanitize_id(tg_id)
    if not clean_id:
        return False, None
    user_data = database.get_user(clean_id)
    if user_data:
        return True, user_data
    return False, None


def log_broadcast_campaign(admin_name, message, total_targets, success_count, blocked_count):
    """أرشفة وتسجيل نتائج حملة الإرسال الجماعي في جدول broadcasts"""
    try:
        total = int(total_targets or 0)
        sent = int(success_count or 0)
        blocked = int(blocked_count or 0)
        failed = max(0, total - (sent + blocked))
        snippet = (str(message or "")[:100] + "...") if len(str(message or "")) > 100 else str(message or "")

        with database.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO broadcasts (admin_name, message_snippet, total_targets, success_count, blocked_count, failed_count, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """, (str(admin_name or "الأدمن"), snippet, total, sent, blocked, failed))

        database.log_admin_action(
            admin_name,
            f"حملة إرسال جماعي: تم {sent}/{total} | حظروا البوت {blocked} | فشل {failed}",
            action="broadcast_campaign"
        )
        return True
    except Exception as e:
        print(f"❌ Error logging broadcast campaign: {e}")
        return False


def get_latest_broadcast_stats():
    """جلب بيانات أحدث حملة إرسال محفوظة بالتنسيق المتوافق مع الواجهة"""
    try:
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM broadcasts
                    ORDER BY created_at DESC
                    LIMIT 1
                """)
                row = cur.fetchone()
                if not row:
                    return None
                d = dict(row)
                dt_val = d.get("created_at")
                if isinstance(dt_val, datetime):
                    d["created_at_str"] = dt_val.strftime("%Y-%m-%d %H:%M:%S")
                    d["created_at"] = database.format_iso(dt_val)
                else:
                    d["created_at_str"] = str(dt_val or "مؤخراً")

                total = int(d.get("total_targets") or 0)
                sent = int(d.get("success_count") or 0)
                blocked = int(d.get("blocked_count") or 0)
                d["failed_count"] = int(d.get("failed_count") or max(0, total - (sent + blocked)))
                return d
    except Exception as e:
        print(f"❌ Error fetching latest broadcast: {e}")
        return None

# -*- coding: utf-8 -*-
# addons/addons_db.py
import os
import re
import json
import datetime
import logging
import psycopg2
from psycopg2.extras import RealDictCursor, Json
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_addons_tables_ready = False

# الحدود القصوى ومعدلات التعدين والمخازن المتوافقة مع جدول users في Supabase
SYSTEM_LIMITS = {
    "max_upgrade_per_lvl": 50,   # الحد الأقصى لكل مستوى من المستويات الـ 9
    "max_storage_level": 20      # الحد الأقصى لمستوى المخزن
}

# مقدار الزيادة في سرعة التعدين (mining_rate) لكل مستوى من المستويات التسعة
UPGRADE_RATE_BONUS = {
    "lvl1": 0.2,
    "lvl2": 0.5,
    "lvl3": 1.2,
    "lvl4": 2.5,
    "lvl5": 5.0,
    "lvl6": 10.0,
    "lvl7": 20.0,
    "lvl8": 40.0,
    "lvl9": 80.0
}

BASE_MINING_RATE = 0.1
BASE_STORAGE_CAP = 0.3
STORAGE_CAP_PER_LEVEL = 5.0  # كل مستوى مخزن إضافي فوق المستوى 1 يضيف +5 للسعة القصوى


@contextmanager
def _get_db_connection():
    """
    جلب اتصال قاعدة بيانات Supabase بأمان سواء عبر database.get_db_connection
    أو الاتصال المباشر عبر DATABASE_URL.
    """
    import database
    if hasattr(database, 'get_db_connection'):
        with database.get_db_connection() as conn:
            yield conn
    else:
        db_url = os.environ.get('DATABASE_URL') or os.environ.get('SUPABASE_DB_URL')
        conn = psycopg2.connect(db_url)
        try:
            yield conn
        finally:
            conn.close()


def ensure_promo_table():
    """التأكد من وجود جدول promo_codes وجدول سجلات التحكم admin_action_logs في Supabase"""
    global _addons_tables_ready
    if _addons_tables_ready:
        return
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS promo_codes (
                        code VARCHAR(64) PRIMARY KEY,
                        coins DOUBLE PRECISION DEFAULT 0.0,
                        reward_coins DOUBLE PRECISION DEFAULT 0.0,
                        amount DOUBLE PRECISION DEFAULT 0.0,
                        points DOUBLE PRECISION DEFAULT 0.0,
                        max_uses INT DEFAULT 0,
                        used_count INT DEFAULT 0,
                        used_by JSONB DEFAULT '[]'::jsonb,
                        is_active BOOLEAN DEFAULT TRUE,
                        expires_at TIMESTAMPTZ NULL,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );

                    ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS coins DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS reward_coins DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS max_uses INT DEFAULT 0;
                    ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS used_count INT DEFAULT 0;
                    ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS used_by JSONB DEFAULT '[]'::jsonb;
                    ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE;
                    ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ NULL;
                    ALTER TABLE promo_codes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP;

                    CREATE TABLE IF NOT EXISTS admin_action_logs (
                        id SERIAL PRIMARY KEY,
                        admin_id VARCHAR(64),
                        target_type VARCHAR(20),
                        target_id VARCHAR(64),
                        category VARCHAR(32),
                        action VARCHAR(32),
                        action_title VARCHAR(120),
                        description TEXT,
                        affected_count INT DEFAULT 0,
                        snapshot_data JSONB DEFAULT '[]'::jsonb,
                        is_undone BOOLEAN DEFAULT FALSE,
                        is_cleared BOOLEAN DEFAULT FALSE,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        undone_at TIMESTAMPTZ NULL
                    );
                """)
            conn.commit()
        _addons_tables_ready = True
    except Exception as e:
        logger.error(f"Error ensuring addons tables: {e}")


def _sanitize_code(code_name) -> str:
    """تنظيف الكود والسماح فقط بالحروف والأرقام والشرطة لمنع أي حقن أو تلاعب"""
    if not code_name:
        return ""
    cleaned = str(code_name).strip().upper()
    if not re.match(r'^[A-Z0-9_\-]{2,32}$', cleaned):
        return ""
    return cleaned


def _clean_uid(uid) -> str:
    """تنظيف والتحقق من معرف تيليجرام الرقمي"""
    if uid is None:
        return ""
    s = str(uid).strip()
    if s.startswith("ref_"):
        s = s.replace("ref_", "", 1).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if not re.match(r'^\d{3,20}$', s):
        return ""
    return s


def _parse_json_dict(val) -> dict:
    if isinstance(val, dict):
        return dict(val)
    if isinstance(val, str) and val.strip():
        try:
            parsed = json.loads(val)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass
    return {}


# ==================== Promo Code Core Database Operations ====================

def create_promo_code(code_name, reward_coins, duration_value, duration_type, max_uses=0):
    """إنشاء كود مكافأة جديد في Supabase بحساب صلاحيته الزمنية"""
    ensure_promo_table()
    try:
        code_id = _sanitize_code(code_name)
        if not code_id:
            return False, "❌ اسم الكود غير صالح! استخدم حروف إنجليزية وأرقام فقط (2 إلى 32 حرف)."

        try:
            reward_val = round(float(reward_coins), 4)
            duration_val = float(duration_value)
            max_uses_val = int(max_uses or 0)
        except (ValueError, TypeError):
            return False, "❌ يرجى إدخال أرقام صحيحة في خانة العملات والمدة!"

        if reward_val <= 0 or reward_val > 1000000000:
            return False, "❌ قيمة المكافأة يجب أن تكون أكبر من صفر ومنطقية!"
        if duration_val <= 0 or duration_val > 3650:
            return False, "❌ مدة الصلاحية غير منطقية!"
        if max_uses_val < 0:
            return False, "❌ أقصى عدد مستخدمين لا يمكن أن يكون بالسالب!"

        now = datetime.datetime.now(datetime.timezone.utc)
        if duration_type == 'minutes':
            expires_at = now + datetime.timedelta(minutes=duration_val)
        elif duration_type == 'hours':
            expires_at = now + datetime.timedelta(hours=duration_val)
        elif duration_type == 'days':
            expires_at = now + datetime.timedelta(days=duration_val)
        else:
            expires_at = now + datetime.timedelta(hours=duration_val)

        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO promo_codes (
                        code, coins, reward_coins, amount, points,
                        max_uses, used_count, used_by, is_active,
                        expires_at, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, 0, '[]'::jsonb, TRUE, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    ON CONFLICT (code) DO UPDATE SET
                        coins = EXCLUDED.coins,
                        reward_coins = EXCLUDED.reward_coins,
                        amount = EXCLUDED.amount,
                        points = EXCLUDED.points,
                        max_uses = EXCLUDED.max_uses,
                        is_active = TRUE,
                        expires_at = EXCLUDED.expires_at,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    code_id, reward_val, reward_val, reward_val, reward_val,
                    max_uses_val, expires_at
                ))
            conn.commit()

        return True, f"✅ تم إنشاء الكود '{code_id}' بنجاح! ينتهي في {expires_at.strftime('%Y-%m-%d %H:%M UTC')}"
    except Exception as e:
        logger.error(f"❌ خطأ أثناء إنشاء كود المكافأة: {e}")
        return False, "❌ حدث خطأ أثناء إنشاء الكود في قاعدة البيانات."


def get_all_promo_codes():
    """جلب قائمة بكل أكواد المكافآت من Supabase مع التحقق من انتهاء الصلاحية"""
    ensure_promo_table()
    try:
        with _get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        code,
                        COALESCE(NULLIF(reward_coins, 0), NULLIF(coins, 0), amount, 0) AS reward_coins,
                        COALESCE(max_uses, 0) AS max_uses,
                        COALESCE(used_count, 0) AS used_count,
                        COALESCE(is_active, TRUE) AS is_active,
                        expires_at,
                        (expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP) AS is_expired
                    FROM promo_codes
                    ORDER BY created_at DESC
                """)
                rows = cur.fetchall()
                codes_list = []
                for row in rows:
                    item = dict(row)
                    if item.get('expires_at'):
                        item['expires_at'] = item['expires_at'].strftime('%Y-%m-%d %H:%M UTC')
                    else:
                        item['expires_at'] = None
                    codes_list.append(item)
                return codes_list
    except Exception as e:
        logger.error(f"❌ خطأ جلب أكواد المكافآت: {e}")
        return []


def delete_promo_code(code_name):
    """حذف كود مكافأة من Supabase"""
    ensure_promo_table()
    try:
        code_id = _sanitize_code(code_name)
        if not code_id:
            return False, "❌ اسم الكود غير صالح!"

        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM promo_codes WHERE UPPER(code) = %s", (code_id,))
            conn.commit()
        return True, f"🗑️ تم حذف الكود '{code_id}' بنجاح!"
    except Exception as e:
        logger.error(f"Error deleting promo code: {e}")
        return False, "❌ خطأ أثناء حذف الكود."


def toggle_promo_code_status(code_name, is_active):
    """تفعيل أو تعطيل كود المكافأة في Supabase"""
    ensure_promo_table()
    try:
        code_id = _sanitize_code(code_name)
        if not code_id:
            return False, "❌ اسم الكود غير صالح!"

        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE promo_codes
                    SET is_active = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE UPPER(code) = %s
                """, (bool(is_active), code_id))
            conn.commit()

        status_str = "تفعيل" if is_active else "تعطيل"
        return True, f"✅ تم {status_str} الكود '{code_id}' بنجاح!"
    except Exception as e:
        logger.error(f"Error toggling promo code: {e}")
        return False, "❌ حدث خطأ أثناء تعديل حالة الكود."


def redeem_promo_code(telegram_id, code_name):
    """تفعيل الكود بأمان تام في حال تم استدعاؤه من جهة الأدمن API"""
    ensure_promo_table()
    user_id_str = _clean_uid(telegram_id)
    code_id = _sanitize_code(code_name)

    if not user_id_str or not code_id:
        return False, "❌ يرجى إدخال كود صحيح!", 0

    try:
        with _get_db_connection() as conn:
            prev_autocommit = conn.autocommit
            conn.autocommit = False
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT *, (expires_at IS NOT NULL AND expires_at < CURRENT_TIMESTAMP) AS is_expired
                        FROM promo_codes
                        WHERE UPPER(TRIM(code)) = %s
                        FOR UPDATE
                    """, (code_id,))
                    code_row = cur.fetchone()

                    if not code_row:
                        conn.rollback()
                        return False, "❌ الكود غير موجود أو غير صحيح!", 0

                    if not code_row.get('is_active', True):
                        conn.rollback()
                        return False, "❌ هذا الكود معطل حالياً!", 0

                    if code_row.get('is_expired'):
                        conn.rollback()
                        return False, "⏰ للأسف، انتهت صلاحية هذا الكود!", 0

                    used_by = code_row.get('used_by') or []
                    if isinstance(used_by, str):
                        try:
                            used_by = json.loads(used_by)
                        except Exception:
                            used_by = []
                    used_by_strs = [str(u).strip() for u in used_by]

                    if user_id_str in used_by_strs:
                        conn.rollback()
                        return False, "⚠️ لقد استخدمت هذا الكود من قبل! يُسمح بالاستخدام مرة واحدة فقط.", 0

                    max_uses = int(code_row.get('max_uses') if code_row.get('max_uses') is not None else 0)
                    used_count = int(code_row.get('used_count') or 0)
                    if max_uses > 0 and used_count >= max_uses:
                        conn.rollback()
                        return False, "❌ وصل هذا الكود للحد الأقصى من الاستخدامات!", 0

                    reward = float(code_row.get('reward_coins') or code_row.get('coins') or 0)
                    if reward <= 0:
                        conn.rollback()
                        return False, "❌ قيمة مكافأة الكود غير صالحة!", 0

                    cur.execute("""
                        SELECT tg_id, COALESCE(is_banned, FALSE) AS is_banned
                        FROM users
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                        LIMIT 1
                        FOR UPDATE
                    """, (user_id_str, user_id_str, user_id_str))
                    user_row = cur.fetchone()

                    if not user_row:
                        conn.rollback()
                        return False, "❌ حساب المستخدم غير موجود!", 0

                    if user_row.get('is_banned'):
                        conn.rollback()
                        return False, "🚫 حسابك محظور من استخدام الأكواد!", 0

                    used_by_strs.append(user_id_str)
                    cur.execute("""
                        UPDATE promo_codes
                        SET used_count = COALESCE(used_count, 0) + 1,
                            used_by = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE code = %s
                    """, (Json(used_by_strs), code_row['code']))

                    cur.execute("""
                        UPDATE users
                        SET balance = COALESCE(balance, 0.0) + %s,
                            total_earned = COALESCE(total_earned, 0.0) + %s
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    """, (reward, reward, user_id_str, user_id_str, user_id_str))

                    conn.commit()
                    return True, f"🎉 مبروك! تم تفعيل الكود وحصلت على {reward:g} عملة!", reward
            except Exception as tx_e:
                conn.rollback()
                logger.error(f"Transaction error in admin redeem_promo_code: {tx_e}")
                return False, "❌ حدث خطأ أثناء تفعيل الكود.", 0
            finally:
                conn.autocommit = prev_autocommit
    except Exception as e:
        logger.error(f"Database error in redeem_promo_code: {e}")
        return False, "❌ خطأ في الاتصال بقاعدة البيانات.", 0


# ==================== Data Control & User Inspection Operations ====================

def get_user_full_data_for_admin(telegram_id: str) -> dict:
    """جلب كافة تفاصيل حساب اللاعب لعرضها للأدمن قبل التعديل"""
    ensure_promo_table()
    clean_id = _clean_uid(telegram_id)
    if not clean_id:
        return {"success": False, "message": "⚠️ يرجى إدخال رقم ID صحيح!"}

    try:
        with _get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        COALESCE(tg_id, user_id, telegram_id) AS tg_id,
                        first_name,
                        last_name,
                        name,
                        username,
                        COALESCE(balance, 0.0) AS balance,
                        COALESCE(usd_balance, 0.0) AS usd_balance,
                        COALESCE(znx_balance, 0.0) AS znx_balance,
                        COALESCE(total_earned, 0.0) AS total_earned,
                        COALESCE(referrals_count, 0) AS referrals_count,
                        COALESCE(is_banned, FALSE) AS is_banned,
                        COALESCE(farm_level, 1) AS farm_level,
                        COALESCE(storage_level, 1) AS storage_level,
                        COALESCE(extra_storage, 0.0) AS extra_storage,
                        COALESCE(max_cap, 0.3) AS max_cap,
                        COALESCE(mining_rate, 0.1) AS mining_rate,
                        GREATEST(
                            COALESCE(mined_points, 0.0),
                            COALESCE(total_mined, 0.0),
                            COALESCE(mining_points, 0.0),
                            COALESCE(mined_total, 0.0),
                            COALESCE(farm_mined, 0.0)
                        ) AS mined_points,
                        upgrades,
                        COALESCE(upgrades_count, 0) AS upgrades_count,
                        COALESCE(is_vip, FALSE) AS is_vip,
                        COALESCE(vip_active, FALSE) AS vip_active,
                        vip_package,
                        plan,
                        vip_level,
                        vip_expires_at,
                        vip_expiry,
                        vip_status
                    FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))

                row = cur.fetchone()
                if not row:
                    return {"success": False, "message": f"❌ لم يتم العثور على مستخدم يحمل الـ ID: {clean_id}"}

                u = dict(row)
                raw_upgrades = _parse_json_dict(u.get('upgrades'))
                normalized_upgrades = {}
                for i in range(1, 10):
                    k = f"lvl{i}"
                    try:
                        normalized_upgrades[k] = max(0, int(raw_upgrades.get(k, 0)))
                    except (ValueError, TypeError):
                        normalized_upgrades[k] = 0
                u['upgrades'] = normalized_upgrades

                vip_status_dict = _parse_json_dict(u.get('vip_status'))
                is_vip_flag = bool(u.get('is_vip') or u.get('vip_active') or vip_status_dict.get('active'))
                u['is_vip'] = is_vip_flag
                u['vip_active'] = is_vip_flag
                u['vip_package'] = u.get('vip_package') or u.get('plan') or vip_status_dict.get('package') or ''
                u['vip_expires_at'] = (
                    u.get('vip_expires_at')
                    or u.get('vip_expiry')
                    or vip_status_dict.get('expires_at')
                    or ''
                )

                return {
                    "success": True,
                    "user": u,
                    "limits": SYSTEM_LIMITS
                }
    except Exception as e:
        logger.error(f"Error inspecting user {clean_id}: {e}")
        return {"success": False, "message": "❌ حدث خطأ في قاعدة البيانات أثناء فحص اللاعب."}


def _extract_user_snapshot(row: dict) -> dict:
    """أخذ نسخة احتياطية دقيقة لكل الحقول القابلة للتعديل قبل تنفيذ العملية"""
    return {
        "tg_id": str(row.get('tg_id') or row.get('user_id') or row.get('telegram_id') or ''),
        "balance": float(row.get('balance') or 0.0),
        "usd_balance": float(row.get('usd_balance') or 0.0),
        "znx_balance": float(row.get('znx_balance') or 0.0),
        "total_earned": float(row.get('total_earned') or 0.0),
        "referrals_count": int(row.get('referrals_count') or 0),
        "mined_points": float(row.get('mined_points') or 0.0),
        "total_mined": float(row.get('total_mined') or 0.0),
        "mining_points": float(row.get('mining_points') or 0.0),
        "mined_total": float(row.get('mined_total') or 0.0),
        "farm_mined": float(row.get('farm_mined') or 0.0),
        "mining_rate": float(row.get('mining_rate') or BASE_MINING_RATE),
        "farm_level": int(row.get('farm_level') or 1),
        "storage_level": int(row.get('storage_level') or 1),
        "extra_storage": float(row.get('extra_storage') or 0.0),
        "max_cap": float(row.get('max_cap') or BASE_STORAGE_CAP),
        "upgrades": _parse_json_dict(row.get('upgrades')),
        "upgrades_count": int(row.get('upgrades_count') or 0),
        "is_vip": bool(row.get('is_vip') or False),
        "vip_active": bool(row.get('vip_active') or False),
        "vip_package": row.get('vip_package'),
        "plan": row.get('plan'),
        "vip_level": row.get('vip_level'),
        "vip_expires_at": row.get('vip_expires_at'),
        "vip_expiry": row.get('vip_expiry'),
        "vip_expiry_date": row.get('vip_expiry_date'),
        "vip_status": _parse_json_dict(row.get('vip_status'))
    }


def execute_admin_data_action(admin_id: str, payload: dict) -> dict:
    """
    تنفيذ التعديلات الإدارية (إضافة/خصم رصيد، ترقيات سرعة، مخازن، باقات VIP)
    لمستخدم محدد أو لجميع المستخدمين مع حفظ Snapshot كامل للتراجع (Undo).
    """
    ensure_promo_table()

    target_type = str(payload.get('target_type') or 'single').strip().lower()
    if target_type not in ('single', 'all'):
        return {"success": False, "message": "❌ نوع الهدف غير صالح!"}

    target_id = _clean_uid(payload.get('telegram_id')) if target_type == 'single' else 'ALL'
    if target_type == 'single' and not target_id:
        return {"success": False, "message": "⚠️ يرجى إدخال رقم ID صحيح للمستخدم!"}

    category = str(payload.get('category') or '').strip().lower()
    action = str(payload.get('action') or '').strip().lower()

    if category not in ('balance', 'upgrade', 'storage', 'vip'):
        return {"success": False, "message": "❌ قسم التعديل غير معروف!"}

    try:
        with _get_db_connection() as conn:
            prev_autocommit = conn.autocommit
            conn.autocommit = False
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. جلب وقفل الصفوف المستهدفة (FOR UPDATE) لمنع أي تداخل
                    if target_type == 'single':
                        cur.execute("""
                            SELECT * FROM users
                            WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                            LIMIT 1
                            FOR UPDATE
                        """, (target_id, target_id, target_id))
                    else:
                        cur.execute("SELECT * FROM users FOR UPDATE")

                    users_rows = cur.fetchall()
                    if not users_rows:
                        conn.rollback()
                        return {"success": False, "message": "❌ لم يتم العثور على مستخدمين لتطبيق العملية!"}

                    snapshots = []
                    updated_count = 0
                    action_title = ""
                    description = ""

                    # ==================== أولاً: قسم الأرصدة والنقاط ====================
                    if category == 'balance':
                        field = str(payload.get('field') or '').strip()
                        allowed_fields = {
                            'balance': 'عملات ZN',
                            'znx_balance': 'عملات ZNX',
                            'usd_balance': 'رصيد الدولار USD',
                            'mined_points': 'نقاط التعدين',
                            'referrals_count': 'عدد الإحالات'
                        }
                        if field not in allowed_fields:
                            conn.rollback()
                            return {"success": False, "message": "❌ الحقل المطلوب تعديله غير مسموح به!"}

                        if action not in ('add', 'deduct'):
                            conn.rollback()
                            return {"success": False, "message": "❌ نوع العملية غير صالح!"}

                        try:
                            amount = float(payload.get('amount') or 0)
                        except (ValueError, TypeError):
                            amount = 0.0

                        if amount <= 0 or amount > 10000000000:
                            conn.rollback()
                            return {"success": False, "message": "⚠️ يرجى إدخال كمية منطقية أكبر من صفر!"}

                        if field == 'referrals_count':
                            amount = int(amount)

                        sign = 1 if action == 'add' else -1
                        op_word = "إضافة" if action == 'add' else "خصم"
                        field_label = allowed_fields[field]
                        action_title = f"{op_word} {field_label}"
                        description = f"{op_word} {amount:g} في ({field_label})"

                        for u_row in users_rows:
                            snap = _extract_user_snapshot(u_row)
                            snapshots.append(snap)
                            uid = snap['tg_id']

                            if field == 'balance':
                                new_bal = max(0.0, round(snap['balance'] + (sign * amount), 6))
                                new_earned = snap['total_earned'] + amount if action == 'add' else snap['total_earned']
                                cur.execute("""
                                    UPDATE users
                                    SET balance = %s, total_earned = %s, updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (new_bal, new_earned, uid, uid, uid))

                            elif field == 'znx_balance':
                                new_znx = max(0.0, round(snap['znx_balance'] + (sign * amount), 6))
                                cur.execute("""
                                    UPDATE users
                                    SET znx_balance = %s, updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (new_znx, uid, uid, uid))

                            elif field == 'usd_balance':
                                new_usd = max(0.0, round(snap['usd_balance'] + (sign * amount), 6))
                                cur.execute("""
                                    UPDATE users
                                    SET usd_balance = %s, updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (new_usd, uid, uid, uid))

                            elif field == 'mined_points':
                                current_mp = max(
                                    snap['mined_points'],
                                    snap['total_mined'],
                                    snap['mining_points'],
                                    snap['mined_total'],
                                    snap['farm_mined']
                                )
                                new_mp = max(0.0, round(current_mp + (sign * amount), 6))
                                cur.execute("""
                                    UPDATE users
                                    SET mined_points = %s,
                                        total_mined = %s,
                                        mining_points = %s,
                                        mined_total = %s,
                                        farm_mined = %s,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (new_mp, new_mp, new_mp, new_mp, new_mp, uid, uid, uid))

                            elif field == 'referrals_count':
                                new_refs = max(0, int(snap['referrals_count'] + (sign * int(amount))))
                                cur.execute("""
                                    UPDATE users
                                    SET referrals_count = %s, updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (new_refs, uid, uid, uid))

                            updated_count += 1

                    # ==================== ثانياً: ترقيات سرعة التعدين (lvl1 - lvl9) ====================
                    elif category == 'upgrade':
                        level_key = str(payload.get('level_key') or '').strip().lower()
                        if level_key not in UPGRADE_RATE_BONUS:
                            conn.rollback()
                            return {"success": False, "message": "❌ مستوى التعدين المحدد غير صالح (lvl1 - lvl9)!"}

                        if action not in ('add', 'deduct'):
                            conn.rollback()
                            return {"success": False, "message": "❌ نوع العملية غير صالح!"}

                        try:
                            count_delta = int(payload.get('amount') or 1)
                        except (ValueError, TypeError):
                            count_delta = 0

                        if count_delta <= 0 or count_delta > SYSTEM_LIMITS['max_upgrade_per_lvl']:
                            conn.rollback()
                            return {"success": False, "message": "⚠️ عدد الترقيات المدخل غير صالح!"}

                        max_lvl = SYSTEM_LIMITS['max_upgrade_per_lvl']
                        rate_per_unit = UPGRADE_RATE_BONUS[level_key]

                        for u_row in users_rows:
                            snap = _extract_user_snapshot(u_row)
                            upg_dict = dict(snap['upgrades'])
                            current_lvl_val = max(0, int(upg_dict.get(level_key, 0) or 0))

                            if action == 'add':
                                if current_lvl_val >= max_lvl:
                                    if target_type == 'single':
                                        conn.rollback()
                                        return {
                                            "success": False,
                                            "message": f"⚠️ اللاعب وصل بالفعل للحد الأقصى ({max_lvl}) في {level_key}!"
                                        }
                                    continue
                                new_lvl_val = min(max_lvl, current_lvl_val + count_delta)
                            else:
                                if current_lvl_val <= 0:
                                    if target_type == 'single':
                                        conn.rollback()
                                        return {
                                            "success": False,
                                            "message": f"⚠️ اللاعب لا يملك أي ترقيات في {level_key} لسحبها!"
                                        }
                                    continue
                                new_lvl_val = max(0, current_lvl_val - count_delta)

                            actual_diff = new_lvl_val - current_lvl_val
                            if actual_diff == 0:
                                continue

                            snapshots.append(snap)
                            uid = snap['tg_id']
                            upg_dict[level_key] = new_lvl_val

                            # حساب إجمالي عدد الترقيات وسرعة التعدين الجديدة
                            total_upg_count = sum(max(0, int(upg_dict.get(f"lvl{i}", 0) or 0)) for i in range(1, 10))
                            new_mining_rate = max(
                                BASE_MINING_RATE,
                                round(snap['mining_rate'] + (actual_diff * rate_per_unit), 4)
                            )
                            new_farm_level = max(1, total_upg_count + 1)

                            cur.execute("""
                                UPDATE users
                                SET upgrades = %s,
                                    upgrades_count = %s,
                                    mining_rate = %s,
                                    farm_level = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                            """, (Json(upg_dict), total_upg_count, new_mining_rate, new_farm_level, uid, uid, uid))
                            updated_count += 1

                        op_word = "ترقية (+)" if action == 'add' else "سحب (-)"
                        action_title = f"{op_word} سرعة التعدين ({level_key})"
                        description = f"{op_word} بمقدار {count_delta} في المستوى {level_key}"

                    # ==================== ثالثاً: التحكم في المخازن (Storage) ====================
                    elif category == 'storage':
                        if action not in ('add', 'deduct'):
                            conn.rollback()
                            return {"success": False, "message": "❌ نوع العملية غير صالح!"}

                        try:
                            st_delta = int(payload.get('amount') or 1)
                        except (ValueError, TypeError):
                            st_delta = 0

                        max_st = SYSTEM_LIMITS['max_storage_level']
                        if st_delta <= 0 or st_delta > max_st:
                            conn.rollback()
                            return {"success": False, "message": "⚠️ عدد مستويات المخزن غير صالح!"}

                        for u_row in users_rows:
                            snap = _extract_user_snapshot(u_row)
                            curr_st = max(1, int(snap['storage_level'] or 1))

                            if action == 'add':
                                if curr_st >= max_st:
                                    if target_type == 'single':
                                        conn.rollback()
                                        return {
                                            "success": False,
                                            "message": f"⚠️ مخزن اللاعب وصل للحد الأقصى ({max_st}) بالفعل!"
                                        }
                                    continue
                                new_st = min(max_st, curr_st + st_delta)
                            else:
                                if curr_st <= 1:
                                    if target_type == 'single':
                                        conn.rollback()
                                        return {
                                            "success": False,
                                            "message": "⚠️ مخزن اللاعب في المستوى الأساسي (1) ولا يمكن إنقاصه أكثر!"
                                        }
                                    continue
                                new_st = max(1, curr_st - st_delta)

                            if new_st == curr_st:
                                continue

                            snapshots.append(snap)
                            uid = snap['tg_id']

                            new_extra_storage = round((new_st - 1) * STORAGE_CAP_PER_LEVEL, 4)
                            new_max_cap = round(BASE_STORAGE_CAP + new_extra_storage, 4)

                            cur.execute("""
                                UPDATE users
                                SET storage_level = %s,
                                    extra_storage = %s,
                                    max_cap = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                            """, (new_st, new_extra_storage, new_max_cap, uid, uid, uid))
                            updated_count += 1

                        op_word = "ترقية (+)" if action == 'add' else "إنقاص (-)"
                        action_title = f"{op_word} مستوى المخزن"
                        description = f"{op_word} المخزن بمقدار {st_delta} مستويات"

                    # ==================== رابعاً: شحن وإدارة باقات VIP ====================
                    elif category == 'vip':
                        if action not in ('activate', 'deactivate'):
                            conn.rollback()
                            return {"success": False, "message": "❌ إجراء الباقة غير معروف!"}

                        pkg_name = str(payload.get('vip_package') or 'VIP_1').strip()
                        dur_type = str(payload.get('duration_type') or 'days').strip()
                        try:
                            dur_val = float(payload.get('duration_val') or 30)
                        except (ValueError, TypeError):
                            dur_val = 30.0

                        now_utc = datetime.datetime.now(datetime.timezone.utc)
                        if dur_type == 'hours':
                            exp_dt = now_utc + datetime.timedelta(hours=max(1.0, dur_val))
                        else:
                            exp_dt = now_utc + datetime.timedelta(days=max(1.0, dur_val))

                        exp_str = exp_dt.strftime('%Y-%m-%d %H:%M UTC')

                        for u_row in users_rows:
                            snap = _extract_user_snapshot(u_row)
                            snapshots.append(snap)
                            uid = snap['tg_id']

                            if action == 'activate':
                                vip_json = {
                                    "active": True,
                                    "package": pkg_name,
                                    "activated_at": now_utc.isoformat(),
                                    "expires_at": exp_str
                                }
                                cur.execute("""
                                    UPDATE users
                                    SET is_vip = TRUE,
                                        vip_active = TRUE,
                                        vip_package = %s,
                                        plan = %s,
                                        vip_level = %s,
                                        vip_expires_at = %s,
                                        vip_expiry = %s,
                                        vip_expiry_date = %s,
                                        vip_status = %s,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (pkg_name, pkg_name, pkg_name, exp_str, exp_str, exp_str, Json(vip_json), uid, uid, uid))
                            else:
                                vip_json = {"active": False, "package": None, "expires_at": None}
                                cur.execute("""
                                    UPDATE users
                                    SET is_vip = FALSE,
                                        vip_active = FALSE,
                                        vip_package = NULL,
                                        plan = NULL,
                                        vip_level = NULL,
                                        vip_expires_at = NULL,
                                        vip_expiry = NULL,
                                        vip_expiry_date = NULL,
                                        vip_status = %s,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (Json(vip_json), uid, uid, uid))

                            updated_count += 1

                        if action == 'activate':
                            action_title = f"شحن باقة {pkg_name}"
                            description = f"تفعيل {pkg_name} حتى {exp_str}"
                        else:
                            action_title = "إلغاء باقة VIP"
                            description = "إيقاف وإلغاء اشتراك VIP"

                    if updated_count == 0 or not snapshots:
                        conn.rollback()
                        return {"success": False, "message": "⚠️ لم يتم تعديل أي حساب (قد تكون الحسابات في الحد الأقصى/الأدنى بالفعل)."}

                    # 2. حفظ العملية والـ Snapshot في جدول السجلات لإمكانية الإرجاع (Undo)
                    cur.execute("""
                        INSERT INTO admin_action_logs (
                            admin_id, target_type, target_id, category, action,
                            action_title, description, affected_count, snapshot_data,
                            is_undone, is_cleared, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, FALSE, CURRENT_TIMESTAMP)
                        RETURNING id
                    """, (
                        str(admin_id), target_type, target_id, category, action,
                        action_title, description, updated_count, Json(snapshots)
                    ))
                    log_row = cur.fetchone()
                    log_id = log_row['id'] if log_row else 0

                    conn.commit()
                    target_msg = f"للمستخدم ({target_id})" if target_type == 'single' else f"لجميع المستخدمين ({updated_count} حساب)"
                    return {
                        "success": True,
                        "message": f"✅ تمت العملية بنجاح (#{log_id}): {description} {target_msg}."
                    }

            except Exception as tx_err:
                conn.rollback()
                logger.error(f"Transaction error in execute_admin_data_action: {tx_err}")
                return {"success": False, "message": "❌ حدث خطأ أثناء تنفيذ العملية في قاعدة البيانات."}
            finally:
                conn.autocommit = prev_autocommit

    except Exception as e:
        logger.error(f"DB connection error in execute_admin_data_action: {e}")
        return {"success": False, "message": "❌ تعذر الاتصال بقاعدة البيانات."}


# ==================== Undo & Logs Management Operations ====================

def undo_last_admin_actions(admin_id: str, count: int = 1, specific_log_id=None) -> dict:
    """
    إرجاع آخر N عمليات (أو عملية محددة بالـ ID) بترتيب عكسي آمن
    وإعادة أرصدة ومستويات وباقات المستخدمين إلى حالتها السابقة بالضبط.
    """
    ensure_promo_table()
    try:
        safe_count = max(1, min(int(count or 1), 50))
    except (ValueError, TypeError):
        safe_count = 1

    try:
        with _get_db_connection() as conn:
            prev_autocommit = conn.autocommit
            conn.autocommit = False
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if specific_log_id is not None:
                        cur.execute("""
                            SELECT * FROM admin_action_logs
                            WHERE id = %s AND COALESCE(is_undone, FALSE) = FALSE
                            FOR UPDATE
                        """, (int(specific_log_id),))
                    else:
                        cur.execute("""
                            SELECT * FROM admin_action_logs
                            WHERE COALESCE(is_undone, FALSE) = FALSE
                            ORDER BY id DESC
                            LIMIT %s
                            FOR UPDATE
                        """, (safe_count,))

                    logs_to_undo = cur.fetchall()
                    if not logs_to_undo:
                        conn.rollback()
                        return {"success": False, "message": "⚠️ لا توجد عمليات قابلة للإرجاع حالياً!"}

                    undone_ops_count = 0
                    restored_users_total = 0

                    # التراجع بالترتيب العكسي من الأحدث إلى الأقدم لضمان دقة الأرصدة
                    for log_entry in logs_to_undo:
                        snapshots = log_entry.get('snapshot_data') or []
                        if isinstance(snapshots, str):
                            try:
                                snapshots = json.loads(snapshots)
                            except Exception:
                                snapshots = []

                        for snap in snapshots:
                            uid = str(snap.get('tg_id') or '').strip()
                            if not uid:
                                continue

                            cur.execute("""
                                UPDATE users
                                SET balance = %s,
                                    usd_balance = %s,
                                    znx_balance = %s,
                                    total_earned = %s,
                                    referrals_count = %s,
                                    mined_points = %s,
                                    total_mined = %s,
                                    mining_points = %s,
                                    mined_total = %s,
                                    farm_mined = %s,
                                    mining_rate = %s,
                                    farm_level = %s,
                                    storage_level = %s,
                                    extra_storage = %s,
                                    max_cap = %s,
                                    upgrades = %s,
                                    upgrades_count = %s,
                                    is_vip = %s,
                                    vip_active = %s,
                                    vip_package = %s,
                                    plan = %s,
                                    vip_level = %s,
                                    vip_expires_at = %s,
                                    vip_expiry = %s,
                                    vip_expiry_date = %s,
                                    vip_status = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                            """, (
                                float(snap.get('balance', 0.0)),
                                float(snap.get('usd_balance', 0.0)),
                                float(snap.get('znx_balance', 0.0)),
                                float(snap.get('total_earned', 0.0)),
                                int(snap.get('referrals_count', 0)),
                                float(snap.get('mined_points', 0.0)),
                                float(snap.get('total_mined', 0.0)),
                                float(snap.get('mining_points', 0.0)),
                                float(snap.get('mined_total', 0.0)),
                                float(snap.get('farm_mined', 0.0)),
                                float(snap.get('mining_rate', BASE_MINING_RATE)),
                                int(snap.get('farm_level', 1)),
                                int(snap.get('storage_level', 1)),
                                float(snap.get('extra_storage', 0.0)),
                                float(snap.get('max_cap', BASE_STORAGE_CAP)),
                                Json(_parse_json_dict(snap.get('upgrades'))),
                                int(snap.get('upgrades_count', 0)),
                                bool(snap.get('is_vip', False)),
                                bool(snap.get('vip_active', False)),
                                snap.get('vip_package'),
                                snap.get('plan'),
                                snap.get('vip_level'),
                                snap.get('vip_expires_at'),
                                snap.get('vip_expiry'),
                                snap.get('vip_expiry_date'),
                                Json(_parse_json_dict(snap.get('vip_status'))),
                                uid, uid, uid
                            ))
                            restored_users_total += 1

                        cur.execute("""
                            UPDATE admin_action_logs
                            SET is_undone = TRUE, undone_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (log_entry['id'],))
                        undone_ops_count += 1

                    conn.commit()
                    return {
                        "success": True,
                        "message": f"⏪ تم إرجاع ({undone_ops_count}) عملية بنجاح، واستعادة البيانات الأصلية لـ ({restored_users_total}) حساب كأن شيئاً لم يكن!"
                    }
            except Exception as tx_e:
                conn.rollback()
                logger.error(f"Transaction error in undo_last_admin_actions: {tx_e}")
                return {"success": False, "message": "❌ حدث خطأ أثناء استرجاع البيانات."}
            finally:
                conn.autocommit = prev_autocommit
    except Exception as e:
        logger.error(f"DB error in undo_last_admin_actions: {e}")
        return {"success": False, "message": "❌ خطأ في الاتصال بقاعدة البيانات."}


def get_admin_action_logs(limit: int = 50) -> list:
    """جلب سجل العمليات الإدارية غير الممسوحة لعرضها في الجدول"""
    ensure_promo_table()
    try:
        safe_limit = max(1, min(int(limit or 50), 100))
        with _get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        id,
                        admin_id,
                        target_type,
                        target_id,
                        category,
                        action,
                        action_title,
                        description,
                        affected_count,
                        COALESCE(is_undone, FALSE) AS is_undone,
                        created_at
                    FROM admin_action_logs
                    WHERE COALESCE(is_cleared, FALSE) = FALSE
                    ORDER BY id DESC
                    LIMIT %s
                """, (safe_limit,))
                rows = cur.fetchall()
                result = []
                for r in rows:
                    item = dict(r)
                    if item.get('created_at'):
                        item['created_at'] = item['created_at'].strftime('%Y-%m-%d %H:%M UTC')
                    else:
                        item['created_at'] = ''
                    result.append(item)
                return result
    except Exception as e:
        logger.error(f"Error fetching admin action logs: {e}")
        return []


def clear_admin_action_logs():
    """مسح سجل العرض فقط دون تغيير أي رصيد أو بيانات في حسابات المستخدمين"""
    ensure_promo_table()
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE admin_action_logs
                    SET is_cleared = TRUE
                    WHERE COALESCE(is_cleared, FALSE) = FALSE
                """)
            conn.commit()
        return True, "🗑️ تم مسح سجل العمليات المعروض بنجاح (دون المساس بأرصدة اللاعبين)!"
    except Exception as e:
        logger.error(f"Error clearing admin action logs: {e}")
        return False, "❌ حدث خطأ أثناء مسح السجل."

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

_tables_ready = False

# الحدود القصوى ومعدلات المستويات والمخازن
MAX_UPGRADE_PER_LVL = 50
MAX_STORAGE_LEVEL = 20

# مقدار الزيادة في سرعة التعدين (hourly_rate) لكل مستوى (lvl1 -> lvl9)
UPGRADE_RATES_MAP = {
    'lvl1': 0.10,
    'lvl2': 0.25,
    'lvl3': 0.50,
    'lvl4': 0.95,
    'lvl5': 1.80,
    'lvl6': 3.50,
    'lvl7': 7.00,
    'lvl8': 14.00,
    'lvl9': 28.00
}

# أرقام مستويات باقات الـ VIP المتوافقة مع عمود vip_status (int8)
VIP_PACKAGE_LEVEL_MAP = {
    'VIP_1': 1,
    'VIP_2': 2,
    'VIP_3': 3,
    'VIP_MAX': 4
}


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
    global _tables_ready
    if _tables_ready:
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
                        action_title VARCHAR(150) NOT NULL,
                        category VARCHAR(50) NOT NULL,
                        action VARCHAR(50) NOT NULL,
                        target_type VARCHAR(20) NOT NULL,
                        target_id VARCHAR(64),
                        description TEXT,
                        affected_count INT DEFAULT 0,
                        snapshot_data JSONB DEFAULT '[]'::jsonb,
                        is_undone BOOLEAN DEFAULT FALSE,
                        undone_at TIMESTAMPTZ NULL,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                """)
            conn.commit()
        _tables_ready = True
    except Exception as e:
        logger.error(f"Error ensuring tables in addons_db: {e}")


def _sanitize_code(code_name) -> str:
    """تنظيف الكود والسماح فقط بالحروف والأرقام والشرطة لمنع أي حقن أو تلاعب"""
    if not code_name:
        return ""
    cleaned = str(code_name).strip().upper()
    if not re.match(r'^[A-Z0-9_\-]{2,32}$', cleaned):
        return ""
    return cleaned


def _clean_telegram_id(val) -> str:
    """تنظيف والتحقق من معرف تيليجرام"""
    if val is None:
        return ""
    s = str(val).strip()
    if s.startswith("ref_"):
        s = s.replace("ref_", "", 1).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if not re.match(r'^\d{3,20}$', s):
        return ""
    return s


def _parse_json_obj(val) -> dict:
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


def _calc_storage_max_cap(storage_lvl: int, current_max_cap: float = 0.3, prev_lvl: int = 1) -> float:
    """حساب سعة المخزن (max_cap) تلقائياً بناءً على مستوى المخزن"""
    lvl = max(1, int(storage_lvl or 1))
    if lvl == 1:
        return 0.3
    cap_table = {
        1: 0.3, 2: 0.5, 3: 0.8, 4: 1.1, 5: 1.4,
        6: 1.8, 7: 2.2, 8: 2.7, 9: 3.3, 10: 4.0,
        11: 4.8, 12: 5.7, 13: 6.7, 14: 7.8, 15: 9.0,
        16: 10.5, 17: 12.0, 18: 14.0, 19: 16.5, 20: 20.0
    }
    if lvl in cap_table:
        return cap_table[lvl]
    return round(0.3 + (lvl - 1) * 0.35, 4)


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
    user_id_str = _clean_telegram_id(telegram_id)
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

def get_user_full_data_for_admin(telegram_id):
    """جلب كافة بيانات اللاعب وممتلكاته ومستوياته لعرضها للأدمن قبل التعديل"""
    ensure_promo_table()
    clean_id = _clean_telegram_id(telegram_id)
    if not clean_id:
        return False, "❌ يرجى إدخال رقم ID صحيح!", None, None

    try:
        with _get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT *
                    FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))
                row = cur.fetchone()
                if not row:
                    return False, f"❌ لم يتم العثور على لاعب بالمعرف ({clean_id})!", None, None

                d = dict(row)
                raw_upg = _parse_json_obj(d.get('upgrades'))
                upgrades_clean = {}
                total_upg = 0
                for i in range(1, 10):
                    k = f"lvl{i}"
                    v = max(0, int(raw_upg.get(k, 0) or 0))
                    upgrades_clean[k] = v
                    total_upg += v

                mined_score = max(
                    float(d.get('mined_points') or 0.0),
                    float(d.get('total_mined') or 0.0),
                    float(d.get('mining_points') or 0.0),
                    float(d.get('mined_total') or 0.0),
                    float(d.get('farm_mined') or 0.0)
                )

                refs = max(
                    int(d.get('referrals_count') or 0),
                    int(d.get('total_referrals') or 0)
                )

                vip_exp = (
                    d.get('vip_expires_at')
                    or d.get('vip_expire')
                    or d.get('expires_at')
                    or ''
                )
                if vip_exp and len(str(vip_exp)) >= 16:
                    vip_exp = str(vip_exp)[:16].replace('T', ' ')

                vip_status_num = int(d.get('vip_status') or 0) if str(d.get('vip_status') or '').lstrip('-').isdigit() else 0
                vip_pkg = (
                    d.get('vip_package')
                    or d.get('plan')
                    or d.get('vip_level')
                    or (f"VIP_{vip_status_num}" if vip_status_num > 0 else '')
                )
                is_vip_bool = bool(d.get('is_vip') or d.get('vip_active') or (vip_status_num > 0))

                # قراءة السرعة من عمود hourly_rate الأساسي في Supabase
                current_rate = float(d.get('hourly_rate') or d.get('mining_rate') or 0.1)

                user_payload = {
                    "tg_id": str(d.get('tg_id') or d.get('user_id') or d.get('telegram_id') or clean_id),
                    "first_name": d.get('first_name') or d.get('name') or 'لاعب',
                    "username": d.get('username') or '',
                    "is_banned": bool(d.get('is_banned', False)),
                    "balance": round(float(d.get('balance') or 0.0), 4),
                    "znx_balance": round(float(d.get('znx_balance') or 0.0), 4),
                    "usd_balance": round(float(d.get('usd_balance') or 0.0), 4),
                    "mined_points": round(mined_score, 4),
                    "mining_rate": round(current_rate, 4),
                    "hourly_rate": round(current_rate, 4),
                    "storage_level": max(1, int(d.get('storage_level') or 1)),
                    "max_cap": round(float(d.get('max_cap') or 0.3), 4),
                    "referrals_count": refs,
                    "upgrades": upgrades_clean,
                    "upgrades_count": total_upg,
                    "is_vip": is_vip_bool,
                    "vip_active": is_vip_bool,
                    "vip_package": str(vip_pkg) if vip_pkg else '',
                    "vip_expires_at": str(vip_exp) if vip_exp else ''
                }

                limits = {
                    "max_upgrade_per_lvl": MAX_UPGRADE_PER_LVL,
                    "max_storage_level": MAX_STORAGE_LEVEL
                }

                return True, "تم جلب بيانات اللاعب بنجاح", user_payload, limits
    except Exception as e:
        logger.error(f"Error in get_user_full_data_for_admin: {e}")
        return False, "❌ حدث خطأ أثناء فحص بيانات اللاعب.", None, None


def _extract_user_snapshot(row: dict) -> dict:
    """أخذ نسخة احتياطية دقيقة من كافة أعمدة المستخدم الموجودة فعلياً قبل التعديل"""
    vip_st_raw = row.get('vip_status')
    try:
        vip_st_val = int(vip_st_raw or 0)
    except (ValueError, TypeError):
        vip_st_val = 0

    return {
        "tg_id": str(row.get('tg_id') or row.get('user_id') or row.get('telegram_id') or ''),
        "balance": float(row.get('balance') or 0.0),
        "zn_balance": float(row.get('zn_balance') or 0.0),
        "total_earned": float(row.get('total_earned') or 0.0),
        "znx_balance": float(row.get('znx_balance') or 0.0),
        "usd_balance": float(row.get('usd_balance') or 0.0),
        "mined_points": float(row.get('mined_points') or 0.0),
        "total_mined": float(row.get('total_mined') or 0.0),
        "mining_points": float(row.get('mining_points') or 0.0),
        "mined_total": float(row.get('mined_total') or 0.0),
        "farm_mined": float(row.get('farm_mined') or 0.0),
        "referrals_count": int(row.get('referrals_count') or 0),
        "total_referrals": int(row.get('total_referrals') or 0),
        "upgrades": _parse_json_obj(row.get('upgrades')),
        "upgrades_count": int(row.get('upgrades_count') or 0),
        "farm_level": int(row.get('farm_level') or 1),
        "hourly_rate": float(row.get('hourly_rate') or 0.1),
        "storage_level": int(row.get('storage_level') or 1),
        "max_cap": float(row.get('max_cap') or 0.3),
        "is_vip": bool(row.get('is_vip', False)),
        "vip_active": bool(row.get('vip_active', False)),
        "vip_package": row.get('vip_package'),
        "vip_level": row.get('vip_level'),
        "plan": row.get('plan'),
        "vip_status": vip_st_val,
        "vip_expire": row.get('vip_expire'),
        "vip_expires_at": row.get('vip_expires_at'),
        "expires_at": row.get('expires_at')
    }


def execute_admin_data_action(admin_id: str, payload: dict):
    """
    تنفيذ أوامر التحكم في بيانات المستخدمين (إضافة/خصم أرصدة، ترقيات التعدين، المخازن، VIP)
    مع الالتزام بالحدود القصوى وحفظ نسخة احتياطية كاملة في السجل لدعم الإرجاع الذكي.
    """
    ensure_promo_table()

    target_type = str(payload.get('target_type') or 'single').strip().lower()
    raw_tid = payload.get('telegram_id')
    category = str(payload.get('category') or '').strip().lower()
    action = str(payload.get('action') or '').strip().lower()

    if target_type not in ('single', 'all'):
        return False, "❌ نوع الهدف غير صالح!"

    clean_tid = ""
    if target_type == 'single':
        clean_tid = _clean_telegram_id(raw_tid)
        if not clean_tid:
            return False, "❌ يرجى إدخال ID صحيح للاعب المستهدف!"

    if category not in ('balance', 'upgrade', 'storage', 'vip'):
        return False, "❌ قسم التعديل غير معروف!"

    try:
        with _get_db_connection() as conn:
            prev_autocommit = conn.autocommit
            conn.autocommit = False
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    if target_type == 'single':
                        cur.execute("""
                            SELECT * FROM users
                            WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                            LIMIT 1
                            FOR UPDATE
                        """, (clean_tid, clean_tid, clean_tid))
                    else:
                        cur.execute("SELECT * FROM users FOR UPDATE")

                    rows = cur.fetchall()
                    if not rows:
                        conn.rollback()
                        return False, "❌ لم يتم العثور على مستخدمين لتطبيق العملية!"

                    snapshots = []
                    affected_count = 0
                    action_title = ""
                    description = ""

                    # ==================== أولاً: قسم الأرصدة والنقاط ====================
                    if category == 'balance':
                        field = str(payload.get('field') or 'balance').strip()
                        try:
                            amount = round(float(payload.get('amount') or 0), 4)
                        except (ValueError, TypeError):
                            conn.rollback()
                            return False, "❌ يرجى إدخال قيمة رقمية صحيحة!"

                        if amount <= 0 or amount > 10000000000:
                            conn.rollback()
                            return False, "❌ القيمة المدخلة غير منطقية!"

                        field_labels = {
                            'balance': 'رصيد ZN',
                            'znx_balance': 'عملات ZNX',
                            'usd_balance': 'رصيد USD',
                            'mined_points': 'نقاط التعدين',
                            'referrals_count': 'عدد الإحالات'
                        }
                        if field not in field_labels:
                            conn.rollback()
                            return False, "❌ نوع الرصيد المحدد غير صالح!"

                        is_add = (action == 'add')
                        op_label = "إضافة" if is_add else "خصم"
                        action_title = f"{op_label} {field_labels[field]}"
                        description = f"{op_label} {amount:g} في ({field_labels[field]})"

                        for r in rows:
                            uid = str(r.get('tg_id') or r.get('user_id') or r.get('telegram_id') or '')
                            if not uid:
                                continue
                            snapshots.append(_extract_user_snapshot(r))

                            if field == 'balance':
                                cur_val = float(r.get('balance') or 0.0)
                                new_val = round(cur_val + amount, 4) if is_add else round(max(0.0, cur_val - amount), 4)
                                cur_earned = float(r.get('total_earned') or 0.0)
                                new_earned = round(cur_earned + amount, 4) if is_add else cur_earned
                                cur.execute("""
                                    UPDATE users
                                    SET balance = %s,
                                        total_earned = %s,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (new_val, new_earned, uid, uid, uid))

                            elif field == 'znx_balance':
                                cur_val = float(r.get('znx_balance') or 0.0)
                                new_val = round(cur_val + amount, 4) if is_add else round(max(0.0, cur_val - amount), 4)
                                cur.execute("""
                                    UPDATE users
                                    SET znx_balance = %s,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (new_val, uid, uid, uid))

                            elif field == 'usd_balance':
                                cur_val = float(r.get('usd_balance') or 0.0)
                                new_val = round(cur_val + amount, 4) if is_add else round(max(0.0, cur_val - amount), 4)
                                cur.execute("""
                                    UPDATE users
                                    SET usd_balance = %s,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (new_val, uid, uid, uid))

                            elif field == 'mined_points':
                                cur_val = max(
                                    float(r.get('mined_points') or 0.0),
                                    float(r.get('total_mined') or 0.0),
                                    float(r.get('mining_points') or 0.0),
                                    float(r.get('mined_total') or 0.0),
                                    float(r.get('farm_mined') or 0.0)
                                )
                                new_val = round(cur_val + amount, 4) if is_add else round(max(0.0, cur_val - amount), 4)
                                cur.execute("""
                                    UPDATE users
                                    SET mined_points = %s,
                                        total_mined = %s,
                                        mining_points = %s,
                                        mined_total = %s,
                                        farm_mined = %s,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (new_val, new_val, new_val, new_val, new_val, uid, uid, uid))

                            elif field == 'referrals_count':
                                delta_int = max(1, int(amount))
                                cur_val = max(int(r.get('referrals_count') or 0), int(r.get('total_referrals') or 0))
                                new_val = (cur_val + delta_int) if is_add else max(0, cur_val - delta_int)
                                cur.execute("""
                                    UPDATE users
                                    SET referrals_count = %s,
                                        total_referrals = %s,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (new_val, new_val, uid, uid, uid))

                            affected_count += 1

                    # ==================== ثانياً: قسم ترقيات سرعة التعدين ====================
                    elif category == 'upgrade':
                        level_key = str(payload.get('level_key') or 'lvl1').strip().lower()
                        if level_key not in UPGRADE_RATES_MAP:
                            conn.rollback()
                            return False, "❌ مستوى التعدين المختار غير صالح!"

                        try:
                            count_delta = int(payload.get('amount') or 1)
                        except (ValueError, TypeError):
                            count_delta = 1
                        if count_delta <= 0 or count_delta > MAX_UPGRADE_PER_LVL:
                            conn.rollback()
                            return False, f"❌ عدد الترقيات يجب أن يكون بين 1 و {MAX_UPGRADE_PER_LVL}!"

                        is_add = (action == 'add')
                        lvl_num = level_key.replace('lvl', '')
                        action_title = f"{'ترقية' if is_add else 'سحب'} مستوى التعدين ({lvl_num})"
                        description = f"{'إضافة' if is_add else 'إنقاص'} {count_delta} في المستوى {lvl_num}"

                        for r in rows:
                            uid = str(r.get('tg_id') or r.get('user_id') or r.get('telegram_id') or '')
                            if not uid:
                                continue

                            upg_dict = _parse_json_obj(r.get('upgrades'))
                            cur_lvl_val = max(0, int(upg_dict.get(level_key, 0) or 0))

                            if is_add:
                                if cur_lvl_val >= MAX_UPGRADE_PER_LVL:
                                    if target_type == 'single':
                                        conn.rollback()
                                        return False, f"⚠️ اللاعب وصل بالفعل للحد الأقصى ({MAX_UPGRADE_PER_LVL}) في المستوى {lvl_num}!"
                                    continue
                                new_lvl_val = min(MAX_UPGRADE_PER_LVL, cur_lvl_val + count_delta)
                            else:
                                if cur_lvl_val <= 0:
                                    if target_type == 'single':
                                        conn.rollback()
                                        return False, f"⚠️ اللاعب لا يمتلك أي ترقيات (0) في المستوى {lvl_num} لسحبها!"
                                    continue
                                new_lvl_val = max(0, cur_lvl_val - count_delta)

                            actual_diff = new_lvl_val - cur_lvl_val
                            if actual_diff == 0:
                                continue

                            snapshots.append(_extract_user_snapshot(r))
                            upg_dict[level_key] = new_lvl_val

                            # حساب إجمالي الترقيات وسرعة التعدين الجديدة (hourly_rate) بدقة
                            total_upg_count = 0
                            for i in range(1, 10):
                                k = f"lvl{i}"
                                v = max(0, int(upg_dict.get(k, 0) or 0))
                                upg_dict[k] = v
                                total_upg_count += v

                            cur_rate = float(r.get('hourly_rate') or 0.1)
                            rate_delta = actual_diff * UPGRADE_RATES_MAP[level_key]
                            new_rate = round(max(0.1, cur_rate + rate_delta), 4)

                            cur.execute("""
                                UPDATE users
                                SET upgrades = %s,
                                    upgrades_count = %s,
                                    hourly_rate = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                            """, (Json(upg_dict), total_upg_count, new_rate, uid, uid, uid))
                            affected_count += 1

                    # ==================== ثالثاً: قسم المخازن (Storage) ====================
                    elif category == 'storage':
                        try:
                            count_delta = int(payload.get('amount') or 1)
                        except (ValueError, TypeError):
                            count_delta = 1
                        if count_delta <= 0 or count_delta > MAX_STORAGE_LEVEL:
                            conn.rollback()
                            return False, f"❌ عدد مستويات المخزن يجب أن يكون بين 1 و {MAX_STORAGE_LEVEL}!"

                        is_add = (action == 'add')
                        action_title = f"{'ترقية' if is_add else 'إنقاص'} مستوى المخزن"
                        description = f"{'إضافة' if is_add else 'سحب'} {count_delta} مستوى مخزن"

                        for r in rows:
                            uid = str(r.get('tg_id') or r.get('user_id') or r.get('telegram_id') or '')
                            if not uid:
                                continue

                            cur_st = max(1, int(r.get('storage_level') or 1))
                            if is_add:
                                if cur_st >= MAX_STORAGE_LEVEL:
                                    if target_type == 'single':
                                        conn.rollback()
                                        return False, f"⚠️ مخزن اللاعب وصل بالفعل للحد الأقصى ({MAX_STORAGE_LEVEL})!"
                                    continue
                                new_st = min(MAX_STORAGE_LEVEL, cur_st + count_delta)
                            else:
                                if cur_st <= 1:
                                    if target_type == 'single':
                                        conn.rollback()
                                        return False, "⚠️ مخزن اللاعب في المستوى الأساسي (1) ولا يمكن إنقاصه أكثر!"
                                    continue
                                new_st = max(1, cur_st - count_delta)

                            if new_st == cur_st:
                                continue

                            snapshots.append(_extract_user_snapshot(r))
                            new_cap = _calc_storage_max_cap(new_st, float(r.get('max_cap') or 0.3), cur_st)

                            cur.execute("""
                                UPDATE users
                                SET storage_level = %s,
                                    max_cap = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                            """, (new_st, new_cap, uid, uid, uid))
                            affected_count += 1

                    # ==================== رابعاً: قسم باقات المتجر والـ VIP ====================
                    elif category == 'vip':
                        is_activate = (action == 'activate')
                        pkg_name = str(payload.get('vip_package') or 'VIP_1').strip()
                        vip_num = VIP_PACKAGE_LEVEL_MAP.get(pkg_name, 1)

                        try:
                            dur_val = max(1.0, float(payload.get('duration_val') or 30))
                        except (ValueError, TypeError):
                            dur_val = 30.0
                        dur_type = str(payload.get('duration_type') or 'days').strip().lower()

                        now_utc = datetime.datetime.now(datetime.timezone.utc)
                        if dur_type == 'hours':
                            exp_dt = now_utc + datetime.timedelta(hours=dur_val)
                            dur_str = f"{dur_val:g} ساعة"
                        else:
                            exp_dt = now_utc + datetime.timedelta(days=dur_val)
                            dur_str = f"{dur_val:g} يوم"

                        exp_iso = exp_dt.isoformat()

                        if is_activate:
                            action_title = f"تفعيل باقة {pkg_name}"
                            description = f"شحن {pkg_name} لمدة {dur_str}"
                        else:
                            action_title = "إلغاء باقة VIP"
                            description = "إيقاف وإلغاء اشتراك VIP"

                        for r in rows:
                            uid = str(r.get('tg_id') or r.get('user_id') or r.get('telegram_id') or '')
                            if not uid:
                                continue

                            snapshots.append(_extract_user_snapshot(r))

                            if is_activate:
                                cur.execute("""
                                    UPDATE users
                                    SET is_vip = TRUE,
                                        vip_active = TRUE,
                                        vip_package = %s,
                                        vip_level = %s,
                                        plan = %s,
                                        vip_status = %s,
                                        vip_expire = %s,
                                        vip_expires_at = %s,
                                        expires_at = %s,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (
                                    pkg_name, str(vip_num), pkg_name, int(vip_num),
                                    exp_iso, exp_iso, exp_iso, uid, uid, uid
                                ))
                            else:
                                cur.execute("""
                                    UPDATE users
                                    SET is_vip = FALSE,
                                        vip_active = FALSE,
                                        vip_package = NULL,
                                        vip_level = NULL,
                                        plan = NULL,
                                        vip_status = 0,
                                        vip_expire = NULL,
                                        vip_expires_at = NULL,
                                        expires_at = NULL,
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                                """, (uid, uid, uid))
                            affected_count += 1

                    if affected_count == 0:
                        conn.rollback()
                        return False, "⚠️ لم يتم تعديل أي حساب (قد تكون جميع الحسابات وصلت للحد الأقصى بالفعل)."

                    # تسجيل العملية مع النسخة الاحتياطية (Snapshot) في جدول admin_action_logs
                    cur.execute("""
                        INSERT INTO admin_action_logs (
                            admin_id, action_title, category, action,
                            target_type, target_id, description,
                            affected_count, snapshot_data, is_undone, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, FALSE, CURRENT_TIMESTAMP)
                        RETURNING id
                    """, (
                        str(admin_id or ''),
                        action_title,
                        category,
                        action,
                        target_type,
                        clean_tid if target_type == 'single' else 'ALL',
                        description,
                        affected_count,
                        Json(snapshots)
                    ))
                    log_row = cur.fetchone()
                    log_id = log_row['id'] if log_row else 0

                    conn.commit()
                    target_msg = f"اللاعب ({clean_tid})" if target_type == 'single' else f"جميع المستخدمين ({affected_count} حساب)"
                    return True, f"✅ تمت العملية #{log_id} بنجاح على {target_msg}!\n({description})"

            except Exception as tx_e:
                conn.rollback()
                logger.error(f"Transaction error in execute_admin_data_action: {tx_e}")
                return False, f"❌ حدث خطأ أثناء تنفيذ العملية: {tx_e}"
            finally:
                conn.autocommit = prev_autocommit

    except Exception as e:
        logger.error(f"Database error in execute_admin_data_action: {e}")
        return False, "❌ خطأ في الاتصال بقاعدة البيانات."


def undo_last_admin_actions(count: int = 1, specific_log_id=None):
    """
    إرجاع آخر (count) عمليات أو عملية محددة (specific_log_id) إلى حالتها الأصلية تماماً
    باستخدام النسخة الاحتياطية المخزنة (Snapshot) بترتيب عكسي آمن.
    """
    ensure_promo_table()
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
                        safe_count = max(1, min(int(count or 1), 50))
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
                        return False, "⚠️ لا توجد عمليات نشطة قابلة للإرجاع حالياً!"

                    restored_ops_count = 0
                    restored_users_total = 0

                    for log_item in logs_to_undo:
                        log_id = log_item['id']
                        snap_list = log_item.get('snapshot_data') or []
                        if isinstance(snap_list, str):
                            try:
                                snap_list = json.loads(snap_list)
                            except Exception:
                                snap_list = []

                        for snap in snap_list:
                            if not isinstance(snap, dict):
                                continue
                            uid = str(snap.get('tg_id') or '').strip()
                            if not uid:
                                continue

                            vip_st_raw = snap.get('vip_status')
                            try:
                                vip_st_int = int(vip_st_raw or 0)
                            except (ValueError, TypeError):
                                vip_st_int = 0

                            cur.execute("""
                                UPDATE users
                                SET balance = %s,
                                    zn_balance = %s,
                                    total_earned = %s,
                                    znx_balance = %s,
                                    usd_balance = %s,
                                    mined_points = %s,
                                    total_mined = %s,
                                    mining_points = %s,
                                    mined_total = %s,
                                    farm_mined = %s,
                                    referrals_count = %s,
                                    total_referrals = %s,
                                    upgrades = %s,
                                    upgrades_count = %s,
                                    farm_level = %s,
                                    hourly_rate = %s,
                                    storage_level = %s,
                                    max_cap = %s,
                                    is_vip = %s,
                                    vip_active = %s,
                                    vip_package = %s,
                                    vip_level = %s,
                                    plan = %s,
                                    vip_status = %s,
                                    vip_expire = %s,
                                    vip_expires_at = %s,
                                    expires_at = %s,
                                    updated_at = CURRENT_TIMESTAMP
                                WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                            """, (
                                float(snap.get('balance') or 0.0),
                                float(snap.get('zn_balance') or 0.0),
                                float(snap.get('total_earned') or 0.0),
                                float(snap.get('znx_balance') or 0.0),
                                float(snap.get('usd_balance') or 0.0),
                                float(snap.get('mined_points') or 0.0),
                                float(snap.get('total_mined') or 0.0),
                                float(snap.get('mining_points') or 0.0),
                                float(snap.get('mined_total') or 0.0),
                                float(snap.get('farm_mined') or 0.0),
                                int(snap.get('referrals_count') or 0),
                                int(snap.get('total_referrals') or 0),
                                Json(_parse_json_obj(snap.get('upgrades'))),
                                int(snap.get('upgrades_count') or 0),
                                int(snap.get('farm_level') or 1),
                                float(snap.get('hourly_rate') or snap.get('mining_rate') or 0.1),
                                int(snap.get('storage_level') or 1),
                                float(snap.get('max_cap') or 0.3),
                                bool(snap.get('is_vip', False)),
                                bool(snap.get('vip_active', False)),
                                snap.get('vip_package'),
                                snap.get('vip_level'),
                                snap.get('plan'),
                                vip_st_int,
                                snap.get('vip_expire') or snap.get('vip_expiry'),
                                snap.get('vip_expires_at'),
                                snap.get('expires_at'),
                                uid, uid, uid
                            ))
                            restored_users_total += 1

                        cur.execute("""
                            UPDATE admin_action_logs
                            SET is_undone = TRUE,
                                undone_at = CURRENT_TIMESTAMP
                            WHERE id = %s
                        """, (log_id,))
                        restored_ops_count += 1

                    conn.commit()
                    return True, f"⏪ تم بنجاح إرجاع ({restored_ops_count}) عملية وإعادة بيانات ({restored_users_total}) حساب كما كانت تماماً!"

            except Exception as tx_e:
                conn.rollback()
                logger.error(f"Transaction error in undo_last_admin_actions: {tx_e}")
                return False, f"❌ حدث خطأ أثناء استرجاع البيانات: {tx_e}"
            finally:
                conn.autocommit = prev_autocommit

    except Exception as e:
        logger.error(f"Database error in undo_last_admin_actions: {e}")
        return False, "❌ خطأ في الاتصال بقاعدة البيانات."


def get_admin_action_logs(limit: int = 40):
    """جلب سجل العمليات الإدارية لعرضه في الجدول السفلي"""
    ensure_promo_table()
    try:
        safe_limit = max(1, min(int(limit or 40), 100))
        with _get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        id,
                        action_title,
                        category,
                        action,
                        target_type,
                        target_id,
                        description,
                        affected_count,
                        COALESCE(is_undone, FALSE) AS is_undone,
                        created_at
                    FROM admin_action_logs
                    ORDER BY id DESC
                    LIMIT %s
                """, (safe_limit,))
                rows = cur.fetchall()
                logs = []
                for r in rows:
                    item = dict(r)
                    if item.get('created_at'):
                        item['created_at'] = item['created_at'].strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        item['created_at'] = ''
                    logs.append(item)
                return logs
    except Exception as e:
        logger.error(f"Error fetching admin action logs: {e}")
        return []


def clear_admin_action_logs():
    """مسح سجل العمليات المعروض فقط دون المساس بأرصدة أو بيانات المستخدمين"""
    ensure_promo_table()
    try:
        with _get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM admin_action_logs")
            conn.commit()
        return True, "🗑️ تم مسح سجل العمليات بالكامل بنجاح (دون تغيير أرصدة اللاعبين)!"
    except Exception as e:
        logger.error(f"Error clearing admin action logs: {e}")
        return False, "❌ حدث خطأ أثناء مسح السجل."

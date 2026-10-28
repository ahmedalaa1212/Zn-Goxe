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

_promo_table_ready = False

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
    """التأكد من وجود جدول promo_codes بكامل أعمدته في Supabase"""
    global _promo_table_ready
    if _promo_table_ready:
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
                """)
            conn.commit()
        _promo_table_ready = True
    except Exception as e:
        logger.error(f"Error ensuring promo_codes table: {e}")


def _sanitize_code(code_name) -> str:
    """تنظيف الكود والسماح فقط بالحروف والأرقام والشرطة لمنع أي حقن أو تلاعب"""
    if not code_name:
        return ""
    cleaned = str(code_name).strip().upper()
    if not re.match(r'^[A-Z0-9_\-]{2,32}$', cleaned):
        return ""
    return cleaned


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
    user_id_str = str(telegram_id or '').strip()
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

                    # التحقق من المستخدم وقفل صفه لمنع الغش
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

# -*- coding: utf-8 -*-
# settings/settings_db.py
import json
import logging
from psycopg2.extras import RealDictCursor, Json
import database

logger = logging.getLogger(__name__)

_settings_tables_initialized = False


def ensure_settings_tables():
    """
    التأكد من وجود جدول أكواد الهدايا (promo_codes) وجميع أعمدة التعدين والإحصائيات
    في قاعدة بيانات Supabase تلقائياً لمنع أي خطأ.
    """
    global _settings_tables_initialized
    if _settings_tables_initialized:
        return

    try:
        with database.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS promo_codes (
                        code VARCHAR(64) PRIMARY KEY,
                        coins DOUBLE PRECISION DEFAULT 0.0,
                        reward_coins DOUBLE PRECISION DEFAULT 0.0,
                        amount DOUBLE PRECISION DEFAULT 0.0,
                        points DOUBLE PRECISION DEFAULT 0.0,
                        max_uses INT DEFAULT 1,
                        used_count INT DEFAULT 0,
                        used_by JSONB DEFAULT '[]'::jsonb,
                        is_active BOOLEAN DEFAULT TRUE,
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );

                    ALTER TABLE users ADD COLUMN IF NOT EXISTS username VARCHAR(100);
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name VARCHAR(100);
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS total_earned DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS mining_points DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS mined_total DOUBLE PRECISION DEFAULT 0.0;
                    ALTER TABLE users ADD COLUMN IF NOT EXISTS farm_mined DOUBLE PRECISION DEFAULT 0.0;

                    CREATE INDEX IF NOT EXISTS idx_users_mined_points ON users(mined_points DESC);
                    CREATE INDEX IF NOT EXISTS idx_users_total_mined ON users(total_mined DESC);
                """)
        _settings_tables_initialized = True
    except Exception as e:
        logger.error(f"Error ensuring settings tables in Supabase: {e}")


def _clean_uid(uid) -> str:
    """تنظيف معرف المستخدم"""
    if uid is None:
        return ""
    s = str(uid).strip()
    if s.startswith("ref_"):
        s = s.replace("ref_", "", 1).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def mask_telegram_id(uid_str: str) -> str:
    """إخفاء أرقام الـ ID للحفاظ على الخصوصية (أول 3 أرقام + ***** + آخر 3 أرقام)"""
    s = str(uid_str).strip()
    if len(s) > 6:
        return f"{s[:3]}*****{s[-3:]}"
    elif len(s) > 3:
        return f"{s[:2]}*****{s[-1:]}"
    return "*****"


def get_user_settings_stats(uid: str) -> dict:
    """
    جلب إحصائيات مستويات المزرعة والمخازن والرصيد للمستخدم لحظياً من Supabase.
    """
    default_stats = {
        "farm_levels_count": 0,
        "storage_levels_count": 0,
        "balance": 0,
        "usd_balance": 0,
        "znx_balance": 0,
        "mined_points": 0
    }
    clean_id = _clean_uid(uid)
    if not clean_id:
        return default_stats

    ensure_settings_tables()

    try:
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        upgrades,
                        COALESCE(upgrades_count, 0) AS upgrades_count,
                        COALESCE(farm_level, 0) AS farm_level,
                        COALESCE(storage_level, 0) AS storage_level,
                        COALESCE(balance, 0.0) AS balance,
                        COALESCE(usd_balance, 0.0) AS usd_balance,
                        COALESCE(znx_balance, 0.0) AS znx_balance,
                        GREATEST(
                            COALESCE(mined_points, 0.0),
                            COALESCE(total_mined, 0.0),
                            COALESCE(mining_points, 0.0),
                            COALESCE(mined_total, 0.0),
                            COALESCE(farm_mined, 0.0)
                        ) AS mined_points
                    FROM users
                    WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                    LIMIT 1
                """, (clean_id, clean_id, clean_id))

                row = cur.fetchone()
                if not row:
                    return default_stats

                data = dict(row)

                # حساب إجمالي مستويات التعدين عبر الـ 9 مستويات من JSONB
                farm_levels_count = 0
                upgrades = data.get('upgrades')
                if isinstance(upgrades, str):
                    try:
                        upgrades = json.loads(upgrades)
                    except Exception:
                        upgrades = {}

                if isinstance(upgrades, dict) and upgrades:
                    for i in range(1, 10):
                        lvl_val = upgrades.get(f'lvl{i}', 0)
                        try:
                            farm_levels_count += max(0, int(lvl_val))
                        except (ValueError, TypeError):
                            pass

                # إذا لم تكن مفصلة داخل upgrades نعتمد على upgrades_count المخزن
                if farm_levels_count == 0:
                    try:
                        farm_levels_count = max(0, int(data.get('upgrades_count') or 0))
                    except (ValueError, TypeError):
                        farm_levels_count = 0

                # حساب مستويات المخزن
                storage_levels_count = 0
                try:
                    storage_levels_count = max(0, int(data.get('storage_level') or 0))
                except (ValueError, TypeError):
                    storage_levels_count = 0

                # تنسيق الرصيد الأساسي والأرصدة الإضافية
                def _format_num(val):
                    try:
                        num = float(val or 0.0)
                        return int(num) if num.is_integer() else round(num, 4)
                    except (ValueError, TypeError):
                        return 0

                return {
                    "farm_levels_count": farm_levels_count,
                    "storage_levels_count": storage_levels_count,
                    "balance": _format_num(data.get('balance')),
                    "usd_balance": _format_num(data.get('usd_balance')),
                    "znx_balance": _format_num(data.get('znx_balance')),
                    "mined_points": _format_num(data.get('mined_points')),
                    "upgrades": upgrades if isinstance(upgrades, dict) else {}
                }

    except Exception as e:
        logger.error(f"Error fetching settings stats from Supabase for user {clean_id}: {e}")
        return default_stats


def get_top_mining_leaderboard(limit: int = 10) -> list:
    """
    جلب أفضل 10 مستخدمين حصدوا أكبر قدر من نقاط التعدين من Supabase مع إخفاء الـ ID لحماية الخصوصية.
    """
    default_leaderboard = []
    ensure_settings_tables()

    try:
        safe_limit = max(1, min(int(limit or 10), 50))
        with database.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT 
                        COALESCE(tg_id, user_id, telegram_id) AS uid,
                        first_name,
                        last_name,
                        name,
                        username,
                        GREATEST(
                            COALESCE(mined_points, 0.0),
                            COALESCE(total_mined, 0.0),
                            COALESCE(mining_points, 0.0),
                            COALESCE(mined_total, 0.0),
                            COALESCE(farm_mined, 0.0)
                        ) AS mined_score
                    FROM users
                    WHERE COALESCE(is_banned, FALSE) = FALSE
                    ORDER BY mined_score DESC, COALESCE(balance, 0.0) DESC
                    LIMIT %s
                """, (safe_limit,))

                rows = cur.fetchall()
                leaderboard = []

                for row in rows:
                    raw_uid = str(row.get('uid') or '').strip()
                    first_name = str(row.get('first_name') or '').strip()
                    last_name = str(row.get('last_name') or '').strip()
                    alt_name = str(row.get('name') or '').strip()
                    username = str(row.get('username') or '').strip()

                    if first_name and last_name and first_name != 'لاعب':
                        full_name = f"{first_name} {last_name}"
                    elif first_name and first_name != 'لاعب':
                        full_name = first_name
                    elif alt_name and alt_name != 'لاعب':
                        full_name = alt_name
                    elif username:
                        full_name = username
                    elif first_name:
                        full_name = first_name
                    else:
                        full_name = f"لاعب #{raw_uid[-4:]}" if len(raw_uid) >= 4 else "لاعب"

                    try:
                        mined_pts = round(float(row.get('mined_score') or 0.0), 4)
                    except (ValueError, TypeError):
                        mined_pts = 0.0

                    leaderboard.append({
                        "uid": raw_uid,
                        "masked_id": mask_telegram_id(raw_uid),
                        "first_name": full_name,
                        "username": username,
                        "mining_points": mined_pts,
                        "mined_points": mined_pts
                    })

                return leaderboard

    except Exception as e:
        logger.error(f"Error fetching mining leaderboard from Supabase: {e}")
        return default_leaderboard


def redeem_promo_code(uid: str, code_input: str) -> dict:
    """
    تفعيل كود الهدايا والمكافآت في Supabase باستخدام Transaction ذري (FOR UPDATE)
    لمنع التكرار أو التلاعب وتحديث رصيد المستخدم لحظياً.
    """
    clean_id = _clean_uid(uid)
    if not clean_id or not code_input:
        return {"success": False, "message": "⚠️ البيانات المدخلة غير مكتملة."}

    raw_code = str(code_input).strip()
    if not raw_code or len(raw_code) > 30:
        return {"success": False, "message": "⚠️ صيغة الكود غير صالحة."}

    ensure_settings_tables()

    try:
        with database.get_db_connection() as conn:
            # تعطيل الـ autocommit مؤقتاً لتنفيذ Transaction مغلق وآمن (Row-Level Lock)
            prev_autocommit = conn.autocommit
            conn.autocommit = False
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. البحث عن الكود مع قفل الصف لحين انتهاء العملية (FOR UPDATE)
                    cur.execute("""
                        SELECT * FROM promo_codes
                        WHERE UPPER(TRIM(code)) = UPPER(%s)
                        FOR UPDATE
                    """, (raw_code,))
                    code_row = cur.fetchone()

                    if not code_row:
                        conn.rollback()
                        return {"success": False, "message": "❌ هذا الكود غير صحيح أو غير موجود!"}

                    if code_row.get('is_active') is False:
                        conn.rollback()
                        return {"success": False, "message": "⚠️ هذا الكود غير مفعل حالياً."}

                    # استخراج قيمة المكافأة من أي حقل متاح
                    raw_coins = (
                        code_row.get('coins')
                        or code_row.get('reward_coins')
                        or code_row.get('amount')
                        or code_row.get('points')
                        or 0
                    )
                    try:
                        coins = float(raw_coins)
                    except (ValueError, TypeError):
                        coins = 0.0

                    if coins <= 0:
                        conn.rollback()
                        return {"success": False, "message": "⚠️ هذا الكود لا يحتوي على مكافأة صالحة."}

                    max_uses = int(code_row.get('max_uses') or 1)
                    used_count = int(code_row.get('used_count') or 0)

                    used_by = code_row.get('used_by')
                    if isinstance(used_by, str):
                        try:
                            used_by = json.loads(used_by)
                        except Exception:
                            used_by = []
                    if not isinstance(used_by, list):
                        used_by = []

                    # فحص هل استخدم اللاعب الكود مسبقاً
                    used_by_strs = [str(u).strip() for u in used_by]
                    if clean_id in used_by_strs:
                        conn.rollback()
                        return {"success": False, "message": "⚠️ لقد قمت باستخدام هذا الكود من قبل!"}

                    if used_count >= max_uses:
                        conn.rollback()
                        return {"success": False, "message": "⚠️ للأسف، اكتمل الحد الأقصى لاستخدام هذا الكود!"}

                    # 2. تحديث بيانات الكود
                    used_by.append(clean_id)
                    cur.execute("""
                        UPDATE promo_codes
                        SET used_count = COALESCE(used_count, 0) + 1,
                            used_by = %s,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE code = %s
                    """, (Json(used_by), code_row['code']))

                    # 3. التأكد من وجود المستخدم وتحديث رصيده لحظياً
                    cur.execute("""
                        INSERT INTO users (tg_id, user_id, telegram_id, first_name, name, balance, total_earned)
                        VALUES (%s, %s, %s, 'لاعب', 'لاعب', %s, %s)
                        ON CONFLICT (tg_id) DO UPDATE
                        SET balance = COALESCE(users.balance, 0.0) + EXCLUDED.balance,
                            total_earned = COALESCE(users.total_earned, 0.0) + EXCLUDED.total_earned,
                            last_active_at = CURRENT_TIMESTAMP
                        RETURNING balance
                    """, (clean_id, clean_id, clean_id, coins, coins))

                    updated_user = cur.fetchone()
                    new_balance = float(updated_user['balance']) if updated_user else coins

                    # اعتماد العملية بالكامل
                    conn.commit()

                    return {
                        "success": True,
                        "message": f"🎉 مبروك! تم إضافة {coins:,.0f} ZN إلى رصيدك بنجاح.",
                        "coins": coins,
                        "new_balance": new_balance
                    }

            except Exception as tx_err:
                conn.rollback()
                logger.error(f"Transaction error in redeem_promo_code for user {clean_id}, code {raw_code}: {tx_err}")
                return {"success": False, "message": "❌ حدث خطأ أثناء معالجة الكود، يرجى المحاولة لاحقاً."}
            finally:
                conn.autocommit = prev_autocommit

    except Exception as e:
        logger.error(f"Database connection error in redeem_promo_code: {e}")
        return {"success": False, "message": "❌ خطأ في الاتصال بقاعدة البيانات."}

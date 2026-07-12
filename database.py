import os
import psycopg2
from psycopg2.extras import DictCursor

# جلب رابط الاتصال من متغيرات بيئة سيرفر Railway
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_connection():
    """إنشاء اتصال آمن بقاعدة البيانات"""
    return psycopg2.connect(DATABASE_URL)

def init_user(telegram_id):
    """تجهيز لاعب جديد وجدول ترقياته لو مش موجودين في اللعبة"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # إضافة المستخدم في جدول users لو مش موجود
                cur.execute("""
                    INSERT INTO users (telegram_id)
                    VALUES (%s)
                    ON CONFLICT (telegram_id) DO NOTHING;
                """, (telegram_id,))
                
                # إضافة مستويات الترقيات له في جدول upgrades لو مش موجود
                cur.execute("""
                    INSERT INTO upgrades (telegram_id)
                    VALUES (%s)
                    ON CONFLICT (telegram_id) DO NOTHING;
                """, (telegram_id,))
                conn.commit()
    except Exception as e:
        print(f"Error in init_user: {e}")

def get_user_data(telegram_id):
    """جلب بيانات اللاعب بالكامل (الرصيد والترقيات) في خطوة واحدة"""
    init_user(telegram_id)  # نتأكد الأول إنه متسجل
    try:
        with get_connection() as conn:
            with conn.cursor(cursor_factory=DictCursor) as cur:
                cur.execute("""
                    SELECT u.telegram_id, u.balance, u.last_claim_time, u.is_banned,
                           up.lvl1_count, up.lvl2_count, up.lvl3_count, up.lvl4_count, up.lvl5_count,
                           up.lvl6_count, up.lvl7_count, up.lvl8_count, up.lvl9_count, up.lvl10_count
                    FROM users u
                    JOIN upgrades up ON u.telegram_id = up.telegram_id
                    WHERE u.telegram_id = %s;
                """, (telegram_id,))
                return cur.fetchone()
    except Exception as e:
        print(f"Error in get_user_data: {e}")
        return None

def update_balance(telegram_id, new_balance):
    """تحديث رصيد اللاعب (زيادة أو نقصان بعد الضغط أو الشراء)"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users SET balance = %s WHERE telegram_id = %s;
                """, (new_balance, telegram_id))
                conn.commit()
    except Exception as e:
        print(f"Error in update_balance: {e}")

def update_upgrade_level(telegram_id, lvl_column, new_level):
    """تحديث مستوى ترقية معينة للاعب بشكل ديناميكي"""
    allowed_columns = [f"lvl{i}_count" for i in range(1, 11)]
    if lvl_column not in allowed_columns:
        return
        
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                query = f"UPDATE upgrades SET {lvl_column} = %s WHERE telegram_id = %s;"
                cur.execute(query, (new_level, telegram_id))
                conn.commit()
    except Exception as e:
        print(f"Error in update_upgrade_level: {e}")

def update_claim_time(telegram_id):
    """تحديث وقت آخر مطالبة بالهدية اليومية للوقت الحالي"""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users SET last_claim_time = NOW() WHERE telegram_id = %s;
                """, (telegram_id,))
                conn.commit()
    except Exception as e:
        print(f"Error in update_claim_time: {e}")

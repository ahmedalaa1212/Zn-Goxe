# shop/shop_db.py
# =================================================================
# 🛒 ZN Goxe - Shop Backend Database Operations (Supabase / PostgreSQL)
# =================================================================

import json
import logging
from datetime import datetime, timezone, timedelta
from psycopg2.extras import RealDictCursor, Json
from database import get_db_connection, format_iso

logger = logging.getLogger(__name__)

# قائمة الباقات الافتراضية الشاملة تماماً مثل الفيربيس (VIP0 -> VIP5)
DEFAULT_USDT_PACKAGES = {
    "VIP0": {
        "title": "باقة VIP0 (2 يوم)",
        "usdt": 2.0,
        "duration_days": 2,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.12,
            "ref_min_upgrades": 1,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2",
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط الإحالة: ترقية واحدة فقط",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    },
    "VIP1": {
        "title": "باقة VIP1 (7 أيام)",
        "usdt": 2.5,
        "duration_days": 7,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.0,
            "ref_min_upgrades": 0,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2"
        ]
    },
    "VIP2": {
        "title": "باقة VIP2 (7 أيام)",
        "usdt": 2.0,
        "duration_days": 7,
        "features": {
            "auto_bot": False,
            "double_storage": False,
            "referral_rate": 0.12,
            "ref_min_upgrades": 1,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط الإحالة: ترقية واحدة فقط",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    },
    "VIP3": {
        "title": "باقة VIP3 (30 يوم)",
        "usdt": 5.5,
        "duration_days": 30,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.0,
            "ref_min_upgrades": 0,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2"
        ]
    },
    "VIP4": {
        "title": "باقة VIP4 (30 يوم)",
        "usdt": 6.0,
        "duration_days": 30,
        "features": {
            "auto_bot": False,
            "double_storage": False,
            "referral_rate": 0.12,
            "ref_min_upgrades": 1,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط الإحالة: ترقية واحدة فقط",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    },
    "VIP5": {
        "title": "باقة VIP5 (30 يوم)",
        "usdt": 9.99,
        "duration_days": 30,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.12,
            "ref_min_upgrades": 1,
            "ref_withdraw_fee": 0.0
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2",
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط الإحالة: ترقية واحدة فقط",
            "⚡ إعفاء كامل من رسوم السحب (0%)"
        ]
    }
}

# قيم افتراضية لترقيات التعدين لضمان عدم إرسال بيانات فارغة تكسر الواجهة
DEFAULT_UPGRADE_CONFIG = {
    "1": {"cost_zn": 100.0, "cost_usd": 0.0, "rate_bonus": 0.20},
    "2": {"cost_zn": 400.0, "cost_usd": 0.25, "rate_bonus": 0.50},
    "3": {"cost_zn": 1500.0, "cost_usd": 0.60, "rate_bonus": 1.20},
    "4": {"cost_zn": 5000.0, "cost_usd": 1.25, "rate_bonus": 2.80},
    "5": {"cost_zn": 15000.0, "cost_usd": 3.00, "rate_bonus": 6.00},
    "6": {"cost_zn": 40000.0, "cost_usd": 6.00, "rate_bonus": 14.00},
    "7": {"cost_zn": 100000.0, "cost_usd": 12.00, "rate_bonus": 30.00},
    "8": {"cost_zn": 250000.0, "cost_usd": 25.00, "rate_bonus": 70.00}
}

# قيم افتراضية لسعات المخزن لضمان عدم إرسال بيانات فارغة تكسر الواجهة
DEFAULT_STORAGE_CONFIG = {
    "0": {"capacity": 0.5, "cost_zn": 0.0, "cost_usd": 0.0},
    "1": {"capacity": 1.5, "cost_zn": 50.0, "cost_usd": 0.0},
    "2": {"capacity": 4.0, "cost_zn": 200.0, "cost_usd": 0.20},
    "3": {"capacity": 10.0, "cost_zn": 800.0, "cost_usd": 0.50},
    "4": {"capacity": 25.0, "cost_zn": 2500.0, "cost_usd": 1.00},
    "5": {"capacity": 60.0, "cost_zn": 7000.0, "cost_usd": 2.50},
    "6": {"capacity": 150.0, "cost_zn": 20000.0, "cost_usd": 5.00},
    "7": {"capacity": 400.0, "cost_zn": 50000.0, "cost_usd": 10.00},
    "8": {"capacity": 1000.0, "cost_zn": 120000.0, "cost_usd": 20.00}
}


def _parse_json_field(field_val, default=None):
    """تحليل حقول JSONB بأمان تام مع معالجة التشفير المزدوج (Double-Encoded JSON)"""
    if default is None:
        default = {}
    if field_val is None:
        return default
    
    if isinstance(field_val, str):
        try:
            parsed = json.loads(field_val)
            # معالجة حالة إذا كان النص مشفراً مرتين بسبب لوحة تحكم Supabase
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return parsed if isinstance(parsed, (dict, list)) else default
        except Exception:
            return default
            
    if isinstance(field_val, (dict, list)):
        return field_val
        
    return default


def get_shop_catalog():
    """جلب بيانات المزرعة والمتجر وتوحيدها بشكل مثالي لمنع تعليق شاشة التحميل"""
    try:
        farm_settings = {}
        shop_settings = {}

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT key, value FROM settings WHERE key IN ('farm_settings', 'shop_settings')")
                rows = cur.fetchall()
                for row in rows:
                    if row['key'] == 'farm_settings':
                        farm_settings = _parse_json_field(row['value'], {})
                    elif row['key'] == 'shop_settings':
                        shop_settings = _parse_json_field(row['value'], {})

        # 1. إعدادات التعدين العامة (فصل تام عن مستويات الترقية)
        mining_cfg = farm_settings.get("mining_config", {})
        if not isinstance(mining_cfg, dict):
            mining_cfg = {}

        # 2. مستويات التعدين (الترقيات)
        upgrade_cfg = farm_settings.get("upgrade_config")
        if not upgrade_cfg or not isinstance(upgrade_cfg, dict) or len(upgrade_cfg) == 0:
            upgrade_cfg = DEFAULT_UPGRADE_CONFIG

        # 3. سعات المخزن
        storage_caps = farm_settings.get("storage_capacities") or farm_settings.get("storage_config")
        if not storage_caps or not isinstance(storage_caps, dict) or len(storage_caps) == 0:
            storage_caps = DEFAULT_STORAGE_CONFIG

        # 4. باقات العروض المميزة
        usdt_pkgs = shop_settings.get("usdt_packages") or shop_settings.get("packages") or farm_settings.get("usdt_packages")
        if not usdt_pkgs or not isinstance(usdt_pkgs, dict) or len(usdt_pkgs) == 0:
            usdt_pkgs = DEFAULT_USDT_PACKAGES.copy()

        # 5. استخراج المحفظة وسعر الصرف بأمان
        ton_wallet = shop_settings.get("ton_wallet") or shop_settings.get("wallet_address") or ""
        try:
            ton_usdt_rate = float(shop_settings.get("ton_usdt_rate", 5.5))
        except (ValueError, TypeError):
            ton_usdt_rate = 5.5

        # تحويل المفاتيح إلى نصوص String Keys لضمان معالجتها صحيحة في الـ Frontend
        return {
            "mining_config": mining_cfg,
            "upgrade_config": {str(k): v for k, v in upgrade_cfg.items()},
            "storage_config": {str(k): v for k, v in storage_caps.items()},
            "storage_capacities": {str(k): v for k, v in storage_caps.items()},
            "usdt_packages": {str(k): v for k, v in usdt_pkgs.items()},
            "packages": {str(k): v for k, v in usdt_pkgs.items()},
            "ton_wallet": ton_wallet,
            "ton_usdt_rate": ton_usdt_rate
        }
    except Exception as e:
        logger.error(f"❌ Error in get_shop_catalog: {e}")
        return {
            "mining_config": {},
            "upgrade_config": DEFAULT_UPGRADE_CONFIG,
            "storage_config": DEFAULT_STORAGE_CONFIG,
            "storage_capacities": DEFAULT_STORAGE_CONFIG,
            "usdt_packages": DEFAULT_USDT_PACKAGES.copy(),
            "packages": DEFAULT_USDT_PACKAGES.copy(),
            "ton_wallet": "",
            "ton_usdt_rate": 5.5
        }


def get_shop_settings():
    """جلب إعدادات المتجر الكاملة لتظهر فوراً في الواجهة"""
    return get_shop_catalog()


def get_user_vip_status(user_id):
    """التحقق من حالة اشتراك VIP للمستخدم وتاريخ انتهائه ودقة الميزات المفعّلة"""
    try:
        if not user_id:
            return {"is_active": False, "package_id": None, "remaining_seconds": 0}

        str_uid = str(user_id)
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT vip_status FROM users WHERE tg_id = %s", (str_uid,))
                row = cur.fetchone()

                if not row or not row.get('vip_status'):
                    return {"is_active": False, "package_id": None, "remaining_seconds": 0}

                vip_status = _parse_json_field(row['vip_status'], {})
                if not isinstance(vip_status, dict) or not vip_status:
                    return {"is_active": False, "package_id": None, "remaining_seconds": 0}

                expires_at_str = vip_status.get("expires_at")
                if not expires_at_str:
                    return {"is_active": False, "package_id": None, "remaining_seconds": 0}

                now_dt = datetime.now(timezone.utc)
                clean_exp_str = str(expires_at_str).replace(' ', 'T').replace('Z', '+00:00')
                expires_dt = datetime.fromisoformat(clean_exp_str)
                if expires_dt.tzinfo is None:
                    expires_dt = expires_dt.replace(tzinfo=timezone.utc)

                remaining_seconds = max(0, int((expires_dt - now_dt).total_seconds()))
                is_active = remaining_seconds > 0

                return {
                    "is_active": is_active,
                    "package_id": vip_status.get("package_id"),
                    "expires_at": format_iso(expires_dt),
                    "remaining_seconds": remaining_seconds,
                    "auto_bot": bool(vip_status.get("auto_bot", False)) if is_active else False,
                    "double_storage": bool(vip_status.get("double_storage", False)) if is_active else False,
                    "referral_rate": float(vip_status.get("referral_rate", 0.0)) if is_active else 0.0,
                    "ref_min_upgrades": int(vip_status.get("ref_min_upgrades", 0)) if is_active else 0,
                    "ref_withdraw_fee": float(vip_status.get("ref_withdraw_fee", 0.0)) if is_active else 0.0
                }
    except Exception as e:
        logger.error(f"❌ Error in get_user_vip_status: {e}")
        return {"is_active": False, "package_id": None, "remaining_seconds": 0}


def log_purchase_transaction(tg_id, tx_type, item_id, cost_zn=0.0, cost_usd=0.0, tx_hash=None, details=None):
    """تسجيل المعاملة المالية في جدول purchase_history و processed_txs لمنع التكرار"""
    try:
        str_uid = str(tg_id)
        tx_h = str(tx_hash).strip() if tx_hash else None
        details_obj = details if isinstance(details, dict) else {}

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO purchase_history (tg_id, type, item_id, cost_zn, cost_usd, tx_hash, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                """, (str_uid, str(tx_type), str(item_id), float(cost_zn), float(cost_usd), tx_h, Json(details_obj)))

                if tx_h:
                    cur.execute("""
                        INSERT INTO processed_txs (tx_hash, tg_id, type, cost_zn, cost_usd, details)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tx_hash) DO NOTHING;
                    """, (tx_h, str_uid, str(tx_type), float(cost_zn), float(cost_usd), Json(details_obj)))

        return True
    except Exception as e:
        logger.error(f"⚠️ Failed to log purchase transaction: {e}")
        return False


def buy_mining_upgrade(tg_id, upgrade_level):
    """شراء ترقية كرت تعدين مع التحقق المعاملاتي الآمن (FOR UPDATE)"""
    try:
        if not tg_id or upgrade_level is None:
            return False, "بيانات الترقية غير صالحة", {}

        catalog = get_shop_catalog()
        mining_cfg = catalog.get("upgrade_config", {})
        lvl_str = str(upgrade_level)

        if lvl_str not in mining_cfg:
            return False, "مستوى الترقية غير موجود في المتجر", {}

        item_info = mining_cfg[lvl_str]
        cost_zn = float(item_info.get("cost_zn", item_info.get("price", 0.0)))
        cost_usd = float(item_info.get("cost_usd", item_info.get("usd_cost", 0.0)))
        rate_bonus = float(item_info.get("rate_bonus", item_info.get("rate", 0.0)))
        max_purchases = int(item_info.get("max", item_info.get("max_limit", 15)))

        str_uid = str(tg_id)

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    return False, "المستخدم غير موجود", {}

                user_data = dict(user_data)
                user_upgrades = _parse_json_field(user_data.get("upgrades"), {})

                current_owned = int(user_upgrades.get(f"lvl{lvl_str}", user_upgrades.get(lvl_str, 0)))

                if current_owned >= max_purchases:
                    return False, "وصلت للحد الأقصى لشراء هذه الترقية", {}

                current_balance = float(user_data.get("balance", 0.0) or 0.0)
                current_usd_balance = float(user_data.get("usd_balance", 0.0) or 0.0)

                if current_balance < cost_zn:
                    return False, f"رصيد ZN غير كافٍ! تحتاج {cost_zn:g} ZN", {}

                if current_usd_balance < cost_usd:
                    return False, f"رصيد الدولار غير كافٍ! تحتاج ${cost_usd:g}", {}

                last_claim_raw = user_data.get('last_claim_time')
                now_dt = datetime.now(timezone.utc)
                old_rate = float(user_data.get("hourly_rate", 0.0) or 0.0)
                old_cap = float(user_data.get("max_cap", 100.0) or 100.0)

                pending_mined = 0.0
                if last_claim_raw:
                    try:
                        clean_str = str(last_claim_raw).replace(' ', 'T').replace('Z', '+00:00')
                        last_claim_dt = datetime.fromisoformat(clean_str)
                        if last_claim_dt.tzinfo is None:
                            last_claim_dt = last_claim_dt.replace(tzinfo=timezone.utc)
                        time_elapsed = max(0.0, (now_dt - last_claim_dt).total_seconds())
                        pending_mined = min(time_elapsed * (old_rate / 3600.0), old_cap)
                    except Exception:
                        pending_mined = 0.0

                new_balance = round(current_balance - cost_zn, 4)
                new_usd_balance = round(current_usd_balance - cost_usd, 4)
                new_hourly_rate = round(old_rate + rate_bonus, 4)

                if new_hourly_rate > 0:
                    time_needed = pending_mined / (new_hourly_rate / 3600.0)
                    new_last_claim_dt = now_dt - timedelta(seconds=time_needed)
                else:
                    new_last_claim_dt = now_dt

                user_upgrades[f"lvl{lvl_str}"] = current_owned + 1
                total_upgrades_cnt = sum(int(v) for v in user_upgrades.values() if isinstance(v, (int, float)))

                cur.execute("""
                    UPDATE users SET
                        balance = %s,
                        usd_balance = %s,
                        hourly_rate = %s,
                        upgrades = %s,
                        upgrades_count = %s,
                        last_claim_time = %s
                    WHERE tg_id = %s
                """, (new_balance, new_usd_balance, new_hourly_rate, Json(user_upgrades), total_upgrades_cnt, new_last_claim_dt, str_uid))

                updated_fields = {
                    "balance": new_balance,
                    "usd_balance": new_usd_balance,
                    "hourly_rate": new_hourly_rate,
                    "upgrades": user_upgrades,
                    "upgrades_count": total_upgrades_cnt,
                    "last_claim_time": format_iso(new_last_claim_dt)
                }

        log_purchase_transaction(tg_id, "mining_upgrade", lvl_str, cost_zn, cost_usd)
        return True, f"تم شراء الترقية مستوى {lvl_str} بنجاح!", updated_fields

    except Exception as e:
        logger.error(f"❌ Error buying mining upgrade: {e}")
        return False, str(e), {}


def upgrade_storage_capacity(tg_id):
    """ترقية المخزن وزيادة السعة بنظام معاملات آمن"""
    try:
        if not tg_id:
            return False, "معرف غير صالح", {}

        catalog = get_shop_catalog()
        storage_cfg = catalog.get("storage_capacities", {})
        str_uid = str(tg_id)

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    return False, "المستخدم غير موجود", {}

                user_data = dict(user_data)
                current_lvl = int(user_data.get("storage_level", 0))
                next_lvl_str = str(current_lvl + 1)

                if next_lvl_str not in storage_cfg:
                    return False, "وصلت لأعلى مستوى مخزن حالياً!", {}

                next_info = storage_cfg[next_lvl_str]
                cost_zn = float(next_info.get("cost_zn", next_info.get("price", 0.0)))
                cost_usd = float(next_info.get("cost_usd", next_info.get("usd_cost", 0.0)))
                new_base_capacity = float(next_info.get("capacity", next_info.get("cap", 100.0)))
                extra_storage = float(user_data.get("extra_storage", 0.0) or 0.0)

                current_balance = float(user_data.get("balance", 0.0) or 0.0)
                current_usd_balance = float(user_data.get("usd_balance", 0.0) or 0.0)

                if current_balance < cost_zn:
                    return False, f"رصيدك من ZN غير كافٍ لترقية المخزن! تحتاج {cost_zn:g} ZN", {}

                if current_usd_balance < cost_usd:
                    return False, f"رصيدك من الدولار غير كافٍ لترقية المخزن! تحتاج ${cost_usd:g}", {}

                last_claim_raw = user_data.get('last_claim_time')
                now_dt = datetime.now(timezone.utc)
                hourly_rate = float(user_data.get("hourly_rate", 0.0) or 0.0)
                old_cap = float(user_data.get("max_cap", 100.0) or 100.0)

                pending_mined = 0.0
                if last_claim_raw:
                    try:
                        clean_str = str(last_claim_raw).replace(' ', 'T').replace('Z', '+00:00')
                        last_claim_dt = datetime.fromisoformat(clean_str)
                        if last_claim_dt.tzinfo is None:
                            last_claim_dt = last_claim_dt.replace(tzinfo=timezone.utc)
                        time_elapsed = max(0.0, (now_dt - last_claim_dt).total_seconds())
                        pending_mined = min(time_elapsed * (hourly_rate / 3600.0), old_cap)
                    except Exception:
                        pending_mined = 0.0

                new_balance = round(current_balance - cost_zn, 4)
                new_usd_balance = round(current_usd_balance - cost_usd, 4)

                vip_status = _parse_json_field(user_data.get("vip_status"), {})
                is_double_active = False
                if isinstance(vip_status, dict) and vip_status.get("double_storage"):
                    exp_str = vip_status.get("expires_at")
                    if exp_str:
                        try:
                            clean_exp = str(exp_str).replace(' ', 'T').replace('Z', '+00:00')
                            exp_dt = datetime.fromisoformat(clean_exp)
                            if exp_dt.tzinfo is None: exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                            if exp_dt > now_dt: is_double_active = True
                        except Exception: pass

                raw_cap = new_base_capacity + extra_storage
                new_max_cap = round(raw_cap * 2.0 if is_double_active else raw_cap, 4)

                if hourly_rate > 0:
                    time_needed = pending_mined / (hourly_rate / 3600.0)
                    new_last_claim_dt = now_dt - timedelta(seconds=time_needed)
                else:
                    new_last_claim_dt = now_dt

                cur.execute("""
                    UPDATE users SET
                        balance = %s,
                        usd_balance = %s,
                        storage_level = %s,
                        max_cap = %s,
                        last_claim_time = %s
                    WHERE tg_id = %s
                """, (new_balance, new_usd_balance, int(next_lvl_str), new_max_cap, new_last_claim_dt, str_uid))

                updated_fields = {
                    "balance": new_balance,
                    "usd_balance": new_usd_balance,
                    "storage_level": int(next_lvl_str),
                    "max_cap": new_max_cap,
                    "last_claim_time": format_iso(new_last_claim_dt)
                }

        log_purchase_transaction(tg_id, "storage_upgrade", next_lvl_str, cost_zn, cost_usd)
        return True, f"تم ترقية المخزن إلى المستوى {next_lvl_str} (سعة: {new_max_cap:g}) بنجاح!", updated_fields

    except Exception as e:
        logger.error(f"❌ Error upgrading storage: {e}")
        return False, str(e), {}


def process_upgrade_purchase(tg_id, upgrade_type, upgrade_id):
    """دالة عامة موحدة لمعالجة شراء الترقيات"""
    if str(upgrade_type).lower() in ["mining", "card"]:
        return buy_mining_upgrade(tg_id, upgrade_id)
    elif str(upgrade_type).lower() in ["storage", "capacity"]:
        return upgrade_storage_capacity(tg_id)
    else:
        return False, "نوع الترقية غير معروف", {}


def verify_and_apply_package(tg_id, package_id, boc=None, tx_hash=None):
    """تفعيل باقات الدفع المباشر (VIP0 -> VIP5) عبر المحفظة وتطبيقها في Supabase"""
    try:
        if not tg_id or not package_id:
            return False, "بيانات غير صالحة", {}

        catalog = get_shop_catalog()
        pkgs = catalog.get("packages", {})
        pkg_key = str(package_id)

        if pkg_key not in pkgs:
            return False, "الباقة غير موجودة في المتجر", {}

        pkg_info = pkgs[pkg_key]
        duration_days = int(pkg_info.get("duration_days", 30))
        features = pkg_info.get("features", {}) if isinstance(pkg_info.get("features"), dict) else {}

        auto_bot = bool(features.get("auto_bot", False))
        double_storage = bool(features.get("double_storage", False))
        referral_rate = float(features.get("referral_rate", 0.0))
        ref_min_upgrades = int(features.get("ref_min_upgrades", 0))
        ref_withdraw_fee = float(features.get("ref_withdraw_fee", 0.0))

        zn_add = float(pkg_info.get("zn_add", 0.0))
        rate_add = float(pkg_info.get("rate_add", 0.0))
        storage_add = float(pkg_info.get("storage_add", 0.0))
        usd_add = float(pkg_info.get("usd_add", 0.0))
        pkg_price_usd = float(pkg_info.get("usdt", 0.0))

        tx_identifier = str(boc or tx_hash or "").strip()
        str_uid = str(tg_id)

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if tx_identifier:
                    cur.execute("SELECT 1 FROM processed_txs WHERE tx_hash = %s", (tx_identifier,))
                    if cur.fetchone():
                        return False, "تمت معالجة هذه العملية سابقاً!", {}

                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    return False, "المستخدم غير موجود", {}

                user_data = dict(user_data)

                current_balance = float(user_data.get("balance", 0.0) or 0.0)
                current_usd = float(user_data.get("usd_balance", 0.0) or 0.0)
                current_rate = float(user_data.get("hourly_rate", 0.0) or 0.0)
                current_extra_storage = float(user_data.get("extra_storage", 0.0) or 0.0)
                current_max_cap = float(user_data.get("max_cap", 100.0) or 100.0)
                last_claim_raw = user_data.get('last_claim_time')

                now_dt = datetime.now(timezone.utc)

                existing_vip = _parse_json_field(user_data.get("vip_status"), {})
                existing_expires_str = existing_vip.get("expires_at")
                is_currently_active = False
                existing_expires_dt = None

                if existing_expires_str:
                    try:
                        clean_exp = str(existing_expires_str).replace(' ', 'T').replace('Z', '+00:00')
                        existing_expires_dt = datetime.fromisoformat(clean_exp)
                        if existing_expires_dt.tzinfo is None:
                            existing_expires_dt = existing_expires_dt.replace(tzinfo=timezone.utc)
                        if existing_expires_dt > now_dt:
                            is_currently_active = True
                    except Exception:
                        is_currently_active = False

                if is_currently_active and existing_expires_dt:
                    new_expires_dt = existing_expires_dt + timedelta(days=duration_days)
                else:
                    new_expires_dt = now_dt + timedelta(days=duration_days)

                pending_mined = 0.0
                if last_claim_raw:
                    try:
                        clean_str = str(last_claim_raw).replace(' ', 'T').replace('Z', '+00:00')
                        last_claim_dt = datetime.fromisoformat(clean_str)
                        if last_claim_dt.tzinfo is None:
                            last_claim_dt = last_claim_dt.replace(tzinfo=timezone.utc)
                        time_elapsed = max(0.0, (now_dt - last_claim_dt).total_seconds())
                        pending_mined = min(time_elapsed * (current_rate / 3600.0), current_max_cap)
                    except Exception:
                        pending_mined = 0.0

                was_double_active = is_currently_active and bool(existing_vip.get("double_storage", False))
                new_max_cap = current_max_cap
                if double_storage and not was_double_active:
                    new_max_cap = current_max_cap * 2.0
                elif not double_storage and was_double_active:
                    new_max_cap = max(100.0, current_max_cap / 2.0)

                new_balance = round(current_balance + zn_add, 4)
                new_usd = round(current_usd + usd_add, 4)
                new_rate = round(current_rate + rate_add, 4)
                new_extra_storage = round(current_extra_storage + storage_add, 4)
                new_max_cap = round(new_max_cap + storage_add, 4)

                if new_rate > 0:
                    time_needed = pending_mined / (new_rate / 3600.0)
                    new_last_claim_dt = now_dt - timedelta(seconds=time_needed)
                else:
                    new_last_claim_dt = now_dt

                new_vip_status = {
                    "package_id": pkg_key,
                    "expires_at": format_iso(new_expires_dt),
                    "auto_bot": auto_bot,
                    "double_storage": double_storage,
                    "referral_rate": referral_rate,
                    "ref_min_upgrades": ref_min_upgrades,
                    "ref_withdraw_fee": ref_withdraw_fee,
                    "updated_at": format_iso(now_dt)
                }

                cur.execute("""
                    UPDATE users SET
                        balance = %s,
                        usd_balance = %s,
                        hourly_rate = %s,
                        extra_storage = %s,
                        max_cap = %s,
                        last_claim_time = %s,
                        vip_status = %s,
                        bot_active = %s,
                        bot_expires_at = %s
                    WHERE tg_id = %s
                """, (new_balance, new_usd, new_rate, new_extra_storage, new_max_cap, new_last_claim_dt, Json(new_vip_status), auto_bot, new_expires_dt, str_uid))

                if tx_identifier:
                    cur.execute("""
                        INSERT INTO processed_txs (tx_hash, tg_id, package_id, type, cost_usd)
                        VALUES (%s, %s, %s, 'vip_package', %s)
                        ON CONFLICT (tx_hash) DO NOTHING;
                    """, (tx_identifier, str_uid, pkg_key, pkg_price_usd))

                updated_fields = {
                    "balance": new_balance,
                    "usd_balance": new_usd,
                    "hourly_rate": new_rate,
                    "extra_storage": new_extra_storage,
                    "max_cap": new_max_cap,
                    "last_claim_time": format_iso(new_last_claim_dt),
                    "vip_status": new_vip_status
                }

        log_purchase_transaction(tg_id, "vip_package", pkg_key, 0.0, pkg_price_usd, tx_identifier)
        return True, "تم تفعيل الباقة بنجاح!", updated_fields

    except Exception as e:
        logger.error(f"❌ Error applying package: {e}")
        return False, str(e), {}


def get_user_purchase_history(tg_id, limit=20):
    """جلب سجل المشتريات للمستخدم من Supabase"""
    try:
        if not tg_id:
            return []

        str_uid = str(tg_id)
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT id, type, item_id, cost_zn, cost_usd, tx_hash, details, created_at
                    FROM purchase_history
                    WHERE tg_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (str_uid, limit))
                rows = cur.fetchall()

                history = []
                for row in rows:
                    item = dict(row)
                    item["details"] = _parse_json_field(item.get("details"), {})
                    if item.get("created_at"):
                        item["created_at"] = format_iso(item["created_at"])
                    history.append(item)

                return history
    except Exception as e:
        logger.error(f"❌ Error fetching user purchase history: {e}")
        return []

# -*- coding: utf-8 -*-
# shop/shop_db.py
# =================================================================
# 🛒 ZN Goxe - Shop Backend Database Operations (Supabase / PostgreSQL)
# =================================================================

import copy
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from database import format_iso, get_db_connection, get_db_transaction
from psycopg2.extras import Json, RealDictCursor

logger = logging.getLogger(__name__)

# قائمة الباقات الافتراضية الاحتياطية (مطابقة لملف farm_db.py)
DEFAULT_USDT_PACKAGES = {
    "VIP0": {
        "title": "باقة VIP0 (2 يوم)",
        "usdt": 2.0,
        "duration_days": 2,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.12,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0,
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2",
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط مهام الإحالة: 3 ترقيات",
            "⚡ إعفاء كامل من رسوم السحب (0%)",
        ],
    },
    "VIP1": {
        "title": "باقة VIP1 (7 أيام)",
        "usdt": 2.5,
        "duration_days": 7,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.0,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0,
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2",
        ],
    },
    "VIP2": {
        "title": "باقة VIP2 (7 أيام)",
        "usdt": 2.0,
        "duration_days": 7,
        "features": {
            "auto_bot": False,
            "double_storage": False,
            "referral_rate": 0.12,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0,
        },
        "perks_text": [
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط مهام الإحالة: 3 ترقيات",
            "⚡ إعفاء كامل من رسوم السحب (0%)",
        ],
    },
    "VIP3": {
        "title": "باقة VIP3 (30 يوم)",
        "usdt": 5.5,
        "duration_days": 30,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.0,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0,
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2",
        ],
    },
    "VIP4": {
        "title": "باقة VIP4 (30 يوم)",
        "usdt": 6.0,
        "duration_days": 30,
        "features": {
            "auto_bot": False,
            "double_storage": False,
            "referral_rate": 0.12,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0,
        },
        "perks_text": [
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط مهام الإحالة: 3 ترقيات",
            "⚡ إعفاء كامل من رسوم السحب (0%)",
        ],
    },
    "VIP5": {
        "title": "باقة VIP5 (30 يوم)",
        "usdt": 9.99,
        "duration_days": 30,
        "features": {
            "auto_bot": True,
            "double_storage": True,
            "referral_rate": 0.12,
            "ref_min_upgrades": 3,
            "ref_withdraw_fee": 0.0,
        },
        "perks_text": [
            "🤖 بوت تجميع تلقائي",
            "📦 زيادة سعة المخزن الضعف ×2",
            "💎 رفع أرباح الإحالة إلى 12%",
            "🎯 شرط مهام الإحالة: 3 ترقيات",
            "⚡ إعفاء كامل من رسوم السحب (0%)",
        ],
    },
}

DEFAULT_UPGRADE_CONFIG = {
    "1": {"cost_zn": 100.0, "cost_usd": 0.0, "rate_bonus": 0.20},
    "2": {"cost_zn": 400.0, "cost_usd": 0.25, "rate_bonus": 0.50},
    "3": {"cost_zn": 1500.0, "cost_usd": 0.60, "rate_bonus": 1.20},
    "4": {"cost_zn": 5000.0, "cost_usd": 1.25, "rate_bonus": 2.80},
    "5": {"cost_zn": 15000.0, "cost_usd": 3.00, "rate_bonus": 6.00},
    "6": {"cost_zn": 40000.0, "cost_usd": 6.00, "rate_bonus": 14.00},
    "7": {"cost_zn": 100000.0, "cost_usd": 12.00, "rate_bonus": 30.00},
    "8": {"cost_zn": 250000.0, "cost_usd": 25.00, "rate_bonus": 70.00},
}

DEFAULT_STORAGE_CONFIG = {
    "0": {"capacity": 0.5, "cost_zn": 0.0, "cost_usd": 0.0},
    "1": {"capacity": 1.5, "cost_zn": 50.0, "cost_usd": 0.0},
    "2": {"capacity": 4.0, "cost_zn": 200.0, "cost_usd": 0.20},
    "3": {"capacity": 10.0, "cost_zn": 800.0, "cost_usd": 0.50},
    "4": {"capacity": 25.0, "cost_zn": 2500.0, "cost_usd": 1.00},
    "5": {"capacity": 60.0, "cost_zn": 7000.0, "cost_usd": 2.50},
    "6": {"capacity": 150.0, "cost_zn": 20000.0, "cost_usd": 5.00},
    "7": {"capacity": 400.0, "cost_zn": 50000.0, "cost_usd": 10.00},
    "8": {"capacity": 1000.0, "cost_zn": 120000.0, "cost_usd": 20.00},
}


def _normalize_tx_identifier(tx_hash=None, boc=None):
    if tx_hash:
        clean_tx = str(tx_hash).strip()
        if len(clean_tx) > 128:
            return hashlib.sha256(clean_tx.encode("utf-8")).hexdigest()
        return clean_tx

    if boc:
        clean_boc = str(boc).strip()
        if clean_boc:
            return hashlib.sha256(clean_boc.encode("utf-8")).hexdigest()

    return ""


def _parse_json_field(field_val, default=None):
    if default is None:
        default = {}
    if field_val is None:
        return copy.deepcopy(default)

    if isinstance(field_val, str):
        try:
            parsed = json.loads(field_val)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            return copy.deepcopy(parsed) if isinstance(parsed, (dict, list)) else copy.deepcopy(default)
        except Exception:
            return copy.deepcopy(default)

    if isinstance(field_val, (dict, list)):
        return copy.deepcopy(field_val)

    return copy.deepcopy(default)


def _is_user_row_banned(user_row: dict) -> bool:
    """فحص داخلي سريع لحالة الحظر داخل صف المستخدم"""
    if not isinstance(user_row, dict):
        return False
    return bool(
        user_row.get("is_banned")
        or user_row.get("banned")
        or str(user_row.get("status") or "").lower() == "banned"
    )


def ensure_pending_payments_table():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pending_ton_payments (
                        id SERIAL PRIMARY KEY,
                        tg_id VARCHAR(64) NOT NULL,
                        package_id VARCHAR(32) NOT NULL,
                        usdt_price NUMERIC(12, 4) DEFAULT 0,
                        expected_nano_ton BIGINT NOT NULL,
                        payload_memo VARCHAR(128) UNIQUE NOT NULL,
                        boc_hash VARCHAR(128),
                        tx_hash VARCHAR(128),
                        status VARCHAR(24) DEFAULT 'pending',
                        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
    except Exception as e:
        logger.error(f"⚠️ Error ensuring pending_ton_payments table: {e}")


def create_pending_ton_payment(tg_id, package_id, usdt_price, expected_nano_ton, payload_memo):
    try:
        ensure_pending_payments_table()
        str_uid = str(tg_id).strip()
        str_pkg = str(package_id).strip()
        clean_memo = str(payload_memo or "").strip()

        if not str_uid or not str_pkg or not clean_memo:
            return False

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pending_ton_payments (tg_id, package_id, usdt_price, expected_nano_ton, payload_memo, status)
                    VALUES (%s, %s, %s, %s, %s, 'pending')
                    ON CONFLICT (payload_memo) DO NOTHING;
                    """,
                    (
                        str_uid,
                        str_pkg,
                        float(usdt_price or 0.0),
                        int(expected_nano_ton or 0),
                        clean_memo,
                    ),
                )
        return True
    except Exception as e:
        logger.error(f"⚠️ Failed to create pending payment: {e}")
        return False


def attach_boc_to_pending_payment(tg_id, package_id, boc, payload_memo=None):
    """
    ربط الـ BOC بطلب الدفع المعلق مع التحقق الصارم من تطابق (tg_id, package_id, payload_memo)
    لمنع ثغرة الدفع لباقة رخيصة وتفعيل باقة أغلى.
    """
    try:
        ensure_pending_payments_table()
        boc_hash = _normalize_tx_identifier(boc=boc)
        str_uid = str(tg_id).strip()
        str_pkg = str(package_id).strip()
        clean_memo = str(payload_memo or "").strip()

        if not str_uid or not str_pkg:
            return None

        expected_prefix = f"BUY_{str_pkg}_USER_{str_uid}_"
        if clean_memo and not clean_memo.startswith(expected_prefix):
            logger.error(f"🚨 [Security] محاولة تلاعب بالميمو: {clean_memo} لا يطابق {expected_prefix}")
            return None

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if clean_memo:
                    cur.execute(
                        """
                        UPDATE pending_ton_payments
                        SET boc_hash = COALESCE(%s, boc_hash), updated_at = CURRENT_TIMESTAMP
                        WHERE payload_memo = %s
                          AND tg_id = %s
                          AND package_id = %s
                          AND status = 'pending'
                        RETURNING *;
                        """,
                        (boc_hash or None, clean_memo, str_uid, str_pkg),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE pending_ton_payments
                        SET boc_hash = COALESCE(%s, boc_hash), updated_at = CURRENT_TIMESTAMP
                        WHERE id = (
                            SELECT id FROM pending_ton_payments
                            WHERE tg_id = %s AND package_id = %s AND status = 'pending'
                            ORDER BY created_at DESC LIMIT 1
                        )
                        RETURNING *;
                        """,
                        (boc_hash or None, str_uid, str_pkg),
                    )
                row = cur.fetchone()
                return dict(row) if row else None
    except Exception as e:
        logger.error(f"⚠️ Failed to attach BOC to pending payment: {e}")
        return None


def get_pending_ton_payments(tg_id=None, limit=25):
    try:
        ensure_pending_payments_table()
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if tg_id:
                    cur.execute(
                        """
                        SELECT * FROM pending_ton_payments
                        WHERE tg_id = %s AND status = 'pending'
                        AND created_at >= NOW() - INTERVAL '24 hours'
                        ORDER BY created_at DESC LIMIT %s;
                        """,
                        (str(tg_id), limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT * FROM pending_ton_payments
                        WHERE status = 'pending'
                        AND created_at >= NOW() - INTERVAL '24 hours'
                        ORDER BY created_at ASC LIMIT %s;
                        """,
                        (limit,),
                    )
                return [dict(r) for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"⚠️ Error fetching pending payments: {e}")
        return []


def get_shop_catalog(tg_id=None):
    """جلب بيانات المتجر وبيانات اللاعب الحية مباشرة من Supabase بدون كاش"""
    try:
        farm_settings = {}
        shop_settings = {}
        user_state = {}

        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT key, value FROM settings WHERE key IN ('farm_settings', 'shop_settings')"
                )
                rows = cur.fetchall()
                for row in rows:
                    if row["key"] == "farm_settings":
                        farm_settings = _parse_json_field(row["value"], {})
                    elif row["key"] == "shop_settings":
                        shop_settings = _parse_json_field(row["value"], {})

                if tg_id:
                    clean_uid = str(tg_id).strip()
                    cur.execute(
                        """
                        SELECT * FROM users
                        WHERE tg_id = %s OR user_id = %s OR telegram_id = %s
                        LIMIT 1
                        """,
                        (clean_uid, clean_uid, clean_uid),
                    )
                    u_row = cur.fetchone()
                    if u_row:
                        user_state = dict(u_row)
                        for k, v in list(user_state.items()):
                            if isinstance(v, datetime):
                                user_state[k] = format_iso(v)
                        user_state["balance"] = float(user_state.get("balance") or 0.0)
                        user_state["ad_balance"] = float(user_state.get("ad_balance") or 0.0)
                        user_state["usd_balance"] = float(user_state.get("usd_balance") or 0.0)
                        user_state["znx_balance"] = float(user_state.get("znx_balance") or 0.0)
                        user_state["hourly_rate"] = float(user_state.get("hourly_rate") or 0.10)
                        user_state["max_cap"] = float(user_state.get("max_cap") or 0.5)
                        user_state["extra_storage"] = float(user_state.get("extra_storage") or 0.0)
                        user_state["storage_level"] = int(user_state.get("storage_level") or 0)
                        user_state["upgrades"] = _parse_json_field(user_state.get("upgrades"), {})
                        user_state["vip_status"] = _parse_json_field(user_state.get("vip_status"), {})

        mining_cfg = farm_settings.get("mining_config") or shop_settings.get("mining_config") or {}
        if not isinstance(mining_cfg, dict):
            mining_cfg = {}

        global_max_upgrades = int(mining_cfg.get("max_upgrades_per_level") or 15)

        raw_upgrade_cfg = (
            farm_settings.get("upgrade_config")
            or shop_settings.get("upgrade_config")
        )
        if not raw_upgrade_cfg or not isinstance(raw_upgrade_cfg, dict) or len(raw_upgrade_cfg) == 0:
            raw_upgrade_cfg = copy.deepcopy(DEFAULT_UPGRADE_CONFIG)

        normalized_upgrades = {}
        for k, v in raw_upgrade_cfg.items():
            if isinstance(v, dict):
                c_zn = float(v.get("cost_zn") or v.get("price") or v.get("cost") or 0.0)
                c_usd = float(v.get("cost_usd") or v.get("usd_cost") or v.get("usd") or 0.0)
                r_bonus = float(v.get("rate_bonus") or v.get("rate") or v.get("speed") or 0.0)
                max_lim = int(v.get("max") or v.get("max_limit") or global_max_upgrades)
                normalized_upgrades[str(k)] = {
                    **v,
                    "cost_zn": c_zn,
                    "price": c_zn,
                    "cost_usd": c_usd,
                    "usd_cost": c_usd,
                    "rate_bonus": r_bonus,
                    "rate": r_bonus,
                    "max": max_lim,
                    "max_limit": max_lim,
                }

        raw_storage_caps = (
            farm_settings.get("storage_config")
            or shop_settings.get("storage_config")
            or farm_settings.get("storage_capacities")
            or shop_settings.get("storage_capacities")
        )
        if not raw_storage_caps or not isinstance(raw_storage_caps, dict) or len(raw_storage_caps) == 0:
            raw_storage_caps = copy.deepcopy(DEFAULT_STORAGE_CONFIG)

        normalized_storage = {}
        for k, v in raw_storage_caps.items():
            if isinstance(v, dict):
                cap = float(v.get("capacity") or v.get("cap") or v.get("max_cap") or 0.5)
                c_zn = float(v.get("cost_zn") or v.get("price") or v.get("cost") or 0.0)
                c_usd = float(v.get("cost_usd") or v.get("usd_cost") or v.get("usd") or 0.0)
                normalized_storage[str(k)] = {
                    **v,
                    "capacity": cap,
                    "cap": cap,
                    "cost_zn": c_zn,
                    "price": c_zn,
                    "cost_usd": c_usd,
                    "usd_cost": c_usd,
                }

        db_packages = (
            shop_settings.get("packages")
            or farm_settings.get("packages")
            or shop_settings.get("usdt_packages")
            or farm_settings.get("usdt_packages")
        )
        if not db_packages or not isinstance(db_packages, dict) or len(db_packages) == 0:
            raw_pkgs = copy.deepcopy(DEFAULT_USDT_PACKAGES)
        else:
            raw_pkgs = copy.deepcopy(db_packages)

        usdt_pkgs = {}
        for k, v in raw_pkgs.items():
            if isinstance(v, dict):
                u_price = float(v.get("usdt") or v.get("cost_usd") or v.get("price") or 0.0)
                usdt_pkgs[str(k)] = {
                    **v,
                    "usdt": u_price,
                    "cost_usd": u_price,
                    "price": u_price,
                }

        ton_wallet = (
            shop_settings.get("ton_wallet")
            or shop_settings.get("wallet_address")
            or farm_settings.get("ton_wallet")
            or ""
        )
        try:
            ton_usdt_rate = float(
                shop_settings.get("ton_usdt_rate") or farm_settings.get("ton_usdt_rate") or 5.5
            )
        except (ValueError, TypeError):
            ton_usdt_rate = 5.5

        return {
            "mining_config": mining_cfg,
            "upgrade_config": normalized_upgrades,
            "storage_config": normalized_storage,
            "storage_capacities": normalized_storage,
            "packages": usdt_pkgs,
            "usdt_packages": usdt_pkgs,
            "ton_wallet": ton_wallet,
            "ton_usdt_rate": ton_usdt_rate,
            "user_state": user_state,
        }
    except Exception as e:
        logger.error(f"❌ Error in get_shop_catalog: {e}")
        return {
            "mining_config": {},
            "upgrade_config": copy.deepcopy(DEFAULT_UPGRADE_CONFIG),
            "storage_config": copy.deepcopy(DEFAULT_STORAGE_CONFIG),
            "storage_capacities": copy.deepcopy(DEFAULT_STORAGE_CONFIG),
            "packages": copy.deepcopy(DEFAULT_USDT_PACKAGES),
            "usdt_packages": copy.deepcopy(DEFAULT_USDT_PACKAGES),
            "ton_wallet": "",
            "ton_usdt_rate": 5.5,
            "user_state": {},
        }


def get_shop_settings(tg_id=None):
    return get_shop_catalog(tg_id)


def get_user_vip_status(user_id):
    try:
        if not user_id:
            return {"is_active": False, "package_id": None, "remaining_seconds": 0}

        str_uid = str(user_id).strip()
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT vip_status FROM users WHERE tg_id = %s", (str_uid,))
                row = cur.fetchone()

                if not row or not row.get("vip_status"):
                    return {"is_active": False, "package_id": None, "remaining_seconds": 0}

                vip_status = _parse_json_field(row["vip_status"], {})
                if not isinstance(vip_status, dict) or not vip_status:
                    return {"is_active": False, "package_id": None, "remaining_seconds": 0}

                expires_at_str = vip_status.get("expires_at")
                if not expires_at_str:
                    return {"is_active": False, "package_id": None, "remaining_seconds": 0}

                now_dt = datetime.now(timezone.utc)
                clean_exp_str = str(expires_at_str).replace(" ", "T").replace("Z", "+00:00")
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
                    "referral_rate": float(vip_status.get("referral_rate") or 0.0) if is_active else 0.0,
                    "ref_min_upgrades": int(vip_status.get("ref_min_upgrades") or 3) if is_active else 3,
                    "ref_withdraw_fee": float(vip_status.get("ref_withdraw_fee") or 0.0) if is_active else 0.0,
                }
    except Exception as e:
        logger.error(f"❌ Error in get_user_vip_status: {e}")
        return {"is_active": False, "package_id": None, "remaining_seconds": 0}


def log_purchase_transaction(tg_id, tx_type, item_id, cost_zn=0.0, cost_usd=0.0, tx_hash=None, details=None):
    try:
        str_uid = str(tg_id).strip()
        safe_tx_h = _normalize_tx_identifier(tx_hash=tx_hash) or None
        details_obj = details if isinstance(details, dict) else {}

        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO purchase_history (tg_id, type, item_id, cost_zn, cost_usd, tx_hash, details)
                    VALUES (%s, %s, %s, %s, %s, %s, %s);
                    """,
                    (str_uid, str(tx_type), str(item_id), float(cost_zn or 0.0), float(cost_usd or 0.0), safe_tx_h, Json(details_obj)),
                )

                if safe_tx_h:
                    cur.execute(
                        """
                        INSERT INTO processed_txs (tx_hash, tg_id, type, cost_zn, cost_usd, details)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (tx_hash) DO NOTHING;
                        """,
                        (safe_tx_h, str_uid, str(tx_type), float(cost_zn or 0.0), float(cost_usd or 0.0), json.dumps(details_obj, ensure_ascii=False)),
                    )
        return True
    except Exception as e:
        logger.error(f"⚠️ Failed to log purchase transaction: {e}")
        return False


def buy_mining_upgrade(tg_id, upgrade_level):
    """شراء ترقية سرعة التعدين باستخدام get_db_transaction لضمان القفل الذري الحقيقي (FOR UPDATE)"""
    try:
        if not tg_id or upgrade_level is None:
            return False, "بيانات الترقية غير صالحة", {}

        catalog = get_shop_catalog()
        mining_cfg = catalog.get("upgrade_config", {})
        global_max = int(catalog.get("mining_config", {}).get("max_upgrades_per_level") or 15)
        lvl_str = str(upgrade_level).strip()

        if lvl_str not in mining_cfg:
            return False, "مستوى الترقية غير موجود في المتجر", {}

        item_info = mining_cfg[lvl_str]
        cost_zn = float(item_info.get("cost_zn") or item_info.get("price") or 0.0)
        cost_usd = float(item_info.get("cost_usd") or item_info.get("usd_cost") or 0.0)
        rate_bonus = float(item_info.get("rate_bonus") or item_info.get("rate") or 0.0)
        max_purchases = int(item_info.get("max") or item_info.get("max_limit") or global_max)

        str_uid = str(tg_id).strip()
        tx_ctx = get_db_transaction() if callable(get_db_transaction) else get_db_connection()

        with tx_ctx as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    return False, "المستخدم غير موجود", {}

                user_data = dict(user_data)
                if _is_user_row_banned(user_data):
                    return False, "⛔ هذا الحساب محظور ولا يمكنه إجراء عمليات شراء.", {}

                user_upgrades = _parse_json_field(user_data.get("upgrades"), {})

                # إصلاح خطأ ?? البرمجي بطريقة بايثون القياسية الآمنة
                raw_owned = user_upgrades.get(f"lvl{lvl_str}")
                if raw_owned is None:
                    raw_owned = user_upgrades.get(lvl_str, 0)
                current_owned = int(raw_owned or 0)

                if current_owned >= max_purchases:
                    return False, "وصلت للحد الأقصى لشراء هذه الترقية", {}

                current_balance = float(user_data.get("balance") or 0.0)
                current_usd_balance = float(user_data.get("usd_balance") or 0.0)

                if current_balance < cost_zn:
                    return False, f"رصيد ZN غير كافٍ! تحتاج {cost_zn:g} ZN", {}

                if current_usd_balance < cost_usd:
                    return False, f"رصيد الدولار غير كافٍ! تحتاج ${cost_usd:g}", {}

                last_claim_raw = user_data.get("last_claim_time")
                now_dt = datetime.now(timezone.utc)
                old_rate = float(user_data.get("hourly_rate") or 0.0)
                old_cap = float(user_data.get("max_cap") or 100.0)

                pending_mined = 0.0
                if last_claim_raw:
                    try:
                        clean_str = str(last_claim_raw).replace(" ", "T").replace("Z", "+00:00")
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

                # توحيد المفتاح لمنع ازدواجية العد بين lvlX و X
                if lvl_str in user_upgrades:
                    user_upgrades.pop(lvl_str, None)
                user_upgrades[f"lvl{lvl_str}"] = current_owned + 1
                total_upgrades_cnt = sum(int(v) for v in user_upgrades.values() if isinstance(v, (int, float)))

                cur.execute(
                    """
                    UPDATE users SET
                        balance = %s,
                        usd_balance = %s,
                        hourly_rate = %s,
                        upgrades = %s,
                        upgrades_count = %s,
                        last_claim_time = %s,
                        last_active_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tg_id = %s
                    """,
                    (new_balance, new_usd_balance, new_hourly_rate, Json(user_upgrades), total_upgrades_cnt, new_last_claim_dt, str_uid),
                )

                u_name = user_data.get("first_name") or user_data.get("name") or "صديق"
                cur.execute(
                    """
                    UPDATE user_friends
                    SET upgrades_count = GREATEST(COALESCE(upgrades_count, 0), %s),
                        first_name = %s,
                        name = %s,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE friend_id = %s;
                    """,
                    (total_upgrades_cnt, u_name, u_name, str_uid),
                )

                updated_fields = {
                    "balance": new_balance,
                    "usd_balance": new_usd_balance,
                    "hourly_rate": new_hourly_rate,
                    "upgrades": user_upgrades,
                    "upgrades_count": total_upgrades_cnt,
                    "last_claim_time": format_iso(new_last_claim_dt),
                }

        log_purchase_transaction(tg_id, "mining_upgrade", lvl_str, cost_zn, cost_usd)
        return True, f"تم شراء الترقية مستوى {lvl_str} بنجاح!", updated_fields

    except Exception as e:
        logger.error(f"❌ Error buying mining upgrade: {e}")
        return False, str(e), {}


def upgrade_storage_capacity(tg_id):
    """ترقية سعة المخزن باستخدام get_db_transaction لضمان القفل الذري الحقيقي (FOR UPDATE)"""
    try:
        if not tg_id:
            return False, "معرف غير صالح", {}

        catalog = get_shop_catalog()
        storage_cfg = catalog.get("storage_config", {})
        str_uid = str(tg_id).strip()
        tx_ctx = get_db_transaction() if callable(get_db_transaction) else get_db_connection()

        with tx_ctx as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    return False, "المستخدم غير موجود", {}

                user_data = dict(user_data)
                if _is_user_row_banned(user_data):
                    return False, "⛔ هذا الحساب محظور ولا يمكنه إجراء عمليات شراء.", {}

                current_lvl = int(user_data.get("storage_level") or 0)
                next_lvl_str = str(current_lvl + 1)

                if next_lvl_str not in storage_cfg:
                    return False, "وصلت لأعلى مستوى مخزن حالياً!", {}

                next_info = storage_cfg[next_lvl_str]
                cost_zn = float(next_info.get("cost_zn") or next_info.get("price") or 0.0)
                cost_usd = float(next_info.get("cost_usd") or next_info.get("usd_cost") or 0.0)
                new_base_capacity = float(next_info.get("capacity") or next_info.get("cap") or 100.0)
                extra_storage = float(user_data.get("extra_storage") or 0.0)

                current_balance = float(user_data.get("balance") or 0.0)
                current_usd_balance = float(user_data.get("usd_balance") or 0.0)

                if current_balance < cost_zn:
                    return False, f"رصيدك من ZN غير كافٍ لترقية المخزن! تحتاج {cost_zn:g} ZN", {}

                if current_usd_balance < cost_usd:
                    return False, f"رصيدك من الدولار غير كافٍ لترقية المخزن! تحتاج ${cost_usd:g}", {}

                last_claim_raw = user_data.get("last_claim_time")
                now_dt = datetime.now(timezone.utc)
                hourly_rate = float(user_data.get("hourly_rate") or 0.0)
                old_cap = float(user_data.get("max_cap") or 100.0)

                pending_mined = 0.0
                if last_claim_raw:
                    try:
                        clean_str = str(last_claim_raw).replace(" ", "T").replace("Z", "+00:00")
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
                            clean_exp = str(exp_str).replace(" ", "T").replace("Z", "+00:00")
                            exp_dt = datetime.fromisoformat(clean_exp)
                            if exp_dt.tzinfo is None:
                                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                            if exp_dt > now_dt:
                                is_double_active = True
                        except Exception:
                            pass

                raw_cap = new_base_capacity + extra_storage
                new_max_cap = round(raw_cap * 2.0 if is_double_active else raw_cap, 4)

                if hourly_rate > 0:
                    time_needed = pending_mined / (hourly_rate / 3600.0)
                    new_last_claim_dt = now_dt - timedelta(seconds=time_needed)
                else:
                    new_last_claim_dt = now_dt

                cur.execute(
                    """
                    UPDATE users SET
                        balance = %s,
                        usd_balance = %s,
                        storage_level = %s,
                        max_cap = %s,
                        last_claim_time = %s,
                        last_active_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tg_id = %s
                    """,
                    (new_balance, new_usd_balance, int(next_lvl_str), new_max_cap, new_last_claim_dt, str_uid),
                )

                updated_fields = {
                    "balance": new_balance,
                    "usd_balance": new_usd_balance,
                    "storage_level": int(next_lvl_str),
                    "max_cap": new_max_cap,
                    "last_claim_time": format_iso(new_last_claim_dt),
                }

        log_purchase_transaction(tg_id, "storage_upgrade", next_lvl_str, cost_zn, cost_usd)
        return True, f"تم ترقية المخزن إلى المستوى {next_lvl_str} (سعة: {new_max_cap:g}) بنجاح!", updated_fields

    except Exception as e:
        logger.error(f"❌ Error upgrading storage: {e}")
        return False, str(e), {}


def process_upgrade_purchase(tg_id, upgrade_type, upgrade_id):
    if str(upgrade_type).lower() in ["mining", "card"]:
        return buy_mining_upgrade(tg_id, upgrade_id)
    elif str(upgrade_type).lower() in ["storage", "capacity"]:
        return upgrade_storage_capacity(tg_id)
    else:
        return False, "نوع الترقية غير معروف", {}


def verify_and_apply_package(tg_id, package_id, boc=None, tx_hash=None, payload_memo=None):
    """
    تفعيل باقات VIP عبر get_db_transaction لتوفير القفل الذري الحقيقي ومنع Race Condition
    مع التحقق الجنائي من تطابق الباقة والمستخدم والميمو.
    """
    try:
        if not tg_id or not package_id:
            return False, "بيانات غير صالحة", {}

        str_uid = str(tg_id).strip()
        pkg_key = str(package_id).strip()
        clean_memo = str(payload_memo or "").strip()

        expected_prefix = f"BUY_{pkg_key}_USER_{str_uid}_"
        if not clean_memo or not clean_memo.startswith(expected_prefix):
            return False, "⛔ معرف الدفع (Memo) غير صالح أو لا يطابق هذه الباقة.", {}

        tx_identifier = _normalize_tx_identifier(tx_hash=tx_hash, boc=boc)
        boc_hash = _normalize_tx_identifier(boc=boc) if boc else ""

        if not tx_identifier:
            return False, "معرف المعاملة مفقود أو غير صالح", {}

        catalog = get_shop_catalog()
        pkgs = catalog.get("packages", {})

        if pkg_key not in pkgs:
            return False, "الباقة غير موجودة في المتجر", {}

        pkg_info = pkgs[pkg_key]
        duration_days = int(pkg_info.get("duration_days") or 30)
        features = pkg_info.get("features", {}) if isinstance(pkg_info.get("features"), dict) else {}

        auto_bot = bool(features.get("auto_bot", False))
        double_storage = bool(features.get("double_storage", False))
        referral_rate = float(features.get("referral_rate") or 0.0)
        ref_min_upgrades = int(features.get("ref_min_upgrades") or 3)
        ref_withdraw_fee = float(features.get("ref_withdraw_fee") or 0.0)

        zn_add = float(pkg_info.get("zn_add") or 0.0)
        rate_add = float(pkg_info.get("rate_add") or 0.0)
        storage_add = float(pkg_info.get("storage_add") or 0.0)
        usd_add = float(pkg_info.get("usd_add") or 0.0)
        pkg_price_usd = float(pkg_info.get("usdt") or pkg_info.get("cost_usd") or pkg_info.get("price") or 0.0)

        ensure_pending_payments_table()
        tx_ctx = get_db_transaction() if callable(get_db_transaction) else get_db_connection()

        with tx_ctx as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 1. التحقق من وجود طلب دفع معلق مطابق لنفس المستخدم ونفس الباقة ونفس الميمو
                cur.execute(
                    """
                    SELECT * FROM pending_ton_payments
                    WHERE payload_memo = %s AND tg_id = %s AND package_id = %s
                    FOR UPDATE
                    """,
                    (clean_memo, str_uid, pkg_key),
                )
                pending_row = cur.fetchone()
                if not pending_row:
                    return False, "⛔ لم يتم العثور على طلب دفع مسجل مطابق لهذه الباقة.", {}

                if str(pending_row.get("status") or "").lower() == "completed":
                    return False, "تمت معالجة وتفعيل هذا الطلب سابقاً!", {}

                # 2. التحقق من عدم معالجة الهاش أو الـ BOC سابقاً
                check_hashes = [h for h in {tx_identifier, boc_hash, clean_memo} if h]
                cur.execute(
                    "SELECT 1 FROM processed_txs WHERE tx_hash = ANY(%s)",
                    (check_hashes,),
                )
                if cur.fetchone():
                    return False, "تمت معالجة هذه العملية سابقاً!", {}

                cur.execute(
                    """
                    INSERT INTO processed_txs (tx_hash, tg_id, package_id, type, cost_usd, details)
                    VALUES (%s, %s, %s, 'vip_package', %s, %s)
                    ON CONFLICT (tx_hash) DO NOTHING
                    RETURNING tx_hash;
                    """,
                    (tx_identifier, str_uid, pkg_key, pkg_price_usd, clean_memo),
                )
                if not cur.fetchone():
                    return False, "تمت معالجة هذه العملية سابقاً!", {}

                if boc_hash and boc_hash != tx_identifier:
                    cur.execute(
                        """
                        INSERT INTO processed_txs (tx_hash, tg_id, package_id, type, cost_usd, details)
                        VALUES (%s, %s, %s, 'vip_package_boc', %s, %s)
                        ON CONFLICT (tx_hash) DO NOTHING;
                        """,
                        (boc_hash, str_uid, pkg_key, pkg_price_usd, clean_memo),
                    )

                # 3. قفل صف المستخدم والتحقق من عدم حظره
                cur.execute("SELECT * FROM users WHERE tg_id = %s FOR UPDATE", (str_uid,))
                user_data = cur.fetchone()

                if not user_data:
                    raise ValueError("المستخدم غير موجود")

                user_data = dict(user_data)
                if _is_user_row_banned(user_data):
                    raise ValueError("هذا الحساب محظور لمخالفة القوانين")

                current_balance = float(user_data.get("balance") or 0.0)
                current_usd = float(user_data.get("usd_balance") or 0.0)
                current_rate = float(user_data.get("hourly_rate") or 0.0)
                current_extra_storage = float(user_data.get("extra_storage") or 0.0)
                current_max_cap = float(user_data.get("max_cap") or 100.0)
                last_claim_raw = user_data.get("last_claim_time")

                now_dt = datetime.now(timezone.utc)

                existing_vip = _parse_json_field(user_data.get("vip_status"), {})
                existing_expires_str = existing_vip.get("expires_at")
                is_currently_active = False
                existing_expires_dt = None

                if existing_expires_str:
                    try:
                        clean_exp = str(existing_expires_str).replace(" ", "T").replace("Z", "+00:00")
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
                        clean_str = str(last_claim_raw).replace(" ", "T").replace("Z", "+00:00")
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
                    new_max_cap = max(0.5, current_max_cap / 2.0)

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
                    "updated_at": format_iso(now_dt),
                }

                cur.execute(
                    """
                    UPDATE users SET
                        balance = %s,
                        usd_balance = %s,
                        hourly_rate = %s,
                        extra_storage = %s,
                        max_cap = %s,
                        last_claim_time = %s,
                        vip_status = %s,
                        bot_active = %s,
                        bot_expires_at = %s,
                        is_vip = TRUE,
                        vip_active = TRUE,
                        last_active_at = CURRENT_TIMESTAMP,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE tg_id = %s
                    """,
                    (new_balance, new_usd, new_rate, new_extra_storage, new_max_cap, new_last_claim_dt, Json(new_vip_status), auto_bot, new_expires_dt, str_uid),
                )

                cur.execute(
                    """
                    UPDATE pending_ton_payments
                    SET status = 'completed', tx_hash = %s, updated_at = CURRENT_TIMESTAMP
                    WHERE payload_memo = %s AND tg_id = %s AND package_id = %s;
                    """,
                    (tx_identifier, clean_memo, str_uid, pkg_key),
                )

                updated_fields = {
                    "balance": new_balance,
                    "usd_balance": new_usd,
                    "hourly_rate": new_rate,
                    "extra_storage": new_extra_storage,
                    "max_cap": new_max_cap,
                    "last_claim_time": format_iso(new_last_claim_dt),
                    "vip_status": new_vip_status,
                    "is_vip": True,
                    "vip_active": True,
                }

        log_purchase_transaction(
            tg_id,
            "vip_package",
            pkg_key,
            0.0,
            pkg_price_usd,
            tx_identifier,
            details={"payload_memo": clean_memo, "boc_hash": boc_hash},
        )
        return True, "تم تفعيل الباقة بنجاح!", updated_fields

    except Exception as e:
        logger.error(f"❌ Error applying package: {e}")
        return False, str(e), {}


def get_user_purchase_history(tg_id, limit=20):
    try:
        if not tg_id:
            return []

        str_uid = str(tg_id).strip()
        with get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, type, item_id, cost_zn, cost_usd, tx_hash, details, created_at
                    FROM purchase_history
                    WHERE tg_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (str_uid, limit),
                )
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

import time
from datetime import datetime, timezone, timedelta
from google.cloud import firestore
from database import get_db

# الدقة الداخلية أعلى من دقة العرض لمنع ضياع أرباح التعدين الصغيرة.
ZN_INTERNAL_DECIMALS = 8
USD_INTERNAL_DECIMALS = 6
DISPLAY_ZN_DECIMALS = 4

def round_zn(value):
    try:
        return round(float(value), ZN_INTERNAL_DECIMALS)
    except (TypeError, ValueError):
        return 0.0

def round_usd(value):
    try:
        return round(float(value), USD_INTERNAL_DECIMALS)
    except (TypeError, ValueError):
        return 0.0

def to_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("true", "1", "yes")
    if isinstance(val, (int, float)):
        return val != 0
    return False

_SETTINGS_CACHE = {"data": None, "timestamp": 0}
CACHE_TTL_SECONDS = 15

DEFAULT_GAME_SETTINGS = {
    "daily_rewards": [
        5, 10, 15, 20, 25, 30, 40, 45, 50, 60,
        65, 70, 75, 90, 100, 110, 120, 130, 140, 160,
        180, 200, 220, 240, 270, 300, 330, 360, 400, 450
    ],
    "mining_config": {
        "daily_boost_reward": 0.15,
        "max_daily_boost_rate": 4.5,
        "boost_max_reward_coins": 35.0,
        "claim_cooldown_seconds": 15,
        "base_free_rate": 0.05,
        "max_upgrades_per_level": 15
    },
    "storage_capacities": {
        "0": {"capacity": 30.0, "cost_zn": 0.0, "cost_usd": 0.0},
        "1": {"capacity": 150.0, "cost_zn": 400.0, "cost_usd": 0.0},
        "2": {"capacity": 500.0, "cost_zn": 1200.0, "cost_usd": 0.05},
        "3": {"capacity": 1500.0, "cost_zn": 3500.0, "cost_usd": 0.10},
        "4": {"capacity": 4000.0, "cost_zn": 10000.0, "cost_usd": 0.15},
        "5": {"capacity": 10000.0, "cost_zn": 25000.0, "cost_usd": 0.20},
        "6": {"capacity": 25000.0, "cost_zn": 65000.0, "cost_usd": 0.25},
        "7": {"capacity": 70000.0, "cost_zn": 180000.0, "cost_usd": 0.30},
        "8": {"capacity": 200000.0, "cost_zn": 500000.0, "cost_usd": 0.35},
        "9": {"capacity": 600000.0, "cost_zn": 1500000.0, "cost_usd": 0.40}
    },
    "upgrade_config": {
        "1": {"cost_zn": 600.0, "cost_usd": 0.0, "rate_bonus": 1.0},
        "2": {"cost_zn": 1500.0, "cost_usd": 0.10, "rate_bonus": 2.5},
        "3": {"cost_zn": 3800.0, "cost_usd": 0.15, "rate_bonus": 6.0},
        "4": {"cost_zn": 10000.0, "cost_usd": 0.20, "rate_bonus": 15.0},
        "5": {"cost_zn": 28000.0, "cost_usd": 0.25, "rate_bonus": 40.0},
        "6": {"cost_zn": 75000.0, "cost_usd": 0.30, "rate_bonus": 100.0},
        "7": {"cost_zn": 200000.0, "cost_usd": 0.35, "rate_bonus": 250.0},
        "8": {"cost_zn": 500000.0, "cost_usd": 0.40, "rate_bonus": 600.0},
        "9": {"cost_zn": 1400000.0, "cost_usd": 0.50, "rate_bonus": 1500.0}
    }
}

def get_game_settings(force_refresh=False):
    global _SETTINGS_CACHE
    now_ts = time.time()

    if (
        not force_refresh
        and _SETTINGS_CACHE["data"]
        and (now_ts - _SETTINGS_CACHE["timestamp"] < CACHE_TTL_SECONDS)
    ):
        return _SETTINGS_CACHE["data"]

    db = get_db()
    try:
        doc_ref = db.collection("settings").document("farm_settings")
        doc = doc_ref.get()

        if doc.exists:
            data = doc.to_dict() or DEFAULT_GAME_SETTINGS
            _SETTINGS_CACHE = {"data": data, "timestamp": now_ts}
            return data

        doc_ref.set(DEFAULT_GAME_SETTINGS)
        _SETTINGS_CACHE = {"data": DEFAULT_GAME_SETTINGS, "timestamp": now_ts}
        return DEFAULT_GAME_SETTINGS

    except Exception as e:
        print(f"⚠️ خطأ أثناء جلب إعدادات المزرعة من Firebase: {e}")

    return _SETTINGS_CACHE["data"] or DEFAULT_GAME_SETTINGS

def parse_daily_rewards(rewards_data):
    if isinstance(rewards_data, list) and len(rewards_data) > 0:
        try:
            return [int(x) for x in rewards_data[:30]]
        except (TypeError, ValueError):
            pass

    if isinstance(rewards_data, dict):
        result = []
        for i in range(1, 31):
            value = rewards_data.get(f"day_{i}")
            if value is None:
                value = rewards_data.get(str(i))
            if value is None:
                value = DEFAULT_GAME_SETTINGS["daily_rewards"][i - 1]
            try:
                result.append(int(value))
            except (TypeError, ValueError):
                result.append(DEFAULT_GAME_SETTINGS["daily_rewards"][i - 1])
        return result

    return DEFAULT_GAME_SETTINGS["daily_rewards"]

def get_base_storage_capacity(storage_level, settings=None):
    if settings is None:
        settings = get_game_settings()

    try:
        level = int(storage_level)
    except (ValueError, TypeError):
        level = 0

    level = max(0, min(level, 9))
    capacities = settings.get("storage_capacities") or DEFAULT_GAME_SETTINGS["storage_capacities"]

    value = capacities.get(str(level))
    if value is None:
        value = capacities.get(level)

    if isinstance(value, dict):
        return round(float(value.get("capacity", 30.0)), 2)
    if value is not None:
        return round(float(value), 2)

    return 30.0

def calculate_user_max_cap(user_data, settings=None):
    if settings is None:
        settings = get_game_settings()

    storage_level = user_data.get("storage_level", 0)
    base_cap = get_base_storage_capacity(storage_level, settings)

    try:
        extra_cap = float(user_data.get("extra_storage", 0.0))
    except (TypeError, ValueError):
        extra_cap = 0.0

    return round(max(0.0, base_cap + extra_cap), 2)

def calculate_accrued_mined(user_data, now_dt, max_cap):
    """
    يحسب المحصول بدقة داخلية 8 منازل.
    مهم: لا يتم تقريب المحصول إلى منزلتين لأن ذلك كان يؤدي لضياع
    أرباح التعدين الصغيرة، خصوصاً عند معدل 0.05 ZN/h.
    """
    last_claim_str = user_data.get("last_claim_time")

    try:
        hourly_rate = float(user_data.get("hourly_rate", 0.05))
    except (TypeError, ValueError):
        hourly_rate = 0.05

    if not last_claim_str or hourly_rate <= 0 or max_cap <= 0:
        return 0.0

    try:
        last_claim = datetime.fromisoformat(
            str(last_claim_str).replace("Z", "+00:00")
        )
        if last_claim.tzinfo is None:
            last_claim = last_claim.replace(tzinfo=timezone.utc)

        seconds_passed = max(0.0, (now_dt - last_claim).total_seconds())
        mined = (hourly_rate / 3600.0) * seconds_passed

        return round(min(max(0.0, mined), max_cap), ZN_INTERNAL_DECIMALS)
    except Exception:
        return 0.0

def dismiss_welcome_db(user_id_str):
    db = get_db()
    user_ref = db.collection("users").document(user_id_str)
    user_ref.set(
        {"welcome_seen": True, "is_new_user": False},
        merge=True
    )
    return {"success": True, "welcome_seen": True, "is_new_user": False}

def get_or_create_user_farm_data(user_id_str):
    db = get_db()
    user_ref = db.collection("users").document(user_id_str)
    user_doc = user_ref.get()
    now = datetime.now(timezone.utc)

    game_settings = get_game_settings()
    mining_cfg = game_settings.get(
        "mining_config",
        DEFAULT_GAME_SETTINGS["mining_config"]
    )
    base_free_rate = float(mining_cfg.get("base_free_rate", 0.05))

    if not user_doc.exists:
        base_cap = get_base_storage_capacity(0, game_settings)

        user_data = {
            "tg_id": user_id_str,
            "telegram_id": user_id_str,
            "balance": 0.0,
            "usd_balance": 0.0,
            "hourly_rate": base_free_rate,
            "daily_boost_rate": 0.0,
            "unclaimed": 0.0,
            "storage_level": 0,
            "extra_storage": 0.0,
            "max_cap": base_cap,
            "daily_day": 1,
            "daily_streak": 1,
            "last_claim_time": now.isoformat(),
            "last_daily_claim_date": None,
            "last_boost_date": None,
            "ads_watched": 0,
            "upgrades": {},
            "upgrades_count": 0,
            "welcome_seen": False,
            "is_new_user": True
        }
        user_ref.set(user_data)

    else:
        user_data = user_doc.to_dict() or {}
        auto_fix = {}

        if "welcome_seen" not in user_data:
            has_progress = bool(
                user_data.get("upgrades")
                or user_data.get("last_daily_claim_date")
                or user_data.get("last_boost_date")
            )
            auto_fix["welcome_seen"] = has_progress
            auto_fix["is_new_user"] = not has_progress

        if "usd_balance" not in user_data:
            auto_fix["usd_balance"] = 0.0

        if "hourly_rate" not in user_data or float(user_data.get("hourly_rate", 0)) == 0.0:
            auto_fix["hourly_rate"] = base_free_rate

        if "daily_boost_rate" not in user_data:
            auto_fix["daily_boost_rate"] = 0.0

        if "ads_watched" not in user_data:
            auto_fix["ads_watched"] = 0

        if "storage_level" not in user_data:
            auto_fix["storage_level"] = 0

        if "upgrades" not in user_data:
            auto_fix["upgrades"] = {}

        if "upgrades_count" not in user_data:
            upgrades_dict = user_data.get("upgrades", {})
            if isinstance(upgrades_dict, dict):
                auto_fix["upgrades_count"] = sum(
                    int(v) for v in upgrades_dict.values()
                    if isinstance(v, (int, float))
                )
            else:
                auto_fix["upgrades_count"] = 0

        expected_max_cap = calculate_user_max_cap(user_data, game_settings)
        if user_data.get("max_cap") != expected_max_cap:
            auto_fix["max_cap"] = expected_max_cap

        if auto_fix:
            user_ref.update(auto_fix)
            user_data.update(auto_fix)

    expected_max_cap = calculate_user_max_cap(user_data, game_settings)
    user_data["max_cap"] = expected_max_cap

    user_data["balance"] = round_zn(user_data.get("balance", 0.0))
    user_data["usd_balance"] = round_usd(user_data.get("usd_balance", 0.0))
    user_data["unclaimed"] = calculate_accrued_mined(
        user_data,
        now,
        expected_max_cap
    )

    welcome_seen = to_bool(user_data.get("welcome_seen", False))
    user_data["welcome_seen"] = welcome_seen
    user_data["is_new_user"] = not welcome_seen

    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    last_daily_claim = user_data.get("last_daily_claim_date")

    try:
        raw_daily_day = int(
            user_data.get("daily_day")
            or user_data.get("daily_streak")
            or 1
        )
    except (TypeError, ValueError):
        raw_daily_day = 1

    raw_daily_day = max(1, min(raw_daily_day, 30))

    if last_daily_claim == today_str:
        effective_daily_day = raw_daily_day
    elif last_daily_claim == yesterday_str:
        effective_daily_day = min(raw_daily_day + 1, 30)
    else:
        effective_daily_day = 1

    user_data["daily_day"] = effective_daily_day
    user_data["daily_streak"] = effective_daily_day

    return user_data, game_settings, now

def claim_mined_tokens_db(user_id_str):
    db = get_db()
    user_ref = db.collection("users").document(user_id_str)
    game_settings = get_game_settings()

    mining_cfg = game_settings.get(
        "mining_config",
        DEFAULT_GAME_SETTINGS["mining_config"]
    )
    cooldown_seconds = max(
        0,
        int(mining_cfg.get("claim_cooldown_seconds", 15))
    )

    @firestore.transactional
    def run_claim_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)

        if not snapshot.exists:
            return {"success": False, "error": "المستخدم غير موجود"}

        user_data = snapshot.to_dict() or {}
        now = datetime.now(timezone.utc)

        last_claim_str = user_data.get("last_claim_time")

        if last_claim_str:
            try:
                last_claim = datetime.fromisoformat(
                    str(last_claim_str).replace("Z", "+00:00")
                )
                if last_claim.tzinfo is None:
                    last_claim = last_claim.replace(tzinfo=timezone.utc)

                seconds_passed = (now - last_claim).total_seconds()

                if seconds_passed < cooldown_seconds:
                    wait = max(1, int(cooldown_seconds - seconds_passed))
                    return {
                        "success": False,
                        "error": f"الرجاء الانتظار {wait} ثانية قبل التجميع مجدداً"
                    }
            except Exception:
                pass

        max_cap = calculate_user_max_cap(user_data, game_settings)
        mined_amount = calculate_accrued_mined(user_data, now, max_cap)

        if mined_amount <= 0:
            return {"success": False, "error": "المخزن فارغ حالياً"}

        current_balance = round_zn(user_data.get("balance", 0.0))
        current_usd_balance = round_usd(user_data.get("usd_balance", 0.0))

        new_balance = round_zn(current_balance + mined_amount)
        now_iso = now.isoformat()

        transaction.update(
            ref,
            {
                "balance": new_balance,
                "last_claim_time": now_iso
            }
        )

        referrer_id = (
            user_data.get("referrer_id")
            or user_data.get("referred_by")
            or user_data.get("invited_by")
        )
        upgrades_cnt = user_data.get("upgrades_count", 0)
        user_name = (
            user_data.get("first_name")
            or user_data.get("name")
            or user_data.get("username")
        )

        return {
            "success": True,
            "new_balance": new_balance,
            "new_usd_balance": current_usd_balance,
            "last_claim_time": now_iso,
            "unclaimed": 0.0,
            "server_time": now_iso,
            "claimed_amount": round_zn(mined_amount),
            "referrer_id": referrer_id,
            "upgrades_count": upgrades_cnt,
            "user_name": user_name
        }

    try:
        transaction = db.transaction()
        result = run_claim_transaction(transaction, user_ref)
    except Exception as e:
        return {
            "success": False,
            "error": f"تعذر تنفيذ التجميع: {str(e)}"
        }

    if (
        result.get("success")
        and result.get("referrer_id")
        and result.get("claimed_amount", 0) > 0
    ):
        try:
            from friends.friends_db import add_referral_reward

            add_referral_reward(
                referrer_id=result["referrer_id"],
                user_id=user_id_str,
                mined_amount=result["claimed_amount"],
                user_upgrades_count=result.get("upgrades_count"),
                user_name=result.get("user_name")
            )
        except Exception as e:
            print(f"⚠️ Error adding referral reward on claim: {e}")

    return result

def buy_upgrade_db(user_id_str, level):
    level_str = str(level)
    db = get_db()
    user_ref = db.collection("users").document(user_id_str)
    game_settings = get_game_settings()

    upgrade_configs = (
        game_settings.get("upgrade_config")
        or DEFAULT_GAME_SETTINGS["upgrade_config"]
    )

    if level_str not in upgrade_configs:
        return {"success": False, "error": "بيانات المستوى غير متوفرة"}

    level_cfg = upgrade_configs[level_str]

    cost_zn = float(
        level_cfg.get(
            "cost_zn",
            level_cfg.get("base_cost", level_cfg.get("price", 0))
        )
    )
    cost_usd = float(
        level_cfg.get(
            "cost_usd",
            level_cfg.get("base_cost_usd", 0.0)
        )
    )
    rate_bonus = round(
        float(level_cfg.get("rate_bonus", level_cfg.get("rate", 0))),
        2
    )

    @firestore.transactional
    def run_upgrade_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)

        if not snapshot.exists:
            return {"success": False, "error": "المستخدم غير موجود"}

        user_data = snapshot.to_dict() or {}

        current_balance = round_zn(user_data.get("balance", 0.0))
        current_usd_balance = round_usd(user_data.get("usd_balance", 0.0))

        if current_balance + 1e-12 < cost_zn:
            return {
                "success": False,
                "error": f"رصيد العملات غير كافٍ! سعر الترقية {cost_zn:,.0f} ZN"
            }

        if cost_usd > 0 and current_usd_balance + 1e-12 < cost_usd:
            return {
                "success": False,
                "error": f"رصيد الدولار غير كافٍ! يتطلب ${cost_usd:.2f} USD"
            }

        upgrades = user_data.get("upgrades", {})
        if not isinstance(upgrades, dict):
            upgrades = {}

        lvl_key = f"lvl{level_str}"

        try:
            current_count = int(upgrades.get(lvl_key, 0))
        except (TypeError, ValueError):
            current_count = 0

        max_upgrades = int(
            game_settings.get("mining_config", {}).get(
                "max_upgrades_per_level", 15
            )
        )
        max_upgrades = max(1, max_upgrades)

        if current_count >= max_upgrades:
            return {
                "success": False,
                "error": f"لقد وصلت للحد الأقصى للشراء لهذا المستوى ({max_upgrades}/{max_upgrades})"
            }

        if int(level_str) > 1:
            prev_key = f"lvl{int(level_str) - 1}"
            try:
                prev_count = int(upgrades.get(prev_key, 0))
            except (TypeError, ValueError):
                prev_count = 0

            if prev_count == 0:
                return {
                    "success": False,
                    "error": "يجب شراء المستوى السابق أولاً"
                }

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        max_cap = calculate_user_max_cap(user_data, game_settings)
        mined_amount = calculate_accrued_mined(user_data, now, max_cap)

        new_balance = round_zn(current_balance - cost_zn)
        new_usd_balance = round_usd(current_usd_balance - cost_usd)

        current_hourly_rate = float(user_data.get("hourly_rate", 0.05))
        new_hourly_rate = round(current_hourly_rate + rate_bonus, 2)

        if new_hourly_rate > 0 and mined_amount > 0:
            equivalent_seconds = mined_amount / (new_hourly_rate / 3600.0)
            new_last_claim_iso = (
                now - timedelta(seconds=equivalent_seconds)
            ).isoformat()
        else:
            new_last_claim_iso = now_iso

        upgrades[lvl_key] = current_count + 1

        total_upgrades_count = sum(
            int(v)
            for v in upgrades.values()
            if isinstance(v, (int, float))
        )

        transaction.update(
            ref,
            {
                "balance": new_balance,
                "usd_balance": new_usd_balance,
                "hourly_rate": new_hourly_rate,
                "upgrades": upgrades,
                "upgrades_count": total_upgrades_count,
                "last_claim_time": new_last_claim_iso
            }
        )

        referrer_id = (
            user_data.get("referrer_id")
            or user_data.get("referred_by")
            or user_data.get("invited_by")
        )

        return {
            "success": True,
            "new_balance": new_balance,
            "new_usd_balance": new_usd_balance,
            "new_hourly_rate": new_hourly_rate,
            "last_claim_time": new_last_claim_iso,
            "unclaimed": mined_amount,
            "upgrades": upgrades,
            "upgrades_count": total_upgrades_count,
            "server_time": now_iso,
            "referrer_id": referrer_id
        }

    try:
        transaction = db.transaction()
        result = run_upgrade_transaction(transaction, user_ref)
    except Exception as e:
        return {
            "success": False,
            "error": f"تعذر تنفيذ عملية الترقية: {str(e)}"
        }

    if result.get("success") and result.get("referrer_id"):
        try:
            ref_id = str(result["referrer_id"])
            db.collection("users").document(ref_id).collection("friends").document(
                user_id_str
            ).set(
                {
                    "upgrades_count": result["upgrades_count"],
                    "tg_id": user_id_str
                },
                merge=True
            )
        except Exception as e:
            print(
                f"⚠️ Warning updating friend upgrades_count for referrer: {e}"
            )

    return result

def buy_storage_db(user_id_str):
    db = get_db()
    user_ref = db.collection("users").document(user_id_str)
    game_settings = get_game_settings()

    storage_cfgs = (
        game_settings.get("storage_capacities")
        or DEFAULT_GAME_SETTINGS["storage_capacities"]
    )

    @firestore.transactional
    def run_storage_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)

        if not snapshot.exists:
            return {"success": False, "error": "المستخدم غير موجود"}

        user_data = snapshot.to_dict() or {}

        try:
            current_level = int(user_data.get("storage_level", 0))
        except (TypeError, ValueError):
            current_level = 0

        next_level = current_level + 1

        if next_level > 9 or str(next_level) not in storage_cfgs:
            return {
                "success": False,
                "error": "المخزن في أقصى مستوى بالفعل (MAX)"
            }

        next_cfg = storage_cfgs[str(next_level)]

        if isinstance(next_cfg, dict):
            cost_zn = float(next_cfg.get("cost_zn", next_cfg.get("cost", 0.0)))
            cost_usd = float(next_cfg.get("cost_usd", 0.0))
            new_capacity = float(next_cfg.get("capacity", 30.0))
        else:
            cost_zn = 0.0
            cost_usd = 0.0
            new_capacity = float(next_cfg)

        current_balance = round_zn(user_data.get("balance", 0.0))
        current_usd_balance = round_usd(user_data.get("usd_balance", 0.0))

        if current_balance + 1e-12 < cost_zn:
            return {
                "success": False,
                "error": f"رصيدك غير كافٍ! سعر ترقية المخزن {cost_zn:,.0f} ZN"
            }

        if cost_usd > 0 and current_usd_balance + 1e-12 < cost_usd:
            return {
                "success": False,
                "error": f"رصيد الدولار غير كافٍ! يتطلب ${cost_usd:.2f} USD"
            }

        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()

        old_max_cap = calculate_user_max_cap(user_data, game_settings)
        mined_amount = calculate_accrued_mined(
            user_data,
            now,
            old_max_cap
        )

        hourly_rate = float(user_data.get("hourly_rate", 0.05))
        extra_cap = float(user_data.get("extra_storage", 0.0))

        new_max_cap = round(new_capacity + extra_cap, 2)
        new_balance = round_zn(current_balance - cost_zn)
        new_usd_balance = round_usd(current_usd_balance - cost_usd)

        if hourly_rate > 0 and mined_amount > 0:
            equivalent_seconds = mined_amount / (hourly_rate / 3600.0)
            new_last_claim_iso = (
                now - timedelta(seconds=equivalent_seconds)
            ).isoformat()
        else:
            new_last_claim_iso = now_iso

        transaction.update(
            ref,
            {
                "balance": new_balance,
                "usd_balance": new_usd_balance,
                "storage_level": next_level,
                "max_cap": new_max_cap,
                "last_claim_time": new_last_claim_iso
            }
        )

        return {
            "success": True,
            "new_balance": new_balance,
            "new_usd_balance": new_usd_balance,
            "storage_level": next_level,
            "max_cap": new_max_cap,
            "last_claim_time": new_last_claim_iso,
            "unclaimed": mined_amount,
            "server_time": now_iso
        }

    try:
        transaction = db.transaction()
        return run_storage_transaction(transaction, user_ref)
    except Exception as e:
        return {
            "success": False,
            "error": f"تعذر إتمام ترقية المخزن: {str(e)}"
        }

def claim_daily_reward_db(user_id_str):
    db = get_db()
    user_ref = db.collection("users").document(user_id_str)
    game_settings = get_game_settings()
    parsed_rewards = parse_daily_rewards(
        game_settings.get("daily_rewards")
    )

    @firestore.transactional
    def run_daily_claim_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)

        if not snapshot.exists:
            return {"success": False, "error": "المستخدم غير موجود"}

        user_data = snapshot.to_dict() or {}
        now = datetime.now(timezone.utc)

        today_str = now.strftime("%Y-%m-%d")
        yesterday_str = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        last_daily_claim = user_data.get("last_daily_claim_date")

        if last_daily_claim == today_str:
            return {
                "success": False,
                "error": "لقد قمت باستلام المكافأة اليوم بالفعل"
            }

        try:
            raw_daily_day = int(
                user_data.get("daily_day")
                or user_data.get("daily_streak")
                or 1
            )
        except (TypeError, ValueError):
            raw_daily_day = 1

        if last_daily_claim == yesterday_str:
            effective_daily_day = min(raw_daily_day + 1, 30)
        else:
            effective_daily_day = 1

        reward_index = min(max(effective_daily_day - 1, 0), 29)
        reward_amount = float(parsed_rewards[reward_index])

        current_balance = round_zn(user_data.get("balance", 0.0))
        current_usd_balance = round_usd(user_data.get("usd_balance", 0.0))

        new_balance = round_zn(current_balance + reward_amount)
        new_ads_watched = int(user_data.get("ads_watched", 0)) + 1

        transaction.update(
            ref,
            {
                "balance": new_balance,
                "daily_day": effective_daily_day,
                "daily_streak": effective_daily_day,
                "last_daily_claim_date": today_str,
                "ads_watched": new_ads_watched
            }
        )

        return {
            "success": True,
            "new_balance": new_balance,
            "new_usd_balance": current_usd_balance,
            "daily_day": effective_daily_day,
            "last_daily_claim_date": today_str,
            "ads_watched": new_ads_watched,
            "server_time": now.isoformat()
        }

    try:
        transaction = db.transaction()
        return run_daily_claim_transaction(transaction, user_ref)
    except Exception as e:
        return {
            "success": False,
            "error": f"تعذر استلام المكافأة اليومية: {str(e)}"
        }

def claim_daily_boost_db(user_id_str):
    db = get_db()
    user_ref = db.collection("users").document(user_id_str)
    game_settings = get_game_settings()

    mining_cfg = game_settings.get(
        "mining_config",
        DEFAULT_GAME_SETTINGS["mining_config"]
    )

    daily_boost_reward = round(
        float(mining_cfg.get("daily_boost_reward", 0.15)),
        2
    )
    max_daily_boost_rate = round(
        float(mining_cfg.get("max_daily_boost_rate", 4.5)),
        2
    )
    boost_max_reward_coins = round(
        float(mining_cfg.get("boost_max_reward_coins", 35.0)),
        2
    )

    @firestore.transactional
    def run_boost_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)

        if not snapshot.exists:
            return {"success": False, "error": "المستخدم غير موجود"}

        user_data = snapshot.to_dict() or {}
        now = datetime.now(timezone.utc)

        today_str = now.strftime("%Y-%m-%d")
        now_iso = now.isoformat()

        if user_data.get("last_boost_date") == today_str:
            return {
                "success": False,
                "error": "لقد حصلت على تعزيز اليوم بالفعل"
            }

        daily_boost_rate = float(
            user_data.get("daily_boost_rate", 0.0) or 0.0
        )
        current_hourly_rate = float(
            user_data.get("hourly_rate", 0.05) or 0.05
        )
        current_balance = round_zn(user_data.get("balance", 0.0))
        current_usd_balance = round_usd(
            user_data.get("usd_balance", 0.0)
        )

        current_ads = int(user_data.get("ads_watched", 0) or 0)
        new_ads = current_ads + 1

        max_cap = calculate_user_max_cap(user_data, game_settings)
        mined_amount = calculate_accrued_mined(
            user_data,
            now,
            max_cap
        )

        remaining_boost = max(
            0.0,
            max_daily_boost_rate - daily_boost_rate
        )

        if remaining_boost > 0.00000001:
            applied_boost = min(
                daily_boost_reward,
                remaining_boost
            )
            applied_boost = round(applied_boost, 2)

            new_daily_boost_rate = round(
                min(
                    max_daily_boost_rate,
                    daily_boost_rate + applied_boost
                ),
                2
            )
            new_hourly_rate = round(
                current_hourly_rate + applied_boost,
                2
            )

            if new_hourly_rate > 0 and mined_amount > 0:
                equivalent_seconds = mined_amount / (
                    new_hourly_rate / 3600.0
                )
                new_last_claim_iso = (
                    now - timedelta(seconds=equivalent_seconds)
                ).isoformat()
            else:
                new_last_claim_iso = now_iso

            transaction.update(
                ref,
                {
                    "daily_boost_rate": new_daily_boost_rate,
                    "hourly_rate": new_hourly_rate,
                    "last_boost_date": today_str,
                    "ads_watched": new_ads,
                    "last_claim_time": new_last_claim_iso
                }
            )

            return {
                "success": True,
                "type": "speed",
                "boost_amount": applied_boost,
                "new_rate": new_hourly_rate,
                "daily_boost_rate": new_daily_boost_rate,
                "last_boost_date": today_str,
                "last_claim_time": new_last_claim_iso,
                "unclaimed": mined_amount,
                "new_balance": current_balance,
                "new_usd_balance": current_usd_balance,
                "server_time": now_iso
            }

        new_balance = round_zn(
            current_balance + boost_max_reward_coins
        )

        transaction.update(
            ref,
            {
                "balance": new_balance,
                "last_boost_date": today_str,
                "ads_watched": new_ads
            }
        )

        return {
            "success": True,
            "type": "balance",
            "reward_coins": boost_max_reward_coins,
            "new_balance": new_balance,
            "new_usd_balance": current_usd_balance,
            "last_boost_date": today_str,
            "server_time": now_iso
        }

    try:
        transaction = db.transaction()
        return run_boost_transaction(transaction, user_ref)
    except Exception as e:
        return {
            "success": False,
            "error": f"تعذر تفعيل التعزيز: {str(e)}"
        }

import os
import re
import time
import json
from datetime import datetime, timezone
from supabase import create_client, Client

# قراءة عنوان عقد العملة الذكي من متغيرات البيئة
ZNX_CONTRACT_ADDRESS = os.getenv("ZNX_CONTRACT_ADDRESS", "EQCp7mIbe-eR-j6b7opnHBtCbl74gnyYAP2XZlSpHkERkwdJ")

# إعدادات الاتصال بـ Supabase (يفضل استخدام SERVICE_ROLE_KEY في الباك إند لتخطي RLS بأمان)
SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_KEY = (
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_SECRET_KEY")
    or os.getenv("SUPABASE_KEY")
    or ""
).strip()

_SUPABASE_CLIENT: Client | None = None

# --- نظام Caching لتسريع الاستجابة وتخفيف الضغط على قاعدة البيانات ---
_TIER_CACHE = {
    "data": None,
    "timestamp": 0
}
CACHE_TTL_SECONDS = 5  # تحديث الكاش كل 5 ثوانٍ

TON_WALLET_REGEX = re.compile(r"^(EQ|UQ|0:)[a-zA-Z0-9_-]{46,66}$")


def safe_get_db() -> Client | None:
    """إنشاء وإرجاع اتصال آمن ومستقر مع Supabase"""
    global _SUPABASE_CLIENT
    if _SUPABASE_CLIENT is not None:
        return _SUPABASE_CLIENT

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("⚠️ تحذير: متغيرات SUPABASE_URL أو SUPABASE_KEY غير موجودة في البيئة!")
        return None

    try:
        _SUPABASE_CLIENT = create_client(SUPABASE_URL, SUPABASE_KEY)
        return _SUPABASE_CLIENT
    except Exception as e:
        print(f"⚠️ خطأ الاتصال بـ Supabase في withdraw_db: {e}")
        return None


get_db = safe_get_db


class SupabaseUserRef:
    """
    كلاس توافقي يحاكي DocumentReference لتجنب كسر أي كود قديم
    يستدعي user_ref.update() أو user_ref.set() في باقي ملفات المشروع.
    """
    def __init__(self, db: Client, pk_col: str, pk_val, data: dict):
        self.db = db
        self.pk_col = pk_col
        self.pk_val = pk_val
        self.id = str(data.get("user_id") or data.get("tg_id") or data.get("id") or pk_val)
        self._data = data

    def update(self, payload: dict):
        clean_payload = dict(payload)
        return (
            self.db.table("users")
            .update(clean_payload)
            .eq(self.pk_col, self.pk_val)
            .execute()
        )

    def set(self, payload: dict, merge: bool = True):
        return self.update(payload)


def is_valid_ton_address(address: str) -> bool:
    if not address or not isinstance(address, str):
        return False
    return bool(TON_WALLET_REGEX.match(address.strip()))


def format_crypto_display(amount):
    if amount is None:
        return "0.0000"
    try:
        val = float(amount)
        if val <= 0:
            return "0.0000"
        return f"{val:,.4f}"
    except Exception:
        return str(amount)


def extract_user_balance(data):
    """جلب رصيد ZNX للمستخدم بشكل دقيق واعتماد حقل znx_balance فقط لمنع تضارب الأرصدة"""
    if not isinstance(data, dict):
        return 0.0

    if "znx_balance" in data and data["znx_balance"] is not None:
        try:
            val = float(data["znx_balance"])
            if val >= 0:
                return val
        except (ValueError, TypeError):
            pass

    return 0.0


def extract_usd_balance(data):
    """جلب رصيد الدولار للمستخدم بأمان"""
    if not isinstance(data, dict):
        return 0.0
    try:
        val = float(data.get("usd_balance", 0.0) or 0.0)
        return val if val >= 0 else 0.0
    except (ValueError, TypeError):
        return 0.0


def _parse_json_field(raw_val, default_val):
    if raw_val is None:
        return default_val
    if isinstance(raw_val, type(default_val)):
        return raw_val
    if isinstance(raw_val, str):
        try:
            parsed = json.loads(raw_val)
            if isinstance(parsed, type(default_val)):
                return parsed
        except Exception:
            pass
    return default_val


def get_current_withdraw_tier():
    """جلب بيانات الشريحة الحالية لسحب العملات من Supabase مع Caching فائق السرعة"""
    now = time.time()
    if _TIER_CACHE["data"] and (now - _TIER_CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _TIER_CACHE["data"]

    default_tier = {
        "tier": 1,
        "name": "الشريحة الأولى",
        "min_withdraw_znx": 1000.0,
        "fixed_fee_usd": 0.02
    }

    db = safe_get_db()
    if not db:
        return default_tier

    try:
        res = db.table("znx_global_stats").select("*").eq("id", "summary").limit(1).execute()
        rows = res.data if res and hasattr(res, "data") else []

        if not rows:
            res_any = db.table("znx_global_stats").select("*").limit(1).execute()
            rows = res_any.data if res_any and hasattr(res_any, "data") else []

        if not rows:
            _TIER_CACHE["data"] = default_tier
            _TIER_CACHE["timestamp"] = now
            return default_tier

        stats = rows[0] or {}
        total_global_znx = float(stats.get("total_converted_znx", 0.0) or 0.0)
        tiers = _parse_json_field(stats.get("tiers_config"), [])

        res_tier = default_tier
        for item in tiers:
            if not isinstance(item, dict):
                continue
            min_v = float(item.get("min_pts", 0.0) or 0.0)
            raw_max = item.get("max_pts")
            max_v = float("inf") if str(raw_max).lower() in ("inf", "infinity", "none", "null") else float(raw_max)
            if min_v <= total_global_znx < max_v:
                res_tier = {
                    "tier": int(item.get("tier", 1)),
                    "name": str(item.get("name", "الشريحة الحالية")),
                    "min_withdraw_znx": float(item.get("min_withdraw_znx", 1000.0)),
                    "fixed_fee_usd": float(item.get("fixed_fee_usd", 0.02))
                }
                break
        else:
            if tiers and isinstance(tiers[-1], dict):
                last = tiers[-1]
                res_tier = {
                    "tier": int(last.get("tier", 7)),
                    "name": str(last.get("name", "الشريحة السابعة")),
                    "min_withdraw_znx": float(last.get("min_withdraw_znx", 2.5)),
                    "fixed_fee_usd": float(last.get("fixed_fee_usd", 0.02))
                }

        _TIER_CACHE["data"] = res_tier
        _TIER_CACHE["timestamp"] = now
        return res_tier
    except Exception as e:
        print(f"⚠️ خطأ جلب شريحة السحب من Supabase: {e}")

    return default_tier


def get_user_doc(user_id):
    """البحث عن سجل المستخدم في Supabase بسرعة عالية مع دعم كافة أسماء حقول المعرف"""
    db = safe_get_db()
    if not db or user_id is None:
        return None, None

    str_user_id = str(user_id).strip()
    if not str_user_id:
        return None, None

    # البحث المتدرج حسب الأعمدة المحتملة في جدول users
    search_columns = ["user_id", "tg_id", "id", "telegram_id"]

    for col in search_columns:
        try:
            res = db.table("users").select("*").eq(col, str_user_id).limit(1).execute()
            if res and res.data:
                row = res.data[0]
                pk_col = "id" if "id" in row and row["id"] is not None else col
                pk_val = row.get(pk_col, str_user_id)
                return SupabaseUserRef(db, pk_col, pk_val, row), row
        except Exception:
            pass

        if str_user_id.isdigit():
            try:
                int_val = int(str_user_id)
                res_int = db.table("users").select("*").eq(col, int_val).limit(1).execute()
                if res_int and res_int.data:
                    row = res_int.data[0]
                    pk_col = "id" if "id" in row and row["id"] is not None else col
                    pk_val = row.get(pk_col, int_val)
                    return SupabaseUserRef(db, pk_col, pk_val, row), row
            except Exception:
                pass

    return None, None


def get_user_full_details(user_id):
    """جلب كامل التفاصيل المطلوبة لإشعار السحب اليدوي للأدمن من Supabase"""
    try:
        db = safe_get_db()
        user_ref, data = get_user_doc(user_id)
        if not data:
            return None

        real_znx_balance = extract_user_balance(data)
        usd_balance = extract_usd_balance(data)
        zn_balance = float(data.get("balance", 0.0) or 0.0)

        wallets = _parse_json_field(data.get("wallets"), {})
        wallet_addr = data.get("wallet_address") or wallets.get("ZNX", "") or ""

        # 1. استخراج تاريخ التسجيل بوضوح
        joined_str = "غير محدد"
        joined_raw = data.get("created_at") or data.get("joined_at") or data.get("registration_date")
        if joined_raw:
            try:
                if hasattr(joined_raw, "strftime"):
                    joined_str = joined_raw.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(joined_raw, (int, float)):
                    joined_str = datetime.fromtimestamp(joined_raw, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(joined_raw, str):
                    clean_iso = joined_raw.replace("T", " ").split(".")[0].replace("Z", "")
                    joined_str = clean_iso[:19]
            except Exception:
                pass

        # 2. سرعة التعدين والترقيات والمخازن
        hourly_rate = float(data.get("hourly_rate", 0.0) or 0.0)
        upgrades_count = int(data.get("upgrades_count", 0) or 0)
        storage_level = int(data.get("storage_level", 1) or 1)
        max_cap = float(data.get("max_cap", 0.0) or 0.0)

        # 3. حساب عدد الإحالات (الأصدقاء)
        ref_count = int(data.get("referral_count", 0) or data.get("ref_count", 0) or 0)
        if ref_count == 0 and db:
            str_uid = str(user_id).strip()
            try:
                ref_res = (
                    db.table("users")
                    .select("user_id", count="exact")
                    .eq("referred_by", str_uid)
                    .execute()
                )
                if ref_res and ref_res.count is not None:
                    ref_count = int(ref_res.count)
            except Exception:
                pass

        return {
            "user_id": str(user_id),
            "first_name": data.get("first_name") or "غير محدد",
            "username": data.get("username") or "لا يوجد",
            "znx_balance": real_znx_balance,
            "zn_balance": zn_balance,
            "usd_balance": usd_balance,
            "joined_at": joined_str,
            "hourly_rate": hourly_rate,
            "upgrades_count": upgrades_count,
            "storage_level": storage_level,
            "max_cap": max_cap,
            "ref_count": ref_count,
            "is_banned": bool(data.get("is_banned", False)),
            "wallets": wallets,
            "wallet_address": wallet_addr
        }
    except Exception as e:
        print(f"⚠️ خطأ جلب تفاصيل المستخدم كاملة من Supabase: {e}")
        return None


def save_user_wallet(user_id, currency, wallet_address):
    """حفظ عنوان المحفظة للمستخدم في Supabase بعد التحقق من صحته"""
    db = safe_get_db()
    if not db:
        return False, "تعذر الاتصال بقاعدة البيانات."

    clean_wallet = str(wallet_address or "").strip()
    if not is_valid_ton_address(clean_wallet):
        return False, "عنوان محفظة TON غير صالح."

    try:
        user_ref, user_data = get_user_doc(user_id)
        if not user_ref or not user_data:
            return False, "المستخدم غير موجود في قاعدة البيانات."

        existing_wallets = _parse_json_field(user_data.get("wallets"), {})
        existing_wallets[str(currency or "ZNX").upper()] = clean_wallet

        user_ref.update({
            "wallets": existing_wallets,
            "wallet_address": clean_wallet,
            "updated_at": datetime.now(timezone.utc).isoformat()
        })
        return True, "تم حفظ المحفظة بنجاح."
    except Exception as e:
        print(f"⚠️ خطأ حفظ المحفظة في Supabase: {e}")
        return False, f"خطأ أثناء الحفظ: {str(e)}"

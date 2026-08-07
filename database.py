import os
import json
import time
from datetime import datetime, timezone
import firebase_admin
from firebase_admin import credentials, firestore

db = None

# ==================== Dynamic In-Memory Cache System ====================
_SETTINGS_CACHE = None
_SETTINGS_CACHE_TIME = 0
SETTINGS_CACHE_TTL = 300  # 5 دقائق للكاش مع تفريغ فوري عند التحديث من الأدمن

_BAN_CACHE = {}           
BAN_CACHE_TTL = 120       

_LEADERBOARD_CACHE = None
_LEADERBOARD_CACHE_TIME = 0
LEADERBOARD_CACHE_TTL = 180  
# ========================================================================

def initialize_firebase():
    """تهيئة الاتصال بقاعدة بيانات Firebase Firestore مع حماية المفاتيح"""
    global db
    if not firebase_admin._apps:
        firebase_creds_json = os.environ.get('FIREBASE_CREDENTIALS')
        try:
            if firebase_creds_json:
                try:
                    creds_dict = json.loads(firebase_creds_json)
                except Exception:
                    creds_dict = json.loads(firebase_creds_json.replace('\\n', '\n'))
                
                if isinstance(creds_dict, dict) and "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace('\\n', '\n')

                cred = credentials.Certificate(creds_dict)
            else:
                if os.path.exists("firebase-adminsdk.json"):
                    cred = credentials.Certificate("firebase-adminsdk.json")
                else:
                    raise FileNotFoundError("لم يتم العثور على بيانات اعتماد Firebase!")
            
            firebase_admin.initialize_app(cred)
            print("✅ Firebase Initialized Successfully!")
        except Exception as e:
            print(f"❌ Critical Firebase Initialization Error: {e}")
            raise e
            
    if db is None:
        db = firestore.client()
    return db


def clear_settings_cache():
    """تفريغ وتصفير ذاكرة التخزين المؤقت للإعدادات فور تعديل النسب من الأدمن"""
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    _SETTINGS_CACHE = None
    _SETTINGS_CACHE_TIME = 0


def ensure_game_settings_exist():
    """ضمان وجود مستند الإعدادات الأساسية والإحصائيات التجميعية في Firestore"""
    global db, _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    if not db:
        try:
            db = initialize_firebase()
        except Exception as e:
            print(f"❌ Error initializing firebase: {e}")
            return None

    try:
        config_ref = db.collection('app_config').document('game_settings')
        doc_snap = config_ref.get()
        
        if doc_snap.exists:
            existing_data = doc_snap.to_dict() or {}
            needs_update = False
            updates = {}
            
            # 1. إعدادات لعبة الشبكة ونسبة ربح البوت المستهدفة (0.70 = 70%)
            if "grid_game_config" not in existing_data:
                grid_cfg = {
                    "min_bet": 250.0,
                    "target_margin": 0.70,
                    "default_broken_coins": 3
                }
                existing_data["grid_game_config"] = grid_cfg
                updates["grid_game_config"] = grid_cfg
                needs_update = True
            else:
                grid_cfg = existing_data["grid_game_config"]
                if "target_margin" not in grid_cfg or grid_cfg["target_margin"] == 0:
                    grid_cfg["target_margin"] = 0.70
                    updates["grid_game_config.target_margin"] = 0.70
                    existing_data["grid_game_config"]["target_margin"] = 0.70
                    needs_update = True

            # 2. حقول الإحصائيات الموحدة التجميعية
            if "global_total_bets" not in existing_data:
                updates["global_total_bets"] = 0.0
                existing_data["global_total_bets"] = 0.0
                needs_update = True
            if "global_total_wins" not in existing_data:
                updates["global_total_wins"] = 0.0
                existing_data["global_total_wins"] = 0.0
                needs_update = True

            if needs_update:
                config_ref.update(updates)

            _SETTINGS_CACHE = existing_data
            _SETTINGS_CACHE_TIME = time.time()
            return existing_data

        # إنشاء مستند الإعدادات الافتراضي في حال عدم وجوده
        daily_rewards_30_days = {
            f"day_{i}": val for i, val in enumerate([
                100, 150, 200, 250, 300, 350, 400, 450, 500, 550,
                600, 600, 650, 650, 700, 700, 750, 750, 800, 800,
                850, 850, 900, 900, 950, 950, 1000, 1000, 1100, 1250
            ], start=1)
        }

        mining_cfg = {
            "1": {"price": 3500.0, "rate": 5.0, "rate_bonus": 5.0, "base_cost": 3500.0, "max": 10},
            "2": {"price": 11500.0, "rate": 15.0, "rate_bonus": 15.0, "base_cost": 11500.0, "max": 10},
            "3": {"price": 28000.0, "rate": 35.0, "rate_bonus": 35.0, "base_cost": 28000.0, "max": 10},
            "4": {"price": 68000.0, "rate": 80.0, "rate_bonus": 80.0, "base_cost": 68000.0, "max": 10},
            "5": {"price": 165000.0, "rate": 180.0, "rate_bonus": 180.0, "base_cost": 165000.0, "max": 10},
            "6": {"price": 390000.0, "rate": 400.0, "rate_bonus": 400.0, "base_cost": 390000.0, "max": 10},
            "7": {"price": 950000.0, "rate": 900.0, "rate_bonus": 900.0, "base_cost": 950000.0, "max": 10},
            "8": {"price": 2300000.0, "rate": 2000.0, "rate_bonus": 2000.0, "base_cost": 2300000.0, "max": 10},
            "9": {"price": 5500000.0, "rate": 4500.0, "rate_bonus": 4500.0, "base_cost": 5500000.0, "max": 10}
        }

        storage_cfg = {
            "0": {"capacity": 100.0, "price": 0},
            "1": {"capacity": 300.0, "price": 3000},
            "2": {"capacity": 800.0, "price": 8500},
            "3": {"capacity": 2000.0, "price": 25000},
            "4": {"capacity": 5000.0, "price": 70000},
            "5": {"capacity": 12000.0, "price": 180000},
            "6": {"capacity": 28000.0, "price": 450000},
            "7": {"capacity": 65000.0, "price": 1100000},
            "8": {"capacity": 150000.0, "price": 2800000},
            "9": {"capacity": 350000.0, "price": 7000000},
            "10": {"capacity": 800000.0, "price": 18000000}
        }

        initial_settings = {
            "usd_to_zn_rate": 1000000,
            "ad_reward_boost": 0.5,
            "daily_rewards": daily_rewards_30_days,
            "mining_config": mining_cfg,
            "storage_config": storage_cfg,
            "global_total_bets": 0.0,
            "global_total_wins": 0.0,
            "grid_game_config": {
                "min_bet": 250.0,
                "target_margin": 0.70,
                "default_broken_coins": 3
            }
        }

        config_ref.set(initial_settings)
        _SETTINGS_CACHE = initial_settings
        _SETTINGS_CACHE_TIME = time.time()
        print("✅ تم إنشاء app_config/game_settings بنجاح!")
        return initial_settings
    except Exception as e:
        print(f"❌ خطأ أثناء تهيئة الإعدادات: {e}")
        return None


def get_game_settings():
    """جلب إعدادات اللعبة من الكاش المؤقت لتوفير قراءات Firestore"""
    global _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    now = time.time()
    if _SETTINGS_CACHE is not None and (now - _SETTINGS_CACHE_TIME) < SETTINGS_CACHE_TTL:
        return _SETTINGS_CACHE

    try:
        if not db: initialize_firebase()
        doc = db.collection('app_config').document('game_settings').get()
        if doc.exists:
            data = doc.to_dict() or {}
            _SETTINGS_CACHE = data
            _SETTINGS_CACHE_TIME = now
            return _SETTINGS_CACHE
        else:
            return ensure_game_settings_exist() or {}
    except Exception as e:
        print(f"❌ Error getting game settings: {e}")
        return _SETTINGS_CACHE or {}


def update_game_settings(new_settings_dict):
    """تحديث الإعدادات وتفريغ الكاش فوراً"""
    global db, _SETTINGS_CACHE, _SETTINGS_CACHE_TIME
    try:
        if not db: initialize_firebase()
        config_ref = db.collection('app_config').document('game_settings')
        config_ref.set(new_settings_dict, merge=True)
        
        clear_settings_cache()
        doc_snap = config_ref.get()
        if doc_snap.exists:
            _SETTINGS_CACHE = doc_snap.to_dict() or {}
            _SETTINGS_CACHE_TIME = time.time()
        return True, "تم حفظ الإعدادات وتحديث السيرفر بنجاح!"
    except Exception as e:
        print(f"❌ Error updating game settings: {e}")
        return False, f"حدث خطأ أثناء الحفظ: {e}"


def update_grid_game_config(min_bet=None, target_margin=None, default_broken_coins=None):
    """تحديث إعدادات ألعاب الشبكة ونسب الأرباح من لوحة التحكم"""
    try:
        if not db: initialize_firebase()
        config_ref = db.collection('app_config').document('game_settings')
        doc = config_ref.get()
        current_data = doc.to_dict() or {} if doc.exists else {}
        grid_cfg = current_data.get("grid_game_config", {})

        if min_bet is not None:
            grid_cfg["min_bet"] = float(min_bet)
        if target_margin is not None:
            val = float(target_margin)
            grid_cfg["target_margin"] = val / 100.0 if val > 1.0 else val
        if default_broken_coins is not None:
            grid_cfg["default_broken_coins"] = int(default_broken_coins)

        config_ref.set({"grid_game_config": grid_cfg}, merge=True)
        clear_settings_cache()
        return True
    except Exception as e:
        print(f"❌ Error in update_grid_game_config: {e}")
        return False


def save_admin_settings(settings_dict):
    """حفظ الإعدادات المرسلة من لوحة تحكم الأدمن وتحديث النسب"""
    try:
        if not isinstance(settings_dict, dict):
            return False, "بيانات الإعدادات غير صالحة"

        current_settings = get_game_settings() or {}
        grid_cfg = current_settings.get("grid_game_config", {})

        if "target_margin" in settings_dict:
            val = float(settings_dict["target_margin"])
            grid_cfg["target_margin"] = val / 100.0 if val > 1.0 else val

        if "bot_margin" in settings_dict:
            val = float(settings_dict["bot_margin"])
            grid_cfg["target_margin"] = val / 100.0 if val > 1.0 else val

        if "min_bet" in settings_dict:
            grid_cfg["min_bet"] = float(settings_dict["min_bet"])

        if "default_broken_coins" in settings_dict:
            grid_cfg["default_broken_coins"] = int(settings_dict["default_broken_coins"])

        payload = {"grid_game_config": grid_cfg}

        if "usd_to_zn_rate" in settings_dict:
            payload["usd_to_zn_rate"] = float(settings_dict["usd_to_zn_rate"])

        return update_game_settings(payload)
    except Exception as e:
        print(f"❌ Error in save_admin_settings: {e}")
        return False, f"خطأ أثناء حفظ الإعدادات: {e}"


# ==================== Core Bet, Win & Loss System ====================

def record_bet_placed(tg_id, bet_amount):
    """1. دالة تسجيل الرهان الأساسي وخصمه من رصيد المستخدم"""
    try:
        if not db: initialize_firebase()
        bet = float(bet_amount)
        if bet <= 0: return False, "مبلغ الرهان غير صالح"

        tg_id_str = str(tg_id)
        user_ref = db.collection('users').document(tg_id_str)
        
        # خصم الرهان وتحديث إجمالي مبالغ الرهان الخاصة بالمستخدم
        user_ref.update({
            "balance": firestore.Increment(-bet),
            "total_bets": firestore.Increment(bet)
        })

        # تحديث إجمالي الرهانات بالنظام العام ذرياً
        config_ref = db.collection('app_config').document('game_settings')
        config_ref.update({"global_total_bets": firestore.Increment(bet)})

        arena_ref = db.collection('arena').document('current')
        arena_ref.set({
            "total_bets": firestore.Increment(bet),
            "last_updated": firestore.SERVER_TIMESTAMP
        }, merge=True)

        clear_settings_cache()
        return True, "تم تسجيل الرهان بنجاح"
    except Exception as e:
        print(f"❌ Error recording bet placed: {e}")
        return False, str(e)


def record_game_loss(tg_id, bet_amount):
    """2. دالة تسجيل الخسارة (عند خسارة المراهنة بالكامل للبوت)"""
    try:
        if not db: initialize_firebase()
        bet = float(bet_amount)
        tg_id_str = str(tg_id)

        # تسجيل الخسارة في بيانات المستخدم (الرهان تم خصمه سابقاً في record_bet_placed)
        user_ref = db.collection('users').document(tg_id_str)
        user_ref.update({
            "total_losses": firestore.Increment(bet)
        })

        # لا تتغير أرباح اللاعبين في arena لأن المبلغ بالكامل أصبح أرباحاً للبوت
        arena_ref = db.collection('arena').document('current')
        arena_ref.set({
            "last_updated": firestore.SERVER_TIMESTAMP
        }, merge=True)

        clear_settings_cache()
        return True
    except Exception as e:
        print(f"❌ Error recording game loss: {e}")
        return False


def record_game_win(tg_id, bet_amount, total_cashout_amount):
    """3. دالة تسجيل الربح والسحب (إعادة مبلغ الرهان + إضافة الصافي لدالة الربح)"""
    try:
        if not db: initialize_firebase()
        bet = float(bet_amount)
        cashout = float(total_cashout_amount)
        
        # الربح الصافي = إجمالي السحب - المبلغ المراهن به (مثال: 110 - 100 = 10)
        net_profit = max(0.0, cashout - bet)

        tg_id_str = str(tg_id)
        user_ref = db.collection('users').document(tg_id_str)

        # 1. إرجاع المبلغ الإجمالي (الرهان الأصلي + الربح الصافي) لرصيد المستخدم
        user_ref.update({
            "balance": firestore.Increment(cashout),
            "total_wins": firestore.Increment(net_profit)
        })

        # 2. إضافة الربح الصافي فقط لمستند الأرباح الإجمالية (payouts) للبوت واللعبة
        config_ref = db.collection('app_config').document('game_settings')
        config_ref.update({
            "global_total_wins": firestore.Increment(net_profit)
        })

        arena_ref = db.collection('arena').document('current')
        arena_ref.set({
            "total_payouts": firestore.Increment(net_profit),
            "last_updated": firestore.SERVER_TIMESTAMP
        }, merge=True)

        clear_settings_cache()
        return True
    except Exception as e:
        print(f"❌ Error recording game win: {e}")
        return False


def get_game_profit_stats():
    """حساب أرباح ونسب البوت واللاعبين بدقة عالية وقراءة سريعة"""
    try:
        settings = get_game_settings() or {}
        grid_cfg = settings.get("grid_game_config", {})

        arena_bets = 0.0
        arena_wins = 0.0
        try:
            if db:
                arena_doc = db.collection('arena').document('current').get()
                if arena_doc.exists:
                    a_data = arena_doc.to_dict() or {}
                    arena_bets = float(a_data.get('total_bets', 0.0))
                    arena_wins = float(a_data.get('total_payouts', 0.0))
        except Exception as e:
            print(f"⚠️ Error reading arena/current: {e}")

        total_bets = arena_bets if arena_bets > 0 else float(settings.get("global_total_bets", 0.0))
        total_wins = arena_wins if arena_wins > 0 else float(settings.get("global_total_wins", 0.0))

        # صافي ربح البوت = إجمالي الرهانات - أرباح المستخدمين الصافية المدفوعة
        bot_net_profit = max(0.0, total_bets - total_wins)
        target_margin = float(grid_cfg.get("target_margin", 0.70))
        target_margin_pct = target_margin * 100.0 if target_margin <= 1.0 else target_margin

        # حساب نسبة ربح البوت الحالية
        actual_bot_pct = round(((total_bets - total_wins) / total_bets * 100.0), 2) if total_bets > 0 else 100.0
        actual_bot_pct = max(0.0, actual_bot_pct)
        actual_user_pct = round(100.0 - actual_bot_pct, 2)

        return {
            "total_bets": total_bets,
            "total_wins": total_wins,
            "total_bot_profit": round(bot_net_profit, 2),
            "total_user_profit": round(total_wins, 2),
            "target_margin": target_margin,
            "target_margin_percent": target_margin_pct,
            "actual_bot_percent": actual_bot_pct,
            "actual_user_percent": actual_user_pct,
            "global_total_bets": total_bets,
            "global_total_wins": total_wins
        }
    except Exception as e:
        print(f"❌ Error fetching game profit stats: {e}")
        return {
            "total_bets": 0.0,
            "total_wins": 0.0,
            "total_bot_profit": 0.0,
            "total_user_profit": 0.0,
            "target_margin": 0.70,
            "target_margin_percent": 70.0,
            "actual_bot_percent": 100.0,
            "actual_user_percent": 0.0,
            "global_total_bets": 0.0,
            "global_total_wins": 0.0
        }


def should_user_win_next_step():
    """دالة ذكية توضع داخل محرك اللعبة للتحكم بنسبة 70% للبوت و30% للمستخدم"""
    try:
        stats = get_game_profit_stats()
        actual_bot_pct = stats.get("actual_bot_percent", 100.0)
        target_bot_pct = stats.get("target_margin_percent", 70.0)

        # إذا كانت نسبة ربح البوت الحالية أقل من النسبة المستهدفة (مثلاً 70%)
        # يتم توجيه اللعبة لإظهار القنبلة وخسارة المستخدم
        if actual_bot_pct < target_bot_pct:
            return False  # اجعل الخطوة خاسرة
        return True       # اجعل الخطوة مسموحة للربح
    except Exception:
        return True


def get_admin_dashboard_stats():
    """جلب إحصائيات الشاشة الرئيسية للأدمن بسرعة دون إرهاق السيرفر"""
    try:
        profit_stats = get_game_profit_stats()
        total_users_count = 0
        
        if db:
            try:
                users_col = db.collection('users')
                count_query = users_col.count()
                total_users_count = count_query.get()[0][0].value
            except Exception:
                total_users_count = 0

        return {
            "status": "success",
            "stats": {
                "total_users": total_users_count,
                "total_bets": profit_stats.get("total_bets", 0.0),
                "total_wins": profit_stats.get("total_wins", 0.0),
                "total_bot_profit": profit_stats.get("total_bot_profit", 0.0),
                "target_margin": profit_stats.get("target_margin", 0.70),
                "target_margin_percent": profit_stats.get("target_margin_percent", 70.0),
                "actual_bot_percent": profit_stats.get("actual_bot_percent", 0.0),
                "actual_user_percent": profit_stats.get("actual_user_percent", 0.0)
            }
        }
    except Exception as e:
        print(f"❌ Error getting admin dashboard stats: {e}")
        return {"status": "error", "message": str(e), "stats": {}}


# ==================== User & Account Functions ====================

def is_user_banned(tg_id):
    """التحقق السريع من حالة حظر المستخدم باستخدام الكاش"""
    if not tg_id: return False
    tg_id_str = str(tg_id)
    now = time.time()

    if tg_id_str in _BAN_CACHE:
        is_banned, expire_time = _BAN_CACHE[tg_id_str]
        if now < expire_time: return is_banned

    try:
        doc = db.collection('users').document(tg_id_str).get()
        is_banned = bool((doc.to_dict() or {}).get('banned', False)) if doc.exists else False
        _BAN_CACHE[tg_id_str] = (is_banned, now + BAN_CACHE_TTL)
        return is_banned
    except Exception as e:
        print(f"❌ Error checking ban status: {e}")
        return False


def ban_user(tg_id, ban_status=True):
    """حظر أو إلغاء حظر مستخدم وتحديث الكاش فوراً"""
    try:
        if not tg_id: return False, "معرف مستخدم غير صالح"
        tg_id_str = str(tg_id)
        
        db.collection('users').document(tg_id_str).update({"banned": bool(ban_status)})
        _BAN_CACHE[tg_id_str] = (bool(ban_status), time.time() + BAN_CACHE_TTL)
        log_admin_action("المدير العام", f"{'حظر' if ban_status else 'إلغاء حظر'} المستخدم {tg_id_str}")
        return True, "تم حظر المستخدم بنجاح" if ban_status else "تم إلغاء الحظر بنجاح"
    except Exception as e:
        print(f"❌ Error banning user {tg_id}: {e}")
        return False, f"حدث خطأ: {e}"


def init_user(tg_id, ref_id=None, first_name="صديقي"):
    """إنشاء أو تحديث حساب مستخدم جديد بالتكامل مع نظام الإحالات"""
    try:
        if not tg_id: return False
            
        tg_id_str = str(tg_id)
        user_ref = db.collection('users').document(tg_id_str)
        user_doc = user_ref.get()
        
        is_new_referral = False
        valid_ref_id = str(ref_id) if ref_id and str(ref_id) != tg_id_str else None
        now_iso = datetime.now(timezone.utc).isoformat()

        if not user_doc.exists:
            new_user_data = {
                "tg_id": tg_id_str,
                "first_name": first_name,
                "balance": 0.0,
                "ad_balance": 0.0,
                "usd_balance": 0.0,
                "hourly_rate": 0.0,
                "daily_boost_rate": 0.0,
                "ads_watched": 0,
                "energy": 100.0,
                "storage_level": 0,
                "extra_storage": 0.0,
                "max_cap": 100.0,
                "last_claim_time": now_iso,
                "daily_streak": 0,
                "daily_day": 1,
                "last_daily_claim_date": None,
                "upgrades": {},
                "completed_tasks": [],
                "banned": False,
                "wallet_address": None,
                "referred_by": valid_ref_id,
                "pending_ref_earnings": 0.0,
                "total_ref_earnings": 0.0,
                "invited_friends_count": 0,
                "total_bets": 0.0,
                "total_wins": 0.0,
                "total_losses": 0.0,
                "last_active": firestore.SERVER_TIMESTAMP,
                "joined_at": firestore.SERVER_TIMESTAMP
            }
            user_ref.set(new_user_data)
            
            if valid_ref_id:
                referrer_ref = db.collection('users').document(valid_ref_id)
                if referrer_ref.get().exists:
                    is_new_referral = True
                    referrer_ref.update({"invited_friends_count": firestore.Increment(1)})
                    referrer_ref.collection('friends').document(tg_id_str).set({
                        "tg_id": tg_id_str,
                        "first_name": first_name,
                        "earned_from_him": 0.0,
                        "joined_at": firestore.SERVER_TIMESTAMP
                    }, merge=True)
        else:
            user_ref.update({
                "first_name": first_name,
                "last_active": firestore.SERVER_TIMESTAMP
            })
        
        return is_new_referral
    except Exception as e:
        print(f"❌ Error initializing user {tg_id}: {e}")
        return False


def get_user(tg_id):
    """جلب بيانات مستخدم محدد"""
    try:
        if not tg_id: return None
        user_ref = db.collection('users').document(str(tg_id))
        doc = user_ref.get()
        if doc.exists:
            data = doc.to_dict() or {}
            data['id'] = doc.id
            
            data["balance"] = float(data.get("balance", 0.0) or 0.0)
            data["usd_balance"] = float(data.get("usd_balance", 0.0) or 0.0)
            data["ad_balance"] = float(data.get("ad_balance", 0.0) or 0.0)
            data["total_bets"] = float(data.get("total_bets", 0.0) or 0.0)
            data["total_wins"] = float(data.get("total_wins", 0.0) or 0.0)
            data["total_losses"] = float(data.get("total_losses", 0.0) or 0.0)
            return data
        return None
    except Exception as e:
        print(f"❌ Error getting user {tg_id}: {e}")
        return None


def get_all_users_admin(limit=100):
    """جلب قائمة للمستخدمين للوحة الأدمن"""
    try:
        if not db: initialize_firebase()
        users_ref = db.collection('users').limit(limit)
        docs = users_ref.stream()

        users_list = []
        for doc in docs:
            d = doc.to_dict() or {}
            users_list.append({
                "tg_id": str(d.get("tg_id", doc.id)),
                "first_name": d.get("first_name", "مستخدم"),
                "balance": float(d.get("balance", 0.0)),
                "banned": bool(d.get("banned", False))
            })
        return users_list
    except Exception as e:
        print(f"❌ Error fetching all users for admin: {e}")
        return []


def update_user(tg_id, update_data):
    """تحديث حقول حساب المستخدم"""
    try:
        if not tg_id or not isinstance(update_data, dict): return False
        db.collection('users').document(str(tg_id)).update(update_data)
        return True
    except Exception as e:
        print(f"❌ Error updating user {tg_id}: {e}")
        return False


# ==================== Moderators & Admin Logs ====================

def get_moderators():
    """جلب قائمة المشرفين للوحة التحكم"""
    try:
        if not db: initialize_firebase()
        docs = db.collection('moderators').stream()
        mods = []
        for d in docs:
            data = d.to_dict() or {}
            data['id'] = str(d.id)
            mods.append(data)
        return mods
    except Exception as e:
        print(f"❌ Error getting moderators: {e}")
        return []


def add_moderator(mod_id, name, permissions=None, added_by="المدير العام"):
    """إضافة مشرف جديد مع تسجيل العملية"""
    try:
        if not db: initialize_firebase()
        mod_ref = db.collection('moderators').document(str(mod_id))
        mod_data = {
            "id": str(mod_id),
            "name": name,
            "permissions": permissions or {},
            "addedBy": added_by,
            "addedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        }
        mod_ref.set(mod_data, merge=True)
        log_admin_action(added_by, f"إضافة المشرف: {name} ({mod_id})")
        return True
    except Exception as e:
        print(f"❌ Error adding moderator: {e}")
        return False


def delete_moderator(mod_id, deleted_by="المدير العام"):
    """حذف مشرف وتجريده من الصلاحيات"""
    try:
        if not db: initialize_firebase()
        db.collection('moderators').document(str(mod_id)).delete()
        log_admin_action(deleted_by, f"حذف المشرف ID: {mod_id}")
        return True
    except Exception as e:
        print(f"❌ Error deleting moderator: {e}")
        return False


def get_admin_logs(limit=50):
    """جلب سجل الأنشطة والتحركات الإدارية"""
    try:
        if not db: initialize_firebase()
        logs_ref = db.collection('admin_logs').order_by('timestamp', direction=firestore.Query.DESCENDING).limit(limit)
        docs = logs_ref.stream()
        logs = []
        for d in docs:
            data = d.to_dict() or {}
            logs.append(data)
        return logs
    except Exception as e:
        print(f"❌ Error getting admin logs: {e}")
        return []


def log_admin_action(admin_name, action):
    """تسجيل حركة جديدة داخل سجل الإدارة المركزية"""
    try:
        if not db: initialize_firebase()
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        db.collection('admin_logs').add({
            "admin": admin_name or "المدير العام",
            "action": action,
            "timestamp": now_str,
            "created_at": firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        print(f"❌ Error logging admin action: {e}")


# ==================== Task & Campaign Functions ====================

def get_active_campaigns(tg_id):
    """جلب قائمة المهمات النشطة"""
    try:
        if not db: initialize_firebase()
        user_data = get_user(tg_id) or {}
        completed_list = [str(x) for x in user_data.get("completed_tasks", [])]

        campaigns_ref = db.collection('tasks').where('active', '==', True).limit(50)
        docs = campaigns_ref.stream()

        campaigns = []
        for doc in docs:
            d = doc.to_dict() or {}
            cid = doc.id
            comp_count = int(d.get('users_completed', 0))
            need_count = int(d.get('users_needed', 1))

            if comp_count >= need_count: continue

            campaigns.append({
                "id": cid,
                "creator_id": str(d.get("creator_id", "")),
                "platform": d.get("platform", "أخرى"),
                "description": d.get("description", ""),
                "url": d.get("url", ""),
                "reward": float(d.get("reward", 0)),
                "users_needed": need_count,
                "users_completed": comp_count,
                "is_completed": (cid in completed_list)
            })

        return campaigns, float(user_data.get("balance", 0.0)), float(user_data.get("ad_balance", 0.0))
    except Exception as e:
        print(f"❌ Error fetching active campaigns: {e}")
        return [], 0.0, 0.0


def complete_user_task(tg_id, task_id):
    """إكمال مهمة وتسليم مكافأتها"""
    try:
        if not tg_id or not task_id: return False, "بيانات غير صالحة", 0.0
        tg_id_str, task_id_str = str(tg_id), str(task_id)

        user_ref = db.collection('users').document(tg_id_str)
        task_ref = db.collection('tasks').document(task_id_str)

        user_doc, task_doc = user_ref.get(), task_ref.get()

        if not user_doc.exists or not task_doc.exists:
            return False, "المهمة أو المستخدم غير موجود", 0.0

        user_data = user_doc.to_dict() or {}
        task_data = task_doc.to_dict() or {}

        completed = [str(x) for x in user_data.get("completed_tasks", [])]
        if task_id_str in completed:
            return False, "تم إكمال المهمة سابقاً!", float(user_data.get("balance", 0.0))

        reward = float(task_data.get("reward", 0.0))
        new_balance = round(float(user_data.get("balance", 0.0)) + reward, 2)

        task_ref.update({"users_completed": firestore.Increment(1)})
        user_ref.update({
            "balance": new_balance,
            "completed_tasks": firestore.ArrayUnion([task_id_str])
        })

        return True, "تم إكمال المهمة بنجاح!", new_balance
    except Exception as e:
        print(f"❌ Error completing task {task_id}: {e}")
        return False, "حدث خطأ أثناء معالجة المهمة", 0.0


def create_ad_campaign(tg_id, platform, description, url, reward, users_needed):
    """إنشاء حملة إعلانية جديدة"""
    try:
        if not tg_id: return False, "معرف غير صالح", 0.0
        tg_id_str = str(tg_id)
        
        reward = float(reward)
        users_needed = int(users_needed)
        total_cost = reward * users_needed

        if reward < 250 or total_cost < 250:
            return False, "الحد الأدنى لتكلفة الضغطة والميزانية هو 250 AdZN", 0.0

        user_ref = db.collection('users').document(tg_id_str)
        user_doc = user_ref.get()
        if not user_doc.exists: return False, "المستخدم غير موجود", 0.0

        current_ad_bal = float((user_doc.to_dict() or {}).get("ad_balance", 0.0))
        if current_ad_bal < total_cost:
            return False, "رصيد الإعلانات غير كافٍ!", current_ad_bal

        new_ad_bal = round(current_ad_bal - total_cost, 2)
        user_ref.update({"ad_balance": new_ad_bal})

        campaign_doc = {
            "creator_id": tg_id_str,
            "platform": platform,
            "description": description,
            "url": url,
            "reward": reward,
            "users_needed": users_needed,
            "users_completed": 0,
            "active": True,
            "created_at": firestore.SERVER_TIMESTAMP
        }
        db.collection('tasks').add(campaign_doc)

        return True, "تم إنشاء الحملة بنجاح!", new_ad_bal
    except Exception as e:
        print(f"❌ Error creating campaign: {e}")
        return False, f"حدث خطأ: {e}", 0.0


def convert_balance_to_ad_balance(tg_id, amount):
    """تحويل من الرصيد ZN إلى رصيد الإعلانات AdZN"""
    try:
        if not tg_id or amount <= 0: return False, "مبلغ غير صالح", 0.0, 0.0
        tg_id_str = str(tg_id)
        user_ref = db.collection('users').document(tg_id_str)
        user_doc = user_ref.get()

        if not user_doc.exists: return False, "المستخدم غير موجود", 0.0, 0.0

        user_data = user_doc.to_dict() or {}
        current_bal = float(user_data.get("balance", 0.0))
        current_ad_bal = float(user_data.get("ad_balance", 0.0))

        if current_bal < amount:
            return False, "رصيدك الأساسي غير كافٍ!", current_bal, current_ad_bal

        new_bal = round(current_bal - amount, 2)
        new_ad_bal = round(current_ad_bal + amount, 2)

        user_ref.update({
            "balance": new_bal,
            "ad_balance": new_ad_bal
        })

        return True, "تم التحويل بنجاح!", new_bal, new_ad_bal
    except Exception as e:
        print(f"❌ Error converting balance: {e}")
        return False, f"حدث خطأ: {e}", 0.0, 0.0


# ==================== Leaderboard & Rewards ====================

def get_leaderboard(limit=10):
    """جلب قائمة المتصدرين بسرعة مع الكاش"""
    global _LEADERBOARD_CACHE, _LEADERBOARD_CACHE_TIME
    now = time.time()
    if _LEADERBOARD_CACHE is not None and (now - _LEADERBOARD_CACHE_TIME) < LEADERBOARD_CACHE_TTL:
        return _LEADERBOARD_CACHE

    try:
        if not db: initialize_firebase()
        users_ref = db.collection('users').order_by('balance', direction=firestore.Query.DESCENDING).limit(limit)
        docs = users_ref.stream()

        leaderboard = []
        for i, doc in enumerate(docs, start=1):
            d = doc.to_dict() or {}
            leaderboard.append({
                "rank": i,
                "tg_id": str(d.get("tg_id", doc.id)),
                "first_name": d.get("first_name", "صديقي"),
                "balance": float(d.get("balance", 0.0))
            })

        _LEADERBOARD_CACHE = leaderboard
        _LEADERBOARD_CACHE_TIME = now
        return leaderboard
    except Exception as e:
        print(f"❌ Error fetching leaderboard: {e}")
        return _LEADERBOARD_CACHE or []


def claim_daily_reward(tg_id):
    """استلام المكافأة اليومية للمستخدم"""
    try:
        if not tg_id: return False, "معرف غير صالح", 0.0, 0
        user_data = get_user(tg_id)
        if not user_data: return False, "المستخدم غير موجود", 0.0, 0

        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        last_claim_date = user_data.get("last_daily_claim_date")

        if last_claim_date == today_str:
            return False, "لقد استلمت المكافأة اليومية بالفعل اليوم!", user_data.get("balance", 0.0), user_data.get("daily_streak", 0)

        current_streak = int(user_data.get("daily_streak", 0)) + 1
        if current_streak > 30: current_streak = 1

        settings = get_game_settings()
        rewards_map = settings.get("daily_rewards", {})
        reward_amount = float(rewards_map.get(f"day_{current_streak}", 100))

        new_balance = round(float(user_data.get("balance", 0.0)) + reward_amount, 2)

        update_user(tg_id, {
            "balance": new_balance,
            "daily_streak": current_streak,
            "last_daily_claim_date": today_str
        })

        return True, f"تم استلام مكافأة اليوم {current_streak} بنجاح (+{reward_amount} ZN)!", new_balance, current_streak
    except Exception as e:
        print(f"❌ Error claiming daily reward: {e}")
        return False, f"حدث خطأ: {e}", 0.0, 0


# التهيئة التلقائية عند استدعاء الملف
try:
    db = initialize_firebase()
    ensure_game_settings_exist()
except Exception as e:
    print(f"⚠️ تنبيه أثناء تهيئة DB تلقائياً: {e}")

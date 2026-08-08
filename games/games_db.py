from firebase_admin import firestore
import database

def update_zn_go_config(min_bet=None, target_margin=None, default_broken_coins=None):
    """تحديث إعدادات لعبة شبكة ZN Go ونسب الأرباح من لوحة التحكم"""
    try:
        db = database.get_db()
        config_ref = db.collection("app_config").document("game_settings")
        doc = config_ref.get()
        current_data = doc.to_dict() or {} if doc.exists else {}
        zn_cfg = current_data.get("zn_go_config") or current_data.get("grid_game_config", {})

        if min_bet is not None:
            zn_cfg["min_bet"] = float(min_bet)
        if target_margin is not None:
            val = float(target_margin)
            zn_cfg["target_margin"] = val / 100.0 if val > 1.0 else val
        if default_broken_coins is not None:
            zn_cfg["default_broken_coins"] = int(default_broken_coins)

        config_ref.set({"zn_go_config": zn_cfg, "grid_game_config": zn_cfg}, merge=True)
        database.clear_settings_cache()
        return True
    except Exception as e:
        print(f"❌ Error in update_zn_go_config: {e}")
        return False


update_grid_game_config = update_zn_go_config


def get_arena_config():
    """جلب إعدادات الساحة الكبرى من الفايربيس (مع استخدام الكاش)"""
    try:
        settings = database.get_game_settings() or {}
        return settings.get(
            "arena_config",
            {
                "entry_fee": 10.0,
                "min_participants": 20,
                "prize_pool_percentage": 0.30,
                "target_margin": 0.70,
            },
        )
    except Exception as e:
        print(f"❌ Error fetching arena_config: {e}")
        return {
            "entry_fee": 10.0,
            "min_participants": 20,
            "prize_pool_percentage": 0.30,
            "target_margin": 0.70,
        }


def update_arena_config(
    entry_fee=None, min_participants=None, prize_pool_percentage=None, target_margin=None
):
    """تحديث إعدادات الساحة الكبرى في الفايربيس وتفريغ الكاش فوراً"""
    try:
        db = database.get_db()
        config_ref = db.collection("app_config").document("game_settings")
        doc = config_ref.get()
        current_data = doc.to_dict() or {} if doc.exists else {}
        arena_cfg = current_data.get("arena_config", {})

        if entry_fee is not None:
            arena_cfg["entry_fee"] = float(entry_fee)
        if min_participants is not None:
            arena_cfg["min_participants"] = int(min_participants)
        if prize_pool_percentage is not None:
            val = float(prize_pool_percentage)
            arena_cfg["prize_pool_percentage"] = val / 100.0 if val > 1.0 else val
        if target_margin is not None:
            val = float(target_margin)
            arena_cfg["target_margin"] = val / 100.0 if val > 1.0 else val

        config_ref.set({"arena_config": arena_cfg}, merge=True)
        database.clear_settings_cache()
        return True
    except Exception as e:
        print(f"❌ Error in update_arena_config: {e}")
        return False


def record_bet_placed(tg_id, bet_amount):
    """1. دالة تسجيل الرهان الأساسي وخصمه من رصيد المستخدم"""
    try:
        db = database.get_db()
        bet = float(bet_amount)
        if bet <= 0:
            return False, "مبلغ الرهان غير صالح"

        tg_id_str = str(tg_id)
        user_ref = db.collection("users").document(tg_id_str)

        user_ref.update({
            "balance": firestore.Increment(-bet),
            "total_bets": firestore.Increment(bet),
        })

        config_ref = db.collection("app_config").document("game_settings")
        config_ref.update({"global_total_bets": firestore.Increment(bet)})

        arena_ref = db.collection("arena").document("current")
        arena_ref.set({
            "total_bets": firestore.Increment(bet),
            "last_updated": firestore.SERVER_TIMESTAMP,
        }, merge=True)

        database.clear_settings_cache()
        return True, "تم تسجيل الرهان بنجاح"
    except Exception as e:
        print(f"❌ Error recording bet placed: {e}")
        return False, str(e)


def record_game_loss(tg_id, bet_amount):
    """2. دالة تسجيل الخسارة (عند خسارة المراهنة بالكامل للبوت)"""
    try:
        db = database.get_db()
        bet = float(bet_amount)
        tg_id_str = str(tg_id)

        user_ref = db.collection("users").document(tg_id_str)
        user_ref.update({"total_losses": firestore.Increment(bet)})

        arena_ref = db.collection("arena").document("current")
        arena_ref.set({"last_updated": firestore.SERVER_TIMESTAMP}, merge=True)

        database.clear_settings_cache()
        return True
    except Exception as e:
        print(f"❌ Error recording game loss: {e}")
        return False


def record_game_win(tg_id, bet_amount, total_cashout_amount):
    """3. دالة تسجيل الربح والسحب (إعادة مبلغ الرهان + إضافة الصافي لدالة الربح)"""
    try:
        db = database.get_db()
        bet = float(bet_amount)
        cashout = float(total_cashout_amount)

        net_profit = max(0.0, cashout - bet)
        tg_id_str = str(tg_id)
        user_ref = db.collection("users").document(tg_id_str)

        user_ref.update({
            "balance": firestore.Increment(cashout),
            "total_wins": firestore.Increment(net_profit),
        })

        config_ref = db.collection("app_config").document("game_settings")
        config_ref.update({"global_total_wins": firestore.Increment(net_profit)})

        arena_ref = db.collection("arena").document("current")
        arena_ref.set({
            "total_payouts": firestore.Increment(net_profit),
            "last_updated": firestore.SERVER_TIMESTAMP,
        }, merge=True)

        database.clear_settings_cache()
        return True
    except Exception as e:
        print(f"❌ Error recording game win: {e}")
        return False


def get_game_profit_stats():
    """حساب أرباح ونسب البوت واللاعبين بدقة عالية وقراءة سريعة"""
    try:
        settings = database.get_game_settings() or {}
        zn_cfg = settings.get("zn_go_config") or settings.get("grid_game_config", {})

        arena_bets = 0.0
        arena_wins = 0.0
        try:
            db = database.get_db()
            arena_doc = db.collection("arena").document("current").get()
            if arena_doc.exists:
                a_data = arena_doc.to_dict() or {}
                arena_bets = float(a_data.get("total_bets", 0.0) or 0.0)
                arena_wins = float(a_data.get("total_payouts", 0.0) or 0.0)
        except Exception as e:
            print(f"⚠️ Error reading arena/current: {e}")

        total_bets = max(arena_bets, float(settings.get("global_total_bets", 0.0) or 0.0))
        total_wins = max(arena_wins, float(settings.get("global_total_wins", 0.0) or 0.0))

        bot_net_profit = max(0.0, total_bets - total_wins)
        target_margin = float(zn_cfg.get("target_margin", 0.70))
        target_margin_pct = target_margin * 100.0 if target_margin <= 1.0 else target_margin

        if total_bets > 0:
            actual_bot_pct = round(((total_bets - total_wins) / total_bets * 100.0), 2)
        else:
            actual_bot_pct = target_margin_pct

        actual_bot_pct = max(0.0, min(100.0, actual_bot_pct))
        actual_user_pct = round(100.0 - actual_bot_pct, 2)

        return {
            "total_bets": round(total_bets, 2),
            "total_wins": round(total_wins, 2),
            "total_bot_profit": round(bot_net_profit, 2),
            "total_user_profit": round(total_wins, 2),
            "target_margin": target_margin,
            "target_margin_percent": target_margin_pct,
            "actual_bot_percent": actual_bot_pct,
            "actual_user_percent": actual_user_pct,
            "global_total_bets": round(total_bets, 2),
            "global_total_wins": round(total_wins, 2),
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
            "actual_bot_percent": 70.0,
            "actual_user_percent": 30.0,
            "global_total_bets": 0.0,
            "global_total_wins": 0.0,
        }


def should_user_win_next_step():
    """دالة توضع داخل محرك اللعبة للتحكم بنسبة الربح المحددة للبوت واللاعب"""
    try:
        stats = get_game_profit_stats()
        actual_bot_pct = stats.get("actual_bot_percent", 70.0)
        target_bot_pct = stats.get("target_margin_percent", 70.0)

        if actual_bot_pct < target_bot_pct:
            return False
        return True
    except Exception:
        return True

import time
from typing import Dict, Any, Tuple, List, Optional
from firebase_admin import firestore

try:
    from database import db
except ImportError:
    try:
        db = firestore.client()
    except Exception:
        db = None

def get_db_instance():
    return db

# ==========================================
# 1. إعدادات الألعاب وإحصائيات الأرباح
# ==========================================

def get_game_settings() -> Dict[str, Any]:
    if not db:
        return {}
    try:
        doc = db.collection('settings').document('games').get()
        return doc.to_dict() if doc.exists else {}
    except Exception as e:
        print(f"⚠️ [games_db] Error fetching game settings: {e}")
        return {}

def get_grid_36_config() -> Dict[str, Any]:
    default_cfg = {
        "bot_margin": 70.0,
        "player_profit_percentage": 30.0,
        "min_bet": 100.0,
        "enabled": True
    }
    if not db:
        return default_cfg
    try:
        doc = db.collection('settings').document('grid_36').get()
        if doc.exists:
            data = doc.to_dict() or {}
            default_cfg.update(data)
            return default_cfg
        gen_settings = get_game_settings()
        grid_data = gen_settings.get('grid_36', {})
        if grid_data:
            default_cfg.update(grid_data)
        return default_cfg
    except Exception as e:
        print(f"⚠️ [games_db] Error fetching grid_36 config: {e}")
        return default_cfg

def get_big_arena_config() -> Dict[str, Any]:
    default_cfg = {
        "bot_margin": 70.0,
        "player_profit_percentage": 30.0,
        "min_bet": 350.0,
        "entry_fee": 350.0,
        "min_players": 2,
        "duration_seconds": 300,
        "lock_seconds": 15,
        "enabled": True
    }
    if not db:
        return default_cfg
    try:
        doc = db.collection('settings').document('big_arena').get()
        if doc.exists:
            data = doc.to_dict() or {}
            default_cfg.update(data)
            return default_cfg
        gen_settings = get_game_settings()
        arena_data = gen_settings.get('arena_config', {})
        if arena_data:
            default_cfg.update(arena_data)
        return default_cfg
    except Exception as e:
        print(f"⚠️ [games_db] Error fetching big_arena config: {e}")
        return default_cfg

def get_game_profit_stats() -> Dict[str, Any]:
    default_stats = {
        "actual_bot_percent": 70.0,
        "total_bot_profit": 0.0,
        "total_player_profit": 0.0,
        "total_bets_amount": 0.0,
        "total_wins": 0,
        "total_bets_count": 0
    }
    if not db:
        return default_stats
    try:
        doc = db.collection('game_stats').document('summary').get()
        if doc.exists:
            data = doc.to_dict() or {}
            total_bets = float(data.get('total_bets_amount', 0.0))
            bot_profit = float(data.get('total_bot_profit', 0.0))
            actual_pct = (bot_profit / total_bets * 100.0) if total_bets > 0 else 70.0
            data['actual_bot_percent'] = max(0.0, min(100.0, actual_pct))
            default_stats.update(data)
        return default_stats
    except Exception as e:
        print(f"⚠️ [games_db] Error fetching game profit stats: {e}")
        return default_stats

def should_user_win_next_step(uid: str = None) -> bool:
    try:
        grid_cfg = get_grid_36_config()
        player_pct = float(grid_cfg.get('player_profit_percentage', 30.0))
        target_margin = (100.0 - player_pct) / 100.0 if player_pct <= 100.0 else 0.70

        stats = get_game_profit_stats()
        actual_margin = float(stats.get('actual_bot_percent', 70.0)) / 100.0

        if actual_margin < target_margin:
            return False
        return True
    except Exception as e:
        print(f"⚠️ [games_db] Error calculating win condition: {e}")
        return True

# ==========================================
# 2. تسجيل المراهنات وتحديث الإحصائيات
# ==========================================

def update_db_game_stats(bet_amount: float = 0.0, win_amount: float = 0.0) -> bool:
    if not db:
        return False
    try:
        stats_ref = db.collection('game_stats').document('summary')
        bot_profit_change = bet_amount - win_amount

        update_payload = {}
        if bet_amount > 0:
            update_payload['total_bets_amount'] = firestore.Increment(bet_amount)
            update_payload['total_bets_count'] = firestore.Increment(1)
        if win_amount > 0:
            update_payload['total_player_profit'] = firestore.Increment(win_amount)
            update_payload['total_wins_count'] = firestore.Increment(1)
            update_payload['total_wins'] = firestore.Increment(1)
        if bot_profit_change != 0:
            update_payload['total_bot_profit'] = firestore.Increment(bot_profit_change)

        if update_payload:
            stats_ref.set(update_payload, merge=True)
        return True
    except Exception as e:
        print(f"⚠️ [games_db] Error updating game stats: {e}")
        return False

def record_user_game_result(uid: str, bet_amount: float = 0.0, win_amount: float = 0.0) -> None:
    if not db:
        return
    try:
        uid_str = str(uid)
        ref = db.collection('game_logs').document()
        ref.set({
            'uid': uid_str,
            'bet_amount': float(bet_amount),
            'win_amount': float(win_amount),
            'timestamp': time.time(),
            'created_at': firestore.SERVER_TIMESTAMP
        })
    except Exception as e:
        print(f"⚠️ [games_db] Error recording result: {e}")

# ==========================================
# 3. إدارة المعاملات المالية الحسابية
# ==========================================

def get_user_data(uid: str) -> Tuple[bool, Dict[str, Any]]:
    if not db:
        return False, {}
    try:
        user_doc = db.collection('users').document(str(uid)).get()
        if user_doc.exists:
            return True, user_doc.to_dict() or {}
        return False, {}
    except Exception as e:
        print(f"⚠️ [games_db] Error getting user data: {e}")
        return False, {}

def deduct_user_balance_transactional(uid: str, amount: float) -> Tuple[bool, str, float]:
    if not db:
        return False, "قاعدة البيانات غير متصلة", 0.0

    uid_str = str(uid)
    user_ref = db.collection('users').document(uid_str)

    @firestore.transactional
    def txn(transaction):
        doc = user_ref.get(transaction=transaction)
        if not doc.exists:
            return False, "المستخدم غير موجود", 0.0

        data = doc.to_dict() or {}
        bal = round(float(data.get('balance', 0.0)), 2)
        if bal < amount:
            return False, "الرصيد غير كافٍ", bal

        new_bal = round(bal - amount, 2)
        transaction.update(user_ref, {'balance': new_bal})
        return True, "تم الخصم بنجاح", new_bal

    try:
        return txn(db.transaction())
    except Exception as e:
        print(f"⚠️ [games_db] Transaction deduction error: {e}")
        return False, "خطأ في المعاملة المالية", 0.0

def add_user_balance_transactional(uid: str, amount: float) -> Tuple[bool, str, float]:
    if not db:
        return False, "قاعدة البيانات غير متصلة", 0.0

    uid_str = str(uid)
    user_ref = db.collection('users').document(uid_str)

    @firestore.transactional
    def txn(transaction):
        doc = user_ref.get(transaction=transaction)
        if not doc.exists:
            return False, "المستخدم غير موجود", 0.0

        data = doc.to_dict() or {}
        bal = round(float(data.get('balance', 0.0)), 2)
        new_bal = round(bal + amount, 2)

        transaction.update(user_ref, {'balance': new_bal})
        return True, "تمت إضافة المبلغ بنجاح", new_bal

    try:
        return txn(db.transaction())
    except Exception as e:
        print(f"⚠️ [games_db] Transaction addition error: {e}")
        return False, "خطأ في المعاملة المالية", 0.0

def clear_user_pending_refund(uid: str) -> Tuple[float, float]:
    if not db:
        return 0.0, 0.0
    try:
        uid_str = str(uid)
        user_ref = db.collection('users').document(uid_str)
        user_doc = user_ref.get()
        if not user_doc.exists:
            return 0.0, 0.0

        data = user_doc.to_dict() or {}
        pending_refund = round(float(data.get('pending_refund', 0.0)), 2)
        current_balance = round(float(data.get('balance', 0.0)), 2)

        if pending_refund > 0:
            new_bal = round(current_balance + pending_refund, 2)
            user_ref.update({'pending_refund': 0, 'balance': new_bal})
            return pending_refund, new_bal

        return 0.0, current_balance
    except Exception as e:
        print(f"⚠️ [games_db] Error clearing pending refund: {e}")
        return 0.0, 0.0

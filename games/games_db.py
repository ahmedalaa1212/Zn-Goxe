import time
from typing import Dict, Any, Tuple, List, Optional
from firebase_admin import firestore

def _get_db():
    """الحصول على كائن قاعدة البيانات المتاح بشكل ديناميكي من database.py"""
    try:
        from database import get_db
        db_instance = get_db()
        if db_instance:
            return db_instance
    except Exception:
        pass

    try:
        return firestore.client()
    except Exception as e:
        print(f"⚠️ [games_db] Failed to acquire Firestore client: {e}")
        return None

# ==========================================
# 1. إعدادات الألعاب وإحصائيات الأرباح
# ==========================================

def get_game_settings() -> Dict[str, Any]:
    db = _get_db()
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
    db = _get_db()
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
        "enabled": True,
        "payout_percentages": [40.0, 20.0, 10.0, 8.0, 6.0, 5.0, 4.0, 3.0, 2.0, 2.0]
    }
    db = _get_db()
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
    db = _get_db()
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
    db = _get_db()
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
    db = _get_db()
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
# 3. إدارة المستخدم والمعاملات المالية والإشعارات المباشرة
# ==========================================

def get_user_doc_ref(uid: str):
    """البحث الذكي عن مستند المستخدم سواء كان المعرف نصي أو رقمي"""
    db = _get_db()
    if not db or not uid:
        return None, {}

    uid_str = str(uid).strip()

    # 1. التجربة بواسطة String ID
    doc_ref = db.collection('users').document(uid_str)
    doc = doc_ref.get()
    if doc.exists:
        return doc_ref, doc.to_dict() or {}

    # 2. التجربة بواسطة Integer ID
    if uid_str.isdigit():
        doc_ref_int = db.collection('users').document(str(int(uid_str)))
        doc_int = doc_ref_int.get()
        if doc_int.exists:
            return doc_ref_int, doc_int.to_dict() or {}

    # 3. البحث باستخدام استعلام حقول المعرفات المتنوعة
    try:
        queries = ['telegram_id', 'tg_id', 'user_id', 'id']
        for field in queries:
            val = int(uid_str) if uid_str.isdigit() else uid_str
            q = db.collection('users').where(field, '==', val).limit(1).get()
            if q:
                return q[0].reference, q[0].to_dict() or {}
    except Exception as e:
        print(f"⚠️ [games_db] Query lookup exception: {e}")

    return None, {}

def get_user_data(uid: str) -> Tuple[bool, Dict[str, Any]]:
    doc_ref, data = get_user_doc_ref(uid)
    if doc_ref and data:
        if 'balance' not in data:
            data['balance'] = data.get('zn_balance', data.get('coins', 0.0))
        return True, data
    return False, {}

def deduct_user_balance_transactional(uid: str, amount: float) -> Tuple[bool, str, float]:
    db = _get_db()
    if not db:
        return False, "قاعدة البيانات غير متصلة", 0.0

    doc_ref, data = get_user_doc_ref(uid)
    if not doc_ref:
        return False, "المستخدم غير موجود", 0.0

    @firestore.transactional
    def txn(transaction):
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            return False, "المستخدم غير موجود", 0.0

        u_data = snapshot.to_dict() or {}
        bal = round(float(u_data.get('balance', u_data.get('zn_balance', 0.0))), 2)
        if bal < amount:
            return False, "الرصيد غير كافٍ", bal

        new_bal = round(bal - amount, 2)
        transaction.update(doc_ref, {
            'balance': new_bal,
            'zn_balance': new_bal
        })
        return True, "تم الخصم بنجاح", new_bal

    try:
        return txn(db.transaction())
    except Exception as e:
        print(f"⚠️ [games_db] Transaction deduction error: {e}")
        return False, "خطأ في المعاملة المالية", 0.0

def add_user_balance_transactional(uid: str, amount: float) -> Tuple[bool, str, float]:
    db = _get_db()
    if not db:
        return False, "قاعدة البيانات غير متصلة", 0.0

    doc_ref, data = get_user_doc_ref(uid)
    if not doc_ref:
        return False, "المستخدم غير موجود", 0.0

    @firestore.transactional
    def txn(transaction):
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            return False, "المستخدم غير موجود", 0.0

        u_data = snapshot.to_dict() or {}
        bal = round(float(u_data.get('balance', u_data.get('zn_balance', 0.0))), 2)
        new_bal = round(bal + amount, 2)

        transaction.update(doc_ref, {
            'balance': new_bal,
            'zn_balance': new_bal
        })
        return True, "تمت إضافة المبلغ بنجاح", new_bal

    try:
        return txn(db.transaction())
    except Exception as e:
        print(f"⚠️ [games_db] Transaction addition error: {e}")
        return False, "خطأ في المعاملة المالية", 0.0

def clear_user_pending_refund(uid: str) -> Tuple[float, float, str]:
    """تحديث واسترجاع المبالغ المعلقة محصنة بـ Transaction تمنع استرجاع المبلغ أكثر من مرة"""
    db = _get_db()
    if not db:
        return 0.0, 0.0, ""

    doc_ref, _ = get_user_doc_ref(uid)
    if not doc_ref:
        return 0.0, 0.0, ""

    @firestore.transactional
    def txn(transaction):
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            return 0.0, 0.0, ""

        data = snapshot.to_dict() or {}
        pending_refund = round(float(data.get('pending_refund', 0.0)), 2)
        current_balance = round(float(data.get('balance', data.get('zn_balance', 0.0))), 2)
        pending_msg = data.get('pending_notification', '')

        if pending_refund > 0:
            new_bal = round(current_balance + pending_refund, 2)
            msg = pending_msg or f"تم استرجاع رصيد بقيمة {pending_refund} ZN إلى حسابك بنجاح! 💰"
            transaction.update(doc_ref, {
                'pending_refund': 0.0,
                'pending_notification': '',
                'balance': new_bal,
                'zn_balance': new_bal
            })
            return pending_refund, new_bal, msg
        elif pending_msg:
            transaction.update(doc_ref, {'pending_notification': ''})
            return 0.0, current_balance, pending_msg

        return 0.0, current_balance, ""

    try:
        return txn(db.transaction())
    except Exception as e:
        print(f"⚠️ [games_db] Error clearing pending refund atomically: {e}")
        return 0.0, 0.0, ""

# ==========================================
# 4. حفظ واسترجاع حالة الساحة والشبكة بالدعم المباشر
# ==========================================

def get_arena_state_db() -> Optional[Dict[str, Any]]:
    db = _get_db()
    if not db:
        return None
    try:
        doc = db.collection('settings').document('arena_state').get()
        return doc.to_dict() if doc.exists else None
    except Exception as e:
        print(f"⚠️ [games_db] Error fetching arena state: {e}")
        return None

def save_arena_state_db(state: Dict[str, Any]) -> None:
    db = _get_db()
    if not db:
        return
    try:
        db.collection('settings').document('arena_state').set(state, merge=True)
    except Exception as e:
        print(f"⚠️ [games_db] Error saving arena state: {e}")

from typing import Dict, Any, Tuple
from games.games_db import (
    get_big_arena_config,
    deduct_user_balance_transactional,
    add_user_balance_transactional,
    record_user_game_result,
    update_db_game_stats
)

class BigArenaManager:
    """إدارة مواجهات ورهانات الساحة الكبرى Arena"""

    def __init__(self):
        self.arena_rooms: Dict[str, Dict[str, Any]] = {}

    def enter_arena(self, uid: str) -> Tuple[bool, str, float]:
        """خصم رسم دخول الساحة الكبرى"""
        config = get_big_arena_config()
        if not config.get("enabled", True):
            return False, "⚠️ الساحة الكبرى مغلقة حالياً.", 0.0

        entry_fee = float(config.get("entry_fee", 350.0))

        # خصم رسوم الدخول
        success, msg, new_bal = deduct_user_balance_transactional(uid, entry_fee)
        if not success:
            return False, f"❌ فشل الانضمام للساحة: {msg}", 0.0

        # تسجيل الخصم المبدئي
        record_user_game_result(uid, bet_amount=entry_fee, win_amount=0.0)
        return True, f"⚔️ تم دخول الساحة الكبرى بنجاح! تم خصم {entry_fee} كوينز.", new_bal

    def resolve_arena_match(self, winner_uid: str, loser_uid: str, prize_pool: float) -> Tuple[bool, str]:
        """إنهاء المواجهة وتوزيع الجوائز للفائز مع احتساب هامش أرباح النظام"""
        config = get_big_arena_config()
        margin_pct = float(config.get("bot_margin", 70.0))

        # احتساب حصة الفائز بعد اقتطاع هامش البوت
        winner_payout = round(prize_pool * ((100.0 - margin_pct) / 100.0), 2)

        # إضافة الجائزة لرصيد الفائز
        success, msg, _ = add_user_balance_transactional(winner_uid, winner_payout)
        if not success:
            return False, f"❌ فشل تحويل الجائزة للفائز: {msg}"

        # تسجيل أرباح الفائز والخسارة للمهزوم
        record_user_game_result(winner_uid, bet_amount=0.0, win_amount=winner_payout)
        update_db_game_stats(bet_amount=prize_pool, win_amount=winner_payout)

        return True, f"🏆 تم إعلان الفائز وتوزيع {winner_payout} كوينز بنجاح!"

big_arena_manager = BigArenaManager()

import random
import uuid
from typing import Dict, Any, Tuple, List
from games.games_db import (
    get_grid_36_config,
    should_user_win_next_step,
    deduct_user_balance_transactional,
    add_user_balance_transactional,
    record_user_game_result,
    update_db_game_stats
)

class Grid36Manager:
    """إدارة جلسات لعبة شبكة ZN Go (36 صندوق)"""

    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

    def generate_multipliers(self, broken_count: int) -> List[float]:
        """إنشاء جدول مضاعفات متوازن برمجياً"""
        base_mults = [1.2, 1.5, 2.0, 2.8, 3.8, 5.2, 7.5, 10.0, 14.0, 20.0, 28.0, 40.0]
        extra_factor = 1.0 + ((broken_count - 3) * 0.25)
        return [round(m * extra_factor, 2) for m in base_mults]

    def start_new_game(self, uid: str, bet_amount: float, broken_count: int = 3) -> Tuple[bool, str, Dict[str, Any]]:
        config = get_grid_36_config()
        if not config.get("enabled", True):
            return False, "⚠️ اللعبة معطلة حالياً من قبل الإدارة.", {}

        min_bet = float(config.get("min_bet", 100.0))
        if bet_amount < min_bet:
            return False, f"⚠️ الحد الأدنى للرهان هو {min_bet} ZN.", {}

        broken_count = max(3, min(8, broken_count))

        success, msg, new_bal = deduct_user_balance_transactional(uid, bet_amount)
        if not success:
            return False, f"❌ فشل بدء اللعبة: {msg}", {}

        record_user_game_result(uid, bet_amount=bet_amount, win_amount=0.0)

        # توليد أماكن القنابل خفية
        board_layout = [False] * 36
        bomb_indices = random.sample(range(36), broken_count)
        for idx in bomb_indices:
            board_layout[idx] = True

        session_token = str(uuid.uuid4())
        multipliers = self.generate_multipliers(broken_count)

        session = {
            "uid": str(uid),
            "session_token": session_token,
            "bet_amount": bet_amount,
            "broken_count": broken_count,
            "layout": board_layout,
            "opened_boxes": [],
            "multipliers": multipliers,
            "active": True
        }
        self.active_sessions[str(uid)] = session

        return True, "🎮 تم بدء الجولة بنجاح!", {
            "new_balance": new_bal,
            "session_token": session_token,
            "multipliers": multipliers
        }

    def open_box(self, uid: str, box_index: int, session_token: str = None) -> Tuple[bool, str, Dict[str, Any]]:
        uid_str = str(uid)
        session = self.active_sessions.get(uid_str)

        if not session or not session.get("active"):
            return False, "⚠️ لا توجد جولة نشطة حالياً.", {}

        if box_index < 0 or box_index >= 36:
            return False, "⚠️ رقم الصندوق غير صحيح.", {}

        if box_index in session["opened_boxes"]:
            return False, "⚠️ الصندوق مفتوح بالفعل!", {}

        bet = session["bet_amount"]
        is_bomb = session["layout"][box_index]

        # حماية الخزينة
        if not should_user_win_next_step(uid_str):
            is_bomb = True

        if is_bomb:
            session["active"] = False
            update_db_game_stats(bet_amount=bet, win_amount=0.0)
            layout_copy = list(session["layout"])
            del self.active_sessions[uid_str]

            return True, "💥 اصطدمت بقنبلة!", {
                "status": "loss",
                "is_bomb": True,
                "box_index": box_index,
                "layout": layout_copy,
                "win_amount": 0.0
            }

        session["opened_boxes"].append(box_index)
        step_idx = len(session["opened_boxes"]) - 1
        mults = session["multipliers"]
        current_mult = mults[min(step_idx, len(mults) - 1)]
        current_win = round(bet * current_mult, 2)

        return True, f"✨ صندوق آمن! المضاعف: x{current_mult}", {
            "status": "safe",
            "is_bomb": False,
            "box_index": box_index,
            "step": step_idx + 1,
            "multiplier": current_mult,
            "current_win": current_win
        }

    def cashout(self, uid: str) -> Tuple[bool, str, Dict[str, Any]]:
        uid_str = str(uid)
        session = self.active_sessions.get(uid_str)

        if not session or not session.get("active"):
            return False, "⚠️ لا توجد أرباح قابلة للسحب.", {}

        opened_count = len(session["opened_boxes"])
        if opened_count == 0:
            return False, "⚠️ اختر صندوقاً واحداً على الأقل قبل السحب.", {}

        bet = session["bet_amount"]
        mults = session["multipliers"]
        current_mult = mults[min(opened_count - 1, len(mults) - 1)]
        win_amount = round(bet * current_mult, 2)

        success, msg, new_bal = add_user_balance_transactional(uid_str, win_amount)
        if not success:
            return False, f"❌ فشل إضافة الأرباح: {msg}", {}

        record_user_game_result(uid_str, bet_amount=bet, win_amount=win_amount)
        update_db_game_stats(bet_amount=bet, win_amount=win_amount)

        layout_copy = list(session["layout"])
        session["active"] = False
        del self.active_sessions[uid_str]

        return True, f"🎉 تم سحب الأرباح: {win_amount} ZN", {
            "payout": win_amount,
            "multiplier": current_mult,
            "new_balance": new_bal,
            "layout": layout_copy
        }

grid_36_manager = Grid36Manager()

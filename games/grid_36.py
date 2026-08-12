import random
from typing import Dict, Any, Tuple
from games.games_db import get_user_data, get_user_doc_ref, record_user_game_result

class BoxesGameManager:
    """إدارة لعبة الصناديق شبكة ZN Go"""

    def __init__(self):
        self.multipliers = [0.0, 0.5, 1.2, 1.5, 2.0, 3.0, 5.0]

    def play_box(self, uid: str, box_index: int, bet_amount: float) -> Tuple[bool, str, Dict[str, Any]]:
        uid_str = str(uid)
        bet = round(float(bet_amount), 2)

        if bet <= 0:
            return False, "❌ مبلغ الرهان غير صالح.", {}

        p_ref, udata = get_user_doc_ref(uid_str)
        if not p_ref or not udata:
            return False, "❌ المستخدم غير موجود.", {}

        curr_bal = round(float(udata.get("balance", udata.get("zn_balance", 0.0))), 2)

        if curr_bal < bet:
            return False, "❌ رصيدك غير كافٍ.", {}

        # اختر مضاعفاً عشوائياً
        mult = random.choice(self.multipliers)
        win_amt = round(bet * mult, 2)
        new_bal = round(curr_bal - bet + win_amt, 2)

        # تحديث قاعدة البيانات
        p_ref.set({'balance': new_bal, 'zn_balance': new_bal}, merge=True)
        record_user_game_result(uid_str, bet_amount=bet, win_amount=win_amt)

        return True, "تم الكشف عن الصندوق!", {
            "multiplier": mult,
            "win_amount": win_amt,
            "new_balance": new_bal
        }

boxes_game_manager = BoxesGameManager()

import random
from typing import Dict, Any, Tuple
from games.games_db import (
    get_grid_36_config,
    should_user_win_next_step,
    deduct_user_balance_transactional,
    add_user_balance_transactional,
    record_user_game_result,
    update_db_game_stats
)

class Grid36Manager:
    """إدارة جلسات لعبة ZN Go الـ 36 صندوقاً"""

    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

    def start_new_game(self, uid: str, bet_amount: float) -> Tuple[bool, str, Dict[str, Any]]:
        """بدء جولة جديدة لـ 36 صندوق وخصم قيمة الرهان"""
        config = get_grid_36_config()
        if not config.get("enabled", True):
            return False, "⚠️ اللعبة معطلة حالياً من قبل الإدارة.", {}

        min_bet = float(config.get("min_bet", 100.0))
        if bet_amount < min_bet:
            return False, f"⚠️ الحد الأدنى للرهان هو {min_bet} كوينز.", {}

        # خصم الرصيد بآلية معاملة آمنة (Transaction)
        success, msg, new_bal = deduct_user_balance_transactional(uid, bet_amount)
        if not success:
            return False, f"❌ فشل بدء اللعبة: {msg}", {}

        # تسجيل الرهان في قاعدة البيانات
        record_user_game_result(uid, bet_amount=bet_amount, win_amount=0.0)

        # إنشاء جلسة جديدة للاعب
        session = {
            "uid": str(uid),
            "bet_amount": bet_amount,
            "current_step": 0,
            "multiplier": 1.0,
            "opened_boxes": [],
            "active": True
        }
        self.active_sessions[str(uid)] = session

        return True, "🎮 تم بدء الجولة بنجاح! اختر صندوقاً.", {
            "new_balance": new_bal,
            "session": session
        }

    def open_box(self, uid: str, box_index: int) -> Tuple[bool, str, Dict[str, Any]]:
        """فتح صندوق محدد من الـ 36 صندوقاً"""
        uid_str = str(uid)
        session = self.active_sessions.get(uid_str)

        if not session or not session.get("active"):
            return False, "⚠️ لا توجد جولة نشطة حالياً.", {}

        if box_index < 0 or box_index >= 36:
            return False, "⚠️ رقم الصندوق غير صحيح (من 0 إلى 35).", {}

        if box_index in session["opened_boxes"]:
            return False, "⚠️ هذا الصندوق تم فتحه بالفعل!", {}

        bet = session["bet_amount"]
        
        # التحقق من خوارزمية حماية الخزينة وأرباح البوت
        can_win = should_user_win_next_step(uid_str)

        # احتساب نسبة حدوث القنبلة (15% عشوائي أو إجباري إذا انخفضت أرباح البوت)
        is_bomb = not can_win or (random.random() < 0.18)

        if is_bomb:
            # خسارة الجولة
            session["active"] = False
            update_db_game_stats(bet_amount=bet, win_amount=0.0)
            del self.active_sessions[uid_str]

            return True, "💥 للأسف! اصطدمت بقنبلة وخسرت الرهان.", {
                "status": "loss",
                "box_index": box_index,
                "win_amount": 0.0
            }

        # نجاح وفتح صندوق آمن
        session["opened_boxes"].append(box_index)
        session["current_step"] += 1
        
        # زيادة المضاعف مع كل خطوة (مثال: +20% كل صندوق آمن)
        session["multiplier"] = round(session["multiplier"] + 0.20, 2)
        current_win = round(bet * session["multiplier"], 2)

        return True, f"✨ صندوق آمن! المضاعف الحالي: x{session['multiplier']}", {
            "status": "safe",
            "box_index": box_index,
            "step": session["current_step"],
            "multiplier": session["multiplier"],
            "current_win": current_win
        }

    def cashout(self, uid: str) -> Tuple[bool, str, float]:
        """سحب الأرباح وإنهاء الجولة"""
        uid_str = str(uid)
        session = self.active_sessions.get(uid_str)

        if not session or not session.get("active"):
            return False, "⚠️ لا توجد أرباح قابلة للسحب.", 0.0

        if session["current_step"] == 0:
            return False, "⚠️ يجب فتح صندوق آمن واحد على الأقل قبل السحب.", 0.0

        bet = session["bet_amount"]
        win_amount = round(bet * session["multiplier"], 2)

        # إضافة الأرباح لرصيد المستخدم
        success, msg, new_bal = add_user_balance_transactional(uid_str, win_amount)
        if not success:
            return False, f"❌ فشل إضافة الأرباح: {msg}", 0.0

        # تسجيل الفوز وتحديث إحصائيات الأرباح
        record_user_game_result(uid_str, bet_amount=bet, win_amount=win_amount)
        update_db_game_stats(bet_amount=bet, win_amount=win_amount)

        # إغلاق الجولة
        session["active"] = False
        del self.active_sessions[uid_str]

        return True, f"🎉 تم سحب الأرباح بنجاح: {win_amount} كوينز!", new_bal

grid_36_manager = Grid36Manager()

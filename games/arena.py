import time
from typing import Dict, Any, Tuple, List
from games.games_db import (
    get_big_arena_config,
    deduct_user_balance_transactional,
    add_user_balance_transactional,
    record_user_game_result,
    update_db_game_stats,
    get_db_instance,
    get_user_data
)

class BigArenaManager:
    """إدارة جولات ورهانات الساحة الكبرى Arena مع السحب التلقائي"""

    def __init__(self):
        self.current_round: Dict[str, Any] = None
        self._init_or_load_round()

    def _init_or_load_round(self):
        cfg = get_big_arena_config()
        duration = int(cfg.get("duration_seconds", 300))
        now = int(time.time())
        self.current_round = {
            "round_id": f"arena_{now}",
            "start_time": now,
            "end_time": now + duration,
            "prize_pool": 0.0,
            "participants": [],
            "status": "active",
            "winners": []
        }

    def get_status(self, uid: str) -> Dict[str, Any]:
        cfg = get_big_arena_config()
        now = int(time.time())

        # تجديد الجولة تلقائياً عند انتهائها
        if now >= self.current_round["end_time"] and self.current_round["status"] == "active":
            self.resolve_round()

        uid_str = str(uid) if uid else ""
        has_joined = uid_str in self.current_round.get("participants", [])
        _, user_data = get_user_data(uid_str) if uid_str else (False, {})

        return {
            "success": True,
            "round_id": self.current_round["round_id"],
            "end_time": self.current_round["end_time"],
            "entry_fee": float(cfg.get("entry_fee", 350.0)),
            "lock_seconds": int(cfg.get("lock_seconds", 15)),
            "prize_pool": self.current_round["prize_pool"],
            "has_joined": has_joined,
            "balance": float(user_data.get("balance", 0.0))
        }

    def enter_arena(self, uid: str) -> Tuple[bool, str, Dict[str, Any]]:
        cfg = get_big_arena_config()
        if not cfg.get("enabled", True):
            return False, "⚠️ الساحة الكبرى مغلقة حالياً.", {}

        now = int(time.time())
        lock_secs = int(cfg.get("lock_seconds", 15))
        if self.current_round["end_time"] - now <= lock_secs:
            return False, "🔒 تم إغلاق باب الاشتراك لهذه الجولة.", {}

        uid_str = str(uid)
        if uid_str in self.current_round["participants"]:
            return False, "⚠️ أنت مشترك بالفعل في هذه الجولة.", {}

        entry_fee = float(cfg.get("entry_fee", 350.0))
        success, msg, new_bal = deduct_user_balance_transactional(uid_str, entry_fee)
        if not success:
            return False, f"❌ فشل الدخول: {msg}", {}

        self.current_round["participants"].append(uid_str)
        self.current_round["prize_pool"] += entry_fee
        record_user_game_result(uid_str, bet_amount=entry_fee, win_amount=0.0)

        return True, f"⚔️ تم انضمامك للساحة بنجاح!", {
            "new_balance": new_bal,
            "prize_pool": self.current_round["prize_pool"]
        }

    def resolve_round(self):
        cfg = get_big_arena_config()
        min_players = int(cfg.get("min_players", 2))
        participants = self.current_round["participants"]
        entry_fee = float(cfg.get("entry_fee", 350.0))

        if len(participants) < min_players:
            # إعادة الأموال لعدم اكتمال النصاب
            self.current_round["status"] = "refunded"
            db = get_db_instance()
            for p_uid in participants:
                if db:
                    db.collection('users').document(p_uid).set({'pending_refund': entry_fee}, merge=True)
                else:
                    add_user_balance_transactional(p_uid, entry_fee)
        else:
            self.current_round["status"] = "completed"
            bot_margin = float(cfg.get("bot_margin", 70.0))
            total_pool = self.current_round["prize_pool"]
            distributable_pool = total_pool * ((100.0 - bot_margin) / 100.0)

            # توزيع الجوائز نسبياً 30% - 25% - 20% - 15% - 10%
            shares = [0.30, 0.25, 0.20, 0.15, 0.10]
            winners = []
            import random
            shuffled = list(participants)
            random.shuffle(shuffled)

            for idx, p_uid in enumerate(shuffled[:5]):
                prize = round(distributable_pool * shares[idx], 2)
                add_user_balance_transactional(p_uid, prize)
                record_user_game_result(p_uid, bet_amount=0.0, win_amount=prize)
                _, udata = get_user_data(p_uid)
                winners.append({
                    "uid": p_uid,
                    "name": udata.get("name", f"مستخدم #{p_uid[:5]}"),
                    "prize": prize,
                    "rank": idx + 1
                })

            update_db_game_stats(bet_amount=total_pool, win_amount=distributable_pool)
            self.current_round["winners"] = winners

        # بدء جولة جديدة تلقائياً
        self._init_or_load_round()

    def get_results(self, round_id: str, uid: str) -> Dict[str, Any]:
        if self.current_round.get("status") in ["refunded", "completed"]:
            return {
                "success": True,
                "status": self.current_round["status"],
                "winners": self.current_round.get("winners", []),
                "refund_amount": float(get_big_arena_config().get("entry_fee", 350.0))
            }
        return {"success": True, "status": "completed", "winners": self.current_round.get("winners", [])}

big_arena_manager = BigArenaManager()

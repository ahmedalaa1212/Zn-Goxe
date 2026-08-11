import time
import random
from typing import Dict, Any, Tuple, List
from games.games_db import (
    get_big_arena_config,
    deduct_user_balance_transactional,
    add_user_balance_transactional,
    record_user_game_result,
    update_db_game_stats,
    get_user_data,
    get_arena_state_db,
    save_arena_state_db,
    _get_db
)

class BigArenaManager:
    """إدارة جولات ورهانات الساحة الكبرى Arena مع السحب التلقائي ونظام المبادرين وإرجاع الأموال"""

    def __init__(self):
        self.current_round: Dict[str, Any] = None
        self._init_or_load_round()

    def _sync_round_state(self):
        """مزامنة حالة الجولة من قاعدة البيانات وإنهاؤها تلقائياً عند انقضاء الوقت"""
        db_state = get_arena_state_db()
        now = int(time.time())

        if db_state:
            self.current_round = db_state

        if not self.current_round:
            self._init_or_load_round()
            return

        # إذا انتهى وقت الجولة وهي لا تزال نشطة، نقوم بإنهائها فوراً وتوزيع الأرباح
        if now >= self.current_round.get("end_time", 0) and self.current_round.get("status") == "active":
            self.resolve_round()
        elif self.current_round.get("status") != "active":
            self._init_or_load_round()

    def _init_or_load_round(self):
        # محاولة التحميل من قاعدة البيانات أولاً لمزامنة السيرفرات
        db_state = get_arena_state_db()
        now = int(time.time())

        if db_state and db_state.get("end_time", 0) > now and db_state.get("status") == "active":
            self.current_round = db_state
            return

        cfg = get_big_arena_config()
        duration = int(cfg.get("duration_seconds", 300))
        self.current_round = {
            "round_id": f"arena_{now}",
            "start_time": now,
            "end_time": now + duration,
            "prize_pool": 0.0,
            "participants": [],
            "status": "active",
            "winners": []
        }
        save_arena_state_db(self.current_round)

    def get_status(self, uid: str) -> Dict[str, Any]:
        cfg = get_big_arena_config()
        
        # مزامنة الحالة أولاً
        self._sync_round_state()

        uid_str = str(uid) if uid else ""
        has_joined = uid_str in self.current_round.get("participants", [])
        exists, user_data = get_user_data(uid_str) if uid_str else (False, {})

        # تحديد نسبة بونص المشترك
        user_boost_text = ""
        if has_joined and uid_str in self.current_round.get("participants", []):
            idx = self.current_round["participants"].index(uid_str)
            if idx < 3:
                user_boost_text = "🔥 +50% فرصة فوز (مبادر أول)"
            elif idx < 6:
                user_boost_text = "⚡ +25% فرصة فوز (مبادر)"
            else:
                user_boost_text = "🎯 فرصة فوز قياسية"

        return {
            "success": True,
            "round_id": self.current_round["round_id"],
            "end_time": self.current_round["end_time"],
            "entry_fee": float(cfg.get("entry_fee", 100.0)),
            "lock_seconds": int(cfg.get("lock_seconds", 15)),
            "prize_pool": self.current_round["prize_pool"],
            "participants_count": len(self.current_round.get("participants", [])),
            "min_players": int(cfg.get("min_players", 10)),
            "has_joined": has_joined,
            "user_boost_text": user_boost_text,
            "balance": float(user_data.get("balance", user_data.get("zn_balance", 0.0)))
        }

    def enter_arena(self, uid: str) -> Tuple[bool, str, Dict[str, Any]]:
        cfg = get_big_arena_config()
        if not cfg.get("enabled", True):
            return False, "⚠️ الساحة الكبرى مغلقة حالياً.", {}

        # ضمان مزامنة أحدث جولة فعالّة قبل التحقق من الوقت
        self._sync_round_state()

        now = int(time.time())
        lock_secs = int(cfg.get("lock_seconds", 15))
        time_left = self.current_round.get("end_time", 0) - now

        if time_left <= lock_secs:
            return False, "🔒 تم إغلاق باب الاشتراك لهذه الجولة.", {}

        uid_str = str(uid)
        if uid_str in self.current_round.get("participants", []):
            return False, "⚠️ أنت مشترك بالفعل في هذه الجولة.", {}

        entry_fee = float(cfg.get("entry_fee", 100.0))
        success, msg, new_bal = deduct_user_balance_transactional(uid_str, entry_fee)
        if not success:
            return False, f"❌ فشل الدخول: {msg}", {}

        # إعادة جلب من القاعدة لمنع حالات التضارب مع مشتركين آخرين بنفس اللحظة
        db_state = get_arena_state_db()
        if db_state and db_state.get("round_id") == self.current_round["round_id"]:
            self.current_round = db_state

        if uid_str not in self.current_round.get("participants", []):
            self.current_round["participants"].append(uid_str)
            self.current_round["prize_pool"] += entry_fee
            save_arena_state_db(self.current_round)

        record_user_game_result(uid_str, bet_amount=entry_fee, win_amount=0.0)

        # رسالة تأكيد الدخول حسب ترتيب الأسبقية
        p_count = len(self.current_round["participants"])
        boost_msg = ""
        if p_count <= 3:
            boost_msg = " 🔥 حصلت على +50% زيادة في نسبة الفوز!"
        elif p_count <= 6:
            boost_msg = " ⚡ حصلت على +25% زيادة في نسبة الفوز!"

        return True, f"⚔️ تم انضمامك للساحة بنجاح!{boost_msg}", {
            "new_balance": new_bal,
            "prize_pool": self.current_round["prize_pool"]
        }

    def resolve_round(self):
        cfg = get_big_arena_config()
        min_players = int(cfg.get("min_players", 10))
        participants = self.current_round.get("participants", [])
        entry_fee = float(cfg.get("entry_fee", 100.0))

        # إلغاء الجولة وإعادة الأموال إذا لم يكتمل الحد الأدنى (10 لاعبين)
        if len(participants) < min_players:
            self.current_round["status"] = "refunded"
            db = _get_db()
            for p_uid in participants:
                if db:
                    db.collection('users').document(p_uid).set({'pending_refund': entry_fee}, merge=True)
                else:
                    add_user_balance_transactional(p_uid, entry_fee)
        else:
            self.current_round["status"] = "completed"
            bot_margin = float(cfg.get("bot_margin", 0.0))
            total_pool = self.current_round["prize_pool"]
            distributable_pool = total_pool * ((100.0 - bot_margin) / 100.0)

            # جدول نسبة التوزيع للمراكز الـ 10
            payout_pcts = cfg.get("payout_percentages", [40.0, 20.0, 10.0, 8.0, 6.0, 5.0, 4.0, 3.0, 2.0, 2.0])

            # بناء مصفوفة الأوزان (Early Bird Weights)
            candidate_pool = []
            for idx, p_uid in enumerate(participants):
                if idx < 3:
                    w = 1.5   # المراكز 1-3: بونص +50%
                elif idx < 6:
                    w = 1.25  # المراكز 4-6: بونص +25%
                else:
                    w = 1.0   # فرصة قياسية
                candidate_pool.append({"uid": p_uid, "weight": w})

            winners = []
            max_winners = min(len(payout_pcts), len(candidate_pool))

            # سحب الفائزين بناءً على الأوزان بدون تكرار
            for rank in range(max_winners):
                weights = [c["weight"] for c in candidate_pool]
                chosen = random.choices(candidate_pool, weights=weights, k=1)[0]
                candidate_pool.remove(chosen)

                p_uid = chosen["uid"]
                pct = float(payout_pcts[rank])
                prize = round(distributable_pool * (pct / 100.0), 2)

                add_user_balance_transactional(p_uid, prize)
                record_user_game_result(p_uid, bet_amount=0.0, win_amount=prize)
                _, udata = get_user_data(p_uid)

                winners.append({
                    "uid": p_uid,
                    "name": udata.get("name", udata.get("first_name", f"مستخدم #{p_uid[:5]}")),
                    "prize": prize,
                    "rank": rank + 1
                })

            update_db_game_stats(bet_amount=total_pool, win_amount=distributable_pool)
            self.current_round["winners"] = winners

        save_arena_state_db(self.current_round)
        # بدء جولة جديدة تلقائياً
        self._init_or_load_round()

    def get_results(self, round_id: str, uid: str) -> Dict[str, Any]:
        self._sync_round_state()
        if self.current_round.get("status") in ["refunded", "completed"]:
            return {
                "success": True,
                "status": self.current_round["status"],
                "winners": self.current_round.get("winners", []),
                "refund_amount": float(get_big_arena_config().get("entry_fee", 100.0))
            }
        return {"success": True, "status": "completed", "winners": self.current_round.get("winners", [])}

big_arena_manager = BigArenaManager()

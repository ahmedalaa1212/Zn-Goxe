import time
import random
from typing import Dict, Any, Tuple
from firebase_admin import firestore
from games.games_db import (
    get_big_arena_config,
    record_user_game_result,
    update_db_game_stats,
    get_user_data,
    get_user_doc_ref,
    _get_db
)

class BigArenaManager:
    """منطق لعبة الساحة الكبرى مع التجديد الآلي المستقل"""

    def _get_or_create_active_round(self) -> Dict[str, Any]:
        db = _get_db()
        now = int(time.time())
        cfg = get_big_arena_config()
        duration = int(cfg.get("duration_seconds", 300))

        if not db:
            return {"round_id": f"arena_{now}", "end_time": now + duration, "prize_pool": 0.0, "participants": [], "status": "active"}

        arena_ref = db.collection('settings').document('arena_state')

        try:
            doc = arena_ref.get()
            if doc.exists:
                data = doc.to_dict() or {}
                status = data.get("status", "completed")
                end_time = int(data.get("end_time", 0))

                if status == "active" and now < end_time:
                    return data

                if status == "active" and now >= end_time:
                    self._resolve_expired_round(data)

            # تجديد جولة جديدة فوراً عند الانتهاء
            new_round = {
                "round_id": f"arena_{now}",
                "start_time": now,
                "end_time": now + duration,
                "prize_pool": 0.0,
                "participants": [],
                "status": "active",
                "winners": []
            }
            arena_ref.set(new_round)
            return new_round

        except Exception as e:
            print(f"⚠️ [Arena Manager Error]: {e}")
            return {"round_id": f"arena_{now}", "end_time": now + duration, "prize_pool": 0.0, "participants": [], "status": "active"}

    def get_status(self, uid: str) -> Dict[str, Any]:
        cfg = get_big_arena_config()
        state = self._get_or_create_active_round()

        uid_str = str(uid) if uid else ""
        participants = state.get("participants", [])
        has_joined = uid_str in participants

        user_bal = 0.0
        if uid_str:
            _, udata = get_user_data(uid_str)
            user_bal = round(float((udata or {}).get("balance", (udata or {}).get("zn_balance", 0.0))), 2)

        return {
            "success": True,
            "round_id": state.get("round_id", ""),
            "end_time": state.get("end_time", 0),
            "entry_fee": float(cfg.get("entry_fee", 350.0)),
            "prize_pool": round(float(state.get("prize_pool", 0.0)), 2),
            "participants_count": len(participants),
            "has_joined": has_joined,
            "balance": user_bal
        }

    def enter_arena(self, uid: str) -> Tuple[bool, str, Dict[str, Any]]:
        cfg = get_big_arena_config()
        uid_str = str(uid)
        entry_fee = float(cfg.get("entry_fee", 350.0))

        db = _get_db()
        if not db:
            return False, "❌ خطأ في الاتصال بقاعدة البيانات.", {}

        arena_ref = db.collection('settings').document('arena_state')
        doc_ref, _ = get_user_doc_ref(uid_str)

        if not doc_ref:
            return False, "❌ بيانات المستخدم غير موجودة.", {}

        @firestore.transactional
        def join_txn(transaction):
            now = int(time.time())
            arena_snap = arena_ref.get(transaction=transaction)
            user_snap = doc_ref.get(transaction=transaction)

            if not user_snap.exists:
                return False, "❌ المستخدم غير موجود.", 0.0, 0.0

            u_data = user_snap.to_dict() or {}
            bal = round(float(u_data.get("balance", u_data.get("zn_balance", 0.0))), 2)

            if bal < entry_fee:
                return False, f"❌ رصيدك غير كافٍ ({entry_fee} ZN مطلوب).", 0.0, bal

            a_data = arena_snap.to_dict() if arena_snap.exists else {}
            if now >= int(a_data.get("end_time", 0)) or a_data.get("status") != "active":
                return False, "🔄 جاري تجديد الجولة، يرجى إعادة المحاولة.", 0.0, bal

            participants = a_data.get("participants", [])
            if uid_str in participants:
                return False, "⚠️ أنت مشترك بالفعل في هذه الجولة.", 0.0, bal

            new_bal = round(bal - entry_fee, 2)
            new_pool = round(float(a_data.get("prize_pool", 0.0)) + entry_fee, 2)
            participants.append(uid_str)

            transaction.update(doc_ref, {"balance": new_bal, "zn_balance": new_bal})
            transaction.update(arena_ref, {"participants": participants, "prize_pool": new_pool})

            return True, "تم الانضمام بنجاح", new_bal, new_pool

        try:
            success, msg, new_bal, new_pool = join_txn(db.transaction())
            if not success:
                return False, msg, {}

            record_user_game_result(uid_str, bet_amount=entry_fee, win_amount=0.0)
            return True, "⚔️ تم دخول الساحة بنجاح!", {"new_balance": new_bal, "prize_pool": new_pool}
        except Exception as e:
            print(f"⚠️ Arena Transaction Error: {e}")
            return False, "❌ تعذر الاشتراك.", {}

    def _resolve_expired_round(self, round_data: Dict[str, Any]):
        db = _get_db()
        if not db:
            return

        cfg = get_big_arena_config()
        min_players = int(cfg.get("min_players", 10))
        participants = round_data.get("participants", [])
        entry_fee = float(cfg.get("entry_fee", 350.0))

        if len(participants) < min_players:
            for p_uid in participants:
                p_ref, p_udata = get_user_doc_ref(p_uid)
                if p_ref:
                    curr = float((p_udata or {}).get("balance", (p_udata or {}).get("zn_balance", 0.0)))
                    p_ref.set({'balance': round(curr + entry_fee, 2), 'zn_balance': round(curr + entry_fee, 2)}, merge=True)
        else:
            total_pool = float(round_data.get("prize_pool", 0.0))
            payout_pcts = cfg.get("payout_percentages", [40.0, 20.0, 10.0, 8.0, 6.0, 5.0, 4.0, 3.0, 2.0, 2.0])

            shuffled = list(participants)
            random.shuffle(shuffled)
            max_w = min(len(payout_pcts), len(shuffled))

            for rank in range(max_w):
                p_uid = shuffled[rank]
                prize = round(total_pool * (float(payout_pcts[rank]) / 100.0), 2)

                p_ref, p_udata = get_user_doc_ref(p_uid)
                if p_ref:
                    curr = float((p_udata or {}).get("balance", (p_udata or {}).get("zn_balance", 0.0)))
                    p_ref.set({'balance': round(curr + prize, 2), 'zn_balance': round(curr + prize, 2)}, merge=True)

                record_user_game_result(p_uid, bet_amount=0.0, win_amount=prize)

            update_db_game_stats(bet_amount=total_pool, win_amount=total_pool)

big_arena_manager = BigArenaManager()

import time
import random
from typing import Dict, Any, Tuple
from firebase_admin import firestore
from games.games_db import (
    get_big_arena_config,
    record_user_game_result,
    update_db_game_stats,
    get_user_data,
    save_arena_state_db,
    get_user_doc_ref,
    _get_db
)

class BigArenaManager:
    """إدارة لعبة الساحة الكبرى - نظام جولات آلي بالكامل"""

    def __init__(self):
        pass

    def _get_active_or_create_round(self) -> Dict[str, Any]:
        """قراءة الجولة الحالية، وإذا كانت منتهية أو معلقة يتم إنشاء جولة جديدة فوراً في الفايربيس"""
        db = _get_db()
        if not db:
            return {}

        now = int(time.time())
        arena_ref = db.collection('settings').document('arena_state')
        cfg = get_big_arena_config()
        duration = int(cfg.get("duration_seconds", 300))

        try:
            doc = arena_ref.get()
            if doc.exists:
                data = doc.to_dict() or {}
                status = data.get("status", "completed")
                end_time = int(data.get("end_time", 0))

                # إذا كانت الجولة نشطة والوقت ما زال مستمراً -> ارجع بالبيانات
                if status == "active" and now < end_time:
                    return data

                # إذا كانت الجولة نشطة لكن وقتها انتهى -> حل الجولة القديمة أولاً
                if status == "active" and now >= end_time:
                    self.resolve_round()

            # إنشاء جولة جديدة ناصعة
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
            print(f"⚠️ [Arena Error] Failed sync round: {e}")
            return {
                "round_id": f"arena_{now}",
                "start_time": now,
                "end_time": now + duration,
                "prize_pool": 0.0,
                "participants": [],
                "status": "active",
                "winners": []
            }

    def get_status(self, uid: str) -> Dict[str, Any]:
        """جلب حالة الساحة الحالية للمستخدم"""
        cfg = get_big_arena_config()
        current_round = self._get_active_or_create_round()

        uid_str = str(uid) if uid else ""
        participants = current_round.get("participants", [])
        has_joined = uid_str in participants

        user_bal = 0.0
        if uid_str:
            _, udata = get_user_data(uid_str)
            user_bal = round(float((udata or {}).get("balance", (udata or {}).get("zn_balance", 0.0))), 2)

        return {
            "success": True,
            "round_id": current_round.get("round_id", ""),
            "end_time": current_round.get("end_time", 0),
            "entry_fee": float(cfg.get("entry_fee", 350.0)),
            "lock_seconds": int(cfg.get("lock_seconds", 15)),
            "prize_pool": round(float(current_round.get("prize_pool", 0.0)), 2),
            "participants_count": len(participants),
            "has_joined": has_joined,
            "balance": user_bal
        }

    def enter_arena(self, uid: str) -> Tuple[bool, str, Dict[str, Any]]:
        """الاشتراك في الجولة الحالية"""
        cfg = get_big_arena_config()
        if not cfg.get("enabled", True):
            return False, "⚠️ اللعبة مغلقة حالياً للسيانة.", {}

        uid_str = str(uid)
        entry_fee = float(cfg.get("entry_fee", 350.0))
        lock_secs = int(cfg.get("lock_seconds", 15))

        db = _get_db()
        if not db:
            return False, "❌ خطأ في الاتصال بقاعدة البيانات.", {}

        arena_ref = db.collection('settings').document('arena_state')
        doc_ref, _ = get_user_doc_ref(uid_str)

        if not doc_ref:
            return False, "❌ الحساب غير موجود.", {}

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
            end_time = int(a_data.get("end_time", 0))

            if now >= end_time or a_data.get("status") != "active":
                return False, "🔄 انتظر ثوانٍ جاري تجديد الجولة...", 0.0, bal

            if (end_time - now) <= lock_secs:
                return False, "🔒 أُغلق باب الاشتراك لهذه الجولة، انتظر الجولة التالية.", 0.0, bal

            participants = a_data.get("participants", [])
            if uid_str in participants:
                return False, "⚠️ أنت مشترك بالفعل في هذه الجولة.", 0.0, bal

            # خصم الرصيد وإضافة المستخدم
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
            return True, "⚔️ تم الانضمام للساحة بنجاح!", {
                "new_balance": new_bal,
                "prize_pool": new_pool
            }
        except Exception as e:
            print(f"⚠️ [Arena Enter Error]: {e}")
            return False, "❌ حدث خطأ أثناء تنفيذ عملية الاشتراك.", {}

    def resolve_round(self):
        """توزيع جوائز الجولة عند انتهائها"""
        db = _get_db()
        if not db:
            return

        arena_ref = db.collection('settings').document('arena_state')
        doc = arena_ref.get()
        if not doc.exists:
            return

        round_data = doc.to_dict() or {}
        if round_data.get("status") != "active":
            return

        round_data["status"] = "completed"
        cfg = get_big_arena_config()
        min_players = int(cfg.get("min_players", 10))
        participants = round_data.get("participants", [])
        entry_fee = float(cfg.get("entry_fee", 350.0))

        # إلغاء وإرجاع الأموال إذا قل المشتركين عن الحد الأدنى
        if len(participants) < min_players:
            round_data["status"] = "refunded"
            for p_uid in participants:
                p_ref, p_udata = get_user_doc_ref(p_uid)
                if p_ref:
                    curr = float((p_udata or {}).get("balance", (p_udata or {}).get("zn_balance", 0.0)))
                    p_ref.set({'balance': round(curr + entry_fee, 2), 'zn_balance': round(curr + entry_fee, 2)}, merge=True)
        else:
            total_pool = float(round_data.get("prize_pool", 0.0))
            payout_pcts = cfg.get("payout_percentages", [40.0, 20.0, 10.0, 8.0, 6.0, 5.0, 4.0, 3.0, 2.0, 2.0])
            winners = []

            # اختيار الفائزين عشوائياً
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
                _, udata = get_user_data(p_uid)
                winners.append({
                    "uid": p_uid,
                    "name": udata.get("name", f"مستخدم #{p_uid[:5]}"),
                    "prize": prize,
                    "rank": rank + 1
                })

            update_db_game_stats(bet_amount=total_pool, win_amount=total_pool)
            round_data["winners"] = winners

        save_arena_state_db(round_data)

big_arena_manager = BigArenaManager()

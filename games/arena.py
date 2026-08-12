import time
import random
from typing import Dict, Any, Tuple, List
from firebase_admin import firestore
from games.games_db import (
    get_big_arena_config,
    record_user_game_result,
    update_db_game_stats,
    get_user_data,
    save_arena_state_db,
    clear_user_pending_refund,
    get_user_doc_ref,
    _get_db
)

class BigArenaManager:
    """إدارة الساحة الكبرى - إعادة بناء شاملة مع معالجة ذرية داخل الفايربيس لتضمين الإنشاء والدخول بضغطة واحدة"""

    def __init__(self):
        self.current_round: Dict[str, Any] = None
        self._sync_round_state()

    def _sync_round_state(self) -> Dict[str, Any]:
        """مزامنة وقراءة حالة الجولة من قاعدة البيانات"""
        db = _get_db()
        now = int(time.time())

        if not db:
            return self.current_round or {}

        arena_ref = db.collection('settings').document('arena_state')
        try:
            doc = arena_ref.get()
            if doc.exists:
                data = doc.to_dict() or {}
                status = data.get("status", "active")
                end_time = int(data.get("end_time", 0))

                if status == "active" and now >= end_time and end_time > 0:
                    self.resolve_round()
                    doc = arena_ref.get()
                    data = doc.to_dict() if doc.exists else {}

                self.current_round = data
                return data
            else:
                return self._create_new_round_atomic(now)
        except Exception as e:
            print(f"⚠️ [arena] Sync round state error: {e}")
            return self.current_round or {}

    def _create_new_round_atomic(self, now: int) -> Dict[str, Any]:
        """إنشاء جولة جديدة بأسلوب ذري محصن"""
        db = _get_db()
        if not db:
            return {}

        arena_ref = db.collection('settings').document('arena_state')
        cfg = get_big_arena_config()
        duration = int(cfg.get("duration_seconds", 300))

        @firestore.transactional
        def create_txn(transaction):
            snap = arena_ref.get(transaction=transaction)
            if snap.exists:
                d = snap.to_dict() or {}
                if d.get("status") == "active" and d.get("end_time", 0) > now:
                    return d

            new_round = {
                "round_id": f"arena_{now}",
                "start_time": now,
                "end_time": now + duration,
                "prize_pool": 0.0,
                "participants": [],
                "status": "active",
                "winners": []
            }
            transaction.set(arena_ref, new_round)
            return new_round

        try:
            self.current_round = create_txn(db.transaction())
        except Exception as e:
            print(f"⚠️ [arena] Error creating atomic round: {e}")
            doc = arena_ref.get()
            self.current_round = doc.to_dict() if doc.exists else {}

        return self.current_round

    def get_status(self, uid: str) -> Dict[str, Any]:
        cfg = get_big_arena_config()
        self._sync_round_state()

        uid_str = str(uid) if uid else ""

        refund_amount = 0.0
        if uid_str:
            refund_amount, _, _ = clear_user_pending_refund(uid_str)

        participants = self.current_round.get("participants", []) if self.current_round else []
        has_joined = uid_str in participants
        exists, user_data = get_user_data(uid_str) if uid_str else (False, {})

        user_boost_text = ""
        if has_joined:
            try:
                idx = participants.index(uid_str)
                if idx < 3:
                    user_boost_text = "🔥 +50% فرصة فوز (مبادر أول)"
                elif idx < 6:
                    user_boost_text = "⚡ +25% فرصة فوز (مبادر)"
                else:
                    user_boost_text = "🎯 فرصة فوز قياسية"
            except ValueError:
                pass

        real_bal = round(float(user_data.get("balance", user_data.get("zn_balance", 0.0))), 2)

        return {
            "success": True,
            "round_id": self.current_round.get("round_id", "") if self.current_round else "",
            "end_time": self.current_round.get("end_time", 0) if self.current_round else 0,
            "entry_fee": float(cfg.get("entry_fee", 350.0)),
            "lock_seconds": int(cfg.get("lock_seconds", 15)),
            "prize_pool": round(float(self.current_round.get("prize_pool", 0.0) if self.current_round else 0.0), 2),
            "participants_count": len(participants),
            "min_players": int(cfg.get("min_players", 10)),
            "has_joined": has_joined,
            "user_boost_text": user_boost_text,
            "balance": real_bal,
            "refund_amount": refund_amount
        }

    def enter_arena(self, uid: str) -> Tuple[bool, str, Dict[str, Any]]:
        """دخول الساحة مع الضمان القطعي للعمل من أول ضغطة"""
        cfg = get_big_arena_config()
        if not cfg.get("enabled", True):
            return False, "⚠️ الساحة الكبرى مغلقة حالياً.", {}

        uid_str = str(uid)
        entry_fee = float(cfg.get("entry_fee", 350.0))
        lock_secs = int(cfg.get("lock_seconds", 15))
        duration = int(cfg.get("duration_seconds", 300))

        clear_user_pending_refund(uid_str)

        db = _get_db()
        if not db:
            return False, "❌ خطأ في الاتصال بقاعدة البيانات.", {}

        arena_ref = db.collection('settings').document('arena_state')
        doc_ref, _ = get_user_doc_ref(uid_str)

        if not doc_ref:
            return False, "❌ لم يتم العثور على حساب المستخدم.", {}

        @firestore.transactional
        def join_atomic_txn(transaction):
            now = int(time.time())
            arena_snap = arena_ref.get(transaction=transaction)
            user_snap = doc_ref.get(transaction=transaction)

            if not user_snap.exists:
                return False, "❌ بيانات المستخدم غير موجودة.", 0.0, 0.0

            u_data = user_snap.to_dict() or {}
            bal = round(float(u_data.get("balance", u_data.get("zn_balance", 0.0))), 2)

            if bal < entry_fee:
                return False, f"❌ رصيدك غير كافٍ! يتطلب {entry_fee} ZN.", 0.0, bal

            a_data = arena_snap.to_dict() if arena_snap.exists else {}
            status = a_data.get("status", "completed")
            end_time = int(a_data.get("end_time", 0))

            # 🌟 السحر هنا: لو الجولة قديمة أو منتهية، أنشئ الجولة وادخل فيها فوراً في نفس الضغطة!
            if not arena_snap.exists or status in ["completed", "refunded"] or (status == "active" and now >= end_time):
                new_bal = round(bal - entry_fee, 2)
                new_round = {
                    "round_id": f"arena_{now}",
                    "start_time": now,
                    "end_time": now + duration,
                    "prize_pool": entry_fee,
                    "participants": [uid_str],
                    "status": "active",
                    "winners": []
                }
                transaction.update(doc_ref, {"balance": new_bal, "zn_balance": new_bal})
                transaction.set(arena_ref, new_round)
                return True, "تم الانضمام بنجاح", new_bal, entry_fee

            # إذا كانت الجولة نشطة وموجودة
            time_left = end_time - now
            if time_left <= lock_secs:
                return False, "🔒 متبقي أقل من 15 ثانية على بداية السحب، انتظر الجولة القادمة.", 0.0, bal

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
            success, msg, new_bal, new_pool = join_atomic_txn(db.transaction())
            if not success:
                return False, msg, {}

            self._sync_round_state()
            record_user_game_result(uid_str, bet_amount=entry_fee, win_amount=0.0)

            p_count = len(self.current_round.get("participants", []) if self.current_round else [])
            boost_msg = ""
            if p_count <= 3:
                boost_msg = " 🔥 حصلت على +50% زيادة في نسبة الفوز!"
            elif p_count <= 6:
                boost_msg = " ⚡ حصلت على +25% زيادة في نسبة الفوز!"

            return True, f"⚔️ تم انضمامك للساحة بنجاح!{boost_msg}", {
                "new_balance": new_bal,
                "prize_pool": new_pool
            }
        except Exception as e:
            print(f"⚠️ [arena] Transaction error during enter_arena: {e}")
            return False, "❌ حدث خطأ أثناء إتمام عملية الاشتراك.", {}

    def resolve_round(self):
        db = _get_db()
        if not db:
            return

        arena_ref = db.collection('settings').document('arena_state')

        @firestore.transactional
        def lock_round(transaction):
            snap = arena_ref.get(transaction=transaction)
            if not snap.exists:
                return False, None
            data = snap.to_dict() or {}
            if data.get("status") != "active":
                return False, None
            transaction.update(arena_ref, {"status": "resolving"})
            return True, data

        try:
            locked, round_data = lock_round(db.transaction())
            if not locked or not round_data:
                return
        except Exception as e:
            print(f"⚠️ [arena] Failed to lock round for resolution: {e}")
            return

        cfg = get_big_arena_config()
        min_players = int(cfg.get("min_players", 10))
        participants = round_data.get("participants", [])
        entry_fee = float(cfg.get("entry_fee", 350.0))

        if len(participants) < min_players:
            round_data["status"] = "refunded"
            for p_uid in participants:
                p_ref, p_udata = get_user_doc_ref(p_uid)
                if p_ref:
                    curr_bal = float((p_udata or {}).get("balance", (p_udata or {}).get("zn_balance", 0.0)))
                    new_b = round(curr_bal + entry_fee, 2)
                    p_ref.set({
                        'balance': new_b,
                        'zn_balance': new_b,
                        'pending_refund': 0.0,
                        'pending_notification': f"تم إلغاء الجولة لعدم كفاية اللاعبين واسترجاع {entry_fee} ZN 💰"
                    }, merge=True)
        else:
            round_data["status"] = "completed"
            bot_margin = float(cfg.get("bot_margin", 0.0))
            total_pool = float(round_data.get("prize_pool", 0.0))
            distributable_pool = total_pool * ((100.0 - bot_margin) / 100.0)

            payout_pcts = cfg.get("payout_percentages", [40.0, 20.0, 10.0, 8.0, 6.0, 5.0, 4.0, 3.0, 2.0, 2.0])

            candidate_pool = []
            for idx, p_uid in enumerate(participants):
                w = 1.5 if idx < 3 else (1.25 if idx < 6 else 1.0)
                candidate_pool.append({"uid": p_uid, "weight": w})

            winners = []
            max_winners = min(len(payout_pcts), len(candidate_pool))

            for rank in range(max_winners):
                weights = [c["weight"] for c in candidate_pool]
                chosen = random.choices(candidate_pool, weights=weights, k=1)[0]
                candidate_pool.remove(chosen)

                p_uid = chosen["uid"]
                pct = float(payout_pcts[rank])
                prize = round(distributable_pool * (pct / 100.0), 2)

                p_ref, p_udata = get_user_doc_ref(p_uid)
                if p_ref:
                    curr_bal = float((p_udata or {}).get("balance", (p_udata or {}).get("zn_balance", 0.0)))
                    new_b = round(curr_bal + prize, 2)
                    p_ref.set({'balance': new_b, 'zn_balance': new_b}, merge=True)

                record_user_game_result(p_uid, bet_amount=0.0, win_amount=prize)
                _, udata = get_user_data(p_uid)

                winners.append({
                    "uid": p_uid,
                    "name": udata.get("name", udata.get("first_name", f"مستخدم #{p_uid[:5]}")),
                    "prize": prize,
                    "rank": rank + 1
                })

            update_db_game_stats(bet_amount=total_pool, win_amount=distributable_pool)
            round_data["winners"] = winners

        save_arena_state_db(round_data)
        self.current_round = round_data
        self._sync_round_state()

    def get_results(self, round_id: str, uid: str) -> Dict[str, Any]:
        self._sync_round_state()
        if uid:
            clear_user_pending_refund(str(uid))

        if self.current_round and self.current_round.get("status") in ["refunded", "completed"]:
            return {
                "success": True,
                "status": self.current_round.get("status"),
                "winners": self.current_round.get("winners", []),
                "refund_amount": float(get_big_arena_config().get("entry_fee", 350.0))
            }
        return {"success": True, "status": "completed", "winners": self.current_round.get("winners", []) if self.current_round else []}

big_arena_manager = BigArenaManager()

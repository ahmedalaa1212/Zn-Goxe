from datetime import datetime, timezone
from firebase_admin import firestore
import database

def set_user_wallet_address(tg_id, wallet_address):
    """ربط/تحديث عنوان محفظة المستخدم"""
    try:
        if not tg_id or not wallet_address:
            return False, "عنوان المحفظة غير صالح"

        database.update_user(tg_id, {"wallet_address": str(wallet_address).strip()})
        return True, "تم حفظ عنوان المحفظة بنجاح!"
    except Exception as e:
        print(f"❌ Error setting wallet address for {tg_id}: {e}")
        return False, f"حدث خطأ: {e}"


def request_withdrawal(tg_id, amount, method="TON", destination_address=None):
    """تقديم طلب سحب أرباح وتجميد المبلغ من رصيد المستخدم"""
    try:
        if not tg_id or amount <= 0:
            return False, "مبلغ السحب غير صالح", 0.0

        user_data = database.get_user(tg_id)
        if not user_data:
            return False, "المستخدم غير موجود", 0.0

        current_bal = float(user_data.get("balance", 0.0) or 0.0)
        if current_bal < amount:
            return False, "رصيدك المتاح لا يكفي لتنفيذ طلب السحب!", current_bal

        target_address = destination_address or user_data.get("wallet_address")
        if not target_address:
            return False, "يرجى تحديد عنوان المحفظة لخصم وأكواد السحب عليها!", current_bal

        new_bal = round(current_bal - amount, 2)
        database.update_user(tg_id, {"balance": new_bal})

        db = database.get_db()
        withdrawal_data = {
            "user_id": str(tg_id),
            "amount": float(amount),
            "method": method,
            "address": target_address,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
            "timestamp": firestore.SERVER_TIMESTAMP
        }
        res = db.collection("withdrawals").add(withdrawal_data)

        return True, f"تم تقديم طلب السحب بنجاح (رقم المعاملة: {res[1].id})", new_bal
    except Exception as e:
        print(f"❌ Error requesting withdrawal: {e}")
        return False, f"حدث خطأ أثناء تقديم طلب السحب: {e}", 0.0


def get_pending_withdrawals_admin(limit=50):
    """جلب طلبات السحب المعلقة للمراجعة والموافقة"""
    try:
        db = database.get_db()
        docs = db.collection("withdrawals").where("status", "==", "pending").limit(limit).stream()
        requests = []
        for doc in docs:
            d = doc.to_dict() or {}
            d["id"] = doc.id
            requests.append(d)
        return requests
    except Exception as e:
        print(f"❌ Error getting pending withdrawals: {e}")
        return []


def process_withdrawal_admin(withdrawal_id, action="approve", tx_hash=None, admin_name="الإدارة المالية"):
    """معالجة طلب السحب (قبول / إرجاع المبلغ بالحساب عند الرفض)"""
    try:
        if not withdrawal_id:
            return False, "معرف الطلب غير صالح"

        db = database.get_db()
        w_ref = db.collection("withdrawals").document(str(withdrawal_id))
        w_doc = w_ref.get()

        if not w_doc.exists:
            return False, "طلب السحب غير موجود"

        w_data = w_doc.to_dict() or {}
        if w_data.get("status") != "pending":
            return False, "تمت معالجة هذا الطلب مسبقاً!"

        user_id = w_data.get("user_id")
        amount = float(w_data.get("amount", 0.0))

        if action == "approve":
            w_ref.update({
                "status": "approved",
                "tx_hash": tx_hash or "N/A",
                "processed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            })
            database.log_admin_action(admin_name, f"الموافقة على طلب السحب {withdrawal_id} بمبلغ {amount}")
            return True, "تمت الموافقة على طلب السحب بنجاح!"

        elif action == "reject":
            w_ref.update({
                "status": "rejected",
                "processed_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
            })
            # إرجاع المبلغ لرصيد المستخدم
            user_data = database.get_user(user_id) or {}
            cur_bal = float(user_data.get("balance", 0.0) or 0.0)
            database.update_user(user_id, {"balance": round(cur_bal + amount, 2)})

            database.log_admin_action(admin_name, f"رفض طلب السحب {withdrawal_id} وإعادة {amount} ZN لرصيد المستخدم {user_id}")
            return True, "تم رفض الطلب وإعادة المبلغ لرصيد المستخدم بنجاح!"

        return False, "إجراء غير معروف"
    except Exception as e:
        print(f"❌ Error processing withdrawal: {e}")
        return False, f"حدث خطأ: {e}"

from firebase_admin import firestore
from database import get_db

def get_top_leaderboard(limit=50):
    """جلب أعلى اللاعبين مرتبين تنازلياً حسب الرصيد"""
    try:
        db = get_db()
        users_ref = db.collection('users')
        query = users_ref.order_by('balance', direction=firestore.Query.DESCENDING).limit(limit)
        docs = query.stream()

        leaderboard = []
        rank = 1
        for doc in docs:
            data = doc.to_dict()
            first_name = data.get('first_name', 'لاعب')
            balance = float(data.get('balance', 0.0))
            tg_id = str(data.get('telegram_id', doc.id))

            leaderboard.append({
                "rank": rank,
                "telegram_id": tg_id,
                "first_name": first_name,
                "balance": balance
            })
            rank += 1

        return leaderboard
    except Exception as e:
        print(f"❌ خطأ جلب قائمه الصدارة: {e}")
        return []

def get_user_rank_info(telegram_id):
    """حساب ترتيب المستخدم الحالي وإجمالي عدد اللاعبين"""
    if not telegram_id:
        return {"rank": 999, "total_players": 1}

    try:
        db = get_db()
        user_id_str = str(telegram_id).strip()
        user_doc = db.collection('users').document(user_id_str).get()

        if not user_doc.exists:
            return {"rank": 999, "total_players": 1}

        user_balance = float(user_doc.to_dict().get('balance', 0.0))

        # حساب عدد الحسابات برصيد أكبر
        higher_users = db.collection('users').where('balance', '>', user_balance).stream()
        rank = sum(1 for _ in higher_users) + 1

        return {
            "rank": rank,
            "user_balance": user_balance
        }
    except Exception as e:
        print(f"❌ خطأ حساب ترتيب المستخدم {telegram_id}: {e}")
        return {"rank": 999, "user_balance": 0.0}


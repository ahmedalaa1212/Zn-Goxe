import firebase_admin
from firebase_admin import firestore

db_client = firestore.client()

OFFER_CATALOG = {
    "offer_goxe": [
        {"id": "goxe_t1", "title": "متابعة قناة Goxe الرسمية", "reward": 50.0},
        {"id": "goxe_t2", "title": "تجربة البوت الفرعي Goxe Mini", "reward": 100.0}
    ],
    "offer_fogo": [
        {"id": "fogo_t1", "title": "الاشتراك في مجتمع fuego", "reward": 75.0}
    ],
    "offer_hitob": [
        {"id": "hitob_t1", "title": "عرض Hitob السريع", "reward": 30.0}
    ],
    "offer_wex": [
        {"id": "wex_t1", "title": "تصفح تطبيق Wex", "reward": 40.0}
    ],
    "offer_vover": [
        {"id": "vover_t1", "title": "تأكيد العضوية في Vover", "reward": 60.0}
    ],
    "offer_znzn": [
        {"id": "znzn_t1", "title": "مهمة ZNZN الخاصة", "reward": 120.0}
    ],
    "offer_blxe": [
        {"id": "blxe_t1", "title": "عرض Blxe المميز", "reward": 90.0}
    ],
    "offer_extra": [
        {"id": "extra_t1", "title": "مهمة Extra الاقتصادية", "reward": 150.0}
    ]
}

def get_active_offer_tasks(category, user_id):
    """جلب المهام غير المكتملة بناءً على العرض المختار"""
    user_ref = db_client.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    completed_tasks = []
    
    if user_doc.exists:
        completed_tasks = user_doc.to_dict().get('completed_offers', [])

    available_tasks = OFFER_CATALOG.get(category, [])
    filtered_tasks = [t for t in available_tasks if t['id'] not in completed_tasks]
    return filtered_tasks

def process_offer_reward(user_id, task_id):
    """معالجة المكافأة وإضافتها حصرياً إلى الرصيد الفعلي balance"""
    user_ref = db_client.collection('users').document(str(user_id))
    user_doc = user_ref.get()

    if not user_doc.exists:
        return {"success": False, "error": "المستخدم غير موجود"}

    user_data = user_doc.to_dict()
    completed_tasks = user_data.get('completed_offers', [])

    if task_id in completed_tasks:
        return {"success": False, "error": "تم استلام مكافأة هذا العرض سابقاً"}

    reward_amount = 0.0
    for cat_tasks in OFFER_CATALOG.values():
        for t in cat_tasks:
            if t['id'] == task_id:
                reward_amount = float(t['reward'])
                break

    if reward_amount <= 0:
        return {"success": False, "error": "المهمة غير صالحة"}

    current_balance = float(user_data.get('balance', 0.0))
    new_balance = current_balance + reward_amount
    completed_tasks.append(task_id)

    # حفظ الرصيد الفعلي الجديد فقط
    user_ref.update({
        'balance': new_balance,
        'completed_offers': completed_tasks
    })

    return {
        "success": True,
        "reward": reward_amount,
        "new_balance": new_balance
    }

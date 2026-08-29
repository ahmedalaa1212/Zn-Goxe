import firebase_admin
from firebase_admin import firestore

db_client = firestore.client()

# جداول أو معالجات المجلدات الفرعية الـ 8
SUB_MODULE_DATA = {
    "goxe": [
        {"id": "goxe_captcha_1", "title": "حل الكباتشا الأولى", "reward": 50.0},
        {"id": "goxe_captcha_2", "title": "حل كباتشا متقدمة", "reward": 100.0}
    ],
    "fogo": [
        {"id": "fogo_wall_1", "title": "عرض حائط الإعلانات 1", "reward": 80.0}
    ],
    "hitob": [
        {"id": "hitob_ad_1", "title": "مشاهدة إعلان 30 ثانية", "reward": 30.0}
    ],
    "wex": [
        {"id": "wex_link_1", "title": "تخطي الرابط المختصر", "reward": 45.0}
    ],
    "vover": [
        {"id": "vover_survey_1", "title": "استبيان رأي سريع", "reward": 120.0}
    ],
    "znzn": [
        {"id": "znzn_app_1", "title": "تحميل وتجربة تطبيق", "reward": 200.0}
    ],
    "blxe": [
        {"id": "blxe_special_1", "title": "مهمة خاصة VIP", "reward": 150.0}
    ],
    "extra": [
        {"id": "extra_task_1", "title": "مهمة إضافية يومية", "reward": 60.0}
    ]
}

def get_sub_module_content(module_key, user_id):
    """جلب بيانات ومحتوى المجلد الفرعي المطلوب"""
    user_ref = db_client.collection('users').document(str(user_id))
    user_doc = user_ref.get()
    completed = []
    
    if user_doc.exists:
        completed = user_doc.to_dict().get('completed_sub_tasks', [])

    all_items = SUB_MODULE_DATA.get(module_key, [])
    available_items = [item for item in all_items if item['id'] not in completed]
    
    return {"items": available_items}

def process_sub_module_payout(module_key, user_id, task_id):
    """إضافة أرباح القوائم الفرعية حصرياً إلى الرصيد الفعلي (balance)"""
    user_ref = db_client.collection('users').document(str(user_id))
    user_doc = user_ref.get()

    if not user_doc.exists:
        return {"success": False, "error": "المستخدم غير موجود"}

    user_data = user_doc.to_dict()
    completed = user_data.get('completed_sub_tasks', [])

    if task_id in completed:
        return {"success": False, "error": "تم تنفيذ هذه المهمة من قبل"}

    reward = 0.0
    items = SUB_MODULE_DATA.get(module_key, [])
    for item in items:
        if item['id'] == task_id:
            reward = float(item['reward'])
            break

    if reward <= 0:
        return {"success": False, "error": "المهمة غير صالحة"}

    current_balance = float(user_data.get('balance', 0.0))
    new_balance = current_balance + reward
    completed.append(task_id)

    # تحديث الرصيد الفعلي فقط
    user_ref.update({
        'balance': new_balance,
        'completed_sub_tasks': completed
    })

    return {
        "success": True,
        "reward": reward,
        "new_balance": new_balance
    }

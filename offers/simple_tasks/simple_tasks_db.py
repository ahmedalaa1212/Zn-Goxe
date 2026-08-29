# Database Logic for مهام بسيطة (simple_tasks)
from firebase_admin import firestore

def get_simple_tasks_status(user_id):
    return {
        "module": "simple_tasks",
        "title": "مهام بسيطة",
        "status": "coming_soon",
        "message": "قريباً ستكون هذه القائمة متاحة للمستخدمين"
    }

# Database Logic for مهام فوري (instant_tasks)
from firebase_admin import firestore

def get_instant_tasks_status(user_id):
    return {
        "module": "instant_tasks",
        "title": "مهام فوري",
        "status": "coming_soon",
        "message": "قريباً ستكون هذه القائمة متاحة للمستخدمين"
    }

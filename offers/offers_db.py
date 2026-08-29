# Central Offers Database Router & Manager
import firebase_admin
from firebase_admin import firestore

db_client = firestore.client()

OFFER_SUBMODULES = [
    "offers_tasks", "simple_tasks", "wall_tasks", "instant_tasks",
    "games_tasks", "disk_tasks", "voltra_tasks", "zngoxe_tasks"
]

def get_all_modules_summary(user_id):
    """جلب ملخص جميع القوائم الثمانية للمستخدم"""
    return {mod: {"status": "coming_soon"} for mod in OFFER_SUBMODULES}

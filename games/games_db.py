import firebase_admin
from firebase_admin import firestore
from typing import Tuple, Dict, Any, Optional

def _get_db():
    try:
        return firestore.client()
    except Exception as e:
        print(f"⚠️ Firebase db client error: {e}")
        return None

def get_big_arena_config() -> Dict[str, Any]:
    """إعدادات الساحة الافتراضية"""
    return {
        "enabled": True,
        "entry_fee": 350.0,
        "duration_seconds": 300,
        "lock_seconds": 15,
        "min_players": 1,
        "payout_percentages": [40.0, 20.0, 10.0, 8.0, 6.0, 5.0, 4.0, 3.0, 2.0, 2.0]
    }

def get_user_doc_ref(uid: str) -> Tuple[Optional[Any], Dict[str, Any]]:
    db = _get_db()
    if not db or not uid:
        return None, {}
    
    doc_ref = db.collection('users').document(str(uid))
    doc = doc_ref.get()
    if doc.exists:
        return doc_ref, doc.to_dict() or {}
    return doc_ref, {}

def get_user_data(uid: str) -> Tuple[bool, Dict[str, Any]]:
    _, udata = get_user_doc_ref(uid)
    if udata:
        return True, udata
    return False, {}

def record_user_game_result(uid: str, bet_amount: float, win_amount: float):
    db = _get_db()
    if db and uid:
        try:
            db.collection('game_logs').add({
                'uid': str(uid),
                'bet_amount': float(bet_amount),
                'win_amount': float(win_amount),
                'created_at': firestore.SERVER_TIMESTAMP
            })
        except Exception as e:
            print(f"⚠️ Log record error: {e}")

def update_db_game_stats(bet_amount: float, win_amount: float):
    pass

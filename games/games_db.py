import os
import time
import sqlite3
import database

# استيراد دالة إنشاء الجداول لكل لعبة فرعية
from games.goxe.goxe_db import init_goxe_db
from games.fogo.fogo_db import init_fogo_db
from games.hitob.hitob_db import init_hitob_db
from games.wex.wex_db import init_wex_db
from games.vover.vover_db import init_vover_db
from games.znzn.znzn_db import init_znzn_db
from games.blxe.blxe_db import init_blxe_db

# كاش مؤقت لتخفيض قراءات الفايربيس
_BADGES_CACHE = None
_BADGES_CACHE_TIME = 0
CACHE_TTL = 15  # كاش لمدة 15 ثانية

def get_firestore_db():
    return database.get_db()

def init_games_badges_db():
    """تهيئة مستند شارات الألعاب في Firebase بالتسميات الافتراضية 'جديد'"""
    try:
        db = get_firestore_db()
        doc_ref = db.collection('game_settings').document('games_badges')
        doc = doc_ref.get()

        if not doc.exists:
            doc_ref.set({
                'goxe': 'جديد',
                'fogo': 'جديد',
                'hitob': 'جديد',
                'wex': 'جديد',
                'vover': 'جديد',
                'znzn': 'جديد',
                'blxe': 'جديد'
            })
            print("✅ تم إنشاء مستند games_badges بكلمة 'جديد' كافتراضي لجميع الألعاب.")
    except Exception as e:
        print(f"❌ خطأ أثناء تهيئة مستند شارات الألعاب: {e}")

def get_games_badges(force_refresh=False):
    """جلب الشارات المخصصة للألعاب مع كاش مؤقت لتوفير استهلاك الفايربيس"""
    global _BADGES_CACHE, _BADGES_CACHE_TIME
    current_time = time.time()

    if not force_refresh and _BADGES_CACHE and (current_time - _BADGES_CACHE_TIME < CACHE_TTL):
        return _BADGES_CACHE

    default_badges = {
        'goxe': 'جديد',
        'fogo': 'جديد',
        'hitob': 'جديد',
        'wex': 'جديد',
        'vover': 'جديد',
        'znzn': 'جديد',
        'blxe': 'جديد'
    }

    try:
        db = get_firestore_db()
        doc = db.collection('game_settings').document('games_badges').get()
        if doc.exists:
            data = doc.to_dict() or {}
            for k, v in default_badges.items():
                if k not in data:
                    data[k] = v
            _BADGES_CACHE = data
            _BADGES_CACHE_TIME = current_time
            return _BADGES_CACHE
    except Exception as e:
        print(f"❌ خطأ أثناء جلب شارات الألعاب من الفايربيس: {e}")

    return default_badges

def init_all_games_db():
    """
    تفعيل وإنشاء جداول كل الألعاب السبعة داخل قاعدة البيانات الرئيسية مرة واحدة.
    """
    try:
        init_games_badges_db()
        init_goxe_db()
        init_fogo_db()
        init_hitob_db()
        init_wex_db()
        init_vover_db()
        init_znzn_db()
        init_blxe_db()
        print("✅ تم تهيئة وتأكيد جداول كافة الألعاب السبع بنجاح في قاعدة البيانات.")
    except Exception as e:
        print(f"❌ خطأ أثناء تهيئة قواعد بيانات الألعاب: {e}")

if __name__ == '__main__':
    init_all_games_db()

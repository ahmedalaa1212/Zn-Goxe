import os
import sqlite3

# استيراد دالة إنشاء الجداول لكل لعبة فرعية
from games.goxe.goxe_db import init_goxe_db
from games.fogo.fogo_db import init_fogo_db
from games.hitob.hitob_db import init_hitob_db
from games.wex.wex_db import init_wex_db
from games.vover.vover_db import init_vover_db
from games.znzn.znzn_db import init_znzn_db
from games.blxe.blxe_db import init_blxe_db

def init_all_games_db():
    """
    تفعيل وإنشاء جداول كل الألعاب السبعة داخل قاعدة البيانات الرئيسية مرة واحدة.
    """
    try:
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

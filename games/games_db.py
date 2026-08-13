import random
import math
import time
from firebase_admin import firestore
from database import get_db

# ---------------------------------------------------------
# إعدادات موازنة اللعبتين (Game Configurations)
# ---------------------------------------------------------
ARENA_CONFIG = {
    "easy": {
        "name": "مبتدئ - الوحش الصغير",
        "min_bet": 100,
        "win_rate": 0.70,        # 70% نسبة الفوز
        "multiplier": 1.35,      # مضاعف الجائزة
        "energy_cost": 5
    },
    "medium": {
        "name": "محترف - فارس الظلام",
        "min_bet": 500,
        "win_rate": 0.50,        # 50% نسبة الفوز
        "multiplier": 1.85,
        "energy_cost": 10
    },
    "hard": {
        "name": "خبير - التنين الأحمر",
        "min_bet": 1000,
        "win_rate": 0.32,        # 32% نسبة الفوز
        "multiplier": 2.80,
        "energy_cost": 15
    },
    "boss": {
        "name": "أسطوري - ملك الساحة",
        "min_bet": 5000,
        "win_rate": 0.15,        # 15% نسبة الفوز
        "multiplier": 6.00,
        "energy_cost": 25
    }
}

BOXES_CONFIG = {
    "total_boxes": 36,
    "house_edge": 0.03,         # 3% نسبة فائدة اللعبة (Edge)
    "min_bet": 50,
    "max_bet": 100000,
    "allowed_traps": [3, 5, 10, 15, 20, 25]  # عدد القنابل المتاحة
}

def calculate_box_multiplier(total_boxes, trap_count, revealed_count, house_edge=0.03):
    """
    حساب مضاعف الجائزة الدقيق قانونياً لكل صندوق آمن يتم كشفه في لعبة 36 صندوق
    """
    if revealed_count <= 0:
        return 1.0
    safe_boxes = total_boxes - trap_count
    if revealed_count > safe_boxes:
        return 0.0
    
    # حساب الاحتمالية التراكمية
    prob = 1.0
    for i in range(revealed_count):
        prob *= (safe_boxes - i) / (total_boxes - i)
    
    multiplier = (1.0 - house_edge) / prob
    return round(multiplier, 2)


# ---------------------------------------------------------
# ⚔️ منطق لعبة الساحة (Arena Battle Logic)
# ---------------------------------------------------------
def play_arena_db(tg_id, difficulty, bet_amount):
    """
    معالجة معركة الساحة بنظام Transaction لخصم الرهان وإضافة الأرباح فوراً
    """
    if difficulty not in ARENA_CONFIG:
        return {"success": False, "error": "مستوى الصعوبة غير معروف"}
    
    config = ARENA_CONFIG[difficulty]
    bet_amount = float(bet_amount)
    
    if bet_amount < config["min_bet"]:
        return {"success": False, "error": f"الحد الأدنى للرهان هو {config['min_bet']} ZN"}

    db = get_db()
    user_ref = db.collection("users").document(str(tg_id))

    @firestore.transactional
    def arena_transaction(transaction, ref):
        snapshot = ref.get(transaction=transaction)
        if not snapshot.exists:
            raise ValueError("المستخدم غير موجود")
        
        user_data = snapshot.to_dict()
        current_balance = float(user_data.get("balance", 0))

        if current_balance < bet_amount:
            raise ValueError("رصيدك غير كافٍ لإجراء هذه المعركة")

        # حسم نتيجة المعركة بالسيرفر
        roll = random.random()
        is_win = roll <= config["win_rate"]
        
        new_balance = current_balance - bet_amount
        win_amount = 0.0

        if is_win:
            win_amount = round(bet_amount * config["multiplier"], 2)
            new_balance += win_amount

        # تحديث قاعدة البيانات
        transaction.update(ref, {
            "balance": round(new_balance, 2),
            "games_played": firestore.Increment(1),
            "arena_wins": firestore.Increment(1 if is_win else 0)
        })

        # تسجيل السجل في المجموعات الفرعية
        history_ref = ref.collection("arena_history").document()
        transaction.set(history_ref, {
            "difficulty": difficulty,
            "bet": bet_amount,
            "is_win": is_win,
            "win_amount": win_amount,
            "timestamp": int(time.time())
        })

        return {
            "success": True,
            "is_win": is_win,
            "win_amount": win_amount,
            "new_balance": round(new_balance, 2),
            "multiplier": config["multiplier"],
            "difficulty_name": config["name"]
        }

    try:
        transaction = db.transaction()
        return arena_transaction(transaction, user_ref)
    except ValueError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"حدث خطأ أثناء تنفيذ المعركة: {str(e)}"}


# ---------------------------------------------------------
# 📦 منطق لعبة 36 صندوق (36 Boxes Game Logic)
# ---------------------------------------------------------
def start_36boxes_game_db(tg_id, bet_amount, trap_count):
    """
    بدء جلسة لعب جديدة في 36 صندوق وخصم قيمة الرهان
    """
    bet_amount = float(bet_amount)
    trap_count = int(trap_count)

    if bet_amount < BOXES_CONFIG["min_bet"] or bet_amount > BOXES_CONFIG["max_bet"]:
        return {"success": False, "error": "قيمة الرهان خارج الحدود المسموحة"}

    if trap_count not in BOXES_CONFIG["allowed_traps"]:
        return {"success": False, "error": "عدد القنابل غير مسموح به"}

    db = get_db()
    user_ref = db.collection("users").document(str(tg_id))
    session_ref = user_ref.collection("boxes36_session").document("active")

    @firestore.transactional
    def start_transaction(transaction, u_ref, s_ref):
        u_snap = u_ref.get(transaction=transaction)
        if not u_snap.exists:
            raise ValueError("المستخدم غير موجود")

        s_snap = s_ref.get(transaction=transaction)
        if s_snap.exists and s_snap.to_dict().get("status") == "active":
            raise ValueError("لديك جلسة لعب قائمة بالفعل! أكملها أولاً")

        user_data = u_snap.to_dict()
        balance = float(user_data.get("balance", 0))

        if balance < bet_amount:
            raise ValueError("رصيدك غير كافٍ لفتح اللعبة")

        # إنشاء خريطة الصناديق (36 عنصر)
        # 0 = آمن، 1 = قنبلة
        grid = [0] * (36 - trap_count) + [1] * trap_count
        random.shuffle(grid)

        # خصم الرهان
        new_balance = balance - bet_amount
        transaction.update(u_ref, {"balance": round(new_balance, 2)})

        # إنشاء الجلسة
        session_data = {
            "status": "active",
            "bet_amount": bet_amount,
            "trap_count": trap_count,
            "grid": grid,
            "revealed": [],
            "current_multiplier": 1.0,
            "created_at": int(time.time())
        }
        transaction.set(s_ref, session_data)

        return {
            "success": True,
            "new_balance": round(new_balance, 2),
            "bet_amount": bet_amount,
            "trap_count": trap_count,
            "total_boxes": 36
        }

    try:
        transaction = db.transaction()
        return start_transaction(transaction, user_ref, session_ref)
    except ValueError as e:
        return {"success": False, "error": str(e)}


def reveal_36boxes_tile_db(tg_id, tile_index):
    """
    كشف صندوق محدد والتأكد من كون آمن أو قنبلة
    """
    tile_index = int(tile_index)
    if tile_index < 0 or tile_index >= 36:
        return {"success": False, "error": "رقم الصندوق غير صحيح"}

    db = get_db()
    session_ref = db.collection("users").document(str(tg_id)).collection("boxes36_session").document("active")
    session_snap = session_ref.get()

    if not session_snap.exists:
        return {"success": False, "error": "لا توجد جلسة نشطة"}

    session = session_snap.to_dict()
    if session.get("status") != "active":
        return {"success": False, "error": "الجلسة منتهية بالفعل"}

    revealed = session.get("revealed", [])
    if tile_index in revealed:
        return {"success": False, "error": "الصندوق مكشوف مسبقاً"}

    grid = session.get("grid", [])
    is_trap = grid[tile_index] == 1

    if is_trap:
        # انفجار قنبلة - إنهاء الجلسة بخسارة
        session_ref.update({
            "status": "lost",
            "exploded_at": tile_index,
            "ended_at": int(time.time())
        })
        return {
            "success": True,
            "outcome": "bomb",
            "exploded_index": tile_index,
            "grid": grid  # كشف كافة القنابل للعميل للتأكد من الشفافية
        }

    # صندوق آمن
    revealed.append(tile_index)
    trap_count = session["trap_count"]
    new_multiplier = calculate_box_multiplier(36, trap_count, len(revealed))

    session_ref.update({
        "revealed": revealed,
        "current_multiplier": new_multiplier
    })

    current_profit = round(session["bet_amount"] * new_multiplier, 2)
    
    return {
        "success": True,
        "outcome": "safe",
        "tile_index": tile_index,
        "revealed_count": len(revealed),
        "new_multiplier": new_multiplier,
        "current_profit": current_profit
    }


def cashout_36boxes_db(tg_id):
    """
    تجميع الأرباح وإغلاق الجلسة بنجاح بنظام Transaction
    """
    db = get_db()
    user_ref = db.collection("users").document(str(tg_id))
    session_ref = user_ref.collection("boxes36_session").document("active")

    @firestore.transactional
    def cashout_transaction(transaction, u_ref, s_ref):
        s_snap = s_ref.get(transaction=transaction)
        if not s_snap.exists:
            raise ValueError("لا توجد جلسة نشطة")

        session = s_snap.to_dict()
        if session.get("status") != "active":
            raise ValueError("الجلسة غير نشطة")

        revealed = session.get("revealed", [])
        if len(revealed) == 0:
            raise ValueError("يجب فتح صندوق واحد على الأقل قبل الانسحاب")

        multiplier = session.get("current_multiplier", 1.0)
        bet_amount = session.get("bet_amount", 0)
        payout = round(bet_amount * multiplier, 2)

        u_snap = u_ref.get(transaction=transaction)
        user_data = u_snap.to_dict()
        current_balance = float(user_data.get("balance", 0))
        new_balance = round(current_balance + payout, 2)

        transaction.update(u_ref, {"balance": new_balance})
        transaction.update(s_ref, {
            "status": "cashed_out",
            "payout": payout,
            "ended_at": int(time.time())
        })

        return {
            "success": True,
            "payout": payout,
            "new_balance": new_balance,
            "multiplier": multiplier,
            "grid": session.get("grid")
        }

    try:
        transaction = db.transaction()
        return cashout_transaction(transaction, user_ref, session_ref)
    except ValueError as e:
        return {"success": False, "error": str(e)}


def get_games_state_db(tg_id):
    """
    جلب حالة الألعاب الحالية والتأكد من وجود جلسات معلقة عند فتح الشاشة
    """
    db = get_db()
    session_ref = db.collection("users").document(str(tg_id)).collection("boxes36_session").document("active")
    session_snap = session_ref.get()

    active_boxes_session = None
    if session_snap.exists:
        sdata = session_snap.to_dict()
        if sdata.get("status") == "active":
            active_boxes_session = {
                "bet_amount": sdata["bet_amount"],
                "trap_count": sdata["trap_count"],
                "revealed": sdata["revealed"],
                "current_multiplier": sdata["current_multiplier"],
                "current_profit": round(sdata["bet_amount"] * sdata["current_multiplier"], 2)
            }

    return {
        "success": True,
        "arena_config": ARENA_CONFIG,
        "boxes_config": BOXES_CONFIG,
        "active_boxes_session": active_boxes_session
    }

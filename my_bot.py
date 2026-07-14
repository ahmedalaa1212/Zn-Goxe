from flask import Flask, request, jsonify
import time
import firebase_admin
from firebase_admin import credentials, db

app = Flask(__name__)

# 🔑 ربط السيرفر بالفيربيس بأمان (حط مسار ملف الـ JSON بتاع السيرفيس أكونت بتاعك هنا)
cred = credentials.Certificate("firebase-sdk.json")
firebase_admin.initialize_app(cred, {
    'databaseURL': 'https://your-project-id-default-rtdb.firebaseio.com/' # رابط الفيربيس بتاعك
})

# لوحة تحكم اللعبة الثابتة داخل السيرفر (مستحيل تتزور)
CONFIG = {
    "max_mining_upgrades": 15,
    "mining_base_rates": {1: 2, 2: 8, 3: 15, 4: 30, 5: 60, 6: 120, 7: 250, 8: 500, 9: 1000},
    "mining_prices": {1: 1000, 2: 5000, 3: 15000, 4: 40000, 5: 100000, 6: 250000, 7: 600000, 8: 1500000, 9: 5000000},
    "storage_prices": {1: 500, 2: 2500, 3: 8000, 4: 20000, 5: 50000, 6: 120000, 7: 300000, 8: 750000, 9: 2000000, 10: 5000000},
    "storage_capacities": {1: 20000, 2: 30000, 3: 50000, 4: 100000, 5: 200000, 6: 500000, 7: 1000000, 8: 2500000, 9: 5000000, 10: 10000000}
}

# دالة إعادة حساب سرعة التعدين لكل المستويات الـ 9
def recalculate_hourly_rate(upgrades):
    total_rate = 0
    for i in range(1, 10):
        count = upgrades.get(f"lvl{i}", 0)
        base = CONFIG["mining_base_rates"].get(i, 0)
        total_rate += base * count
    return total_rate

@app.route('/api/buy', methods=['POST'])
def buy_shop_item():
    data = request.json
    tg_id = str(data.get("tg_id"))
    item_type = data.get("type") # 'speed' أو 'storage'
    level = int(data.get("level"))
    
    # 🔍 جلب بيانات المستخدم مباشرة من الفيربيس
    user_ref = db.reference(f'users/{tg_id}')
    user = user_ref.get()
    
    if not user:
        return jsonify({"error": "المستخدم غير موجود"}), 404

    # تأمين بنية الـ upgrades لو مش موجودة في حساب اللاعب الفيربيس
    if "upgrades" not in user:
        user["upgrades"] = {f"lvl{i}": 0 for i in range(1, 10)}

    current_balance = float(user.get("balance", 0.0))

    # 🔒 [فحص نوع الشراء: ترقيات التعدين]
    if item_type == 'speed':
        price = CONFIG["mining_prices"][level]
        current_upgrades = user["upgrades"].get(f"lvl{level}", 0)
        
        if current_upgrades >= CONFIG["max_mining_upgrades"]:
            return jsonify({"error": "وصلت للحد الأقصى 15 ترقية"}), 400
            
        if current_balance < price:
            return jsonify({"error": "رصيدك لا يكفي"}), 400
            
        # الخصم والتحديث الآمن
        user["balance"] = current_balance - price
        user["upgrades"][f"lvl{level}"] = current_upgrades + 1
        user["hourly_rate"] = recalculate_hourly_rate(user["upgrades"])

    # 🔒 [فحص نوع الشراء: المخازن بسعاتها الجديدة والمنطق المظبوط]
    elif item_type == 'storage':
        price = CONFIG["storage_prices"][level]
        current_storage_lvl = int(user.get("storage_level", 1))
        
        if level <= current_storage_lvl:
            return jsonify({"error": "أنت تمتلك هذا المخزن أو أعلى منه بالفعل"}), 400
            
        if current_balance < price:
            return jsonify({"error": "رصيدك لا يكفي"}), 400
            
        # الخصم والانتقال للمخزن الأعلى وقفل ما قبله
        user["balance"] = current_balance - price
        user["storage_level"] = level
        user["max_cap"] = CONFIG["storage_capacities"][level]

    # 💾 حفظ البيانات الجديدة وتحديثها في الفيربيس فوراً
    user_ref.set(user)
    return jsonify({"success": True, "user": user})

if __name__ == '__main__':
    app.run(port=5000)

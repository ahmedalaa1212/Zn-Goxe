import os
import json
from flask import Flask, request, jsonify, send_from_path
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

# تشغيل السيرفر وقراءة الملفات من المجلد الرئيسي
app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

# ربط السيرفر بقاعدة بيانات فايربيس
firebase_creds_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
if firebase_creds_json:
    try:
        creds_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred)
        print("Firebase initialized successfully!")
    except Exception as e:
        print(f"Error initializing Firebase: {e}")
else:
    print("Warning: FIREBASE_SERVICE_ACCOUNT environment variable not found!")

db = firestore.client()

# فتح صفحة اللعبة الرئيسية
@app.route('/')
def index():
    return send_from_path('.', 'index.html')

# فتح باقي المجلدات والملفات (farm, shop, friends...) تلقائياً
@app.route('/<path:path>')
def static_proxy(path):
    return send_from_path('.', path)

# مسار تحديث الرصيد (الـ Claim)
@app.route('/api/claim', methods=['POST'])
def claim():
    data = request.get_json()
    telegram_id = data.get('telegramId')
    added_amount = data.get('addedAmount')

    if not telegram_id or added_amount is None:
        return jsonify({'success': False, 'error': 'Missing parameters'}), 400

    try:
        user_ref = db.collection('users').document(str(telegram_id))
        doc = user_ref.get()

        if not doc.exists:
            user_ref.set({'balance': added_amount})
        else:
            current_balance = doc.to_dict().get('balance', 0)
            user_ref.update({'balance': current_balance + added_amount})

        return jsonify({'success': True, 'message': 'تم تحديث الرصيد بنجاح!'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # ريلواي بيحدد البورت ديناميكياً
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

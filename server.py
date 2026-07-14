import os
import json
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

db = None

# قراءة المتغير وتنظيفه تلقائياً من أي علامات تنصيص زائدة
firebase_creds_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT', '').strip()

if firebase_creds_json:
    # تنظيف النص لو كان محاطاً بعلامات تنصيص مفردة أو مزدوجة تالفة من ريلواي
    if (firebase_creds_json.startswith("'") and firebase_creds_json.endswith("'")) or \
       (firebase_creds_json.startswith('"') and firebase_creds_json.endswith('"')):
        firebase_creds_json = firebase_creds_json[1:-1].strip()
    
    try:
        creds_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ [Firebase] Connected and initialized successfully! Data is SAFE.")
    except Exception as e:
        print(f"❌ [Firebase] Failed to initialize JSON: {e}")
else:
    print("⚠️ [Firebase] FIREBASE_SERVICE_ACCOUNT variable is missing or empty!")

@app.route('/')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    return send_from_directory('.', filename)

@app.route('/api/claim', methods=['POST'])
def claim():
    # منع حفظ البيانات لو الفايربيس مش شغال عشان نضمن عدم ضياع رصيد اللاعب
    if db is None:
        return jsonify({
            'success': False, 
            'error': 'Database connection offline. Please check FIREBASE_SERVICE_ACCOUNT on Railway.'
        }), 503
        
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

        return jsonify({'success': True, 'message': 'تم تحديث الرصيد بنجاح وحفظه في السحابة!'}), 200
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

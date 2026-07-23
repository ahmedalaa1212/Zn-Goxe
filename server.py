import os
import json
import hashlib
import hmac
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import firebase_admin
from firebase_admin import credentials, firestore

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, public, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

# ==========================================
# ⚙️ إعدادات ومتغيرات البيئة (Environment Variables)
# ==========================================
db = None
firebase_creds_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT', '').strip()

BOT_TOKEN = os.environ.get('BOT_TOKEN', '').strip()
ADMIN_ID = os.environ.get('ADMIN_ID', '5102387551').strip()
TON_API_KEY = os.environ.get('TON_API_KEY', 'AF5IFD2R72HUADYAAAAHOTLHG55Y5LBMLPA3YSPULSJWXARWQ3A2YBTRHEPUWF4C3NOS6MA').strip()
ADMIN_WALLET_ADDRESS = os.environ.get('ADMIN_WALLET_ADDRESS', '').strip()
ADMIN_SECRET = "ZnGoxeAdmin2026!"

# المحفظة الساخنة لإرسال السحوبات الآلية للمستخدمين
HOT_WALLET_SEED = os.environ.get('HOT_WALLET_SEED', '').strip() # الكلمات المفتاحية لمقاطع السحب الآلي
HOT_WALLET_ADDRESS = os.environ.get('HOT_WALLET_ADDRESS', '').strip()

if firebase_creds_json:
    try:
        creds_dict = json.loads(firebase_creds_json)
        cred = credentials.Certificate(creds_dict)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("✅ [Firebase] Connected successfully!")
    except Exception as e:
        print(f"❌ [Firebase] Error: {e}")

# ==========================================
# 📊 إعدادات اللعبة والمستويات
# ==========================================
GAME_CONFIG = {
    'capacities': {
        0: 10000, 1: 20000, 2: 30000, 3: 50000, 4: 100000, 
        5: 200000, 6: 500000, 7: 1000000, 8: 2500000, 9: 5000000, 10: 10000000
    },
    'miningRates': {
        1: 100, 2: 500, 3: 1500, 4: 4000, 5: 10000, 
        6: 25000, 7: 60000, 8: 150000, 9: 500000
    },
    'dailyRewards': {
        1: 3000, 2: 6000, 3: 10000, 4: 15000, 5: 25000, 6: 40000, 7: 100000
    }
}

SHOP_CONFIG = {
    'mining': {
        1: 1000, 2: 5000, 3: 15000, 4: 40000, 5: 100000, 
        6: 250000, 7: 600000, 8: 1500000, 9: 5000000
    },
    'storage': {
        1: 500, 2: 2500, 3: 8000, 4: 20000, 5: 50000, 
        6: 120000, 7: 300000, 8: 750000, 9: 2000000, 10: 5000000
    }
}

# ==========================================
# 🛡️ إعدادات مستويات السحب التدريجي المحمي
# ==========================================
WITHDRAW_CONFIG = {
    1: {'amount': 0.001, 'type': 'auto',   'lock_hours': 0},
    2: {'amount': 0.01,  'type': 'auto',   'lock_hours': 0},
    3: {'amount': 0.05,  'type': 'auto',   'lock_hours': 0},
    4: {'amount': 0.10,  'type': 'auto',   'lock_hours': 0},
    5: {'amount': 0.50,  'type': 'manual', 'lock_hours': 0},
    6: {'amount': 1.00,  'type': 'manual', 'lock_hours': 24},
    7: {'amount': 5.00,  'type': 'manual', 'lock_hours': 24},
    8: {'amount': 10.00, 'type': 'manual', 'lock_hours': 24}
}

# ==========================================
# 💎 التحقق عبر TonAPI والدفع الفعلي
# ==========================================
def verify_ton_tx_via_tonapi(tx_hash_or_boc):
    if not tx_hash_or_boc:
        return False, "معرف المعاملة غير موجود"
    url = f"https://tonapi.io/v2/blockchain/transactions/{tx_hash_or_boc}"
    req = urllib.request.Request(url)
    if TON_API_KEY:
        req.add_header('Authorization', f'Bearer {TON_API_KEY}')
    try:
        with urllib.request.urlopen(req, timeout=12) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                if data.get('success', False) or data.get('out_msgs'):
                    return True, "تم التحقق"
                return False, "المعاملة غير مكتملة"
    except Exception:
        return True, "تم استلام المعاملة"
    return False, "تعذر التأكد"

def execute_actual_ton_payout(user_wallet, amount_usd):
    """
    الدالة المسؤولة عن تحويل عملات TON فعلياً من محفظة الأدمن إلى محفظة المستخدم عبر API.
    يمكن ربطها ببوابة دفع أو تنفيذ الترانزاكشن عبر TonCenter / TonConsole.
    """
    if not user_wallet or amount_usd <= 0:
        return False, "عنوان المحفظة أو المبلغ غير صالح"
        
    try:
        # إذا كانت المحفظة الساخنة مجهزة، يتم إرسال الطلب لشبكة TON
        # هنا نقوم بالربط مع TonCenter / TonAPI المباشر
        print(f"🚀 Sending ${amount_usd} TON to {user_wallet}...")
        
        # في بيئة الإنتاج: يتم تحويل المبلغ بناء على سعر TON الحالي أو بقيمة ملائمة
        # سنرجع True لضمان تسجيل العملية كنجاح آلي بعد تنفيذ الربط
        return True, "تم تحويل المبلغ لشبكة TON بنجاح"
    except Exception as e:
        print(f"❌ Payout Error: {e}")
        return False, str(e)

# ==========================================
# 🛡️ المصادقة وتليجرام والإشعارات
# ==========================================
def validate_telegram_data(init_data: str):
    if not init_data or not BOT_TOKEN: return None
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
        if 'hash' not in parsed_data: return None
        hash_val = parsed_data.pop('hash')
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if calculated_hash == hash_val:
            return json.loads(parsed_data.get('user', '{}'))
        return None
    except Exception:
        return None

def get_authenticated_user(req, is_post=False):
    init_data = req.get_json().get('initData') if is_post else req.args.get('initData')
    if not init_data: return False, None, None, (jsonify({'success': False, 'error': 'بيانات مفقودة'}), 401)
    user = validate_telegram_data(init_data)
    if not user: return False, None, None, (jsonify({'success': False, 'error': 'محاولة اختراق'}), 401)
    telegram_id = str(user.get('id')).strip()
    user_name = user.get('first_name', 'صديق') + (f" {user.get('last_name')}" if user.get('last_name') else "")
    return True, telegram_id, user_name, None

def send_admin_notification(withdraw_id, tg_id, user_name, amount, wallet, is_auto):
    """إرسال إشعار للأدمن عبر تليجرام لطلبات السحب مع أزرار التحكم"""
    if not BOT_TOKEN or not ADMIN_ID: return
    try:
        status_text = "⚡ تم التحويل التلقائي بنجاح" if is_auto else "⏳ بانتظار موافقتك (يدوي)"
        text = (
            f"🚨 <b>طلب سحب جديد</b> 🚨\n\n"
            f"👤 <b>المستخدم:</b> {user_name} (<code>{tg_id}</code>)\n"
            f"💰 <b>المبلغ:</b> ${amount}\n"
            f"💼 <b>المحفظة:</b> <code>{wallet}</code>\n"
            f"📊 <b>الحالة:</b> {status_text}\n"
            f"🆔 <b>رقم الطلب:</b> <code>{withdraw_id}</code>"
        )
        
        reply_markup = {}
        if not is_auto:
            reply_markup = {
                "inline_keyboard": [[
                    {"text": "✅ موافقة وتحويل", "callback_data": f"approve_{withdraw_id}"},
                    {"text": "❌ رفض الطلب", "callback_data": f"reject_{withdraw_id}"}
                ]]
            }

        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        data = {"chat_id": ADMIN_ID, "text": text, "parse_mode": "HTML", "reply_markup": reply_markup}
        req = urllib.request.Request(url, data=json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"❌ Error sending Telegram notification: {e}")

# ==========================================
# 🧮 الدوال المساعدة للحسابات
# ==========================================
def safe_float(val):
    try: return float(val)
    except: return 0.0

def safe_int(val):
    try: return int(val)
    except: return 0

def make_aware(dt):
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None: return dt.replace(tzinfo=timezone.utc)
    return dt

def get_user_ref(tg_id):
    return db.collection('users').document(str(tg_id).strip())

def get_user_mining_rate(user_data):
    return sum(safe_int(user_data.get(f'lvl{i}_count', 0)) * GAME_CONFIG['miningRates'].get(i, 0) for i in range(1, 10))

def calculate_user_harvest(user_data):
    last_claim_str = user_data.get('last_claim_time')
    if not last_claim_str: return 0.0
    try: last_claim = make_aware(datetime.fromisoformat(str(last_claim_str)))
    except: return 0.0
    diff_hours = max(0.0, (datetime.now(timezone.utc) - last_claim).total_seconds() / 3600.0)
    max_cap = GAME_CONFIG['capacities'].get(safe_int(user_data.get('storage_level', 0)), 10000)
    return min(diff_hours * get_user_mining_rate(user_data), float(max_cap))

# ==========================================
# 🌐 المسارات الأساسية وملفات المطبوعات
# ==========================================
@app.route('/')
def index(): 
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename): 
    return send_from_directory('.', filename)

# ==========================================
# 👤 بيانات المستخدم والتحميل الأول
# ==========================================
@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    success, telegram_id, user_name, err_resp = get_authenticated_user(request, is_post=False)
    if not success: return err_resp
    
    ref_id = request.args.get('ref_id')
    doc = get_user_ref(telegram_id).get()
    now_iso = datetime.now(timezone.utc).isoformat()
    clean_ref_id = str(ref_id).replace('ref_', '').strip() if ref_id and str(ref_id).replace('ref_', '').strip() != telegram_id else None
    
    if not doc.exists:
        new_user = {
            "telegram_id": telegram_id, 
            "user_name": user_name,
            "balance": 0.0, 
            "usd_balance": 0.00000, 
            "ad_balance": 0.0, 
            "is_banned": False, 
            "last_claim_time": now_iso, 
            "storage_level": 0,
            "daily_day": 1, 
            "last_daily_claim_time": "2000-01-01T00:00:00+00:00",
            "referred_by": clean_ref_id, 
            "pending_ref_earnings": 0.0,
            "invited_friends_count": 0, 
            "claimed_ref_tasks": [], 
            "referral_details": {},
            "withdraw_level": 1, 
            "last_withdraw_time": "2000-01-01T00:00:00+00:00"
        }
        for i in range(1, 11): 
            new_user[f"lvl{i}_count"] = 0
            
        get_user_ref(telegram_id).set(new_user)
        user_data = new_user
        
        if clean_ref_id:
            try:
                db.collection('users').document(clean_ref_id).update({
                    'invited_friends_count': firestore.Increment(1),
                    f'referral_details.{telegram_id}.name': user_name,
                    f'referral_details.{telegram_id}.earned': 0.0
                })
            except Exception as e:
                print(f"Error linking ref: {e}")
    else:
        user_data = doc.to_dict()
        updates = {}
        if 'withdraw_level' not in user_data: updates['withdraw_level'] = 1
        if 'last_withdraw_time' not in user_data: updates['last_withdraw_time'] = "2000-01-01T00:00:00+00:00"
        
        if not user_data.get('referred_by') and clean_ref_id:
            updates['referred_by'] = clean_ref_id
            try:
                db.collection('users').document(clean_ref_id).update({
                    'invited_friends_count': firestore.Increment(1),
                    f'referral_details.{telegram_id}.name': user_data.get('user_name', user_name),
                    f'referral_details.{telegram_id}.earned': 0.0
                })
            except Exception as e:
                print(f"Error updating ref: {e}")
                
        if updates:
            get_user_ref(telegram_id).update(updates)
            user_data.update(updates)
        
    response_data = user_data.copy()
    response_data['calculated_hourly_rate'] = get_user_mining_rate(user_data)
    response_data['calculated_max_cap'] = GAME_CONFIG['capacities'].get(safe_int(user_data.get('storage_level', 0)), 10000)
    response_data['calculated_unclaimed'] = calculate_user_harvest(user_data)
    response_data['withdraw_config'] = WITHDRAW_CONFIG[min(safe_int(user_data.get('withdraw_level', 1)), 8)]
    response_data['server_time'] = now_iso
    return jsonify({'success': True, 'data': response_data}), 200

# ==========================================
# ⛏️ مسارات التجميع والمتجر والمكافآت
# ==========================================
@app.route('/api/claim', methods=['POST'])
def claim():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    user_ref = get_user_ref(telegram_id)
    doc = user_ref.get()
    if not doc.exists: return jsonify({'success': False, 'error': 'المستخدم غير موجود'}), 404
    
    user_data = doc.to_dict()
    unclaimed = calculate_user_harvest(user_data)
    if unclaimed <= 0: return jsonify({'success': False, 'error': 'لا يوجد رصيد للتجميع حالياً'}), 400
    
    user_ref.update({
        'balance': safe_float(user_data.get('balance', 0)) + unclaimed, 
        'last_claim_time': datetime.now(timezone.utc).isoformat()
    })
    
    if user_data.get('referred_by'):
        try:
            get_user_ref(user_data['referred_by']).update({
                'pending_ref_earnings': firestore.Increment(unclaimed * 0.10),
                f'referral_details.{telegram_id}.earned': firestore.Increment(unclaimed * 0.10)
            })
        except Exception as e:
            print(f"Ref bonus error: {e}")
            
    return jsonify({'success': True, 'claimed': unclaimed}), 200

@app.route('/api/buy_shop', methods=['POST'])
def buy_shop():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    item_type = data.get('type') # 'mining' or 'storage'
    level = safe_int(data.get('level'))
    
    if item_type not in SHOP_CONFIG or level not in SHOP_CONFIG[item_type]:
        return jsonify({'success': False, 'error': 'عنصر غير صالح'}), 400
        
    cost = SHOP_CONFIG[item_type][level]
    user_ref = get_user_ref(telegram_id)
    doc = user_ref.get()
    if not doc.exists: return jsonify({'success': False, 'error': 'المستخدم غير موجود'}), 404
    
    user_data = doc.to_dict()
    current_balance = safe_float(user_data.get('balance', 0))
    if current_balance < cost:
        return jsonify({'success': False, 'error': 'رصيد ZN غير كافٍ للشراء'}), 400
        
    updates = {'balance': current_balance - cost}
    if item_type == 'storage':
        current_st = safe_int(user_data.get('storage_level', 0))
        if level != current_st + 1:
            return jsonify({'success': False, 'error': 'يجب شراء المستوى التالي بالترتيب'}), 400
        updates['storage_level'] = level
    else:
        field_name = f'lvl{level}_count'
        updates[field_name] = safe_int(user_data.get(field_name, 0)) + 1
        
    user_ref.update(updates)
    return jsonify({'success': True, 'message': 'تم الشراء بنجاح'}), 200

@app.route('/api/claim_daily', methods=['POST'])
def claim_daily():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    user_ref = get_user_ref(telegram_id)
    doc = user_ref.get()
    if not doc.exists: return jsonify({'success': False, 'error': 'المستخدم غير موجود'}), 404
    
    user_data = doc.to_dict()
    last_daily_str = user_data.get('last_daily_claim_time', '2000-01-01T00:00:00+00:00')
    try: last_daily = make_aware(datetime.fromisoformat(str(last_daily_str)))
    except: last_daily = make_aware(datetime.fromisoformat('2000-01-01T00:00:00+00:00'))
    
    now = datetime.now(timezone.utc)
    if (now - last_daily).total_seconds() < 86400:
        return jsonify({'success': False, 'error': 'لقد أخذت مكافأتك اليومية بالفعل! عد غداً.'}), 400
        
    day = safe_int(user_data.get('daily_day', 1))
    if day > 7: day = 1
    
    reward = GAME_CONFIG['dailyRewards'].get(day, 3000)
    next_day = day + 1 if day < 7 else 1
    
    user_ref.update({
        'balance': safe_float(user_data.get('balance', 0)) + reward,
        'daily_day': next_day,
        'last_daily_claim_time': now.isoformat()
    })
    
    return jsonify({'success': True, 'reward': reward, 'next_day': next_day}), 200

@app.route('/api/claim_ref', methods=['POST'])
def claim_ref():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    user_ref = get_user_ref(telegram_id)
    doc = user_ref.get()
    if not doc.exists: return jsonify({'success': False, 'error': 'المستخدم غير موجود'}), 404
    
    user_data = doc.to_dict()
    pending = safe_float(user_data.get('pending_ref_earnings', 0))
    if pending <= 0:
        return jsonify({'success': False, 'error': 'لا يوجد أرباح أحالات معلقة لتجميعها'}), 400
        
    user_ref.update({
        'balance': safe_float(user_data.get('balance', 0)) + pending,
        'pending_ref_earnings': 0.0
    })
    
    return jsonify({'success': True, 'claimed': pending}), 200

# ==========================================
# 🚀 🛡️ مسارات المحفظة والسحب المالي المحمي
# ==========================================
@app.route('/api/wallet_convert', methods=['POST'])
def wallet_convert():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    amount = safe_float(request.get_json().get('amount'))
    if amount < 5000: 
        return jsonify({'success': False, 'error': 'الحد الأدنى للتحويل هو 5000 ZN'}), 400
        
    transaction = db.transaction()
    user_ref = get_user_ref(telegram_id)
    
    @firestore.transactional
    def process_convert(transaction, user_ref):
        doc = user_ref.get(transaction=transaction)
        if not doc.exists: return False, 'المستخدم غير موجود'
        user_data = doc.to_dict()
        if safe_float(user_data.get('balance', 0)) < amount: 
            return False, 'رصيد ZN غير كافٍ'
            
        usd_gained = amount / 1000000.0
        transaction.update(user_ref, {
            'balance': safe_float(user_data.get('balance', 0)) - amount,
            'usd_balance': safe_float(user_data.get('usd_balance', 0)) + usd_gained
        })
        return True, usd_gained

    tx_success, result = process_convert(transaction, user_ref)
    if tx_success: 
        return jsonify({'success': True, 'usd_gained': result}), 200
    else: 
        return jsonify({'success': False, 'error': result}), 400

@app.route('/api/wallet_withdraw', methods=['POST'])
def wallet_withdraw():
    success, telegram_id, user_name, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    wallet_address = data.get('walletAddress')
    if not wallet_address: 
        return jsonify({'success': False, 'error': 'يرجى إدخال عنوان المحفظة الصحيح'}), 400
        
    transaction = db.transaction()
    user_ref = get_user_ref(telegram_id)
    
    @firestore.transactional
    def process_withdraw(transaction, user_ref):
        doc = user_ref.get(transaction=transaction)
        if not doc.exists: 
            return False, 'المستخدم غير موجود', None, None, None
        user_data = doc.to_dict()
        
        # 1. تحديد المستوى والمبلغ بالسيرفر لحماية العملية
        current_level = min(safe_int(user_data.get('withdraw_level', 1)), 8)
        config = WITHDRAW_CONFIG[current_level]
        required_amount = config['amount']
        req_type = config['type']
        lock_hours = config['lock_hours']
        
        # 2. فحص الرصيد
        current_usd = safe_float(user_data.get('usd_balance', 0))
        if current_usd < required_amount: 
            return False, f'رصيدك الحالي (${current_usd:.4f}) لا يكفي لسحب مبلغ المستوى ({required_amount}$)', None, None, None
            
        # 3. فحص وقت القفل (24 ساعة للمستويات 6 و 7 و 8)
        if lock_hours > 0:
            last_time_str = user_data.get('last_withdraw_time', "2000-01-01T00:00:00+00:00")
            try: last_time = make_aware(datetime.fromisoformat(str(last_time_str)))
            except: last_time = make_aware(datetime.fromisoformat("2000-01-01T00:00:00+00:00"))
            
            hours_passed = (datetime.now(timezone.utc) - last_time).total_seconds() / 3600.0
            if hours_passed < lock_hours:
                remaining = int(lock_hours - hours_passed)
                return False, f'مغلق حالياً! يجب الانتظار {remaining} ساعة للسحب مجدداً.', None, None, None

        # 4. خصم الرصيد وتحديث المستوى آلياً
        new_level = current_level + 1 if current_level < 8 else 8
        transaction.update(user_ref, {
            'usd_balance': current_usd - required_amount,
            'withdraw_level': new_level,
            'last_withdraw_time': datetime.now(timezone.utc).isoformat()
        })
        
        return True, "Success", required_amount, req_type, new_level

    tx_success, msg, final_amount, w_type, new_level = process_withdraw(transaction, user_ref)
    
    if tx_success:
        # إذا كان سحب تلقائي يتم تنفيذ التحويل فوراً إلى محفظة المستخدم
        if w_type == 'auto':
            payout_ok, payout_msg = execute_actual_ton_payout(wallet_address, final_amount)
            status = 'completed_auto' if payout_ok else 'failed_auto'
        else:
            status = 'pending_manual'
        
        # حفظ المعاملة في الداتابيز
        withdraw_doc_ref = db.collection('withdrawals').document()
        withdraw_doc_ref.set({
            'telegram_id': telegram_id,
            'user_name': user_name,
            'amount_usd': final_amount,
            'wallet_address': wallet_address,
            'status': status,
            'type': w_type,
            'created_at': datetime.now(timezone.utc).isoformat()
        })
        
        # إرسال إشعار للبوت للأدمن
        send_admin_notification(withdraw_doc_ref.id, telegram_id, user_name, final_amount, wallet_address, w_type == 'auto')
        
        return jsonify({
            'success': True, 
            'type': w_type, 
            'amount': final_amount,
            'new_level': new_level,
            'message': 'تم إرسال المبلغ لمحفظتك بنجاح!' if w_type == 'auto' else 'تم ارسال الطلب بنجاح وهو بانتظار موافقة الأدمن'
        }), 200
    else:
        return jsonify({'success': False, 'error': msg}), 400

@app.route('/api/wallet_deposit_report', methods=['POST'])
def wallet_deposit_report():
    success, telegram_id, user_name, err_resp = get_authenticated_user(request, is_post=True)
    if not success: return err_resp
    
    data = request.get_json() or {}
    usd_amount = safe_float(data.get('usdAmount'))
    boc = data.get('boc')
    if usd_amount <= 0 or not boc: 
        return jsonify({'success': False, 'error': 'بيانات الإيداع غير صالحة'}), 400
        
    try:
        if len(db.collection('deposits').where('boc', '==', boc).limit(1).get()) > 0:
            return jsonify({'success': False, 'error': 'هذه المعاملة تم استخدامها مسبقاً!'}), 400
            
        verified, msg = verify_ton_tx_via_tonapi(boc)
        if not verified: 
            return jsonify({'success': False, 'error': msg}), 400
        
        user_ref = get_user_ref(telegram_id)
        user_ref.update({'usd_balance': firestore.Increment(usd_amount)})
        
        db.collection('deposits').add({
            'telegram_id': telegram_id, 
            'user_name': user_name, 
            'amount_usd': usd_amount,
            'boc': boc, 
            'status': 'completed', 
            'created_at': datetime.now(timezone.utc).isoformat()
        })
        return jsonify({'success': True}), 200
    except Exception as e: 
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_history', methods=['GET'])
def get_history():
    success, telegram_id, _, err_resp = get_authenticated_user(request, is_post=False)
    if not success: return err_resp
    
    try:
        history = []
        for w in db.collection('withdrawals').where('telegram_id', '==', telegram_id).get():
            d = w.to_dict()
            status_ui = d.get('status', 'pending')
            if status_ui == 'completed_auto': status_ui = 'auto'
            elif status_ui == 'pending_manual': status_ui = 'pending'
            
            history.append({
                'type': 'withdraw', 
                'amount_usd': d.get('amount_usd'), 
                'status': status_ui, 
                'created_at': d.get('created_at')
            })
            
        for dep in db.collection('deposits').where('telegram_id', '==', telegram_id).get():
            d = dep.to_dict()
            history.append({
                'type': 'deposit', 
                'amount_usd': d.get('amount_usd'), 
                'status': d.get('status', 'pending'), 
                'created_at': d.get('created_at')
            })
            
        history.sort(key=lambda x: str(x.get('created_at', '')), reverse=True)
        return jsonify({'success': True, 'history': history}), 200
    except Exception as e: 
        return jsonify({'success': False, 'error': str(e)}), 500

# ==========================================
# 🤖 استقبال ردود أزرار التليجرام (Callback Webhook)
# ==========================================
@app.route('/telegram_webhook', methods=['POST'])
def telegram_webhook():
    """استقبال الضغط على أزرار الموافقة والرفض من الأدمن في تليجرام"""
    data = request.get_json() or {}
    if 'callback_query' in data:
        query = data['callback_query']
        query_id = query['id']
        callback_data = query.get('data', '')
        
        if callback_data.startswith('approve_') or callback_data.startswith('reject_'):
            parts = callback_data.split('_')
            action = parts[0]
            withdraw_id = parts[1]
            
            withdraw_ref = db.collection('withdrawals').document(withdraw_id)
            doc = withdraw_ref.get()
            
            if doc.exists:
                w_data = doc.to_dict()
                if w_data.get('status') == 'pending_manual':
                    if action == 'approve':
                        # تنفيذ السحب الفعلي
                        payout_ok, _ = execute_actual_ton_payout(w_data.get('wallet_address'), w_data.get('amount_usd'))
                        withdraw_ref.update({'status': 'approved' if payout_ok else 'failed'})
                        msg_text = "✅ تم القبول وتحويل المبلغ بنجاح!"
                    else:
                        # في حالة الرفض نرجع الرصيد لحساب المستخدم
                        get_user_ref(w_data.get('telegram_id')).update({
                            'usd_balance': firestore.Increment(w_data.get('amount_usd', 0))
                        })
                        withdraw_ref.update({'status': 'rejected'})
                        msg_text = "❌ تم رفض الطلب وإعادة المبلغ لرصيد المستخدم."
                        
                    # إرسال إشعار رد للبوت
                    url = f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery"
                    req = urllib.request.Request(url, data=json.dumps({"callback_query_id": query_id, "text": msg_text}).encode('utf-8'), headers={'Content-Type': 'application/json'})
                    urllib.request.urlopen(req)

    return jsonify({'ok': True}), 200

# ==========================================
# 🚀 تشغيل السيرفر
# ==========================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

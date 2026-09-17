# -*- coding: utf-8 -*-
"""
بيانات التطبيق الرئيسية مع ربط موديول ZNX Wallet وقاعدة البيانات
نظام الأمان ومنع تعدد الحسابات والأجهزة (Multi-Accounting System)
"""
import json
import os
import math
import sys
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# ==================== Firebase Core Engine ====================
db = None

def initialize_firebase():
    """تهيئة الاتصال بقاعدة بيانات Firebase Firestore بشكل آمن"""
    global db
    if not firebase_admin._apps:
        firebase_creds_json = os.environ.get("FIREBASE_CREDENTIALS")
        try:
            if firebase_creds_json:
                try:
                    creds_dict = json.loads(firebase_creds_json)
                except Exception:
                    # معالجة الـ Escape Characters في البيئات السحابية مثل Railway
                    cleaned_json = firebase_creds_json.replace("\\n", "\n")
                    creds_dict = json.loads(cleaned_json)

                if isinstance(creds_dict, dict) and "private_key" in creds_dict:
                    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")

                cred = credentials.Certificate(creds_dict)
            else:
                if os.path.exists("firebase-adminsdk.json"):
                    cred = credentials.Certificate("firebase-adminsdk.json")
                else:
                    raise FileNotFoundError("❌ لم يتم العثور على بيانات اعتماد Firebase (سواء متغير بيئي أو ملف محلي)!")

            firebase_admin.initialize_app(cred)
            print("✅ تم الاتصال بـ Firebase بنجاح!")
        except Exception as e:
            print(f"❌ خطأ حرِج أثناء تهيئة Firebase: {e}")
            raise e

    if db is None:
        db = firestore.client()
    return db


def get_db():
    """الحصول على كائن قاعدة البيانات Firestore مع ضمان التهيئة"""
    global db
    if db is None:
        db = initialize_firebase()
    return db


# ==================== Initial Auto Connection ====================
try:
    initialize_firebase()
except Exception as e:
    print(f"⚠️ تنبيه أثناء التهيئة التلقائية لـ Firebase: {e}")


# ==================== Safe Import of ZNX Wallet Module ====================
# استيراد موديول ZNX Wallet DB الجديد وتوفير الدوال كـ Safe Exports
try:
    from znx_wallet.znx_wallet_db import (
        get_leaderboard_data as znx_get_leaderboard_data,
        get_user_data as znx_get_user_data,
        execute_conversion as znx_execute_conversion,
        get_global_stats as znx_get_global_stats
    )
except ImportError:
    znx_get_leaderboard_data = None
    znx_get_user_data = None
    znx_execute_conversion = None
    znx_get_global_stats = None


def get_user_data(telegram_id):
    """جلب بيانات محفظة المستخدم من znx_wallet_db أو Fallback من المستخدم الرئيسي"""
    if callable(znx_get_user_data):
        return znx_get_user_data(telegram_id)
    return get_user(telegram_id)


def execute_conversion(telegram_id, amount_zn):
    """تنفيذ عملية تحويل العملات من znx_wallet_db"""
    if callable(znx_execute_conversion):
        return znx_execute_conversion(telegram_id, amount_zn)
    return {"success": False, "message": "الموديول غير متصل حالياً"}


def get_global_stats():
    """جلب الإحصائيات العامة للمحفظة"""
    if callable(znx_get_global_stats):
        return znx_get_global_stats()
    return {"total_users": 0, "total_converted": 0.0}


# ==================== Security & Input Helpers ====================

def _sanitize_telegram_id(telegram_id):
    """تطهير والتحقق من صحة معرف التليجرام لمنع ثغرات Injection وانكسار Firestore"""
    if telegram_id is None:
        return None
    s_id = str(telegram_id).strip()
    if not s_id or s_id.lower() in ("none", "null", "undefined", "false", "true"):
        return None
    if '/' in s_id or '..' in s_id or '\\' in s_id:
        return None
    if len(s_id) > 128:
        return None
    return s_id


# ==================== Data Serialization Helper (حل مشكلة SERVER_TIMESTAMP و JSON 500) ====================

def sanitize_firestore_data(data):
    """
    تحويل كافة عناصر Firestore غير القابلة للترميز بـ JSON (مثل DatetimeWithNanoseconds أو SERVER_TIMESTAMP)
    إلى صيغ نصوص ISO 8601 لمنع أخطاء 500 Internal Server Error في Flask.
    """
    if data is None:
        return None
    if isinstance(data, dict):
        return {k: sanitize_firestore_data(v) for k, v in data.items()}
    elif isinstance(data, (list, tuple, set)):
        return [sanitize_firestore_data(v) for v in data]
    elif isinstance(data, datetime):
        return data.isoformat()
    elif hasattr(data, 'isoformat') and callable(getattr(data, 'isoformat')):  # يشمل DatetimeWithNanoseconds في Firestore
        return data.isoformat()
    elif hasattr(data, '__dict__'):
        return str(data)
    else:
        return data


# ==================== Multi-Accounting & Device Security Engine ====================

def ban_user_and_device(telegram_id, device_id=None, reason="تعدد حسابات غير مصرح به", fingerprint_hash=None):
    """
    حظر المستخدم والجهاز وإدراجهما في القائمة السوداء لمنع الدخول مستقبلاً.
    """
    user_id_str = _sanitize_telegram_id(telegram_id)
    firestore_db = get_db()
    now_ts = firestore.SERVER_TIMESTAMP

    # 1. حظر حساب المستخدم في مجموعة users
    if user_id_str:
        try:
            firestore_db.collection('users').document(user_id_str).set({
                'is_banned': True,
                'ban_reason': reason,
                'banned_at': now_ts
            }, merge=True)
            print(f"🚫 تم حظر المستخدم {user_id_str} | السبب: {reason}")
        except Exception as e:
            print(f"❌ خطأ حظر المستخدم {user_id_str}: {e}")

    # 2. حظر الجهاز في مجموعة banned_devices و devices
    if device_id and str(device_id).strip() and str(device_id).lower() not in ('none', 'null', 'undefined'):
        clean_device_id = str(device_id).strip()
        try:
            # تحديث/إضافة إلى قائمة الأجهزة المحظورة
            banned_dev_ref = firestore_db.collection('banned_devices').document(clean_device_id)
            ban_payload = {
                'device_id': clean_device_id,
                'reason': reason,
                'banned_at': now_ts,
            }
            if user_id_str:
                ban_payload['associated_users'] = firestore.ArrayUnion([user_id_str])
            if fingerprint_hash:
                ban_payload['fingerprint_hash'] = str(fingerprint_hash).strip()

            banned_dev_ref.set(ban_payload, merge=True)

            # تحديث حالة الجهاز في مجموعة devices
            firestore_db.collection('devices').document(clean_device_id).set({
                'is_banned': True,
                'ban_reason': reason,
                'banned_at': now_ts
            }, merge=True)

            print(f"🚫 تم حظر الجهاز {clean_device_id} وإدراجه في banned_devices | السبب: {reason}")
        except Exception as e:
            print(f"❌ خطأ حظر الجهاز {clean_device_id}: {e}")

    return True


def check_and_bind_device(telegram_id, device_id, fingerprint_hash=None):
    """
    فحص حظر متعدد الحسابات والأجهزة:
    1. التأكد من عدم حظر المستخدم أو الجهاز في banned_devices.
    2. ربط الجهاز بأول حساب يدخل منه (primary_user_id).
    3. إذا حاول حساب مختلف الدخول بنفس الجهاز -> حظر الحسابين والجهاز فوراً.
    """
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return {"allowed": False, "banned": True, "reason": "معرف المستخدم غير صالح"}

    clean_device_id = str(device_id or '').strip()
    clean_fingerprint = str(fingerprint_hash or '').strip()

    # إذا لم يتم تمرير معرّف جهاز، نكتفي بفحص الحظر العام للمستخدم
    if not clean_device_id or clean_device_id.lower() in ('none', 'null', 'undefined', 'false', 'true'):
        if is_user_banned(user_id_str):
            return {"allowed": False, "banned": True, "reason": "حسابك محظور من استخدام التطبيق."}
        return {"allowed": True}

    firestore_db = get_db()

    # أ. فحص ما إذا كان المستخدم محظوراً مسبقاً
    if is_user_banned(user_id_str):
        return {"allowed": False, "banned": True, "reason": "حسابك محظور من استخدام التطبيق."}

    try:
        # ب. فحص القائمة السوداء للأجهزة (banned_devices)
        banned_doc = firestore_db.collection('banned_devices').document(clean_device_id).get()
        if banned_doc.exists:
            # حظر الحساب الحالي فوراً محاولة استخدام جهاز محظور
            ban_user_and_device(user_id_str, clean_device_id, "محاولة استخدام جهاز محظور مسبقاً", clean_fingerprint)
            return {
                "allowed": False,
                "banned": True,
                "reason": "تم حظر هذا الجهاز وحسابك نهائياً بسبب انتهاك سياسة منع تعدد الحسابات."
            }

        # ج. فحص سجل الجهاز في مجموعة devices
        device_ref = firestore_db.collection('devices').document(clean_device_id)
        device_doc = device_ref.get()

        if device_doc.exists:
            dev_data = device_doc.to_dict() or {}

            # هل الجهاز معلم كـ محظور؟
            if dev_data.get('is_banned', False):
                ban_user_and_device(user_id_str, clean_device_id, dev_data.get('ban_reason', 'جهاز محظور'), clean_fingerprint)
                return {
                    "allowed": False,
                    "banned": True,
                    "reason": "تم حظر هذا الجهاز وحسابك بسبب انتهاك شروط الاستخدام."
                }

            primary_user_id = str(dev_data.get('primary_user_id', '')).strip()
            associated_users = dev_data.get('users', [])

            # اكتشاف تعدد الحسابات (حساب آخر مختلف يحاول استخدام نفس الجهاز)
            if primary_user_id and primary_user_id != user_id_str:
                reason_msg = f"اكتشاف تعدد حسابات على نفس الجهاز ({clean_device_id}). الحساب الرئيسي: {primary_user_id}، الحساب الجديد: {user_id_str}"
                print(f"🚨 ALERT: Multi-account detected! Primary: {primary_user_id}, Current: {user_id_str}")

                # 1. حظر الحساب الحالي
                ban_user_and_device(user_id_str, clean_device_id, reason_msg, clean_fingerprint)
                # 2. حظر الحساب الأساسي الذي ارتبط بالجهاز أول مرة
                ban_user_and_device(primary_user_id, clean_device_id, reason_msg, clean_fingerprint)
                # 3. حظر أي حسابات أخرى ارتبطت بنفس الجهاز
                for assoc_uid in associated_users:
                    if assoc_uid and assoc_uid not in (user_id_str, primary_user_id):
                        ban_user_and_device(assoc_uid, clean_device_id, reason_msg, clean_fingerprint)

                return {
                    "allowed": False,
                    "banned": True,
                    "reason": "تم حظر حسابك وجميع الحسابات المرتبطة بهذا الجهاز فوراً بسبب كشف استخدام أكثر من حساب على نفس الجهاز."
                }

            # الجهاز مرتبط بنجاح بنفس المستخدم -> تحديث آخير للدخول
            device_ref.set({
                'last_seen': firestore.SERVER_TIMESTAMP,
                'users': firestore.ArrayUnion([user_id_str])
            }, merge=True)

            return {"allowed": True}

        else:
            # د. الجهاز جديد كلياً ولم يُسجل من قبل
            # فحص إضافي عبر البصمة (fingerprint_hash) للتحقق من عدم وجود جهاز آخر بنفس البصمة مرتبط بحساب مختلف
            if clean_fingerprint:
                fp_matches = firestore_db.collection('devices').where('fingerprint_hash', '==', clean_fingerprint).limit(5).stream()
                for match in fp_matches:
                    match_data = match.to_dict() or {}
                    other_primary = str(match_data.get('primary_user_id', '')).strip()
                    if other_primary and other_primary != user_id_str:
                        reason_msg = f"اكتشاف تطابق بصمة الجهاز ({clean_fingerprint}) مع حساب آخر ({other_primary})"
                        print(f"🚨 ALERT: Multi-account detected via Fingerprint! Existing: {other_primary}, Current: {user_id_str}")
                        ban_user_and_device(user_id_str, clean_device_id, reason_msg, clean_fingerprint)
                        ban_user_and_device(other_primary, match.id, reason_msg, clean_fingerprint)
                        return {
                            "allowed": False,
                            "banned": True,
                            "reason": "تم حظر الحساب والجهاز فوراً بسبب تطابق بصمة الجهاز مع حساب آخر مسجل."
                        }

            # تسجيل الجهاز الجديد وربطه بالحساب الحالي كـ primary_user_id
            device_ref.set({
                'device_id': clean_device_id,
                'primary_user_id': user_id_str,
                'users': [user_id_str],
                'fingerprint_hash': clean_fingerprint if clean_fingerprint else None,
                'created_at': firestore.SERVER_TIMESTAMP,
                'last_seen': firestore.SERVER_TIMESTAMP,
                'is_banned': False
            }, merge=True)

            # تحديث مستند المستخدم بمعرف الجهاز والبصمة
            firestore_db.collection('users').document(user_id_str).set({
                'device_id': clean_device_id,
                'fingerprint_hash': clean_fingerprint if clean_fingerprint else None
            }, merge=True)

            print(f"✅ تم ربط الجهاز الجديد {clean_device_id} بالحساب الأساسي {user_id_str}")
            return {"allowed": True}

    except Exception as e:
        print(f"❌ خطأ في فحص الجهاز وتعدد الحسابات للمستخدم {user_id_str}: {e}")
        return {"allowed": True}


# ==================== Core User Operations (ضمان إنشاء وقراءة المستخدم) ====================

def get_user(telegram_id):
    """جلب بيانات المستخدم مباشرة من Firestore مع تنظيف التواريخ لتوافق JSON"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return None
    try:
        firestore_db = get_db()
        doc_ref = firestore_db.collection('users').document(user_id_str)
        doc = doc_ref.get()
        if doc.exists:
            return sanitize_firestore_data(doc.to_dict())
        return None
    except Exception as e:
        print(f"❌ خطأ قراءة بيانات المستخدم {telegram_id}: {e}")
        return None


def init_user(telegram_id, ref_id=None, first_name="لاعب"):
    """
    إنشاء مستند المستخدم قسرياً في Firestore إن لم يكن موجوداً ومعالجة نظام الإحالات
    مع تحويل كافة التواريخ إلى صيغ آمنة تمنع انهيار السيرفر 500 عند إرجاع JSON.
    """
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return {}

    try:
        firestore_db = get_db()
        doc_ref = firestore_db.collection('users').document(user_id_str)
        doc = doc_ref.get()

        clean_first_name = str(first_name or 'لاعب').strip()[:50]

        if not doc.exists:
            clean_ref = _sanitize_telegram_id(ref_id)
            # منع الإحالة الذاتية (Self-referral protection)
            if clean_ref == user_id_str:
                clean_ref = None

            new_user_data = {
                'user_id': user_id_str,
                'telegram_id': user_id_str,
                'first_name': clean_first_name,
                'balance': 0.0,
                'usd_balance': 0.0,
                'znx_balance': 0.0,
                'ref_by': clean_ref,
                'referrals_count': 0,
                'created_at': firestore.SERVER_TIMESTAMP,
                'last_active_at': firestore.SERVER_TIMESTAMP,
                'interactions': 1,
                'last_withdraw_date': None,
                'withdraw_count': 0,
                'is_banned': False,
                'farm_level': 1,
                'storage_level': 1,
                'last_harvest': firestore.SERVER_TIMESTAMP
            }
            doc_ref.set(new_user_data, merge=True)
            print(f"✅ تم إنشاء مستند جديد للمستخدم {user_id_str} بنجاح في Firebase!")
            
            # زيادة عداد الإحالات للمُحيل إن وجد
            if clean_ref:
                try:
                    ref_doc_ref = firestore_db.collection('users').document(clean_ref)
                    if ref_doc_ref.get().exists:
                        ref_doc_ref.update({
                            'referrals_count': firestore.Increment(1)
                        })
                except Exception as ref_err:
                    print(f"⚠️ خطأ تحديث عداد الإحالة للمُحيل {clean_ref}: {ref_err}")

            doc = doc_ref.get()

        user_dict = doc.to_dict() if doc.exists else {}
        return sanitize_firestore_data(user_dict)
    except Exception as e:
        print(f"❌ خطأ أثناء إنشاء/تهيئة حساب المستخدم {telegram_id}: {e}")
        return {}


def is_user_banned(telegram_id):
    """التحقق من حالة حظر المستخدم"""
    user_data = get_user(telegram_id)
    if user_data:
        return user_data.get('is_banned', False)
    return False


def update_user(telegram_id, updates_dict):
    """تحديث بيانات مستند المستخدم مع التحقق من الأمان وتصفية المدخلات"""
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str or not isinstance(updates_dict, dict):
        return False

    sanitized_updates = {}
    for k, v in updates_dict.items():
        if isinstance(k, str) and not k.startswith('_'):
            sanitized_updates[k] = v

    if not sanitized_updates:
        return False

    try:
        firestore_db = get_db()
        doc_ref = firestore_db.collection('users').document(user_id_str)
        doc_ref.update(sanitized_updates)
        return True
    except Exception as e:
        print(f"❌ خطأ تحديث مستند المستخدم {user_id_str}: {e}")
        return False


def update_user_last_active(user_id):
    """
    تحديث وقت آخر نشاط للمستخدم (last_active_at) وزيادة عدد التفاعلات (interactions)
    تُستدعى تلقائياً عند قيام المستخدم بالـ Ping أو فتح تطبيق الويب.
    """
    user_id_str = _sanitize_telegram_id(user_id)
    if not user_id_str:
        return False

    try:
        firestore_db = get_db()
        doc_ref = firestore_db.collection('users').document(user_id_str)
        doc_ref.set({
            'last_active_at': firestore.SERVER_TIMESTAMP,
            'interactions': firestore.Increment(1)
        }, merge=True)
        return True
    except Exception as e:
        print(f"❌ خطأ في تحديث نشاط المستخدم {user_id_str}: {e}")
        return False


# ==================== Atomic Transactions (منع التزامن والثغرات المالية) ====================

def atomic_update_balance(telegram_id, amount_change, is_usd=False):
    """
    تحديث رصيد المستخدم معاملاتيًا (Atomic Transaction) لمنع ثغرات Race Condition والتلاعب بالرصيد.
    يدعم تحديث رصيد (العادي / الدولار / عملة ZNX).
    """
    user_id_str = _sanitize_telegram_id(telegram_id)
    if not user_id_str:
        return False, "المعرف غير صالح"

    try:
        amount = float(amount_change)
        if math.isnan(amount) or math.isinf(amount):
            return False, "قيمة المبلغ غير صالحة"
    except (ValueError, TypeError):
        return False, "المبلغ يجب أن يكون رقماً صحيحاً أو عشرياً"

    firestore_db = get_db()
    doc_ref = firestore_db.collection('users').document(user_id_str)

    # مرونة اختيار الحقل للتوافق مع العملة المطلوبة
    if is_usd is True or str(is_usd).lower() in ('usd', 'usd_balance'):
        field_name = 'usd_balance'
    elif str(is_usd).lower() in ('znx', 'znx_balance'):
        field_name = 'znx_balance'
    else:
        field_name = 'balance'

    @firestore.transactional
    def update_in_transaction(transaction, doc_ref):
        snapshot = doc_ref.get(transaction=transaction)
        if not snapshot.exists:
            return False, "المستخدم غير موجود"
        
        user_data = snapshot.to_dict()
        current_balance = float(user_data.get(field_name, 0.0))
        new_balance = round(current_balance + amount, 6)

        if new_balance < 0:
            return False, "الرصيد غير كافٍ"

        transaction.update(doc_ref, {field_name: new_balance})
        return True, new_balance

    try:
        transaction = firestore_db.transaction()
        success, result = update_in_transaction(transaction, doc_ref)
        return success, result
    except Exception as e:
        print(f"❌ خطأ في معاملة تحديث الرصيد للمستخدم {user_id_str}: {e}")
        return False, str(e)


# ==================== Leaderboard Bridge & Fallback System ====================

def get_leaderboard_rankings_legacy(limit=50):
    """🌉 جسر توافقي لأي موديول قديم يستدعي get_leaderboard_rankings_legacy"""
    return get_leaderboard_data(limit=limit)


def _fallback_get_leaderboard_data(limit=50, user_id=None):
    """
    الآلية الاحتياطية الداخلية لجلب قائمة المتصدرين مباشرة من Firestore
    في حال تعذر استدعائها من znx_wallet_db.py.
    """
    try:
        firestore_db = get_db()
        users_ref = firestore_db.collection('users')
        safe_limit = max(1, min(int(limit or 50), 100))

        query = users_ref.order_by('balance', direction=firestore.Query.DESCENDING).limit(safe_limit)
        docs = query.stream()

        leaderboard = []
        rank = 1
        user_rank = None
        user_in_top = False

        target_user_id = _sanitize_telegram_id(user_id)

        for doc in docs:
            data = doc.to_dict()
            u_id = str(data.get('user_id') or doc.id)
            user_entry = {
                'rank': rank,
                'user_id': u_id,
                'first_name': str(data.get('first_name', 'لاعب')),
                'balance': float(data.get('balance', 0.0)),
                'usd_balance': float(data.get('usd_balance', 0.0)),
                'znx_balance': float(data.get('znx_balance', 0.0)),
                'farm_level': data.get('farm_level', 1)
            }
            leaderboard.append(user_entry)

            if target_user_id and u_id == target_user_id:
                user_rank = rank
                user_in_top = True

            rank += 1

        # حساب ترتيب المستخدم الحالي إذا لم يكن ضمن أوائل القائمة
        if target_user_id and not user_in_top:
            target_doc = users_ref.document(target_user_id).get()
            if target_doc.exists:
                target_data = target_doc.to_dict()
                target_balance = float(target_data.get('balance', 0.0))
                higher_docs = users_ref.where('balance', '>', target_balance).stream()
                higher_count = sum(1 for _ in higher_docs)
                user_rank = higher_count + 1

        return {
            'success': True,
            'leaderboard': leaderboard,
            'my_rank': user_rank or "غير مصنف"
        }
    except Exception as e:
        print(f"❌ خطأ أثناء جلب قائمة المتصدرين (الاحتياطي): {e}")
        return {
            'success': False,
            'error': str(e),
            'leaderboard': [],
            'my_rank': "غير مصنف"
        }


def get_leaderboard_data(limit=50, user_id=None):
    """
    دالة الجسر (Bridge Pattern) لربط طلبات بيانات الترتيب بموديول znx_wallet_db.py بشكل مباشر.
    تضمن عدم انكسار أي موديول قديم يطلب البيانات من database.py.
    """
    if callable(znx_get_leaderboard_data):
        try:
            res = znx_get_leaderboard_data(limit=limit, user_id=user_id)
            if res and isinstance(res, dict) and res.get('success', False):
                return res
        except Exception as e:
            print(f"⚠️ تعذر استدعاء المتصدرين عبر الجسر من znx_wallet_db: {e}")

    # الانتقال للحل الاحتياطي المباشر
    return _fallback_get_leaderboard_data(limit=limit, user_id=user_id)


# ==================== Sub-Modules Re-exports ====================

# 0. Admin Database Module (أكواد المكافآت والإدارة العامة)
try:
    from admin_database import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل admin_database: {e}")

# 1. Admin Chat Module
try:
    from admin_chat.admin_chat_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل admin_chat_db: {e}")

# 2. Farm Module
try:
    from farm.farm_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل farm_db: {e}")

# 3. Friends Module
try:
    from friends.friends_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل friends_db: {e}")

# 4. Games Module
try:
    from games.games_db import *
    if 'init_all_games_db' in locals():
        init_all_games_db()
except Exception as e:
    print(f"⚠️ خطأ في تحميل games_db: {e}")

# 5. Settings Module
try:
    from settings.settings_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل settings_db: {e}")

# 6. Shop Module
try:
    from shop.shop_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل shop_db: {e}")

# 7. Super Admin Module
try:
    from super_admin.super_admin_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل super_admin_db: {e}")

# 8. Support Module
try:
    from support.support_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل support_db: {e}")

# 9. Tasks Module
try:
    from tasks.tasks_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل tasks_db: {e}")

# 10. Users Module
try:
    from users.users_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل users_db: {e}")

# 11. Wallet Module (يشمل المحفظة والأنشطة الفرعية)
try:
    from wallet.wallet_db import *
    from wallet.deposit.deposit_db import *
    from wallet.history.history_db import *
    from wallet.withdraw.withdraw_db import *
    from wallet.exchange.exchange_db import *
except Exception as e:
    print(f"⚠️ خطأ في تحميل wallet_db وموديولاتها الفرعية: {e}")

# 12. Offers, ZNX Wallet & Ads Modules
try:
    from offers.offers_db import *
except Exception:
    pass

try:
    from ads.ads_db import *
except Exception:
    pass

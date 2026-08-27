import datetime
from firebase_admin import firestore


def _get_db():
    """جلب كائن داتا بيز من الملف الرئيسي لمنع الدوران الدائري (Circular Import)"""
    from database import get_db
    return get_db()


# ==================== Promo Code Engine (نظام أكواد المكافآت) ====================

def create_promo_code(code_name, reward_coins, duration_value, duration_type, max_uses=0):
    """
    إنشاء كود مكافأة جديد في قاعدة البيانات.
    
    :param code_name: اسم الكود (مثل: BONUS2026)
    :param reward_coins: عدد العملات للمستخدم
    :param duration_value: قيمة مدة الصلاحية (رقم)
    :param duration_type: نوع المدة ('minutes', 'hours', 'days')
    :param max_uses: أقصى عدد لاستخدام الكود إجمالاً (0 تعني غير محدود)
    """
    try:
        db = _get_db()
        code_id = str(code_name).strip().upper()
        if not code_id:
            return False, "❌ اسم الكود غير صالح!"

        # حساب تاريخ ووقت الانتهاء
        now = datetime.datetime.now(datetime.timezone.utc)
        duration_value = float(duration_value)
        
        if duration_type == 'minutes':
            expires_at = now + datetime.timedelta(minutes=duration_value)
        elif duration_type == 'hours':
            expires_at = now + datetime.timedelta(hours=duration_value)
        elif duration_type == 'days':
            expires_at = now + datetime.timedelta(days=duration_value)
        else:
            expires_at = now + datetime.timedelta(hours=duration_value)

        doc_ref = db.collection('promo_codes').document(code_id)
        
        promo_data = {
            'code': code_id,
            'reward_coins': float(reward_coins),
            'max_uses': int(max_uses),
            'used_count': 0,
            'used_by': [],
            'is_active': True,
            'created_at': firestore.SERVER_TIMESTAMP,
            'expires_at': expires_at
        }
        
        doc_ref.set(promo_data, merge=True)
        print(f"✅ تم إنشاء كود المكافأة {code_id} بنجاح!")
        return True, f"✅ تم إنشاء الكود '{code_id}' بنجاح! ينتهي في {expires_at.strftime('%Y-%m-%d %H:%M UTC')}"
    except Exception as e:
        print(f"❌ خطأ أثناء إنشاء كود المكافأة: {e}")
        return False, f"❌ حدث خطأ أثناء إنشاء الكود: {e}"


def redeem_promo_code(telegram_id, code_name):
    """
    استبدال وتفعيل كود المكافأة للمستخدم (تُستدعى من بوت/تطبيق المستخدم).
    
    :param telegram_id: معرف التليجرام الخاص بالمستخدم
    :param code_name: الكود المدخل
    :return: (Boolean, Message, RewardCoins)
    """
    try:
        db = _get_db()
        user_id_str = str(telegram_id).strip()
        code_id = str(code_name).strip().upper()

        if not code_id:
            return False, "❌ يرجى إدخال كود صحيح!", 0

        promo_ref = db.collection('promo_codes').document(code_id)
        promo_doc = promo_ref.get()

        if not promo_doc.exists:
            return False, "❌ الكود غير موجود أو غير صحيح!", 0

        data = promo_doc.to_dict()

        # 1. التحقق من تفعيل الكود
        if not data.get('is_active', True):
            return False, "❌ هذا الكود معطل حالياً!", 0

        # 2. التحقق من الصلاحية الزمنية
        expires_at = data.get('expires_at')
        if expires_at:
            now = datetime.datetime.now(datetime.timezone.utc)
            # معالجة الفروق في التوقيت بين Firestore و Python
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
            if now > expires_at:
                return False, "⏰ للأسف، انتهت صلاحية هذا الكود!", 0

        # 3. التحقق مما إذا كان المستخدم استخدم الكود سابقاً
        used_by = data.get('used_by', [])
        if user_id_str in used_by:
            return False, "⚠️ لقد استخدمت هذا الكود من قبل! يُسمح بالاستخدام مرة واحدة فقط.", 0

        # 4. التحقق من الحد الأقصى للإجمالي
        max_uses = data.get('max_uses', 0)
        used_count = data.get('used_count', 0)
        if max_uses > 0 and used_count >= max_uses:
            return False, "❌ وصل هذا الكود للحد الأقصى من الاستخدامات!", 0

        reward = float(data.get('reward_coins', 0))

        # 5. تحديث داتا بيز المستخدم وإضافة العملات
        user_ref = db.collection('users').document(user_id_str)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return False, "❌ حساب المستخدم غير موجود!", 0

        # إضافة العملات للمستخدم
        user_ref.update({
            'balance': firestore.Increment(reward)
        })

        # تسجيل استخدام المستخدم للرمز
        promo_ref.update({
            'used_count': firestore.Increment(1),
            'used_by': firestore.ArrayUnion([user_id_str])
        })

        return True, f"🎉 مبروك! تم تفعيل الكود وحصلت على {reward} عملة!", reward

    except Exception as e:
        print(f"❌ خطأ أثناء تفعيل كود المكافأة: {e}")
        return False, "❌ حدث خطأ غير متوقع أثناء تفعيل الكود.", 0


def get_all_promo_codes():
    """جلب قائمة بكل أكواد المكافآت المتاحة في النظام للادمن"""
    try:
        db = _get_db()
        docs = db.collection('promo_codes').stream()
        codes_list = []
        for doc in docs:
            item = doc.to_dict()
            codes_list.append(item)
        return codes_list
    except Exception as e:
        print(f"❌ خطأ جلب أكواد المكافآت: {e}")
        return []


def delete_promo_code(code_name):
    """حذف كود مكافأة من داتا بيز الأدمن"""
    try:
        db = _get_db()
        code_id = str(code_name).strip().upper()
        db.collection('promo_codes').document(code_id).delete()
        return True, f"🗑️ تم حذف الكود '{code_id}' بنجاح!"
    except Exception as e:
        print(f"❌ خطأ حذف الكود: {e}")
        return False, f"❌ خطأ أثناء حذف الكود: {e}"


def toggle_promo_code_status(code_name, is_active):
    """تفعيل أو تعطيل كود مكافأة"""
    try:
        db = _get_db()
        code_id = str(code_name).strip().upper()
        db.collection('promo_codes').document(code_id).update({
            'is_active': bool(is_active)
        })
        status_str = "تفعيل" if is_active else "تعطيل"
        return True, f"✅ تم {status_str} الكود '{code_id}' بنجاح!"
    except Exception as e:
        print(f"❌ خطأ تغيير حالة الكود: {e}")
        return False, f"❌ حدث خطأ أثناء تعديل حالة الكود: {e}"

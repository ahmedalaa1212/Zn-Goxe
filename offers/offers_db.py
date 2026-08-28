import time
from firebase_admin import firestore
from database import get_db, get_user, update_user

# قائمة العروض الافتراضية
DEFAULT_OFFERS = [
    {
        "id": "offer_welcome_bonus",
        "title": "مكافأة الترحيب الخاصة",
        "description": "قم بزيارة قناتنا الرسمية واحصل على مكافأة فورية من عملة ZN",
        "reward_type": "balance",  # balance, usd_balance, ad_balance
        "reward_amount": 500.0,
        "action_url": "https://t.me/ZNGOXE",
        "is_active": True,
        "icon": "🎁"
    },
    {
        "id": "offer_watch_ad_pack",
        "title": "مشاهدة إعلان مميز",
        "description": "شاهد إعلان كامل واحصل على 200 ZN + 1.0 AdZN",
        "reward_type": "hybrid",
        "reward_amount": 200.0,
        "secondary_reward_type": "ad_balance",
        "secondary_reward_amount": 1.0,
        "action_url": "",
        "is_active": True,
        "icon": "📺"
    },
    {
        "id": "offer_invite_3_friends",
        "title": "دعوة 3 أصدقاء جدد",
        "description": "قم بدعوة 3 من أصدقائك للانضمام إلى البوت واحصل على 1000 ZN",
        "reward_type": "balance",
        "reward_amount": 1000.0,
        "required_referrals": 3,
        "action_url": "",
        "is_active": True,
        "icon": "👥"
    }
]

def init_offers_collection():
    """تهيئة العروض الافتراضية في Firestore إذا لم تكن موجودة"""
    try:
        db = get_db()
        offers_ref = db.collection('offers')
        for offer in DEFAULT_OFFERS:
            doc_ref = offers_ref.document(offer['id'])
            if not doc_ref.get().exists:
                doc_ref.set(offer)
    except Exception as e:
        print(f"❌ خطأ أثناء تهيئة مجموعات العروض: {e}")

def get_all_offers():
    """جلب كافة العروض النشطة"""
    try:
        db = get_db()
        offers_ref = db.collection('offers').where('is_active', '==', True).stream()
        offers = []
        for doc in offers_ref:
            data = doc.to_dict()
            data['id'] = doc.id
            offers.append(data)
        
        if not offers:
            init_offers_collection()
            return DEFAULT_OFFERS
            
        return offers
    except Exception as e:
        print(f"❌ خطأ جلب العروض: {e}")
        return DEFAULT_OFFERS

def get_user_completed_offers(telegram_id):
    """جلب قائمة معرفات العروض التي أكملها المستخدم"""
    if not telegram_id:
        return []
    try:
        user = get_user(telegram_id)
        if user:
            return user.get('completed_offers', [])
        return []
    except Exception as e:
        print(f"❌ خطأ جلب عروض المستخدم المكتملة {telegram_id}: {e}")
        return []

def claim_offer_reward(telegram_id, offer_id):
    """معالجة استلام مكافأة العرض وتحديث رصيد المستخدم"""
    if not telegram_id or not offer_id:
        return {"success": False, "error": "بيانات الطلب غير مكتملة."}

    try:
        db = get_db()
        user_id_str = str(telegram_id).strip()
        user_ref = db.collection('users').document(user_id_str)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return {"success": False, "error": "المستخدم غير موجود."}

        user_data = user_doc.to_dict()
        completed_offers = user_data.get('completed_offers', [])

        if offer_id in completed_offers:
            return {"success": False, "error": "لقد قمت باستلام مكافأة هذا العرض سابقاً."}

        # جلب تفاصيل العرض
        offer_doc = db.collection('offers').document(offer_id).get()
        if offer_doc.exists:
            offer = offer_doc.to_dict()
        else:
            # التحقق من القائمة الافتراضية
            offer = next((o for o in DEFAULT_OFFERS if o['id'] == offer_id), None)

        if not offer or not offer.get('is_active', True):
            return {"success": False, "error": "العرض غير متاح حالياً."}

        # التحقق من شرط الدعوات إن وجد
        req_refs = offer.get('required_referrals', 0)
        if req_refs > 0:
            user_refs = user_data.get('referrals_count', 0)
            if user_refs < req_refs:
                return {"success": False, "error": f"يحتاج هذا العرض لـ {req_refs} إحالات. لديك حالياً {user_refs}."}

        # إعداد التحديثات
        updates = {}
        completed_offers.append(offer_id)
        updates['completed_offers'] = completed_offers

        reward_type = offer.get('reward_type', 'balance')
        reward_amount = float(offer.get('reward_amount', 0.0))

        if reward_type == 'balance':
            updates['balance'] = float(user_data.get('balance', 0.0)) + reward_amount
        elif reward_type == 'usd_balance':
            updates['usd_balance'] = float(user_data.get('usd_balance', 0.0)) + reward_amount
        elif reward_type == 'ad_balance':
            updates['ad_balance'] = float(user_data.get('ad_balance', 0.0)) + reward_amount
        elif reward_type == 'hybrid':
            updates['balance'] = float(user_data.get('balance', 0.0)) + reward_amount
            sec_type = offer.get('secondary_reward_type', 'ad_balance')
            sec_amount = float(offer.get('secondary_reward_amount', 0.0))
            if sec_type in ['ad_balance', 'usd_balance', 'balance']:
                updates[sec_type] = float(user_data.get(sec_type, 0.0)) + sec_amount

        user_ref.update(updates)
        updated_user = user_ref.get().to_dict()

        return {
            "success": True,
            "message": "تم استلام مكافأة العرض بنجاح! 🎉",
            "player": updated_user
        }

    except Exception as e:
        print(f"❌ خطأ أثناء المطالبة بالمكافأة {telegram_id}: {e}")
        return {"success": False, "error": f"حدث خطأ في السيرفر: {str(e)}"}


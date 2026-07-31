import firebase_admin
from firebase_admin import firestore

# تأكد أن db معرف ومربوط بالفايربيس عندك
db = firestore.client()

def get_or_create_user(telegram_id):
    """
    جلب بيانات المستخدم برقم ID التلجرام، 
    وإذا لم يكن موجوداً يتم إنشاؤه تلقائياً بالبيانات الافتراضية.
    """
    user_ref = db.collection('users').document(str(telegram_id))
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        # البيانات الأوليّة للمستخدم الجديد
        initial_data = {
            "telegram_id": str(telegram_id),
            "balance": 0.0,       # الرصيد الأولي
            "hourly_rate": 0.0    # سرعة التعدين الساعية الأولية
        }
        user_ref.set(initial_data)
        return initial_data
    
    return user_doc.to_dict()


def add_user_mining_speed(telegram_id, speed_increase):
    """
    زيادة سرعة التعدين للمستخدم بمقدار معين عند شراء ترقية.
    """
    user_ref = db.collection('users').document(str(telegram_id))
    
    # زيادة قيمة hourly_rate في الفايربيس بمقدار speed_increase
    user_ref.update({
        "hourly_rate": firestore.Increment(speed_increase)
    })
    
    # إعادة البيانات المحدثة
    return user_ref.get().to_dict()

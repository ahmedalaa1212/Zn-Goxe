# core/ton_price.py
import requests
import time

# ذاكرة مؤقتة لتخزين السعر وتجنب كثرة الطلبات (Cache)
_ton_price_cache = {
    "price": 5.50, # سعر افتراضي في حال انقطاع الـ API
    "updated_at": 0
}

def get_live_ton_price():
    """جلب سعر TON اللحظي بالدولار مع نظام التخزين المؤقت لمد 60 ثانية"""
    global _ton_price_cache
    now = time.time()
    
    # تحديث السعر كل 60 ثانية فقط
    if now - _ton_price_cache["updated_at"] < 60:
        return _ton_price_cache["price"]
    
    try:
        # الاستعلام من API كوين جيكو المباشر
        url = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd"
        response = requests.get(url, timeout=4)
        if response.status_code == 200:
            data = response.json()
            price = float(data['the-open-network']['usd'])
            _ton_price_cache = {
                "price": price,
                "updated_at": now
            }
            return price
    except Exception as e:
        print(f"⚠️ تعذر جلب سعر TON اللحظي، استخدام السعر المحفوظ: {e}")
    
    return _ton_price_cache["price"]

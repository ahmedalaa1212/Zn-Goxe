# core/ton_price.py
import requests
import time

# ذاكرة مؤقتة لتخزين السعر وتجنب كثرة الطلبات (Cache)
_ton_price_cache = {
    "price": 5.50,  # سعر افتراضي احتياطي
    "updated_at": 0
}

def get_live_ton_price():
    """جلب سعر TON اللحظي بالدولار من السيرفر حصراً"""
    global _ton_price_cache
    now = time.time()
    
    # تحديث السعر كل 60 ثانية فقط
    if now - _ton_price_cache["updated_at"] < 60:
        return _ton_price_cache["price"]
    
    try:
        # API سعر TON اللحظي
        url = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd"
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            price = float(data['the-open-network']['usd'])
            if price > 0:
                _ton_price_cache = {
                    "price": price,
                    "updated_at": now
                }
                return price
    except Exception as e:
        print(f"⚠️ تعذر جلب سعر TON اللحظي، استخدام السعر المحفوظ: {e}")
    
    return _ton_price_cache["price"]

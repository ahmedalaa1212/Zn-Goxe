import requests
import time

# التخزين المؤقت الافتراضي بالسيرفر
_ton_price_cache = {
    "price": 5.50,
    "updated_at": 0
}

def get_live_ton_price():
    """
    جلب سعر TON المباشر في السيرفر (للتحقق الخلفي والمعاملات الحساسة فقط).
    ملاحظة: الواجهات تكتفي بالسعر المباشر من Client-side لتفادي الإجهاد.
    """
    global _ton_price_cache
    now = time.time()
    
    # 1. الاعتماد على الكاش بالسيرفر لمدة 5 دقائق (300 ثانية) لتفادي البطء وحظر الـ API
    if now - _ton_price_cache["updated_at"] < 300 and _ton_price_cache["price"] > 0:
        return _ton_price_cache["price"]
    
    # المصدر الأول والرئيسي: TonAPI (الأسرع والأدق لشبكة TON)
    try:
        url = "https://tonapi.io/v2/rates?tokens=ton&currencies=usd"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            price = float(data.get('rates', {}).get('TON', {}).get('prices', {}).get('USD', 0))
            if price > 0:
                _ton_price_cache = {"price": price, "updated_at": now}
                return price
    except Exception as e:
        print(f"⚠️ فشل TonAPI، الانتقال للمصدر الاحتياطي الأول (OKX): {e}")

    # المصدر الاحتياطي الأول: منصة OKX
    try:
        url = "https://www.okx.com/api/v5/market/ticker?instId=TON-USDT"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            price = float(data.get('data', [{}])[0].get('last', 0))
            if price > 0:
                _ton_price_cache = {"price": price, "updated_at": now}
                return price
    except Exception as e:
        print(f"⚠️ فشل OKX، الانتقال للمصدر الاحتياطي الثاني (CoinGecko): {e}")

    # المصدر الاحتياطي الثاني: CoinGecko
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            price = float(data.get('the-open-network', {}).get('usd', 0))
            if price > 0:
                _ton_price_cache = {"price": price, "updated_at": now}
                return price
    except Exception as e:
        print(f"⚠️ تعذر جلب السعر من جميع المصادر، استخدام السعر الاحتياطي المسجل: {e}")
    
    # إرجاع آخر سعر تم حفظه عند فشل كافة الاتصالات
    return _ton_price_cache["price"]

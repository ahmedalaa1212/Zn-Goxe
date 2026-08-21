import time
import requests

# السعر الافتراضي المبدئي (مبني على الصورة الخاصة بك) لتجنب توقف النظام لو النت فصل
_cached_price = 1.46 
_last_fetch_time = 0

def get_gram_price_usd():
    global _cached_price, _last_fetch_time
    current_time = time.time()
    
    # تحديث السعر كل 5 دقائق (300 ثانية) لتجنب حظر الـ API
    if current_time - _last_fetch_time > 300:
        try:
            # استخدام API مجاني من CoinGecko لجلب السعر المباشر لعملة TON (Gram)
            url = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd"
            response = requests.get(url, timeout=5)
            data = response.json()
            
            if "the-open-network" in data and "usd" in data["the-open-network"]:
                _cached_price = float(data["the-open-network"]["usd"])
                _last_fetch_time = current_time
                print(f"✅ تم جلب السعر المباشر بنجاح: {_cached_price} دولار")
        except Exception as e:
            print(f"⚠️ فشل جلب السعر المباشر، سيتم استخدام آخر سعر متاح ({_cached_price}): {e}")
            
    return _cached_price

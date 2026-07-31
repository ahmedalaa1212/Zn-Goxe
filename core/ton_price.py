import requests
import time

_ton_price_cache = {
    "price": 5.50,
    "updated_at": 0
}

def get_live_ton_price():
    global _ton_price_cache
    now = time.time()
    
    if now - _ton_price_cache["updated_at"] < 60 and _ton_price_cache["price"] > 0:
        return _ton_price_cache["price"]
    
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd"
        response = requests.get(url, timeout=4)
        if response.status_code == 200:
            data = response.json()
            price = float(data['the-open-network']['usd'])
            if price > 0:
                _ton_price_cache = {"price": price, "updated_at": now}
                return price
    except Exception as e:
        print(f"⚠️ فشل CoinGecko، الانتقال للمصدر الاحتياطي: {e}")

    try:
        url = "https://api.coincap.io/v2/assets/toncoin"
        response = requests.get(url, timeout=4)
        if response.status_code == 200:
            data = response.json()
            price = float(data['data']['priceUsd'])
            if price > 0:
                _ton_price_cache = {"price": price, "updated_at": now}
                return price
    except Exception as e:
        print(f"⚠️ تعذر جلب سعر TON، استخدام السعر الاحتياطي: {e}")
    
    return _ton_price_cache["price"]

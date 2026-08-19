let tonPriceUSD = 0;
let withdrawConfig = null;
let userWallet = null;

async function initWithdraw(userId) {
    const res = await fetch(`/api/withdraw/config?user_id=${userId}`);
    const data = await res.json();
    
    if (data.success) {
        withdrawConfig = data.config;
        tonPriceUSD = data.ton_price;
        if(data.already_withdrawn) {
            alert("لقد قمت بإجراء سحب اليوم. عاود المحاولة غداً بعد 00:00 UTC.");
        }
    }
}

// حساب المقابل بـ TON والعمولة لحظياً
document.getElementById('coins-input').addEventListener('input', (e) => {
    const coins = parseFloat(e.target.value) || 0;
    const rate = withdrawConfig.rate_coins_per_usd; // 100,000
    
    const usdValue = coins / rate;
    const tonValue = usdValue / tonPriceUSD;
    
    const feeCoins = coins * (withdrawConfig.fee_percent / 100);
    const netCoins = coins - feeCoins;
    const netTon = (netCoins / rate) / tonPriceUSD;

    document.getElementById('ton-output').value = tonValue.toFixed(4) + " TON";
    document.getElementById('fee-amount').innerText = feeCoins.toLocaleString() + " العملة";
    document.getElementById('net-ton').innerText = netTon.toFixed(4) + " TON";
    
    document.getElementById('confirm-withdraw-btn').disabled = (coins <= 0 || !userWallet);
});

// التعامل مع زر الربط والتأكيد بواسطة TONConnect SDK...

let tonPriceUSD = 0;
let withdrawConfig = null;
let currentWalletAddress = null;
let currentLevel = null;

// تهيئة الواجهة
async function initWithdrawPage(userId) {
  try {
    const response = await fetch(`/api/withdraw/config?user_id=${userId}`);
    const data = await response.json();

    if (data.success) {
      withdrawConfig = data.config;
      tonPriceUSD = data.ton_price;

      if (data.already_withdrawn) {
        alert("⚠️ تم إكمال سحبتك اليومية. يمكنك السحب مجدداً غداً بعد 00:00 UTC.");
      }

      if (data.saved_wallet) {
        setConnectedWallet(data.saved_wallet);
      }
    }
  } catch (err) {
    console.error("فشل تحميل إعدادات السحب", err);
  }
}

// محاكاة أو ربط TonConnect
function connectWallet() {
  // يمكن دمج TonConnect UI SDK هنا
  const mockAddress = "EQD" + Math.random().toString(36).substring(2, 10).toUpperCase() + "...";
  setConnectedWallet(mockAddress);
}

function setConnectedWallet(address) {
  currentWalletAddress = address;
  document.getElementById("wallet-not-connected").style.display = "none";
  document.getElementById("wallet-connected").style.display = "block";
  document.getElementById("connected-address-text").innerText = address;
  calculateWithdraw();
}

// الحساب الفوري ومطابقة المستويات
function calculateWithdraw() {
  const coinsInput = parseFloat(document.getElementById("coins-input").value) || 0;
  const btn = document.getElementById("confirm-withdraw-btn");
  const levelBadge = document.getElementById("level-indicator");

  if (!withdrawConfig || coinsInput <= 0) {
    resetCalculations();
    btn.disabled = true;
    return;
  }

  // 1. تحديد المستوى المتاح بناءً على الكمية المدخلة
  const levels = withdrawConfig.levels;
  currentLevel = levels.find(l => coinsInput >= l.min && coinsInput <= l.max);

  if (!currentLevel) {
    levelBadge.innerText = "غير مطابقة للمستويات";
    levelBadge.style.color = "#ff4757";
    resetCalculations();
    btn.disabled = true;
    return;
  }

  levelBadge.innerText = `المستوى ${currentLevel.level} (${currentLevel.type === 'auto' ? 'فوري' : 'يدوي'})`;
  levelBadge.style.color = "#00a8ff";

  // 2. حساب القيمة بـ USD ثم تحويلها لـ TON
  const usdRate = withdrawConfig.rate_coins_per_usd; // 100,000 ZN = $1
  const usdValue = coinsInput / usdRate;
  const rawTon = usdValue / tonPriceUSD;

  // 3. خصم 3%
  const feeCoins = coinsInput * (withdrawConfig.fee_percent / 100);
  const netCoins = coinsInput - feeCoins;
  const netUsd = netCoins / usdRate;
  const netTon = netUsd / tonPriceUSD;

  // 4. تحديث الشاشة
  document.getElementById("ton-output").value = rawTon.toFixed(4) + " TON";
  document.getElementById("fee-amount").innerText = `${feeCoins.toLocaleString()} ZN`;
  document.getElementById("net-ton").innerText = `${netTon.toFixed(4)} TON`;

  // تفعيل الزر شرط ربط المحفظة
  btn.disabled = !currentWalletAddress;
}

function resetCalculations() {
  document.getElementById("ton-output").value = "0.0000 TON";
  document.getElementById("fee-amount").innerText = "0 ZN";
  document.getElementById("net-ton").innerText = "0.0000 TON";
}

// إرسال طلب السحب
async function submitWithdrawal() {
  const coins = parseFloat(document.getElementById("coins-input").value);
  const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "5102387551";

  const btn = document.getElementById("confirm-withdraw-btn");
  btn.disabled = true;
  btn.innerText = "جاري الإرسال...";

  try {
    const res = await fetch('/api/withdraw/request', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_id: userId,
        coins: coins,
        wallet_address: currentWalletAddress
      })
    });
    
    const data = await res.json();
    alert(data.message);
    if(data.success) location.reload();

  } catch (err) {
    alert("حدث خطأ أثناء تنفيذ الطلب.");
  } finally {
    btn.innerText = "تأكيد السحب";
    btn.disabled = false;
  }
}

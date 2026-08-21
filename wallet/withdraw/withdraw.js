let tonPriceUSD = 0;
let withdrawConfig = null;
let currentWalletAddress = null;
let tonConnectUI = null;
let userBalance = 0;

document.addEventListener("DOMContentLoaded", function() {
  const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "5102387551";
  initTonConnect();
  initWithdrawPage(userId);

  const coinsInput = document.getElementById("coins-input");
  if (coinsInput) {
    coinsInput.addEventListener("input", calculateWithdraw);
    coinsInput.addEventListener("keyup", calculateWithdraw);
    coinsInput.addEventListener("change", calculateWithdraw);
  }
});

function initTonConnect() {
  try {
    const TonConnectClass = window.TON_CONNECT_UI?.TonConnectUI || window.TonConnectSDK?.TonConnectUI;
    if (!TonConnectClass) {
      console.warn("جاري الانتظار لتحميل TonConnect SDK...");
      setTimeout(initTonConnect, 500);
      return;
    }

    tonConnectUI = new TonConnectClass({
      manifestUrl: window.location.origin + '/tonconnect-manifest.json',
      buttonRootId: 'ton-connect-button'
    });

    tonConnectUI.onStatusChange(wallet => {
      const statusBadge = document.getElementById("wallet-connect-status");
      const walletBox = document.getElementById("connected-wallet-box");
      const addressDisplay = document.getElementById("wallet-address-display");

      if (wallet) {
        currentWalletAddress = wallet.account.address;
        if (statusBadge) {
          statusBadge.innerText = "متصل ✅";
          statusBadge.style.color = "#4ade80";
        }
        if (walletBox) walletBox.style.display = "flex";
        if (addressDisplay) {
          const shortAddr = currentWalletAddress.substring(0, 6) + "..." + currentWalletAddress.substring(currentWalletAddress.length - 4);
          addressDisplay.innerText = shortAddr;
        }
      } else {
        currentWalletAddress = null;
        if (statusBadge) {
          statusBadge.innerText = "غير متصل";
          statusBadge.style.color = "#ef4444";
        }
        if (walletBox) walletBox.style.display = "none";
      }
      calculateWithdraw();
    });
  } catch (e) {
    console.error("خطأ تهيئة TonConnect:", e);
  }
}

async function initWithdrawPage(userId) {
  try {
    const response = await fetch(`/api/withdraw/config?user_id=${userId}`);
    const data = await response.json();

    if (data.success) {
      withdrawConfig = data.config;
      tonPriceUSD = parseFloat(data.ton_price) || 5.50;
      userBalance = parseFloat(data.user_balance) || 0;
      calculateWithdraw();
    }
  } catch (err) {
    console.error("خطأ في جلب إعدادات السحب:", err);
  }
}

function setMaxCoins() {
  const coinsInput = document.getElementById("coins-input");
  if (!coinsInput) return;

  if (userBalance <= 0) {
    alert("رصيدك الحالي 0 ZN");
    coinsInput.value = "";
    resetCalculations();
    return;
  }

  coinsInput.value = userBalance;
  calculateWithdraw();
}

function calculateWithdraw() {
  const coinsInput = document.getElementById("coins-input");
  const coinsInputVal = parseFloat(coinsInput.value) || 0;
  const btn = document.getElementById("confirm-withdraw-btn");
  const levelBadge = document.getElementById("level-indicator");

  if (!withdrawConfig || !tonPriceUSD || coinsInputVal <= 0) {
    resetCalculations();
    if (btn) btn.disabled = true;
    if (levelBadge) {
      levelBadge.innerText = "المستوى: --";
      levelBadge.style.color = "#38bdf8";
    }
    return;
  }

  if (coinsInputVal > userBalance) {
    if (levelBadge) {
      levelBadge.innerText = "الرصيد غير كافٍ ❌";
      levelBadge.style.color = "#ef4444";
    }
    resetCalculations();
    if (btn) btn.disabled = true;
    return;
  }

  const levels = withdrawConfig.levels || [];
  const matchedLevel = levels.find(l => coinsInputVal >= l.min && coinsInputVal <= l.max);

  if (!matchedLevel) {
    if (levelBadge) {
      levelBadge.innerText = "خارج حدود المستويات ❌";
      levelBadge.style.color = "#ef4444";
    }
    resetCalculations();
    if (btn) btn.disabled = true;
    return;
  }

  if (levelBadge) {
    levelBadge.innerText = `المستوى ${matchedLevel.level} (${matchedLevel.type === 'auto' ? 'فوري ⚡' : 'يدوي 🛡️'})`;
    levelBadge.style.color = "#38bdf8";
  }

  // معادلة التحويل: 100,000 عملة = 1 دولار
  const usdRate = withdrawConfig.rate_coins_per_usd || 100000;
  const usdValue = coinsInputVal / usdRate;
  const rawTon = usdValue / tonPriceUSD;

  const feePercent = withdrawConfig.fee_percent || 3;
  const feeCoins = coinsInputVal * (feePercent / 100);
  const netCoins = coinsInputVal - feeCoins;
  const netUsd = netCoins / usdRate;
  const netTon = netUsd / tonPriceUSD;

  document.getElementById("ton-output").value = rawTon.toFixed(4) + " TON";
  document.getElementById("fee-amount").innerText = `${feeCoins.toLocaleString()} ZN`;
  document.getElementById("net-ton").innerText = `${netTon.toFixed(4)} TON`;

  if (btn) {
    btn.disabled = !currentWalletAddress || coinsInputVal <= 0;
  }
}

function resetCalculations() {
  const tonOutput = document.getElementById("ton-output");
  const feeAmount = document.getElementById("fee-amount");
  const netTon = document.getElementById("net-ton");

  if (tonOutput) tonOutput.value = "0.0000 TON";
  if (feeAmount) feeAmount.innerText = "0 ZN";
  if (netTon) netTon.innerText = "0.0000 TON";
}

async function submitWithdrawal() {
  const coins = parseFloat(document.getElementById("coins-input").value);
  const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "5102387551";
  const btn = document.getElementById("confirm-withdraw-btn");

  if (!currentWalletAddress) {
    alert("يرجى ربط محفظة TON أولاً قبل تأكيد السحب!");
    return;
  }

  if (coins > userBalance) {
    alert("رصيدك الحالي غير كافٍ لتمام هذه العملية!");
    return;
  }

  btn.disabled = true;
  btn.innerText = "جاري معالجة الطلب...";

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
    if (data.success) {
      location.reload();
    }
  } catch (err) {
    alert("حدث خطأ أثناء الاتصال بالخادم.");
  } finally {
    btn.innerText = "تأكيد السحب";
    btn.disabled = false;
  }
}

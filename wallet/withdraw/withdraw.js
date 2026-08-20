let tonPriceUSD = 0;
let withdrawConfig = null;
let currentWalletAddress = null;
let tonConnectUI = null;

document.addEventListener("DOMContentLoaded", function() {
  const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "5102387551";
  initTonConnect();
  initWithdrawPage(userId);

  const coinsInput = document.getElementById("coins-input");
  if (coinsInput) {
    coinsInput.addEventListener("input", calculateWithdraw);
  }
});

function initTonConnect() {
  tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
    manifestUrl: window.location.origin + '/tonconnect-manifest.json',
    buttonRootId: 'ton-connect-button'
  });

  tonConnectUI.onStatusChange(wallet => {
    if (wallet) {
      currentWalletAddress = wallet.account.address;
      calculateWithdraw();
    } else {
      currentWalletAddress = null;
      calculateWithdraw();
    }
  });
}

async function initWithdrawPage(userId) {
  try {
    const response = await fetch(`/api/withdraw/config?user_id=${userId}`);
    const data = await response.json();

    if (data.success) {
      withdrawConfig = data.config;
      tonPriceUSD = data.ton_price || 5.50;
      calculateWithdraw();
    }
  } catch (err) {
    console.error("خطأ في جلب بيانات السحب:", err);
  }
}

function calculateWithdraw() {
  const coinsInputVal = parseFloat(document.getElementById("coins-input").value) || 0;
  const btn = document.getElementById("confirm-withdraw-btn");
  const levelBadge = document.getElementById("level-indicator");

  if (!withdrawConfig || !tonPriceUSD || coinsInputVal <= 0) {
    resetCalculations();
    btn.disabled = true;
    return;
  }

  const levels = withdrawConfig.levels;
  const matchedLevel = levels.find(l => coinsInputVal >= l.min && coinsInputVal <= l.max);

  if (!matchedLevel) {
    levelBadge.innerText = "خارج حدود المستويات";
    levelBadge.style.color = "#ff4757";
    resetCalculations();
    btn.disabled = true;
    return;
  }

  levelBadge.innerText = `المستوى ${matchedLevel.level} (${matchedLevel.type === 'auto' ? 'فوري' : 'يدوي'})`;
  levelBadge.style.color = "#00a8ff";

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

  btn.disabled = !currentWalletAddress;
}

function resetCalculations() {
  document.getElementById("ton-output").value = "0.0000 TON";
  document.getElementById("fee-amount").innerText = "0 ZN";
  document.getElementById("net-ton").innerText = "0.0000 TON";
}

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
    if (data.success) location.reload();

  } catch (err) {
    alert("حدث خطأ في الاتصال بالخادم.");
  } finally {
    btn.innerText = "تأكيد السحب";
    btn.disabled = false;
  }
}

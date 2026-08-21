let tonPriceUSD = 0;
let withdrawConfig = null;
let currentWalletAddress = null;
let tonConnectUI = null;
let userBalance = 0;
let withdrawCount = 0;
let activeLevelIndex = 0;

document.addEventListener("DOMContentLoaded", function() {
  const urlParams = new URLSearchParams(window.location.search);
  const userId = urlParams.get('user_id') || window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "5102387551";
  
  initTonConnect();
  initWithdrawPage(userId);
});

function initTonConnect() {
  try {
    const TonConnectClass = window.TON_CONNECT_UI?.TonConnectUI || window.TonConnectSDK?.TonConnectUI;
    if (!TonConnectClass) {
      setTimeout(initTonConnect, 300);
      return;
    }

    if (!tonConnectUI) {
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
    }
  } catch (e) {
    console.error("خطأ تهيئة TonConnect:", e);
  }
}

async function initWithdrawPage(userId) {
  try {
    const response = await fetch(`/api/wallet/withdraw/config?user_id=${userId}`);
    const data = await response.json();

    if (data.success) {
      withdrawConfig = data.config;
      tonPriceUSD = parseFloat(data.ton_price) || 5.50;
      userBalance = parseFloat(data.user_balance) || 0;
      withdrawCount = parseInt(data.withdraw_count) || 0;

      // تحديد رقم المستوى بناءً على عدد السحوبات السابقة (من 0 إلى 5+)
      activeLevelIndex = Math.min(withdrawCount, (withdrawConfig.levels || []).length - 1);

      renderLevelsGuide();
      // الوضع الافتراضي عند الفتح: اختيار الحد الأقصى للمستوى الحالي
      setPreset('max');
    }
  } catch (err) {
    console.error("خطأ في جلب إعدادات السحب:", err);
  }
}

function renderLevelsGuide() {
  const container = document.getElementById("levels-list-container");
  const userLevelText = document.getElementById("current-user-level-text");
  if (!container || !withdrawConfig || !withdrawConfig.levels) return;

  if (userLevelText) {
    userLevelText.innerText = `السحبة رقم (${withdrawCount + 1})`;
  }

  let html = "";
  withdrawConfig.levels.forEach((lvl, idx) => {
    const isActive = idx === activeLevelIndex;
    const isAuto = lvl.type === 'auto';
    const maxText = lvl.max >= 999999999 ? "مفتوح" : lvl.max.toLocaleString() + " ZN";

    html += `
      <div class="level-item ${isActive ? 'active-level' : ''}">
        <div>
          <span>السحبة ${lvl.level}: </span>
          <strong>${lvl.min.toLocaleString()} - ${maxText}</strong>
        </div>
        <span class="level-item-tag ${isAuto ? 'tag-auto' : 'tag-manual'}">
          ${isAuto ? 'فوري ⚡' : 'يدوي 🛡️'} ${isActive ? ' (مستواك الحالي)' : ''}
        </span>
      </div>
    `;
  });

  container.innerHTML = html;
}

function setPreset(type) {
  if (!withdrawConfig || !withdrawConfig.levels) return;

  const currentLvl = withdrawConfig.levels[activeLevelIndex];
  if (!currentLvl) return;

  const coinsInput = document.getElementById("coins-input");
  let targetAmount = 0;

  const minVal = currentLvl.min;
  const maxVal = currentLvl.max >= 999999999 ? userBalance : currentLvl.max;

  if (type === 'min') {
    targetAmount = minVal;
  } else if (type === 'half') {
    targetAmount = Math.floor((minVal + maxVal) / 2);
  } else if (type === 'max') {
    targetAmount = maxVal;
  }

  // إذا كان الرصيد أقل من الحد الأدنى للمستوى
  if (userBalance < minVal && type !== 'min') {
    targetAmount = minVal;
  }

  if (coinsInput) {
    coinsInput.value = targetAmount;
  }

  calculateWithdraw();
}

function calculateWithdraw() {
  const coinsInput = document.getElementById("coins-input");
  const coinsInputVal = parseFloat(coinsInput?.value) || 0;
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

  const currentLvl = withdrawConfig.levels[activeLevelIndex];

  if (userBalance < coinsInputVal) {
    if (levelBadge) {
      levelBadge.innerText = "الرصيد غير كافٍ ❌";
      levelBadge.style.color = "#ef4444";
    }
    resetCalculations();
    if (btn) btn.disabled = true;
    return;
  }

  if (levelBadge && currentLvl) {
    levelBadge.innerText = `السحبة ${currentLvl.level} (${currentLvl.type === 'auto' ? 'فوري ⚡' : 'يدوي 🛡️'})`;
    levelBadge.style.color = "#38bdf8";
  }

  // معادلة التحويل الثابتة: 100,000 عملة = 1 دولار
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
    btn.disabled = !currentWalletAddress || coinsInputVal <= 0 || userBalance < coinsInputVal;
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
  const urlParams = new URLSearchParams(window.location.search);
  const userId = urlParams.get('user_id') || window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "5102387551";
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
    const res = await fetch('/api/wallet/withdraw/request', {
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

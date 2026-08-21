(function () {
  let gramPriceUSD = 0;
  let withdrawConfig = null;
  let currentWalletAddress = null;
  let tonConnectUI = null;
  let userBalance = 0;
  let withdrawCount = 0;
  let activeLevelIndex = 0;

  function parseInputValue(val) {
    if (val === null || val === undefined) return 0;
    const cleanStr = val.toString().replace(/,/g, '').trim();
    const num = parseFloat(cleanStr);
    return isNaN(num) ? 0 : num;
  }

  function getUserId() {
    const urlParams = new URLSearchParams(window.location.search);
    return (
      urlParams.get('user_id') ||
      window.userState?.userId ||
      window.userState?.id ||
      window.Telegram?.WebApp?.initDataUnsafe?.user?.id ||
      "5102387551"
    );
  }

  function bindInputEvents() {
    const coinsInput = document.getElementById("coins-input");
    if (coinsInput && !coinsInput.dataset.bound) {
      coinsInput.dataset.bound = "true";
      coinsInput.addEventListener("input", calculateWithdraw);
      coinsInput.addEventListener("keyup", calculateWithdraw);
      coinsInput.addEventListener("change", calculateWithdraw);
    }
  }

  function loadTonConnectSDK(callback) {
    if (window.TON_CONNECT_UI || window.TonConnectSDK) {
      if (callback) callback();
      return;
    }
    const script = document.createElement('script');
    script.src = "https://unpkg.com/@tonconnect/ui@latest/dist/tonconnect-ui.min.js";
    script.onload = () => { if (callback) callback(); };
    script.onerror = () => { console.error("فشل تحميل TonConnect SDK"); };
    document.head.appendChild(script);
  }

  function initTonConnect() {
    try {
      const TonConnectClass = window.TON_CONNECT_UI?.TonConnectUI || window.TonConnectSDK?.TonConnectUI;
      if (!TonConnectClass) {
        setTimeout(initTonConnect, 300);
        return;
      }
      if (!window.globalTonConnectUI) {
        window.globalTonConnectUI = new TonConnectClass({
          manifestUrl: window.location.origin + '/tonconnect-manifest.json'
        });
      }
      tonConnectUI = window.globalTonConnectUI;
      if (tonConnectUI.wallet) {
        updateWalletUI(tonConnectUI.wallet);
      } else {
        updateWalletUI(null);
      }
      tonConnectUI.onStatusChange(wallet => {
        updateWalletUI(wallet);
      });
    } catch (e) {
      console.error("خطأ تهيئة TonConnect:", e);
    }
  }

  async function connectWallet() {
    if (!tonConnectUI) initTonConnect();
    try {
      if (tonConnectUI) await tonConnectUI.openModal();
    } catch (e) {
      console.error("خطأ في فتح نافذة الربط:", e);
    }
  }

  function updateWalletUI(wallet) {
    const statusBadge = document.getElementById("wallet-connect-status");
    const walletBox = document.getElementById("connected-wallet-box");
    const addressDisplay = document.getElementById("wallet-address-display");
    const tonConnectBtnContainer = document.getElementById("ton-connect-button");

    if (wallet && wallet.account) {
      currentWalletAddress = wallet.account.address;
      if (statusBadge) {
        statusBadge.innerText = "متصل ✅";
        statusBadge.style.color = "#4ade80";
      }
      if (tonConnectBtnContainer) tonConnectBtnContainer.style.display = "none";
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
      if (tonConnectBtnContainer) {
        tonConnectBtnContainer.style.display = "block";
        tonConnectBtnContainer.innerHTML = `
          <button onclick="window.withdrawModule.connectWallet()" style="
            width: 100%;
            background: linear-gradient(135deg, #0088cc, #005588);
            color: #ffffff;
            border: none;
            padding: 12px 20px;
            border-radius: 12px;
            font-weight: bold;
            font-size: 15px;
            cursor: pointer;
            box-shadow: 0 4px 12px rgba(0, 136, 204, 0.3);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
          ">
            💎 ربط محفظة GRAM
          </button>
        `;
      }
    }
    calculateWithdraw();
  }

  async function disconnectWallet() {
    if (tonConnectUI && tonConnectUI.connected) {
      try { await tonConnectUI.disconnect(); } catch (e) { console.error("خطأ أثناء قطع الاتصال:", e); }
    } else {
      updateWalletUI(null);
    }
  }

  async function initWithdrawPage(userId) {
    const currentUid = userId || getUserId();
    bindInputEvents();
    try {
      const response = await fetch(`/api/wallet/withdraw/config?user_id=${currentUid}`);
      if (!response.ok) return;
      const data = await response.json();

      if (data.success) {
        withdrawConfig = data.config;
        gramPriceUSD = parseFloat(data.gram_price) || 0.01;
        userBalance = parseFloat(data.user_balance) || 0;
        withdrawCount = parseInt(data.withdraw_count) || 0;

        const userBalDisplay = document.getElementById("user-balance-display");
        if (userBalDisplay) userBalDisplay.innerText = `رصيدك: ${userBalance.toLocaleString()} ZN`;

        const feePercentDisplay = document.getElementById("fee-percent-display");
        if (feePercentDisplay && withdrawConfig.fee_percent) {
            feePercentDisplay.innerText = withdrawConfig.fee_percent;
        }

        if (withdrawConfig && withdrawConfig.levels) {
          activeLevelIndex = Math.min(withdrawCount, withdrawConfig.levels.length - 1);
        }

        const levelBadge = document.getElementById("level-indicator");
        if (levelBadge && withdrawConfig && withdrawConfig.levels) {
          levelBadge.innerText = `المستوى ${activeLevelIndex + 1}`;
        }

        renderLevelsGuide();
        setPreset('max');
      }
    } catch (err) {
      console.error("خطأ جلب إعدادات السحب:", err);
    }
  }

  function renderLevelsGuide() {
    const container = document.getElementById("levels-list-container");
    const userLevelText = document.getElementById("current-user-level-text");
    if (!withdrawConfig || !withdrawConfig.levels) return;

    if (userLevelText) userLevelText.innerText = `المستوى: ${activeLevelIndex + 1}`;
    if (!container) return;

    let html = "";
    withdrawConfig.levels.forEach((lvl, idx) => {
      const isActive = idx === activeLevelIndex;
      const maxText = lvl.max >= 999999999 ? "مفتوح" : lvl.max.toLocaleString() + " ZN";
      html += `
        <div class="level-item ${isActive ? 'active-level' : ''}" style="display:flex; justify-content:space-between; padding:10px; margin-bottom:6px; background:${isActive ? 'rgba(56, 189, 248, 0.15)' : 'rgba(255, 255, 255, 0.03)'}; border-radius:8px; border:${isActive ? '1px solid #38bdf8' : 'none'};">
          <div>
            <span>المستوى ${lvl.level}: </span>
            <strong>${lvl.min.toLocaleString()} - ${maxText}</strong>
          </div>
          <span class="level-item-tag" style="color:${isActive ? '#38bdf8' : '#888'};">
            ${isActive ? 'مستواك الحالي ✅' : 'المستوى ' + lvl.level}
          </span>
        </div>
      `;
    });
    container.innerHTML = html;
  }

  function setPreset(type) {
    if (!withdrawConfig || !withdrawConfig.levels || withdrawConfig.levels.length === 0) return;
    const currentLvl = withdrawConfig.levels[activeLevelIndex] || withdrawConfig.levels[0];
    const coinsInput = document.getElementById("coins-input");
    if (!coinsInput) return;

    let targetAmount = 0;
    const minVal = currentLvl.min;
    const levelMax = currentLvl.max >= 999999999 ? userBalance : currentLvl.max;
    const maxVal = Math.min(userBalance, levelMax);

    if (type === 'min') {
      targetAmount = minVal;
    } else if (type === 'half') {
      targetAmount = Math.floor((minVal + maxVal) / 2);
    } else if (type === 'max') {
      targetAmount = maxVal > 0 ? maxVal : minVal;
    }

    coinsInput.value = targetAmount;
    calculateWithdraw();
  }

  function calculateWithdraw() {
    const coinsInput = document.getElementById("coins-input");
    const coinsInputVal = parseInputValue(coinsInput?.value);
    const btn = document.getElementById("confirm-withdraw-btn");
    const levelBadge = document.getElementById("level-indicator");

    if (!withdrawConfig || !gramPriceUSD || coinsInputVal <= 0) {
      resetCalculations();
      if (btn) btn.disabled = true;
      if (levelBadge && withdrawConfig && withdrawConfig.levels) {
        const currentLvl = withdrawConfig.levels[activeLevelIndex] || withdrawConfig.levels[0];
        levelBadge.innerText = `المستوى ${currentLvl.level}`;
        levelBadge.style.color = "#38bdf8";
      }
      return;
    }

    const currentLvl = withdrawConfig.levels[activeLevelIndex] || withdrawConfig.levels[0];

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
      levelBadge.innerText = `المستوى ${currentLvl.level}`;
      levelBadge.style.color = "#38bdf8";
    }

    // الاعتماد على القيم من الفايربيس (100000 = 1 دولار)
    const usdRate = withdrawConfig.rate_coins_per_usd || 100000;
    const usdValue = coinsInputVal / usdRate;
    const grossGram = usdValue / gramPriceUSD;

    const feePercent = withdrawConfig.fee_percent || 3;
    const feeCoins = coinsInputVal * (feePercent / 100);
    const netCoins = coinsInputVal - feeCoins;
    const netUsd = netCoins / usdRate;
    
    // الصافي بدون خصم أي رسوم شبكة من المستخدم
    const finalNetGram = Math.max(0, netUsd / gramPriceUSD);

    const gramOutput = document.getElementById("gram-output");
    const feeAmount = document.getElementById("fee-amount");
    const netGramElem = document.getElementById("net-gram");

    if (gramOutput) gramOutput.value = grossGram.toFixed(4) + " GRAM";
    if (feeAmount) feeAmount.innerText = `${feeCoins.toLocaleString()} ZN`;
    if (netGramElem) netGramElem.innerText = `${finalNetGram.toFixed(4)} GRAM`;

    if (btn) btn.disabled = !currentWalletAddress || coinsInputVal <= 0 || userBalance < coinsInputVal;
  }

  function resetCalculations() {
    const gramOutput = document.getElementById("gram-output");
    const feeAmount = document.getElementById("fee-amount");
    const netGramElem = document.getElementById("net-gram");

    if (gramOutput) gramOutput.value = "0.0000 GRAM";
    if (feeAmount) feeAmount.innerText = "0 ZN";
    if (netGramElem) netGramElem.innerText = "0.0000 GRAM";
  }

  async function submitWithdrawal() {
    const coinsInput = document.getElementById("coins-input");
    const coins = parseInputValue(coinsInput?.value);
    const userId = getUserId();
    const btn = document.getElementById("confirm-withdraw-btn");

    if (!currentWalletAddress) { alert("يرجى ربط محفظة GRAM أولاً قبل تأكيد السحب!"); return; }
    if (coins <= 0) { alert("يرجى إدخال مبلغ سحب صحيح!"); return; }
    if (coins > userBalance) { alert("رصيدك الحالي غير كافٍ لإتمام هذه العملية!"); return; }

    if (btn) { btn.disabled = true; btn.innerText = "جاري معالجة الطلب..."; }

    try {
      const res = await fetch('/api/wallet/withdraw/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: userId, coins: coins, wallet_address: currentWalletAddress })
      });
      const data = await res.json();
      alert(data.message || (data.success ? "تم طلب السحب بنجاح!" : "فشلت العملية"));
      if (data.success) {
        if (typeof window.loadWalletData === 'function') window.loadWalletData();
        else location.reload();
      }
    } catch (err) {
      alert("حدث خطأ أثناء الاتصال بالخادم.");
    } finally {
      if (btn) { btn.innerText = "تأكيد السحب"; btn.disabled = false; }
    }
  }

  const withdrawModule = {
    init: function () {
      const userId = getUserId();
      loadTonConnectSDK(() => { initTonConnect(); });
      initWithdrawPage(userId);
    },
    connectWallet, setPreset, calculateWithdraw, disconnectWallet, submitWithdrawal
  };

  window.withdrawModule = withdrawModule;
  window.init_withdraw_module = function () { withdrawModule.init(); };
  window.connectWallet = connectWallet;
  window.setPreset = setPreset;
  window.calculateWithdraw = calculateWithdraw;
  window.disconnectWallet = disconnectWallet;
  window.submitWithdrawal = submitWithdrawal;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => withdrawModule.init());
  } else {
    withdrawModule.init();
  }
})();

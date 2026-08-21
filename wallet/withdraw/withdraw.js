(function () {
  let cryptoPrices = { DOGE: 0.12, TRX: 0.15, PEPE: 0.00001, LTC: 75.0 };
  let selectedCurrency = "DOGE";
  let withdrawConfig = null;
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

    const currencySelect = document.getElementById("currency-select");
    if (currencySelect && !currencySelect.dataset.bound) {
      currencySelect.dataset.bound = "true";
      currencySelect.addEventListener("change", (e) => {
        selectedCurrency = e.target.value.toUpperCase();
        calculateWithdraw();
      });
    }

    const walletInput = document.getElementById("wallet-address-input");
    if (walletInput && !walletInput.dataset.bound) {
      walletInput.dataset.bound = "true";
      walletInput.addEventListener("input", calculateWithdraw);
    }
  }

  async function initWithdrawPage(userId) {
    const currentUid = userId || getUserId();
    bindInputEvents();
    try {
      const response = await fetch(`/api/wallet/withdraw/config?user_id=${currentUid}`);
      if (!response.ok) {
        console.error("فشل الاتصال بـ API السحب:", response.status);
        return;
      }
      const data = await response.json();

      if (data.success) {
        withdrawConfig = data.config;
        if (data.crypto_prices) {
          cryptoPrices = data.crypto_prices;
        }
        userBalance = parseFloat(data.user_balance) || 0;
        withdrawCount = parseInt(data.withdraw_count) || 0;

        const userBalDisplay = document.getElementById("user-balance-display");
        if (userBalDisplay) {
          userBalDisplay.innerText = `رصيدك: ${userBalance.toLocaleString()} ZN`;
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

    if (userLevelText) {
      userLevelText.innerText = `المستوى: ${activeLevelIndex + 1}`;
    }

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

  function selectCurrency(curr) {
    selectedCurrency = curr.toUpperCase();
    const currencySelect = document.getElementById("currency-select");
    if (currencySelect) currencySelect.value = selectedCurrency;
    calculateWithdraw();
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
    const walletInput = document.getElementById("wallet-address-input");
    const coinsInputVal = parseInputValue(coinsInput?.value);
    const walletAddress = walletInput?.value?.trim() || "";
    const btn = document.getElementById("confirm-withdraw-btn");
    const levelBadge = document.getElementById("level-indicator");

    const priceUSD = cryptoPrices[selectedCurrency] || 1.0;

    if (!withdrawConfig || coinsInputVal <= 0) {
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

    // معادلة تحويل ZN إلى USD (100,000 ZN = $1.00 USD)
    const usdRate = withdrawConfig.rate_coins_per_usd || 100000;
    const grossUsdValue = coinsInputVal / usdRate;
    const grossCrypto = grossUsdValue / priceUSD;

    // خصم الرسوم (3%)
    const feePercent = withdrawConfig.fee_percent || 3;
    const feeCoins = coinsInputVal * (feePercent / 100);
    const netCoins = coinsInputVal - feeCoins;
    const netUsd = netCoins / usdRate;
    
    // الصافي النهائي للعملة المشفرة المستلمة
    const finalNetCrypto = netUsd / priceUSD;

    const cryptoOutput = document.getElementById("crypto-output");
    const feeAmount = document.getElementById("fee-amount");
    const netCryptoElem = document.getElementById("net-crypto");

    if (cryptoOutput) cryptoOutput.value = `${grossCrypto.toFixed(6)} ${selectedCurrency}`;
    if (feeAmount) feeAmount.innerText = `${feeCoins.toLocaleString()} ZN (3%)`;
    if (netCryptoElem) netCryptoElem.innerText = `${finalNetCrypto.toFixed(6)} ${selectedCurrency}`;

    if (btn) {
      btn.disabled = !walletAddress || coinsInputVal <= 0 || userBalance < coinsInputVal;
    }
  }

  function resetCalculations() {
    const cryptoOutput = document.getElementById("crypto-output");
    const feeAmount = document.getElementById("fee-amount");
    const netCryptoElem = document.getElementById("net-crypto");

    if (cryptoOutput) cryptoOutput.value = `0.000000 ${selectedCurrency}`;
    if (feeAmount) feeAmount.innerText = "0 ZN";
    if (netCryptoElem) netCryptoElem.innerText = `0.000000 ${selectedCurrency}`;
  }

  async function submitWithdrawal() {
    const coinsInput = document.getElementById("coins-input");
    const walletInput = document.getElementById("wallet-address-input");
    const coins = parseInputValue(coinsInput?.value);
    const walletAddress = walletInput?.value?.trim();
    const userId = getUserId();
    const btn = document.getElementById("confirm-withdraw-btn");

    if (!walletAddress) {
      alert("يرجى إدخال عنوان أو بريد FaucetPay الإلكتروني أولاً!");
      return;
    }

    if (coins <= 0) {
      alert("يرجى إدخال مبلغ سحب صحيح!");
      return;
    }

    if (coins > userBalance) {
      alert("رصيدك الحالي غير كافٍ لإتمام هذه العملية!");
      return;
    }

    if (btn) {
      btn.disabled = true;
      btn.innerText = "جاري معالجة الطلب...";
    }

    try {
      const res = await fetch('/api/wallet/withdraw/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          coins: coins,
          currency: selectedCurrency,
          wallet_address: walletAddress
        })
      });
      
      const data = await res.json();
      alert(data.message || (data.success ? "تم طلب السحب بنجاح!" : "فشلت العملية"));
      if (data.success) {
        if (typeof window.loadWalletData === 'function') {
          window.loadWalletData();
        } else {
          location.reload();
        }
      }
    } catch (err) {
      alert("حدث خطأ أثناء الاتصال بالخادم.");
    } finally {
      if (btn) {
        btn.innerText = "تأكيد السحب";
        btn.disabled = false;
      }
    }
  }

  const withdrawModule = {
    init: function () {
      const userId = getUserId();
      initWithdrawPage(userId);
    },
    selectCurrency: selectCurrency,
    setPreset: setPreset,
    calculateWithdraw: calculateWithdraw,
    submitWithdrawal: submitWithdrawal
  };

  window.withdrawModule = withdrawModule;
  window.init_withdraw_module = function () {
    withdrawModule.init();
  };

  window.selectCurrency = selectCurrency;
  window.setPreset = setPreset;
  window.calculateWithdraw = calculateWithdraw;
  window.submitWithdrawal = submitWithdrawal;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => withdrawModule.init());
  } else {
    withdrawModule.init();
  }
})();

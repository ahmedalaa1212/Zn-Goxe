(function () {
  let cryptoPrices = { DOGE: 0.10, TRX: 0.12, PEPE: 0.000008, LTC: 70.0 };
  let selectedCurrency = "DOGE";
  let withdrawConfig = null;
  let userBalance = 0;
  let userLevel = 1;
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

  async function fetchLivePrices() {
    try {
      const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=dogecoin,tron,pepe,litecoin&vs_currencies=usd');
      const data = await res.json();
      if (data) {
        if (data.dogecoin?.usd) cryptoPrices.DOGE = data.dogecoin.usd;
        if (data.tron?.usd) cryptoPrices.TRX = data.tron.usd;
        if (data.pepe?.usd) cryptoPrices.PEPE = data.pepe.usd;
        if (data.litecoin?.usd) cryptoPrices.LTC = data.litecoin.usd;
      }
    } catch (e) {
      console.log('استخدام الأسعار الاحتياطية عند تعذر الجلب اللحظي');
    }
    updatePriceDisplay();
  }

  function updatePriceDisplay() {
    const priceDisplay = document.getElementById('coin-price-display');
    if (priceDisplay) {
      const price = cryptoPrices[selectedCurrency] || 1;
      priceDisplay.innerText = `$${price} USD`;
    }
  }

  function bindInputEvents() {
    const coinsInput = document.getElementById("coins-input");
    if (coinsInput && !coinsInput.dataset.bound) {
      coinsInput.dataset.bound = "true";
      coinsInput.addEventListener("input", calculateWithdraw);
      coinsInput.addEventListener("keyup", calculateWithdraw);
      coinsInput.addEventListener("change", calculateWithdraw);
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
    await fetchLivePrices();

    try {
      let response = await fetch(`/api/wallet/withdraw/config?user_id=${currentUid}`);
      if (!response.ok) {
        response = await fetch(`/api/withdraw/config?user_id=${currentUid}`);
      }
      if (!response.ok) {
        console.error("فشل الاتصال بـ API السحب:", response.status);
        return;
      }
      const data = await response.json();

      if (data.success || data.config) {
        withdrawConfig = data.config || data;
        if (data.crypto_prices) {
          cryptoPrices = { ...cryptoPrices, ...data.crypto_prices };
          updatePriceDisplay();
        }
        
        userBalance = parseFloat(data.user_balance ?? data.user?.balance) || 0;
        userLevel = parseInt(data.user_level ?? data.user?.current_level) || 1;
        withdrawCount = parseInt(data.withdraw_count) || (userLevel - 1);

        const userBalDisplay = document.getElementById("user-balance-display");
        if (userBalDisplay) {
          userBalDisplay.innerText = `رصيدك: ${userBalance.toLocaleString()} ZN`;
        }

        if (withdrawConfig && withdrawConfig.levels) {
          activeLevelIndex = withdrawConfig.levels.findIndex(l => l.level === userLevel);
          if (activeLevelIndex === -1) {
            activeLevelIndex = Math.min(withdrawCount, withdrawConfig.levels.length - 1);
          }
        }

        const levelBadge = document.getElementById("level-indicator");
        if (levelBadge) {
          levelBadge.innerText = `المستوى ${userLevel}`;
        }

        renderLevelsGuide();
        calculateWithdraw();
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
      userLevelText.innerText = `المستوى: ${userLevel}`;
    }

    if (!container) return;

    let html = "";
    withdrawConfig.levels.forEach((lvl, idx) => {
      const isActive = lvl.level === userLevel || idx === activeLevelIndex;
      const typeText = lvl.type === 'auto' ? 'فوري آلي' : 'موافقة أدمن';
      const usdMin = (lvl.min / 100000).toFixed(4);
      const usdMax = lvl.max >= 999999999 ? "مفتوح" : `$${(lvl.max / 100000).toFixed(2)}`;
      const maxText = lvl.max >= 999999999 ? "مفتوح" : lvl.max.toLocaleString() + " ZN";

      html += `
        <div class="level-item ${isActive ? 'active-level' : ''}">
          <div>
            <span>المستوى ${lvl.level}: ${lvl.min.toLocaleString()} - ${maxText}</span>
            <br><small style="color:#94a3b8;">($${usdMin} - ${usdMax})</small>
          </div>
          <span class="level-item-tag" style="color:${isActive ? '#38bdf8' : '#888'};">
            ${isActive ? 'مستواك الحالي ✅' : typeText}
          </span>
        </div>
      `;
    });

    container.innerHTML = html;
  }

  function selectCurrency(curr) {
    selectedCurrency = curr.toUpperCase();
    
    document.querySelectorAll('.currency-btn').forEach(btn => btn.classList.remove('selected'));
    const selectedBtn = document.getElementById(`coin-${selectedCurrency}`);
    if (selectedBtn) selectedBtn.classList.add('selected');

    const label = document.getElementById('selected-coin-label');
    if (label) label.innerText = selectedCurrency;

    updatePriceDisplay();
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
      targetAmount = Math.floor(maxVal / 2);
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
    const currentLvl = withdrawConfig?.levels ? (withdrawConfig.levels[activeLevelIndex] || withdrawConfig.levels[0]) : null;

    if (!withdrawConfig || coinsInputVal <= 0) {
      resetCalculations();
      if (btn) btn.disabled = true;
      if (levelBadge) {
        levelBadge.innerText = `المستوى ${userLevel}`;
        levelBadge.style.color = "#38bdf8";
      }
      return;
    }

    if (userBalance < coinsInputVal) {
      if (levelBadge) {
        levelBadge.innerText = "الرصيد غير كافٍ ❌";
        levelBadge.style.color = "#ef4444";
      }
      resetCalculations();
      if (btn) btn.disabled = true;
      return;
    }

    if (levelBadge) {
      levelBadge.innerText = `المستوى ${userLevel}`;
      levelBadge.style.color = "#38bdf8";
    }

    // معادلة تحويل ZN إلى USD (100,000 ZN = $1.00 USD)
    const usdRate = withdrawConfig.rate_coins_per_usd || 100000;
    const grossUsdValue = coinsInputVal / usdRate;

    // خصم الرسوم (3%)
    const feePercent = withdrawConfig.fee_percent || 3;
    const feeCoins = coinsInputVal * (feePercent / 100);
    const netCoins = coinsInputVal - feeCoins;
    const netUsd = netCoins / usdRate;
    
    // الصافي النهائي للعملة المشفرة المستلمة
    const finalNetCrypto = netUsd / priceUSD;
    const decimals = selectedCurrency === 'PEPE' ? 2 : 8;

    const usdOutput = document.getElementById("usd-output");
    const feeAmount = document.getElementById("fee-amount");
    const netCryptoElem = document.getElementById("net-crypto");

    if (usdOutput) usdOutput.value = `$${grossUsdValue.toFixed(4)} USD`;
    if (feeAmount) feeAmount.innerText = `${Math.round(feeCoins).toLocaleString()} ZN (${feePercent}%)`;
    if (netCryptoElem) netCryptoElem.innerText = `${finalNetCrypto.toFixed(decimals)} ${selectedCurrency}`;

    if (btn) {
      const isMinOk = currentLvl ? coinsInputVal >= currentLvl.min : true;
      const isMaxOk = currentLvl ? coinsInputVal <= currentLvl.max : true;
      const isValidAddress = walletAddress.length >= 5;
      
      btn.disabled = !(isMinOk && isMaxOk && isValidAddress && userBalance >= coinsInputVal);
    }
  }

  function resetCalculations() {
    const usdOutput = document.getElementById("usd-output");
    const feeAmount = document.getElementById("fee-amount");
    const netCryptoElem = document.getElementById("net-crypto");

    if (usdOutput) usdOutput.value = "$0.0000 USD";
    if (feeAmount) feeAmount.innerText = "0 ZN";
    if (netCryptoElem) netCryptoElem.innerText = `0.00000000 ${selectedCurrency}`;
  }

  async function submitWithdrawal() {
    const coinsInput = document.getElementById("coins-input");
    const walletInput = document.getElementById("wallet-address-input");
    const coins = parseInputValue(coinsInput?.value);
    const walletAddress = walletInput?.value?.trim();
    const userId = getUserId();
    const btn = document.getElementById("confirm-withdraw-btn");

    if (!walletAddress) {
      alert("يرجى إدخال عنوان المحفظة أو البريد الإلكتروني أولاً!");
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
      let res = await fetch('/api/wallet/withdraw/request', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          coins: coins,
          currency: selectedCurrency,
          wallet_address: walletAddress,
          coin_price_usd: cryptoPrices[selectedCurrency]
        })
      });

      if (!res.ok) {
        res = await fetch('/api/withdraw/request', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            coins_amount: coins,
            currency: selectedCurrency,
            wallet_address: walletAddress,
            coin_price_usd: cryptoPrices[selectedCurrency]
          })
        });
      }
      
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

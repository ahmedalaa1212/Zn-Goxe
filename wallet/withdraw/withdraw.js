(function () {
  let znxPriceUsd = 0.000010; // سعر افتراضي حتى يتم الجلب
  let userBalance = 0;
  let userWallet = "";
  const feePercent = 5; // 5% رسوم السحب

  function parseInputValue(val) {
    if (val === null || val === undefined) return 0;
    const cleanStr = val.toString().replace(/,/g, '').trim();
    const num = parseFloat(cleanStr);
    return isNaN(num) ? 0 : num;
  }

  function formatUSD(num) {
    if (!num || isNaN(num)) return "0.00";
    return parseFloat(num).toFixed(4);
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

  function validateWalletAddress(address) {
    if (!address || typeof address !== 'string') {
      return { valid: false, message: "⚠️ يرجى إدخال عنوان محفظة تلجرام الصحيح." };
    }
    const addr = address.trim();
    if (addr.length < 10) {
      return { valid: false, message: "⚠️ عنوان المحفظة قصير جدًا وغير صحيح." };
    }
    return { valid: true, message: "" };
  }

  async function fetchLivePrices() {
    try {
      let res = await fetch(`/api/wallet/withdraw/config?user_id=${getUserId()}`);
      if (!res.ok) {
        res = await fetch(`/api/withdraw/config?user_id=${getUserId()}`);
      }
      if (res.ok) {
        const data = await res.json();
        if (data && data.znx_price) {
          znxPriceUsd = parseFloat(data.znx_price) || znxPriceUsd;
        }
      }
    } catch (e) {
      console.log('استخدام سعر ZNX الإفتراضي');
    }
    updatePriceDisplay();
  }

  function updatePriceDisplay() {
    const priceDisplay = document.getElementById('coin-price-display');
    const statusDisplay = document.getElementById('rate-status');
    const priceStr = `$${znxPriceUsd < 0.001 ? znxPriceUsd.toFixed(6) : znxPriceUsd.toFixed(4)} USD`;
    
    if (priceDisplay) priceDisplay.innerText = priceStr;
    if (statusDisplay) statusDisplay.innerText = `السعر اللحظي: ${priceStr} ⚡`;
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

  function updateWalletDisplay() {
    const hiddenInput = document.getElementById("wallet-address-input");
    const displayDiv = document.getElementById("wallet-address-display");
    const connectBtn = document.getElementById("btn-connect-wallet");

    if (hiddenInput) hiddenInput.value = userWallet;

    if (userWallet && userWallet.length > 0) {
      if (displayDiv) {
        displayDiv.innerText = userWallet;
        displayDiv.style.display = "block";
      }
      if (connectBtn) {
        connectBtn.innerHTML = "✏️ تعديل المحفظة";
      }
    } else {
      if (displayDiv) {
        displayDiv.innerText = "";
        displayDiv.style.display = "none";
      }
      if (connectBtn) {
        connectBtn.innerHTML = "🔗 ربط محفظة تلجرام";
      }
    }

    calculateWithdraw();
  }

  async function initWithdrawPage(userId) {
    const currentUid = userId || getUserId();
    bindInputEvents();

    try {
      let response = await fetch(`/api/wallet/withdraw/config?user_id=${currentUid}`);
      if (!response.ok) {
        response = await fetch(`/api/withdraw/config?user_id=${currentUid}`);
      }
      if (response.ok) {
        const data = await response.json();
        userBalance = parseFloat(data.user_balance || data.zn_balance || 0);
        userWallet = data.wallet_address || (data.wallets && data.wallets.ZNX) || "";
        if (data.znx_price) znxPriceUsd = parseFloat(data.znx_price);

        updateUIBalance();
        updatePriceDisplay();
        updateWalletDisplay();
      }
    } catch (err) {
      console.error("خطأ جلب بيانات السحب:", err);
    }
  }

  function updateUIBalance() {
    const userBalDisplay = document.getElementById("user-balance-display");
    if (userBalDisplay) {
      userBalDisplay.innerText = `رصيدك: ${userBalance.toLocaleString()} ZNX`;
    }
  }

  function setPreset(type) {
    const coinsInput = document.getElementById("coins-input");
    if (!coinsInput) return;

    if (type === 'max') {
      coinsInput.value = userBalance;
    }
    calculateWithdraw();
  }

  function openWalletModal() {
    const modal = document.getElementById("wallet-modal");
    const modalInput = document.getElementById("modal-wallet-input");

    if (modalInput) {
      modalInput.value = userWallet;
    }

    if (modal) {
      modal.classList.add("active");
    }
  }

  function closeWalletModal() {
    const modal = document.getElementById("wallet-modal");
    if (modal) {
      modal.classList.remove("active");
    }
  }

  async function saveWalletAddress() {
    const modalInput = document.getElementById("modal-wallet-input");
    const val = modalInput ? modalInput.value.trim() : "";
    const userId = getUserId();

    const check = validateWalletAddress(val);
    if (!check.valid) {
      alert(check.message);
      return;
    }

    try {
      let res = await fetch('/api/wallet/withdraw/save-wallet', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          currency: 'ZNX',
          wallet_address: val
        })
      });

      const data = await res.json().catch(() => null);

      if (res.ok && data?.success) {
        userWallet = val;
        updateWalletDisplay();
        closeWalletModal();
      } else {
        alert(data?.message || "حدث خطأ أثناء حفظ المحفظة.");
      }
    } catch (e) {
      console.error(e);
      alert("تعذر الاتصال بالخادم لحفظ المحفظة.");
    }
  }

  function calculateWithdraw() {
    const coinsInput = document.getElementById("coins-input");
    const walletInput = document.getElementById("wallet-address-input");
    const coinsVal = parseInputValue(coinsInput?.value);
    const walletAddress = walletInput?.value?.trim() || "";
    const btn = document.getElementById("confirm-withdraw-btn");

    const usdOutput = document.getElementById("usd-output");
    const feeAmount = document.getElementById("fee-amount");
    const netCryptoElem = document.getElementById("net-crypto");

    if (coinsVal <= 0) {
      resetCalculations();
      if (btn) btn.disabled = true;
      return;
    }

    if (coinsVal > userBalance) {
      resetCalculations();
      if (btn) btn.disabled = true;
      return;
    }

    const feeCoins = coinsVal * (feePercent / 100);
    const netCoins = coinsVal - feeCoins;
    const usdValue = coinsVal * znxPriceUsd;

    if (usdOutput) usdOutput.value = `$${formatUSD(usdValue)} USD`;
    if (feeAmount) feeAmount.innerText = `${Math.round(feeCoins).toLocaleString()} ZNX (${feePercent}%)`;
    if (netCryptoElem) netCryptoElem.innerText = `${netCoins.toLocaleString()} ZNX`;

    if (btn) {
      const addrCheck = validateWalletAddress(walletAddress);
      btn.disabled = !(coinsVal > 0 && coinsVal <= userBalance && addrCheck.valid);
    }
  }

  function resetCalculations() {
    const usdOutput = document.getElementById("usd-output");
    const feeAmount = document.getElementById("fee-amount");
    const netCryptoElem = document.getElementById("net-crypto");

    if (usdOutput) usdOutput.value = "$0.00 USD";
    if (feeAmount) feeAmount.innerText = "0 ZNX";
    if (netCryptoElem) netCryptoElem.innerText = "0 ZNX";
  }

  async function submitWithdrawal(event) {
    if (event) event.preventDefault();

    const coinsInput = document.getElementById("coins-input");
    const walletInput = document.getElementById("wallet-address-input");
    const coins = parseInputValue(coinsInput?.value);
    const walletAddress = walletInput?.value?.trim();
    const userId = getUserId();
    const btn = document.getElementById("confirm-withdraw-btn");

    if (!walletAddress) {
      alert("⚠️ يرجى ربط محفظة تلجرام أولاً!");
      return;
    }

    if (coins <= 0) {
      alert("يرجى إدخال مبلغ سحب صحيح!");
      return;
    }

    if (coins > userBalance) {
      alert("رصيدك الحالي غير كافٍ لإتمام العملية!");
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
          currency: 'ZNX',
          wallet_address: walletAddress
        })
      });

      const data = await res.json().catch(() => null);

      if (data && data.success) {
        alert(data.message || "تم تقديم طلب السحب بنجاح!");
        userBalance = data.new_balance !== undefined ? data.new_balance : (userBalance - coins);
        if (coinsInput) coinsInput.value = "";
        updateUIBalance();
        resetCalculations();
      } else {
        alert(data?.message || "حدث خطأ أثناء تقديم الطلب.");
      }
    } catch (err) {
      console.error(err);
      alert("حدث خطأ أثناء الاتصال بالخادم.");
    } finally {
      if (btn) {
        btn.innerText = "تأكيد السحب";
        calculateWithdraw();
      }
    }
  }

  const withdrawModule = {
    init: function () {
      initWithdrawPage(getUserId());
      fetchLivePrices();
    },
    setPreset: setPreset,
    calculateWithdraw: calculateWithdraw,
    submitWithdrawal: submitWithdrawal,
    openWalletModal: openWalletModal,
    closeWalletModal: closeWalletModal,
    saveWalletAddress: saveWalletAddress
  };

  window.withdrawModule = withdrawModule;
  window.init_withdraw_module = function () {
    withdrawModule.init();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => withdrawModule.init());
  } else {
    withdrawModule.init();
  }
})();

(function () {
  let userBalance = 0;
  let usdBalance = 0;
  let userWallet = "";
  let minWithdraw = 1000;
  let fixedFeeUsd = 0.02;
  let currentTierName = "الشريحة الأولى";
  let tonConnectUI = null;

  function parseInputValue(val) {
    if (val === null || val === undefined) return 0;
    const cleanStr = val.toString().replace(/,/g, '').trim();
    const num = parseFloat(cleanStr);
    return isNaN(num) ? 0 : num;
  }

  function formatCryptoSmartRaw(val) {
    if (val === null || val === undefined || isNaN(val)) return "0";
    const num = parseFloat(val);
    if (num <= 0) return "0";

    if (num >= 100) {
      return Math.floor(num).toString();
    } else if (num >= 50) {
      return parseFloat(num.toFixed(2)).toString();
    } else {
      return parseFloat(num.toFixed(4)).toString();
    }
  }

  function formatCryptoSmartHtml(val) {
    const raw = formatCryptoSmartRaw(val);
    const parts = raw.split('.');
    if (parts.length > 1 && parts[1]) {
      return `${parts[0]}<span style="font-size: 0.8em; opacity: 0.75; font-weight: normal;">.${parts[1]}</span>`;
    }
    return raw;
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
      return { valid: false, message: "⚠️ يرجى اختيار محفظة TON الصحيحة." };
    }
    const addr = address.trim();
    const tonRegex = /^(EQ|UQ|0:)[a-zA-Z0-9_-]{46,48}$/;
    if (!tonRegex.test(addr)) {
      return { valid: false, message: "⚠️ عنوان المحفظة غير صحيح! يجب أن يكون عنوان TON صالحاً يبدأ بـ EQ أو UQ وطوله 48 حرفاً." };
    }
    return { valid: true, message: "" };
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

  async function initTonConnect() {
    if (window.tonConnectInstance) {
      tonConnectUI = window.tonConnectInstance;
      return;
    }

    if (typeof TON_CONNECT_UI === 'undefined') {
      await new Promise((resolve) => {
        const script = document.createElement('script');
        script.src = "https://unpkg.com/@tonconnect/ui@latest/dist/tonconnect-ui.min.js";
        script.onload = resolve;
        script.onerror = resolve;
        document.head.appendChild(script);
      });
    }

    if (typeof TON_CONNECT_UI !== 'undefined') {
      try {
        let hiddenRoot = document.getElementById('ton-connect-hidden-root');
        if (!hiddenRoot) {
          hiddenRoot = document.createElement('div');
          hiddenRoot.id = 'ton-connect-hidden-root';
          hiddenRoot.style.display = 'none';
          document.body.appendChild(hiddenRoot);
        }

        const manifestUrl = window.location.origin + '/tonconnect-manifest.json';
        tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
          manifestUrl: manifestUrl,
          buttonRootId: 'ton-connect-hidden-root'
        });

        window.tonConnectInstance = tonConnectUI;

        tonConnectUI.onStatusChange(async (wallet) => {
          if (wallet && wallet.account) {
            let addr = wallet.account.address;
            try {
              if (TON_CONNECT_UI.toUserFriendlyAddress) {
                addr = TON_CONNECT_UI.toUserFriendlyAddress(addr);
              }
            } catch (e) {}

            userWallet = addr;
            updateWalletDisplay();
            await saveWalletToServer(addr);
          }
        });
      } catch (e) {
        console.warn("TONConnect initialization warning:", e);
      }
    }
  }

  async function connectTonWallet() {
    if (!tonConnectUI) {
      await initTonConnect();
    }

    if (tonConnectUI) {
      try {
        if (tonConnectUI.connected) {
          await tonConnectUI.disconnect();
        }
        await tonConnectUI.openModal();
      } catch (e) {
        console.error("خطأ فتح نافذة المحافظ:", e);
        openWalletModal();
      }
    } else {
      openWalletModal();
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
        connectBtn.innerHTML = "✏️ تغيير / قطع اتصال محفظة TON";
      }
    } else {
      if (displayDiv) {
        displayDiv.innerText = "";
        displayDiv.style.display = "none";
      }
      if (connectBtn) {
        connectBtn.innerHTML = "🔗 ربط محفظة TON (Telegram / Tonkeeper)";
      }
    }

    calculateWithdraw();
  }

  async function saveWalletToServer(val) {
    const userId = getUserId();
    const check = validateWalletAddress(val);
    if (!check.valid) return false;

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
        return true;
      }
    } catch (e) {
      console.error("خطأ حفظ المحفظة بالخادم:", e);
    }
    return false;
  }

  function syncBalanceFromGlobal() {
    let currentZnx = null;
    let currentUsd = null;

    if (window.userState && window.userState.znx_balance !== undefined) {
      currentZnx = parseFloat(window.userState.znx_balance);
    } else if (window.PlayerData && window.PlayerData.znx_balance !== undefined) {
      currentZnx = parseFloat(window.PlayerData.znx_balance);
    }

    if (window.userState && window.userState.usd_balance !== undefined) {
      currentUsd = parseFloat(window.userState.usd_balance);
    }

    if (currentZnx !== null && !isNaN(currentZnx) && currentZnx !== userBalance) {
      userBalance = currentZnx;
      updateUIBalance();
      calculateWithdraw();
    }

    if (currentUsd !== null && !isNaN(currentUsd) && currentUsd !== usdBalance) {
      usdBalance = currentUsd;
      updateUIBalance();
      calculateWithdraw();
    }
  }

  async function initWithdrawPage(userId) {
    const currentUid = userId || getUserId();
    bindInputEvents();
    initTonConnect();

    try {
      let response = await fetch(`/api/wallet/withdraw/config?user_id=${currentUid}`);
      if (!response.ok) {
        response = await fetch(`/api/withdraw/config?user_id=${currentUid}`);
      }
      if (response.ok) {
        const data = await response.json();
        userBalance = parseFloat(data.znx_balance ?? data.user_balance ?? 0);
        usdBalance = parseFloat(data.usd_balance ?? 0);
        userWallet = data.wallet_address || (data.wallets && data.wallets.ZNX) || "";
        
        if (data.min_withdraw_znx !== undefined) minWithdraw = parseFloat(data.min_withdraw_znx);
        if (data.fixed_fee_usd !== undefined) fixedFeeUsd = parseFloat(data.fixed_fee_usd);
        if (data.current_tier && data.current_tier.name) currentTierName = data.current_tier.name;

        if (window.userState) {
          window.userState.znx_balance = userBalance;
          window.userState.usd_balance = usdBalance;
        }

        updateUIBalance();
        updateWalletDisplay();
      }
    } catch (err) {
      console.error("خطأ جلب بيانات السحب:", err);
    }

    window.addEventListener('userStateUpdated', syncBalanceFromGlobal);
    if (window.withdrawBalanceInterval) clearInterval(window.withdrawBalanceInterval);
    window.withdrawBalanceInterval = setInterval(syncBalanceFromGlobal, 2000);
  }

  function updateUIBalance() {
    const userBalDisplay = document.getElementById("user-balance-display");
    const usdBalDisplay = document.getElementById("usd-balance-display");
    const minInfo = document.getElementById("min-withdraw-info");
    const feeInfo = document.getElementById("fee-amount");
    const tierBadge = document.getElementById("tier-badge");

    if (userBalDisplay) userBalDisplay.innerHTML = `رصيدك: ${formatCryptoSmartHtml(userBalance)} ZNX`;
    if (usdBalDisplay) usdBalDisplay.innerText = `$${usdBalance.toFixed(2)} USD`;
    if (minInfo) minInfo.innerText = `الحد الأدنى: ${minWithdraw} ZNX`;
    if (feeInfo) feeInfo.innerText = `$${fixedFeeUsd.toFixed(2)} USD (من رصيد الدولار)`;
    if (tierBadge) tierBadge.innerText = currentTierName;
  }

  function setPreset(type) {
    const coinsInput = document.getElementById("coins-input");
    if (!coinsInput) return;

    if (type === 'max') {
      const safeBal = Math.max(0, parseFloat(userBalance) || 0);
      coinsInput.value = safeBal > 0 ? formatCryptoSmartRaw(safeBal) : "";
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

  function openFeeNoticeModal(requiredFee) {
    const modal = document.getElementById("fee-notice-modal");
    const reqFeeElem = document.getElementById("modal-required-fee");
    const curUsdElem = document.getElementById("modal-current-usd");

    if (reqFeeElem) reqFeeElem.innerText = requiredFee.toFixed(2);
    if (curUsdElem) curUsdElem.innerText = usdBalance.toFixed(2);

    if (modal) {
      modal.classList.add("active");
    }
  }

  function closeFeeNoticeModal() {
    const modal = document.getElementById("fee-notice-modal");
    if (modal) {
      modal.classList.remove("active");
    }
  }

  function goToDeposit() {
    closeFeeNoticeModal();
    if (typeof window.switchTab === 'function') {
      window.switchTab('deposit');
    } else {
      const depositTabBtn = document.querySelector('[onclick*="deposit"], [data-tab="deposit"]');
      if (depositTabBtn) depositTabBtn.click();
      else alert("يرجى الانتقال لصفحة الإيداع لتعبئة رصيد الدولار ($0.02 USD).");
    }
  }

  async function saveWalletAddress() {
    const modalInput = document.getElementById("modal-wallet-input");
    const val = modalInput ? modalInput.value.trim() : "";

    const check = validateWalletAddress(val);
    if (!check.valid) {
      alert(check.message);
      return;
    }

    const saved = await saveWalletToServer(val);
    if (saved) {
      closeWalletModal();
    } else {
      alert("حدث خطأ أثناء حفظ المحفظة.");
    }
  }

  function calculateWithdraw() {
    const coinsInput = document.getElementById("coins-input");
    const walletInput = document.getElementById("wallet-address-input");
    const coinsVal = parseInputValue(coinsInput?.value);
    const walletAddress = walletInput?.value?.trim() || userWallet;
    const btn = document.getElementById("confirm-withdraw-btn");

    const netCryptoElem = document.getElementById("net-crypto");

    if (coinsVal <= 0 || coinsVal > userBalance + 0.0001) {
      resetCalculations();
      if (btn) btn.disabled = true;
      return;
    }

    if (netCryptoElem) netCryptoElem.innerHTML = `${formatCryptoSmartHtml(coinsVal)} ZNX`;

    if (btn) {
      const addrCheck = validateWalletAddress(walletAddress);
      const isEnoughCoins = coinsVal >= minWithdraw && coinsVal <= userBalance + 0.0001;
      btn.disabled = !(isEnoughCoins && addrCheck.valid);
    }
  }

  function resetCalculations() {
    const netCryptoElem = document.getElementById("net-crypto");
    if (netCryptoElem) netCryptoElem.innerHTML = '0<span style="font-size: 0.8em; opacity: 0.75; font-weight: normal;">.0000</span> ZNX';
  }

  async function submitWithdrawal(event) {
    if (event) event.preventDefault();

    const coinsInput = document.getElementById("coins-input");
    const walletInput = document.getElementById("wallet-address-input");
    const coins = parseInputValue(coinsInput?.value);
    const walletAddress = walletInput?.value?.trim() || userWallet;
    const userId = getUserId();
    const btn = document.getElementById("confirm-withdraw-btn");

    if (!walletAddress) {
      alert("⚠️ يرجى ربط محفظة TON أولاً!");
      return;
    }

    const addrCheck = validateWalletAddress(walletAddress);
    if (!addrCheck.valid) {
      alert(addrCheck.message);
      return;
    }

    if (coins < minWithdraw) {
      alert(`⚠️ الحد الأدنى للسحب لهذه الشريحة هو ${minWithdraw} ZNX.`);
      return;
    }

    if (coins > userBalance + 0.0001) {
      alert("رصيدك الحالي من ZNX غير كافٍ لإتمام العملية!");
      return;
    }

    if (usdBalance < fixedFeeUsd) {
      openFeeNoticeModal(fixedFeeUsd);
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
        userBalance = data.new_balance !== undefined ? parseFloat(data.new_balance) : (userBalance - coins);
        usdBalance = data.new_usd_balance !== undefined ? parseFloat(data.new_usd_balance) : Math.max(0, usdBalance - fixedFeeUsd);
        
        // تحديث الحالات العالمية فوراً بدون انتظار التحديث التلقائي
        if (window.userState) {
          window.userState.znx_balance = userBalance;
          window.userState.usd_balance = usdBalance;
        }
        if (window.PlayerData) {
          window.PlayerData.znx_balance = userBalance;
          window.PlayerData.usd_balance = usdBalance;
        }

        window.dispatchEvent(new Event('userStateUpdated'));

        if (coinsInput) coinsInput.value = "";
        updateUIBalance();
        resetCalculations();
      } else if (data && data.code === "INSUFFICIENT_USD") {
        openFeeNoticeModal(data.fee_required || fixedFeeUsd);
      } else {
        alert(data?.message || "حدث خطأ أثناء تقديم الطلب.");
      }
    } catch (err) {
      console.error("خطأ أثناء إرسال طلب السحب:", err);
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
    },
    setPreset: setPreset,
    calculateWithdraw: calculateWithdraw,
    submitWithdrawal: submitWithdrawal,
    connectTonWallet: connectTonWallet,
    openWalletModal: openWalletModal,
    closeWalletModal: closeWalletModal,
    openFeeNoticeModal: openFeeNoticeModal,
    closeFeeNoticeModal: closeFeeNoticeModal,
    goToDeposit: goToDeposit,
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

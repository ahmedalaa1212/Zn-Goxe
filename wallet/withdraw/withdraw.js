(function () {
  let userBalance = 0;
  let userWallet = "";
  const feePercent = 5;
  let tonConnectUI = null;

  function parseInputValue(val) {
    if (val === null || val === undefined) return 0;
    const cleanStr = val.toString().replace(/,/g, '').trim();
    const num = parseFloat(cleanStr);
    return isNaN(num) ? 0 : num;
  }

  function formatCryptoSmart(val) {
    if (val === null || val === undefined || isNaN(val)) return "0.0000";
    const num = parseFloat(val);
    if (num === 0) return "0.0000";
    if (num < 0.0001) return num.toFixed(6);
    return num.toFixed(4);
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
    if (addr.length < 10) {
      return { valid: false, message: "⚠️ عنوان المحفظة غير صحيح." };
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

  // --- TONConnect Wallet System ---
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

  // --- Real-time Balance Syncing ---
  function syncBalanceFromGlobal() {
    let currentZnx = null;

    if (window.userState && window.userState.znx_balance !== undefined) {
      currentZnx = parseFloat(window.userState.znx_balance);
    } else if (window.PlayerData && window.PlayerData.znx_balance !== undefined) {
      currentZnx = parseFloat(window.PlayerData.znx_balance);
    }

    if (currentZnx !== null && !isNaN(currentZnx) && currentZnx !== userBalance) {
      userBalance = currentZnx;
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
        userWallet = data.wallet_address || (data.wallets && data.wallets.ZNX) || "";

        if (window.userState) {
          window.userState.znx_balance = userBalance;
        }

        updateUIBalance();
        updateWalletDisplay();
      }
    } catch (err) {
      console.error("خطأ جلب بيانات السحب:", err);
    }

    // مزامنة لحظية فورية
    window.addEventListener('userStateUpdated', syncBalanceFromGlobal);
    if (window.withdrawBalanceInterval) clearInterval(window.withdrawBalanceInterval);
    window.withdrawBalanceInterval = setInterval(syncBalanceFromGlobal, 1500);
  }

  function updateUIBalance() {
    const userBalDisplay = document.getElementById("user-balance-display");
    if (userBalDisplay) {
      userBalDisplay.innerText = `رصيدك: ${formatCryptoSmart(userBalance)} ZNX`;
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

    const feeAmount = document.getElementById("fee-amount");
    const netCryptoElem = document.getElementById("net-crypto");

    if (coinsVal <= 0 || coinsVal > userBalance) {
      resetCalculations();
      if (btn) btn.disabled = true;
      return;
    }

    const feeCoins = coinsVal * (feePercent / 100);
    const netCoins = coinsVal - feeCoins;

    if (feeAmount) feeAmount.innerText = `${formatCryptoSmart(feeCoins)} ZNX (${feePercent}%)`;
    if (netCryptoElem) netCryptoElem.innerText = `${formatCryptoSmart(netCoins)} ZNX`;

    if (btn) {
      const addrCheck = validateWalletAddress(walletAddress);
      btn.disabled = !(coinsVal > 0 && coinsVal <= userBalance && addrCheck.valid);
    }
  }

  function resetCalculations() {
    const feeAmount = document.getElementById("fee-amount");
    const netCryptoElem = document.getElementById("net-crypto");

    if (feeAmount) feeAmount.innerText = "0.0000 ZNX";
    if (netCryptoElem) netCryptoElem.innerText = "0.0000 ZNX";
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
        if (window.userState) window.userState.znx_balance = userBalance;
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
    },
    setPreset: setPreset,
    calculateWithdraw: calculateWithdraw,
    submitWithdrawal: submitWithdrawal,
    connectTonWallet: connectTonWallet,
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

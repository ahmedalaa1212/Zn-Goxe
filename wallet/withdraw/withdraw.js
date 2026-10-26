(function () {
  let userBalance = 0;
  let usdBalance = 0;
  let userWallet = "";
  let minWithdraw = 1000;
  let fixedFeeUsd = 0.02;
  let currentTierName = "الشريحة الأولى";
  let tonConnectUI = null;
  let isSubmitting = false;
  let isSavingWallet = false;

  // قص الأرقام العشرية للأسفل لأربع خانات بدقة تمنع أخطاء Floating Point
  function floorTo4Decimals(val) {
    const num = parseFloat(val);
    if (isNaN(num) || !isFinite(num) || num <= 0) return 0;
    return Math.floor((num + 1e-9) * 10000) / 10000;
  }

  // تنسيق نظيف للأرقام يمنع ظهور .0000 للأرقام الصحيحة (1000 يظهر 1,000 وليس 1000.0000)
  function formatCleanZnx(val) {
    if (val === null || val === undefined || isNaN(val) || !isFinite(val)) return "0";
    const num = floorTo4Decimals(val);
    if (num <= 0) return "0";
    return num.toLocaleString('en-US', {
      minimumFractionDigits: 0,
      maximumFractionDigits: 4
    });
  }

  // تحويل الأرقام العربية/الفارسية إلى إنجليزية وتنظيف المدخلات
  function normalizeNumericString(str) {
    if (!str) return "";
    const arabicNums = ['٠', '١', '٢', '٣', '٤', '٥', '٦', '٧', '٨', '٩'];
    let out = str.toString();
    for (let i = 0; i < 10; i++) {
      out = out.replace(new RegExp(arabicNums[i], 'g'), i.toString());
    }
    out = out.replace(/,/g, '').replace(/[^0-9.]/g, '');
    const parts = out.split('.');
    if (parts.length > 2) {
      out = parts[0] + '.' + parts.slice(1).join('');
    }
    if (parts.length === 2 && parts[1].length > 4) {
      out = parts[0] + '.' + parts[1].substring(0, 4);
    }
    return out;
  }

  function parseInputValue(val) {
    if (val === null || val === undefined) return 0;
    const cleanStr = normalizeNumericString(val);
    if (!cleanStr) return 0;
    const num = parseFloat(cleanStr);
    return (isNaN(num) || !isFinite(num) || num < 0) ? 0 : floorTo4Decimals(num);
  }

  function getTelegramInitData() {
    return window.Telegram?.WebApp?.initData || "";
  }

  function getAuthHeaders() {
    return {
      'Content-Type': 'application/json',
      'X-Telegram-Init-Data': getTelegramInitData()
    };
  }

  function getUserId() {
    const urlParams = new URLSearchParams(window.location.search);
    const id = (
      window.Telegram?.WebApp?.initDataUnsafe?.user?.id ||
      window.userState?.userId ||
      window.userState?.id ||
      window.userState?.tg_id ||
      window.PlayerData?.userId ||
      window.PlayerData?.id ||
      urlParams.get('user_id') ||
      localStorage.getItem('user_id') ||
      ""
    );
    return id ? id.toString().trim() : "";
  }

  function validateWalletAddress(address) {
    if (!address || typeof address !== 'string') {
      return { valid: false, message: "⚠️ يرجى ربط محفظة TON أولاً." };
    }
    const addr = address.trim();
    const tonRegex = /^(EQ|UQ|0:)[a-zA-Z0-9_-]{46,66}$/;
    if (!tonRegex.test(addr)) {
      return {
        valid: false,
        message: "⚠️ عنوان المحفظة غير صالح! يرجى اختيار محفظة TON صحيحة."
      };
    }
    return { valid: true, message: "" };
  }

  // ربط حدث واحد نظيف وسلس لحقل المبلغ لمنع أي تقطيع أو تهنيج في الكيبورد
  function bindInputEvents() {
    const coinsInput = document.getElementById("coins-input");
    if (coinsInput && !coinsInput.dataset.bound) {
      coinsInput.dataset.bound = "true";
      coinsInput.addEventListener("input", function () {
        const rawVal = coinsInput.value;
        const cleanVal = normalizeNumericString(rawVal);
        if (rawVal !== cleanVal) {
          const pos = coinsInput.selectionStart || cleanVal.length;
          coinsInput.value = cleanVal;
          try {
            coinsInput.setSelectionRange(pos, pos);
          } catch (e) {}
        }
        calculateWithdraw();
      });
    }
  }

  async function initTonConnect() {
    if (window.tonConnectInstance) {
      tonConnectUI = window.tonConnectInstance;
      return;
    }

    if (typeof TON_CONNECT_UI === 'undefined') {
      const existingScript = document.querySelector('script[src*="tonconnect-ui.min.js"]');
      if (!existingScript) {
        await new Promise((resolve) => {
          const script = document.createElement('script');
          script.src = "https://unpkg.com/@tonconnect/ui@latest/dist/tonconnect-ui.min.js";
          script.onload = resolve;
          script.onerror = resolve;
          document.head.appendChild(script);
        });
      } else {
        await new Promise((resolve) => setTimeout(resolve, 300));
      }
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
          if (wallet && wallet.account && wallet.account.address) {
            let addr = wallet.account.address;
            try {
              if (TON_CONNECT_UI.toUserFriendlyAddress) {
                addr = TON_CONNECT_UI.toUserFriendlyAddress(addr);
              }
            } catch (e) {}

            const result = await saveWalletToServer(addr);
            if (!result.ok && result.message) {
              alert(result.message);
            }
          }
        });
      } catch (e) {
        console.warn("TONConnect initialization warning:", e);
      }
    }
  }

  // فتح قائمة محافظ TON Connect الرسمية لاختيار المحفظة أو تغييرها في أي وقت
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
        console.error("خطأ فتح قائمة المحافظ:", e);
        alert("⚠️ يرجى المحاولة مرة أخرى لفتح قائمة محافظ TON.");
      }
    } else {
      alert("⚠️ جاري تحميل قائمة محافظ TON، يرجى الضغط مرة أخرى بعد ثانية.");
      await initTonConnect();
    }
  }

  // إظهار قائمة السحب فقط إذا كانت المحفظة مربوطة، وإخفاؤها تماماً إذا لم تكن مربوطة
  function updateWalletDisplay() {
    const hiddenInput = document.getElementById("wallet-address-input");
    const displayDiv = document.getElementById("wallet-address-display");
    const connectBtn = document.getElementById("btn-connect-wallet");
    const unlinkedHint = document.getElementById("wallet-unlinked-hint");
    const withdrawFormCard = document.getElementById("withdraw-form-card");

    const isWalletLinked = validateWalletAddress(userWallet).valid;

    if (hiddenInput) hiddenInput.value = isWalletLinked ? userWallet : "";

    if (isWalletLinked) {
      if (displayDiv) {
        displayDiv.innerText = userWallet;
        displayDiv.style.display = "block";
      }
      if (unlinkedHint) {
        unlinkedHint.style.display = "none";
      }
      if (connectBtn) {
        connectBtn.innerHTML = "🔄 تغيير محفظة TON (اختيار محفظة أخرى)";
      }
      if (withdrawFormCard) {
        withdrawFormCard.style.display = "block";
      }
    } else {
      if (displayDiv) {
        displayDiv.innerText = "";
        displayDiv.style.display = "none";
      }
      if (unlinkedHint) {
        unlinkedHint.style.display = "block";
      }
      if (connectBtn) {
        connectBtn.innerHTML = "🔗 ربط محفظة TON (اختيار من المحافظ)";
      }
      if (withdrawFormCard) {
        withdrawFormCard.style.display = "none";
      }
    }

    calculateWithdraw();
  }

  async function saveWalletToServer(val) {
    if (isSavingWallet) return { ok: false, message: "جاري حفظ المحفظة حالياً..." };
    const userId = getUserId();
    const check = validateWalletAddress(val);
    if (!check.valid) return { ok: false, message: check.message };

    isSavingWallet = true;
    try {
      let res = await fetch('/api/wallet/withdraw/save-wallet', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          user_id: userId,
          currency: 'ZNX',
          wallet_address: val.trim(),
          init_data: getTelegramInitData()
        })
      });

      if (res.status === 404) {
        res = await fetch('/api/withdraw/save-wallet', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            user_id: userId,
            currency: 'ZNX',
            wallet_address: val.trim(),
            init_data: getTelegramInitData()
          })
        });
      }

      const data = await res.json().catch(() => null);
      if (res.ok && data?.success) {
        userWallet = val.trim();
        if (window.userState) {
          window.userState.wallet_address = userWallet;
          if (!window.userState.wallets) window.userState.wallets = {};
          window.userState.wallets.ZNX = userWallet;
        }
        if (window.PlayerData) {
          window.PlayerData.wallet_address = userWallet;
        }
        updateWalletDisplay();
        return { ok: true, message: data.message || "تم ربط وحفظ المحفظة بنجاح!" };
      }
      return { ok: false, message: data?.message || "تعذر حفظ المحفظة في الخادم." };
    } catch (e) {
      console.error("خطأ حفظ المحفظة بالخادم:", e);
      return { ok: false, message: "حدث خطأ في الاتصال أثناء حفظ المحفظة." };
    } finally {
      isSavingWallet = false;
    }
  }

  function syncBalanceFromGlobal() {
    if (isSubmitting) return;

    // عدم مقاطعة المستخدم أو إعادة رسم الواجهة أثناء كتابة المبلغ في الحقل
    const coinsInput = document.getElementById("coins-input");
    if (coinsInput && document.activeElement === coinsInput) {
      return;
    }

    let currentZnx = null;
    let currentUsd = null;

    if (window.userState && window.userState.znx_balance !== undefined) {
      currentZnx = parseFloat(window.userState.znx_balance);
    } else if (window.PlayerData && window.PlayerData.znx_balance !== undefined) {
      currentZnx = parseFloat(window.PlayerData.znx_balance);
    }

    if (window.userState && window.userState.usd_balance !== undefined) {
      currentUsd = parseFloat(window.userState.usd_balance);
    } else if (window.PlayerData && window.PlayerData.usd_balance !== undefined) {
      currentUsd = parseFloat(window.PlayerData.usd_balance);
    }

    if (currentZnx !== null && !isNaN(currentZnx) && Math.abs(currentZnx - userBalance) > 1e-6) {
      userBalance = Math.max(0, currentZnx);
      updateUIBalance();
      calculateWithdraw();
    }

    if (currentUsd !== null && !isNaN(currentUsd) && Math.abs(currentUsd - usdBalance) > 1e-6) {
      usdBalance = Math.max(0, currentUsd);
      updateUIBalance();
      calculateWithdraw();
    }
  }

  // جلب الرصيد والشريحة الحقيقية والمحفظة من السيرفر مباشرة
  async function refreshBalanceFromServer(userId) {
    const currentUid = userId || getUserId();
    if (!currentUid) return;

    try {
      let response = await fetch(`/api/wallet/withdraw/config?user_id=${encodeURIComponent(currentUid)}&_t=${Date.now()}`, {
        headers: { 'X-Telegram-Init-Data': getTelegramInitData() },
        cache: 'no-store'
      });
      if (!response.ok) {
        response = await fetch(`/api/withdraw/config?user_id=${encodeURIComponent(currentUid)}&_t=${Date.now()}`, {
          headers: { 'X-Telegram-Init-Data': getTelegramInitData() },
          cache: 'no-store'
        });
      }
      if (response.ok) {
        const data = await response.json();
        userBalance = Math.max(0, parseFloat(data.znx_balance ?? data.user_balance ?? userBalance) || 0);
        usdBalance = Math.max(0, parseFloat(data.usd_balance ?? usdBalance) || 0);
        userWallet = data.wallet_address || (data.wallets && data.wallets.ZNX) || userWallet;

        if (data.min_withdraw_znx !== undefined) minWithdraw = parseFloat(data.min_withdraw_znx);
        if (data.fixed_fee_usd !== undefined) fixedFeeUsd = parseFloat(data.fixed_fee_usd);
        if (data.current_tier && data.current_tier.name) currentTierName = data.current_tier.name;

        if (window.userState) {
          window.userState.znx_balance = userBalance;
          window.userState.usd_balance = usdBalance;
          window.userState.wallet_address = userWallet;
        }
        if (window.PlayerData) {
          window.PlayerData.znx_balance = userBalance;
          window.PlayerData.usd_balance = usdBalance;
          window.PlayerData.wallet_address = userWallet;
        }

        updateUIBalance();
        updateWalletDisplay();
      }
    } catch (err) {
      console.error("خطأ جلب بيانات السحب من السيرفر:", err);
    }
  }

  async function initWithdrawPage(userId) {
    const currentUid = userId || getUserId();
    bindInputEvents();
    initTonConnect();

    if (window.userState) {
      if (window.userState.znx_balance !== undefined) userBalance = Math.max(0, parseFloat(window.userState.znx_balance) || 0);
      if (window.userState.usd_balance !== undefined) usdBalance = Math.max(0, parseFloat(window.userState.usd_balance) || 0);
      userWallet = window.userState.wallet_address || (window.userState.wallets && window.userState.wallets.ZNX) || userWallet;
      updateUIBalance();
      updateWalletDisplay();
    }

    await refreshBalanceFromServer(currentUid);

    window.removeEventListener('userStateUpdated', syncBalanceFromGlobal);
    window.addEventListener('userStateUpdated', syncBalanceFromGlobal);
    if (window.withdrawBalanceInterval) clearInterval(window.withdrawBalanceInterval);
    window.withdrawBalanceInterval = setInterval(syncBalanceFromGlobal, 3000);
  }

  function updateUIBalance() {
    const userBalDisplay = document.getElementById("user-balance-display");
    const usdBalDisplay = document.getElementById("usd-balance-display");
    const minInfo = document.getElementById("min-withdraw-info");
    const feeInfo = document.getElementById("fee-amount");
    const noticeFeeDisplay = document.getElementById("notice-fee-display");
    const tierBadge = document.getElementById("tier-badge");

    if (userBalDisplay) userBalDisplay.innerText = `رصيدك: ${formatCleanZnx(userBalance)} ZNX`;
    if (usdBalDisplay) usdBalDisplay.innerText = `$${usdBalance.toFixed(2)} USD`;
    if (minInfo) minInfo.innerText = `الحد الأدنى: ${formatCleanZnx(minWithdraw)} ZNX`;
    if (feeInfo) feeInfo.innerText = `$${fixedFeeUsd.toFixed(2)} USD (من رصيد الدولار)`;
    if (noticeFeeDisplay) noticeFeeDisplay.innerText = `$${fixedFeeUsd.toFixed(2)} USD`;
    if (tierBadge) tierBadge.innerText = currentTierName;
  }

  function setPreset(type) {
    const coinsInput = document.getElementById("coins-input");
    if (!coinsInput) return;

    if (type === 'max') {
      const flooredBal = floorTo4Decimals(userBalance);
      coinsInput.value = flooredBal > 0 ? flooredBal.toString() : "";
    }
    calculateWithdraw();
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
    } else if (window.walletModule && typeof window.walletModule.switchTab === 'function') {
      window.walletModule.switchTab('deposit');
    } else {
      const depositTabBtn = document.querySelector('[onclick*="deposit"], [data-tab="deposit"]');
      if (depositTabBtn) depositTabBtn.click();
      else alert("يرجى الانتقال لتبويب الإيداع لتعبئة رصيد الدولار.");
    }
  }

  function calculateWithdraw() {
    const coinsInput = document.getElementById("coins-input");
    const walletInput = document.getElementById("wallet-address-input");
    const coinsVal = parseInputValue(coinsInput?.value);
    const maxAvail = floorTo4Decimals(userBalance);
    const walletAddress = walletInput?.value?.trim() || userWallet;
    const btn = document.getElementById("confirm-withdraw-btn");
    const netCryptoElem = document.getElementById("net-crypto");

    if (coinsVal <= 0 || coinsVal > maxAvail) {
      resetCalculations();
      if (btn) btn.disabled = true;
      return;
    }

    if (netCryptoElem) netCryptoElem.innerText = `${formatCleanZnx(coinsVal)} ZNX`;

    if (btn) {
      const addrCheck = validateWalletAddress(walletAddress);
      const isEnoughCoins = coinsVal >= minWithdraw && coinsVal <= maxAvail;
      btn.disabled = !(isEnoughCoins && addrCheck.valid) || isSubmitting;
    }
  }

  function resetCalculations() {
    const netCryptoElem = document.getElementById("net-crypto");
    if (netCryptoElem) {
      netCryptoElem.innerText = '0 ZNX';
    }
  }

  async function submitWithdrawal(event) {
    if (event) event.preventDefault();
    if (isSubmitting) return;

    const coinsInput = document.getElementById("coins-input");
    const walletInput = document.getElementById("wallet-address-input");
    const coins = floorTo4Decimals(parseInputValue(coinsInput?.value));
    const maxAvail = floorTo4Decimals(userBalance);
    const walletAddress = walletInput?.value?.trim() || userWallet;
    const userId = getUserId();
    const btn = document.getElementById("confirm-withdraw-btn");

    if (!userId) {
      alert("⚠️ تعذر تحديد بيانات حسابك، يرجى إعادة فتح التطبيق.");
      return;
    }

    const addrCheck = validateWalletAddress(walletAddress);
    if (!addrCheck.valid) {
      alert("⚠️ يرجى ربط واختيار محفظة TON أولاً!");
      connectTonWallet();
      return;
    }

    if (coins < minWithdraw) {
      alert(`⚠️ الحد الأدنى للسحب في ${currentTierName} هو ${formatCleanZnx(minWithdraw)} ZNX.`);
      return;
    }

    if (coins > maxAvail) {
      alert("رصيدك الحالي من ZNX غير كافٍ لإتمام العملية!");
      return;
    }

    if (usdBalance < fixedFeeUsd) {
      openFeeNoticeModal(fixedFeeUsd);
      return;
    }

    isSubmitting = true;
    if (btn) {
      btn.disabled = true;
      btn.innerText = "جاري معالجة الطلب...";
    }

    try {
      let res = await fetch('/api/wallet/withdraw/request', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          user_id: userId,
          coins: coins,
          currency: 'ZNX',
          wallet_address: walletAddress,
          init_data: getTelegramInitData()
        })
      });

      if (res.status === 404) {
        res = await fetch('/api/withdraw/request', {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            user_id: userId,
            coins: coins,
            currency: 'ZNX',
            wallet_address: walletAddress,
            init_data: getTelegramInitData()
          })
        });
      }

      const data = await res.json().catch(() => null);

      if (res.ok && data && data.success) {
        alert(data.message || `✅ تم تقديم طلب سحب ${formatCleanZnx(coins)} ZNX بنجاح!`);
        userBalance = data.new_balance !== undefined ? Math.max(0, parseFloat(data.new_balance)) : Math.max(0, userBalance - coins);
        usdBalance = data.new_usd_balance !== undefined ? Math.max(0, parseFloat(data.new_usd_balance)) : Math.max(0, usdBalance - fixedFeeUsd);

        if (window.userState) {
          window.userState.znx_balance = userBalance;
          window.userState.usd_balance = usdBalance;
        }
        if (window.PlayerData) {
          window.PlayerData.znx_balance = userBalance;
          window.PlayerData.usd_balance = usdBalance;
        }

        // تحديث الهيدر العلوي والسجلات فوراً
        window.dispatchEvent(new Event('userStateUpdated'));
        window.dispatchEvent(new Event('withdrawSubmitted'));
        if (typeof window.updateHeaderBalances === 'function') {
          window.updateHeaderBalances();
        }
        if (window.historyModule && typeof window.historyModule.refresh === 'function') {
          window.historyModule.refresh(true);
        }

        if (coinsInput) coinsInput.value = "";
        updateUIBalance();
        resetCalculations();
      } else if (data && data.code === "INSUFFICIENT_USD") {
        await refreshBalanceFromServer(userId);
        openFeeNoticeModal(data.fee_required || fixedFeeUsd);
      } else {
        await refreshBalanceFromServer(userId);
        alert(data?.message || "حدث خطأ أثناء تقديم الطلب.");
      }
    } catch (err) {
      console.error("خطأ أثناء إرسال طلب السحب:", err);
      await refreshBalanceFromServer(userId);
      alert("حدث خطأ أثناء الاتصال بالخادم.");
    } finally {
      isSubmitting = false;
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
    openWalletModal: connectTonWallet,
    closeWalletModal: function () {},
    openFeeNoticeModal: openFeeNoticeModal,
    closeFeeNoticeModal: closeFeeNoticeModal,
    goToDeposit: goToDeposit
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

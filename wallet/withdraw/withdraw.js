(function () {
  let cryptoPrices = { DOGE: 0.10, TRX: 0.12, PEPE: 0.000008, LTC: 70.0 };
  let selectedCurrency = "DOGE";
  let withdrawConfig = null;
  let userBalance = 0;
  let userLevel = 1;
  let withdrawCount = 0;
  let activeLevelIndex = 0;
  let keyboardDebounceTimer = null;
  let userWallets = {}; // حفظ المحافظ لكل عملة بشكل مستقل

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

  function validateWalletAddress(address, currency) {
    if (!address || typeof address !== 'string') {
      return { valid: false, message: "يرجى إدخال عنوان المحفظة أو البريد الإلكتروني." };
    }
    const addr = address.trim();
    if (addr.length === 0) {
      return { valid: false, message: "يرجى إدخال عنوان المحفظة أو البريد الإلكتروني." };
    }

    const emailRegex = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
    if (emailRegex.test(addr)) {
      return { valid: true, message: "" };
    }

    const curr = (currency || selectedCurrency || "DOGE").toUpperCase();

    if (curr === "DOGE") {
      if (/^D[1-9A-HJ-NP-Za-km-z]{33}$/.test(addr)) {
        return { valid: true, message: "" };
      }
      return {
        valid: false,
        message: "عنوان DOGE غير صحيح! يجب أن يبدأ بحرف D ويتكون من 34 خانة، أو أدخل البريد الإلكتروني لحسابك في FaucetPay."
      };
    } else if (curr === "TRX") {
      if (/^T[1-9A-HJ-NP-Za-km-z]{33}$/.test(addr)) {
        return { valid: true, message: "" };
      }
      return {
        valid: false,
        message: "عنوان TRX غير صحيح! يجب أن يبدأ بحرف T ويتكون من 34 خانة، أو أدخل البريد الإلكتروني لحسابك في FaucetPay."
      };
    } else if (curr === "LTC") {
      if (/^(L|M)[1-9A-HJ-NP-Za-km-z]{33}$/.test(addr) || /^ltc1[a-z0-9]{38,58}$/i.test(addr)) {
        return { valid: true, message: "" };
      }
      return {
        valid: false,
        message: "عنوان LTC غير صحيح! يجب أن يبدأ بـ L أو M أو ltc1، أو أدخل البريد الإلكتروني لحسابك في FaucetPay."
      };
    } else if (curr === "PEPE") {
      if (/^0x[a-fA-F0-9]{40}$/.test(addr)) {
        return { valid: true, message: "" };
      }
      return {
        valid: false,
        message: "عنوان PEPE غير صحيح! يجب أن يبدأ بـ 0x (42 خانة)، أو أدخل البريد الإلكتروني لحسابك في FaucetPay."
      };
    }

    return { valid: true, message: "" };
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

  /* حقن تنسيقات الإخفاء الشاملة لأزرار محفظة تلجرام و TON Connect */
  function injectTonConnectHideStyles(doc) {
    try {
      if (!doc || doc.getElementById('hide-ton-connect-style')) return;
      const style = doc.createElement('style');
      style.id = 'hide-ton-connect-style';
      style.innerHTML = `
        #ton-connect-button,
        .ton-connect-button,
        tc-root,
        [class*="ton-connect"],
        [id*="ton-connect"],
        div[class*="tc-"],
        button[class*="go-tonconnect"],
        .go-tonconnect-btn,
        [data-tc-button],
        .tc-dropdown-button {
          display: none !important;
          visibility: hidden !important;
          opacity: 0 !important;
          pointer-events: none !important;
          position: absolute !important;
          top: -9999px !important;
          left: -9999px !important;
          width: 0 !important;
          height: 0 !important;
        }
      `;
      doc.head?.appendChild(style);
    } catch (e) {}
  }

  /* البحث المستمر والديناميكي لإخفاء أي زر ربط محفظة ينشئه تلجرام أو TON Connect */
  function hideTelegramWalletButtons() {
    const targetDocs = [document];
    try {
      if (window.parent && window.parent !== window && window.parent.document) {
        targetDocs.push(window.parent.document);
      }
      if (window.top && window.top !== window && window.top.document) {
        targetDocs.push(window.top.document);
      }
    } catch (e) {}

    targetDocs.forEach(doc => {
      injectTonConnectHideStyles(doc);
      try {
        const elements = doc.querySelectorAll('#ton-connect-button, .ton-connect-button, tc-root, [class*="ton-connect"], [id*="ton-connect"], div[class*="tc-"], button[class*="go-tonconnect"], .go-tonconnect-btn, [data-tc-button]');
        elements.forEach(el => {
          el.style.setProperty('display', 'none', 'important');
          el.style.setProperty('visibility', 'hidden', 'important');
          el.style.setProperty('opacity', '0', 'important');
          el.style.setProperty('pointer-events', 'none', 'important');
        });
      } catch (e) {}
    });
  }

  function injectKeyboardStyles(doc) {
    try {
      if (!doc || doc.getElementById('keyboard-hide-nav-style')) return;
      const style = doc.createElement('style');
      style.id = 'keyboard-hide-nav-style';
      style.innerHTML = `
        body.keyboard-active .bottom-nav,
        body.keyboard-active .nav-bar,
        body.keyboard-active .navbar,
        body.keyboard-active .footer-menu,
        body.keyboard-active .main-menu,
        body.keyboard-active .navigation-bar,
        body.keyboard-active #bottom-nav,
        body.keyboard-active #bottom-navigation,
        body.keyboard-active #main-nav,
        body.keyboard-active footer,
        body.keyboard-active [class*="bottom-nav"],
        body.keyboard-active [class*="footer"],
        body.keyboard-active [class*="navigation"],
        body.keyboard-active [id*="bottom-nav"],
        body.keyboard-active [id*="footer"] {
          display: none !important;
          visibility: hidden !important;
          opacity: 0 !important;
          pointer-events: none !important;
        }
      `;
      doc.head?.appendChild(style);
    } catch (e) {}
  }

  function toggleKeyboardClass(active) {
    const targetDocs = [document];
    try {
      if (window.parent && window.parent !== window && window.parent.document) {
        targetDocs.push(window.parent.document);
      }
      if (window.top && window.top !== window && window.top.document) {
        targetDocs.push(window.top.document);
      }
    } catch (e) {}

    targetDocs.forEach(doc => {
      try {
        if (!doc || !doc.body) return;
        injectKeyboardStyles(doc);
        injectTonConnectHideStyles(doc);
        if (active) {
          doc.body.classList.add('keyboard-active');
          doc.documentElement?.classList.add('keyboard-active');
        } else {
          doc.body.classList.remove('keyboard-active');
          doc.documentElement?.classList.remove('keyboard-active');
        }
      } catch (e) {}
    });
  }

  function hideMenus() {
    if (keyboardDebounceTimer) {
      clearTimeout(keyboardDebounceTimer);
      keyboardDebounceTimer = null;
    }
    toggleKeyboardClass(true);
  }

  function showMenus(immediate = false) {
    if (keyboardDebounceTimer) {
      clearTimeout(keyboardDebounceTimer);
      keyboardDebounceTimer = null;
    }

    if (immediate) {
      toggleKeyboardClass(false);
    } else {
      keyboardDebounceTimer = setTimeout(() => {
        const active = document.activeElement;
        const isInput = active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA') && !active.readOnly;
        if (!isInput) {
          toggleKeyboardClass(false);
        }
      }, 150);
    }
  }

  function setupKeyboardListeners() {
    if (window._keyboardListenersInitialized) return;
    window._keyboardListenersInitialized = true;

    toggleKeyboardClass(false);

    document.addEventListener('focusin', (e) => {
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') && !e.target.readOnly) {
        hideMenus();
      }
    }, true);

    document.addEventListener('focusout', (e) => {
      if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) {
        showMenus(false);
      }
    }, true);

    if (window.visualViewport) {
      let vpResizeTimer = null;
      const initialHeight = window.visualViewport.height;

      window.visualViewport.addEventListener('resize', () => {
        if (vpResizeTimer) clearTimeout(vpResizeTimer);
        vpResizeTimer = setTimeout(() => {
          const currentHeight = window.visualViewport.height;
          const active = document.activeElement;
          const isInput = active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA') && !active.readOnly;

          if (initialHeight - currentHeight > 120 && isInput) {
            hideMenus();
          } else if (currentHeight >= initialHeight - 50 && !isInput) {
            showMenus(true);
          }
        }, 100);
      });
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
    setupKeyboardListeners();
  }

  function updateWalletDisplay() {
    const hiddenInput = document.getElementById("wallet-address-input");
    const displayDiv = document.getElementById("wallet-address-display");
    const connectBtn = document.getElementById("btn-connect-wallet");

    const savedAddr = userWallets[selectedCurrency] || "";

    if (hiddenInput) hiddenInput.value = savedAddr;

    if (savedAddr && savedAddr.length > 0) {
      if (displayDiv) {
        displayDiv.innerText = savedAddr;
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
        connectBtn.innerHTML = "🔗 ربط المحفظة";
      }
    }

    calculateWithdraw();
  }

  async function initWithdrawPage(userId) {
    const currentUid = userId || getUserId();
    bindInputEvents();
    hideTelegramWalletButtons();
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
        withdrawCount = parseInt(data.withdraw_count) || 0;
        userWallets = data.wallets || {};

        if (withdrawConfig && withdrawConfig.levels) {
          userLevel = Math.min(withdrawCount + 1, withdrawConfig.levels.length);
          activeLevelIndex = Math.min(withdrawCount, withdrawConfig.levels.length - 1);
        }

        updateUIBalance();
        renderLevelsGuide();
        updateWalletDisplay();
      }
    } catch (err) {
      console.error("خطأ جلب إعدادات السحب:", err);
    } finally {
      hideTelegramWalletButtons();
    }
  }

  function updateUIBalance() {
    const userBalDisplay = document.getElementById("user-balance-display");
    if (userBalDisplay) {
      userBalDisplay.innerText = `رصيدك: ${userBalance.toLocaleString()} ZN`;
    }

    const levelBadge = document.getElementById("level-indicator");
    if (levelBadge) {
      levelBadge.innerText = `المستوى ${userLevel}`;
    }
  }

  // --- عرض دليل المستويات دون كشف نوع السحب (آلي / يدوي) ---
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
      const usdMin = (lvl.min / 100000).toFixed(4);
      const usdMax = (lvl.max / 100000).toFixed(4);

      let znText = "";
      let usdText = "";

      if (lvl.min === lvl.max) {
        znText = `${lvl.min.toLocaleString()} ZN - ${lvl.max.toLocaleString()} ZN`;
        usdText = `$${usdMin} - $${usdMax}`;
      } else {
        znText = `من ${lvl.min.toLocaleString()} ZN إلى ${lvl.max.toLocaleString()} ZN`;
        usdText = `$${usdMin} - $${usdMax}`;
      }

      html += `
        <div class="level-item ${isActive ? 'active-level' : ''}">
          <div>
            <span>المستوى ${lvl.level}: ${znText}</span>
            <br><small style="color:#94a3b8;">(${usdText})</small>
          </div>
          ${isActive ? '<span class="level-item-tag" style="color:#38bdf8;">مستواك الحالي ✅</span>' : ''}
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
    updateWalletDisplay();
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

  function openWalletModal() {
    const modal = document.getElementById("wallet-modal");
    const modalInput = document.getElementById("modal-wallet-input");
    const modalLabel = document.getElementById("modal-coin-label");

    if (modalLabel) modalLabel.innerText = selectedCurrency;

    if (modalInput) {
      modalInput.value = userWallets[selectedCurrency] || "";
    }

    if (modal) {
      modal.classList.add("active");
      setTimeout(() => {
        if (modalInput) {
          modalInput.focus();
          hideMenus();
        }
      }, 100);
    }
  }

  function closeWalletModal() {
    if (document.activeElement && typeof document.activeElement.blur === 'function') {
      document.activeElement.blur();
    }
    
    showMenus(true);

    const modal = document.getElementById("wallet-modal");
    if (modal) {
      modal.classList.remove("active");
    }
  }

  async function saveWalletAddress() {
    const modalInput = document.getElementById("modal-wallet-input");
    const saveBtn = document.querySelector("#wallet-modal .btn-save");
    const val = modalInput ? modalInput.value.trim() : "";
    const userId = getUserId();

    const addressValidation = validateWalletAddress(val, selectedCurrency);
    if (!addressValidation.valid) {
      alert(addressValidation.message);
      return;
    }

    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.innerText = "جاري الحفظ...";
    }

    try {
      let res = await fetch('/api/wallet/withdraw/save-wallet', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: userId,
          currency: selectedCurrency,
          wallet_address: val
        })
      });

      if (res.status === 404) {
        res = await fetch('/api/withdraw/save-wallet', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            currency: selectedCurrency,
            wallet_address: val
          })
        });
      }

      const data = await res.json().catch(() => null);

      if (res.ok && data?.success) {
        userWallets[selectedCurrency] = val;
        updateWalletDisplay();
        closeWalletModal();
      } else {
        alert(data?.message || "حدث خطأ أثناء حفظ العنوان في قاعدة البيانات.");
      }
    } catch (e) {
      console.error(e);
      alert("تعذر الاتصال بالخادم لحفظ العنوان.");
    } finally {
      if (saveBtn) {
        saveBtn.disabled = false;
        saveBtn.innerText = "حفظ";
      }
    }
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

    const usdRate = withdrawConfig.rate_coins_per_usd || 100000;
    const grossUsdValue = coinsInputVal / usdRate;

    const feePercent = withdrawConfig.fee_percent || 3;
    const feeCoins = coinsInputVal * (feePercent / 100);
    const netCoins = coinsInputVal - feeCoins;
    const netUsd = netCoins / usdRate;

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
      const addrCheck = validateWalletAddress(walletAddress, selectedCurrency);

      btn.disabled = !(isMinOk && isMaxOk && addrCheck.valid && userBalance >= coinsInputVal);
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

  async function submitWithdrawal(event) {
    if (event) event.preventDefault();

    const coinsInput = document.getElementById("coins-input");
    const walletInput = document.getElementById("wallet-address-input");
    const coins = parseInputValue(coinsInput?.value);
    const walletAddress = walletInput?.value?.trim();
    const userId = getUserId();
    const btn = document.getElementById("confirm-withdraw-btn");

    if (!walletAddress) {
      alert("يرجى ربط عنوان المحفظة أو البريد الإلكتروني أولاً!");
      return;
    }

    const addressValidation = validateWalletAddress(walletAddress, selectedCurrency);
    if (!addressValidation.valid) {
      alert(addressValidation.message);
      return;
    }

    if (coins <= 0) {
      alert("يرجى إدخال مبلغ سحب صحيح!");
      return;
    }

    if (userBalance > 0 && coins > userBalance) {
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
          coins_amount: coins,
          currency: selectedCurrency,
          wallet_address: walletAddress,
          coin_price_usd: cryptoPrices[selectedCurrency]
        })
      });

      if (res.status === 404) {
        res = await fetch('/api/withdraw/request', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            coins: coins,
            coins_amount: coins,
            currency: selectedCurrency,
            wallet_address: walletAddress,
            coin_price_usd: cryptoPrices[selectedCurrency]
          })
        });
      }

      const data = await res.json().catch(() => null);

      if (data && data.success) {
        alert(data.message || "تم إرسال طلب السحب بنجاح!");

        if (typeof data.new_balance === 'number') {
          userBalance = data.new_balance;
        } else {
          userBalance = Math.max(0, userBalance - coins);
        }
        withdrawCount += 1;

        if (coinsInput) coinsInput.value = "";
        updateUIBalance();
        resetCalculations();

        if (typeof window.loadWalletData === 'function') {
          window.loadWalletData();
        }
      } else {
        alert(data?.message || "حدث خطأ أثناء معالجة الطلب.");
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
      const userId = getUserId();
      initWithdrawPage(userId);
      setupKeyboardListeners();
      hideTelegramWalletButtons();
    },
    selectCurrency: selectCurrency,
    setPreset: setPreset,
    calculateWithdraw: calculateWithdraw,
    submitWithdrawal: submitWithdrawal,
    validateWalletAddress: validateWalletAddress,
    setupKeyboardListeners: setupKeyboardListeners,
    hideTelegramWalletButtons: hideTelegramWalletButtons,
    openWalletModal: openWalletModal,
    closeWalletModal: closeWalletModal,
    saveWalletAddress: saveWalletAddress
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
    document.addEventListener("DOMContentLoaded", () => {
      withdrawModule.init();
      hideTelegramWalletButtons();
    });
  } else {
    withdrawModule.init();
    hideTelegramWalletButtons();
  }
})();

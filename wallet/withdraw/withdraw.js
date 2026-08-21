(function () {
  let tonPriceUSD = 0;
  let withdrawConfig = null;
  let currentWalletAddress = null;
  let tonConnectUI = null;
  let userBalance = 0;
  let withdrawCount = 0;
  let activeLevelIndex = 0;

  // جلب معرف المستخدم الموحد من النظام
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

  // تحميل مكتبة TonConnect ديناميكياً
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

  // تهيئة زر ومحفظة TonConnect
  function initTonConnect() {
    try {
      const TonConnectClass = window.TON_CONNECT_UI?.TonConnectUI || window.TonConnectSDK?.TonConnectUI;
      if (!TonConnectClass) {
        setTimeout(initTonConnect, 300);
        return;
      }

      const buttonContainer = document.getElementById("ton-connect-button");
      if (!buttonContainer) return;

      buttonContainer.innerHTML = "";

      if (!window.globalTonConnectUI) {
        window.globalTonConnectUI = new TonConnectClass({
          manifestUrl: window.location.origin + '/tonconnect-manifest.json',
          buttonRootId: 'ton-connect-button'
        });
      } else {
        try {
          window.globalTonConnectUI.setUIOptions({ buttonRootId: 'ton-connect-button' });
        } catch (e) {}
      }

      tonConnectUI = window.globalTonConnectUI;

      // فحص حالة المحفظة الحالية فور التهيئة
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

  // تحديث عناصر الواجهة حسب حالة اتصال المحفظة
  function updateWalletUI(wallet) {
    const statusBadge = document.getElementById("wallet-connect-status");
    const walletBox = document.getElementById("connected-wallet-box");
    const addressDisplay = document.getElementById("wallet-address-display");

    if (wallet && wallet.account) {
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
  }

  // قطع اتصال المحفظة
  async function disconnectWallet() {
    if (tonConnectUI && tonConnectUI.connected) {
      try {
        await tonConnectUI.disconnect();
      } catch (e) {
        console.error("خطأ أثناء قطع الاتصال:", e);
      }
    }
  }

  // جلب بيانات الإعدادات والرصيد والمستويات
  async function initWithdrawPage(userId) {
    const currentUid = userId || getUserId();
    try {
      const response = await fetch(`/api/wallet/withdraw/config?user_id=${currentUid}`);
      if (!response.ok) {
        console.error("فشل الاتصال بـ API السحب:", response.status);
        return;
      }
      const data = await response.json();

      if (data.success) {
        withdrawConfig = data.config;
        tonPriceUSD = parseFloat(data.ton_price) || 5.50;
        userBalance = parseFloat(data.user_balance) || 0;
        withdrawCount = parseInt(data.withdraw_count) || 0;

        const userBalDisplay = document.getElementById("user-balance-display");
        if (userBalDisplay) {
          userBalDisplay.innerText = `رصيدك: ${userBalance.toLocaleString()} ZN`;
        }

        if (withdrawConfig && withdrawConfig.levels) {
          activeLevelIndex = Math.min(withdrawCount, withdrawConfig.levels.length - 1);
        }

        renderLevelsGuide();
        setPreset('max');
      }
    } catch (err) {
      console.error("خطأ جلب إعدادات السحب:", err);
    }
  }

  // رسم جدول مستويات السحب المتدرجة
  function renderLevelsGuide() {
    const container = document.getElementById("levels-list-container");
    const userLevelText = document.getElementById("current-user-level-text");
    if (!container || !withdrawConfig || !withdrawConfig.levels) return;

    if (userLevelText) {
      userLevelText.innerText = `المستوى ${activeLevelIndex + 1}`;
    }

    let html = "";
    withdrawConfig.levels.forEach((lvl, idx) => {
      const isActive = idx === activeLevelIndex;
      const maxText = lvl.max >= 999999999 ? "مفتوح" : lvl.max.toLocaleString() + " ZN";

      html += `
        <div class="level-item ${isActive ? 'active-level' : ''}">
          <div>
            <span>المستوى ${lvl.level}: </span>
            <strong>${lvl.min.toLocaleString()} - ${maxText}</strong>
          </div>
          <span class="level-item-tag ${isActive ? 'tag-auto' : ''}">
            ${isActive ? 'مستواك الحالي ✅' : 'المستوى ' + lvl.level}
          </span>
        </div>
      `;
    });

    container.innerHTML = html;
  }

  // تحديد القيم السريعة (حد أدنى / نصف / حد أقصى)
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

  // حساب المبالغ والرسوم والصافي
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

    const usdRate = withdrawConfig.rate_coins_per_usd || 100000;
    const usdValue = coinsInputVal / usdRate;
    const rawTon = usdValue / tonPriceUSD;

    const feePercent = withdrawConfig.fee_percent || 3;
    const feeCoins = coinsInputVal * (feePercent / 100);
    const netCoins = coinsInputVal - feeCoins;
    const netUsd = netCoins / usdRate;
    const netTon = netUsd / tonPriceUSD;

    const tonOutput = document.getElementById("ton-output");
    const feeAmount = document.getElementById("fee-amount");
    const netTonElem = document.getElementById("net-ton");

    if (tonOutput) tonOutput.value = rawTon.toFixed(4) + " TON";
    if (feeAmount) feeAmount.innerText = `${feeCoins.toLocaleString()} ZN`;
    if (netTonElem) netTonElem.innerText = `${netTon.toFixed(4)} TON`;

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

  // إرسال طلب السحب للخادم
  async function submitWithdrawal() {
    const coinsInput = document.getElementById("coins-input");
    const coins = parseFloat(coinsInput ? coinsInput.value : 0);
    const userId = getUserId();
    const btn = document.getElementById("confirm-withdraw-btn");

    if (!currentWalletAddress) {
      alert("يرجى ربط محفظة TON أولاً قبل تأكيد السحب!");
      return;
    }

    if (coins > userBalance) {
      alert("رصيدك الحالي غير كافٍ لتمام هذه العملية!");
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
          wallet_address: currentWalletAddress
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

  // تصدير الكائن والدوال للعمل داخل SPA وفي النافذة العامة
  const withdrawModule = {
    init: function () {
      const userId = getUserId();
      loadTonConnectSDK(() => {
        initTonConnect();
      });
      initWithdrawPage(userId);
    },
    setPreset: setPreset,
    calculateWithdraw: calculateWithdraw,
    disconnectWallet: disconnectWallet,
    submitWithdrawal: submitWithdrawal
  };

  window.withdrawModule = withdrawModule;
  window.init_withdraw_module = function () {
    withdrawModule.init();
  };

  window.setPreset = setPreset;
  window.calculateWithdraw = calculateWithdraw;
  window.disconnectWallet = disconnectWallet;
  window.submitWithdrawal = submitWithdrawal;

  // التشغيل التلقائي عند التحميل المباشر للملف
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => withdrawModule.init());
  } else {
    withdrawModule.init();
  }
})();

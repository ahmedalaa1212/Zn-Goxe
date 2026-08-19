window.withdrawModule = (function () {
    let tonPriceUsd = 1.30; // سعر افتراضي لحين جلب السعر اللحظي
    const ZN_PER_USD = 100000; // 100,000 ZN = $1.00 USD
    const FEE_PERCENT = 0.03;  // رسوم 3%

    async function fetchTonLivePrice() {
        try {
            const res = await fetch('/api/wallet/withdraw/ton-price');
            if (res.ok) {
                const data = await res.json();
                if (data.success && data.ton_price > 0) {
                    tonPriceUsd = parseFloat(data.ton_price);
                }
            }
        } catch (e) {
            console.warn("⚠️ استخدام سعر TON المحلي الحقيقي:", e);
        }
        
        const rateElem = document.getElementById('withdraw-ton-rate-info');
        if (rateElem) {
            rateElem.innerText = `(سعر 1 TON = $${tonPriceUsd.toFixed(2)} USD)`;
        }
        calculateLiveExchange();
    }

    function calculateLiveExchange() {
        const amountInput = document.getElementById('withdraw-amount-input');
        const feeElem = document.getElementById('withdraw-fee-display');
        const usdElem = document.getElementById('withdraw-usd-display');
        const tonElem = document.getElementById('withdraw-ton-display');

        if (!amountInput || !feeElem || !usdElem || !tonElem) return;

        const amountZN = parseFloat(amountInput.value) || 0;

        if (amountZN <= 0) {
            feeElem.innerText = "0 ZN";
            usdElem.innerText = "$0.00";
            tonElem.innerText = "0.0000 TON";
            return;
        }

        // حساب الرسوم والصافي
        const feeZN = amountZN * FEE_PERCENT;
        const netZN = Math.max(0, amountZN - feeZN);
        
        // التحويل للدولار (100,000 ZN = $1)
        const netUSD = netZN / ZN_PER_USD;
        
        // التحويل لعملة TON بناءً على السعر المباشر
        const netTON = tonPriceUsd > 0 ? (netUSD / tonPriceUsd) : 0;

        // تحديث الواجهة
        feeElem.innerText = `${feeZN.toLocaleString('en-US', { maximumFractionDigits: 2 })} ZN`;
        usdElem.innerText = `$${netUSD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 })}`;
        tonElem.innerText = `${netTON.toFixed(4)} TON`;
    }

    function setMaxAmount() {
        const amountInput = document.getElementById('withdraw-amount-input');
        const userZn = window.userState?.balance || window.userState?.zn_balance || window.PlayerData?.balance || 0;
        
        if (amountInput) {
            amountInput.value = userZn;
            calculateLiveExchange();
        }
    }

    function connectWallet() {
        const addressInput = document.getElementById('withdraw-address-input');
        const msgElem = document.getElementById('withdraw-status-msg');

        // البحث عن محفظة مسجلة سابقاً في ذاكرة المستخدم أو Telegram WebApp
        const savedAddress = window.userState?.wallet_address || 
                             window.PlayerData?.wallet_address || 
                             window.Telegram?.WebApp?.initDataUnsafe?.user?.wallet_address;

        if (savedAddress && savedAddress.length > 10) {
            addressInput.value = savedAddress;
            showStatus("✅ تم ربط محفظتك المسجلة بنجاح!", "#34d399");
        } else if (window.Telegram?.WebApp?.openTelegramLink) {
            // توجيه مستخدمي تليجرام للتأكيد أو استخدام TON Connect إذا وجد
            showStatus("💡 أدخل عنوان محفظة TON الخاصة بك مباشرة (EQ... / UQ...)", "#38bdf8");
        } else {
            showStatus("💡 يرجى لصق عنوان محفظتك بصيغة EQ... أو UQ...", "#38bdf8");
        }
    }

    function showStatus(text, color) {
        const msgElem = document.getElementById('withdraw-status-msg');
        if (msgElem) {
            msgElem.style.display = 'block';
            msgElem.style.color = color;
            msgElem.style.background = 'rgba(0,0,0,0.4)';
            msgElem.innerText = text;
        }
    }

    async function submitWithdrawal() {
        const addressInput = document.getElementById('withdraw-address-input');
        const amountInput = document.getElementById('withdraw-amount-input');
        const btn = document.getElementById('withdraw-submit-btn');

        const address = addressInput?.value?.trim() || '';
        const amountZN = parseFloat(amountInput?.value) || 0;
        const currentBalance = window.userState?.balance || window.PlayerData?.balance || 0;

        // التحقق من صحة المدخلات
        if (!address || address.length < 20) {
            showStatus("❌ يرجى إدخال أو ربط عنوان محفظة TON صحيح!", "#f87171");
            return;
        }

        if (amountZN <= 0) {
            showStatus("❌ يرجى إدخال كمية عملات ZN مقبولة للسحب!", "#f87171");
            return;
        }

        if (amountZN > currentBalance) {
            showStatus("❌ رصيدك الحالي لا يكفي لتمام عملية السحب!", "#f87171");
            return;
        }

        btn.disabled = true;
        btn.innerText = "جاري معالجة طلب السحب...";
        showStatus("⏳ جاري تسجيل طلب السحب الفوري...", "#38bdf8");

        try {
            const tg = window.Telegram?.WebApp;
            const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || window.userState?.user_id || '';
            const initData = tg?.initData || '';

            const res = await fetch('/api/wallet/withdraw/request', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-User-Id': String(userId),
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({
                    user_id: userId,
                    address: address,
                    amount_zn: amountZN
                })
            });

            const data = await res.json();

            if (data.success) {
                showStatus("✅ تم تقديم طلب السحب بنجاح وخصم الرصيد!", "#34d399");

                // تحديث رصيد المستخدم محلياً فوراً
                if (data.new_balance !== undefined) {
                    if (window.userState) window.userState.balance = data.new_balance;
                    if (window.PlayerData) window.PlayerData.balance = data.new_balance;
                } else {
                    if (window.userState) window.userState.balance -= amountZN;
                    if (window.PlayerData) window.PlayerData.balance -= amountZN;
                }

                // تحديث واجهة المحفظة العلوية
                if (window.walletModule?.updateBalancesUI) {
                    window.walletModule.updateBalancesUI();
                }

                amountInput.value = "";
                calculateLiveExchange();
            } else {
                showStatus(`❌ فشل السحب: ${data.error || 'حدث خطأ غير متوقع'}`, "#f87171");
            }
        } catch (err) {
            console.error("خطأ السحب:", err);
            showStatus("❌ تعذر الاتصال بالسيرفر، حاول مجدداً.", "#f87171");
        } finally {
            btn.disabled = false;
            btn.innerText = "تأكيد طلب السحب الفوري 🚀";
        }
    }

    function init() {
        fetchTonLivePrice();
        connectWallet();
    }

    return {
        init,
        fetchTonLivePrice,
        calculateLiveExchange,
        setMaxAmount,
        connectWallet,
        submitWithdrawal
    };
})();

// تشغيل عند التحميل
if (document.getElementById('withdraw-amount-input')) {
    window.withdrawModule.init();
}

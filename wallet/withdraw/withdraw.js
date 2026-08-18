window.withdrawModule = (function () {
    let currentTierInfo = null;
    let tonPriceUsd = 6.0; // قيمة افتراضية لحين الجلب من السيرفر

    async function fetchWithdrawInfo() {
        try {
            const tg = window.Telegram?.WebApp;
            const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || window.userState?.user_id || '';
            const initData = tg?.initData || '';

            if (!userId) return;

            const res = await fetch(`/api/wallet/withdraw/info?user_id=${userId}`, {
                headers: {
                    'X-Telegram-User-Id': String(userId),
                    'Authorization': `Bearer ${initData}`
                }
            });

            const data = await res.json();
            if (data.success) {
                currentTierInfo = data.tier_info;
                tonPriceUsd = data.ton_price || 6.0;
                renderTierInfo();
            }
        } catch (err) {
            console.error("خطأ في جلب بيانات السحب:", err);
        }
    }

    function renderTierInfo() {
        if (!currentTierInfo) return;

        const titleElem = document.getElementById('tier-title');
        const badgeElem = document.getElementById('tier-badge');
        const minElem = document.getElementById('tier-min');
        const maxElem = document.getElementById('tier-max');
        const noteElem = document.getElementById('utc-limit-note');
        const btnElem = document.getElementById('withdraw-submit-btn');

        if (titleElem) titleElem.innerText = `السحبة رقم (${currentTierInfo.withdraw_count + 1}) - ${currentTierInfo.tier_name}`;
        
        if (badgeElem) {
            badgeElem.innerText = currentTierInfo.is_auto ? "تلقائي فوري" : "يدوي (موافقة أدمن)";
            badgeElem.style.background = currentTierInfo.is_auto ? "rgba(52, 211, 153, 0.15)" : "rgba(245, 158, 11, 0.15)";
            badgeElem.style.color = currentTierInfo.is_auto ? "#34d399" : "#f59e0b";
        }

        if (minElem) minElem.innerText = currentTierInfo.min_zn.toLocaleString();
        if (maxElem) maxElem.innerText = currentTierInfo.max_zn ? currentTierInfo.max_zn.toLocaleString() : "مفتوح (بلا حد)";

        if (currentTierInfo.has_withdrawn_today) {
            if (noteElem) noteElem.style.display = 'block';
            if (btnElem) {
                btnElem.disabled = true;
                btnElem.style.opacity = "0.5";
                btnElem.style.cursor = "not-allowed";
                btnElem.innerText = "تم السحب اليوم (توقيت UTC)";
            }
        }
    }

    function calculateDetails() {
        const inputElem = document.getElementById('withdraw-amount-input');
        const feeElem = document.getElementById('calc-fee');
        const usdElem = document.getElementById('calc-net-usd');
        const tonElem = document.getElementById('calc-net-ton');

        const amount = parseFloat(inputElem?.value || 0);

        if (amount <= 0 || isNaN(amount)) {
            if (feeElem) feeElem.innerText = "0 ZN";
            if (usdElem) usdElem.innerText = "$0.00";
            if (tonElem) tonElem.innerText = "0.0000 TON";
            return;
        }

        const feeZN = amount * 0.03; // خصم 3%
        const netZN = Math.max(0, amount - feeZN);
        
        // 100,000 ZN = $1.00 USD
        const netUSD = netZN / 100000.0;
        const netTON = tonPriceUsd > 0 ? (netUSD / tonPriceUsd) : 0;

        if (feeElem) feeElem.innerText = `${feeZN.toFixed(2)} ZN`;
        if (usdElem) usdElem.innerText = `$${netUSD.toFixed(4)}`;
        if (tonElem) tonElem.innerText = `${netTON.toFixed(4)} TON`;
    }

    function setMaxAmount() {
        if (!currentTierInfo) return;
        const userBalance = window.userState?.balance || 0;
        let target = userBalance;

        if (currentTierInfo.max_zn && target > currentTierInfo.max_zn) {
            target = currentTierInfo.max_zn;
        }

        const inputElem = document.getElementById('withdraw-amount-input');
        if (inputElem) {
            inputElem.value = target;
            calculateDetails();
        }
    }

    async function submitWithdrawal() {
        const address = document.getElementById('withdraw-address-input')?.value?.trim();
        const amount = parseFloat(document.getElementById('withdraw-amount-input')?.value || 0);
        const userBalance = window.userState?.balance || 0;

        if (!address || address.length < 20) {
            alert("يرجى إدخال عنوان محفظة TON صحيح!");
            return;
        }

        if (!amount || amount <= 0) {
            alert("يرجى إدخال كمية سحب صالحة!");
            return;
        }

        if (amount > userBalance) {
            alert("رصيدك الحالي غير كافٍ لإجراء السحب!");
            return;
        }

        if (currentTierInfo) {
            if (amount < currentTierInfo.min_zn) {
                alert(`الحد الأدنى لهذا المستوى هو ${currentTierInfo.min_zn.toLocaleString()} ZN`);
                return;
            }
            if (currentTierInfo.max_zn && amount > currentTierInfo.max_zn) {
                alert(`الحد الأقصى لهذا المستوى هو ${currentTierInfo.max_zn.toLocaleString()} ZN`);
                return;
            }
        }

        const btn = document.getElementById('withdraw-submit-btn');
        if (btn) {
            btn.disabled = true;
            btn.innerText = "جاري معالجة الطلب...";
        }

        try {
            const tg = window.Telegram?.WebApp;
            const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || window.userState?.user_id || '';

            const res = await fetch('/api/wallet/withdraw/request', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-User-Id': String(userId)
                },
                body: JSON.stringify({
                    user_id: userId,
                    amount_zn: amount,
                    wallet_address: address
                })
            });

            const data = await res.json();
            if (data.success) {
                alert(data.message || "تم تقديم طلب السحب بنجاح!");
                
                // تحديث الرصيد المحلي مباشرة
                if (window.userState && data.new_balance !== undefined) {
                    window.userState.balance = data.new_balance;
                    if (window.walletModule?.updateBalancesUI) {
                        window.walletModule.updateBalancesUI();
                    }
                }
                
                // إعادة جلب معلومات التبويب لتعطيل السحب اليومي
                fetchWithdrawInfo();
            } else {
                alert(data.error || "فشل تقديم طلب السحب!");
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = "تأكيد طلب السحب";
                }
            }
        } catch (e) {
            console.error("Error submitting withdrawal:", e);
            alert("حدث خطأ أثناء الاتصال بالسيرفر!");
            if (btn) {
                btn.disabled = false;
                btn.innerText = "تأكيد طلب السحب";
            }
        }
    }

    function init() {
        fetchWithdrawInfo();
    }

    return {
        init,
        calculateDetails,
        setMaxAmount,
        submitWithdrawal
    };
})();

function init_withdraw_module() {
    window.withdrawModule?.init();
}

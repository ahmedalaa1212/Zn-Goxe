(function() {
    // دالة التهيئة الرئيسية للقسم
    window.initWalletView = function() {
        try {
            console.log("⚡ جاري تهيئة قسم المحفظة...");

            // 1. تحديث الأرصدة المعروضة بأمان
            const znEl = document.getElementById('wallet-zn-balance');
            const usdEl = document.getElementById('wallet-usd-balance');
            
            if (znEl && window.userState?.balance !== undefined) {
                znEl.innerText = `${window.formatBalance(window.userState.balance)} ZN`;
            }
            if (usdEl && window.userState?.usd_balance !== undefined) {
                usdEl.innerText = `$${window.formatBalance(window.userState.usd_balance)}`;
            }

            // 2. تحديث حالة ربط المحفظة
            updateWalletStatusUI();

            // 3. إرباط الأحداث للأزرار بأمان (Event Listeners)
            bindWalletEvents();

        } catch (err) {
            console.error("❌ خطأ غير متوقع بداخل wallet.js:", err);
        } finally {
            // إخفاء شاشة التحميل دائماً حتى لو حدث خطأ
            if (typeof hideLoadingScreen === 'function') {
                hideLoadingScreen();
            }
        }
    };

    function updateWalletStatusUI() {
        const addressText = document.getElementById('wallet-address-text');
        const connectBtn = document.getElementById('connect-wallet-btn');
        const disconnectBtn = document.getElementById('disconnect-wallet-btn');
        const statusBox = document.getElementById('wallet-status-box');

        const savedAddress = window.userState?.wallet_address;

        if (savedAddress) {
            if (addressText) addressText.innerText = `${savedAddress.slice(0, 6)}...${savedAddress.slice(-4)}`;
            if (statusBox) statusBox.className = "wallet-status connected";
            if (connectBtn) connectBtn.style.display = 'none';
            if (disconnectBtn) disconnectBtn.style.display = 'block';
        } else {
            if (addressText) addressText.innerText = "لم يتم ربط المحفظة";
            if (statusBox) statusBox.className = "wallet-status disconnected";
            if (connectBtn) connectBtn.style.display = 'block';
            if (disconnectBtn) disconnectBtn.style.display = 'none';
        }
    }

    function bindWalletEvents() {
        const connectBtn = document.getElementById('connect-wallet-btn');
        const disconnectBtn = document.getElementById('disconnect-wallet-btn');
        const withdrawBtn = document.getElementById('withdraw-btn');

        if (connectBtn && !connectBtn.dataset.bound) {
            connectBtn.dataset.bound = "true";
            connectBtn.addEventListener('click', async () => {
                const addr = prompt("أدخل عنوان محفظة TON الخاصة بك:");
                if (addr && addr.trim().length > 10) {
                    window.userState.wallet_address = addr.trim();
                    updateWalletStatusUI();
                    try {
                        await window.fetchAPI('/api/wallet/save', 'POST', { wallet_address: addr.trim() });
                    } catch(e) { console.warn("فشل حفظ المحفظة في السيرفر", e); }
                }
            });
        }

        if (disconnectBtn && !disconnectBtn.dataset.bound) {
            disconnectBtn.dataset.bound = "true";
            disconnectBtn.addEventListener('click', async () => {
                window.userState.wallet_address = null;
                updateWalletStatusUI();
                try {
                    await window.fetchAPI('/api/wallet/save', 'POST', { wallet_address: null });
                } catch(e) { console.warn("فشل إلغاء حفظ المحفظة", e); }
            });
        }

        if (withdrawBtn && !withdrawBtn.dataset.bound) {
            withdrawBtn.dataset.bound = "true";
            withdrawBtn.addEventListener('click', () => {
                if (!window.userState?.wallet_address) {
                    alert("يرجى ربط محفظة TON أولاً لطلب السحب.");
                    return;
                }
                alert("طلب السحب قيد التطوير وستتم إضافته قريباً!");
            });
        }
    }

    // تصدير الدوال على مستوى النطاق العام ليتعرف عليها game.js
    window.onWalletTabOpen = window.initWalletView;
})();

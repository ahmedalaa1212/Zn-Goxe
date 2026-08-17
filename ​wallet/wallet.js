(function () {
    let tonConnectUI = null;

    window.initWalletView = async function () {
        try {
            console.log("⚡ جاري فتح شاشة المحفظة...");

            // 1. تحديث بيانات الواجهة الرئيسية
            updateWalletHeaderUI();

            // 2. تهيئة TON Connect المباشر مع حماية من الأخطاء
            try {
                initTonConnectSDK();
            } catch (tcErr) {
                console.warn("TON Connect Initialization skipped/error:", tcErr);
            }

            // 3. ربط أزرار التبويب الداخلي
            setupSubTabNavigation();

            // 4. ربط أحداث الإيداع والسحب
            setupWalletActionEvents();

            // 5. تحميل سجل العمليات بشكل منفصل ومستقل
            loadWalletHistory().catch(e => console.warn("History load warn:", e));

        } catch (err) {
            console.error("❌ خطأ أثناء تهيئة المحفظة:", err);
        } finally {
            if (typeof hideLoadingScreen === 'function') {
                hideLoadingScreen();
            }
        }
    };

    function updateWalletHeaderUI() {
        const balEl = document.getElementById('wallet-main-balance');
        const usdEl = document.getElementById('wallet-usd-val');
        const addrEl = document.getElementById('wallet-address-display');
        const withdrawAddrInput = document.getElementById('withdraw-address-input');
        const connectBox = document.getElementById('wallet-connect-box');

        if (balEl && window.userState?.balance !== undefined) {
            balEl.innerText = `${window.formatBalance ? window.formatBalance(window.userState.balance) : window.userState.balance} ZN`;
        }
        if (usdEl && window.userState?.usd_balance !== undefined) {
            usdEl.innerText = `$${window.formatBalance ? window.formatBalance(window.userState.usd_balance) : window.userState.usd_balance} USD`;
        }

        const savedAddr = window.userState?.wallet_address;
        if (savedAddr && typeof savedAddr === 'string' && savedAddr.length > 8) {
            if (addrEl) addrEl.innerText = `${savedAddr.slice(0, 6)}...${savedAddr.slice(-4)}`;
            if (withdrawAddrInput) withdrawAddrInput.value = savedAddr;
            if (connectBox) connectBox.className = "connect-box connected";
        } else {
            if (addrEl) addrEl.innerText = "لم يتم ربط المحفظة";
            if (withdrawAddrInput) withdrawAddrInput.value = "";
            if (connectBox) connectBox.className = "connect-box disconnected";
        }
    }

    function initTonConnectSDK() {
        const container = document.getElementById('ton-connect-btn-container');
        if (!container) return;

        if (tonConnectUI) {
            return; // تم التهيئة مسبقاً
        }

        if (typeof TONConnectUI !== 'undefined') {
            try {
                tonConnectUI = new TONConnectUI.TonConnectUI({
                    manifestUrl: 'https://zn-goxe-production.up.railway.app/tonconnect-manifest.json',
                    buttonRootId: 'ton-connect-btn-container'
                });

                tonConnectUI.onStatusChange(wallet => {
                    if (wallet && wallet.account) {
                        const accountAddress = wallet.account.address;
                        window.userState = window.userState || {};
                        window.userState.wallet_address = accountAddress;
                        updateWalletHeaderUI();
                        if (typeof window.fetchAPI === 'function') {
                            window.fetchAPI('/api/wallet/save_address', 'POST', { wallet_address: accountAddress }).catch(e => {
                                console.warn("حفظ العنوان في السيرفر فشل:", e);
                            });
                        }
                    }
                });
            } catch (err) {
                console.warn("خطأ أثناء إنشاء TONConnectUI:", err);
                showTonConnectFallback(container);
            }
        } else {
            console.warn("مكتبة TONConnectUI غير متاحة حالياً.");
            showTonConnectFallback(container);
        }
    }

    function showTonConnectFallback(container) {
        if (!container) return;
        container.innerHTML = `
            <div style="background: rgba(255, 255, 255, 0.05); color: #aaa; padding: 10px; border-radius: 8px; text-align: center; font-size: 13px;">
                ⚠️ خدمة TON Connect غير متوفرة حالياً، يمكنك استخدام باقي خصائص المحفظة.
            </div>
        `;
    }

    function setupSubTabNavigation() {
        const wrapper = document.querySelector('.wallet-wrapper') || document;
        const tabBtns = wrapper.querySelectorAll('.w-tab-btn');
        const tabPanes = wrapper.querySelectorAll('.w-tab-pane');

        tabBtns.forEach(btn => {
            btn.onclick = function () {
                const targetTab = this.dataset.tab;
                
                // تحديث الأزرار
                tabBtns.forEach(b => {
                    b.classList.remove('active');
                    b.style.background = '#161f2e';
                });
                this.classList.add('active');
                this.style.background = '#0088cc';

                // تحديث التبويبات الصريحة
                tabPanes.forEach(p => {
                    p.classList.remove('active');
                    p.style.display = 'none';
                });

                const selectedPane = document.getElementById(`subtab-${targetTab}`);
                if (selectedPane) {
                    selectedPane.classList.add('active');
                    selectedPane.style.display = 'block';
                }

                if (targetTab === 'history') {
                    loadWalletHistory();
                }
            };
        });
    }

    function setupWalletActionEvents() {
        const copyBtn = document.getElementById('btn-copy-deposit');
        if (copyBtn && !copyBtn.dataset.bound) {
            copyBtn.dataset.bound = "true";
            copyBtn.onclick = () => {
                const addrInput = document.getElementById('deposit-address-input');
                if (addrInput && addrInput.value) {
                    navigator.clipboard.writeText(addrInput.value);
                    alert("تم نسخ عنوان الإيداع!");
                }
            };
        }

        const withdrawBtn = document.getElementById('btn-submit-withdraw');
        if (withdrawBtn && !withdrawBtn.dataset.bound) {
            withdrawBtn.dataset.bound = "true";
            withdrawBtn.onclick = async () => {
                const amountInput = document.getElementById('withdraw-amount-input');
                const amount = parseFloat(amountInput?.value || 0);
                const address = window.userState?.wallet_address;

                if (!address) return alert("يرجى ربط المحفظة أولاً.");
                if (isNaN(amount) || amount <= 0) return alert("يرجى إدخال مبلغ سحب صحيح.");
                if (amount > (window.userState?.balance || 0)) return alert("رصيدك غير كافٍ لتنفيذ العملية.");

                try {
                    const res = await window.fetchAPI('/api/wallet/withdraw', 'POST', { amount, address });
                    if (res && res.success) {
                        alert("تم تقديم طلب السحب بنجاح!");
                        if (res.new_balance !== undefined) {
                            window.userState.balance = res.new_balance;
                        }
                        updateWalletHeaderUI();
                        if (amountInput) amountInput.value = "";
                    } else {
                        alert(res?.error || "فشل تنفيذ السحب.");
                    }
                } catch (err) {
                    alert("حدث خطأ أثناء الاتصال بالسيرفر.");
                }
            };
        }
    }

    async function loadWalletHistory() {
        const historyContainer = document.getElementById('wallet-history-list');
        if (!historyContainer) return;

        try {
            const res = await window.fetchAPI('/api/wallet/history', 'GET');
            if (res && res.success && Array.isArray(res.history) && res.history.length > 0) {
                historyContainer.innerHTML = res.history.map(item => `
                    <div class="history-item ${item.type}" style="display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid rgba

(function () {
    let tonConnectUI = null;

    window.initWalletView = async function () {
        try {
            console.log("⚡ جاري فتح شاشة المحفظة...");

            // 1. تحديث بيانات الواجهة الرئيسية (الرصيد والعنوان)
            updateWalletHeaderUI();

            // 2. تهيئة TON Connect المباشر مع حماية لمنع تعطيل المحفظة عند الفشل
            try {
                initTonConnectSDK();
            } catch (tcErr) {
                console.warn("⚠️ TON Connect Initialization skipped/error:", tcErr);
            }

            // 3. ربط أزرار التبويب الداخلي
            setupSubTabNavigation();

            // 4. ربط أحداث الإيداع والسحب
            setupWalletActionEvents();

            // 5. تحميل سجل العمليات
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

        const formatFn = typeof window.formatBalance === 'function' 
            ? window.formatBalance 
            : (val) => Number(val || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });

        if (balEl && window.userState?.balance !== undefined) {
            balEl.innerText = `${formatFn(window.userState.balance)} ZN`;
        }
        if (usdEl && window.userState?.usd_balance !== undefined) {
            usdEl.innerText = `$${formatFn(window.userState.usd_balance)} USD`;
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

        if (typeof TONConnectUI !== 'undefined') {
            if (!tonConnectUI) {
                try {
                    tonConnectUI = new TONConnectUI.TonConnectUI({
                        manifestUrl: window.location.origin + '/tonconnect-manifest.json',
                        buttonRootId: 'ton-connect-btn-container'
                    });

                    tonConnectUI.onStatusChange(wallet => {
                        if (wallet && wallet.account) {
                            const accountAddress = wallet.account.address;
                            if (!window.userState) window.userState = {};
                            window.userState.wallet_address = accountAddress;
                            updateWalletHeaderUI();

                            const fetchFn = typeof window.fetchAPI === 'function' 
                                ? window.fetchAPI 
                                : async (url, method, body) => fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json());

                            fetchFn('/api/wallet/save_address', 'POST', { wallet_address: accountAddress }).catch(e => console.warn("Failed to save wallet address:", e));
                        }
                    });
                } catch (e) {
                    console.warn("⚠️ Error creating TONConnectUI instance:", e);
                }
            }
        } else {
            console.warn("⚠️ TONConnectUI غير معرف حالياً، ستعمل باقي واجهات المحفظة بشكل طبيعي.");
            if (container && container.children.length === 0) {
                container.innerHTML = `<div style="font-size: 12px; color: #888; padding: 5px;">ملاحظة: TON Connect غير محمل حالياً. يمكنك استخدام باقي خصائص المحفظة.</div>`;
            }
        }
    }

    function setupSubTabNavigation() {
        const wrapper = document.querySelector('.wallet-wrapper') || document;
        const tabBtns = wrapper.querySelectorAll('.w-tab-btn');
        const tabPanes = wrapper.querySelectorAll('.w-tab-pane');

        tabBtns.forEach(btn => {
            btn.onclick = function () {
                const targetTab = this.dataset.tab;

                tabBtns.forEach(b => {
                    b.classList.remove('active');
                    b.style.background = '#161f2e';
                });
                this.classList.add('active');
                this.style.background = '#0088cc';

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
                const address = window.userState?.wallet_address || document.getElementById('withdraw-address-input')?.value;

                if (!address) return alert("يرجى ربط المحفظة أو إدخال عنوان السحب أولاً.");
                if (isNaN(amount) || amount <= 0) return alert("يرجى إدخال مبلغ سحب صحيح.");
                if (window.userState && amount > (window.userState.balance || 0)) return alert("رصيدك غير كافٍ لتنفيذ العملية.");

                try {
                    const fetchFn = typeof window.fetchAPI === 'function'
                        ? window.fetchAPI
                        : async (url, method, body) => fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.json());

                    const res = await fetchFn('/api/wallet/withdraw', 'POST', { amount, address });
                    if (res && res.success) {
                        alert(res.message || "تم تقديم طلب السحب بنجاح!");
                        if (res.new_balance !== undefined && window.userState) {
                            window.userState.balance = res.new_balance;
                        }
                        if (amountInput) amountInput.value = "";
                        updateWalletHeaderUI();
                    } else {
                        alert(res?.error || "فشل تنفيذ السحب.");
                    }
                } catch (err) {
                    console.error("Withdraw Error:", err);
                    alert("حدث خطأ أثناء الاتصال بالسيرفر.");
                }
            };
        }
    }

    async function loadWalletHistory() {
        const historyContainer = document.getElementById('wallet-history-list');
        if (!historyContainer) return;

        try {
            const fetchFn = typeof window.fetchAPI === 'function'
                ? window.fetchAPI
                : async (url, method) => fetch(url, { method }).then(r => r.json());

            const res = await fetchFn('/api/wallet/history', 'GET');
            if (res && res.success && Array.isArray(res.history) && res.history.length > 0) {
                historyContainer.innerHTML = res.history.map(item => `
                    <div class="history-item ${item.type || 'withdraw'}" style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #333;">
                        <div class="h-info">
                            <div class="h-type" style="font-weight: bold; font-size: 14px; color: #fff;">
                                ${item.type === 'deposit' ? '📥 إيداع' : '📤 سحب'}
                            </div>
                            <div class="h-date" style="font-size: 12px; color: #888;">${item.date || ''}</div>
                        </div>
                        <div class="h-amount ${item.type || 'withdraw'}" style="font-weight: bold; color: ${item.type === 'deposit' ? '#4caf50' : '#f44336'};">
                            ${item.type === 'deposit' ? '+' : '-'}${item.amount} ZN
                        </div>
                    </div>
                `).join('');
            } else {
                historyContainer.innerHTML = `<div class="empty-history" style="padding: 15px; text-align: center; color: #aaa;">لا توجد معاملات مسجلة حتى الآن.</div>`;
            }
        } catch (e) {
            console.error("Error loading wallet history:", e);
            historyContainer.innerHTML = `<div class="empty-history" style="padding: 15px; text-align: center; color: #ff5555;">تعذر تحميل السجل.</div>`;
        }
    }

    window.onWalletTabOpen = window.initWalletView;
})();

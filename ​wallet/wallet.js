(function () {
    // دالة التهيئة الرئيسية لشاشة المحفظة
    window.initWalletView = async function () {
        try {
            console.log("⚡ جاري فتح شاشة المحفظة وتفعيل التنقل الداخلي...");

            // 1. تحديث بيانات الواجهة الرئيسية
            updateWalletHeaderUI();

            // 2. ربط أزرار التبويب الداخلي (Sub-Tabs)
            setupSubTabNavigation();

            // 3. ربط أحداث الإيداع والسحب
            setupWalletActionEvents();

            // 4. تحميل سجل العمليات
            await loadWalletHistory();

        } catch (err) {
            console.error("❌ خطأ أثناء تهيئة المحفظة:", err);
        } finally {
            // إخفاء شاشة التحميل لمنع التجمد
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
            balEl.innerText = `${window.formatBalance(window.userState.balance)} ZN`;
        }
        if (usdEl && window.userState?.usd_balance !== undefined) {
            usdEl.innerText = `$${window.formatBalance(window.userState.usd_balance)} USD`;
        }

        const savedAddr = window.userState?.wallet_address;
        if (savedAddr) {
            if (addrEl) addrEl.innerText = `${savedAddr.slice(0, 6)}...${savedAddr.slice(-4)}`;
            if (withdrawAddrInput) withdrawAddrInput.value = savedAddr;
            if (connectBox) connectBox.className = "connect-box connected";
        } else {
            if (addrEl) addrEl.innerText = "لم يتم ربط المحفظة";
            if (withdrawAddrInput) withdrawAddrInput.value = "";
            if (connectBox) connectBox.className = "connect-box disconnected";
        }
    }

    // إدارة التنقل بين القوائم الداخلية (إيداع / سحب / سجل)
    function setupSubTabNavigation() {
        const tabBtns = document.querySelectorAll('.w-tab-btn');
        const tabPanes = document.querySelectorAll('.w-tab-pane');

        tabBtns.forEach(btn => {
            btn.onclick = function () {
                const targetTab = this.dataset.tab;

                tabBtns.forEach(b => b.classList.remove('active'));
                tabPanes.forEach(p => p.classList.remove('active'));

                this.classList.add('active');
                const selectedPane = document.getElementById(`subtab-${targetTab}`);
                if (selectedPane) selectedPane.classList.add('active');

                if (targetTab === 'history') {
                    loadWalletHistory();
                }
            };
        });
    }

    function setupWalletActionEvents() {
        // زر ربط المحفظة
        const connectBtn = document.getElementById('btn-wallet-connect');
        if (connectBtn && !connectBtn.dataset.bound) {
            connectBtn.dataset.bound = "true";
            connectBtn.onclick = async () => {
                const addr = prompt("أدخل عنوان محفظة TON الخاصة بك:");
                if (addr && addr.trim().length > 10) {
                    window.userState.wallet_address = addr.trim();
                    updateWalletHeaderUI();
                    try {
                        await window.fetchAPI('/api/wallet/save_address', 'POST', { wallet_address: addr.trim() });
                    } catch (e) { console.warn("خطأ في حفظ المحفظة بالخادم", e); }
                }
            };
        }

        // نسخ عنوان الإيداع
        const copyBtn = document.getElementById('btn-copy-deposit');
        if (copyBtn && !copyBtn.dataset.bound) {
            copyBtn.dataset.bound = "true";
            copyBtn.onclick = () => {
                const addrInput = document.getElementById('deposit-address-input');
                if (addrInput) {
                    navigator.clipboard.writeText(addrInput.value);
                    alert("تم نسخ عنوان الإيداع!");
                }
            };
        }

        // تنفيذ طلب السحب
        const withdrawBtn = document.getElementById('btn-submit-withdraw');
        if (withdrawBtn && !withdrawBtn.dataset.bound) {
            withdrawBtn.dataset.bound = "true";
            withdrawBtn.onclick = async () => {
                const amount = parseFloat(document.getElementById('withdraw-amount-input')?.value || 0);
                const address = window.userState?.wallet_address;

                if (!address) {
                    alert("يرجى ربط المحفظة أولاً.");
                    return;
                }
                if (isNaN(amount) || amount <= 0) {
                    alert("يرجى إدخال مبلغ سحب صحيح.");
                    return;
                }
                if (amount > window.userState.balance) {
                    alert("رصيدك غير كافٍ لتنفيذ العملية.");
                    return;
                }

                try {
                    const res = await window.fetchAPI('/api/wallet/withdraw', 'POST', { amount, address });
                    if (res.success) {
                        alert("تم تقديم طلب السحب بنجاح!");
                        if (res.new_balance !== undefined) window.userState.balance = res.new_balance;
                        updateWalletHeaderUI();
                    } else {
                        alert(res.error || "فشل تنفيذ السحب.");
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
            if (res.success && res.history && res.history.length > 0) {
                historyContainer.innerHTML = res.history.map(item => `
                    <div class="history-item ${item.type}">
                        <div class="h-info">
                            <span class="h-type">${item.type === 'deposit' ? '📥 إيداع' : '📤 سحب'}</span>
                            <span class="h-date">${item.date}</span>
                        </div>
                        <div class="h-amount ${item.type}">${item.type === 'deposit' ? '+' : '-'}${item.amount} ZN</div>
                    </div>
                `).join('');
            } else {
                historyContainer.innerHTML = `<div class="empty-history">لا توجد معاملات مسجلة حتى الآن.</div>`;
            }
        } catch (e) {
            historyContainer.innerHTML = `<div class="empty-history">فشل تحميل السجل.</div>`;
        }
    }

    window.onWalletTabOpen = window.initWalletView;
})();

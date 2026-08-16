// wallet/wallet.js

(function() {
    const tg = window.Telegram?.WebApp;

    // 🎯 دالة التهيئة المربوطة بمحرك التبديل في game.js
    window.initWalletView = function() {
        if (tg) {
            tg.ready();
            tg.expand();
        }
        updateWalletUIFromState();
        window.loadWalletData();
        window.switchWalletTab('deposit');
    };

    // 🔄 مزامنة العرض الفوري مع Firebase / LocalState
    function updateWalletUIFromState() {
        if (!window.userState) return;
        
        const coinElem = document.getElementById('coin-balance');
        const usdElem = document.getElementById('usd-balance');

        if (coinElem) {
            const bal = parseFloat(window.userState.balance || 0);
            coinElem.innerText = typeof window.formatBalance === 'function' ? window.formatBalance(bal) : bal.toLocaleString('en-US');
        }
        if (usdElem) {
            const usd = parseFloat(window.userState.usd_balance || 0);
            usdElem.innerText = '$' + usd.toFixed(2);
        }
    }

    // 📡 الاستماع للتحديثات الحية من Firestore
    window.addEventListener('userStateUpdated', () => {
        updateWalletUIFromState();
    });

    // 💳 جلب البيانات عبر API الخادم
    window.loadWalletData = async function() {
        try {
            let data;
            if (typeof window.fetchAPI === 'function') {
                data = await window.fetchAPI('/api/wallet/info', 'POST');
            } else {
                const initData = tg?.initData || '';
                const response = await fetch('/api/wallet/info', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-Telegram-Init-Data': initData,
                        'Authorization': `Bearer ${initData}`
                    },
                    body: JSON.stringify({ initData })
                });
                data = await response.json();
            }

            if (data && data.success && data.wallet) {
                if (window.userState) {
                    if (data.wallet.balance !== undefined) window.userState.balance = parseFloat(data.wallet.balance);
                    if (data.wallet.usd_balance !== undefined) window.userState.usd_balance = parseFloat(data.wallet.usd_balance);
                }
                updateWalletUIFromState();
            }
        } catch (error) {
            console.error("❌ خطأ أثناء جلب رصيد المحفظة:", error);
        }
    };

    // 🔘 التبديل بين أزرار الأقسام الثلاثة
    window.switchWalletTab = function(tabName) {
        document.querySelectorAll('.btn-tab').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.content-section').forEach(sec => sec.classList.remove('active'));

        const activeBtn = document.querySelector(`.btn-tab[data-tab="${tabName}"]`);
        const activeSec = document.getElementById(`${tabName}-section`);

        if (activeBtn) activeBtn.classList.add('active');
        if (activeSec) activeSec.classList.add('active');

        if (tabName === 'deposit') loadDepositData();
        if (tabName === 'withdraw') loadWithdrawData();
        if (tabName === 'history') loadHistoryData();
    };

    // 📥 تحميل بيانات قسم الإيداع
    async function loadDepositData() {
        const container = document.getElementById('deposit-options');
        if (!container) return;

        try {
            let data;
            if (typeof window.fetchAPI === 'function') {
                data = await window.fetchAPI('/api/wallet/deposit/', 'GET');
            } else {
                const res = await fetch('/api/wallet/deposit/', { method: 'GET' });
                data = await res.json();
            }

            if (data && data.success && data.methods && data.methods.length > 0) {
                container.innerHTML = data.methods.map(m => `
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 12px; background: #0f172a; border: 1px solid #334155; border-radius: 12px; margin-bottom: 8px;">
                        <div>
                            <div style="font-weight: bold; font-size: 14px;">${m.name}</div>
                            <div style="font-size: 11px; color: #94a3b8;">${m.description || ''}</div>
                        </div>
                        <button onclick="window.initDeposit('${m.id}')" style="padding: 8px 16px; background: #10b981; color: #fff; border: none; border-radius: 8px; font-weight: bold; cursor: pointer; font-size: 13px;">شحن</button>
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<div class="empty-msg">وسائل الإيداع المتاحة ستظهر هنا قريباً.</div>';
            }
        } catch (e) {
            container.innerHTML = '<div class="empty-msg">وسائل الشحن التلقائي قيد التجهيز.</div>';
        }
    }

    // 📤 تحميل نموذج السحب
    async function loadWithdrawData() {
        const container = document.getElementById('withdraw-form');
        if (!container) return;

        container.innerHTML = `
            <div style="display: flex; flex-direction: column; gap: 12px;">
                <div>
                    <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">المبلغ المراد سحبه ($):</label>
                    <input type="number" id="withdraw-amount" placeholder="0.00" step="0.01" style="width: 100%; padding: 12px; border-radius: 10px; border: 1px solid #334155; background: #0f172a; color: #fff; font-size: 14px; box-sizing: border-box;">
                </div>
                <div>
                    <label style="font-size: 12px; color: #94a3b8; display: block; margin-bottom: 4px;">عنوان المحفظة (TON Wallet Address):</label>
                    <input type="text" id="withdraw-address" placeholder="UQ..." style="width: 100%; padding: 12px; border-radius: 10px; border: 1px solid #334155; background: #0f172a; color: #fff; font-size: 14px; box-sizing: border-box;">
                </div>
                <button onclick="window.submitWithdraw()" style="padding: 12px; background: #2563eb; color: #fff; border: none; border-radius: 10px; font-weight: bold; cursor: pointer; font-size: 14px; margin-top: 5px;">تأكيد طلب السحب</button>
            </div>
        `;
    }

    // 📜 تحميل سجلات العمليات
    async function loadHistoryData() {
        const container = document.getElementById('history-list');
        if (!container) return;

        try {
            let data;
            if (typeof window.fetchAPI === 'function') {
                data = await window.fetchAPI('/api/wallet/history/', 'POST');
            } else {
                const initData = tg?.initData || '';
                const response = await fetch('/api/wallet/history/', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-Telegram-Init-Data': initData,
                        'Authorization': `Bearer ${initData}`
                    },
                    body: JSON.stringify({ initData })
                });
                data = await response.json();
            }

            if (data && data.success && data.history && data.history.length > 0) {
                container.innerHTML = data.history.map(item => `
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px 0; border-bottom: 1px solid #334155; font-size: 13px;">
                        <span>${item.type === 'deposit' ? '📥 إيداع' : '📤 سحب'}</span>
                        <span style="font-weight: bold;">${item.amount}</span>
                        <span style="color: ${item.status === 'completed' ? '#10b981' : '#f59e0b'};">${item.status_text || item.status}</span>
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<div class="empty-msg">لا توجد سجلات عمليات سابقة.</div>';
            }
        } catch (e) {
            container.innerHTML = '<div class="empty-msg">لا توجد عمليات سابقة حتى الآن.</div>';
        }
    }

    // ⚡ إرسال طلب السحب
    window.submitWithdraw = async function() {
        const amountInput = document.getElementById('withdraw-amount');
        const addressInput = document.getElementById('withdraw-address');

        const amount = parseFloat(amountInput?.value);
        const address = addressInput?.value?.trim();

        if (!amount || amount <= 0 || !address) {
            const msg = "يرجى إدخال المبلغ وعنوان المحفظة بشكل صحيح!";
            if (tg?.showAlert) tg.showAlert(msg); else alert(msg);
            return;
        }

        try {
            let res;
            if (typeof window.fetchAPI === 'function') {
                res = await window.fetchAPI('/api/wallet/withdraw/request', 'POST', { amount, address });
            } else {
                const initData = tg?.initData || '';
                const response = await fetch('/api/wallet/withdraw/request', {
                    method: 'POST',
                    headers: { 
                        'Content-Type': 'application/json',
                        'X-Telegram-Init-Data': initData,
                        'Authorization': `Bearer ${initData}`
                    },
                    body: JSON.stringify({ initData, amount, address })
                });
                res = await response.json();
            }

            if (res && res.success) {
                const msg = "تم تقديم طلب السحب بنجاح!";
                if (tg?.showAlert) tg.showAlert(msg); else alert(msg);
                window.loadWalletData();
            } else {
                const msg = res?.error || "فشل إرسال طلب السحب";
                if (tg?.showAlert) tg.showAlert(msg); else alert(msg);
            }
        } catch (err) {
            console.error("❌ Withdraw error:", err);
            const msg = "حدث خطأ أثناء الاتصال بالسيرفر";
            if (tg?.showAlert) tg.showAlert(msg); else alert(msg);
        }
    };

    window.initDeposit = function(methodId) {
        const msg = `جاري تجهيز وسيلة الشحن (${methodId})...`;
        if (tg?.showAlert) tg.showAlert(msg); else alert(msg);
    };

    // التشغيل الفوري في حال تحميل الموديول وكان العرض مفضلاً
    if (document.getElementById('deposit-section')) {
        window.initWalletView();
    }
})();

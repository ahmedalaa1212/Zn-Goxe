window.walletModule = (function () {
    let currentTab = 'deposit';

    // تنسيق الأرقام العشرية: 4 أرقام للأرقام الصغيرة (< 100)، ورقمين للأرقام الكبيرة
    function formatSmartBalance(val) {
        const num = parseFloat(val || 0);
        if (isNaN(num)) return "0.00";
        if (num > 0 && num < 100) {
            return num.toFixed(4);
        }
        return num.toFixed(2);
    }

    // جلب الأرصدة مع إرسال الترويسات الآمنة وتحديث التنسيق
    async function fetchWalletBalances() {
        try {
            const tg = window.Telegram?.WebApp;
            const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || '';
            const initData = tg?.initData || '';

            const headers = { 'Content-Type': 'application/json' };
            if (userId) headers['X-Telegram-User-Id'] = String(userId);
            if (initData) headers['Authorization'] = `Bearer ${initData}`;

            const res = await fetch(`/api/wallet/data?user_id=${userId}`, { headers });
            if (!res.ok) throw new Error("Server response error");
            const data = await res.json();
            
            if (data.success) {
                const znElem = document.getElementById('zn-balance-display');
                const usdtElem = document.getElementById('usdt-balance-display');
                
                const znVal = data.zn_balance !== undefined ? data.zn_balance : (window.userState?.balance || 0);
                const usdtVal = data.usdt_balance !== undefined ? data.usdt_balance : (window.userState?.usd_balance || 0);

                if (znElem) znElem.innerText = formatSmartBalance(znVal);
                if (usdtElem) usdtElem.innerText = formatSmartBalance(usdtVal);
            }
        } catch (err) {
            console.warn("⚠️ استخدام البيانات المحلية مؤقتاً لتخفيف ضغط الاستعلامات:", err);
            const znElem = document.getElementById('zn-balance-display');
            const usdtElem = document.getElementById('usdt-balance-display');
            if (znElem && window.userState?.balance !== undefined) {
                znElem.innerText = formatSmartBalance(window.userState.balance);
            }
            if (usdtElem && window.userState?.usd_balance !== undefined) {
                usdtElem.innerText = formatSmartBalance(window.userState.usd_balance);
            }
        }
    }

    // التنقل السلس والآمن بين القوائم
    async function switchTab(tabName) {
        currentTab = tabName;

        // تحديث إضاءة الأزرار بالتسلسل المطلوب
        ['deposit', 'history', 'withdraw'].forEach(t => {
            const btn = document.getElementById(`tab-btn-${t}`);
            if (btn) {
                if (t === tabName) {
                    btn.style.background = '#0088cc';
                    btn.style.color = '#ffffff';
                    btn.style.border = 'none';
                    btn.style.boxShadow = '0 4px 10px rgba(0,136,204,0.3)';
                } else {
                    btn.style.background = 'rgba(255,255,255,0.08)';
                    btn.style.color = '#cccccc';
                    btn.style.border = '1px solid rgba(255,255,255,0.1)';
                    btn.style.boxShadow = 'none';
                }
            }
        });

        const container = document.getElementById('wallet-subview-container');
        if (!container) return;

        try {
            const cacheBuster = `?v=${Date.now()}`;
            let response = await fetch(`/wallet/${tabName}/${tabName}.html${cacheBuster}`);
            if (!response.ok) {
                response = await fetch(`wallet/${tabName}/${tabName}.html${cacheBuster}`);
            }

            if (response.ok) {
                container.innerHTML = await response.text();
                
                const initFuncName = `init_${tabName}_module`;
                if (typeof window[initFuncName] === 'function') {
                    window[initFuncName]();
                }
            } else {
                container.innerHTML = `<div style="text-align:center; padding:20px; color:#aaa; background:rgba(255,255,255,0.05); border-radius:12px;">جاري تحميل ${tabName}...</div>`;
            }
        } catch (e) {
            console.error(`فشل تحميل واجهة ${tabName}:`, e);
        }
    }

    function init() {
        fetchWalletBalances();
        switchTab('deposit');
    }

    return {
        init,
        switchTab,
        fetchWalletBalances,
        formatSmartBalance
    };
})();

if (document.getElementById('wallet-subview-container')) {
    window.walletModule.init();
}
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('wallet-subview-container')) {
        window.walletModule.init();
    }
});

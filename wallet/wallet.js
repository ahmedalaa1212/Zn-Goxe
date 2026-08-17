window.walletModule = (function () {
    let currentTab = 'deposit';
    let isListening = false;

    // تنسيق الأرقام العشرية: 4 أرقام للأرقام الصغيرة (< 100)، ورقمين للأرقام الكبيرة
    function formatSmartBalance(val) {
        const num = parseFloat(val || 0);
        if (isNaN(num)) return "0.00";
        if (num > 0 && num < 100) {
            return num.toFixed(4);
        }
        return num.toFixed(2);
    }

    // تحديث الواجهة فورياً من الحالة المحلية بالذاكرة (0ms Latency)
    function updateBalancesUI() {
        const znElem = document.getElementById('zn-balance-display');
        const usdtElem = document.getElementById('usdt-balance-display');

        const znVal = window.userState?.balance !== undefined ? window.userState.balance : (window.PlayerData?.balance || 0);
        const usdtVal = window.userState?.usd_balance !== undefined ? window.userState.usd_balance : (window.PlayerData?.usd_balance || 0);

        if (znElem) znElem.innerText = formatSmartBalance(znVal);
        if (usdtElem) usdtElem.innerText = formatSmartBalance(usdtVal);
    }

    // الاستماع المباشر للتغيرات في الفايربيس والحالة العامة للعبة
    function attachRealtimeListeners() {
        if (isListening) return;
        isListening = true;

        window.addEventListener('userStateUpdated', () => {
            updateBalancesUI();
        });
    }

    // جلب الأرصدة من السيرفر كبديل موازي دون تعطيل سرعة العرض المباشر
    async function fetchWalletBalances() {
        updateBalancesUI();

        try {
            const tg = window.Telegram?.WebApp;
            const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || '';
            const initData = tg?.initData || '';

            if (!userId) return;

            const headers = { 'Content-Type': 'application/json' };
            if (userId) headers['X-Telegram-User-Id'] = String(userId);
            if (initData) headers['Authorization'] = `Bearer ${initData}`;

            const res = await fetch(`/api/wallet/data?user_id=${userId}`, { headers });
            if (!res.ok) throw new Error("Server response error");
            const data = await res.json();
            
            if (data.success) {
                if (window.userState) {
                    if (data.zn_balance !== undefined) window.userState.balance = parseFloat(data.zn_balance);
                    if (data.usdt_balance !== undefined) window.userState.usd_balance = parseFloat(data.usdt_balance);
                }
                updateBalancesUI();
            }
        } catch (err) {
            console.warn("⚠️ تم الاعتماد على المزامنة اللحظية المحلية والفايربيس:", err);
            updateBalancesUI();
        }
    }

    // التنقل السلس والآمن بين القوائم
    async function switchTab(tabName) {
        currentTab = tabName;

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
        attachRealtimeListeners();
        updateBalancesUI();
        fetchWalletBalances();
        switchTab(currentTab || 'deposit');
    }

    return {
        init,
        switchTab,
        fetchWalletBalances,
        updateBalancesUI,
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

window.walletModule = (function () {
    let currentTab = 'deposit';
    let isListening = false;
    const viewCache = {}; // تخزين القوائم للتحميل اللحظي وبدون إعادة جلب

    // تنسيق الأرقام العشرية بشكل ثابت يمنع التمدد المفاجئ
    function formatSmartBalance(val) {
        const num = parseFloat(val || 0);
        if (isNaN(num)) return "0.00";
        if (num > 0 && num < 100) {
            return num.toFixed(4);
        }
        return num.toFixed(2);
    }

    // تحديث قيم النصوص فقط لمنع اهتزاز القوائم الفرعية
    function updateBalancesUI() {
        const znElem = document.getElementById('zn-balance-display');
        const usdtElem = document.getElementById('usdt-balance-display');

        const znVal = window.userState?.balance !== undefined ? window.userState.balance : (window.PlayerData?.balance || 0);
        const usdtVal = window.userState?.usd_balance !== undefined ? window.userState.usd_balance : (window.PlayerData?.usd_balance || 0);

        const newZnText = formatSmartBalance(znVal);
        const newUsdtText = formatSmartBalance(usdtVal);

        if (znElem && znElem.innerText !== newZnText) znElem.innerText = newZnText;
        if (usdtElem && usdtElem.innerText !== newUsdtText) usdtElem.innerText = newUsdtText;
    }

    function attachRealtimeListeners() {
        if (isListening) return;
        isListening = true;

        window.addEventListener('userStateUpdated', () => {
            updateBalancesUI();
        });
    }

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
            console.warn("⚠️ اعتماد التحديث اللحظي المحلي:", err);
            updateBalancesUI();
        }
    }

    // الربط والتنقل الثابت بين قوائم (الإيداع - السجلات - السحب)
    async function switchTab(tabName, force = false) {
        if (currentTab === tabName && !force && document.getElementById('wallet-subview-container')?.children.length > 0) {
            return;
        }
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

        // استرجاع القائمة فوراً إذا كانت مخزنة مسبقاً لمنع الرشة والاهتزاز
        if (viewCache[tabName]) {
            container.innerHTML = viewCache[tabName];
            executeSubModuleInit(tabName);
            return;
        }

        try {
            const cacheBuster = `?v=${Date.now()}`;
            let response = await fetch(`/wallet/${tabName}/${tabName}.html${cacheBuster}`);
            if (!response.ok) {
                response = await fetch(`wallet/${tabName}/${tabName}.html${cacheBuster}`);
            }

            if (response.ok) {
                const htmlContent = await response.text();
                viewCache[tabName] = htmlContent;
                container.innerHTML = htmlContent;
                executeSubModuleInit(tabName);
            } else {
                container.innerHTML = `<div style="text-align:center; padding:20px; color:#aaa; background:rgba(255,255,255,0.05); border-radius:12px;">جاري تحميل ${tabName}...</div>`;
            }
        } catch (e) {
            console.error(`فشل تحميل واجهة ${tabName}:`, e);
        }
    }

    function executeSubModuleInit(tabName) {
        const initFuncName = `init_${tabName}_module`;
        if (typeof window[initFuncName] === 'function') {
            window[initFuncName]();
        } else if (window[`${tabName}Module`]?.init) {
            window[`${tabName}Module`].init();
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

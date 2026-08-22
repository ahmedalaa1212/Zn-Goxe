window.walletModule = (function () {
    let currentTab = 'deposit';
    let isListening = false;
    let isInitialized = false;
    let lastFetchTime = 0;
    const viewCache = {}; // تخزين القوائم للتحميل اللحظي والحد من التكرار

    function formatSmartBalance(val) {
        if (typeof val === 'string') {
            val = val.replace(/[^0-9.-]/g, '');
        }
        const num = parseFloat(val || 0);
        if (isNaN(num)) return "0.00";

        if (num >= 1000) {
            return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
        }
        if (num > 0 && num < 100) {
            return num.toFixed(4);
        }
        return num.toFixed(2);
    }

    function getGlobalBalance(keys) {
        const sources = [
            window.userState,
            window.PlayerData,
            window.currentUser,
            window.user,
            window.appData
        ];

        for (const src of sources) {
            if (!src) continue;
            for (const key of keys) {
                if (src[key] !== undefined && src[key] !== null) {
                    let val = src[key];
                    if (typeof val === 'string') val = val.replace(/[^0-9.-]/g, '');
                    const num = parseFloat(val);
                    if (!isNaN(num)) return num;
                }
            }
        }
        return null;
    }

    function updateBalancesUI() {
        const znElem = document.getElementById('zn-balance-display');
        const usdtElem = document.getElementById('usdt-balance-display');

        const znVal = getGlobalBalance(['balance', 'zn_balance', 'user_balance', 'coins']) ?? 0;
        const usdtVal = getGlobalBalance(['usd_balance', 'usdt_balance', 'dollars', 'usd']) ?? 0;

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

    async function fetchWalletBalances(force = false) {
        updateBalancesUI();

        // منع التكرار المفرط للطلبات عند الضغط المتكرر (حد أدنى 15 ثانية بين الطلبات للشبكة)
        const now = Date.now();
        if (!force && lastFetchTime && (now - lastFetchTime < 15000)) {
            return;
        }
        lastFetchTime = now;

        try {
            const tg = window.Telegram?.WebApp;
            const userId = tg?.initDataUnsafe?.user?.id || 
                           window.userState?.tg_id || window.userState?.user_id || window.userState?.id ||
                           window.PlayerData?.tg_id || window.PlayerData?.user_id || window.PlayerData?.id || '';
            const initData = tg?.initData || '';

            if (!userId) {
                updateBalancesUI();
                return;
            }

            const headers = { 'Content-Type': 'application/json' };
            if (userId) headers['X-Telegram-User-Id'] = String(userId);
            if (initData) headers['Authorization'] = `Bearer ${initData}`;

            const res = await fetch(`/api/wallet/data?user_id=${userId}`, { headers });
            if (!res.ok) throw new Error("Server response error");
            const data = await res.json();
            
            if (data.success) {
                const newZn = parseFloat(data.zn_balance || 0);
                const newUsdt = parseFloat(data.usdt_balance || 0);

                if (!window.userState) window.userState = {};

                window.userState.balance = newZn;
                window.userState.zn_balance = newZn;
                window.userState.usd_balance = newUsdt;
                window.userState.usdt_balance = newUsdt;

                if (window.PlayerData) {
                    window.PlayerData.balance = window.userState.balance;
                    window.PlayerData.zn_balance = window.userState.zn_balance;
                    window.PlayerData.usd_balance = window.userState.usd_balance;
                    window.PlayerData.usdt_balance = window.userState.usdt_balance;
                }

                updateBalancesUI();
            }
        } catch (err) {
            console.warn("⚠️ اعتماد التحديث اللحظي المحلي:", err);
            updateBalancesUI();
        }
    }

    async function ensureSubModuleScriptLoaded(tabName) {
        const moduleName = `${tabName}Module`;
        if (window[moduleName]) return;

        return new Promise((resolve) => {
            const scriptId = `script-submodule-${tabName}`;
            if (document.getElementById(scriptId)) {
                resolve();
                return;
            }
            const script = document.createElement('script');
            script.id = scriptId;
            script.src = `wallet/${tabName}/${tabName}.js?v=${Date.now()}`;
            script.onload = () => resolve();
            script.onerror = () => {
                console.error(`⚠️ فشل تحميل السكربت: wallet/${tabName}/${tabName}.js`);
                resolve();
            };
            document.head.appendChild(script);
        });
    }

    async function switchTab(tabName, force = false) {
        const container = document.getElementById('wallet-subview-container');

        // منع إعادة التحميل والـ Refresh إذا كانت التبويبة المطلوبة معروضة بالفعل ومحملة
        if (!force && currentTab === tabName && container && container.children.length > 0 && container.getAttribute('data-active-tab') === tabName) {
            return;
        }

        currentTab = tabName;

        // تحديث تنسيق الأزرار
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

        if (!container) return;
        container.setAttribute('data-active-tab', tabName);

        updateBalancesUI();

        // استخدام التخزين المؤقت لمنع الـ Refresh والإحضار المكرر
        if (viewCache[tabName]) {
            container.innerHTML = viewCache[tabName];
            await ensureSubModuleScriptLoaded(tabName);
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
                
                await ensureSubModuleScriptLoaded(tabName);
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

    function init(force = false) {
        attachRealtimeListeners();
        updateBalancesUI();

        const container = document.getElementById('wallet-subview-container');
        const isAlreadyLoaded = container && container.children.length > 0;

        // إذا تم التهيئة مسبقاً والصفحة معروضة، لا تقم بأي ريفرش أو إعادة بناء
        if (isInitialized && isAlreadyLoaded && !force) {
            fetchWalletBalances(false);
            return;
        }

        isInitialized = true;
        fetchWalletBalances(force);
        switchTab(currentTab || 'deposit', force);
    }

    function resetInitState() {
        isInitialized = false;
    }

    return {
        init,
        switchTab,
        fetchWalletBalances,
        updateBalancesUI,
        formatSmartBalance,
        resetInitState
    };
})();

if (document.getElementById('wallet-subview-container') && !window.walletModule._autoStarted) {
    window.walletModule._autoStarted = true;
    window.walletModule.init();
}
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('wallet-subview-container') && !window.walletModule._autoStarted) {
        window.walletModule._autoStarted = true;
        window.walletModule.init();
    }
});

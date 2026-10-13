// wallet/wallet.js
// =================================================================
// 👛 ZN Goxe - Wallet Module (Supabase PostgreSQL Sync & Instant Balances)
// =================================================================

window.walletModule = (function () {
    let currentTab = 'deposit';
    let isListening = false;
    let isWalletRendered = false; 
    let pollInterval = null;
    let lastFetchTime = 0;
    const viewCache = {};

    function formatSmartBalance(val) {
        if (typeof val === 'string') {
            val = val.replace(/[^0-9.-]/g, '');
        }
        const num = parseFloat(val || 0);
        if (isNaN(num)) return "0.0000";
        return num.toFixed(4);
    }

    function formatSmartBalanceHTML(val) {
        const plainStr = formatSmartBalance(val);
        const parts = plainStr.split('.');
        return `${parts[0]}<span style="font-size: 0.72em; opacity: 0.8; font-weight: normal;">.${parts[1]}</span>`;
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
        return 0.0; 
    }

    function updateBalancesUI() {
        // قراءة القيم من الـ Cache أو من الذاكرة
        const znVal = getGlobalBalance(['balance', 'zn_balance', 'user_balance', 'coins']) ?? 0;
        const usdtVal = getGlobalBalance(['usd_balance', 'usdt_balance', 'dollars', 'usd']) ?? 0;
        const znxVal = getGlobalBalance(['znx_balance', 'total_znx_earned', 'znx']) ?? 0;

        const newZnHTML = formatSmartBalanceHTML(znVal);
        const newUsdtHTML = formatSmartBalanceHTML(usdtVal);
        const newZnxHTML = formatSmartBalanceHTML(znxVal);

        // 1. التحديث بقوة العنف للأيديهات الشائعة (Force Update By IDs)
        const commonZnIds = ['zn-balance-display', 'top-balance', 'top-balance-shop', 'header-zn-balance', 'user-balance-zn'];
        const commonUsdtIds = ['usdt-balance-display', 'shop-usd-text', 'header-usd-balance'];
        const commonZnxIds = ['znx-balance-display', 'top-znx-balance', 'header-znx-balance'];

        commonZnIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = `${newZnHTML} ZN`;
        });

        commonUsdtIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = `<span style="color:#00cc66;">$</span> ${newUsdtHTML}`;
        });

        commonZnxIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerHTML = `ZNX ${newZnxHTML}`;
        });

        // 2. تحديث شامل بـ Query Selector لضمان عدم هروب أي كلاس (Catch All Elements)
        document.querySelectorAll('div, span, p, h1, h2, h3, h4, h5').forEach(el => {
            // التحقق من أن العنصر يحتوي على الكلمة فقط ولا يحتوي على أبناء (تجنب مسح تصميم الصفحة)
            if (el.children.length === 0 || el.classList.contains('zn-balance-display') || el.classList.contains('user-balance')) {
                const text = el.textContent.trim();
                
                if (text.startsWith('ZNX') && text.match(/[0-9]/)) {
                    el.innerHTML = `ZNX ${newZnxHTML}`;
                } else if (text.endsWith('ZN') && text.match(/[0-9]/)) {
                    el.innerHTML = `${newZnHTML} ZN`;
                } else if (text.startsWith('$') && text.match(/[0-9]/)) {
                    el.innerHTML = `<span style="color:#00cc66;">$</span> ${newUsdtHTML}`;
                }
            }
        });
    }

    function applyNewBalances(zn, usdt, znx) {
        const newZn = parseFloat(zn || 0);
        const newUsdt = parseFloat(usdt || 0);
        const newZnx = parseFloat(znx || 0);

        // حقن القيم مباشرة في الأوبجكتات العامة لتقرأها الدوال الأخرى
        if (!window.userState) window.userState = {};
        window.userState.balance = newZn;
        window.userState.zn_balance = newZn;
        window.userState.usd_balance = newUsdt;
        window.userState.usdt_balance = newUsdt;
        window.userState.znx_balance = newZnx;
        
        if (!window.PlayerData) window.PlayerData = {};
        window.PlayerData.balance = newZn;
        window.PlayerData.usd_balance = newUsdt;
        window.PlayerData.znx_balance = newZnx;

        // نداء التحديث القسري للواجهة
        updateBalancesUI();
        
        // إطلاق إيفنت لكي تقوم الشاشات الأخرى بتحديث نفسها (مثل المتجر)
        window.dispatchEvent(new CustomEvent('userStateUpdated'));
    }

    function attachRealtimeListeners() {
        if (isListening) return;
        isListening = true;

        window.addEventListener('userStateUpdated', () => {
            updateBalancesUI();
        });

        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                fetchWalletBalances(true);
            }
        });
    }

    async function fetchWalletBalances(force = false) {
        updateBalancesUI();

        const now = Date.now();
        if (!force && lastFetchTime && (now - lastFetchTime < 1000)) {
            return;
        }
        lastFetchTime = now;

        try {
            const tg = window.Telegram?.WebApp;
            
            // جلب الأيدي بكل الطرق الممكنة لمنع إرسال طلب فارغ للسيرفر
            let userId = tg?.initDataUnsafe?.user?.id || 
                         window.userState?.tg_id || window.userState?.user_id || window.userState?.id ||
                         window.PlayerData?.tg_id || window.PlayerData?.user_id || '';
                         
            const initData = tg?.initData || '';

            if (!userId || String(userId) === 'undefined') {
                return;
            }

            const headers = { 'Content-Type': 'application/json' };
            headers['X-Telegram-User-Id'] = String(userId);
            if (initData) headers['Authorization'] = `Bearer ${initData}`;

            const res = await fetch(`/api/wallet/data?user_id=${userId}&t=${Date.now()}`, { 
                headers, 
                cache: 'no-store' 
            });
            
            if (!res.ok) throw new Error("Server response error");
            const data = await res.json();
            
            if (data.success) {
                applyNewBalances(data.zn_balance, data.usdt_balance, data.znx_balance);
            }
        } catch (err) {
            console.warn("⚠️ فشل جلب الرصيد من السيرفر، يتم الاعتماد على الرصيد المحلي:");
            updateBalancesUI();
        }
    }

    function startAutoPolling() {
        if (pollInterval) clearInterval(pollInterval);
        // تحديث كل 3 ثواني للحفاظ على تزامن Supabase بشكل دائم
        pollInterval = setInterval(() => {
            fetchWalletBalances(true);
        }, 3000);
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
                console.error(`⚠️ فشل تحميل السكربت الفرعي: wallet/${tabName}/${tabName}.js`);
                resolve();
            };
            document.head.appendChild(script);
        });
    }

    async function switchTab(tabName, force = false) {
        const container = document.getElementById('wallet-subview-container');

        if (!force && currentTab === tabName && container && container.children.length > 0 && container.getAttribute('data-active-tab') === tabName) {
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

        if (!container) return;
        container.setAttribute('data-active-tab', tabName);

        fetchWalletBalances(true);

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
        const isSubContentPresent = container && container.children.length > 0;

        if (!force && isWalletRendered && isSubContentPresent) {
            fetchWalletBalances(true);
            return;
        }

        isWalletRendered = true;
        fetchWalletBalances(true);
        startAutoPolling();
        switchTab(currentTab || 'deposit', force);
    }

    return {
        init,
        switchTab,
        fetchWalletBalances,
        updateBalancesUI,
        formatSmartBalance,
        formatSmartBalanceHTML
    };
})();

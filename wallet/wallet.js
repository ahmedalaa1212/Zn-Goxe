// wallet/wallet.js
// =================================================================
// 👛 ZN Goxe - Wallet Module (Realtime Firebase Sync & Instant Balances)
// =================================================================

window.walletModule = (function () {
    let currentTab = 'deposit';
    let isListening = false;
    let isWalletRendered = false; 
    let pollInterval = null;
    let unsubscribeFirestore = null;
    let lastFetchTime = 0;
    const viewCache = {};

    // 🎯 توحيد عرض الأرقام العشرية كـ نص عادي
    function formatSmartBalance(val) {
        if (typeof val === 'string') {
            val = val.replace(/[^0-9.-]/g, '');
        }
        const num = parseFloat(val || 0);
        if (isNaN(num)) return "0.0000";

        return num.toFixed(4);
    }

    // 🎯 نسق جديد لتصغير وتمييز الأرقام العشرية عن الرقم الصحيح في الواجهة
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
        return null;
    }

    function updateBalancesUI() {
        const znElem = document.getElementById('zn-balance-display');
        const usdtElem = document.getElementById('usdt-balance-display');
        const znxElem = document.getElementById('znx-balance-display');

        const znVal = getGlobalBalance(['balance', 'zn_balance', 'user_balance', 'coins']) ?? 0;
        const usdtVal = getGlobalBalance(['usd_balance', 'usdt_balance', 'dollars', 'usd']) ?? 0;
        const znxVal = getGlobalBalance(['znx_balance', 'total_znx_earned', 'znx']) ?? 0;

        const newZnHTML = formatSmartBalanceHTML(znVal);
        const newUsdtHTML = formatSmartBalanceHTML(usdtVal);
        const newZnxHTML = formatSmartBalanceHTML(znxVal);

        if (znElem && znElem.innerHTML !== newZnHTML) znElem.innerHTML = newZnHTML;
        if (usdtElem && usdtElem.innerHTML !== newUsdtHTML) usdtElem.innerHTML = newUsdtHTML;
        if (znxElem && znxElem.innerHTML !== newZnxHTML) znxElem.innerHTML = newZnxHTML;

        // تحديث جميع عناصِر الرصيد العلوية بصفحات التطبيق الأخرى
        const elBalances = document.querySelectorAll('.zn-balance-display, #top-balance-wallet, #top-balance, #header-zn-balance, .user-balance');
        elBalances.forEach(el => {
            if (el.id !== 'zn-balance-display' && el.id !== 'znx-balance-display') {
                if (el.textContent.includes('ZNX')) {
                    el.innerHTML = `${newZnxHTML} ZNX`;
                } else if (el.textContent.includes('ZN')) {
                    el.innerHTML = `${newZnHTML} ZN`;
                } else {
                    el.innerHTML = newZnHTML;
                }
            }
        });
    }

    function applyNewBalances(zn, usdt, znx) {
        const newZn = parseFloat(zn || 0);
        const newUsdt = parseFloat(usdt || 0);
        const newZnx = parseFloat(znx || 0);

        if (!window.userState) window.userState = {};
        window.userState.balance = newZn;
        window.userState.zn_balance = newZn;
        window.userState.usd_balance = newUsdt;
        window.userState.usdt_balance = newUsdt;
        window.userState.znx_balance = newZnx;
        window.userState.total_znx_earned = newZnx;

        if (window.PlayerData) {
            window.PlayerData.balance = newZn;
            window.PlayerData.zn_balance = newZn;
            window.PlayerData.usd_balance = newUsdt;
            window.PlayerData.usdt_balance = newUsdt;
            window.PlayerData.znx_balance = newZnx;
        }

        updateBalancesUI();
    }

    function setupFirestoreRealtimeListener(userId) {
        if (!userId) return false;
        const strUserId = String(userId);

        try {
            let dbInstance = window.db || (window.firebase && window.firebase.firestore ? window.firebase.firestore() : null);
            if (dbInstance && typeof dbInstance.collection === 'function') {
                if (unsubscribeFirestore) unsubscribeFirestore();

                unsubscribeFirestore = dbInstance.collection('users').doc(strUserId).onSnapshot((doc) => {
                    if (doc.exists) {
                        const data = doc.data();
                        const zn = data.balance ?? data.zn_balance ?? 0;
                        const usdt = data.usd_balance ?? data.usdt_balance ?? (data.upgrades?.usd_balance) ?? 0;
                        const znx = data.znx_balance ?? data.total_znx_earned ?? data.znx ?? 0;
                        
                        applyNewBalances(zn, usdt, znx);
                    }
                }, (err) => {
                    console.warn("⚠️ تنبيه استماع الفيربيس المباشر:", err);
                });
                return true;
            }
        } catch (e) {
            console.warn("⚠️ لم يتم تفعيل SDK الفيربيس المباشر للواجهة، الاعتماد على المزامنة السريعة:", e);
        }
        return false;
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
        // حظر بسيط لمدة ثانية واحدة فقط لمنع التكرار الشديد بدلاً من 30 ثانية
        if (!force && lastFetchTime && (now - lastFetchTime < 1000)) {
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

            // محاولة ربط لسنر الفيربيس المباشر إن أمكن
            setupFirestoreRealtimeListener(userId);

            const headers = { 'Content-Type': 'application/json' };
            if (userId) headers['X-Telegram-User-Id'] = String(userId);
            if (initData) headers['Authorization'] = `Bearer ${initData}`;

            const res = await fetch(`/api/wallet/data?user_id=${userId}&t=${Date.now()}`, { headers, cache: 'no-store' });
            if (!res.ok) throw new Error("Server response error");
            const data = await res.json();
            
            if (data.success) {
                applyNewBalances(data.zn_balance, data.usdt_balance, data.znx_balance);
            }
        } catch (err) {
            console.warn("⚠️ اعتماد التحديث اللحظي المحلي:", err);
            updateBalancesUI();
        }
    }

    function startAutoPolling() {
        if (pollInterval) clearInterval(pollInterval);
        // تحديث سريع كل 3 ثوانٍ لضمان الانعكاس اللحظي التام لأي تغيير من الفيربيس
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
                console.error(`⚠️ فشل تحميل السكربت: wallet/${tabName}/${tabName}.js`);
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

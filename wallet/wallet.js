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

    // 🎯 دالة التحديث المباشر للواجهة
    function directUpdateUI(znVal, usdtVal, znxVal) {
        const newZnHTML = formatSmartBalanceHTML(znVal);
        const newUsdtHTML = formatSmartBalanceHTML(usdtVal);
        const newZnxHTML = formatSmartBalanceHTML(znxVal);

        // 1. تحديث عناصر المحفظة الداخلية (إذا كانت موجودة في الـ DOM)
        const znElem = document.getElementById('zn-balance-display');
        const usdtElem = document.getElementById('usdt-balance-display');
        const znxElem = document.getElementById('znx-balance-display');

        if (znElem) znElem.innerHTML = newZnHTML;
        if (usdtElem) usdtElem.innerHTML = newUsdtHTML;
        if (znxElem) znxElem.innerHTML = newZnxHTML;

        // 2. تحديث الشاشة العلوية للتطبيق (Header) وأي مكان آخر يظهر فيه الرصيد
        const topBalances = document.querySelectorAll('#top-balance, #top-balance-shop, #header-zn-balance, .user-balance, .zn-balance-display');
        topBalances.forEach(el => {
            if (el.id !== 'zn-balance-display' && el.id !== 'znx-balance-display' && el.id !== 'usdt-balance-display') {
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

    // الدالة المسؤولة عن حقن القيم في الكاش وتحديث الواجهة
    function applyNewBalances(zn, usdt, znx) {
        const newZn = parseFloat(zn || 0);
        const newUsdt = parseFloat(usdt || 0);
        const newZnx = parseFloat(znx || 0);

        // تحديث جميع الكائنات العامة في التطبيق لمنع ظهور الأصفار لاحقاً
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

        // تحديث الواجهة مباشرة بالأرقام الجديدة
        directUpdateUI(newZn, newUsdt, newZnx);
        
        // إطلاق الحدث لتحديث باقي مكونات التطبيق (مثل المتجر)
        window.dispatchEvent(new CustomEvent('userStateUpdated'));
    }

    function attachRealtimeListeners() {
        if (isListening) return;
        isListening = true;

        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) {
                fetchWalletBalances(true);
            }
        });
    }

    async function fetchWalletBalances(force = false) {
        const now = Date.now();
        if (!force && lastFetchTime && (now - lastFetchTime < 1000)) {
            return;
        }
        lastFetchTime = now;

        try {
            const tg = window.Telegram?.WebApp;
            
            // جلب معرف المستخدم بكل الطرق الممكنة لضمان عدم إرسال طلب فارغ
            let userId = tg?.initDataUnsafe?.user?.id || 
                         window.userState?.tg_id || window.userState?.user_id || window.userState?.id ||
                         window.PlayerData?.tg_id || window.PlayerData?.user_id || '';
                         
            const initData = tg?.initData || '';

            if (!userId || userId === 'undefined') {
                return; // لا ترسل الطلب إذا لم يكن هناك مستخدم
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
                // إرسال البيانات فوراً إلى دالة التطبيق لتحديث الواجهة والكاش
                applyNewBalances(data.zn_balance, data.usdt_balance, data.znx_balance);
            }
        } catch (err) {
            console.warn("⚠️ فشل جلب الرصيد من السيرفر.");
        }
    }

    function startAutoPolling() {
        if (pollInterval) clearInterval(pollInterval);
        // تحديث كل 3 ثواني
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

        // جلب الأرصدة عند تبديل التبويب
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

        const container = document.getElementById('wallet-subview-container');
        const isSubContentPresent = container && container.children.length > 0;

        if (!force && isWalletRendered && isSubContentPresent) {
            fetchWalletBalances(true);
            return;
        }

        isWalletRendered = true;
        fetchWalletBalances(true); // جلب الأرصدة عند التهيئة
        startAutoPolling();
        switchTab(currentTab || 'deposit', force);
    }

    return {
        init,
        switchTab,
        fetchWalletBalances,
        formatSmartBalance,
        formatSmartBalanceHTML
    };
})();

// wallet/wallet.js
// =================================================================
// 👛 ZN Goxe - Wallet Module (Supabase PostgreSQL Instant Sync)
// =================================================================

window.walletModule = (function () {
    let currentTab = 'deposit';
    let eventsBound = false;
    let isWalletRendered = false;
    let pollInterval = null;
    let fastRetryTimer = null;
    let lastFetchTime = 0;
    let isSyncingState = false;
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

    // تحديث كافة عناصر الـ DOM التي تعرض الأرصدة
    function directUpdateUI(znVal, usdtVal, znxVal) {
        const newZnHTML = formatSmartBalanceHTML(znVal);
        const newUsdtHTML = formatSmartBalanceHTML(usdtVal);
        const newZnxHTML = formatSmartBalanceHTML(znxVal);

        // تحديث المربعات الكبيرة داخل المحفظة
        const znElem = document.getElementById('zn-balance-display');
        const usdtElem = document.getElementById('usdt-balance-display') || document.getElementById('usd-balance-display');
        const znxElem = document.getElementById('znx-balance-display');

        if (znElem) znElem.innerHTML = newZnHTML;
        if (usdtElem) usdtElem.innerHTML = newUsdtHTML;
        if (znxElem) znxElem.innerHTML = newZnxHTML;

        // تحديث كل الأشرطة العلوية في كل الواجهات (المزرعة، المتجر، إلخ)
        const topBalances = document.querySelectorAll('#top-balance, #top-balance-shop, #header-zn-balance, .user-balance, .zn-balance-display');
        topBalances.forEach(el => {
            if (el.id !== 'zn-balance-display' && el.id !== 'znx-balance-display' && el.id !== 'usdt-balance-display' && el.id !== 'usd-balance-display') {
                if (el.textContent.includes('ZNX') || el.id.includes('znx')) {
                    el.innerHTML = `${newZnxHTML} ZNX`;
                } else if (el.textContent.includes('ZN') || el.id.includes('zn')) {
                    el.innerHTML = `${newZnHTML} ZN`;
                } else {
                    el.innerHTML = newZnHTML;
                }
            }
        });
    }

    function applyNewBalances(zn, usdt, znx) {
        const newZn = parseFloat(zn ?? 0) || 0;
        const newUsdt = parseFloat(usdt ?? 0) || 0;
        const newZnx = parseFloat(znx ?? 0) || 0;

        // تحديث الكائنات العامة (Global State) لتستخدمها باقي الواجهات
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

        // حفظ الرصيد محلياً للتحميل الفوري المرة القادمة
        try {
            localStorage.setItem('zn_cached_balances', JSON.stringify({
                zn: newZn,
                usdt: newUsdt,
                znx: newZnx,
                ts: Date.now()
            }));
        } catch (e) {}

        // تحديث الواجهة مباشرة
        directUpdateUI(newZn, newUsdt, newZnx);

        // إطلاق الحدث ليخبر باقي النظام أن الرصيد تغير (منع التكرار اللانهائي عبر isSyncingState)
        if (!isSyncingState) {
            isSyncingState = true;
            window.dispatchEvent(new CustomEvent('userStateUpdated', {
                detail: { source: 'wallet_fetch' }
            }));
            isSyncingState = false;
        }
    }

    function renderImmediateCachedBalances() {
        // الاعتماد على Global State أولاً
        const st = window.userState || window.PlayerData || {};
        let zn = st.balance ?? st.zn_balance;
        let usdt = st.usd_balance ?? st.usdt_balance;
        let znx = st.znx_balance ?? st.total_znx_earned;

        // إذا كانت فارغة، استخدم LocalStorage
        if (zn === undefined && usdt === undefined && znx === undefined) {
            try {
                const cached = JSON.parse(localStorage.getItem('zn_cached_balances') || 'null');
                if (cached) {
                    zn = cached.zn;
                    usdt = cached.usdt;
                    znx = cached.znx;
                }
            } catch (e) {}
        }

        if (zn !== undefined || usdt !== undefined || znx !== undefined) {
            directUpdateUI(zn || 0, usdt || 0, znx || 0);
        }
    }

    function getValidUserId() {
        const tg = window.Telegram?.WebApp;
        let id = tg?.initDataUnsafe?.user?.id;

        if (!id && tg?.initData) {
            try {
                const params = new URLSearchParams(tg.initData);
                const userParam = params.get('user');
                if (userParam) {
                    const userObj = JSON.parse(decodeURIComponent(userParam));
                    id = userObj?.id;
                }
            } catch (e) {}
        }

        if (!id) {
            id = window.userState?.tg_id || window.userState?.user_id || window.userState?.telegram_id || window.userState?.id ||
                 window.PlayerData?.tg_id || window.PlayerData?.user_id || window.PlayerData?.telegram_id || window.PlayerData?.id ||
                 window.currentUserId || window.USER_ID || window.tgId;
        }

        if (!id) {
            try {
                const urlParams = new URLSearchParams(window.location.search || window.location.hash.split('?')[1] || '');
                id = urlParams.get('user_id') || urlParams.get('tg_id');
            } catch (e) {}
        }

        if (!id) {
            try {
                id = localStorage.getItem('tg_user_id') || localStorage.getItem('user_id') || localStorage.getItem('tg_id');
            } catch (e) {}
        }

        if (id && !['undefined', 'null', 'None', 'NaN', ''].includes(String(id).trim())) {
            const clean = String(id).trim().replace(/\.0$/, '');
            try { localStorage.setItem('tg_user_id', clean); } catch (e) {}
            return clean;
        }

        return null;
    }

    async function fetchWalletBalances(force = false) {
        const now = Date.now();
        // تقليل مدة الكاش إلى 500 ملي ثانية للسماح بتحديثات أسرع
        if (!force && lastFetchTime && (now - lastFetchTime < 500)) {
            return;
        }

        const userId = getValidUserId();
        const tg = window.Telegram?.WebApp;
        const initData = tg?.initData || '';

        if (!userId && !initData) {
            if (!fastRetryTimer) {
                fastRetryTimer = setTimeout(() => {
                    fastRetryTimer = null;
                    fetchWalletBalances(true);
                }, 250);
            }
            return;
        }

        lastFetchTime = now;

        try {
            const headers = { 'Content-Type': 'application/json' };
            if (userId) headers['X-Telegram-User-Id'] = userId;
            if (initData) headers['Authorization'] = `Bearer ${initData}`;

            const queryId = userId ? `user_id=${encodeURIComponent(userId)}&` : '';
            const res = await fetch(`/api/wallet/data?${queryId}t=${Date.now()}`, {
                method: 'GET',
                headers,
                cache: 'no-store'
            });

            if (!res.ok) throw new Error(`Server returned ${res.status}`);
            const data = await res.json();

            if (data && data.success) {
                applyNewBalances(data.zn_balance, data.usdt_balance, data.znx_balance);
            }
        } catch (err) {
            console.error("❌ خطأ في جلب أرصدة المحفظة:", err);
        }
    }

    function startAutoPolling() {
        if (pollInterval) clearInterval(pollInterval);
        // تحديث من السيرفر كل 2.5 ثانية (سريع وخفيف)
        pollInterval = setInterval(() => {
            fetchWalletBalances(true);
        }, 2500);
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
            script.onerror = () => resolve();
            document.head.appendChild(script);
        });
    }

    async function switchTab(tabName, force = false) {
        const container = document.getElementById('wallet-subview-container');

        if (!force && currentTab === tabName && container && container.children.length > 0 && container.getAttribute('data-active-tab') === tabName) {
            renderImmediateCachedBalances();
            fetchWalletBalances(true);
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

        renderImmediateCachedBalances();
        fetchWalletBalances(true);

        if (!container) return;
        container.setAttribute('data-active-tab', tabName);

        if (viewCache[tabName]) {
            container.innerHTML = viewCache[tabName];
            await ensureSubModuleScriptLoaded(tabName);
            if (typeof window[`init_${tabName}_module`] === 'function') window[`init_${tabName}_module`]();
            return;
        }

        try {
            const cacheBuster = `?v=${Date.now()}`;
            let response = await fetch(`/wallet/${tabName}/${tabName}.html${cacheBuster}`);
            if (!response.ok) response = await fetch(`wallet/${tabName}/${tabName}.html${cacheBuster}`);

            if (response.ok) {
                const htmlContent = await response.text();
                viewCache[tabName] = htmlContent;
                container.innerHTML = htmlContent;
                await ensureSubModuleScriptLoaded(tabName);
                if (typeof window[`init_${tabName}_module`] === 'function') window[`init_${tabName}_module`]();
            } else {
                container.innerHTML = `<div style="text-align:center; padding:20px; color:#aaa;">جاري تحميل ${tabName}...</div>`;
            }
        } catch (e) {}
    }

    function init(force = false) {
        if (!eventsBound) {
            eventsBound = true;
            
            // جلب الأرصدة عند العودة للتطبيق
            document.addEventListener('visibilitychange', () => {
                if (!document.hidden) fetchWalletBalances(true);
            });
            
            // 🎯 الاستماع لأي تحديث يحدث في أي مكان في التطبيق (المزرعة، المتجر...)
            window.addEventListener('userStateUpdated', (e) => {
                // منع حلقة مفرغة: لا نحدث إذا كان التحديث قادماً منا
                if (e && e.detail && e.detail.source === 'wallet_fetch') return;
                
                // تحديث الواجهة فوراً بما هو موجود في Global State
                if (!isSyncingState) {
                    renderImmediateCachedBalances();
                }
            });
        }

        renderImmediateCachedBalances();
        fetchWalletBalances(true);
        startAutoPolling();

        const container = document.getElementById('wallet-subview-container');
        const isSubContentPresent = container && container.children.length > 0;

        if (!force && isWalletRendered && isSubContentPresent) {
            return;
        }

        isWalletRendered = true;
        switchTab(currentTab || 'deposit', force);
    }

    return {
        init,
        switchTab,
        fetchWalletBalances,
        applyNewBalances,
        formatSmartBalance,
        formatSmartBalanceHTML
    };
})();

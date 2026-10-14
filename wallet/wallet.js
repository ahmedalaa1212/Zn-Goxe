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

    // 🎯 دالة مخصصة لإجبار الشاشة على التحديث بالأرقام الحقيقية المجلوبة من السيرفر
    function forceUpdateUIWithValues(znVal, usdtVal, znxVal) {
        const newZnHTML = formatSmartBalanceHTML(znVal);
        const newUsdtHTML = formatSmartBalanceHTML(usdtVal);
        const newZnxHTML = formatSmartBalanceHTML(znxVal);

        // تحديث مربعات المحفظة
        const znElem = document.getElementById('zn-balance-display');
        const usdtElem = document.getElementById('usdt-balance-display');
        const znxElem = document.getElementById('znx-balance-display');

        if (znElem) znElem.innerHTML = newZnHTML;
        if (usdtElem) usdtElem.innerHTML = newUsdtHTML;
        if (znxElem) znxElem.innerHTML = newZnxHTML;

        // تحديث الشاشة العلوية في كل التطبيق
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

    function applyNewBalances(zn, usdt, znx) {
        const newZn = parseFloat(zn || 0);
        const newUsdt = parseFloat(usdt || 0);
        const newZnx = parseFloat(znx || 0);

        // حفظ في الكاش لمنع الأصفار مستقبلاً
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

        // تحديث الشاشة إجبارياً
        forceUpdateUIWithValues(newZn, newUsdt, newZnx);
        window.dispatchEvent(new CustomEvent('userStateUpdated'));
    }

    // 🎯 دالة لجلب الآي دي الخاص بتليجرام بشكل سليم
    function getTelegramUserId() {
        let tg = window.Telegram?.WebApp;
        if (tg?.initDataUnsafe?.user?.id) {
            return String(tg.initDataUnsafe.user.id);
        }
        let fallbackId = window.userState?.tg_id || window.userState?.user_id || window.userState?.id || window.PlayerData?.tg_id;
        if (fallbackId && String(fallbackId) !== 'undefined') {
            return String(fallbackId);
        }
        return null;
    }

    async function fetchWalletBalances(force = false) {
        const now = Date.now();
        if (!force && lastFetchTime && (now - lastFetchTime < 1000)) {
            return;
        }
        
        let userId = getTelegramUserId();
        
        if (!userId) {
            return; // لا نرسل طلبات فارغة للسيرفر
        }

        lastFetchTime = now;

        try {
            const tg = window.Telegram?.WebApp;
            const initData = tg?.initData || '';
            const headers = { 'Content-Type': 'application/json' };
            headers['X-Telegram-User-Id'] = userId;
            if (initData) headers['Authorization'] = `Bearer ${initData}`;

            const res = await fetch(`/api/wallet/data?user_id=${userId}&t=${Date.now()}`, { 
                headers, 
                cache: 'no-store' 
            });
            
            if (!res.ok) throw new Error("Server error");
            const data = await res.json();
            
            if (data.success) {
                // تطبيق البيانات القادمة من Supabase مباشرة
                applyNewBalances(data.zn_balance, data.usdt_balance, data.znx_balance);
            }
        } catch (err) {
            console.error("Wallet Fetch Error:", err);
        }
    }

    function startAutoPolling() {
        if (pollInterval) clearInterval(pollInterval);
        pollInterval = setInterval(() => {
            fetchWalletBalances(true); // تحديث الأرصدة كل 3 ثواني بثبات
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
            script.onerror = () => resolve();
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
            if (typeof window[`init_${tabName}_module`] === 'function') window[`init_${tabName}_module`]();
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
                if (typeof window[`init_${tabName}_module`] === 'function') window[`init_${tabName}_module`]();
            } else {
                container.innerHTML = `<div style="text-align:center; padding:20px; color:#aaa;">جاري تحميل ${tabName}...</div>`;
            }
        } catch (e) {}
    }

    function init(force = false) {
        if (isListening) return;
        isListening = true;

        document.addEventListener('visibilitychange', () => {
            if (!document.hidden) fetchWalletBalances(true);
        });

        const container = document.getElementById('wallet-subview-container');
        const isSubContentPresent = container && container.children.length > 0;

        if (!force && isWalletRendered && isSubContentPresent) {
            fetchWalletBalances(true);
            return;
        }

        isWalletRendered = true;
        
        // جلب الأرصدة وبدء التحديث التلقائي
        setTimeout(() => {
            fetchWalletBalances(true);
            startAutoPolling();
        }, 300);
        
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

// wallet/wallet.js
// =================================================================
// 💳 ZN Goxe - Wallet Module Controller (Dynamic Split System)
// =================================================================

(function initWalletCore() {
    'use strict';

    window.isWalletConnected = false;
    window.userWalletAddress = null;
    window.currentWalletTab = localStorage.getItem('lastWalletTab') || 'withdraw';
    
    let tonConnectUI = null;
    let priceIntervalTimer = null;

    // 🛡️ تثبيت دالة API
    if (typeof window.apiCall !== 'function') {
        window.apiCall = async function(url, method = 'POST', payload = {}) {
            try {
                const initData = window.Telegram?.WebApp?.initData || '';
                const response = await fetch(url, {
                    method: method,
                    headers: { 
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${initData}`
                    },
                    body: JSON.stringify(payload)
                });
                return await response.json();
            } catch (err) {
                return { success: false, error: "تعذر الاتصال بالسيرفر، تأكد من اتصال الإنترنت." };
            }
        };
    }

    window.currentTonPriceUSD = parseFloat(localStorage.getItem('last_ton_price')) || 0;

    const tgApp = window.Telegram?.WebApp;
    if (tgApp) tgApp.ready();

    window.showAppAlert = function(message) {
        if (tgApp && typeof tgApp.showAlert === 'function') {
            tgApp.showAlert(message);
        } else {
            alert(message);
        }
    };

    window.triggerHapticFeedback = function(type = 'impact', style = 'medium') {
        if (tgApp && tgApp.HapticFeedback) {
            if (type === 'impact') tgApp.HapticFeedback.impactOccurred(style);
            else if (type === 'notification') tgApp.HapticFeedback.notificationOccurred(style);
        }
    };

    window.getAuthPayload = function(extraData = {}) {
        const initData = window.Telegram?.WebApp?.initData || '';
        const rawUserId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || window.GameState?.user_id || '';
        return { initData, tg_id: String(rawUserId), ...extraData };
    };

    window.getTonConnectInstance = function() {
        return tonConnectUI;
    };

    // 🧮 0. Smooth Counter Animation
    function animateValue(element, start, end, duration = 800, decimals = 2, prefix = '', suffix = '') {
        if (!element) return;
        if (isNaN(start)) start = 0;
        if (isNaN(end)) end = 0;
        
        if (Math.abs(start - end) < 0.001) {
            element.innerText = prefix + (decimals === 0 ? Math.floor(end).toLocaleString('en-US') : end.toFixed(decimals)) + suffix;
            element.dataset.currentVal = end;
            return;
        }

        let startTimestamp = null;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const current = start + (end - start) * progress;
            
            if (decimals === 0) {
                element.innerText = prefix + Math.floor(current).toLocaleString('en-US') + suffix;
            } else {
                element.innerText = prefix + current.toFixed(decimals) + suffix;
            }

            if (progress < 1) {
                window.requestAnimationFrame(step);
            } else {
                element.dataset.currentVal = end;
            }
        };
        window.requestAnimationFrame(step);
    }

    // 📡 1. جلب سعر TON اللحظي
    function applyTonPrice(price) {
        let validPrice = parseFloat(price);
        if (isNaN(validPrice) || validPrice <= 0.1 || validPrice > 200) return;

        window.currentTonPriceUSD = validPrice;
        localStorage.setItem('last_ton_price', validPrice.toString());

        const tonPriceElem = document.getElementById('current-ton-price');
        if (tonPriceElem) {
            tonPriceElem.innerText = validPrice.toFixed(2);
        }

        window.updateWalletHeaderUI();
    }

    async function fetchLiveTonPrice() {
        try {
            let res = await fetch('https://tonapi.io/v2/rates?tokens=ton&currencies=usd');
            if (res.ok) {
                let data = await res.json();
                let price = parseFloat(data?.rates?.TON?.prices?.USD);
                if (price > 0) return applyTonPrice(price);
            }
        } catch (e) {}

        try {
            let res = await fetch('https://www.okx.com/api/v5/market/ticker?instId=TON-USDT');
            if (res.ok) {
                let data = await res.json();
                let price = parseFloat(data?.data?.[0]?.last);
                if (price > 0) return applyTonPrice(price);
            }
        } catch (e) {}
    }

    function startTonPriceSync() {
        fetchLiveTonPrice();
        if (priceIntervalTimer) clearInterval(priceIntervalTimer);
        priceIntervalTimer = setInterval(fetchLiveTonPrice, 30000);
    }

    // 🔄 2. ربط ومزامنة المحفظة
    const originalUpdateGlobalUI = window.updateGlobalUI;
    window.updateGlobalUI = function() {
        if (typeof originalUpdateGlobalUI === 'function') {
            originalUpdateGlobalUI();
        }
        window.updateWalletHeaderUI();
    };

    window.updateWalletHeaderUI = function() {
        if (!window.GameState) return;

        const zn = Number(window.GameState.balance) || 0;
        const usd = Number(window.GameState.usd_balance) || 0;

        const znElem = document.getElementById('wallet-zn-balance');
        const usdElem = document.getElementById('wallet-usd-balance');
        const tonElem = document.getElementById('wallet-ton-estimate');
        const tonPriceElem = document.getElementById('current-ton-price');

        if (znElem) {
            const currentZn = parseFloat(znElem.dataset.currentVal || znElem.innerText.replace(/,/g, '')) || 0;
            animateValue(znElem, currentZn, zn, 600, 0);
        }
        
        if (usdElem) {
            const currentUsd = parseFloat(usdElem.dataset.currentVal || usdElem.innerText.replace('$', '')) || 0;
            animateValue(usdElem, currentUsd, usd, 600, 2, '$');
        }
        
        if (window.currentTonPriceUSD > 0) {
            let estimateTon = (usd / window.currentTonPriceUSD);
            if (tonElem) tonElem.innerText = "≈ " + estimateTon.toFixed(2) + " TON";
            if (tonPriceElem) tonPriceElem.innerText = window.currentTonPriceUSD.toFixed(2);
        }
    };

    // 🔗 3. تهيئة TON Connect
    function initTonConnect() {
        if (typeof window.TON_CONNECT_UI === 'undefined') {
            setTimeout(initTonConnect, 150);
            return;
        }

        if (!tonConnectUI) {
            const themeDark = window.TON_CONNECT_UI.THEME ? window.TON_CONNECT_UI.THEME.DARK : 'DARK';

            tonConnectUI = new window.TON_CONNECT_UI.TonConnectUI({
                manifestUrl: 'https://zn-goxe-production.up.railway.app/tonconnect-manifest.json',
                buttonRootId: 'hidden-ton-root',
                uiPreferences: {
                    theme: themeDark,
                    colorsSet: {
                        [themeDark]: {
                            connectButton: { background: '#0098ea', foreground: '#ffffff' },
                            accent: '#0098ea',
                            iconOnAccent: '#ffffff',
                            background: { primary: '#0a0d14', secondary: '#161c27', qr: '#ffffff', tint: '#1e293b' },
                            text: { primary: '#ffffff', secondary: '#94a3b8' }
                        }
                    }
                }
            });

            tonConnectUI.connectionRestored.then(restored => {
                if (restored && tonConnectUI.wallet) {
                    window.isWalletConnected = true;
                    window.userWalletAddress = window.TON_CONNECT_UI.toUserFriendlyAddress(tonConnectUI.wallet.account.address);
                    window.renderWalletTab(window.currentWalletTab); 
                }
            });

            tonConnectUI.onStatusChange(wallet => {
                if (wallet && wallet.account) {
                    window.isWalletConnected = true;
                    window.userWalletAddress = window.TON_CONNECT_UI.toUserFriendlyAddress(wallet.account.address);
                    window.triggerHapticFeedback('notification', 'success');
                } else {
                    window.isWalletConnected = false;
                    window.userWalletAddress = null;
                }
                window.renderWalletTab(window.currentWalletTab);
            });
        }
    }

    window.connectCustomWallet = async function() {
        window.triggerHapticFeedback('impact', 'light');
        try {
            if (!tonConnectUI) initTonConnect();
            await tonConnectUI.openModal();
        } catch (e) {
            console.log("تم إلغاء عملية الاتصال");
        }
    };

    window.disconnectCustomWallet = async function() {
        window.triggerHapticFeedback('impact', 'medium');
        if (tonConnectUI) {
            try { 
                await tonConnectUI.disconnect(); 
                window.showAppAlert("تم إلغاء ربط المحفظة بنجاح.");
            } catch (e) {}
        }
    };

    // 🖼️ 4. محول التبويبات والمحمل الديناميكي للملفات
    window.renderWalletTab = async function(tab) {
        window.currentWalletTab = tab;
        localStorage.setItem('lastWalletTab', tab);

        const content = document.getElementById('wallet-content');
        if (!content) return;
        
        ['withdraw', 'history', 'deposit'].forEach(t => {
            const btn = document.getElementById(`btn-${t}`);
            if (btn) btn.classList.toggle('active', t === tab);
        });

        try {
            const response = await fetch(`${tab}/${tab}.html`);
            if (response.ok) {
                content.innerHTML = await response.text();
            }
        } catch (e) {
            console.error("فشل تحميل قالب التبويب:", e);
        }

        if (tab === 'deposit') {
            window.renderDepositUI?.();
        } else if (tab === 'withdraw') {
            window.renderWithdrawUI?.();
        } else if (tab === 'history') {
            window.loadHistoryData?.();
        }

        window.updateWalletHeaderUI();
    };

    // 🚀 5. البدء
    startTonPriceSync();
    
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        window.renderWalletTab(window.currentWalletTab);
    } else {
        document.addEventListener('DOMContentLoaded', () => window.renderWalletTab(window.currentWalletTab));
    }

    initTonConnect();
})();


// games/games-core.js
(function initGamesCoreModule() {
    window.tele = window.Telegram?.WebApp;
    window.currentDisplayBalance = 0;

    // استخراج ID المستخدم بجميع الطرق الممكنة لمنع حدوث 0.00
    window.getTgId = function() {
        let id = window.tele?.initDataUnsafe?.user?.id;
        if (id) {
            localStorage.setItem('tg_id', id.toString());
            return id.toString();
        }

        const urlParams = new URLSearchParams(window.location.search);
        const urlId = urlParams.get('tg_id') || urlParams.get('uid') || urlParams.get('user_id');
        if (urlId) {
            localStorage.setItem('tg_id', urlId.toString());
            return urlId.toString();
        }

        if (window.userState && window.userState.tg_id) {
            return window.userState.tg_id.toString();
        }

        return localStorage.getItem('tg_id') || null;
    };

    window.triggerHaptic = function(type = 'light') {
        try {
            if (window.tele?.HapticFeedback) {
                if (type === 'light') window.tele.HapticFeedback.impactOccurred('light');
                else if (type === 'medium') window.tele.HapticFeedback.impactOccurred('medium');
                else if (type === 'heavy') window.tele.HapticFeedback.impactOccurred('heavy');
                else if (type === 'success') window.tele.HapticFeedback.notificationOccurred('success');
                else if (type === 'error') window.tele.HapticFeedback.notificationOccurred('error');
            }
        } catch (e) {}
    };

    window.formatNumberHTML = function(val, suffix = "") {
        const num = parseFloat(val) || 0;
        const parts = num.toFixed(2).split('.');
        const intPart = parseInt(parts[0], 10).toLocaleString('en-US');
        const decPart = parts[1];
        return `${intPart}<span class="small-decimal" style="font-size:0.8em; opacity:0.85;">.${decPart}</span>${suffix}`;
    };

    window.animateCounter = function(elementId, startVal, endVal, duration = 800, suffix = " ZN") {
        const el = document.getElementById(elementId);
        if (!el) return;
        let startTimestamp = null;
        const startNum = parseFloat(startVal) || 0;
        const endNum = parseFloat(endVal) || 0;

        if (startNum === endNum) {
            el.innerHTML = window.formatNumberHTML(endNum, suffix);
            return;
        }

        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const easeProgress = 1 - Math.pow(1 - progress, 3);
            const currentVal = startNum + (endNum - startNum) * easeProgress;
            el.innerHTML = window.formatNumberHTML(currentVal, suffix);
            if (progress < 1) window.requestAnimationFrame(step);
            else el.innerHTML = window.formatNumberHTML(endNum, suffix);
        };
        window.requestAnimationFrame(step);
    };

    window.showNotification = function(msg) {
        window.triggerHaptic('medium');
        if (window.tele && window.tele.showAlert) window.tele.showAlert(msg);
        else alert(msg);
    };

    window.triggerGlobalToast = function(msg, isSuccess = true) {
        let toastBox = document.getElementById('global-toast-notification');
        if (!toastBox) {
            toastBox = document.createElement('div');
            toastBox.id = 'global-toast-notification';
            toastBox.style.cssText = `
                position: fixed; top: 18px; left: 50%; transform: translateX(-50%);
                background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(12px);
                color: #ffffff; padding: 12px 22px; border-radius: 50px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.8); z-index: 99999999;
                font-size: 13px; font-weight: 800; text-align: center; width: 90%; max-width: 380px;
                transition: border-color 0.3s ease;
            `;
            document.body.appendChild(toastBox);
        }
        toastBox.style.border = `1.5px solid ${isSuccess ? '#10b981' : '#ef4444'}`;
        toastBox.innerHTML = msg;
        toastBox.style.display = 'block';
        setTimeout(() => { if (toastBox) toastBox.style.display = 'none'; }, 4000);
    };

    window.getStoredBalance = function() {
        if (window.userState && window.userState.balance !== undefined && !isNaN(window.userState.balance)) {
            return parseFloat(window.userState.balance);
        }
        try {
            const savedState = localStorage.getItem('app_user_state');
            if (savedState) {
                const parsed = JSON.parse(savedState);
                if (parsed.balance !== undefined) return parseFloat(parsed.balance) || 0;
            }
        } catch (e) {}
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        const num = bal !== null ? parseFloat(bal) : 0;
        return isNaN(num) ? 0 : num;
    };

    window.setStoredBalance = function(newBalance, animate = true) {
        if (newBalance !== undefined && newBalance !== null) {
            const numVal = Math.round((parseFloat(newBalance) || 0) * 100) / 100;
            const oldVal = window.currentDisplayBalance || window.getStoredBalance();
            
            if (window.userState) {
                window.userState.balance = numVal;
            } else {
                localStorage.setItem('zn_balance', numVal.toString());
            }

            window.currentDisplayBalance = numVal;

            const targetElements = ['top-balance-games'];
            targetElements.forEach(id => {
                const gameBalEl = document.getElementById(id);
                if (gameBalEl) {
                    if (animate) window.animateCounter(id, oldVal, numVal, 800, " ZN");
                    else gameBalEl.innerHTML = window.formatNumberHTML(numVal, " ZN");
                }
            });
        }
    };

    window.syncUserData = async function() {
        const tgId = window.getTgId();
        if (!tgId) return;

        try {
            const initData = window.tele?.initData || "";
            const res = await fetch(`/api/user/info?tg_id=${tgId}`, {
                headers: {
                    'X-Telegram-Init-Data': initData,
                    'Authorization': `Bearer ${initData}`
                }
            });
            if (!res.ok) return;
            const data = await res.json();
            if (data.success) {
                const balanceVal = data.balance !== undefined ? data.balance : data.user?.balance;
                if (balanceVal !== undefined) {
                    window.setStoredBalance(balanceVal, true);
                }
            }
        } catch (e) {
            console.error("Error syncing user profile:", e);
        }
    };

    window.switchGameTab = function(tabName) {
        window.triggerHaptic('light');
        const arenaTab = document.getElementById('tab-arena');
        const boxesTab = document.getElementById('tab-boxes');
        const arenaContent = document.getElementById('content-arena');
        const boxesContent = document.getElementById('content-boxes');

        if (tabName === 'arena') {
            if (arenaTab) { arenaTab.classList.add('active'); arenaTab.style.opacity = '1'; }
            if (boxesTab) { boxesTab.classList.remove('active'); boxesTab.style.opacity = '0.6'; }
            if (arenaContent) arenaContent.style.display = 'block';
            if (boxesContent) boxesContent.style.display = 'none';
            if (typeof window.fetchArenaStatus === 'function') window.fetchArenaStatus(true);
        } else {
            if (boxesTab) { boxesTab.classList.add('active'); boxesTab.style.opacity = '1'; }
            if (arenaTab) { arenaTab.classList.remove('active'); arenaTab.style.opacity = '0.6'; }
            if (arenaContent) arenaContent.style.display = 'none';
            if (boxesContent) boxesContent.style.display = 'block';
            if (typeof window.renderBoxesGrid === 'function') window.renderBoxesGrid();
        }
    };

    // الاستماع للتغييرات العامة للرصيد
    window.addEventListener('userStateUpdated', (e) => {
        if (e.detail && e.detail.balance !== undefined) {
            const newBal = parseFloat(e.detail.balance) || 0;
            const inBoxesGame = window.boxesState && window.boxesState.inGame;
            if (newBal !== window.currentDisplayBalance && !inBoxesGame) {
                window.currentDisplayBalance = newBal;
                const gameBalEl = document.getElementById('top-balance-games');
                if (gameBalEl) gameBalEl.innerHTML = window.formatNumberHTML(newBal, " ZN");
            }
        }
    });

    function initCore() {
        if (window.tele) {
            try {
                window.tele.ready();
                window.tele.expand();
            } catch (e) {}
        }
        window.syncUserData();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCore);
    } else {
        initCore();
    }
})();

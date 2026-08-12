// games/games-core.js
(function initGamesCoreModule() {
    window.tele = window.Telegram?.WebApp;
    window.currentDisplayBalance = 0;
    window.activeAnimationFrames = window.activeAnimationFrames || {};
    window.isTransactionPending = false;

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
        const num = Math.round((parseFloat(val) || 0) * 100) / 100;
        const parts = num.toFixed(2).split('.');
        const intPart = parseInt(parts[0], 10).toLocaleString('en-US');
        const decPart = parts[1];
        return `${intPart}<span class="small-decimal" style="font-size:0.8em; opacity:0.85;">.${decPart}</span>${suffix}`;
    };

    window.animateCounter = function(elementId, startVal, endVal, duration = 800, suffix = " ZN") {
        const el = document.getElementById(elementId);
        if (!el) return;

        const startNum = Math.round((parseFloat(startVal) || 0) * 100) / 100;
        const endNum = Math.round((parseFloat(endVal) || 0) * 100) / 100;

        if (window.activeAnimationFrames[elementId]) {
            cancelAnimationFrame(window.activeAnimationFrames[elementId]);
            delete window.activeAnimationFrames[elementId];
        }

        if (Math.abs(startNum - endNum) < 0.01) {
            el.innerHTML = window.formatNumberHTML(endNum, suffix);
            return;
        }

        let startTimestamp = null;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const easeProgress = 1 - Math.pow(1 - progress, 3);
            const currentVal = startNum + (endNum - startNum) * easeProgress;

            el.innerHTML = window.formatNumberHTML(currentVal, suffix);

            if (progress < 1) {
                window.activeAnimationFrames[elementId] = window.requestAnimationFrame(step);
            } else {
                el.innerHTML = window.formatNumberHTML(endNum, suffix);
                delete window.activeAnimationFrames[elementId];
            }
        };

        window.activeAnimationFrames[elementId] = window.requestAnimationFrame(step);
    };

    window.showNotification = function(msg) {
        window.triggerHaptic('medium');
        if (window.tele && window.tele.showAlert) window.tele.showAlert(msg);
        else alert(msg);
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
        if (newBalance === undefined || newBalance === null) return;

        const numVal = Math.round((parseFloat(newBalance) || 0) * 100) / 100;
        const oldVal = window.currentDisplayBalance || window.getStoredBalance();

        if (window.userState) {
            window.userState.balance = numVal;
            window.userState.zn_balance = numVal;
        }
        localStorage.setItem('zn_balance', numVal.toString());
        localStorage.setItem('user_balance', numVal.toString());

        window.currentDisplayBalance = numVal;

        // 🌟 تحديث شامل ومستهدف لجميع الهيدرات والعناصر في الواجهة العلوي
        const targetIds = [
            'top-balance-games', 'top-balance', 'user-balance', 'zn-balance', 
            'header-balance', 'main-balance', 'nav-balance', 'header-user-balance',
            'top-bar-balance', 'app-balance', 'user-coins', 'top-coins'
        ];
        
        targetIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                if (animate) window.animateCounter(id, oldVal, numVal, 800, " ZN");
                else el.innerHTML = window.formatNumberHTML(numVal, " ZN");
            }
        });

        document.querySelectorAll('.user-balance-value, .balance-amount, .user-balance-amount, .header-balance-value, .top-balance-text, .zn-balance-display, [data-balance]').forEach(el => {
            el.innerHTML = window.formatNumberHTML(numVal, " ZN");
        });

        try {
            window.dispatchEvent(new CustomEvent('balanceUpdated', { detail: { balance: numVal } }));
            window.dispatchEvent(new CustomEvent('userBalanceChanged', { detail: { balance: numVal } }));
        } catch(e) {}
    };

    window.syncUserData = async function() {
        if (window.isTransactionPending) return;

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
                const balanceVal = data.balance !== undefined ? data.balance : data.user_balance;
                if (balanceVal !== undefined && !window.isTransactionPending) {
                    window.setStoredBalance(balanceVal, true);
                }
                if (data.refund_amount && data.refund_amount > 0) {
                    window.showNotification(`💰 تم استرجاع ${data.refund_amount} ZN إلى حسابك لعدم اكتمال عدد المشاركين!`);
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

    window.addEventListener('userStateUpdated', (e) => {
        if (e.detail && e.detail.balance !== undefined) {
            const newBal = Math.round((parseFloat(e.detail.balance) || 0) * 100) / 100;
            const inBoxesGame = window.boxesState && window.boxesState.inGame;
            if (newBal !== window.currentDisplayBalance && !inBoxesGame && !window.isTransactionPending) {
                window.setStoredBalance(newBal, false);
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

        const initialBal = window.getStoredBalance();
        window.setStoredBalance(initialBal, false);

        window.syncUserData();

        setInterval(() => {
            if (!window.isTransactionPending && (!window.boxesState || !window.boxesState.inGame)) {
                window.syncUserData();
            }
        }, 4000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initCore);
    } else {
        initCore();
    }
})();

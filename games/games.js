// games/games.js
(function initGamesModule() {
    // --- متغيرات الساحة الكبرى ---
    let isJoining = false;
    let currentRoundId = null;
    let arenaEndTime = 0;
    let countdownInterval = null;
    let backgroundSyncInterval = null;
    let hasCheckedResults = false;
    let statusRetryTimeout = null;
    let pendingConfirmCallback = null;

    let lastStatusFetchTimestamp = 0;
    const STATUS_FETCH_COOLDOWN = 12000;
    let hasJoinedCurrentRound = false;

    let currentEntryFee = 250;
    let currentLockSeconds = 15;
    let currentDisplayBalance = 0;
    let currentPrizePool = 0;

    // --- متغيرات لعبة 36 صندوقاً (شبكة العملات والمخاطرة) ---
    const MULTIPLIERS_BASE_3 = [
        1.01, 1.03, 1.06, 1.10, 1.15, 1.21, 1.28, 1.36, 1.45, 1.55,
        1.67, 1.81, 1.97, 2.15, 2.36, 2.60, 2.88, 3.20, 3.58, 4.02,
        4.54, 5.14, 5.84, 6.66, 7.62, 8.75, 10.08, 11.65, 13.50, 15.65,
        17.00, 18.40, 20.00
    ];

    let minesState = {
        active: false,
        bet: 100,
        bombsCount: 3,
        currentStep: 0,
        sessionToken: null,
        openedBoxes: new Set(),
        lastClickTime: 0,
        multipliers: [...MULTIPLIERS_BASE_3]
    };

    const tele = window.Telegram?.WebApp;

    function triggerHaptic(type = 'light') {
        try {
            if (tele?.HapticFeedback) {
                if (type === 'light') tele.HapticFeedback.impactOccurred('light');
                else if (type === 'medium') tele.HapticFeedback.impactOccurred('medium');
                else if (type === 'heavy') tele.HapticFeedback.impactOccurred('heavy');
                else if (type === 'success') tele.HapticFeedback.notificationOccurred('success');
                else if (type === 'error') tele.HapticFeedback.notificationOccurred('error');
            }
        } catch (e) {}
    }

    function formatNumberHTML(val, suffix = "") {
        const num = parseFloat(val) || 0;
        const parts = num.toFixed(2).split('.');
        const intPart = parseInt(parts[0], 10).toLocaleString('en-US');
        const decPart = parts[1];
        return `${intPart}<span class="small-decimal" style="font-size:0.8em; opacity:0.85;">.${decPart}</span>${suffix}`;
    }

    function animateCounter(elementId, startVal, endVal, duration = 800, suffix = " ZN") {
        const el = document.getElementById(elementId);
        if (!el) return;
        let startTimestamp = null;
        const startNum = parseFloat(startVal) || 0;
        const endNum = parseFloat(endVal) || 0;

        if (startNum === endNum) {
            el.innerHTML = formatNumberHTML(endNum, suffix);
            return;
        }

        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const easeProgress = 1 - Math.pow(1 - progress, 3);
            const currentVal = startNum + (endNum - startNum) * easeProgress;
            el.innerHTML = formatNumberHTML(currentVal, suffix);
            if (progress < 1) window.requestAnimationFrame(step);
            else el.innerHTML = formatNumberHTML(endNum, suffix);
        };
        window.requestAnimationFrame(step);
    }

    function showNotification(msg) {
        triggerHaptic('medium');
        if (tele && tele.showAlert) tele.showAlert(msg);
        else alert(msg);
    }

    function getStoredBalance() {
        if (window.userState && window.userState.balance !== undefined) return parseFloat(window.userState.balance) || 0;
        if (window.PlayerData && window.PlayerData.balance !== undefined) return parseFloat(window.PlayerData.balance) || 0;
        if (window.GameState && window.GameState.balance !== undefined) return parseFloat(window.GameState.balance) || 0;
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        const num = bal !== null ? parseFloat(bal) : 0;
        return isNaN(num) ? 0 : num;
    }

    function setStoredBalance(newBalance, animate = true) {
        if (newBalance !== undefined && newBalance !== null) {
            const numVal = Math.round((parseFloat(newBalance) || 0) * 100) / 100;
            const oldVal = currentDisplayBalance || getStoredBalance();
            
            if (window.userState) window.userState.balance = numVal;
            if (window.PlayerData) window.PlayerData.balance = numVal;
            if (window.GameState) window.GameState.balance = numVal;
            
            localStorage.setItem('zn_balance', numVal.toString());
            localStorage.setItem('user_balance', numVal.toString());
            
            if (animate) animateCounter('top-balance-games', oldVal, numVal, 800, " ZN");
            else {
                const gameBalEl = document.getElementById('top-balance-games');
                if (gameBalEl) gameBalEl.innerHTML = formatNumberHTML(numVal, " ZN");
            }
            currentDisplayBalance = numVal;

            if (typeof window.setBalance === 'function') window.setBalance(numVal);
            const mainBalEl = document.getElementById('user-balance') || document.querySelector('.user-balance');
            if (mainBalEl) mainBalEl.innerHTML = formatNumberHTML(numVal, " ZN");
        }
    }

    function syncGameBalance() {
        const stored = getStoredBalance();
        const oldVal = currentDisplayBalance;
        setStoredBalance(stored, oldVal !== stored && oldVal !== 0);
    }

    window.switchGameTab = function(tabName) {
        triggerHaptic('light');
        const arenaTab = document.getElementById('tab-arena');
        const minesTab = document.getElementById('tab-mines');
        const arenaContent = document.getElementById('content-arena');
        const minesContent = document.getElementById('content-mines');

        if (tabName === 'arena') {
            if (arenaTab) { arenaTab.classList.add('active'); arenaTab.style.opacity = '1'; }
            if (minesTab) { minesTab.classList.remove('active'); minesTab.style.opacity = '0.6'; }
            if (arenaContent) arenaContent.style.display = 'block';
            if (minesContent) minesContent.style.display = 'none';
        } else {
            if (minesTab) { minesTab.classList.add('active'); minesTab.style.opacity = '1'; }
            if (arenaTab) { arenaTab.classList.remove('active'); arenaTab.style.opacity = '0.6'; }
            if (arenaContent) arenaContent.style.display = 'none';
            if (minesContent) minesContent.style.display = 'block';
            renderMinesGrid();
        }
    };

    // --- محرك لعبة 36 صندوقاً ---
    function buildMultipliers(bombs) {
        if (bombs === 3) return [...MULTIPLIERS_BASE_3];
        const totalSafe = 36 - bombs;
        const maxCap = 20.0 + (bombs - 3) * 10.0;
        let list = [];
        for (let i = 1; i <= totalSafe; i++) {
            let ratio = i / totalSafe;
            let mult = 1.0 + (maxCap - 1.0) * Math.pow(ratio, 2.2);
            list.push(parseFloat(mult.toFixed(2)));
        }
        return list;
    }

    function renderMinesGrid() {
        const grid = document.getElementById('mines-grid');
        if (!grid) return;
        grid.innerHTML = '';
        for (let i = 0; i < 36; i++) {
            const box = document.createElement('div');
            box.className = 'mine-box';
            box.dataset.index = i;
            box.innerText = '❓';
            box.onclick = () => onBoxClick(i);
            grid.appendChild(box);
        }
    }

    window.openMinesSettings = () => {
        triggerHaptic('light');
        if (minesState.active) return showNotification("لا يمكن تغيير الإعدادات أثناء الجولة الحالية!");
        document.getElementById('mines-settings-modal').style.display = 'flex';
    };

    window.closeMinesSettings = () => {
        triggerHaptic('light');
        document.getElementById('mines-settings-modal').style.display = 'none';
    };

    window.selectMinesCount = (count) => {
        triggerHaptic('medium');
        minesState.bombsCount = count;
        minesState.multipliers = buildMultipliers(count);
        document.getElementById('mines-count-label').innerText = `${count} قنابل`;
        closeMinesSettings();
    };

    window.addBet = (amt) => {
        if (minesState.active) return;
        triggerHaptic('light');
        const input = document.getElementById('mines-bet-input');
        let val = (parseFloat(input.value) || 0) + amt;
        input.value = val;
        updateMinesActionButton();
    };

    window.setBetMax = () => {
        if (minesState.active) return;
        triggerHaptic('medium');
        const input = document.getElementById('mines-bet-input');
        input.value = Math.floor(getStoredBalance());
        updateMinesActionButton();
    };

    function updateMinesActionButton() {
        const btn = document.getElementById('btn-mines-action');
        if (!btn) return;
        if (!minesState.active) {
            const betInput = parseFloat(document.getElementById('mines-bet-input').value) || 100;
            btn.style.background = "linear-gradient(90deg, #f39c12, #d35400)";
            btn.style.boxShadow = "0 6px 20px var(--primary-glow)";
            btn.innerText = `بدء الرهان (${betInput.toLocaleString('en-US')} ZN) 🚀`;
        } else {
            const currentMult = minesState.currentStep > 0 ? minesState.multipliers[minesState.currentStep - 1] : 1.0;
            const cashOutVal = Math.round(minesState.bet * currentMult * 100) / 100;
            btn.style.background = "linear-gradient(90deg, #10b981, #059669)";
            btn.style.boxShadow = "0 6px 20px var(--accent-green-glow)";
            btn.innerText = `سحب الأرباح (${cashOutVal.toLocaleString('en-US')} ZN) 💰`;
        }
    }

    window.handleMinesAction = () => {
        triggerHaptic('heavy');
        if (!minesState.active) startMinesRound();
        else cashOutMinesRound();
    };

    async function startMinesRound() {
        const betVal = parseFloat(document.getElementById('mines-bet-input').value) || 0;
        if (betVal < 100) return showNotification("الحد الأدنى للرهان هو 100 ZN.");
        if (getStoredBalance() < betVal) return showNotification("رصيدك غير كافٍ للرهان.");

        const btn = document.getElementById('btn-mines-action');
        btn.disabled = true;
        btn.innerText = "جاري بدء الجولة... ⏳";

        try {
            const initData = tele?.initData || "";
            const res = await fetch('/api/games/mines/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({ initData: initData, bet: betVal, bombs_count: minesState.bombsCount })
            });

            const data = await res.json();
            if (data.success) {
                triggerHaptic('success');
                minesState.active = true;
                minesState.bet = betVal;
                minesState.sessionToken = data.session_token;
                minesState.currentStep = 0;
                minesState.openedBoxes.clear();
                
                setStoredBalance(data.new_balance, true);
                renderMinesGrid();
                document.getElementById('mines-multiplier-val').innerText = '1.00x';
                updateMinesActionButton();
            } else {
                triggerHaptic('error');
                showNotification("⚠️ " + (data.message || "تعذر بدء الجولة"));
                updateMinesActionButton();
            }
        } catch (e) {
            triggerHaptic('error');
            showNotification("خطأ في الاتصال بالخادم.");
            updateMinesActionButton();
        } finally {
            btn.disabled = false;
        }
    }

    function onBoxClick(boxIndex) {
        if (!minesState.active) return;
        const now = Date.now();
        if (now - minesState.lastClickTime < 350) return;
        if (minesState.openedBoxes.has(boxIndex)) return;

        minesState.lastClickTime = now;
        minesState.openedBoxes.add(boxIndex);

        triggerHaptic('light');
        const boxEl = document.querySelector(`.mine-box[data-index="${boxIndex}"]`);
        
        minesState.currentStep++;
        const currentMult = minesState.multipliers[minesState.currentStep - 1] || 1.0;

        boxEl.classList.add('revealed-safe');
        boxEl.innerText = '💎';
        document.getElementById('mines-multiplier-val').innerText = `${currentMult.toFixed(2)}x`;
        updateMinesActionButton();
    }

    async function cashOutMinesRound() {
        if (!minesState.active || minesState.currentStep === 0) return;

        const btn = document.getElementById('btn-mines-action');
        btn.disabled = true;
        btn.innerText = "جاري سحب الأرباح... 💰";

        try {
            const initData = tele?.initData || "";
            const res = await fetch('/api/games/mines/end', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({
                    initData: initData,
                    session_token: minesState.sessionToken,
                    step: minesState.currentStep,
                    opened_boxes: Array.from(minesState.openedBoxes),
                    action: 'cashout'
                })
            });

            const data = await res.json();
            if (data.success) {
                triggerHaptic('success');
                setStoredBalance(data.new_balance, true);
                triggerGlobalToast(`🎉 مبروك! كسبت ${data.payout.toLocaleString('en-US')} ZN (مضاعف ${data.multiplier}x)`, true);
                revealAllBombs(data.bomb_positions, data.opened_boxes);
            } else if (data.status === 'exploded') {
                handleBombExplosion(data);
            } else {
                triggerHaptic('error');
                showNotification(data.message || "حدث خطأ أثناء السحب.");
            }
        } catch (e) {
            triggerHaptic('error');
            showNotification("خطأ في شبكة الاتصال.");
        } finally {
            minesState.active = false;
            btn.disabled = false;
            updateMinesActionButton();
        }
    }

    function handleBombExplosion(data) {
        triggerHaptic('error');
        minesState.active = false;
        revealAllBombs(data.bomb_positions, Array.from(minesState.openedBoxes));
        
        triggerGlobalToast("💣 للأسف اصطدمت بعملة مكسورة!", false);
        updateMinesActionButton();
    }

    function revealAllBombs(bombPositions = [], openedBoxes = []) {
        const gridBoxes = document.querySelectorAll('.mine-box');
        gridBoxes.forEach((box, idx) => {
            if (bombPositions.includes(idx)) {
                box.classList.add('revealed-bomb');
                box.innerText = '💣';
            } else if (!openedBoxes.includes(idx)) {
                box.style.opacity = '0.4';
                box.innerText = '🪙';
            }
        });
    }

    // --- منطق الساحة الكبرى والتحديثات الخلفية ---
    async function fetchArenaStatus(force = false) {
        if (statusRetryTimeout) { clearTimeout(statusRetryTimeout); statusRetryTimeout = null; }
        const now = Date.now();
        if (!force && (now - lastStatusFetchTimestamp < STATUS_FETCH_COOLDOWN)) return;
        lastStatusFetchTimestamp = now;

        try {
            const initData = tele?.initData || "";
            const response = await fetch('/api/games/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({ initData: initData })
            });
            if (!response.ok) throw new Error("Server Error");
            const data = await response.json();
            if (data.success) {
                if (data.entry_fee) currentEntryFee = data.entry_fee;
                if (data.lock_seconds) currentLockSeconds = data.lock_seconds;
                const subtext = document.getElementById('arena-subtext');
                if (subtext) subtext.innerText = `سحب تلقائي مستمر! رسوم الاشتراك: ${parseInt(currentEntryFee, 10).toLocaleString('en-US')} ZN`;
                if (data.balance !== undefined) setStoredBalance(data.balance, true);
                currentRoundId = data.round_id;
                arenaEndTime = parseInt(data.end_time) || 0;
                hasCheckedResults = false;
                hasJoinedCurrentRound = !!data.has_joined;
                updateArenaPrizes(data);
                startSmoothCountdown();
            }
        } catch (error) {
            statusRetryTimeout = setTimeout(() => fetchArenaStatus(true), 6000);
        }
    }

    function updateArenaPrizes(data) {
        const newPool = parseFloat(data.prize_pool) || 0;
        animateCounter('prize-pool', currentPrizePool, newPool, 900, " ZN");
        currentPrizePool = newPool;
        const p1 = document.getElementById('prize-1');
        const p2 = document.getElementById('prize-2');
        const p3 = document.getElementById('prize-3');
        const p4 = document.getElementById('prize-4');
        const p5 = document.getElementById('prize-5');

        if (p1) p1.innerHTML = formatNumberHTML(newPool * 0.30, " ZN");
        if (p2) p2.innerHTML = formatNumberHTML(newPool * 0.25, " ZN");
        if (p3) p3.innerHTML = formatNumberHTML(newPool * 0.20, " ZN");
        if (p4) p4.innerHTML = formatNumberHTML(newPool * 0.15, " ZN");
        if (p5) p5.innerHTML = formatNumberHTML(newPool * 0.10, " ZN");
    }

    function startSmoothCountdown() {
        if (countdownInterval) clearInterval(countdownInterval);
        timerTick();
        countdownInterval = setInterval(() => timerTick(), 1000);
    }

    function timerTick() {
        if (!arenaEndTime || arenaEndTime <= 0) return;
        const now = Math.floor(Date.now() / 1000);
        let timeLeft = arenaEndTime - now;
        const btn = document.getElementById('btn-join-arena');
        const timerEl = document.getElementById('arena-timer');
        if (timeLeft < 0) timeLeft = 0;

        if (timerEl) {
            let m = Math.floor(timeLeft / 60);
            let s = timeLeft % 60;
            timerEl.innerText = `${m < 10 ? '0'+m : m}:${s < 10 ? '0'+s : s}`;
        }

        if (!btn) return;

        if (timeLeft <= currentLockSeconds && timeLeft > 0) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerText = "🔒 تم إغلاق الاشتراك (جاري السحب⏳)";
        } else if (timeLeft === 0) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerText = "🔄 جاري إعلان النتائج...";
            if (!hasCheckedResults && currentRoundId) {
                hasCheckedResults = true;
                fetchRoundResults(currentRoundId, 0);
            }
        } else {
            if (!hasJoinedCurrentRound) {
                btn.disabled = false;
                btn.classList.remove('btn-disabled');
                btn.innerText = `⚔️ دخول الساحة (${parseInt(currentEntryFee, 10).toLocaleString('en-US')} ZN)`;
            } else {
                btn.disabled = true;
                btn.classList.add('btn-disabled');
                btn.innerText = "أنت مشترك بالفعل ✅";
            }
        }
    }

    window.joinArena = function() {
        triggerHaptic('heavy');
        if (isJoining || hasJoinedCurrentRound) return;
        if (getStoredBalance() < currentEntryFee) {
            showNotification(`⚠️ رصيدك غير كافٍ للدخول في الساحة.`);
            return;
        }
        askForConfirmation(() => executeJoinArena());
    };

    async function executeJoinArena() {
        if (isJoining) return;
        isJoining = true;
        const btn = document.getElementById('btn-join-arena');
        if (btn) { btn.disabled = true; btn.innerText = "جاري الدخول... ⏳"; }

        try {
            const initData = tele?.initData || "";
            const response = await fetch('/api/games/join', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({ initData: initData })
            });
            const data = await response.json();
            if (data.success) {
                triggerHaptic('success');
                hasJoinedCurrentRound = true;
                if (data.new_balance !== undefined) setStoredBalance(data.new_balance, true);
                if (data.prize_pool !== undefined) updateArenaPrizes(data);
                if (btn) { btn.disabled = true; btn.classList.add('btn-disabled'); btn.innerText = "أنت مشترك بالفعل ✅"; }
                showNotification("🎉 تم دخول الساحة بنجاح!");
            } else {
                triggerHaptic('error');
                showNotification("⚠️ " + (data.message || "تعذر الاشتراك"));
            }
        } catch (error) {
            triggerHaptic('error');
            showNotification("حدث خطأ في الاتصال بالخادم.");
        } finally {
            isJoining = false;
        }
    }

    function triggerGlobalToast(msg, isSuccess = true) {
        let toastBox = document.getElementById('global-toast-notification');
        if (!toastBox) {
            toastBox = document.createElement('div');
            toastBox.id = 'global-toast-notification';
            toastBox.style.cssText = `
                position: fixed; top: 18px; left: 50%; transform: translateX(-50%);
                background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(12px);
                border: 1.5px solid ${isSuccess ? '#10b981' : '#ef4444'};
                color: #ffffff; padding: 12px 22px; border-radius: 50px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.8); z-index: 99999999;
                font-size: 13px; font-weight: 800; text-align: center; width: 90%; max-width: 380px;
                display: flex; align-items: center; justify-content: center; gap: 8px;
            `;
            document.body.appendChild(toastBox);
        }
        toastBox.innerHTML = msg;
        toastBox.style.display = 'flex';
        setTimeout(() => { if (toastBox) toastBox.style.display = 'none'; }, 4500);
    }

    function askForConfirmation(onConfirm) {
        const modal = document.getElementById('confirm-modal');
        const feeText = document.getElementById('confirm-fee-text');
        if (feeText) feeText.innerHTML = formatNumberHTML(currentEntryFee, " ZN");
        if (modal) { pendingConfirmCallback = onConfirm; modal.style.display = 'flex'; }
    }

    window.onConfirmJoin = function(confirmed) {
        triggerHaptic('light');
        const modal = document.getElementById('confirm-modal');
        if (modal) modal.style.display = 'none';
        if (confirmed && typeof pendingConfirmCallback === 'function') pendingConfirmCallback();
        pendingConfirmCallback = null;
    };

    function showDrawModal(state, refundFee = 0) {
        const modal = document.getElementById('draw-modal');
        const refundedEl = document.getElementById('draw-refunded');
        const winnersEl = document.getElementById('draw-winners');
        const refundAmountEl = document.getElementById('refund-amount-display');
        if (refundedEl) refundedEl.style.display = 'none';
        if (winnersEl) winnersEl.style.display = 'none';
        if (state === 'refunded' && refundedEl) {
            refundedEl.style.display = 'block';
            if (refundAmountEl) refundAmountEl.innerHTML = `+${formatNumberHTML(refundFee, " ZN")}`;
        }
        if (state === 'winners' && winnersEl) winnersEl.style.display = 'block';
        if (modal) modal.style.display = 'flex';
    }

    window.closeDrawModal = function() {
        triggerHaptic('light');
        const modal = document.getElementById('draw-modal');
        if (modal) modal.style.display = 'none';
        fetchArenaStatus(true);
    };

    async function fetchRoundResults(roundId, retries = 0) {
        if (!roundId || retries > 4) { fetchArenaStatus(true); return; }
        try {
            const initData = tele?.initData || "";
            const response = await fetch('/api/games/results', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({ initData: initData, round_id: roundId })
            });
            const data = await response.json();
            if (data.success) {
                if (data.new_balance !== undefined) setStoredBalance(data.new_balance, true);
                if (data.status === 'refunded') showDrawModal('refunded', data.refund_amount || currentEntryFee);
                else if (data.status === 'completed') { renderWinners(data.winners || []); showDrawModal('winners'); }
                else setTimeout(() => fetchRoundResults(roundId, retries + 1), 2500);
            }
        } catch (e) {
            setTimeout(() => fetchRoundResults(roundId, retries + 1), 2500);
        }
    }

    async function checkBackgroundNotifications() {
        try {
            const initData = tele?.initData || "";
            if (!initData) return;
            const response = await fetch('/api/games/check_notifications', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({ initData: initData })
            });
            const data = await response.json();
            if (data.success) {
                if (data.balance !== undefined) setStoredBalance(data.balance, true);
                if (data.refund && data.refund > 0) {
                    triggerGlobalToast(`💰 تم استرداد المبلغ بنجاح (+${data.refund} ZN)`);
                    showDrawModal('refunded', data.refund);
                }
            }
        } catch (e) {}
    }

    function renderWinners(winners) {
        const list = document.getElementById('winners-list');
        if (!list) return;
        list.innerHTML = '';
        const medals = ['🥇', '🥈', '🥉', '🏅', '🏅'];
        winners.forEach((winner, index) => {
            let name = winner.name || `مستخدم #${(winner.uid || '00000').substring(0,5)}`;
            let prize = formatNumberHTML(winner.prize || 0);
            list.innerHTML += `
                <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 8px; border-bottom:1px solid rgba(255,255,255,0.06);">
                    <span style="font-weight:700;">${medals[index] || '🏅'} ${name}</span>
                    <span style="color:var(--accent-green); font-weight:800;">+${prize} ZN</span>
                </div>
            `;
        });
    }

    if (backgroundSyncInterval) clearInterval(backgroundSyncInterval);
    backgroundSyncInterval = setInterval(checkBackgroundNotifications, 25000);

    syncGameBalance();
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            fetchArenaStatus(true);
            checkBackgroundNotifications();
            renderMinesGrid();
        });
    } else {
        fetchArenaStatus(true);
        checkBackgroundNotifications();
        renderMinesGrid();
    }
})();

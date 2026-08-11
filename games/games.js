// games/games.js
(function initGamesModule() {
    let isJoining = false;
    let currentRoundId = null;
    let arenaEndTime = 0;
    let countdownInterval = null;
    let backgroundSyncInterval = null;
    let hasCheckedResults = false;
    let statusRetryTimeout = null;
    let pendingConfirmCallback = null;

    let lastStatusFetchTimestamp = 0;
    const STATUS_FETCH_COOLDOWN = 8000;
    let hasJoinedCurrentRound = false;

    let currentEntryFee = 350;
    let currentLockSeconds = 15;
    let currentDisplayBalance = 0;
    let currentPrizePool = 0;

    let boxesState = {
        inGame: false,
        isProcessingPick: false,
        bet: 100,
        brokenCount: 3,
        picks: [],
        sessionToken: null,
        multipliers: [1.2, 1.5, 2.0, 2.8, 3.8, 5.2, 7.5, 10.0, 14.0, 20.0, 28.0, 40.0],
        lastHitIndex: null,
        reviveUsed: false
    };

    const tele = window.Telegram?.WebApp;

    // استخراج ID المستخدم بجميع الطرق الممكنة لمنع حدوث 0.00
    function getTgId() {
        let id = tele?.initDataUnsafe?.user?.id;
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
    }

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
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        const num = bal !== null ? parseFloat(bal) : 0;
        return isNaN(num) ? 0 : num;
    }

    function setStoredBalance(newBalance, animate = true) {
        if (newBalance !== undefined && newBalance !== null) {
            const numVal = Math.round((parseFloat(newBalance) || 0) * 100) / 100;
            const oldVal = currentDisplayBalance || getStoredBalance();
            
            if (window.userState) window.userState.balance = numVal;
            localStorage.setItem('zn_balance', numVal.toString());
            
            const targetElements = ['top-balance-games', 'user-balance', 'top-balance'];
            targetElements.forEach(id => {
                const gameBalEl = document.getElementById(id);
                if (gameBalEl) {
                    if (animate) animateCounter(id, oldVal, numVal, 800, " ZN");
                    else gameBalEl.innerHTML = formatNumberHTML(numVal, " ZN");
                }
            });

            currentDisplayBalance = numVal;
        }
    }

    async function syncUserData() {
        const tgId = getTgId();
        if (!tgId) return;

        try {
            const res = await fetch(`/api/user/info?tg_id=${tgId}`);
            const data = await res.json();
            if (data.success && data.balance !== undefined) {
                setStoredBalance(data.balance, true);
            }
        } catch (e) {
            console.error("Error syncing user profile:", e);
        }
    }

    window.switchGameTab = function(tabName) {
        triggerHaptic('light');
        const arenaTab = document.getElementById('tab-arena');
        const boxesTab = document.getElementById('tab-boxes');
        const arenaContent = document.getElementById('content-arena');
        const boxesContent = document.getElementById('content-boxes');

        if (tabName === 'arena') {
            if (arenaTab) { arenaTab.classList.add('active'); arenaTab.style.opacity = '1'; }
            if (boxesTab) { boxesTab.classList.remove('active'); boxesTab.style.opacity = '0.6'; }
            if (arenaContent) arenaContent.style.display = 'block';
            if (boxesContent) boxesContent.style.display = 'none';
            fetchArenaStatus(true);
        } else {
            if (boxesTab) { boxesTab.classList.add('active'); boxesTab.style.opacity = '1'; }
            if (arenaTab) { arenaTab.classList.remove('active'); arenaTab.style.opacity = '0.6'; }
            if (arenaContent) arenaContent.style.display = 'none';
            if (boxesContent) boxesContent.style.display = 'block';
            renderBoxesGrid();
        }
    };

    window.openBoxesSettings = function() {
        if (boxesState.inGame) return;
        triggerHaptic('light');
        const modal = document.getElementById('boxes-settings-modal');
        if (modal) modal.style.display = 'flex';
    };

    window.closeBoxesSettings = function() {
        triggerHaptic('light');
        const modal = document.getElementById('boxes-settings-modal');
        if (modal) modal.style.display = 'none';
    };

    window.selectBrokenCount = function(count) {
        if (boxesState.inGame) return;
        triggerHaptic('medium');
        boxesState.brokenCount = count;
        
        document.querySelectorAll('.btn-broken-opt').forEach(btn => {
            btn.classList.remove('selected');
            if (parseInt(btn.getAttribute('data-count'), 10) === count) {
                btn.classList.add('selected');
            }
        });

        const selectedText = document.getElementById('selected-broken-text');
        if (selectedText) selectedText.innerText = `${count} عملات مكسورة (سقف 🌟 ${20 + (count - 3) * 10}x)`;
        closeBoxesSettings();
    };

    window.addBetBoxes = (amt) => {
        if (boxesState.inGame) return;
        triggerHaptic('light');
        const input = document.getElementById('boxes-bet-input');
        if (!input) return;
        let val = (parseFloat(input.value) || 0) + amt;
        input.value = Math.max(100, Math.floor(val));
    };

    window.setBetMaxBoxes = () => {
        if (boxesState.inGame) return;
        triggerHaptic('medium');
        const input = document.getElementById('boxes-bet-input');
        if (!input) return;
        const maxBal = Math.floor(getStoredBalance());
        input.value = maxBal > 100 ? maxBal : 100;
    };

    function renderBoxesGrid() {
        const gridEl = document.getElementById('boxes-grid');
        if (!gridEl) return;
        gridEl.innerHTML = '';
        
        for (let i = 0; i < 36; i++) {
            const boxCard = document.createElement('div');
            boxCard.className = 'box-card';
            boxCard.setAttribute('data-index', i);
            boxCard.onclick = () => onBoxClick(i);

            boxCard.innerHTML = `
                <div class="box-inner">
                    <div class="box-front"></div>
                    <div class="box-back"></div>
                </div>
            `;
            gridEl.appendChild(boxCard);
        }
        updateCashOutButton();
    }

    function updateCashOutButton() {
        const btn = document.getElementById('btn-cashout-boxes');
        if (!btn) return;

        if (!boxesState.inGame) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerHTML = `سحب الأرباح (0.00 ZN)`;
            return;
        }

        const picksCount = boxesState.picks.length;
        if (picksCount === 0) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerHTML = `اختر الصندوق الأول 🚀`;
        } else {
            btn.disabled = false;
            btn.classList.remove('btn-disabled');
            const multIndex = Math.min(picksCount - 1, boxesState.multipliers.length - 1);
            const currentMult = boxesState.multipliers[multIndex] || 1.2;
            const payout = (boxesState.bet * currentMult).toFixed(2);
            btn.innerHTML = `💰 سحب الأرباح (${formatNumberHTML(payout)} ZN) <span style="font-size:0.85em; opacity:0.9;">(${currentMult}x)</span>`;
        }
    }

    window.startBoxesGame = async function() {
        if (boxesState.inGame) return;
        const betInput = document.getElementById('boxes-bet-input');
        const betVal = parseFloat(betInput ? betInput.value : 100) || 0;
        
        if (betVal < 100) return showNotification("الحد الأدنى للرهان هو 100 ZN.");
        if (getStoredBalance() < betVal) return showNotification("رصيدك غير كافٍ للبدء.");

        triggerHaptic('heavy');
        const btnStart = document.getElementById('btn-start-boxes');
        if (btnStart) {
            btnStart.disabled = true;
            btnStart.innerText = "جاري فتح الشبكة... ⏳";
        }

        try {
            const initData = tele?.initData || "";
            const tgId = getTgId();

            const res = await fetch('/api/game/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    tg_id: tgId, 
                    bet_amount: betVal, 
                    broken_count: boxesState.brokenCount,
                    initData: initData 
                })
            });

            const data = await res.json();
            if (data.status === 'success' || data.success) {
                const newBal = data.new_balance !== undefined ? data.new_balance : (getStoredBalance() - betVal);
                setStoredBalance(newBal, true);
                
                boxesState.inGame = true;
                boxesState.isProcessingPick = false;
                boxesState.bet = betVal;
                boxesState.picks = [];
                boxesState.sessionToken = data.session_token || null;
                if (data.multipliers) boxesState.multipliers = data.multipliers;
                boxesState.reviveUsed = false;
                
                renderBoxesGrid();
                
                if (btnStart) btnStart.style.display = 'none';
                const btnCashOut = document.getElementById('btn-cashout-boxes');
                if (btnCashOut) btnCashOut.style.display = 'block';
                if (betInput) betInput.disabled = true;
                
                updateCashOutButton();
                triggerGlobalToast("✨ بدأت الجولة! اختر صناديقك بحذر.", true);
            } else {
                if (btnStart) {
                    btnStart.disabled = false;
                    btnStart.innerText = "بدء الجولة 🚀";
                }
                showNotification("⚠️ " + (data.message || "تعذر بدء الجولة"));
            }
        } catch (e) {
            if (btnStart) {
                btnStart.disabled = false;
                btnStart.innerText = "بدء الجولة 🚀";
            }
            showNotification("خطأ في الاتصال بالخادم.");
        }
    };

    async function onBoxClick(index) {
        if (!boxesState.inGame || boxesState.picks.includes(index) || boxesState.isProcessingPick) return;
        
        boxesState.isProcessingPick = true;
        triggerHaptic('medium');

        const boxCard = document.querySelector(`.box-card[data-index="${index}"]`);
        if (!boxCard) {
            boxesState.isProcessingPick = false;
            return;
        }

        try {
            const initData = tele?.initData || "";
            const tgId = getTgId();

            const res = await fetch('/api/game/step', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tg_id: tgId,
                    box_index: index,
                    session_token: boxesState.sessionToken,
                    initData: initData
                })
            });

            const data = await res.json();
            const isBomb = data.is_bomb || data.status === 'loss';

            if (!isBomb && (data.status === 'safe' || data.success)) {
                boxesState.picks.push(index);
                const backEl = boxCard.querySelector('.box-back');
                if (backEl) backEl.innerHTML = '<span class="coin-gold">🟡 ZN</span>';
                boxCard.classList.add('flipped', 'safe');
                updateCashOutButton();
            } else {
                handleBrokenCoinHit(index, data.layout);
            }
        } catch (e) {
            showNotification("خطأ في الاتصال بالخادم أثناء الاختيار.");
        } finally {
            boxesState.isProcessingPick = false;
        }
    }

    window.cashOutBoxes = async function() {
        if (!boxesState.inGame) return;
        triggerHaptic('heavy');

        const btnCashOut = document.getElementById('btn-cashout-boxes');
        if (btnCashOut) {
            btnCashOut.disabled = true;
            btnCashOut.innerText = "جاري تأكيد السحب... ⏳";
        }

        try {
            const initData = tele?.initData || "";
            const tgId = getTgId();

            const res = await fetch('/api/game/cashout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tg_id: tgId,
                    session_token: boxesState.sessionToken,
                    initData: initData
                })
            });

            const data = await res.json();
            if (data.status === 'success' || data.success) {
                if (data.new_balance !== undefined) setStoredBalance(data.new_balance, true);
                revealFullBoard(data.layout);
                triggerHaptic('success');
                triggerGlobalToast(`🎉 مبروك! سحبت ${formatNumberHTML(data.payout)} ZN`, true);
                resetBoxesControls();
            } else {
                showNotification("⚠️ " + (data.message || "تعذر إتمام السحب"));
                resetBoxesControls();
            }
        } catch (e) {
            showNotification("خطأ في الاتصال بالخادم.");
            resetBoxesControls();
        }
    };

    function handleBrokenCoinHit(index, layout) {
        boxesState.lastHitIndex = index;
        triggerHaptic('error');
        
        const boxCard = document.querySelector(`.box-card[data-index="${index}"]`);
        if (boxCard) {
            const backEl = boxCard.querySelector('.box-back');
            if (backEl) backEl.innerHTML = '<span class="coin-broken">⚪💥</span>';
            boxCard.classList.add('flipped', 'broken');
        }

        if (!boxesState.reviveUsed && window.Adsgram) {
            showReviveModal(index, layout);
        } else {
            finalizeLoss(layout);
        }
    }

    function showReviveModal(hitIndex, layout) {
        const modal = document.getElementById('revive-modal');
        if (modal) modal.style.display = 'flex';
        
        window.onConfirmRevive = async function(watchAd) {
            if (modal) modal.style.display = 'none';
            if (watchAd) {
                try {
                    const AdController = window.Adsgram?.init({ blockId: "100" });
                    const adResult = await AdController.show();
                    if (adResult && adResult.done) {
                        triggerHaptic('success');
                        boxesState.reviveUsed = true;
                        boxesState.picks = boxesState.picks.filter(p => p !== hitIndex);
                        const card = document.querySelector(`.box-card[data-index="${hitIndex}"]`);
                        if (card) {
                            card.classList.remove('flipped', 'broken');
                            const backEl = card.querySelector('.box-back');
                            if (backEl) backEl.innerHTML = '';
                        }
                        updateCashOutButton();
                        triggerGlobalToast("🛡️ تم تفعيل ميزة الإحياء! تابع اللعب.", true);
                        return;
                    }
                } catch (err) {
                    triggerGlobalToast("⚠️ تعذر تحميل الإعلان، تم تطبيق الخسارة.", false);
                }
            }
            finalizeLoss(layout);
        };
    }

    function finalizeLoss(layout) {
        revealFullBoard(layout);
        triggerGlobalToast("💥 اصطدمت بقنبلة! حظاً أوفير في الجولة القادمة.", false);
        resetBoxesControls();
    }

    function revealFullBoard(layout) {
        if (!layout) return;
        for (let i = 0; i < 36; i++) {
            const card = document.querySelector(`.box-card[data-index="${i}"]`);
            if (!card) continue;
            
            const isBroken = layout[i];
            const backEl = card.querySelector('.box-back');
            if (isBroken) {
                if (backEl) backEl.innerHTML = '<span class="coin-broken">⚪💥</span>';
                card.classList.add('broken');
            } else {
                if (backEl) backEl.innerHTML = '<span class="coin-gold">🟡 ZN</span>';
                card.classList.add('safe');
            }
            card.classList.add('flipped');
        }
    }

    function resetBoxesControls() {
        boxesState.inGame = false;
        boxesState.isProcessingPick = false;
        const btnStart = document.getElementById('btn-start-boxes');
        const btnCashOut = document.getElementById('btn-cashout-boxes');
        const betInput = document.getElementById('boxes-bet-input');
        
        if (btnStart) {
            btnStart.style.display = 'block';
            btnStart.disabled = false;
            btnStart.innerText = "بدء الجولة 🚀";
        }
        if (btnCashOut) btnCashOut.style.display = 'none';
        if (betInput) betInput.disabled = false;
    }

    async function fetchArenaStatus(force = false) {
        const now = Date.now();
        if (!force && (now - lastStatusFetchTimestamp < STATUS_FETCH_COOLDOWN)) return;
        lastStatusFetchTimestamp = now;

        try {
            const initData = tele?.initData || "";
            const response = await fetch('/api/games/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData, tg_id: getTgId() })
            });
            const data = await response.json();
            if (data.success) {
                if (data.entry_fee) currentEntryFee = data.entry_fee;
                if (data.balance !== undefined) setStoredBalance(data.balance, true);
                currentRoundId = data.round_id;
                arenaEndTime = parseInt(data.end_time) || 0;
                hasJoinedCurrentRound = !!data.has_joined;
                updateArenaPrizes(data);
                startSmoothCountdown();
            }
        } catch (error) {}
    }

    function updateArenaPrizes(data) {
        const newPool = parseFloat(data.prize_pool) || 0;
        animateCounter('prize-pool', currentPrizePool, newPool, 900, " ZN");
        currentPrizePool = newPool;
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
            btn.innerText = "🔒 تم إغلاق الاشتراك";
        } else if (timeLeft === 0) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerText = "🔄 جاري إعلان النتائج...";
            if (!hasCheckedResults && currentRoundId) {
                hasCheckedResults = true;
                fetchRoundResults(currentRoundId);
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

        try {
            const initData = tele?.initData || "";
            const response = await fetch('/api/games/join', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData, tg_id: getTgId() })
            });
            const data = await response.json();
            if (data.success) {
                triggerHaptic('success');
                hasJoinedCurrentRound = true;
                if (data.new_balance !== undefined) setStoredBalance(data.new_balance, true);
                showNotification("🎉 تم دخول الساحة بنجاح!");
            } else {
                showNotification("⚠️ " + (data.message || "تعذر الاشتراك"));
            }
        } catch (error) {
            showNotification("خطأ في الاتصال بالخادم.");
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
    }

    function askForConfirmation(onConfirm) {
        const modal = document.getElementById('confirm-modal');
        if (modal) { pendingConfirmCallback = onConfirm; modal.style.display = 'flex'; }
    }

    window.onConfirmJoin = function(confirmed) {
        triggerHaptic('light');
        const modal = document.getElementById('confirm-modal');
        if (modal) modal.style.display = 'none';
        if (confirmed && typeof pendingConfirmCallback === 'function') pendingConfirmCallback();
        pendingConfirmCallback = null;
    };

    async function fetchRoundResults(roundId) {
        try {
            const response = await fetch('/api/games/results', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ round_id: roundId, tg_id: getTgId() })
            });
            const data = await response.json();
            if (data.success) fetchArenaStatus(true);
        } catch (e) {}
    }

    function initModule() {
        if (tele) {
            try {
                tele.ready();
                tele.expand();
            } catch (e) {}
        }
        renderBoxesGrid();
        syncUserData();
        fetchArenaStatus(true);

        if (backgroundSyncInterval) clearInterval(backgroundSyncInterval);
        backgroundSyncInterval = setInterval(() => {
            fetchArenaStatus(false);
        }, 15000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initModule);
    } else {
        initModule();
    }
})();

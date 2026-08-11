// games/arena-game.js
(function initArenaGameModule() {
    let isJoining = false;
    let currentRoundId = null;
    let arenaEndTime = 0;
    let countdownInterval = null;
    let backgroundSyncInterval = null;
    let hasCheckedResults = false;
    let pendingConfirmCallback = null;

    let lastStatusFetchTimestamp = 0;
    const STATUS_FETCH_COOLDOWN = 8000;
    let hasJoinedCurrentRound = false;

    let currentEntryFee = 350;
    let currentLockSeconds = 15;
    let currentPrizePool = 0;
    let currentPayoutPercentages = [40, 20, 10, 8, 6, 5, 4, 3, 2, 2];

    window.fetchArenaStatus = async function(force = false) {
        const now = Date.now();
        if (!force && (now - lastStatusFetchTimestamp < STATUS_FETCH_COOLDOWN)) return;
        lastStatusFetchTimestamp = now;

        try {
            const initData = window.tele?.initData || "";
            const response = await fetch('/api/games/status', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': initData,
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({ initData: initData, tg_id: window.getTgId() })
            });
            if (!response.ok) return;
            const data = await response.json();
            if (data.success) {
                if (data.entry_fee) currentEntryFee = data.entry_fee;
                if (data.lock_seconds !== undefined) currentLockSeconds = parseInt(data.lock_seconds) || 15;
                if (data.balance !== undefined) window.setStoredBalance(data.balance, true);
                if (data.payout_percentages && Array.isArray(data.payout_percentages)) {
                    currentPayoutPercentages = data.payout_percentages;
                }
                
                if (data.round_id !== currentRoundId) {
                    currentRoundId = data.round_id;
                    hasCheckedResults = false;
                }

                arenaEndTime = parseInt(data.end_time) || 0;
                hasJoinedCurrentRound = !!data.has_joined;
                updateArenaPrizes(data);
                startSmoothCountdown();
            }
        } catch (error) {}
    };

    function updateArenaPrizes(data) {
        const newPool = parseFloat(data.prize_pool) || 0;
        window.animateCounter('prize-pool', currentPrizePool, newPool, 900, " ZN");
        currentPrizePool = newPool;
        renderArenaPrizeBreakdown(newPool);
    }

    function renderArenaPrizeBreakdown(prizePool) {
        const container = document.getElementById('arena-prizes-list');
        if (!container) return;

        const medals = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟'];
        let html = '';

        currentPayoutPercentages.forEach((pct, index) => {
            const rankNum = index + 1;
            const medal = medals[index] || `#${rankNum}`;
            const prizeAmount = ((prizePool * parseFloat(pct)) / 100.0);
            
            html += `
                <div class="prize-rank-item">
                    <div class="prize-rank-info">
                        <span class="prize-rank-icon">${medal}</span>
                        <span class="prize-rank-title">المركز ${rankNum}</span>
                    </div>
                    <div class="prize-rank-values">
                        <span class="prize-rank-pct">%${pct}</span>
                        <span class="prize-rank-amount">${window.formatNumberHTML(prizeAmount)} ZN</span>
                    </div>
                </div>
            `;
        });

        container.innerHTML = html;
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
        window.triggerHaptic('heavy');
        if (isJoining || hasJoinedCurrentRound) return;
        if (window.getStoredBalance() < currentEntryFee) {
            window.showNotification(`⚠️ رصيدك غير كافٍ للدخول في الساحة.`);
            return;
        }
        askForConfirmation(() => executeJoinArena());
    };

    async function executeJoinArena() {
        if (isJoining) return;
        isJoining = true;

        try {
            const initData = window.tele?.initData || "";
            const response = await fetch('/api/games/join', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': initData,
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({ initData: initData, tg_id: window.getTgId() })
            });
            const data = await response.json();
            if (response.ok && data.success) {
                window.triggerHaptic('success');
                hasJoinedCurrentRound = true;
                if (data.new_balance !== undefined) window.setStoredBalance(data.new_balance, true);
                window.showNotification("🎉 تم دخول الساحة بنجاح!");
            } else {
                window.showNotification("⚠️ " + (data.message || "تعذر الاشتراك"));
            }
        } catch (error) {
            window.showNotification("خطأ في الاتصال بالخادم.");
        } finally {
            isJoining = false;
        }
    }

    function askForConfirmation(onConfirm) {
        const modal = document.getElementById('confirm-modal');
        if (modal) { pendingConfirmCallback = onConfirm; modal.style.display = 'flex'; }
    }

    window.onConfirmJoin = function(confirmed) {
        window.triggerHaptic('light');
        const modal = document.getElementById('confirm-modal');
        if (modal) modal.style.display = 'none';
        if (confirmed && typeof pendingConfirmCallback === 'function') pendingConfirmCallback();
        pendingConfirmCallback = null;
    };

    async function fetchRoundResults(roundId) {
        try {
            const initData = window.tele?.initData || "";
            const response = await fetch('/api/games/results', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': initData,
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({ round_id: roundId, tg_id: window.getTgId() })
            });
            const data = await response.json();
            if (data.success) window.fetchArenaStatus(true);
        } catch (e) {}
    }

    function initArena() {
        renderArenaPrizeBreakdown(currentPrizePool);
        window.fetchArenaStatus(true);

        if (backgroundSyncInterval) clearInterval(backgroundSyncInterval);
        backgroundSyncInterval = setInterval(() => {
            window.fetchArenaStatus(false);
        }, 15000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initArena);
    } else {
        initArena();
    }
})();

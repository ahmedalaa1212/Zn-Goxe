// games/arena-game.js
(function initArenaGameModule() {
    let isJoining = false;
    let isFetchingStatus = false;
    let currentRoundId = null;
    let arenaEndTime = 0;
    let countdownInterval = null;
    let backgroundSyncInterval = null;
    let hasCheckedResults = false;
    let pendingConfirmCallback = null;

    let lastStatusFetchTimestamp = 0;
    const STATUS_FETCH_COOLDOWN = 5000;
    let hasJoinedCurrentRound = false;

    let currentEntryFee = 350;
    let currentLockSeconds = 15;
    let currentPrizePool = 0;
    let currentPayoutPercentages = [40, 20, 10, 8, 6, 5, 4, 3, 2, 2];

    window.fetchArenaStatus = async function(force = false) {
        const now = Date.now();
        if (isFetchingStatus) return;
        if (!force && (now - lastStatusFetchTimestamp < STATUS_FETCH_COOLDOWN)) return;

        isFetchingStatus = true;
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

                const inBoxesGame = window.boxesState && window.boxesState.inGame;
                const fetchedBalance = data.balance !== undefined ? data.balance : data.user_balance;

                if (fetchedBalance !== undefined && !window.isTransactionPending && !inBoxesGame) {
                    window.setStoredBalance(fetchedBalance, true);
                }

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
        } catch (error) {
            console.error("Error fetching arena status:", error);
        } finally {
            isFetchingStatus = false;
        }
    };

    function updateArenaPrizes(data) {
        const newPool = Math.round((parseFloat(data.prize_pool) || 0) * 100) / 100;
        if (Math.abs(newPool - currentPrizePool) >= 0.01) {
            window.animateCounter('prize-pool', currentPrizePool, newPool, 800, " ZN");
            currentPrizePool = newPool;
        }
        renderArenaPrizeBreakdown(currentPrizePool);
    }

    function renderArenaPrizeBreakdown(prizePool) {
        const container = document.getElementById('arena-prizes-list');
        if (!container) return;

        const medals = ['🥇', '🥈', '🥉', '4️⃣', '5️⃣', '6️⃣', '7️⃣', '8️⃣', '9️⃣', '🔟'];
        let html = '';

        currentPayoutPercentages.forEach((pct, index) => {
            const rankNum = index + 1;
            const medal = medals[index] || `#${rankNum}`;
            const prizeAmount = Math.round(((prizePool * parseFloat(pct)) / 100.0) * 100) / 100;
            
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
                setTimeout(() => fetchRoundResults(currentRoundId), 1500);
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
        window.isTransactionPending = true;

        const btn = document.getElementById('btn-join-arena');
        if (btn) {
            btn.disabled = true;
            btn.innerText = "⏳ جاري الانضمام...";
        }

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

                const currentBal = window.getStoredBalance();
                const updatedBalance = data.new_balance !== undefined 
                    ? data.new_balance 
                    : (data.balance !== undefined ? data.balance : Math.max(0, currentBal - currentEntryFee));

                window.setStoredBalance(updatedBalance, true);

                if (data.prize_pool !== undefined) {
                    updateArenaPrizes(data);
                }

                window.showNotification("🎉 تم دخول الساحة بنجاح!");
            } else {
                window.showNotification("⚠️ " + (data.message || "تعذر الاشتراك"));
                // 🌟 إعادة مزامنة الحالة فوراً عند حدوث خطأ
                window.fetchArenaStatus(true);
            }
        } catch (error) {
            window.showNotification("خطأ في الاتصال بالخادم.");
        } finally {
            isJoining = false;
            setTimeout(() => { window.isTransactionPending = false; }, 2000);
            timerTick();
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
            if (data.success) {
                window.fetchArenaStatus(true);
            }
        } catch (e) {
            console.error("Error fetching round results:", e);
        }
    }

    function initArena() {
        renderArenaPrizeBreakdown(currentPrizePool);
        
        // 🌟 فحص واستعادة أي رصيد معلق مباشرة عند بدء اللعبة
        const tgId = window.getTgId();
        if (tgId) {
            const initData = window.tele?.initData || "";
            fetch(`/api/games/check_notifications?tg_id=${tgId}`, {
                headers: { 'X-Telegram-Init-Data': initData, 'Authorization': `Bearer ${initData}` }
            }).catch(() => {});
        }

        window.fetchArenaStatus(true);

        if (backgroundSyncInterval) clearInterval(backgroundSyncInterval);
        backgroundSyncInterval = setInterval(() => {
            window.fetchArenaStatus(false);
        }, 10000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initArena);
    } else {
        initArena();
    }
})();

// games/arena-game.js
(function () {
    let arenaTimerInterval = null;
    let arenaSyncInterval = null;
    let arenaEndTime = 0;
    let hasJoinedRound = false;
    let entryFee = 350;

    window.initArenaGame = function () {
        fetchArenaStatus(true);
        if (arenaTimerInterval) clearInterval(arenaTimerInterval);
        if (arenaSyncInterval) clearInterval(arenaSyncInterval);

        arenaTimerInterval = setInterval(updateArenaTimerUI, 1000);
        arenaSyncInterval = setInterval(() => fetchArenaStatus(false), 4000);
    };

    window.stopArenaGame = function () {
        if (arenaTimerInterval) clearInterval(arenaTimerInterval);
        if (arenaSyncInterval) clearInterval(arenaSyncInterval);
    };

    async function fetchArenaStatus(force = false) {
        try {
            const initData = window.Telegram?.WebApp?.initData || "";
            const res = await fetch('/api/games/arena/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData, tg_id: window.getTgId() })
            });

            if (!res.ok) return;
            const data = await res.json();

            if (data.success) {
                arenaEndTime = parseInt(data.end_time) || 0;
                hasJoinedRound = !!data.has_joined;
                entryFee = data.entry_fee || 350;

                const poolEl = document.getElementById('prize-pool');
                if (poolEl) poolEl.innerText = `ZN ${(data.prize_pool || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}`;

                if (data.balance !== undefined) {
                    window.updateBalanceDisplay(data.balance);
                }

                renderPrizesBreakdown(data.prize_pool || 0);
                updateArenaTimerUI();
            }
        } catch (e) {
            console.error("Arena fetch status error:", e);
        }
    }

    function updateArenaTimerUI() {
        const timerEl = document.getElementById('arena-timer');
        const btn = document.getElementById('btn-join-arena');
        const now = Math.floor(Date.now() / 1000);
        let left = arenaEndTime - now;

        if (left < 0) left = 0;

        if (timerEl) {
            const m = String(Math.floor(left / 60)).padStart(2, '0');
            const s = String(left % 60).padStart(2, '0');
            timerEl.innerText = `${m}:${s}`;
        }

        if (!btn) return;

        if (left === 0) {
            btn.disabled = true;
            btn.innerText = "🔄 جاري إعلان النتائج واستبدال الجولة...";
            setTimeout(() => fetchArenaStatus(true), 2000);
        } else if (hasJoinedRound) {
            btn.disabled = true;
            btn.innerText = "أنت مشترك بالفعل ✅";
        } else {
            btn.disabled = false;
            btn.innerText = `⚔️ دخول الساحة (${entryFee} ZN)`;
        }
    }

    function renderPrizesBreakdown(pool) {
        const listEl = document.getElementById('arena-prizes-list');
        if (!listEl) return;

        const pcts = [40, 20, 10, 8, 6, 5, 4, 3, 2, 2];
        let html = '';
        pcts.forEach((pct, idx) => {
            const amt = ((pool * pct) / 100).toFixed(2);
            html += `
                <div class="prize-row">
                    <span>المركز ${idx + 1} (%${pct})</span>
                    <strong>${amt} ZN</strong>
                </div>
            `;
        });
        listEl.innerHTML = html;
    }

    window.joinArenaGame = async function () {
        if (hasJoinedRound) return;

        if (window.userBalance < entryFee) {
            window.showGameNotification("⚠️ رصيدك غير كافٍ للاشتراك!");
            return;
        }

        try {
            const initData = window.Telegram?.WebApp?.initData || "";
            const res = await fetch('/api/games/arena/join', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData, tg_id: window.getTgId() })
            });

            const data = await res.json();
            if (res.ok && data.success) {
                window.showGameNotification("🎉 تم دخول الساحة بنجاح!");
                hasJoinedRound = true;
                if (data.new_balance !== undefined) window.updateBalanceDisplay(data.new_balance);
                fetchArenaStatus(true);
            } else {
                window.showGameNotification(data.message || "❌ تعذر الاشتراك.");
                fetchArenaStatus(true);
            }
        } catch (e) {
            window.showGameNotification("❌ خطأ في شبكة الاتصال.");
        }
    };

    // تشغيل آلي تلقائي عند البدء
    document.addEventListener('DOMContentLoaded', () => {
        if (window.currentGameTab === 'arena') window.initArenaGame();
    });
})();

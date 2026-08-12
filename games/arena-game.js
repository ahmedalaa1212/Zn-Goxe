// games/arena-game.js
(function initArenaGame() {
    let isRequesting = false;
    let arenaEndTime = 0;
    let timerInterval = null;
    let syncInterval = null;
    let hasJoined = false;
    let currentFee = 350;

    // جلب حالة الساحة من السيرفر
    window.fetchArenaStatus = async function(force = false) {
        if (isRequesting && !force) return;
        isRequesting = true;

        try {
            const initData = window.tele?.initData || "";
            const res = await fetch('/api/games/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': initData },
                body: JSON.stringify({ initData: initData, tg_id: window.getTgId() })
            });

            if (!res.ok) return;
            const data = await res.json();

            if (data.success) {
                arenaEndTime = parseInt(data.end_time) || 0;
                hasJoined = !!data.has_joined;
                currentFee = data.entry_fee || 350;

                // تحديث المجمع والرصيد
                const poolEl = document.getElementById('prize-pool');
                if (poolEl) poolEl.innerText = `${(data.prize_pool || 0).toLocaleString()} ZN`;

                if (data.balance !== undefined) {
                    window.setStoredBalance(data.balance, true);
                }

                updateTimerUI();
            }
        } catch (err) {
            console.error("Arena sync error:", err);
        } finally {
            isRequesting = false;
        }
    };

    // تحديث العداد والزر
    function updateTimerUI() {
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
            btn.className = "btn-disabled";
            btn.innerText = "🔄 جاري بدء جولة جديدة...";
            // طلب جولة جديدة فوراً عند الوصول لـ 0
            setTimeout(() => window.fetchArenaStatus(true), 2000);
        } else if (hasJoined) {
            btn.disabled = true;
            btn.className = "btn-disabled";
            btn.innerText = "أنت مشترك بالفعل ✅";
        } else {
            btn.disabled = false;
            btn.className = "";
            btn.innerText = `⚔️ دخول الساحة (${currentFee} ZN)`;
        }
    }

    // زر دخول الساحة
    window.joinArena = async function() {
        if (hasJoined || isRequesting) return;

        if (window.getStoredBalance() < currentFee) {
            window.showNotification("⚠️ رصيدك غير كافٍ لدخول الساحة.");
            return;
        }

        btnLoading(true);
        try {
            const initData = window.tele?.initData || "";
            const res = await fetch('/api/games/join', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-Telegram-Init-Data': initData },
                body: JSON.stringify({ initData: initData, tg_id: window.getTgId() })
            });

            const data = await res.json();
            if (res.ok && data.success) {
                window.showNotification("🎉 تم الانضمام للساحة بنجاح!");
                hasJoined = true;
                if (data.result && data.result.new_balance !== undefined) {
                    window.setStoredBalance(data.result.new_balance, true);
                }
                window.fetchArenaStatus(true);
            } else {
                window.showNotification(data.message || "❌ تعذر الانضمام.");
                window.fetchArenaStatus(true);
            }
        } catch (e) {
            window.showNotification("❌ خطأ في الاتصال.");
        } finally {
            btnLoading(false);
        }
    };

    function btnLoading(loading) {
        const btn = document.getElementById('btn-join-arena');
        if (!btn) return;
        if (loading) {
            btn.disabled = true;
            btn.innerText = "⏳ جاري تنفيذ الطلب...";
        }
    }

    // بدء المزامنة
    function start() {
        window.fetchArenaStatus(true);
        if (timerInterval) clearInterval(timerInterval);
        if (syncInterval) clearInterval(syncInterval);

        timerInterval = setInterval(updateTimerUI, 1000);
        syncInterval = setInterval(() => window.fetchArenaStatus(false), 4000);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', start);
    } else {
        start();
    }
})();

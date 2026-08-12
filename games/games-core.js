// games/games-core.js - التحكم المركزي والتبويب
(function () {
    window.currentGameTab = 'arena';
    window.userBalance = 0.0;

    // الحصول على معرف التليجرام
    window.getTgId = function () {
        if (window.Telegram?.WebApp?.initDataUnsafe?.user?.id) {
            return String(window.Telegram.WebApp.user.id);
        }
        return "test_user_id";
    };

    // تحديث الشاشة بالرصيد
    window.updateBalanceDisplay = function (newBal) {
        if (newBal !== undefined && newBal !== null) {
            window.userBalance = parseFloat(newBal);
            const el = document.getElementById('user-zn-balance');
            if (el) el.innerText = window.userBalance.toLocaleString('en-US', { minimumFractionDigits: 2 });
        }
    };

    // التبديل بين اللعبتين بعزل تام
    window.switchGameTab = function (tabName) {
        if (window.currentGameTab === tabName) return;
        window.currentGameTab = tabName;

        // تحديث أزرار التبويب
        document.querySelectorAll('.game-tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.game-view-section').forEach(view => view.classList.remove('active'));

        const activeBtn = document.getElementById(`tab-btn-${tabName}`);
        const activeView = document.getElementById(`game-view-${tabName}`);

        if (activeBtn) activeBtn.classList.add('active');
        if (activeView) activeView.classList.add('active');

        // تشغيل اللعبة المختارة وإيقاف الأخرى
        if (tabName === 'arena') {
            if (window.initArenaGame) window.initArenaGame();
            if (window.stopBoxesGame) window.stopBoxesGame();
        } else if (tabName === 'boxes') {
            if (window.stopArenaGame) window.stopArenaGame();
            if (window.initBoxesGame) window.initBoxesGame();
        }
    };

    // إشعار بسيط للمستخدم
    window.showGameNotification = function (msg) {
        alert(msg);
    };
})();

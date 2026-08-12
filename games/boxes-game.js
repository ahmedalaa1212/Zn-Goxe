// games/boxes-game.js
(function () {
    let isGameActive = false;

    window.initBoxesGame = function () {
        resetBoxesUI();
    };

    window.stopBoxesGame = function () {
        isGameActive = false;
    };

    function resetBoxesUI() {
        const gridContainer = document.getElementById('boxes-grid');
        if (!gridContainer) return;

        const boxes = gridContainer.querySelectorAll('.box-item');
        boxes.forEach(box => {
            box.innerText = "📦";
            box.classList.remove('opened');
        });
        isGameActive = true;
    }

    window.resetBoxesGame = function () {
        resetBoxesUI();
    };

    window.openBox = async function (index) {
        if (!isGameActive) return;

        const betInput = document.getElementById('boxes-bet-input');
        const betAmount = parseFloat(betInput ? betInput.value : 100);

        if (window.userBalance < betAmount) {
            window.showGameNotification("⚠️ رصيدك لا يكفي لهذا الرهان.");
            return;
        }

        try {
            const initData = window.Telegram?.WebApp?.initData || "";
            const res = await fetch('/api/games/boxes/play', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    initData: initData,
                    tg_id: window.getTgId(),
                    box_index: index,
                    bet_amount: betAmount
                })
            });

            const data = await res.json();
            if (res.ok && data.success) {
                const gridContainer = document.getElementById('boxes-grid');
                const box = gridContainer.children[index];
                if (box) {
                    box.innerText = `${data.multiplier}x\n(${data.win_amount} ZN)`;
                    box.classList.add('opened');
                }

                if (data.new_balance !== undefined) window.updateBalanceDisplay(data.new_balance);
                window.showGameNotification(`🎉 فزت بـ ${data.win_amount} ZN!`);
            } else {
                window.showGameNotification(data.message || "❌ فشلت العملية.");
            }
        } catch (e) {
            window.showGameNotification("❌ خطأ في الاتصال بالخادم.");
        }
    };
})();

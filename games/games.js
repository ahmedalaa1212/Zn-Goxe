(function () {
    let currentSelectedDiff = 'easy';
    let isBoxesActive = false;
    let boxesSessionData = null;

    // ---------------------------------------------------------
    // 1. تهيئة الصفحة والتبويب
    // ---------------------------------------------------------
    window.initGamesPage = async function () {
        if (window.Telegram && window.Telegram.WebApp) {
            window.Telegram.WebApp.expand();
        }
        render36BoxesGrid();
        await fetchGamesState();
    };

    window.switchGameSubTab = function (tabName) {
        document.querySelectorAll('.game-tab-btn').forEach(btn => btn.classList.remove('active'));
        document.querySelectorAll('.game-subview').forEach(view => view.classList.remove('active'));

        if (tabName === 'arena') {
            document.getElementById('tab-btn-arena').classList.add('active');
            document.getElementById('subview-arena').classList.add('active');
        } else {
            document.getElementById('tab-btn-boxes').classList.add('active');
            document.getElementById('subview-boxes').classList.add('active');
        }
    };

    // ---------------------------------------------------------
    // 2. جلب حالة الألعاب من الخادم
    // ---------------------------------------------------------
    async function fetchGamesState() {
        try {
            const response = await window.fetchAPI('/api/games/state', { method: 'POST' });
            if (response && response.success) {
                if (response.active_boxes_session) {
                    restoreBoxesSession(response.active_boxes_session);
                }
            }
        } catch (err) {
            console.error("خطأ في جلب حالة الألعاب:", err);
        }
    }

    // ---------------------------------------------------------
    // ⚔️ 3. منطق لعبة الساحة (Arena Controller)
    // ---------------------------------------------------------
    window.selectArenaDiff = function (diff, mult, winRate) {
        currentSelectedDiff = diff;
        document.querySelectorAll('.diff-card').forEach(c => c.classList.remove('active'));
        document.getElementById(`diff-${diff}`).classList.add('active');
    };

    window.adjustArenaBet = function (factor) {
        const input = document.getElementById('arena-bet-input');
        let val = parseFloat(input.value) || 100;
        input.value = Math.max(100, Math.floor(val * factor));
    };

    window.setArenaMaxBet = function () {
        const userBal = window.userState ? window.userState.balance : 0;
        document.getElementById('arena-bet-input').value = Math.max(100, Math.floor(userBal));
    };

    window.startArenaBattle = async function () {
        const betInput = document.getElementById('arena-bet-input');
        const betAmount = parseFloat(betInput.value);
        const btn = document.getElementById('btn-start-arena');

        if (!betAmount || betAmount < 100) {
            if (window.showGlobalToast) window.showGlobalToast("الحد الأدنى للرهان هو 100 ZN", "error");
            return;
        }

        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> جاري القتال...';

        try {
            const res = await window.fetchAPI('/api/games/arena/play', {
                method: 'POST',
                body: JSON.stringify({ difficulty: currentSelectedDiff, bet_amount: betAmount })
            });

            if (res && res.success) {
                if (window.userState) window.userState.balance = res.new_balance;

                if (res.is_win) {
                    if (window.showGlobalToast) {
                        window.showGlobalToast(`🎉 انتصرت في المعركة! كسبت ${res.win_amount} ZN`, "success");
                    }
                } else {
                    if (window.showGlobalToast) {
                        window.showGlobalToast(`💀 هُزمت في المعركة وتكبدت خسارة ${betAmount} ZN`, "error");
                    }
                }
            } else {
                if (window.showGlobalToast) window.showGlobalToast(res.error || "فشلت العملية", "error");
            }
        } catch (e) {
            if (window.showGlobalToast) window.showGlobalToast("حدث خطأ في الاتصال", "error");
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-flag-checkered"></i> دخول الساحة والقتال';
        }
    };

    // ---------------------------------------------------------
    // 📦 4. منطق لعبة 36 صندوق (36 Boxes Controller)
    // ---------------------------------------------------------
    function render36BoxesGrid() {
        const gridContainer = document.getElementById('boxes-grid');
        gridContainer.innerHTML = '';

        for (let i = 0; i < 36; i++) {
            const tile = document.createElement('div');
            tile.className = 'box-tile';
            tile.dataset.index = i;
            tile.innerHTML = '📦';
            tile.onclick = () => onBoxClick(i);
            gridContainer.appendChild(tile);
        }
    }

    window.start36BoxesGame = async function () {
        const betAmount = parseFloat(document.getElementById('boxes-bet-input').value);
        const trapCount = parseInt(document.getElementById('boxes-trap-select').value);
        const btn = document.getElementById('btn-start-boxes');

        if (!betAmount || betAmount < 50) {
            if (window.showGlobalToast) window.showGlobalToast("الحد الأدنى للرهان 50 ZN", "error");
            return;
        }

        btn.disabled = true;

        try {
            const res = await window.fetchAPI('/api/games/36boxes/start', {
                method: 'POST',
                body: JSON.stringify({ bet_amount: betAmount, trap_count: trapCount })
            });

            if (res && res.success) {
                if (window.userState) window.userState.balance = res.new_balance;

                isBoxesActive = true;
                boxesSessionData = { betAmount, trapCount, revealed: [] };

                render36BoxesGrid();
                document.getElementById('boxes-grid').classList.remove('disabled');
                document.getElementById('boxes-setup-panel').style.display = 'none';
                document.getElementById('btn-cashout-boxes').classList.remove('hidden');
                updateBoxesStatus(1.00, 0.00);

                if (window.showGlobalToast) window.showGlobalToast("بدأت اللعبة! اختر الصناديق بحذر", "info");
            } else {
                if (window.showGlobalToast) window.showGlobalToast(res.error || "تعذر بدء اللعبة", "error");
            }
        } catch (e) {
            if (window.showGlobalToast) window.showGlobalToast("خطأ في السيرفر", "error");
        } finally {
            btn.disabled = false;
        }
    };

    async function onBoxClick(tileIndex) {
        if (!isBoxesActive) return;

        const tile = document.querySelector(`.box-tile[data-index="${tileIndex}"]`);
        if (tile.classList.contains('safe') || tile.classList.contains('bomb')) return;

        try {
            const res = await window.fetchAPI('/api/games/36boxes/reveal', {
                method: 'POST',
                body: JSON.stringify({ tile_index: tileIndex })
            });

            if (res && res.success) {
                if (res.outcome === 'safe') {
                    tile.classList.add('safe');
                    tile.innerHTML = '💎';
                    updateBoxesStatus(res.new_multiplier, res.current_profit);
                } else if (res.outcome === 'bomb') {
                    tile.classList.add('bomb');
                    tile.innerHTML = '💥';
                    handleBoxesGameOver(res.grid);
                }
            } else {
                if (window.showGlobalToast) window.showGlobalToast(res.error, "error");
            }
        } catch (e) {
            console.error(e);
        }
    }

    window.cashout36Boxes = async function () {
        if (!isBoxesActive) return;
        const btn = document.getElementById('btn-cashout-boxes');
        btn.disabled = true;

        try {
            const res = await window.fetchAPI('/api/games/36boxes/cashout', { method: 'POST' });
            if (res && res.success) {
                if (window.userState) window.userState.balance = res.new_balance;
                if (window.showGlobalToast) {
                    window.showGlobalToast(`💰 تم سحب ${res.payout} ZN بنجاح!`, "success");
                }
                resetBoxesUI();
            } else {
                if (window.showGlobalToast) window.showGlobalToast(res.error, "error");
            }
        } catch (e) {
            console.error(e);
        } finally {
            btn.disabled = false;
        }
    };

    function handleBoxesGameOver(fullGrid) {
        isBoxesActive = false;
        if (window.showGlobalToast) window.showGlobalToast("💥 انفلقت القنبلة! خسرت الرهان", "error");

        // كشف بقية الخريطة
        if (fullGrid) {
            document.querySelectorAll('.box-tile').forEach((tile, idx) => {
                if (fullGrid[idx] === 1) {
                    tile.classList.add('bomb');
                    tile.innerHTML = '💣';
                }
            });
        }

        setTimeout(() => resetBoxesUI(), 2500);
    }

    function resetBoxesUI() {
        isBoxesActive = false;
        document.getElementById('boxes-grid').classList.add('disabled');
        document.getElementById('boxes-setup-panel').style.display = 'block';
        document.getElementById('btn-cashout-boxes').classList.add('hidden');
        updateBoxesStatus(1.00, 0.00);
    }

    function updateBoxesStatus(mult, profit) {
        document.getElementById('boxes-current-mult').innerText = `x${parseFloat(mult).toFixed(2)}`;
        document.getElementById('boxes-current-profit').innerText = `${parseFloat(profit).toFixed(2)} ZN`;
    }

    function restoreBoxesSession(session) {
        isBoxesActive = true;
        document.getElementById('boxes-grid').classList.remove('disabled');
        document.getElementById('boxes-setup-panel').style.display = 'none';
        document.getElementById('btn-cashout-boxes').classList.remove('hidden');

        session.revealed.forEach(idx => {
            const tile = document.querySelector(`.box-tile[data-index="${idx}"]`);
            if (tile) {
                tile.classList.add('safe');
                tile.innerHTML = '💎';
            }
        });

        updateBoxesStatus(session.current_multiplier, session.current_profit);
    }

    // تشغيل التهيئة تلقائياً
    document.addEventListener("DOMContentLoaded", () => {
        if (document.getElementById('subview-arena')) {
            window.initGamesPage();
        }
    });
})();

(function initGoxeEngine() {
    let goxeState = {
        multipliers: [1.10, 1.30, 1.50, 1.80, 2.20, 2.70, 3.30, 3.90, 4.40, 5.00],
        currentFloor: 0,
        isPlaying: false,
        betAmount: 10,
        minBet: 10,
        maxBet: 10000
    };

    // جلب الإعدادات وجلسة اللاعب الحالية عند الفتح
    function loadGoxeConfig() {
        const initData = window.Telegram?.WebApp?.initData || '';
        
        fetch('/api/games/goxe/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                if (data.multipliers) goxeState.multipliers = data.multipliers;
                goxeState.minBet = data.min_bet || 10;
                goxeState.maxBet = data.max_bet || 10000;
                
                renderTower();

                if (data.active_session) {
                    goxeState.isPlaying = true;
                    goxeState.currentFloor = data.active_session.current_floor || 0;
                    goxeState.betAmount = data.active_session.bet_amount || 10;
                    document.getElementById('goxe-bet-amount').value = goxeState.betAmount;
                    updateUIState();
                }
            }
        })
        .catch(err => console.error("خطأ في جلب بيانات Goxe:", err));
    }

    // بناء شكل البرج في DOM
    function renderTower() {
        const towerEl = document.getElementById('goxe-tower');
        if (!towerEl) return;

        towerEl.innerHTML = '';

        for (let i = 0; i < 10; i++) {
            const floorNum = i + 1;
            const mult = goxeState.multipliers[i] || (1 + i * 0.4);

            const floorDiv = document.createElement('div');
            floorDiv.id = `goxe-floor-${floorNum}`;
            floorDiv.className = 'tower-floor';

            floorDiv.innerHTML = `
                <div class="floor-info">
                    <span class="floor-badge">دور ${floorNum}</span>
                    <span class="floor-multiplier">x${mult.toFixed(2)}</span>
                </div>
                <div class="floor-doors">
                    <button class="door-btn" onclick="chooseGoxeDoor(${floorNum}, 0)" disabled>🚪</button>
                    <button class="door-btn" onclick="chooseGoxeDoor(${floorNum}, 1)" disabled>🚪</button>
                    <button class="door-btn" onclick="chooseGoxeDoor(${floorNum}, 2)" disabled>🚪</button>
                </div>
            `;
            towerEl.appendChild(floorDiv);
        }
    }

    // تحديث الواجهة وحالة الأزرار والأدوار
    function updateUIState() {
        const mainBtn = document.getElementById('goxe-main-btn');
        const betInputGroup = document.getElementById('goxe-bet-group');

        for (let i = 1; i <= 10; i++) {
            const floorDiv = document.getElementById(`goxe-floor-${i}`);
            if (!floorDiv) continue;

            const doorBtns = floorDiv.querySelectorAll('.door-btn');

            if (i === goxeState.currentFloor + 1 && goxeState.isPlaying) {
                // الدور النشط الحالي المنوط بالاختيار
                floorDiv.className = 'tower-floor active-floor';
                doorBtns.forEach(btn => btn.disabled = false);
            } else if (i <= goxeState.currentFloor) {
                // الأدوار التي تم تخطيها بنجاح
                floorDiv.className = 'tower-floor passed-floor';
                doorBtns.forEach(btn => btn.disabled = true);
            } else {
                // الأدوار المتبقية
                floorDiv.className = 'tower-floor';
                doorBtns.forEach(btn => btn.disabled = true);
            }
        }

        if (goxeState.isPlaying) {
            betInputGroup.style.display = 'none';
            if (goxeState.currentFloor === 0) {
                mainBtn.className = 'action-btn start-btn';
                mainBtn.innerHTML = 'اختر أحد الأبواب في الدور الأول ⬆️';
                mainBtn.disabled = true;
            } else {
                const currentMult = goxeState.multipliers[goxeState.currentFloor - 1];
                const currentWinnings = (goxeState.betAmount * currentMult).toFixed(2);
                mainBtn.className = 'action-btn cashout-btn';
                mainBtn.innerHTML = `💰 انسحاب واقتطاع الأرباح (${currentWinnings} 🪙)`;
                mainBtn.disabled = false;
            }
        } else {
            betInputGroup.style.display = 'flex';
            mainBtn.className = 'action-btn start-btn';
            mainBtn.innerHTML = '🚀 بدء التسلق';
            mainBtn.disabled = false;
        }
    }

    // التعامل مع الضغط على زر التحكم الرئيسي (بدء / سحب)
    window.handleGoxeMainAction = function() {
        if (!goxeState.isPlaying) {
            // بدء جولة جديدة
            const betVal = parseFloat(document.getElementById('goxe-bet-amount').value || 10);
            const initData = window.Telegram?.WebApp?.initData || '';

            fetch('/api/games/goxe/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData, bet_amount: betVal })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    goxeState.isPlaying = true;
                    goxeState.currentFloor = 0;
                    goxeState.betAmount = betVal;
                    updateUIState();
                    if (typeof window.updateGlobalBalanceDisplay === 'function') {
                        window.updateGlobalBalanceDisplay();
                    }
                } else {
                    alert(data.error || "حدث خطأ أثناء بدء الجولة");
                }
            })
            .catch(err => console.error("خطأ في بدء الجولة:", err));
        } else {
            // انسحاب واقتطاع الأرباح
            const initData = window.Telegram?.WebApp?.initData || '';

            fetch('/api/games/goxe/cashout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert(`🎉 مبروك! تم سحب ${data.winnings.toFixed(2)} عملة بنجاح!`);
                    goxeState.isPlaying = false;
                    goxeState.currentFloor = 0;
                    updateUIState();
                    if (typeof window.updateGlobalBalanceDisplay === 'function') {
                        window.updateGlobalBalanceDisplay();
                    }
                } else {
                    alert(data.error || "حدث خطأ أثناء الانسحاب");
                }
            })
            .catch(err => console.error("خطأ في السحب:", err));
        }
    };

    // اختيار باب من الأبواب الثلاثة
    window.chooseGoxeDoor = function(floorNum, doorIndex) {
        if (!goxeState.isPlaying || floorNum !== goxeState.currentFloor + 1) return;

        const initData = window.Telegram?.WebApp?.initData || '';

        fetch('/api/games/goxe/climb', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData, door_index: doorIndex })
        })
        .then(res => res.json())
        .then(data => {
            if (data.success) {
                if (data.result === 'bomb') {
                    alert(data.message || "💥 للأسف! كانت قنبلة وخسرت الجولة.");
                    goxeState.isPlaying = false;
                    goxeState.currentFloor = 0;
                } else if (data.result === 'max_win') {
                    alert(data.message || "🎉 مبروك! تم تحقيق أقصى مضاعف وسحب الأرباح تلقائياً!");
                    goxeState.isPlaying = false;
                    goxeState.currentFloor = 0;
                } else {
                    goxeState.currentFloor = data.current_floor;
                }
                updateUIState();
                if (typeof window.updateGlobalBalanceDisplay === 'function') {
                    window.updateGlobalBalanceDisplay();
                }
            } else {
                alert(data.error || "حدث خطأ أثناء الصعود");
            }
        })
        .catch(err => console.error("خطأ في تحديد الباب:", err));
    };

    // زر تحديد قيمة الرهان السريعة
    window.setGoxeBet = function(val) {
        if (!goxeState.isPlaying) {
            document.getElementById('goxe-bet-amount').value = val;
        }
    };

    // تشغيل التهيئة عند التحميل
    loadGoxeConfig();
})();

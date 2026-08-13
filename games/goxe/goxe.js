(function initGoxeEngine() {
    let goxeState = {
        multipliers: [1.10, 1.30, 1.50, 1.80, 2.20, 2.70, 3.30, 3.90, 4.40, 5.00],
        currentFloor: 0,
        isPlaying: false,
        betAmount: 100, // الافتراضي 100
        minBet: 10,
        maxBet: 10000
    };

    // رسم البرج فوراً عند فتح اللعبة
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

    // جلب البيانات والإعدادات من السيرفر
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
                
                renderTower(); // إعادة رسم الأدوار في حال تغيرت المضاعفات من السيرفر

                if (data.active_session) {
                    goxeState.isPlaying = true;
                    goxeState.currentFloor = data.active_session.current_floor || 0;
                    goxeState.betAmount = data.active_session.bet_amount || 100;
                    selectGoxeBet(goxeState.betAmount);
                    updateUIState();
                }
            }
        })
        .catch(err => console.error("خطأ في جلب بيانات Goxe:", err));
    }

    // تحديد مبلغ الرهان من القائمة الثابتة
    window.selectGoxeBet = function(amount) {
        if (goxeState.isPlaying) return;

        goxeState.betAmount = amount;

        // تحديث تنسيق الأزرار
        const chips = document.querySelectorAll('.bet-chip');
        chips.forEach(chip => {
            chip.classList.remove('selected');
            if (chip.textContent.includes(amount.toString())) {
                chip.classList.add('selected');
            }
        });

        // تحديث نص زر التفعيل
        const mainBtn = document.getElementById('goxe-main-btn');
        if (mainBtn && !goxeState.isPlaying) {
            mainBtn.innerHTML = `🚀 بدء التسلق (${amount} ZN)`;
        }
    };

    // تحديث حالات الواجهة
    function updateUIState() {
        const mainBtn = document.getElementById('goxe-main-btn');
        const betSection = document.getElementById('goxe-bet-section');

        for (let i = 1; i <= 10; i++) {
            const floorDiv = document.getElementById(`goxe-floor-${i}`);
            if (!floorDiv) continue;

            const doorBtns = floorDiv.querySelectorAll('.door-btn');

            if (i === goxeState.currentFloor + 1 && goxeState.isPlaying) {
                // الدور النشط
                floorDiv.className = 'tower-floor active-floor';
                doorBtns.forEach(btn => btn.disabled = false);
            } else if (i <= goxeState.currentFloor) {
                // الدور المتخطى
                floorDiv.className = 'tower-floor passed-floor';
                doorBtns.forEach(btn => btn.disabled = true);
            } else {
                // الأدوار القادمة
                floorDiv.className = 'tower-floor';
                doorBtns.forEach(btn => btn.disabled = true);
            }
        }

        if (goxeState.isPlaying) {
            betSection.style.display = 'none';
            if (goxeState.currentFloor === 0) {
                mainBtn.className = 'action-btn start-btn';
                mainBtn.innerHTML = 'اختر أحد الأبواب في الدور الأول ⬆️';
                mainBtn.disabled = true;
            } else {
                const currentMult = goxeState.multipliers[goxeState.currentFloor - 1];
                const currentWinnings = (goxeState.betAmount * currentMult).toFixed(2);
                mainBtn.className = 'action-btn cashout-btn';
                mainBtn.innerHTML = `💰 انسحاب واقتطاع الأرباح (${currentWinnings} ZN)`;
                mainBtn.disabled = false;
            }
        } else {
            betSection.style.display = 'block';
            mainBtn.className = 'action-btn start-btn';
            mainBtn.innerHTML = `🚀 بدء التسلق (${goxeState.betAmount} ZN)`;
            mainBtn.disabled = false;
        }
    }

    // زر التحكم الرئيسي
    window.handleGoxeMainAction = function() {
        if (!goxeState.isPlaying) {
            const initData = window.Telegram?.WebApp?.initData || '';

            fetch('/api/games/goxe/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData, bet_amount: goxeState.betAmount })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    goxeState.isPlaying = true;
                    goxeState.currentFloor = 0;
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
            // طلب اقتطاع الأرباح
            const initData = window.Telegram?.WebApp?.initData || '';

            fetch('/api/games/goxe/cashout', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert(`🎉 مبروك! تم سحب ${data.winnings.toFixed(2)} ZN بنجاح!`);
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

    // اختيارات الأبواب
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

    // تشغيل الرسم الفوري ثم جلب الإعدادات
    renderTower();
    loadGoxeConfig();
})();

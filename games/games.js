(function initGoxeEngine() {
    let goxeState = {
        multipliers: [1.10, 1.30, 1.50, 1.80, 2.20, 2.70, 3.30, 3.90, 4.40, 5.00],
        currentFloor: 0,
        isPlaying: false,
        betAmount: 100,
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

    // جلب البيانات والإعدادات من السيرفر باستخدام fetchAPI
    async function loadGoxeConfig() {
        try {
            if (typeof window.fetchAPI !== 'function') return;
            
            const data = await window.fetchAPI('/api/games/goxe/config', 'POST');
            if (data && data.success) {
                if (data.multipliers) goxeState.multipliers = data.multipliers;
                goxeState.minBet = data.min_bet || 10;
                goxeState.maxBet = data.max_bet || 10000;
                
                renderTower();

                if (data.active_session) {
                    goxeState.isPlaying = true;
                    goxeState.currentFloor = data.active_session.current_floor || 0;
                    goxeState.betAmount = data.active_session.bet_amount || 100;
                    selectGoxeBet(goxeState.betAmount);
                    updateUIState();
                }
            }
        } catch (err) {
            console.error("خطأ في جلب بيانات Goxe:", err);
            renderTower();
        }
    }

    // تحديد مبلغ الرهان الدقيق ومنع الخربطة
    window.selectGoxeBet = function(amount) {
        if (goxeState.isPlaying) return;

        goxeState.betAmount = parseInt(amount);

        // التحديد الدقيق باستخدام data-amount
        const chips = document.querySelectorAll('.bet-chip');
        chips.forEach(chip => {
            const chipVal = parseInt(chip.getAttribute('data-amount'));
            if (chipVal === goxeState.betAmount) {
                chip.classList.add('selected');
            } else {
                chip.classList.remove('selected');
            }
        });

        const mainBtn = document.getElementById('goxe-main-btn');
        if (mainBtn && !goxeState.isPlaying) {
            mainBtn.innerHTML = `🚀 بدء التسلق (${goxeState.betAmount} ZN)`;
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
                floorDiv.className = 'tower-floor active-floor';
                doorBtns.forEach(btn => btn.disabled = false);
            } else if (i <= goxeState.currentFloor) {
                floorDiv.className = 'tower-floor passed-floor';
                doorBtns.forEach(btn => btn.disabled = true);
            } else {
                floorDiv.className = 'tower-floor';
                doorBtns.forEach(btn => btn.disabled = true);
            }
        }

        if (goxeState.isPlaying) {
            if (betSection) betSection.style.display = 'none';
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
            if (betSection) betSection.style.display = 'block';
            mainBtn.className = 'action-btn start-btn';
            mainBtn.innerHTML = `🚀 بدء التسلق (${goxeState.betAmount} ZN)`;
            mainBtn.disabled = false;
        }
    }

    // زر التحكم الرئيسي (بدء / انسحاب)
    window.handleGoxeMainAction = async function() {
        if (!goxeState.isPlaying) {
            // التحقق من الرصيد أولاً
            const currentBal = parseFloat(window.userState?.balance || 0);
            if (currentBal < goxeState.betAmount) {
                alert(`رصيدك غير كافٍ! رصيدك الحالي: ${currentBal.toFixed(2)} ZN`);
                return;
            }

            try {
                const data = await window.fetchAPI('/api/games/goxe/start', 'POST', {
                    bet_amount: goxeState.betAmount
                });

                if (data && data.success) {
                    goxeState.isPlaying = true;
                    goxeState.currentFloor = 0;
                    updateUIState();
                } else {
                    alert(data?.error || data?.message || "حدث خطأ أثناء بدء الجولة");
                }
            } catch (err) {
                alert("تعذر بدء الجولة: " + (err.message || "خطأ في الاتصال بالسيرفر"));
            }
        } else {
            // اقتطاع الأرباح
            try {
                const data = await window.fetchAPI('/api/games/goxe/cashout', 'POST');

                if (data && data.success) {
                    const winVal = parseFloat(data.winnings || 0).toFixed(2);
                    alert(`🎉 مبروك! تم سحب ${winVal} ZN بنجاح!`);
                    goxeState.isPlaying = false;
                    goxeState.currentFloor = 0;
                    updateUIState();
                } else {
                    alert(data?.error || "حدث خطأ أثناء الانسحاب");
                }
            } catch (err) {
                alert("تعذر الانسحاب: " + (err.message || "خطأ في الاتصال"));
            }
        }
    };

    // اختيارات الأبواب
    window.chooseGoxeDoor = async function(floorNum, doorIndex) {
        if (!goxeState.isPlaying || floorNum !== goxeState.currentFloor + 1) return;

        try {
            const data = await window.fetchAPI('/api/games/goxe/climb', 'POST', {
                door_index: doorIndex
            });

            if (data && data.success) {
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
            } else {
                alert(data?.error || "حدث خطأ أثناء الصعود");
            }
        } catch (err) {
            alert("خطأ أثناء الاتصال: " + (err.message || "تعذر اختيار الباب"));
        }
    };

    // تشغيل الرسم الجاهز
    renderTower();
    loadGoxeConfig();
})();

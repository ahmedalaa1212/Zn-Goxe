(function initGoxeEngine() {
    let goxeState = {
        multipliers: [1.10, 1.30, 1.50, 1.80, 2.20, 2.70, 3.30, 3.90, 4.40, 5.00],
        currentFloor: 0,
        isPlaying: false,
        betAmount: 100,
        minBet: 10,
        maxBet: 10000
    };

    // دالة تحديث الرصيد اللحظي في جميع عناصر الواجهة
    function updateGlobalBalance(newBal) {
        if (newBal === undefined || newBal === null) return;
        const balNum = parseFloat(newBal);
        if (isNaN(balNum)) return;

        // 1. تحديث الكائن العام في الذاكرة
        if (!window.userState) window.userState = {};
        window.userState.balance = balNum;

        // 2. تحديث عناصر الرصيد الشائعة في الصفحة
        const balIds = ['user-balance', 'balance', 'user-coins', 'user-balance-val', 'header-balance'];
        balIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerText = balNum.toFixed(2);
        });

        const balClasses = document.querySelectorAll('.user-balance');
        balClasses.forEach(el => {
            el.innerText = balNum.toFixed(2);
        });

        // 3. استدعاء دوال التحديث المباشرة إن وجدت في التطبيق
        if (typeof window.updateUserBalance === 'function') {
            window.updateUserBalance(balNum);
        } else if (typeof window.updateBalance === 'function') {
            window.updateBalance(balNum);
        }
    }

    // دالة طلب آمنة لمنع أخطاء Unexpected token '<'
    async function safeFetch(endpoint, method = 'POST', bodyData = null) {
        try {
            if (typeof window.fetchAPI === 'function') {
                return await window.fetchAPI(endpoint, method, bodyData);
            }

            const headers = { 'Content-Type': 'application/json' };
            const initData = window.Telegram?.WebApp?.initData || '';
            if (initData) headers['X-Telegram-Init-Data'] = initData;

            const res = await fetch(endpoint, {
                method: method,
                headers: headers,
                body: bodyData ? JSON.stringify(bodyData) : null
            });

            const contentType = res.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                throw new Error('تعذر الاتصال بالسيرفر، تأكد من صحة الرابط.');
            }

            return await res.json();
        } catch (err) {
            throw err;
        }
    }

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
    async function loadGoxeConfig() {
        try {
            const data = await safeFetch('/api/games/goxe/config', 'POST');
            if (data && data.success) {
                if (data.multipliers) goxeState.multipliers = data.multipliers;
                goxeState.minBet = data.min_bet || 10;
                goxeState.maxBet = data.max_bet || 10000;
                
                if (data.current_balance !== undefined) {
                    updateGlobalBalance(data.current_balance);
                }

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
                const data = await safeFetch('/api/games/goxe/start', 'POST', {
                    bet_amount: goxeState.betAmount
                });

                if (data && data.success) {
                    goxeState.isPlaying = true;
                    goxeState.currentFloor = 0;
                    
                    // تحديث الرصيد فوراً في الواجهة بعد الخصم
                    if (data.new_balance !== undefined) {
                        updateGlobalBalance(data.new_balance);
                    }
                    
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
                const data = await safeFetch('/api/games/goxe/cashout', 'POST');

                if (data && data.success) {
                    const winVal = parseFloat(data.winnings || 0).toFixed(2);
                    
                    // تحديث الرصيد فوراً في الواجهة بعد إضافة الأرباح
                    if (data.new_balance !== undefined) {
                        updateGlobalBalance(data.new_balance);
                    }

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
            const data = await safeFetch('/api/games/goxe/climb', 'POST', {
                door_index: doorIndex
            });

            if (data && data.success) {
                if (data.result === 'bomb') {
                    if (data.current_balance !== undefined) {
                        updateGlobalBalance(data.current_balance);
                    }
                    alert(data.message || "💥 للأسف! كانت قنبلة وخسرت الجولة.");
                    goxeState.isPlaying = false;
                    goxeState.currentFloor = 0;
                } else if (data.result === 'max_win') {
                    if (data.new_balance !== undefined) {
                        updateGlobalBalance(data.new_balance);
                    }
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

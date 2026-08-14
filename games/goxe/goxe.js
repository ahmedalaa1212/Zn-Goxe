(function initGoxeEngine() {
    let goxeState = {
        multipliers: [1.10, 1.30, 1.50, 1.80, 2.20, 2.70, 3.30, 3.90, 4.40, 5.00],
        currentFloor: 0,
        isPlaying: false,
        betAmount: null,
        allowedBetOptions: [],
        minBet: 10,
        maxBet: 10000,
        isProcessing: false
    };

    // تحديث الرصيد المباشر في جميع العناصر
    function updateGlobalBalance(newBal) {
        if (newBal === undefined || newBal === null) return;
        const balNum = parseFloat(newBal);
        if (isNaN(balNum)) return;

        if (!window.userState) window.userState = {};
        window.userState.balance = balNum;

        const balIds = ['user-balance', 'balance', 'user-coins', 'user-balance-val', 'header-balance'];
        balIds.forEach(id => {
            const el = document.getElementById(id);
            if (el) el.innerText = balNum.toFixed(2);
        });

        const balClasses = document.querySelectorAll('.user-balance');
        balClasses.forEach(el => {
            el.innerText = balNum.toFixed(2);
        });

        if (typeof window.updateUserBalance === 'function') {
            window.updateUserBalance(balNum);
        } else if (typeof window.updateBalance === 'function') {
            window.updateBalance(balNum);
        }
    }

    // دالة طلب آمنة
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

    // دالة تصفير وتنظيف البرج بالكامل ومسح الجواهر والقنابل القديمة
    function resetTowerUI() {
        for (let i = 1; i <= 10; i++) {
            const floorDiv = document.getElementById(`goxe-floor-${i}`);
            if (!floorDiv) continue;

            floorDiv.className = 'tower-floor';
            const doorBtns = floorDiv.querySelectorAll('.door-btn');
            doorBtns.forEach(btn => {
                btn.className = 'door-btn';
                btn.innerHTML = '🚪';
                btn.disabled = true;
            });
        }
    }

    // رسم البرج الأساسي
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
                    <div class="door-wrapper"><button class="door-btn" id="door-${floorNum}-0" onclick="chooseGoxeDoor(${floorNum}, 0)" disabled>🚪</button></div>
                    <div class="door-wrapper"><button class="door-btn" id="door-${floorNum}-1" onclick="chooseGoxeDoor(${floorNum}, 1)" disabled>🚪</button></div>
                    <div class="door-wrapper"><button class="door-btn" id="door-${floorNum}-2" onclick="chooseGoxeDoor(${floorNum}, 2)" disabled>🚪</button></div>
                </div>
            `;
            towerEl.appendChild(floorDiv);
        }
    }

    // بناء خيارات الرهانات المتاحة ديناميكياً بدون وميض
    function renderBetChips(allowedOptions) {
        if (!allowedOptions || !Array.isArray(allowedOptions) || allowedOptions.length === 0) return;
        const grid = document.getElementById('goxe-bet-grid');
        if (!grid) return;

        goxeState.allowedBetOptions = allowedOptions;

        // تحديد الخيار الافتراضي إذا لم يكن محدداً أو لو غير متوفر في الخيارات
        if (!goxeState.betAmount || !allowedOptions.includes(goxeState.betAmount)) {
            goxeState.betAmount = allowedOptions[0];
        }

        grid.innerHTML = '';
        allowedOptions.forEach(opt => {
            const isSelected = (opt === goxeState.betAmount) ? 'selected' : '';
            grid.innerHTML += `<div class="bet-chip ${isSelected}" data-amount="${opt}" onclick="selectGoxeBet(${opt})">${opt} ZN</div>`;
        });
    }

    // جلب الإعدادات عند البداية
    async function loadGoxeConfig() {
        try {
            renderTower();
            const data = await safeFetch('/api/games/goxe/config', 'POST');
            
            if (data && data.success) {
                if (data.multipliers) goxeState.multipliers = data.multipliers;
                goxeState.minBet = data.min_bet || 10;
                goxeState.maxBet = data.max_bet || 10000;
                
                if (data.allowed_bet_options && data.allowed_bet_options.length > 0) {
                    renderBetChips(data.allowed_bet_options);
                }

                if (data.current_balance !== undefined) {
                    updateGlobalBalance(data.current_balance);
                }

                renderTower();

                if (data.active_session) {
                    goxeState.isPlaying = true;
                    goxeState.currentFloor = data.active_session.current_floor || 0;
                    goxeState.betAmount = data.active_session.bet_amount || goxeState.betAmount;
                    selectGoxeBet(goxeState.betAmount);
                    updateUIState();
                } else {
                    goxeState.isPlaying = false;
                    resetTowerUI();
                    updateUIState();
                }
            }
        } catch (err) {
            console.error("خطأ في جلب بيانات Goxe:", err);
            renderTower();
            updateUIState();
        }
    }

    // تحديد الرهان
    window.selectGoxeBet = function(amount) {
        if (goxeState.isPlaying) return;

        goxeState.betAmount = parseInt(amount);

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
            mainBtn.disabled = false;
        }
    };

    // تحديث حالات العناصر
    function updateUIState() {
        const mainBtn = document.getElementById('goxe-main-btn');
        const betSection = document.getElementById('goxe-bet-section');

        if (!goxeState.isPlaying) {
            resetTowerUI();
            if (betSection) betSection.style.display = 'block';
            if (mainBtn) {
                mainBtn.className = 'action-btn start-btn';
                const curBet = goxeState.betAmount || 100;
                mainBtn.innerHTML = `🚀 بدء التسلق (${curBet} ZN)`;
                mainBtn.disabled = false;
            }
            return;
        }

        if (betSection) betSection.style.display = 'none';

        for (let i = 1; i <= 10; i++) {
            const floorDiv = document.getElementById(`goxe-floor-${i}`);
            if (!floorDiv) continue;

            const doorBtns = floorDiv.querySelectorAll('.door-btn');

            if (i === goxeState.currentFloor + 1) {
                floorDiv.className = 'tower-floor active-floor';
                doorBtns.forEach(btn => {
                    btn.disabled = false;
                    if (!btn.classList.contains('door-safe') && !btn.classList.contains('door-bomb')) {
                        btn.className = 'door-btn';
                        btn.innerHTML = '🚪';
                    }
                });
            } else if (i <= goxeState.currentFloor) {
                floorDiv.className = 'tower-floor passed-floor';
                doorBtns.forEach(btn => btn.disabled = true);
            } else {
                floorDiv.className = 'tower-floor';
                doorBtns.forEach(btn => {
                    btn.disabled = true;
                    btn.className = 'door-btn';
                    btn.innerHTML = '🚪';
                });
            }
        }

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
    }

    // بدء / انسحاب
    window.handleGoxeMainAction = async function() {
        if (goxeState.isProcessing) return;

        if (!goxeState.isPlaying) {
            const currentBal = parseFloat(window.userState?.balance || 0);
            if (currentBal < goxeState.betAmount) {
                alert(`رصيدك غير كافٍ! رصيدك الحالي: ${currentBal.toFixed(2)} ZN`);
                return;
            }

            goxeState.isProcessing = true;
            const mainBtn = document.getElementById('goxe-main-btn');
            if (mainBtn) mainBtn.disabled = true;

            try {
                const data = await safeFetch('/api/games/goxe/start', 'POST', {
                    bet_amount: goxeState.betAmount
                });

                if (data && data.success) {
                    goxeState.isPlaying = true;
                    goxeState.currentFloor = 0;
                    resetTowerUI();

                    if (data.new_balance !== undefined) {
                        updateGlobalBalance(data.new_balance);
                    }
                    
                    updateUIState();
                } else {
                    alert(data?.error || data?.message || "حدث خطأ أثناء بدء الجولة");
                    if (mainBtn) mainBtn.disabled = false;
                }
            } catch (err) {
                alert("تعذر بدء الجولة: " + (err.message || "خطأ في الاتصال بالسيرفر"));
                if (mainBtn) mainBtn.disabled = false;
            } finally {
                goxeState.isProcessing = false;
            }
        } else {
            goxeState.isProcessing = true;
            const mainBtn = document.getElementById('goxe-main-btn');
            if (mainBtn) mainBtn.disabled = true;

            try {
                const data = await safeFetch('/api/games/goxe/cashout', 'POST');

                if (data && data.success) {
                    const winVal = parseFloat(data.winnings || 0).toFixed(2);
                    
                    if (data.new_balance !== undefined) {
                        updateGlobalBalance(data.new_balance);
                    }

                    alert(`🎉 مبروك! تم سحب ${winVal} ZN بنجاح!`);
                    goxeState.isPlaying = false;
                    goxeState.currentFloor = 0;
                    resetTowerUI();
                    updateUIState();
                } else {
                    alert(data?.error || "حدث خطأ أثناء الانسحاب");
                    if (mainBtn) mainBtn.disabled = false;
                }
            } catch (err) {
                alert("تعذر الانسحاب: " + (err.message || "خطأ في الاتصال"));
                if (mainBtn) mainBtn.disabled = false;
            } finally {
                goxeState.isProcessing = false;
            }
        }
    };

    // اختيار الباب
    window.chooseGoxeDoor = async function(floorNum, doorIndex) {
        if (!goxeState.isPlaying || floorNum !== goxeState.currentFloor + 1 || goxeState.isProcessing) return;

        goxeState.isProcessing = true;
        const doorBtn = document.getElementById(`door-${floorNum}-${doorIndex}`);
        
        if (doorBtn) {
            doorBtn.classList.add('door-opening');
        }

        try {
            const data = await safeFetch('/api/games/goxe/climb', 'POST', {
                door_index: doorIndex
            });

            if (data && data.success) {
                if (data.result === 'bomb') {
                    if (doorBtn) {
                        doorBtn.classList.add('door-bomb');
                        doorBtn.innerHTML = '💥';
                    }

                    const towerEl = document.getElementById('goxe-tower');
                    if (towerEl) {
                        towerEl.classList.add('shake-tower');
                        setTimeout(() => towerEl.classList.remove('shake-tower'), 500);
                    }

                    if (data.current_balance !== undefined) {
                        updateGlobalBalance(data.current_balance);
                    }

                    setTimeout(() => {
                        alert(data.message || "💥 للأسف! كانت قنبلة وخسرت الجولة.");
                        goxeState.isPlaying = false;
                        goxeState.currentFloor = 0;
                        resetTowerUI();
                        updateUIState();
                    }, 500);

                } else if (data.result === 'max_win') {
                    if (doorBtn) {
                        doorBtn.classList.add('door-safe');
                        doorBtn.innerHTML = '💎';
                    }

                    if (data.new_balance !== undefined) {
                        updateGlobalBalance(data.new_balance);
                    }

                    setTimeout(() => {
                        alert(data.message || "🎉 مبروك! تم تحقيق أقصى مضاعف وسحب الأرباح تلقائياً!");
                        goxeState.isPlaying = false;
                        goxeState.currentFloor = 0;
                        resetTowerUI();
                        updateUIState();
                    }, 500);

                } else {
                    if (doorBtn) {
                        doorBtn.classList.add('door-safe');
                        doorBtn.innerHTML = '💎';
                    }

                    goxeState.currentFloor = data.current_floor;

                    setTimeout(() => {
                        updateUIState();
                    }, 350);
                }
            } else {
                alert(data?.error || "حدث خطأ أثناء الصعود");
            }
        } catch (err) {
            alert("خطأ أثناء الاتصال: " + (err.message || "تعذر اختيار الباب"));
        } finally {
            goxeState.isProcessing = false;
        }
    };

    // تشغيل التهيئة
    loadGoxeConfig();
})();

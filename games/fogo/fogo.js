(function initFogoEngine() {
    let fogoState = {
        isPlaying: false,
        betAmount: 50,
        minesCount: 3,
        shieldEnabled: false,
        shieldActive: false,
        currentFloor: 0,
        currentMultiplier: 1.0,
        allowedBetOptions: [50, 100, 300, 500, 1000, 8000],
        openedTiles: [],
        isProcessing: false
    };

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

            return await res.json();
        } catch (err) {
            throw err;
        }
    }

    function renderGrid() {
        const gridEl = document.getElementById('fogo-grid');
        if (!gridEl) return;

        gridEl.innerHTML = '';
        for (let i = 0; i < 16; i++) {
            const tile = document.createElement('button');
            tile.className = 'fogo-tile';
            tile.id = `fogo-tile-${i}`;
            tile.setAttribute('onclick', `revealFogoTile(${i})`);
            tile.disabled = true;
            tile.innerHTML = '❓';
            gridEl.appendChild(tile);
        }
    }

    function renderBetChips(allowedOptions) {
        if (!allowedOptions || !Array.isArray(allowedOptions)) return;
        const grid = document.getElementById('fogo-bet-grid');
        if (!grid) return;

        fogoState.allowedBetOptions = allowedOptions;
        if (!allowedOptions.includes(fogoState.betAmount)) {
            fogoState.betAmount = allowedOptions[0];
        }

        grid.innerHTML = '';
        allowedOptions.forEach(opt => {
            const isSelected = (opt === fogoState.betAmount) ? 'selected' : '';
            grid.innerHTML += `<div class="bet-chip ${isSelected}" data-amount="${opt}" onclick="selectFogoBet(${opt})">${opt} ZN</div>`;
        });
    }

    window.selectFogoMines = function(count) {
        if (fogoState.isPlaying) return;
        fogoState.minesCount = parseInt(count);

        document.querySelectorAll('.mine-opt-btn').forEach(btn => {
            if (parseInt(btn.getAttribute('data-mines')) === fogoState.minesCount) {
                btn.classList.add('selected');
            } else {
                btn.classList.remove('selected');
            }
        });

        const maxMults = { 3: 'x5.00', 4: 'x10.00', 5: 'x15.00', 6: 'x20.00' };
        const hint = document.getElementById('fogo-max-mult-hint');
        if (hint) hint.innerText = `حد أقصى ${maxMults[fogoState.minesCount] || 'x5.00'}`;
    };

    window.toggleFogoShield = function(checked) {
        if (fogoState.isPlaying) return;
        fogoState.shieldEnabled = checked;
        updateShieldStatusUI(checked ? 'on' : 'off');
    };

    function updateShieldStatusUI(status) {
        const el = document.getElementById('fogo-shield-status');
        if (!el) return;

        if (status === 'on') {
            el.className = 'status-val shield-on';
            el.innerText = '🛡️ نشط';
        } else if (status === 'broken') {
            el.className = 'status-val shield-broken';
            el.innerText = '💥 محطم';
        } else {
            el.className = 'status-val shield-off';
            el.innerText = 'غير مفعل';
        }
    }

    window.selectFogoBet = function(amount) {
        if (fogoState.isPlaying) return;
        fogoState.betAmount = parseInt(amount);

        document.querySelectorAll('.bet-chip').forEach(chip => {
            if (parseInt(chip.getAttribute('data-amount')) === fogoState.betAmount) {
                chip.classList.add('selected');
            } else {
                chip.classList.remove('selected');
            }
        });

        const mainBtn = document.getElementById('fogo-main-btn');
        if (mainBtn && !fogoState.isPlaying) {
            mainBtn.innerHTML = `🚀 بدء التعدين (${fogoState.betAmount} ZN)`;
            mainBtn.disabled = false;
        }
    };

    async function loadFogoConfig() {
        try {
            renderGrid();
            const data = await safeFetch('/api/games/fogo/config', 'POST');

            if (data && data.success) {
                if (data.allowed_bet_options) renderBetChips(data.allowed_bet_options);
                if (data.current_balance !== undefined) updateGlobalBalance(data.current_balance);

                if (data.active_session) {
                    fogoState.isPlaying = true;
                    fogoState.minesCount = data.active_session.mines_count || 3;
                    fogoState.betAmount = data.active_session.bet_amount || 50;
                    fogoState.shieldEnabled = data.active_session.shield_enabled || false;
                    fogoState.shieldActive = data.active_session.shield_active || false;
                    fogoState.openedTiles = data.active_session.opened_tiles || [];
                    fogoState.currentMultiplier = data.active_session.current_multiplier || 1.0;
                    
                    restoreActiveSessionUI();
                } else {
                    fogoState.isPlaying = false;
                    updateUIState();
                }
            }
        } catch (err) {
            console.error("خطأ في تحميل إعدادات fuego:", err);
            updateUIState();
        }
    }

    function restoreActiveSessionUI() {
        document.getElementById('fogo-setup-panel').style.display = 'none';
        
        fogoState.openedTiles.forEach(idx => {
            const tile = document.getElementById(`fogo-tile-${idx}`);
            if (tile) {
                tile.className = 'fogo-tile reveal-gold';
                tile.innerHTML = '<span class="coin-gold-icon">🪙</span>';
                tile.disabled = true;
            }
        });

        for (let i = 0; i < 16; i++) {
            if (!fogoState.openedTiles.includes(i)) {
                const tile = document.getElementById(`fogo-tile-${i}`);
                if (tile) tile.disabled = false;
            }
        }

        if (fogoState.shieldActive) {
            updateShieldStatusUI('on');
        } else if (fogoState.shieldEnabled && !fogoState.shieldActive) {
            updateShieldStatusUI('broken');
        } else {
            updateShieldStatusUI('off');
        }

        updateStatusValues();
        updateMainButton();
    }

    function updateStatusValues() {
        const multEl = document.getElementById('fogo-multiplier-val');
        const winEl = document.getElementById('fogo-winnings-val');

        if (multEl) multEl.innerText = `x${fogoState.currentMultiplier.toFixed(2)}`;
        if (winEl) {
            const winnings = fogoState.betAmount * fogoState.currentMultiplier;
            winEl.innerText = `${winnings.toFixed(2)} ZN`;
        }
    }

    function updateMainButton() {
        const mainBtn = document.getElementById('fogo-main-btn');
        if (!mainBtn) return;

        if (!fogoState.isPlaying) {
            mainBtn.className = 'action-btn start-btn';
            mainBtn.innerHTML = `🚀 بدء التعدين (${fogoState.betAmount} ZN)`;
            mainBtn.disabled = false;
        } else {
            if (fogoState.openedTiles.length === 0) {
                mainBtn.className = 'action-btn start-btn';
                mainBtn.innerHTML = 'اختر أول مربع استكشاف 👆';
                mainBtn.disabled = true;
            } else {
                const winnings = (fogoState.betAmount * fogoState.currentMultiplier).toFixed(2);
                mainBtn.className = 'action-btn cashout-btn';
                mainBtn.innerHTML = `💰 اقتطاع الأرباح (${winnings} ZN)`;
                mainBtn.disabled = false;
            }
        }
    }

    function updateUIState() {
        const setupPanel = document.getElementById('fogo-setup-panel');
        if (!fogoState.isPlaying) {
            if (setupPanel) setupPanel.style.display = 'block';
            renderGrid();
            fogoState.openedTiles = [];
            fogoState.currentMultiplier = 1.0;
            updateStatusValues();
            updateShieldStatusUI(fogoState.shieldEnabled ? 'on' : 'off');
        } else {
            if (setupPanel) setupPanel.style.display = 'none';
        }
        updateMainButton();
    }

    window.handleFogoMainAction = async function() {
        if (fogoState.isProcessing) return;

        if (!fogoState.isPlaying) {
            const currentBal = parseFloat(window.userState?.balance || 0);
            if (currentBal < fogoState.betAmount) {
                alert(`رصيدك غير كافٍ! رصيدك الحالي: ${currentBal.toFixed(2)} ZN`);
                return;
            }

            fogoState.isProcessing = true;
            document.getElementById('fogo-main-btn').disabled = true;

            try {
                const data = await safeFetch('/api/games/fogo/start', 'POST', {
                    bet_amount: fogoState.betAmount,
                    mines_count: fogoState.minesCount,
                    shield_enabled: fogoState.shieldEnabled
                });

                if (data && data.success) {
                    fogoState.isPlaying = true;
                    fogoState.openedTiles = [];
                    fogoState.currentMultiplier = 1.0;
                    fogoState.shieldActive = data.shield_active;

                    if (data.new_balance !== undefined) updateGlobalBalance(data.new_balance);

                    updateUIState();
                    for (let i = 0; i < 16; i++) {
                        const tile = document.getElementById(`fogo-tile-${i}`);
                        if (tile) tile.disabled = false;
                    }
                } else {
                    alert(data?.error || "حدث خطأ أثناء البدء");
                    document.getElementById('fogo-main-btn').disabled = false;
                }
            } catch (err) {
                alert("تعذر الاتصال بالسيرفر");
                document.getElementById('fogo-main-btn').disabled = false;
            } finally {
                fogoState.isProcessing = false;
            }
        } else {
            // اقتطاع الأرباح
            fogoState.isProcessing = true;
            document.getElementById('fogo-main-btn').disabled = true;

            try {
                const data = await safeFetch('/api/games/fogo/cashout', 'POST');

                if (data && data.success) {
                    if (data.new_balance !== undefined) updateGlobalBalance(data.new_balance);

                    alert(`🎉 مبروك! تم اقتطاع أرباحك بمبلغ ${parseFloat(data.winnings).toFixed(2)} ZN بنجاح!`);
                    fogoState.isPlaying = false;
                    updateUIState();
                } else {
                    alert(data?.error || "حدث خطأ أثناء السحب");
                    document.getElementById('fogo-main-btn').disabled = false;
                }
            } catch (err) {
                alert("خطأ في الاتصال");
                document.getElementById('fogo-main-btn').disabled = false;
            } finally {
                fogoState.isProcessing = false;
            }
        }
    };

    window.revealFogoTile = async function(tileIndex) {
        if (!fogoState.isPlaying || fogoState.isProcessing || fogoState.openedTiles.includes(tileIndex)) return;

        fogoState.isProcessing = true;
        const tile = document.getElementById(`fogo-tile-${tileIndex}`);
        if (tile) tile.disabled = true;

        try {
            const data = await safeFetch('/api/games/fogo/reveal', 'POST', {
                tile_index: tileIndex
            });

            if (data && data.success) {
                if (data.result === 'safe') {
                    if (tile) {
                        tile.className = 'fogo-tile reveal-gold';
                        tile.innerHTML = '<span class="coin-gold-icon">🪙</span>';
                    }

                    fogoState.openedTiles.push(tileIndex);
                    fogoState.currentMultiplier = data.current_multiplier;
                    updateStatusValues();
                    updateMainButton();

                } else if (data.result === 'shield_saved') {
                    if (tile) {
                        tile.className = 'fogo-tile reveal-shield-save';
                        tile.innerHTML = '🛡️💥';
                    }

                    fogoState.shieldActive = false;
                    updateShieldStatusUI('broken');
                    alert(data.message || "🛡️ تم تدمير الدرع أثناء امتصاص الصدمة! أنت في أمان ولكن الحماية تحطمت!");

                } else if (data.result === 'broken_coin') {
                    if (tile) {
                        tile.className = 'fogo-tile reveal-gray';
                        tile.innerHTML = '<span class="coin-gray-icon">🪙</span>';
                    }

                    if (data.current_balance !== undefined) updateGlobalBalance(data.current_balance);

                    setTimeout(() => {
                        alert(data.message || "💥 تعثرت في عملة مكسورة وخسرت الجولة!");
                        fogoState.isPlaying = false;
                        updateUIState();
                    }, 400);

                } else if (data.result === 'max_win') {
                    if (tile) {
                        tile.className = 'fogo-tile reveal-gold';
                        tile.innerHTML = '<span class="coin-gold-icon">🪙</span>';
                    }

                    if (data.new_balance !== undefined) updateGlobalBalance(data.new_balance);

                    setTimeout(() => {
                        alert(data.message || "🎉 مبروك! قمت باستخراج كافة العملات بنجاح وتم تحويل الأرباح!");
                        fogoState.isPlaying = false;
                        updateUIState();
                    }, 400);
                }
            } else {
                alert(data?.error || "خطأ أثناء الكشف");
                if (tile) tile.disabled = false;
            }
        } catch (err) {
            alert("خطأ في الاتصال بالسيرفر");
            if (tile) tile.disabled = false;
        } finally {
            fogoState.isProcessing = false;
        }
    };

    loadFogoConfig();
})();

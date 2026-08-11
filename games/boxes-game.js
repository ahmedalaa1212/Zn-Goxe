// games/boxes-game.js
(function initBoxesGameModule() {
    window.boxesState = {
        inGame: false,
        isProcessingPick: false,
        bet: 100,
        brokenCount: 3,
        picks: [],
        sessionToken: null,
        multipliers: [1.2, 1.5, 2.0, 2.8, 3.8, 5.2, 7.5, 10.0, 14.0, 20.0, 28.0, 40.0],
        lastHitIndex: null,
        reviveUsed: false
    };

    window.openBoxesSettings = function() {
        if (window.boxesState.inGame) return;
        window.triggerHaptic('light');
        const modal = document.getElementById('boxes-settings-modal');
        if (modal) modal.style.display = 'flex';
    };

    window.closeBoxesSettings = function() {
        window.triggerHaptic('light');
        const modal = document.getElementById('boxes-settings-modal');
        if (modal) modal.style.display = 'none';
    };

    window.selectBrokenCount = function(count) {
        if (window.boxesState.inGame) return;
        window.triggerHaptic('medium');
        window.boxesState.brokenCount = count;
        
        document.querySelectorAll('.btn-broken-opt').forEach(btn => {
            btn.classList.remove('selected');
            if (parseInt(btn.getAttribute('data-count'), 10) === count) {
                btn.classList.add('selected');
            }
        });

        const selectedText = document.getElementById('selected-broken-text');
        if (selectedText) selectedText.innerText = `${count} عملات مكسورة (سقف 🌟 ${20 + (count - 3) * 10}x)`;
        window.closeBoxesSettings();
    };

    window.addBetBoxes = function(amt) {
        if (window.boxesState.inGame) return;
        window.triggerHaptic('light');
        const input = document.getElementById('boxes-bet-input');
        if (!input) return;
        let val = (parseFloat(input.value) || 0) + amt;
        input.value = Math.max(100, Math.floor(val));
    };

    window.setBetMaxBoxes = function() {
        if (window.boxesState.inGame) return;
        window.triggerHaptic('medium');
        const input = document.getElementById('boxes-bet-input');
        if (!input) return;
        const maxBal = Math.floor(window.getStoredBalance());
        input.value = maxBal > 100 ? maxBal : 100;
    };

    window.renderBoxesGrid = function() {
        const gridEl = document.getElementById('boxes-grid');
        if (!gridEl) return;
        gridEl.innerHTML = '';
        
        for (let i = 0; i < 36; i++) {
            const boxCard = document.createElement('div');
            boxCard.className = 'box-card';
            boxCard.setAttribute('data-index', i);
            boxCard.onclick = () => onBoxClick(i);

            boxCard.innerHTML = `
                <div class="box-inner">
                    <div class="box-front"></div>
                    <div class="box-back"></div>
                </div>
            `;
            gridEl.appendChild(boxCard);
        }
        updateCashOutButton();
    };

    function updateCashOutButton() {
        const btn = document.getElementById('btn-cashout-boxes');
        if (!btn) return;

        if (!window.boxesState.inGame) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerHTML = `سحب الأرباح (0.00 ZN)`;
            return;
        }

        const picksCount = window.boxesState.picks.length;
        if (picksCount === 0) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerHTML = `اختر الصندوق الأول 🚀`;
        } else {
            btn.disabled = false;
            btn.classList.remove('btn-disabled');
            const multIndex = Math.min(picksCount - 1, window.boxesState.multipliers.length - 1);
            const currentMult = window.boxesState.multipliers[multIndex] || 1.2;
            const payout = (window.boxesState.bet * currentMult).toFixed(2);
            btn.innerHTML = `💰 سحب الأرباح (${window.formatNumberHTML(payout)} ZN) <span style="font-size:0.85em; opacity:0.9;">(${currentMult}x)</span>`;
        }
    }

    window.startBoxesGame = async function() {
        if (window.boxesState.inGame) return;
        const betInput = document.getElementById('boxes-bet-input');
        const betVal = parseFloat(betInput ? betInput.value : 100) || 0;
        
        if (betVal < 100) return window.showNotification("الحد الأدنى للرهان هو 100 ZN.");
        if (window.getStoredBalance() < betVal) return window.showNotification("رصيدك غير كافٍ للبدء.");

        window.triggerHaptic('heavy');
        const btnStart = document.getElementById('btn-start-boxes');
        if (btnStart) {
            btnStart.disabled = true;
            btnStart.innerText = "جاري فتح الشبكة... ⏳";
        }

        try {
            const initData = window.tele?.initData || "";
            const tgId = window.getTgId();

            const res = await fetch('/api/game/start', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': initData,
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({ 
                    tg_id: tgId, 
                    bet_amount: betVal, 
                    broken_count: window.boxesState.brokenCount,
                    initData: initData 
                })
            });

            const data = await res.json();
            if (res.ok && (data.status === 'success' || data.success)) {
                const newBal = data.new_balance !== undefined ? data.new_balance : (window.getStoredBalance() - betVal);
                window.setStoredBalance(newBal, true);
                
                window.boxesState.inGame = true;
                window.boxesState.isProcessingPick = false;
                window.boxesState.bet = betVal;
                window.boxesState.picks = [];
                window.boxesState.sessionToken = data.session_token || null;
                if (data.multipliers) window.boxesState.multipliers = data.multipliers;
                window.boxesState.reviveUsed = false;
                
                window.renderBoxesGrid();
                
                if (btnStart) btnStart.style.display = 'none';
                const btnCashOut = document.getElementById('btn-cashout-boxes');
                if (btnCashOut) btnCashOut.style.display = 'block';
                if (betInput) betInput.disabled = true;
                
                updateCashOutButton();
                window.triggerGlobalToast("✨ بدأت الجولة! اختر صناديقك بحذر.", true);
            } else {
                if (btnStart) {
                    btnStart.disabled = false;
                    btnStart.innerText = "بدء الجولة 🚀";
                }
                window.showNotification("⚠️ " + (data.message || "تعذر بدء الجولة"));
            }
        } catch (e) {
            if (btnStart) {
                btnStart.disabled = false;
                btnStart.innerText = "بدء الجولة 🚀";
            }
            window.showNotification("خطأ في الاتصال بالخادم.");
        }
    };

    async function onBoxClick(index) {
        if (!window.boxesState.inGame || window.boxesState.picks.includes(index) || window.boxesState.isProcessingPick) return;
        
        window.boxesState.isProcessingPick = true;
        window.triggerHaptic('medium');

        const boxCard = document.querySelector(`.box-card[data-index="${index}"]`);
        if (!boxCard) {
            window.boxesState.isProcessingPick = false;
            return;
        }

        try {
            const initData = window.tele?.initData || "";
            const tgId = window.getTgId();

            const res = await fetch('/api/game/step', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': initData,
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({
                    tg_id: tgId,
                    box_index: index,
                    session_token: window.boxesState.sessionToken,
                    initData: initData
                })
            });

            const data = await res.json();
            const isBomb = data.is_bomb || data.status === 'loss';

            if (res.ok && !isBomb && (data.status === 'safe' || data.success)) {
                window.boxesState.picks.push(index);
                const backEl = boxCard.querySelector('.box-back');
                if (backEl) backEl.innerHTML = '<span class="coin-gold">🟡 ZN</span>';
                boxCard.classList.add('flipped', 'safe');
                updateCashOutButton();
            } else {
                handleBrokenCoinHit(index, data.layout);
            }
        } catch (e) {
            window.showNotification("خطأ في الاتصال بالخادم أثناء الاختيار.");
        } finally {
            window.boxesState.isProcessingPick = false;
        }
    }

    window.cashOutBoxes = async function() {
        if (!window.boxesState.inGame) return;
        window.triggerHaptic('heavy');

        const btnCashOut = document.getElementById('btn-cashout-boxes');
        if (btnCashOut) {
            btnCashOut.disabled = true;
            btnCashOut.innerText = "جاري تأكيد السحب... ⏳";
        }

        try {
            const initData = window.tele?.initData || "";
            const tgId = window.getTgId();

            const res = await fetch('/api/game/cashout', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': initData,
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({
                    tg_id: tgId,
                    session_token: window.boxesState.sessionToken,
                    initData: initData
                })
            });

            const data = await res.json();
            if (res.ok && (data.status === 'success' || data.success)) {
                if (data.new_balance !== undefined) window.setStoredBalance(data.new_balance, true);
                revealFullBoard(data.layout);
                window.triggerHaptic('success');
                window.triggerGlobalToast(`🎉 مبروك! سحبت ${window.formatNumberHTML(data.payout)} ZN`, true);
                resetBoxesControls();
            } else {
                window.showNotification("⚠️ " + (data.message || "تعذر إتمام السحب"));
                resetBoxesControls();
            }
        } catch (e) {
            window.showNotification("خطأ في الاتصال بالخادم.");
            resetBoxesControls();
        }
    };

    function handleBrokenCoinHit(index, layout) {
        window.boxesState.lastHitIndex = index;
        window.triggerHaptic('error');
        
        const boxCard = document.querySelector(`.box-card[data-index="${index}"]`);
        if (boxCard) {
            const backEl = boxCard.querySelector('.box-back');
            if (backEl) backEl.innerHTML = '<span class="coin-broken">⚪💥</span>';
            boxCard.classList.add('flipped', 'broken');
        }

        if (!window.boxesState.reviveUsed && window.Adsgram) {
            showReviveModal(index, layout);
        } else {
            finalizeLoss(layout);
        }
    }

    function showReviveModal(hitIndex, layout) {
        const modal = document.getElementById('revive-modal');
        if (modal) modal.style.display = 'flex';
        
        window.onConfirmRevive = async function(watchAd) {
            if (modal) modal.style.display = 'none';
            if (watchAd) {
                try {
                    const AdController = window.Adsgram?.init({ blockId: "100" });
                    const adResult = await AdController.show();
                    if (adResult && adResult.done) {
                        window.triggerHaptic('success');
                        window.boxesState.reviveUsed = true;
                        window.boxesState.picks = window.boxesState.picks.filter(p => p !== hitIndex);
                        const card = document.querySelector(`.box-card[data-index="${hitIndex}"]`);
                        if (card) {
                            card.classList.remove('flipped', 'broken');
                            const backEl = card.querySelector('.box-back');
                            if (backEl) backEl.innerHTML = '';
                        }
                        updateCashOutButton();
                        window.triggerGlobalToast("🛡️ تم تفعيل ميزة الإحياء! تابع اللعب.", true);
                        return;
                    }
                } catch (err) {
                    window.triggerGlobalToast("⚠️ تعذر تحميل الإعلان، تم تطبيق الخسارة.", false);
                }
            }
            finalizeLoss(layout);
        };
    }

    function finalizeLoss(layout) {
        revealFullBoard(layout);
        window.triggerGlobalToast("💥 اصطدمت بقنبلة! حظاً أوفير في الجولة القادمة.", false);
        resetBoxesControls();
    }

    function revealFullBoard(layout) {
        if (!layout) return;
        for (let i = 0; i < 36; i++) {
            const card = document.querySelector(`.box-card[data-index="${i}"]`);
            if (!card) continue;
            
            const isBroken = layout[i];
            const backEl = card.querySelector('.box-back');
            if (isBroken) {
                if (backEl) backEl.innerHTML = '<span class="coin-broken">⚪💥</span>';
                card.classList.add('broken');
            } else {
                if (backEl) backEl.innerHTML = '<span class="coin-gold">🟡 ZN</span>';
                card.classList.add('safe');
            }
            card.classList.add('flipped');
        }
    }

    function resetBoxesControls() {
        window.boxesState.inGame = false;
        window.boxesState.isProcessingPick = false;
        const btnStart = document.getElementById('btn-start-boxes');
        const btnCashOut = document.getElementById('btn-cashout-boxes');
        const betInput = document.getElementById('boxes-bet-input');
        
        if (btnStart) {
            btnStart.style.display = 'block';
            btnStart.disabled = false;
            btnStart.innerText = "بدء الجولة 🚀";
        }
        if (btnCashOut) btnCashOut.style.display = 'none';
        if (betInput) betInput.disabled = false;
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', window.renderBoxesGrid);
    } else {
        window.renderBoxesGrid();
    }
})();

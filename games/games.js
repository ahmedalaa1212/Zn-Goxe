// games/games.js
(function initGamesModule() {
    // --- متغيرات الساحة الكبرى ---
    let isJoining = false;
    let currentRoundId = null;
    let arenaEndTime = 0;
    let countdownInterval = null;
    let backgroundSyncInterval = null;
    let hasCheckedResults = false;
    let statusRetryTimeout = null;
    let pendingConfirmCallback = null;

    let lastStatusFetchTimestamp = 0;
    const STATUS_FETCH_COOLDOWN = 12000;
    let hasJoinedCurrentRound = false;

    let currentEntryFee = 350; // الحد الأدنى للاشتراك 350 ZN
    let currentLockSeconds = 15;
    let currentDisplayBalance = 0;
    let currentPrizePool = 0;

    // --- متغيرات لعبة شبكة العملات والمخاطرة (36 صندوقاً) ---
    let boxesState = {
        inGame: false,
        isProcessingPick: false,
        bet: 100,
        brokenCount: 3,
        picks: [],
        sessionToken: null,
        multipliers: [],
        lastHitIndex: null,
        reviveUsed: false
    };

    const tele = window.Telegram?.WebApp;

    // --- 0. الأدوات المساعدة وحالة التطبيق ---

    function triggerHaptic(type = 'light') {
        try {
            if (tele?.HapticFeedback) {
                if (type === 'light') tele.HapticFeedback.impactOccurred('light');
                else if (type === 'medium') tele.HapticFeedback.impactOccurred('medium');
                else if (type === 'heavy') tele.HapticFeedback.impactOccurred('heavy');
                else if (type === 'success') tele.HapticFeedback.notificationOccurred('success');
                else if (type === 'error') tele.HapticFeedback.notificationOccurred('error');
            }
        } catch (e) {}
    }

    function formatNumberHTML(val, suffix = "") {
        const num = parseFloat(val) || 0;
        const parts = num.toFixed(2).split('.');
        const intPart = parseInt(parts[0], 10).toLocaleString('en-US');
        const decPart = parts[1];
        return `${intPart}<span class="small-decimal" style="font-size:0.8em; opacity:0.85;">.${decPart}</span>${suffix}`;
    }

    function animateCounter(elementId, startVal, endVal, duration = 800, suffix = " ZN") {
        const el = document.getElementById(elementId);
        if (!el) return;
        let startTimestamp = null;
        const startNum = parseFloat(startVal) || 0;
        const endNum = parseFloat(endVal) || 0;

        if (startNum === endNum) {
            el.innerHTML = formatNumberHTML(endNum, suffix);
            return;
        }

        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const easeProgress = 1 - Math.pow(1 - progress, 3);
            const currentVal = startNum + (endNum - startNum) * easeProgress;
            el.innerHTML = formatNumberHTML(currentVal, suffix);
            if (progress < 1) window.requestAnimationFrame(step);
            else el.innerHTML = formatNumberHTML(endNum, suffix);
        };
        window.requestAnimationFrame(step);
    }

    function showNotification(msg) {
        triggerHaptic('medium');
        if (tele && tele.showAlert) tele.showAlert(msg);
        else alert(msg);
    }

    function getStoredBalance() {
        if (window.userState && window.userState.balance !== undefined) return parseFloat(window.userState.balance) || 0;
        if (window.PlayerData && window.PlayerData.balance !== undefined) return parseFloat(window.PlayerData.balance) || 0;
        if (window.GameState && window.GameState.balance !== undefined) return parseFloat(window.GameState.balance) || 0;
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        const num = bal !== null ? parseFloat(bal) : 0;
        return isNaN(num) ? 0 : num;
    }

    function setStoredBalance(newBalance, animate = true) {
        if (newBalance !== undefined && newBalance !== null) {
            const numVal = Math.round((parseFloat(newBalance) || 0) * 100) / 100;
            const oldVal = currentDisplayBalance || getStoredBalance();
            
            if (window.userState) window.userState.balance = numVal;
            if (window.PlayerData) window.PlayerData.balance = numVal;
            if (window.GameState) window.GameState.balance = numVal;
            
            localStorage.setItem('zn_balance', numVal.toString());
            localStorage.setItem('user_balance', numVal.toString());
            
            if (animate) animateCounter('top-balance-games', oldVal, numVal, 800, " ZN");
            else {
                const gameBalEl = document.getElementById('top-balance-games');
                if (gameBalEl) gameBalEl.innerHTML = formatNumberHTML(numVal, " ZN");
            }
            currentDisplayBalance = numVal;

            if (typeof window.setBalance === 'function') window.setBalance(numVal);
            const mainBalEl = document.getElementById('user-balance') || document.querySelector('.user-balance');
            if (mainBalEl) mainBalEl.innerHTML = formatNumberHTML(numVal, " ZN");
        }
    }

    function syncGameBalance() {
        const stored = getStoredBalance();
        const oldVal = currentDisplayBalance;
        setStoredBalance(stored, oldVal !== stored && oldVal !== 0);
    }

    window.switchGameTab = function(tabName) {
        triggerHaptic('light');
        const arenaTab = document.getElementById('tab-arena');
        const boxesTab = document.getElementById('tab-boxes');
        const arenaContent = document.getElementById('content-arena');
        const boxesContent = document.getElementById('content-boxes');

        if (tabName === 'arena') {
            if (arenaTab) { arenaTab.classList.add('active'); arenaTab.style.opacity = '1'; }
            if (boxesTab) { boxesTab.classList.remove('active'); boxesTab.style.opacity = '0.6'; }
            if (arenaContent) arenaContent.style.display = 'block';
            if (boxesContent) boxesContent.style.display = 'none';
        } else {
            if (boxesTab) { boxesTab.classList.add('active'); boxesTab.style.opacity = '1'; }
            if (arenaTab) { arenaTab.classList.remove('active'); arenaTab.style.opacity = '0.6'; }
            if (arenaContent) arenaContent.style.display = 'none';
            if (boxesContent) boxesContent.style.display = 'block';
            renderBoxesGrid();
        }
    };

    // --- 1. منطق لعبة شبكة العملات والمخاطرة (36 صندوقاً) ---

    window.openBoxesSettings = function() {
        if (boxesState.inGame) return;
        triggerHaptic('light');
        const modal = document.getElementById('boxes-settings-modal');
        if (modal) modal.style.display = 'flex';
    };

    window.closeBoxesSettings = function() {
        triggerHaptic('light');
        const modal = document.getElementById('boxes-settings-modal');
        if (modal) modal.style.display = 'none';
    };

    window.selectBrokenCount = function(count) {
        if (boxesState.inGame) return;
        triggerHaptic('medium');
        boxesState.brokenCount = count;
        
        document.querySelectorAll('.btn-broken-opt').forEach(btn => {
            btn.classList.remove('selected');
            if (parseInt(btn.getAttribute('data-count'), 10) === count) {
                btn.classList.add('selected');
            }
        });

        const selectedText = document.getElementById('selected-broken-text');
        if (selectedText) selectedText.innerText = `${count} عملات مكسورة (سقف 🌟 ${20 + (count - 3) * 10}x)`;
        
        closeBoxesSettings();
    };

    window.addBetBoxes = (amt) => {
        if (boxesState.inGame) return;
        triggerHaptic('light');
        const input = document.getElementById('boxes-bet-input');
        let val = (parseFloat(input.value) || 0) + amt;
        input.value = val;
    };

    window.setBetMaxBoxes = () => {
        if (boxesState.inGame) return;
        triggerHaptic('medium');
        const input = document.getElementById('boxes-bet-input');
        input.value = Math.floor(getStoredBalance());
    };

    function renderBoxesGrid() {
        const gridEl = document.getElementById('boxes-grid');
        if (!gridEl) return;
        gridEl.innerHTML = '';
        
        for (let i = 0; i < 36; i++) {
            const boxCard = document.createElement('div');
            boxCard.className = 'box-card';
            boxCard.setAttribute('data-index', i);
            boxCard.onclick = () => onBoxClick(i);

            // مربع خالي وفارغ في البداية بدلاً من الملاحظة السابقة
            boxCard.innerHTML = `
                <div class="box-inner">
                    <div class="box-front"></div>
                    <div class="box-back"></div>
                </div>
            `;
            gridEl.appendChild(boxCard);
        }
        updateCashOutButton();
    }

    function updateCashOutButton() {
        const btn = document.getElementById('btn-cashout-boxes');
        if (!btn) return;

        if (!boxesState.inGame) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerHTML = `سحب الأرباح (0.00 ZN)`;
            return;
        }

        const picksCount = boxesState.picks.length;
        if (picksCount === 0) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerHTML = `اختر الصندوق الأول 🚀`;
        } else {
            btn.disabled = false;
            btn.classList.remove('btn-disabled');
            const multIndex = Math.min(picksCount - 1, boxesState.multipliers.length - 1);
            const currentMult = boxesState.multipliers[multIndex] || 1.0;
            const payout = (boxesState.bet * currentMult).toFixed(2);
            btn.innerHTML = `💰 سحب الأرباح (${formatNumberHTML(payout)} ZN) <span style="font-size:0.85em; opacity:0.9;">(${currentMult}x)</span>`;
        }
    }

    window.startBoxesGame = async function() {
        if (boxesState.inGame) return;
        const betInput = document.getElementById('boxes-bet-input');
        const betVal = parseFloat(betInput.value) || 0;
        
        if (betVal < 100) return showNotification("الحد الأدنى للرهان هو 100 ZN.");
        if (getStoredBalance() < betVal) return showNotification("رصيدك غير كافٍ للبدء.");

        triggerHaptic('heavy');
        const btnStart = document.getElementById('btn-start-boxes');
        btnStart.disabled = true;
        btnStart.innerText = "جاري فتح الشبكة... ⏳";

        try {
            const initData = tele?.initData || "";
            const res = await fetch('/api/games/boxes/start', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({ initData: initData, bet: betVal, broken_count: boxesState.brokenCount })
            });

            const data = await res.json();
            if (data.success) {
                setStoredBalance(data.new_balance, true);
                
                boxesState.inGame = true;
                boxesState.isProcessingPick = false;
                boxesState.bet = betVal;
                boxesState.picks = [];
                boxesState.sessionToken = data.session_token;
                boxesState.multipliers = data.multipliers || [];
                boxesState.reviveUsed = false;
                
                renderBoxesGrid();
                
                btnStart.style.display = 'none';
                document.getElementById('btn-cashout-boxes').style.display = 'block';
                betInput.disabled = true;
                document.getElementById('btn-boxes-settings').style.pointerEvents = 'none';
                
                updateCashOutButton();
                triggerGlobalToast("✨ بدأت الجولة! اختر صناديقك بحذر.", true);
            } else {
                btnStart.disabled = false;
                btnStart.innerText = "بدء الجولة 🚀";
                showNotification("⚠️ " + (data.message || "تعذر بدء الجولة"));
            }
        } catch (e) {
            btnStart.disabled = false;
            btnStart.innerText = "بدء الجولة 🚀";
            showNotification("خطأ في الاتصال بالخادم.");
        }
    };

    async function onBoxClick(index) {
        if (!boxesState.inGame || boxesState.picks.includes(index) || boxesState.isProcessingPick) return;
        
        boxesState.isProcessingPick = true;
        triggerHaptic('medium');

        const boxCard = document.querySelector(`.box-card[data-index="${index}"]`);
        if (!boxCard) {
            boxesState.isProcessingPick = false;
            return;
        }

        try {
            const initData = tele?.initData || "";
            const res = await fetch('/api/games/boxes/pick', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({
                    initData: initData,
                    session_token: boxesState.sessionToken,
                    box_index: index
                })
            });

            const data = await res.json();
            if (data.success) {
                boxesState.picks.push(index);
                const backEl = boxCard.querySelector('.box-back');

                if (!data.is_broken) {
                    // عملة ذهبية ZN عند الاختيار الصحيح
                    if (backEl) backEl.innerHTML = '<span class="coin-gold">🟡 ZN</span>';
                    boxCard.classList.add('flipped', 'safe');
                    updateCashOutButton();

                    const safeCountTarget = 36 - boxesState.brokenCount;
                    if (boxesState.picks.length === safeCountTarget) {
                        await cashOutBoxes();
                    }
                } else {
                    // عملة رمادية مكسورة عند الاختيار الخاطئ
                    handleBrokenCoinHit(index, data.layout);
                }
            } else {
                showNotification("⚠️ " + (data.message || "خطأ أثناء اختيار الصندوق"));
            }
        } catch (e) {
            showNotification("خطأ في الاتصال بالخادم أثناء الاختيار.");
        } finally {
            boxesState.isProcessingPick = false;
        }
    }

    window.cashOutBoxes = async function() {
        if (!boxesState.inGame) return;
        triggerHaptic('heavy');

        const btnCashOut = document.getElementById('btn-cashout-boxes');
        btnCashOut.disabled = true;
        btnCashOut.innerText = "جاري تأكيد السحب... ⏳";

        try {
            const initData = tele?.initData || "";
            const res = await fetch('/api/games/boxes/end', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({
                    initData: initData,
                    session_token: boxesState.sessionToken,
                    picks: boxesState.picks,
                    action: 'cashout'
                })
            });

            const data = await res.json();
            if (data.success) {
                setStoredBalance(data.new_balance, true);
                revealFullBoard(data.layout);

                if (data.payout > 0) {
                    triggerHaptic('success');
                    triggerGlobalToast(`🎉 مبروك! سحبت ${data.payout.toLocaleString('en-US')} ZN (مضاعف ${data.multiplier}x)`, true);
                }
                resetBoxesControls();
            } else {
                showNotification("⚠️ " + (data.message || "تعذر إتمام السحب"));
                resetBoxesControls();
            }
        } catch (e) {
            showNotification("خطأ في الاتصال بالخادم.");
            resetBoxesControls();
        }
    };

    function handleBrokenCoinHit(index, layout) {
        boxesState.lastHitIndex = index;
        triggerHaptic('error');
        
        const boxCard = document.querySelector(`.box-card[data-index="${index}"]`);
        if (boxCard) {
            const backEl = boxCard.querySelector('.box-back');
            // إظهار عملة رمادية مكسورة
            if (backEl) backEl.innerHTML = '<span class="coin-broken">⚪💥</span>';
            boxCard.classList.add('flipped', 'broken');
        }

        if (!boxesState.reviveUsed && window.Adsgram) {
            showReviveModal(index, layout);
        } else {
            finalizeLoss(layout);
        }
    }

    function showReviveModal(hitIndex, layout) {
        const modal = document.getElementById('revive-modal');
        if (modal) modal.style.display = 'flex';
        
        window.onConfirmRevive = async function(watchAd) {
            modal.style.display = 'none';
            if (watchAd) {
                try {
                    const AdController = window.Adsgram?.init({ blockId: "100" });
                    const adResult = await AdController.show();
                    if (adResult && adResult.done) {
                        triggerHaptic('success');
                        boxesState.reviveUsed = true;
                        
                        boxesState.picks = boxesState.picks.filter(p => p !== hitIndex);
                        const card = document.querySelector(`.box-card[data-index="${hitIndex}"]`);
                        if (card) {
                            card.classList.remove('flipped', 'broken');
                            const backEl = card.querySelector('.box-back');
                            if (backEl) backEl.innerHTML = '';
                        }
                        updateCashOutButton();
                        triggerGlobalToast("🛡️ تم تفعيل ميزة الإحياء! تابع اختيار صناديقك.", true);
                        return;
                    }
                } catch (err) {
                    triggerGlobalToast("⚠️ تعذر تحميل الإعلان، تم تطبيق الخسارة.", false);
                }
            }
            finalizeLoss(layout);
        };
    }

    function finalizeLoss(layout) {
        revealFullBoard(layout);
        triggerGlobalToast("😅 اصطدمت بعملة مكسورة! حظاً أوفير في الجولة القادمة.", false);
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
        boxesState.inGame = false;
        boxesState.isProcessingPick = false;
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
        
        const settingsBtn = document.getElementById('btn-boxes-settings');
        if (settingsBtn) settingsBtn.style.pointerEvents = 'auto';
    }

    // --- 2. منطق الساحة الكبرى والتحديثات الخلفية الاحترافية ---

    async function fetchArenaStatus(force = false) {
        if (statusRetryTimeout) { clearTimeout(statusRetryTimeout); statusRetryTimeout = null; }
        const now = Date.now();
        if (!force && (now - lastStatusFetchTimestamp < STATUS_FETCH_COOLDOWN)) return;
        lastStatusFetchTimestamp = now;

        try {
            const initData = tele?.initData || "";
            const response = await fetch('/api/games/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({ initData: initData })
            });
            if (!response.ok) throw new Error("Server Error");
            const data = await response.json();
            if (data.success) {
                if (data.entry_fee) currentEntryFee = data.entry_fee;
                if (data.lock_seconds) currentLockSeconds = data.lock_seconds;
                
                const subtext = document.getElementById('arena-subtext');
                if (subtext) subtext.innerText = `سحب تلقائي مستمر! رسوم الاشتراك: ${parseInt(currentEntryFee, 10).toLocaleString('en-US')} ZN`;
                
                if (data.balance !== undefined) setStoredBalance(data.balance, true);
                currentRoundId = data.round_id;
                arenaEndTime = parseInt(data.end_time) || 0;
                hasCheckedResults = false;
                hasJoinedCurrentRound = !!data.has_joined;
                updateArenaPrizes(data);
                startSmoothCountdown();
            }
        } catch (error) {
            statusRetryTimeout = setTimeout(() => fetchArenaStatus(true), 6000);
        }
    }

    function updateArenaPrizes(data) {
        const newPool = parseFloat(data.prize_pool) || 0;
        animateCounter('prize-pool', currentPrizePool, newPool, 900, " ZN");
        currentPrizePool = newPool;
        const p1 = document.getElementById('prize-1');
        const p2 = document.getElementById('prize-2');
        const p3 = document.getElementById('prize-3');
        const p4 = document.getElementById('prize-4');
        const p5 = document.getElementById('prize-5');

        if (p1) p1.innerHTML = formatNumberHTML(newPool * 0.30, " ZN");
        if (p2) p2.innerHTML = formatNumberHTML(newPool * 0.25, " ZN");
        if (p3) p3.innerHTML = formatNumberHTML(newPool * 0.20, " ZN");
        if (p4) p4.innerHTML = formatNumberHTML(newPool * 0.15, " ZN");
        if (p5) p5.innerHTML = formatNumberHTML(newPool * 0.10, " ZN");
    }

    function startSmoothCountdown() {
        if (countdownInterval) clearInterval(countdownInterval);
        timerTick();
        countdownInterval = setInterval(() => timerTick(), 1000);
    }

    function timerTick() {
        if (!arenaEndTime || arenaEndTime <= 0) return;
        const now = Math.floor(Date.now() / 1000);
        let timeLeft = arenaEndTime - now;
        const btn = document.getElementById('btn-join-arena');
        const timerEl = document.getElementById('arena-timer');
        if (timeLeft < 0) timeLeft = 0;

        if (timerEl) {
            let m = Math.floor(timeLeft / 60);
            let s = timeLeft % 60;
            timerEl.innerText = `${m < 10 ? '0'+m : m}:${s < 10 ? '0'+s : s}`;
        }

        if (!btn) return;

        if (timeLeft <= currentLockSeconds && timeLeft > 0) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerText = "🔒 تم إغلاق الاشتراك (جاري السحب⏳)";
        } else if (timeLeft === 0) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerText = "🔄 جاري إعلان النتائج...";
            if (!hasCheckedResults && currentRoundId) {
                hasCheckedResults = true;
                fetchRoundResults(currentRoundId, 0);
            }
        } else {
            if (!hasJoinedCurrentRound) {
                btn.disabled = false;
                btn.classList.remove('btn-disabled');
                btn.innerText = `⚔️ دخول الساحة (${parseInt(currentEntryFee, 10).toLocaleString('en-US')} ZN)`;
            } else {
                btn.disabled = true;
                btn.classList.add('btn-disabled');
                btn.innerText = "أنت مشترك بالفعل ✅";
            }
        }
    }

    window.joinArena = function() {
        triggerHaptic('heavy');
        if (isJoining || hasJoinedCurrentRound) return;
        if (getStoredBalance() < currentEntryFee) {
            showNotification(`⚠️ رصيدك غير كافٍ للدخول في الساحة (${currentEntryFee} ZN).`);
            return;
        }
        askForConfirmation(() => executeJoinArena());
    };

    async function executeJoinArena() {
        if (isJoining) return;
        isJoining = true;
        const btn = document.getElementById('btn-join-arena');
        if (btn) { btn.disabled = true; btn.innerText = "جاري الدخول... ⏳"; }

        try {
            const initData = tele?.initData || "";
            const response = await fetch('/api/games/join', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({ initData: initData })
            });
            const data = await response.json();
            if (data.success) {
                triggerHaptic('success');
                hasJoinedCurrentRound = true;
                if (data.new_balance !== undefined) setStoredBalance(data.new_balance, true);
                if (data.prize_pool !== undefined) updateArenaPrizes(data);
                if (btn) { btn.disabled = true; btn.classList.add('btn-disabled'); btn.innerText = "أنت مشترك بالفعل ✅"; }
                showNotification("🎉 تم دخول الساحة بنجاح!");
            } else {
                triggerHaptic('error');
                showNotification("⚠️ " + (data.message || "تعذر الاشتراك"));
            }
        } catch (error) {
            triggerHaptic('error');
            showNotification("حدث خطأ في الاتصال بالخادم.");
        } finally {
            isJoining = false;
        }
    }

    function triggerGlobalToast(msg, isSuccess = true) {
        let toastBox = document.getElementById('global-toast-notification');
        if (!toastBox) {
            toastBox = document.createElement('div');
            toastBox.id = 'global-toast-notification';
            toastBox.style.cssText = `
                position: fixed; top: 18px; left: 50%; transform: translateX(-50%);
                background: rgba(15, 23, 42, 0.95); backdrop-filter: blur(12px);
                border: 1.5px solid ${isSuccess ? '#10b981' : '#ef4444'};
                color: #ffffff; padding: 12px 22px; border-radius: 50px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.8); z-index: 99999999;
                font-size: 13px; font-weight: 800; text-align: center; width: 90%; max-width: 380px;
                display: flex; align-items: center; justify-content: center; gap: 8px;
            `;
            document.body.appendChild(toastBox);
        }
        toastBox.innerHTML = msg;
        toastBox.style.display = 'flex';
        setTimeout(() => { if (toastBox) toastBox.style.display = 'none'; }, 4500);
    }

    function askForConfirmation(onConfirm) {
        const modal = document.getElementById('confirm-modal');
        const feeText = document.getElementById('confirm-fee-text');
        if (feeText) feeText.innerHTML = formatNumberHTML(currentEntryFee, " ZN");
        if (modal) { pendingConfirmCallback = onConfirm; modal.style.display = 'flex'; }
    }

    window.onConfirmJoin = function(confirmed) {
        triggerHaptic('light');
        const modal = document.getElementById('confirm-modal');
        if (modal) modal.style.display = 'none';
        if (confirmed && typeof pendingConfirmCallback === 'function') pendingConfirmCallback();
        pendingConfirmCallback = null;
    };

    function showDrawModal(state, refundFee = 0) {
        const modal = document.getElementById('draw-modal');
        const refundedEl = document.getElementById('draw-refunded');
        const winnersEl = document.getElementById('draw-winners');
        const refundAmountEl = document.getElementById('refund-amount-display');
        if (refundedEl) refundedEl.style.display = 'none';
        if (winnersEl) winnersEl.style.display = 'none';
        if (state === 'refunded' && refundedEl) {
            refundedEl.style.display = 'block';
            if (refundAmountEl) refundAmountEl.innerHTML = `+${formatNumberHTML(refundFee, " ZN")}`;
        }
        if (state === 'winners' && winnersEl) winnersEl.style.display = 'block';
        if (modal) modal.style.display = 'flex';
    }

    window.closeDrawModal = function() {
        triggerHaptic('light');
        const modal = document.getElementById('draw-modal');
        if (modal) modal.style.display = 'none';
        fetchArenaStatus(true);
    };

    async function fetchRoundResults(roundId, retries = 0) {
        if (!roundId || retries > 4) { fetchArenaStatus(true); return; }
        try {
            const initData = tele?.initData || "";
            const response = await fetch('/api/games/results', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({ initData: initData, round_id: roundId })
            });
            const data = await response.json();
            if (data.success) {
                if (data.new_balance !== undefined) setStoredBalance(data.new_balance, true);
                if (data.status === 'refunded') showDrawModal('refunded', data.refund_amount || currentEntryFee);
                else if (data.status === 'completed') { renderWinners(data.winners || []); showDrawModal('winners'); }
                else setTimeout(() => fetchRoundResults(roundId, retries + 1), 2500);
            }
        } catch (e) {
            setTimeout(() => fetchRoundResults(roundId, retries + 1), 2500);
        }
    }

    async function checkBackgroundNotifications() {
        try {
            const initData = tele?.initData || "";
            if (!initData) return;
            const response = await fetch('/api/games/check_notifications', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${initData}` },
                body: JSON.stringify({ initData: initData })
            });
            const data = await response.json();
            if (data.success) {
                if (data.balance !== undefined) setStoredBalance(data.balance, true);
                if (data.refund && data.refund > 0) {
                    triggerGlobalToast(`💰 تم استرداد المبلغ بنجاح (+${data.refund} ZN)`);
                    showDrawModal('refunded', data.refund);
                }
            }
        } catch (e) {}
    }

    function renderWinners(winners) {
        const list = document.getElementById('winners-list');
        if (!list) return;
        list.innerHTML = '';
        const medals = ['🥇', '🥈', '🥉', '🏅', '🏅'];
        winners.forEach((winner, index) => {
            let name = winner.name || `مستخدم #${(winner.uid || '00000').substring(0,5)}`;
            let prize = formatNumberHTML(winner.prize || 0);
            list.innerHTML += `
                <div style="display:flex; justify-content:space-between; align-items:center; padding:10px 8px; border-bottom:1px solid rgba(255,255,255,0.06);">
                    <span style="font-weight:700;">${medals[index] || '🏅'} ${name}</span>
                    <span style="color:var(--accent-green); font-weight:800;">+${prize} ZN</span>
                </div>
            `;
        });
    }

    if (backgroundSyncInterval) clearInterval(backgroundSyncInterval);
    backgroundSyncInterval = setInterval(checkBackgroundNotifications, 25000);

    syncGameBalance();
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            fetchArenaStatus(true);
            checkBackgroundNotifications();
            renderBoxesGrid();
        });
    } else {
        fetchArenaStatus(true);
        checkBackgroundNotifications();
        renderBoxesGrid();
    }
})();

// games/games.js
(function initGamesModule() {
    let isJoining = false;
    let currentRoundId = null;
    let arenaEndTime = 0;
    let countdownInterval = null;
    let backgroundSyncInterval = null;
    let hasCheckedResults = false;
    let statusRetryTimeout = null;
    let pendingConfirmCallback = null;

    // متغير محلي لتتبع حالة الاشتراك في الجولة الحالية لحظياً
    let hasJoinedCurrentRound = false;

    let currentEntryFee = 1000;
    let currentLockSeconds = 15;
    let currentDisplayBalance = 0;
    let currentPrizePool = 0;

    const tele = window.Telegram?.WebApp;

    // --- دالة تنسيق الأرقام بـ HTML لتصغير الخانات العشرية ---
    function formatNumberHTML(val, suffix = "") {
        const num = parseFloat(val) || 0;
        const parts = num.toFixed(2).split('.');
        const intPart = parseInt(parts[0], 10).toLocaleString('en-US');
        const decPart = parts[1];
        return `${intPart}<span class="small-decimal">.${decPart}</span>${suffix}`;
    }

    // --- العداد البصري التدريجي الانسيابي ---
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

            if (progress < 1) {
                window.requestAnimationFrame(step);
            } else {
                el.innerHTML = formatNumberHTML(endNum, suffix);
            }
        };

        window.requestAnimationFrame(step);
    }

    function showNotification(msg) {
        if (tele && tele.showAlert) {
            tele.showAlert(msg);
        } else {
            alert(msg);
        }
    }

    // --- عرض التنبيه العائم المباشر بدون إغلاق التطبيق ---
    function triggerGlobalToast(msg, isSuccess = true) {
        let toastBox = document.getElementById('global-toast-notification');
        if (!toastBox) {
            toastBox = document.createElement('div');
            toastBox.id = 'global-toast-notification';
            toastBox.style.cssText = `
                position: fixed;
                top: 15px;
                left: 50%;
                transform: translateX(-50%);
                background: linear-gradient(135deg, #1e293b, #0f172a);
                border: 1.5px solid ${isSuccess ? '#38bdf8' : '#f59e0b'};
                color: #ffffff;
                padding: 12px 20px;
                border-radius: 16px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.8), 0 0 15px rgba(56, 189, 248, 0.3);
                z-index: 99999999;
                font-size: 13px;
                font-weight: bold;
                text-align: center;
                width: 90%;
                max-width: 360px;
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 8px;
                animation: slideDownToast 0.4s ease-out;
            `;
            document.body.appendChild(toastBox);
        }

        toastBox.innerHTML = msg;
        toastBox.style.display = 'flex';

        setTimeout(() => {
            if (toastBox) toastBox.style.display = 'none';
        }, 5000);
    }

    function askForConfirmation(onConfirm) {
        const msg = `هل أنت متأكد من خصم ${parseInt(currentEntryFee, 10).toLocaleString('en-US')} ZN للاشتراك في الساحة الكبرى؟`;
        if (tele && tele.showConfirm) {
            tele.showConfirm(msg, (confirmed) => {
                if (confirmed) onConfirm();
            });
        } else {
            const modal = document.getElementById('confirm-modal');
            const feeText = document.getElementById('confirm-fee-text');
            if (feeText) feeText.innerHTML = formatNumberHTML(currentEntryFee, " ZN");
            if (modal) {
                pendingConfirmCallback = onConfirm;
                modal.style.display = 'flex';
            } else if (confirm(msg)) {
                onConfirm();
            }
        }
    }

    window.onConfirmJoin = function(confirmed) {
        const modal = document.getElementById('confirm-modal');
        if (modal) modal.style.display = 'none';
        if (confirmed && typeof pendingConfirmCallback === 'function') {
            pendingConfirmCallback();
        }
        pendingConfirmCallback = null;
    };

    function getStoredBalance() {
        if (window.userState && window.userState.balance !== undefined) {
            return parseFloat(window.userState.balance) || 0;
        }
        if (window.PlayerData && window.PlayerData.balance !== undefined) {
            return parseFloat(window.PlayerData.balance) || 0;
        }
        if (window.GameState && window.GameState.balance !== undefined) {
            return parseFloat(window.GameState.balance) || 0;
        }
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        const num = bal !== null ? parseFloat(bal) : 0;
        return isNaN(num) ? 0 : num;
    }

    // --- إدارة تزامن الرصيد مع كافة المكونات اللحظية ---
    function setStoredBalance(newBalance, animate = true) {
        if (newBalance !== undefined && newBalance !== null) {
            const numVal = Math.round((parseFloat(newBalance) || 0) * 100) / 100;
            const oldVal = currentDisplayBalance || getStoredBalance();
            
            // التحديث الشامل لكافة الكائنات
            if (window.userState) window.userState.balance = numVal;
            if (window.PlayerData) window.PlayerData.balance = numVal;
            if (window.GameState) window.GameState.balance = numVal;
            
            localStorage.setItem('zn_balance', numVal.toString());
            localStorage.setItem('user_balance', numVal.toString());
            
            // تحديث عناصر الواجهة
            if (animate) {
                animateCounter('top-balance-games', oldVal, numVal, 800, " ZN");
            } else {
                const gameBalEl = document.getElementById('top-balance-games');
                if (gameBalEl) gameBalEl.innerHTML = formatNumberHTML(numVal, " ZN");
            }
            
            currentDisplayBalance = numVal;

            if (typeof window.setBalance === 'function') {
                window.setBalance(numVal);
            }

            // تحديث رصيد الصفحة الرئيسية إن وجد
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
        const arenaTab = document.getElementById('tab-arena');
        const soonTab = document.getElementById('tab-soon');
        const arenaContent = document.getElementById('content-arena');
        const soonContent = document.getElementById('content-soon');

        if (tabName === 'arena') {
            if (arenaTab) { arenaTab.classList.add('active'); arenaTab.style.opacity = '1'; }
            if (soonTab) { soonTab.classList.remove('active'); soonTab.style.opacity = '0.6'; }
            if (arenaContent) arenaContent.style.display = 'block';
            if (soonContent) soonContent.style.display = 'none';
        } else {
            if (soonTab) { soonTab.classList.add('active'); soonTab.style.opacity = '1'; }
            if (arenaTab) { arenaTab.classList.remove('active'); arenaTab.style.opacity = '0.6'; }
            if (arenaContent) arenaContent.style.display = 'none';
            if (soonContent) soonContent.style.display = 'block';
        }
    };

    async function fetchArenaStatus() {
        if (statusRetryTimeout) {
            clearTimeout(statusRetryTimeout);
            statusRetryTimeout = null;
        }

        try {
            const initData = tele?.initData || "";

            const response = await fetch('/api/games/status', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({ initData: initData })
            });
            
            if (!response.ok) throw new Error("Server Error");
            
            const data = await response.json();
            
            if (data.success) {
                if (data.entry_fee) currentEntryFee = data.entry_fee;
                if (data.lock_seconds) currentLockSeconds = data.lock_seconds;

                const subtext = document.getElementById('arena-subtext');
                if (subtext) subtext.innerText = `سحب تلقائي مستمر! رسوم الاشتراك: ${parseInt(currentEntryFee, 10).toLocaleString('en-US')} ZN`;

                if (data.balance !== undefined) {
                    setStoredBalance(data.balance, true);
                }
                
                currentRoundId = data.round_id;
                arenaEndTime = parseInt(data.end_time) || 0;
                hasCheckedResults = false;
                
                // تحديث حالة الاشتراك من السيرفر
                hasJoinedCurrentRound = !!data.has_joined;
                
                updateArenaPrizes(data);
                startSmoothCountdown();
            }
        } catch (error) {
            console.error("خطأ جلب حالة الساحة:", error);
            const btn = document.getElementById('btn-join-arena');
            if (btn && btn.innerText.includes("جاري التحميل")) {
                btn.innerText = "تعذر الاتصال، جاري إعادة المحاولة...";
            }
            statusRetryTimeout = setTimeout(fetchArenaStatus, 4000);
        }
    }

    function updateArenaPrizes(data) {
        const newPool = parseFloat(data.prize_pool) || 0;
        const oldPool = currentPrizePool;
        
        animateCounter('prize-pool', oldPool, newPool, 900, " ZN");
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
            
            if (timeLeft <= 60 && timeLeft > 0) {
                timerEl.classList.add('timer-warning');
            } else {
                timerEl.classList.remove('timer-warning');
            }
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
            // اعتماد المتغير الديناميكي لحظياً
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
        if (isJoining || hasJoinedCurrentRound) return;

        const currentBal = getStoredBalance();
        if (currentBal < currentEntryFee) {
            showNotification(`⚠️ رصيدك غير كافٍ للدخول في الساحة (تتطلب ${parseInt(currentEntryFee, 10).toLocaleString('en-US')} ZN).`);
            return;
        }

        askForConfirmation(() => {
            executeJoinArena();
        });
    };

    async function executeJoinArena() {
        if (isJoining) return;
        isJoining = true;

        const btn = document.getElementById('btn-join-arena');
        if (btn) {
            btn.disabled = true;
            btn.innerText = "جاري الدخول... ⏳";
        }

        try {
            const initData = tele?.initData || "";

            const response = await fetch('/api/games/join', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({ initData: initData })
            });
            
            if (!response.ok) throw new Error("Server Error");
            
            const data = await response.json();
            
            if (data.success) {
                // 1. تحديث متغير الاشتراك المحلي فوراً
                hasJoinedCurrentRound = true;

                // 2. تحديث الرصيد والجوائز
                if (data.new_balance !== undefined) {
                    setStoredBalance(data.new_balance, true);
                }
                if (data.prize_pool !== undefined) {
                    updateArenaPrizes(data);
                }

                // 3. تحديث زر الواجهة فوراً وقفله
                if (btn) {
                    btn.disabled = true;
                    btn.classList.add('btn-disabled');
                    btn.innerText = "أنت مشترك بالفعل ✅";
                }

                showNotification("🎉 تم دخول الساحة بنجاح! نتمنى لك التوفيق.");
            } else {
                showNotification("⚠️ " + (data.message || data.error || "تعذر الاشتراك"));
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = `⚔️ دخول الساحة (${parseInt(currentEntryFee, 10).toLocaleString('en-US')} ZN)`;
                }
            }
        } catch (error) {
            showNotification("حدث خطأ في الاتصال بالخادم. حاول مجدداً.");
            if (btn) {
                btn.disabled = false;
                btn.innerText = `⚔️ دخول الساحة (${parseInt(currentEntryFee, 10).toLocaleString('en-US')} ZN)`;
            }
        } finally {
            isJoining = false;
        }
    }

    function showDrawModal(state, refundFee = 0) {
        const modal = document.getElementById('draw-modal');
        const refundedEl = document.getElementById('draw-refunded');
        const winnersEl = document.getElementById('draw-winners');
        const refundAmountEl = document.getElementById('refund-amount-display');

        if (refundedEl) refundedEl.style.display = 'none';
        if (winnersEl) winnersEl.style.display = 'none';
        
        if (state === 'refunded' && refundedEl) {
            refundedEl.style.display = 'block';
            if (refundAmountEl) {
                refundAmountEl.innerHTML = `+${formatNumberHTML(refundFee, " ZN")}`;
            }
        }
        
        if (state === 'winners' && winnersEl) {
            winnersEl.style.display = 'block';
        }

        if (modal) modal.style.display = 'flex';
    }

    window.closeDrawModal = function() {
        const modal = document.getElementById('draw-modal');
        if (modal) modal.style.display = 'none';
        fetchArenaStatus();
    };

    async function fetchRoundResults(roundId, retries = 0) {
        if (!roundId) return;

        if (retries > 5) {
            fetchArenaStatus();
            return;
        }

        try {
            const initData = tele?.initData || "";
            const response = await fetch('/api/games/results', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({ initData: initData, round_id: roundId })
            });
            
            if (!response.ok) {
                setTimeout(() => { fetchRoundResults(roundId, retries + 1); }, 2000);
                return;
            }
            
            const data = await response.json();
            
            if (data.success) {
                if (data.new_balance !== undefined) {
                    setStoredBalance(data.new_balance, true);
                }

                if (data.status === 'refunded') {
                    const refundFee = data.refund_amount || currentEntryFee;
                    showDrawModal('refunded', refundFee);
                } else if (data.status === 'completed') {
                    renderWinners(data.winners || []);
                    showDrawModal('winners');
                } else {
                    setTimeout(() => { fetchRoundResults(roundId, retries + 1); }, 2000);
                }
            }
        } catch (e) {
            console.error("خطأ جلب النتائج:", e);
            setTimeout(() => { fetchRoundResults(roundId, retries + 1); }, 2000);
        }
    }

    // --- خادم الفحص المباشر في الخلفية للتنبيه بالمرتجعات وحجم الرصيد ---
    async function checkBackgroundNotifications() {
        try {
            const initData = tele?.initData || "";
            if (!initData) return;

            const response = await fetch('/api/games/check_notifications', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({ initData: initData })
            });

            if (!response.ok) return;
            const data = await response.json();

            if (data.success) {
                if (data.balance !== undefined) {
                    setStoredBalance(data.balance, true);
                }
                
                // التنبيه المباشر بالمرتجع عند توفره
                if (data.refund && data.refund > 0) {
                    triggerGlobalToast(`💰 تم استرداد المبلغ بنجاح لعدم اكتمال العدد المطلوب في الساحة (+${data.refund} ZN)`);
                    showDrawModal('refunded', data.refund);
                }
            }
        } catch (e) {
            console.error("خطأ فحص المرتجعات الخلفية:", e);
        }
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
                <div class="winner-item" style="animation-delay: ${index * 0.1}s;">
                    <span style="color: #fff; font-weight: bold; font-size: 13px;">
                        ${medals[index] || '🏅'} ${name}
                    </span>
                    <span style="color: #2ecc71; font-weight: bold; font-size: 13px;">
                        +${prize} ZN
                    </span>
                </div>
            `;
        });
    }

    // تشغيل الفحص الدوري كل 4 ثوانٍ لضمان المزامنة في الوقت الفعلي
    if (backgroundSyncInterval) clearInterval(backgroundSyncInterval);
    backgroundSyncInterval = setInterval(checkBackgroundNotifications, 4000);

    window.addEventListener('pageshow', () => {
        syncGameBalance();
        fetchArenaStatus();
        checkBackgroundNotifications();
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            syncGameBalance();
            fetchArenaStatus();
            checkBackgroundNotifications();
        }
    });

    syncGameBalance();
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", () => {
            fetchArenaStatus();
            checkBackgroundNotifications();
        });
    } else {
        fetchArenaStatus();
        checkBackgroundNotifications();
    }
})();

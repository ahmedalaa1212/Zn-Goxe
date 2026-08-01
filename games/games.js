// games/games.js
(function initGamesModule() {
    let isJoining = false;
    let currentRoundId = null;
    let arenaEndTime = 0;
    let countdownInterval = null;
    let hasCheckedResults = false;
    let statusRetryTimeout = null;
    let pendingConfirmCallback = null;

    let currentEntryFee = 1000;
    let currentLockSeconds = 15;
    let currentDisplayBalance = 0;
    let currentPrizePool = 0;

    const tele = window.Telegram?.WebApp;

    // --- العداد البصري التدريجي الانسيابي (Speedometer Dynamic Counter) ---
    function animateCounter(elementId, startVal, endVal, duration = 800, suffix = " ZN") {
        const el = document.getElementById(elementId);
        if (!el) return;

        let startTimestamp = null;
        const startNum = parseFloat(startVal) || 0;
        const endNum = parseFloat(endVal) || 0;

        if (startNum === endNum) {
            el.innerText = `${Math.floor(endNum).toLocaleString('en-US')}${suffix}`;
            return;
        }

        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            
            // معادلة تباطؤ انسيابية (easeOutCubic) تشبه عداد السرعة
            const easeProgress = 1 - Math.pow(1 - progress, 3);
            const currentVal = startNum + (endNum - startNum) * easeProgress;

            el.innerText = `${Math.floor(currentVal).toLocaleString('en-US')}${suffix}`;

            if (progress < 1) {
                window.requestAnimationFrame(step);
            } else {
                el.innerText = `${Math.floor(endNum).toLocaleString('en-US')}${suffix}`;
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

    function askForConfirmation(onConfirm) {
        const msg = `هل أنت متأكد من خصم ${currentEntryFee.toLocaleString('en-US')} ZN للاشتراك في الساحة الكبرى؟`;
        if (tele && tele.showConfirm) {
            tele.showConfirm(msg, (confirmed) => {
                if (confirmed) onConfirm();
            });
        } else {
            const modal = document.getElementById('confirm-modal');
            const feeText = document.getElementById('confirm-fee-text');
            if (feeText) feeText.innerText = `${currentEntryFee.toLocaleString('en-US')} ZN`;
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
        if (window.GameState && window.GameState.balance !== undefined && window.GameState.balance !== null) {
            const val = parseFloat(window.GameState.balance);
            return isNaN(val) ? 0 : val;
        }
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        const num = bal !== null ? parseFloat(bal) : 0;
        return isNaN(num) ? 0 : num;
    }

    function setStoredBalance(newBalance, animate = true) {
        if (newBalance !== undefined && newBalance !== null) {
            const numVal = parseFloat(newBalance);
            if (!isNaN(numVal)) {
                const oldVal = currentDisplayBalance || getStoredBalance();
                
                if (window.GameState) window.GameState.balance = numVal;
                localStorage.setItem('zn_balance', numVal.toString());
                localStorage.setItem('user_balance', numVal.toString());
                
                if (animate) {
                    animateCounter('top-balance-games', oldVal, numVal, 800, " ZN");
                } else {
                    const gameBalEl = document.getElementById('top-balance-games');
                    if (gameBalEl) gameBalEl.innerText = `${Math.floor(numVal).toLocaleString('en-US')} ZN`;
                }
                
                currentDisplayBalance = numVal;

                if (typeof window.setBalance === 'function') {
                    window.setBalance(numVal);
                }
            }
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
                if (subtext) subtext.innerText = `سحب تلقائي مستمر! رسوم الاشتراك: ${currentEntryFee.toLocaleString('en-US')} ZN`;

                if (data.balance !== undefined) {
                    setStoredBalance(data.balance, true);
                }
                
                currentRoundId = data.round_id;
                arenaEndTime = parseInt(data.end_time) || 0;
                hasCheckedResults = false;
                
                updateArenaPrizes(data);
                startSmoothCountdown(data.has_joined);
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
        const newPool = data.prize_pool || 0;
        const oldPool = currentPrizePool;
        
        animateCounter('prize-pool', oldPool, newPool, 900, " ZN");
        currentPrizePool = newPool;
        
        const p1 = document.getElementById('prize-1');
        const p2 = document.getElementById('prize-2');
        const p3 = document.getElementById('prize-3');
        const p4 = document.getElementById('prize-4');
        const p5 = document.getElementById('prize-5');

        if (p1) p1.innerText = Math.floor(newPool * 0.30).toLocaleString('en-US') + " ZN";
        if (p2) p2.innerText = Math.floor(newPool * 0.25).toLocaleString('en-US') + " ZN";
        if (p3) p3.innerText = Math.floor(newPool * 0.20).toLocaleString('en-US') + " ZN";
        if (p4) p4.innerText = Math.floor(newPool * 0.15).toLocaleString('en-US') + " ZN";
        if (p5) p5.innerText = Math.floor(newPool * 0.10).toLocaleString('en-US') + " ZN";
    }

    function startSmoothCountdown(hasJoined) {
        if (countdownInterval) clearInterval(countdownInterval);
        timerTick(hasJoined);
        countdownInterval = setInterval(() => timerTick(hasJoined), 1000);
    }

    function timerTick(hasJoined) {
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
            if (!hasJoined) {
                btn.disabled = false;
                btn.classList.remove('btn-disabled');
                btn.innerText = `⚔️ دخول الساحة (${currentEntryFee.toLocaleString('en-US')} ZN)`;
            } else {
                btn.disabled = true;
                btn.classList.add('btn-disabled');
                btn.innerText = "أنت مشترك بالفعل ✅";
            }
        }
    }

    window.joinArena = function() {
        if (isJoining) return;

        const currentBal = getStoredBalance();
        if (currentBal < currentEntryFee) {
            showNotification(`⚠️ رصيدك غير كافٍ للدخول في الساحة (تتطلب ${currentEntryFee.toLocaleString('en-US')} ZN).`);
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
            const currentBal = getStoredBalance();

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
                // تطبيق القاعدة الذهبية: تحديث الواجهة والعداد البصري فوراً من الـ Response بدون إعادة جلب البيانات بالكامل
                if (data.new_balance !== undefined) {
                    setStoredBalance(data.new_balance, true);
                } else {
                    setStoredBalance(currentBal - currentEntryFee, true);
                }
                
                showNotification("🎉 تم دخول الساحة بنجاح! نتمنى لك التوفيق.");
                fetchArenaStatus(); 
            } else {
                showNotification("⚠️ " + (data.message || data.error || "تعذر الاشتراك"));
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = `⚔️ دخول الساحة (${currentEntryFee.toLocaleString('en-US')} ZN)`;
                }
            }
        } catch (error) {
            showNotification("حدث خطأ في الاتصال بالخادم. حاول مجدداً.");
            if (btn) {
                btn.disabled = false;
                btn.innerText = `⚔️ دخول الساحة (${currentEntryFee.toLocaleString('en-US')} ZN)`;
            }
        } finally {
            isJoining = false;
        }
    }

    function showDrawModal(state) {
        const modal = document.getElementById('draw-modal');
        const refundedEl = document.getElementById('draw-refunded');
        const winnersEl = document.getElementById('draw-winners');

        if (refundedEl) refundedEl.style.display = 'none';
        if (winnersEl) winnersEl.style.display = 'none';
        
        if (modal) modal.style.display = 'flex';
        if (state === 'refunded' && refundedEl) refundedEl.style.display = 'block';
        if (state === 'winners' && winnersEl) winnersEl.style.display = 'block';
    }

    window.closeDrawModal = function() {
        const modal = document.getElementById('draw-modal');
        if (modal) modal.style.display = 'none';
        fetchArenaStatus();
    };

    async function fetchRoundResults(roundId, retries = 0) {
        if (!roundId) return;

        if (retries > 10) {
            console.warn("تأخر السيرفر في إحراز النتائج.");
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
                // القاعدة الذهبية: تحديث سلس بالعداد مباشرة بدون استدعاء شبكي خارجي
                if (data.new_balance !== undefined) {
                    setStoredBalance(data.new_balance, true);
                }

                if (data.status === 'refunded') {
                    const msgEl = document.getElementById('refund-msg-text');
                    if (msgEl) msgEl.innerText = `تمت إعادة رسوم الدخول (${currentEntryFee.toLocaleString('en-US')} ZN) بالكامل إلى محفظتك بدون أي خصم.`;
                    showDrawModal('refunded');
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

    function renderWinners(winners) {
        const list = document.getElementById('winners-list');
        if (!list) return;

        list.innerHTML = '';
        const medals = ['🥇', '🥈', '🥉', '🏅', '🏅'];
        
        winners.forEach((winner, index) => {
            let name = winner.name || `مستخدم #${(winner.uid || '00000').substring(0,5)}`;
            let prize = (winner.prize || 0).toLocaleString('en-US');
            
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

    window.addEventListener('pageshow', () => {
        syncGameBalance();
        fetchArenaStatus();
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            syncGameBalance();
            fetchArenaStatus();
        }
    });

    syncGameBalance();
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", fetchArenaStatus);
    } else {
        fetchArenaStatus();
    }
})();

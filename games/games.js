// games/games.js
let isJoining = false;
let currentRoundId = null;
let arenaEndTime = 0;
let countdownInterval = null;
let hasCheckedResults = false;

// --- أدوات المزامنة الموحدة للرصيد ---
function getStoredBalance() {
    const bal = localStorage.getItem('user_balance') || localStorage.getItem('zn_balance');
    return bal !== null ? parseFloat(bal) : null;
}

function setStoredBalance(newBalance) {
    if (newBalance !== undefined && newBalance !== null) {
        const strVal = newBalance.toString();
        localStorage.setItem('user_balance', strVal);
        localStorage.setItem('zn_balance', strVal);
    }
}

function syncGameBalance() {
    const stored = getStoredBalance();
    if (stored !== null) {
        const gameBalEl = document.getElementById('top-balance-games');
        if (gameBalEl) {
            gameBalEl.innerText = `ZN ${Math.floor(stored).toLocaleString()}`;
        }
    }
}

window.switchGameTab = function(tabName) {
    const arenaTab = document.getElementById('tab-arena');
    const soonTab = document.getElementById('tab-soon');
    const arenaContent = document.getElementById('content-arena');
    const soonContent = document.getElementById('content-soon');

    if (tabName === 'arena') {
        if (arenaTab) { arenaTab.style.border = '2px solid #ffcc00'; arenaTab.style.opacity = '1'; }
        if (soonTab) { soonTab.style.border = '2px solid transparent'; soonTab.style.opacity = '0.6'; }
        
        if (arenaContent) arenaContent.style.display = 'block';
        if (soonContent) soonContent.style.display = 'none';
    } else {
        if (soonTab) { soonTab.style.border = '2px solid #00ffcc'; soonTab.style.opacity = '1'; }
        if (arenaTab) { arenaTab.style.border = '2px solid transparent'; arenaTab.style.opacity = '0.6'; }
        
        if (arenaContent) arenaContent.style.display = 'none';
        if (soonContent) soonContent.style.display = 'block';
    }
};

async function fetchArenaStatus() {
    try {
        const initData = window.Telegram?.WebApp?.initData;
        if (!initData) return;

        const response = await fetch('/api/games/status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData })
        });
        
        if (!response.ok) throw new Error("Server Error");
        
        const data = await response.json();
        
        if (data.success) {
            if (data.balance !== undefined) {
                setStoredBalance(data.balance);
            }
            syncGameBalance();
            
            currentRoundId = data.round_id;
            arenaEndTime = data.end_time;
            hasCheckedResults = false;
            
            updateArenaPrizes(data);
            startSmoothCountdown(data.has_joined);
        }
    } catch (error) {
        console.error("Error fetching game status:", error);
        const btn = document.getElementById('btn-join-arena');
        if (btn && btn.innerText.includes("جاري التحميل")) {
            btn.innerText = "خطأ في الاتصال، جاري إعادة المحاولة...";
        }
        setTimeout(fetchArenaStatus, 3000);
    }
}

function updateArenaPrizes(data) {
    const prizePoolEl = document.getElementById('prize-pool');
    if (prizePoolEl) prizePoolEl.innerText = data.prize_pool.toLocaleString() + " ZN";
    
    const p1 = document.getElementById('prize-1');
    const p2 = document.getElementById('prize-2');
    const p3 = document.getElementById('prize-3');
    const p4 = document.getElementById('prize-4');
    const p5 = document.getElementById('prize-5');

    if (p1) p1.innerText = Math.floor(data.prize_pool * 0.30).toLocaleString() + " ZN";
    if (p2) p2.innerText = Math.floor(data.prize_pool * 0.25).toLocaleString() + " ZN";
    if (p3) p3.innerText = Math.floor(data.prize_pool * 0.20).toLocaleString() + " ZN";
    if (p4) p4.innerText = Math.floor(data.prize_pool * 0.15).toLocaleString() + " ZN";
    if (p5) p5.innerText = Math.floor(data.prize_pool * 0.10).toLocaleString() + " ZN";
}

function startSmoothCountdown(hasJoined) {
    if (countdownInterval) clearInterval(countdownInterval);
    timerTick(hasJoined);
    countdownInterval = setInterval(() => timerTick(hasJoined), 1000);
}

function timerTick(hasJoined) {
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

    if (timeLeft <= 15 && timeLeft > 0) {
        btn.disabled = true;
        btn.classList.add('btn-disabled');
        btn.innerText = "تم إغلاق الاشتراك (جاري السحب⏳)";
    } else if (timeLeft === 0) {
        btn.disabled = true;
        btn.classList.add('btn-disabled');
        btn.innerText = "جاري إعلان النتائج... 🔄";
        
        if (!hasCheckedResults) {
            hasCheckedResults = true;
            fetchRoundResults(currentRoundId, 0);
        }
    } else {
        if (!hasJoined) {
            btn.disabled = false;
            btn.classList.remove('btn-disabled');
            btn.innerText = "دخول الساحة (1000 ZN)";
        } else {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerText = "أنت مشترك بالفعل ✅";
        }
    }
}

window.joinArena = async function() {
    if (isJoining) return;
    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) {
        alert("⚠️ يجب فتح اللعبة من تليجرام لضمان الأمان.");
        return;
    }

    const btn = document.getElementById('btn-join-arena');
    if (btn) {
        btn.disabled = true;
        btn.innerText = "جاري الدخول... ⏳";
    }
    isJoining = true;

    try {
        const response = await fetch('/api/games/join', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData })
        });
        
        if (!response.ok) throw new Error("Server Error");
        
        const data = await response.json();
        
        if (data.success) {
            if (data.new_balance !== undefined) {
                setStoredBalance(data.new_balance);
            } else {
                let current = getStoredBalance();
                if (current !== null) setStoredBalance(current - 1000);
            }
            syncGameBalance();

            if (typeof window.fetchPlayerDataFromServer === 'function') {
                window.fetchPlayerDataFromServer();
            }
            fetchArenaStatus(); 
        } else {
            alert("⚠️ " + data.message);
            if (btn) {
                btn.disabled = false;
                btn.innerText = "دخول الساحة (1000 ZN)";
            }
        }
    } catch (error) {
        alert("حدث خطأ في الاتصال بالخادم. حاول مجدداً.");
        if (btn) {
            btn.disabled = false;
            btn.innerText = "دخول الساحة (1000 ZN)";
        }
    } finally {
        isJoining = false;
    }
};

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
    if (retries > 12) {
        console.warn("تأخر السيرفر في إصدار النتيجة.");
        fetchArenaStatus();
        return;
    }

    try {
        const initData = window.Telegram?.WebApp?.initData;
        const response = await fetch('/api/games/results', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData, round_id: roundId })
        });
        
        if (!response.ok) {
            setTimeout(() => { fetchRoundResults(roundId, retries + 1); }, 2000);
            return;
        }
        
        const data = await response.json();
        
        if (data.success) {
            if (data.new_balance !== undefined) {
                setStoredBalance(data.new_balance);
                syncGameBalance();
            }

            if (data.status === 'refunded') {
                showDrawModal('refunded');
            } else if (data.status === 'completed') {
                renderWinners(data.winners);
                showDrawModal('winners');
            } else {
                setTimeout(() => { fetchRoundResults(roundId, retries + 1); }, 2000);
            }
            
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                window.fetchPlayerDataFromServer();
            }
        }
    } catch (e) {
        console.error("Error fetching results", e);
        setTimeout(() => { fetchRoundResults(roundId, retries + 1); }, 2000);
    }
}

function renderWinners(winners) {
    const list = document.getElementById('winners-list');
    if (!list) return;

    list.innerHTML = '';
    const medals = ['🥇', '🥈', '🥉', '🏅', '🏅'];
    
    winners.forEach((winner, index) => {
        let name = winner.name || `User #${winner.uid.substring(0,5)}`;
        let prize = winner.prize.toLocaleString();
        
        list.innerHTML += `
            <div class="winner-item">
                <span style="color: #fff; font-weight: bold; font-size: 14px;">
                    ${medals[index] || '🏅'} ${name}
                </span>
                <span style="color: #00ff00; font-weight: bold;">
                    +${prize} ZN
                </span>
            </div>
        `;
    });
}

// --- مستمعات التنقل والمزامنة الفورية ---
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

// بدء التشغيل الفوري من الكاش ثم الاتصال بالسيرفر
syncGameBalance();
fetchArenaStatus();

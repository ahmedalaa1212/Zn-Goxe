// games/games.js
let isJoining = false;
let currentRoundId = null;
let arenaEndTime = 0;
let countdownInterval = null;
let hasCheckedResults = false;

window.switchGameTab = function(tabName) {
    const arenaTab = document.getElementById('tab-arena');
    const soonTab = document.getElementById('tab-soon');
    const arenaContent = document.getElementById('content-arena');
    const soonContent = document.getElementById('content-soon');

    if (tabName === 'arena') {
        arenaTab.style.border = '2px solid #ffcc00';
        arenaTab.style.opacity = '1';
        soonTab.style.border = '2px solid transparent';
        soonTab.style.opacity = '0.6';
        
        arenaContent.style.display = 'block';
        soonContent.style.display = 'none';
    } else {
        soonTab.style.border = '2px solid #00ffcc';
        soonTab.style.opacity = '1';
        arenaTab.style.border = '2px solid transparent';
        arenaTab.style.opacity = '0.6';
        
        arenaContent.style.display = 'none';
        soonContent.style.display = 'block';
    }
}

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
            const gameBalEl = document.getElementById('top-balance-games');
            if (gameBalEl) {
                gameBalEl.innerText = `ZN ${Math.floor(data.balance).toLocaleString()}`;
            }
            
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
    document.getElementById('prize-pool').innerText = data.prize_pool.toLocaleString() + " ZN";
    document.getElementById('prize-1').innerText = Math.floor(data.prize_pool * 0.30).toLocaleString() + " ZN";
    document.getElementById('prize-2').innerText = Math.floor(data.prize_pool * 0.25).toLocaleString() + " ZN";
    document.getElementById('prize-3').innerText = Math.floor(data.prize_pool * 0.20).toLocaleString() + " ZN";
    document.getElementById('prize-4').innerText = Math.floor(data.prize_pool * 0.15).toLocaleString() + " ZN";
    document.getElementById('prize-5').innerText = Math.floor(data.prize_pool * 0.10).toLocaleString() + " ZN";
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

    let m = Math.floor(timeLeft / 60);
    let s = timeLeft % 60;
    timerEl.innerText = `${m < 10 ? '0'+m : m}:${s < 10 ? '0'+s : s}`;

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
            fetchRoundResults(currentRoundId, 0); // نبدأ المحاولات من الصفر
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
    btn.disabled = true;
    btn.innerText = "جاري الدخول... ⏳";
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
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                window.fetchPlayerDataFromServer();
            }
            fetchArenaStatus(); 
        } else {
            alert("⚠️ " + data.message);
            btn.disabled = false;
            btn.innerText = "دخول الساحة (1000 ZN)";
        }
    } catch (error) {
        alert("حدث خطأ في الاتصال بالخادم. حاول مجدداً.");
        btn.disabled = false;
        btn.innerText = "دخول الساحة (1000 ZN)";
    } finally {
        isJoining = false;
    }
};

function showDrawModal(state) {
    const modal = document.getElementById('draw-modal');
    document.getElementById('draw-refunded').style.display = 'none';
    document.getElementById('draw-winners').style.display = 'none';
    
    modal.style.display = 'flex';
    if (state === 'refunded') document.getElementById('draw-refunded').style.display = 'block';
    if (state === 'winners') document.getElementById('draw-winners').style.display = 'block';
}

window.closeDrawModal = function() {
    document.getElementById('draw-modal').style.display = 'none';
    fetchArenaStatus();
}

// تعديل الدالة لمنع التعليق المستمر
async function fetchRoundResults(roundId, retries = 0) {
    if (retries > 12) { // أقصى حد للمحاولات، بعدها يتم إعادة تهيئة الساحة
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
    list.innerHTML = '';
    const medals = ['🥇', '🥈', '🥉', '🏅', '🏅'];
    
    winners.forEach((winner, index) => {
        let name = winner.name || `User #${winner.uid.substring(0,5)}`;
        let prize = winner.prize.toLocaleString();
        
        list.innerHTML += `
            <div class="winner-item">
                <span style="color: #fff; font-weight: bold; font-size: 14px;">
                    ${medals[index]} ${name}
                </span>
                <span style="color: #00ff00; font-weight: bold;">
                    +${prize} ZN
                </span>
            </div>
        `;
    });
}

fetchArenaStatus();

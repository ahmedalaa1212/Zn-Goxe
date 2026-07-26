let updateInterval;
let isJoining = false;
let currentRoundId = null;

// تحديث الرصيد العلوي
window.updateGamesUI = function() {
    const pData = window.PlayerData;
    if (!pData) return;
    const gameBalEl = document.getElementById('top-balance-games');
    if (gameBalEl) {
        gameBalEl.innerText = `ZN ${Math.floor(pData.balance).toLocaleString()}`;
    }
};

// جلب حالة الساحة من السيرفر
async function fetchArenaStatus() {
    try {
        const initData = window.Telegram?.WebApp?.initData;
        const response = await fetch('/api/games/status', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData })
        });
        const data = await response.json();
        
        if (data.success) {
            updateArenaUI(data);
        }
    } catch (error) {
        console.error("خطأ في جلب حالة اللعبة:", error);
    }
}

// تحديث واجهة الساحة
function updateArenaUI(data) {
    currentRoundId = data.round_id;
    const now = Math.floor(Date.now() / 1000);
    let timeLeft = data.end_time - now;
    
    const btn = document.getElementById('btn-join-arena');
    const timerEl = document.getElementById('arena-timer');
    
    if (timeLeft < 0) timeLeft = 0;

    // تنسيق الوقت
    let m = Math.floor(timeLeft / 60);
    let s = timeLeft % 60;
    timerEl.innerText = `${m < 10 ? '0'+m : m}:${s < 10 ? '0'+s : s}`;

    // إغلاق الاشتراك في آخر 15 ثانية وعرض الأنيميشن
    if (timeLeft <= 15 && timeLeft > 0) {
        btn.disabled = true;
        btn.classList.add('btn-disabled');
        btn.innerText = "تم إغلاق الاشتراك (جاري السحب⏳)";
        showDrawModal('waiting');
    } else if (timeLeft === 0 && document.getElementById('draw-modal').style.display === 'flex' && document.getElementById('draw-waiting').style.display === 'block') {
        // انتهى الوقت، اطلب النتائج
        fetchRoundResults(currentRoundId);
    } else {
        // الوقت متاح
        if (!data.has_joined) {
            btn.disabled = false;
            btn.classList.remove('btn-disabled');
            btn.innerText = "دخول الساحة (1000 ZN)";
        } else {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            btn.innerText = "أنت مشترك بالفعل ✅";
        }
    }

    // تحديث الأرقام (الفرونت إند بيستقبل الـ 45% جاهزة من السيرفر)
    document.getElementById('participants-count').innerText = data.participants;
    document.getElementById('prize-pool').innerText = data.prize_pool.toLocaleString() + " ZN";

    // تقسيم الجوائز المتوقع
    document.getElementById('prize-1').innerText = Math.floor(data.prize_pool * 0.30).toLocaleString() + " ZN";
    document.getElementById('prize-2').innerText = Math.floor(data.prize_pool * 0.25).toLocaleString() + " ZN";
    document.getElementById('prize-3').innerText = Math.floor(data.prize_pool * 0.20).toLocaleString() + " ZN";
    document.getElementById('prize-4').innerText = Math.floor(data.prize_pool * 0.15).toLocaleString() + " ZN";
    document.getElementById('prize-5').innerText = Math.floor(data.prize_pool * 0.10).toLocaleString() + " ZN";
}

// دالة الاشتراك في الساحة
window.joinArena = async function() {
    if (isJoining) return;
    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) {
        alert("⚠️ يجب فتح اللعبة من تليجرام.");
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
        const data = await response.json();
        
        if (data.success) {
            // تحديث الرصيد فوراً لو عندك دالة المزامنة
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                await window.fetchPlayerDataFromServer();
            }
            fetchArenaStatus(); // تحديث الواجهة
        } else {
            alert("⚠️ " + data.message);
            btn.disabled = false;
            btn.innerText = "دخول الساحة (1000 ZN)";
        }
    } catch (error) {
        alert("حدث خطأ في الاتصال.");
        btn.disabled = false;
    } finally {
        isJoining = false;
    }
};

// إدارة نوافذ السحب
function showDrawModal(state) {
    const modal = document.getElementById('draw-modal');
    document.getElementById('draw-waiting').style.display = 'none';
    document.getElementById('draw-refunded').style.display = 'none';
    document.getElementById('draw-winners').style.display = 'none';
    
    modal.style.display = 'flex';
    if (state === 'waiting') document.getElementById('draw-waiting').style.display = 'block';
    if (state === 'refunded') document.getElementById('draw-refunded').style.display = 'block';
    if (state === 'winners') document.getElementById('draw-winners').style.display = 'block';
}

window.closeDrawModal = function() {
    document.getElementById('draw-modal').style.display = 'none';
}

// جلب نتائج السحب بعد انتهاء الوقت
async function fetchRoundResults(roundId) {
    try {
        const initData = window.Telegram?.WebApp?.initData;
        const response = await fetch('/api/games/results', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData, round_id: roundId })
        });
        const data = await response.json();
        
        if (data.success) {
            if (data.status === 'refunded') {
                showDrawModal('refunded');
            } else if (data.status === 'completed') {
                renderWinners(data.winners);
                showDrawModal('winners');
            }
            // تحديث الرصيد للمستخدم لاحتمال فوزه أو استرداده الفلوس
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                window.fetchPlayerDataFromServer();
            }
        }
    } catch (e) {
        console.error("خطأ في جلب النتائج", e);
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

// التشغيل
window.updateGamesUI();
fetchArenaStatus();
// تحديث الحالة كل 3 ثواني
updateInterval = setInterval(fetchArenaStatus, 3000);

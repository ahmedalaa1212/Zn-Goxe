const USER_ID = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "demo_user";
let currentLivePrice = 0.05;

// بدء تحديث السعر والمؤشرات فور تحميل الصفحة
document.addEventListener('DOMContentLoaded', () => {
    loadData();
    setInterval(updatePriceTicker, 1000); // تحديث السعر كل ثانية
});

function updatePriceTicker() {
    // محاكاة التذبذب اللحظي المباشر للسعر بالثانية
    const fluctuation = (Math.random() - 0.49) * 0.0008;
    currentLivePrice = Math.max(0.01, currentLivePrice + fluctuation);
    document.getElementById('livePrice').innerText = `$${currentLivePrice.toFixed(4)}`;
}

async function loadData() {
    try {
        const res = await fetch(`/api/leaderboard/data?user_id=${USER_ID}`);
        const data = await res.json();
        
        if (data.success) {
            currentLivePrice = data.live_price;
            
            // تحديث المجمّع الكلي
            const total = data.global_total;
            const max = data.max_limit;
            const percentage = Math.min(100, (total / max) * 100);
            
            document.getElementById('poolText').innerText = `${total.toLocaleString()} / ${max.toLocaleString()} ZNX`;
            document.getElementById('poolProgress').style.width = `${percentage}%`;

            renderLeaderboard(data.leaderboard);
        }
    } catch (err) {
        console.error("خطأ في تحميل البيانات:", err);
    }
}

function calculatePreview() {
    const pts = parseFloat(document.getElementById('pointsInput').value) || 0;
    let rate = 10;

    if (pts >= 25000000000) rate = 4000;
    else if (pts >= 8000000000) rate = 1600;
    else if (pts >= 2000000000) rate = 600;
    else if (pts >= 500000000) rate = 200;
    else if (pts >= 100000000) rate = 80;
    else if (pts >= 20000000) rate = 30;
    else rate = 10;

    const znxGained = pts / rate;
    document.getElementById('znxPreview').innerText = `${znxGained.toFixed(4)} ZNX`;
}

async function submitConversion() {
    const points = parseFloat(document.getElementById('pointsInput').value);
    if (!points || points <= 0) {
        alert("يرجى إدخال كمية نقاط صالحة");
        return;
    }

    try {
        const res = await fetch('/api/leaderboard/convert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: USER_ID, points: points })
        });
        
        const result = await res.json();
        if (result.success) {
            alert(`تم التحويل بنجاح! حصلت على ${result.data.znx_gained} ZNX`);
            document.getElementById('pointsInput').value = '';
            calculatePreview();
            loadData();
        } else {
            alert(`فشل التحويل: ${result.message}`);
        }
    } catch (err) {
        alert("حدث خطأ أثناء الاتصال بالسيرفر.");
    }
}

function renderLeaderboard(list) {
    const podiumArea = document.getElementById('podiumArea');
    const leaderboardList = document.getElementById('leaderboardList');
    
    podiumArea.innerHTML = '';
    leaderboardList.innerHTML = '';

    // عرض أول 3 في المنصة
    if (list[0]) podiumArea.innerHTML += createPodiumCard(list[0], 1, 'rank-1');
    if (list[1]) podiumArea.innerHTML += createPodiumCard(list[1], 2, 'rank-2');
    if (list[2]) podiumArea.innerHTML += createPodiumCard(list[2], 3, 'rank-3');

    // باقي القائمة
    for (let i = 3; i < list.length; i++) {
        leaderboardList.innerHTML += `
            <div class="list-item">
                <span>#${i + 1} ${list[i].name}</span>
                <span style="color: #38bdf8; font-weight: bold;">${list[i].znx_balance} ZNX</span>
            </div>
        `;
    }
}

function createPodiumCard(user, rank, rankClass) {
    return `
        <div class="podium-card ${rankClass}">
            <div style="font-weight: bold;">#${rank}</div>
            <div style="font-size: 0.85rem; overflow: hidden; text-overflow: ellipsis;">${user.name}</div>
            <div style="color: #38bdf8; font-size: 0.8rem; font-weight: bold;">${user.znx_balance} ZNX</div>
        </div>
    `;
}

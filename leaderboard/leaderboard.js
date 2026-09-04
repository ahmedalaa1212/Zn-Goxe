const USER_ID = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || "5102387551";
let userData = { balance: 0, usd_balance: 0, znx_balance: 0 };
let currentTier = null;
let currentLivePrice = 0.0524;

document.addEventListener('DOMContentLoaded', () => {
    initApp();
    setInterval(tickLivePrice, 1000); // تحديث السعر بالثانية
});

async function initApp() {
    try {
        const res = await fetch(`/api/leaderboard/init?user_id=${USER_ID}`);
        const data = await res.json();
        
        if (data.success) {
            userData = data.user;
            currentTier = data.current_tier;
            currentLivePrice = data.live_price;

            updateBalancesUI();
            renderTiersUI(data.tiers_all);
            renderLeaderboardUI(data.leaderboard);
        }
    } catch (err) {
        console.error("خطأ في الاتصال بالسيرفر:", err);
    }
}

function updateBalancesUI() {
    document.getElementById('znBalance').innerText = Math.floor(userData.balance).toLocaleString();
    document.getElementById('usdBalance').innerText = `$${userData.usd_balance.toFixed(2)}`;
    document.getElementById('znxBalance').innerText = userData.znx_balance.toFixed(4);
}

function tickLivePrice() {
    // التذبذب اللحظي لسعر العملة بالثانية
    const delta = (Math.random() - 0.48) * 0.0004;
    currentLivePrice = Math.max(0.01, currentLivePrice + delta);
    document.getElementById('livePrice').innerText = `$${currentLivePrice.toFixed(4)}`;
}

function selectOption(type) {
    const input = document.getElementById('convertInput');
    if (type === 'max') {
        input.value = userData.balance;
    } else if (type === 'half') {
        input.value = Math.floor(userData.balance / 2);
    } else if (type === 'min') {
        input.value = currentTier ? currentTier.rate : 10;
    }
    onInputChange();
}

function onInputChange() {
    const points = parseFloat(document.getElementById('convertInput').value) || 0;
    const rate = currentTier ? currentTier.rate : 10;
    const znxGained = points / rate;
    document.getElementById('znxPreview').innerText = `${znxGained.toFixed(4)} ZNX`;
}

async function submitConvert() {
    const amount = parseFloat(document.getElementById('convertInput').value);
    if (!amount || amount <= 0) {
        alert("يرجى تحديد كمية صالحة للتحويل");
        return;
    }

    try {
        const res = await fetch('/api/leaderboard/convert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: USER_ID, amount: amount })
        });
        const result = await res.json();

        if (result.success) {
            alert(`تم التحويل بنجاح! حصلت على ${result.data.znx_gained} ZNX`);
            document.getElementById('convertInput').value = '';
            onInputChange();
            initApp(); // إعادة تحميل الأرصدة والمتصدرين
        } else {
            alert(`فشل التحويل: ${result.message}`);
        }
    } catch (err) {
        alert("حدث خطأ أثناء إجراء التحويل.");
    }
}

function renderTiersUI(tiers) {
    const container = document.getElementById('tiersContainer');
    container.innerHTML = '';

    tiers.forEach(t => {
        const isCurrent = currentTier && currentTier.tier === t.tier;
        container.innerHTML += `
            <div class="tier-item ${isCurrent ? 'current' : ''}">
                <div>
                    <strong>${t.name}</strong> 
                    ${isCurrent ? '<span class="tier-badge-active">شريحتك الحالية</span>' : ''}
                    <div style="color: var(--text-muted); font-size: 0.75rem; margin-top:2px;">
                        سعر التحويل: 1 ZNX = ${t.rate} ZN
                    </div>
                </div>
                <div style="text-align: left; color: #38bdf8; font-weight: bold;">
                    حصة الشريحة: ${(t.quota / 1000000).toFixed(1)}M
                </div>
            </div>
        `;
    });
}

function renderLeaderboardUI(list) {
    const podium = document.getElementById('podiumContainer');
    const rankings = document.getElementById('rankingsContainer');
    podium.innerHTML = '';
    rankings.innerHTML = '';

    if (list.length >= 1) podium.innerHTML += createPodiumCard(list[0], 1, 'podium-1');
    if (list.length >= 2) podium.innerHTML += createPodiumCard(list[1], 2, 'podium-2');
    if (list.length >= 3) podium.innerHTML += createPodiumCard(list[2], 3, 'podium-3');

    for (let i = 3; i < list.length; i++) {
        rankings.innerHTML += `
            <div class="leader-row">
                <span>#${i + 1} ${list[i].name}</span>
                <span style="color:#38bdf8; font-weight:bold;">${list[i].total_znx_earned} ZNX</span>
            </div>
        `;
    }
}

function createPodiumCard(item, rank, pClass) {
    return `
        <div class="podium-item ${pClass}">
            <div style="font-size:0.75rem; color:var(--text-muted);"> المركز #${rank}</div>
            <div style="font-weight:bold; font-size:0.85rem; margin:3px 0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${item.name}</div>
            <div style="color:#38bdf8; font-weight:bold; font-size:0.8rem;">${item.total_znx_earned} ZNX</div>
        </div>
    `;
}

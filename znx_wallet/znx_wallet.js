function getUserId() {
    if (window.Telegram?.WebApp?.initDataUnsafe?.user?.id) {
        return String(window.Telegram.WebApp.initDataUnsafe.user.id);
    }
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('user_id') || urlParams.get('tg_id') || "5102387551";
}

let USER_ID = getUserId();
let userData = { balance: 0, usd_balance: 0, znx_balance: 0, total_znx_earned: 0 };
let currentTier = null;
let currentLivePrice = 0.0524;

document.addEventListener('DOMContentLoaded', () => {
    if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.ready();
        window.Telegram.WebApp.expand();
    }
    USER_ID = getUserId();
    initApp();
    setInterval(tickLivePrice, 1000);
});

function formatCoins(val, decimals = 2) {
    const num = parseFloat(val) || 0;
    const parts = num.toFixed(decimals).split('.');
    const integerPart = parseInt(parts[0], 10).toLocaleString('en-US');
    const decimalPart = parts[1];
    if (decimals === 0 || !decimalPart) {
        return integerPart;
    }
    return `${integerPart}<small class="dec">.${decimalPart}</small>`;
}

async function initApp() {
    try {
        const res = await fetch(`/api/leaderboard/init?user_id=${USER_ID}`);
        if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
        
        const data = await res.json();
        
        if (data.success) {
            userData = data.user;
            currentTier = data.current_tier;
            currentLivePrice = data.live_price;

            updateBalancesUI();
            updateGlobalStatsUI(data.global_total, data.max_global_znx);
            renderTiersUI(data.tiers_all);
            renderLeaderboardUI(data.leaderboard);
        } else {
            console.error("فشل الجلب:", data.message);
        }
    } catch (err) {
        console.error("خطأ الاتصال بالسيرفر:", err);
    }
}

function updateBalancesUI() {
    document.getElementById('znBalance').innerHTML = formatCoins(userData.balance || 0, 2);
    document.getElementById('usdBalance').innerHTML = `$${formatCoins(userData.usd_balance || 0, 2)}`;
    document.getElementById('znxBalance').innerHTML = formatCoins(userData.znx_balance || 0, 4);
}

function updateGlobalStatsUI(globalTotal, maxGlobal) {
    const total = globalTotal || 0;
    const max = maxGlobal || 35000000;
    const pct = Math.min(100, (total / max) * 100);
    
    document.getElementById('globalRatioText').innerHTML = `${formatCoins(total, 2)} / ${(max/1000000).toFixed(0)}M ZNX`;
    document.getElementById('globalProgressBar').style.width = `${pct}%`;
}

function tickLivePrice() {
    const delta = (Math.random() - 0.48) * 0.0004;
    currentLivePrice = Math.max(0.01, currentLivePrice + delta);
    document.getElementById('livePrice').innerText = `$${currentLivePrice.toFixed(4)}`;
}

function selectOption(type) {
    const input = document.getElementById('convertInput');
    const bal = userData.balance || 0;

    if (type === 'max') {
        input.value = bal;
    } else if (type === 'half') {
        input.value = (bal / 2).toFixed(2);
    } else if (type === 'min') {
        input.value = currentTier ? currentTier.rate : 10;
    }
    onInputChange();
}

function onInputChange() {
    const points = parseFloat(document.getElementById('convertInput').value) || 0;
    const rate = currentTier ? currentTier.rate : 10;
    const znxGained = points / rate;
    document.getElementById('znxPreview').innerHTML = `${formatCoins(znxGained, 4)} ZNX`;
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
            initApp();
        } else {
            alert(`تنبيه: ${result.message}`);
        }
    } catch (err) {
        alert("حدث خطأ أثناء الاتصال بالسيرفر لإجراء التحويل.");
    }
}

function renderTiersUI(tiers) {
    const container = document.getElementById('tiersContainer');
    container.innerHTML = '';

    if (!tiers) return;

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
                <div style="text-align: left; color: var(--accent-blue); font-weight: bold;">
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

    if (!list || list.length === 0) {
        rankings.innerHTML = '<div style="text-align:center; padding:15px; color:var(--text-muted);">لا يوجد متصدرين حالياً</div>';
        return;
    }

    if (list.length >= 1) podium.innerHTML += createPodiumCard(list[0], 1, 'podium-1');
    if (list.length >= 2) podium.innerHTML += createPodiumCard(list[1], 2, 'podium-2');
    if (list.length >= 3) podium.innerHTML += createPodiumCard(list[2], 3, 'podium-3');

    for (let i = 3; i < list.length; i++) {
        rankings.innerHTML += `
            <div class="leader-row">
                <span>#${i + 1} ${list[i].name}</span>
                <span style="color:var(--accent-blue); font-weight:bold;">${formatCoins(list[i].total_znx_earned, 4)} ZNX</span>
            </div>
        `;
    }
}

function createPodiumCard(item, rank, pClass) {
    return `
        <div class="podium-item ${pClass}">
            <div style="font-size:0.72rem; color:var(--text-muted);">المركز #${rank}</div>
            <div style="font-weight:bold; font-size:0.82rem; margin:3px 0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${item.name}</div>
            <div style="color:var(--accent-blue); font-weight:bold; font-size:0.78rem;">${formatCoins(item.total_znx_earned, 4)} ZNX</div>
        </div>
    `;
}

/**
 * 💎 ZNX Wallet Engine (Front-end Module)
 */

function escapeHTML(str) {
    if (!str) return '';
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function getUserId() {
    if (window.Telegram?.WebApp?.initDataUnsafe?.user?.id) {
        return String(window.Telegram.WebApp.initDataUnsafe.user.id);
    }
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('user_id') || urlParams.get('tg_id') || urlParams.get('telegram_id') || "5102387551";
}

let USER_ID = getUserId();
let userData = { balance: 0, usd_balance: 0, znx_balance: 0, total_znx_earned: 0 };
let currentTier = null;
let currentLivePrice = 0.0524;
let livePriceInterval = null;

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
    USER_ID = getUserId();
    const initData = window.Telegram?.WebApp?.initData || '';

    try {
        const res = await fetch(`/api/znx-wallet/data?user_id=${encodeURIComponent(USER_ID)}&initData=${encodeURIComponent(initData)}`, {
            method: 'GET',
            headers: {
                'X-Telegram-User-Id': USER_ID,
                'X-Telegram-Init-Data': initData
            }
        });
        
        if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
        
        const data = await res.json();
        
        if (data.success) {
            userData = data.user || data.player || userData;
            currentTier = data.current_tier || data.tier || currentTier;
            currentLivePrice = data.live_price || currentLivePrice;

            updateBalancesUI();
            updateGlobalStatsUI(data.global_total, data.max_global_znx);
            renderTiersUI(data.tiers_all || data.tiers);
            renderLeaderboardUI(data.leaderboard, data.my_rank);
        } else {
            console.error("⚠️ فشل جلب بيانات ZNX Wallet:", data.message || data.error);
        }
    } catch (err) {
        console.error("❌ خطأ الاتصال بسيرفر ZNX Wallet:", err);
    }
}

function updateBalancesUI() {
    const znEl = document.getElementById('znBalance');
    const usdEl = document.getElementById('usdBalance');
    const znxEl = document.getElementById('znxBalance');

    if (znEl) znEl.innerHTML = formatCoins(userData.balance || 0, 2);
    if (usdEl) usdEl.innerHTML = `$${formatCoins(userData.usd_balance || 0, 2)}`;
    if (znxEl) znxEl.innerHTML = formatCoins(userData.znx_balance || 0, 4);
}

function updateGlobalStatsUI(globalTotal, maxGlobal) {
    const ratioEl = document.getElementById('globalRatioText');
    const barEl = document.getElementById('globalProgressBar');

    const total = globalTotal || 0;
    const max = maxGlobal || 35000000;
    const pct = Math.min(100, Math.max(0, (total / max) * 100));
    
    if (ratioEl) ratioEl.innerHTML = `${formatCoins(total, 2)} / ${(max / 1000000).toFixed(0)}M ZNX`;
    if (barEl) barEl.style.width = `${pct}%`;
}

function tickLivePrice() {
    const delta = (Math.random() - 0.48) * 0.0004;
    currentLivePrice = Math.max(0.01, currentLivePrice + delta);
    const priceEl = document.getElementById('livePrice');
    if (priceEl) {
        priceEl.innerText = `$${currentLivePrice.toFixed(4)}`;
    }
}

function selectOption(type) {
    const input = document.getElementById('convertInput');
    if (!input) return;

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
    const inputEl = document.getElementById('convertInput');
    const previewEl = document.getElementById('znxPreview');
    if (!inputEl || !previewEl) return;

    const points = parseFloat(inputEl.value) || 0;
    const rate = (currentTier && currentTier.rate) ? currentTier.rate : 10;
    const znxGained = points > 0 ? (points / rate) : 0;

    previewEl.innerHTML = `${formatCoins(znxGained, 4)} ZNX`;
}

async function submitConvert() {
    const inputEl = document.getElementById('convertInput');
    const btnEl = document.getElementById('convertSubmitBtn');
    
    if (!inputEl) return;

    const amount = parseFloat(inputEl.value);
    if (isNaN(amount) || amount <= 0) {
        alert("يرجى تحديد كمية نقاط صالحة للتحويل");
        return;
    }

    if (userData.balance && amount > userData.balance) {
        alert("رصيدك الحالي غير كافٍ لإتمام العملية");
        return;
    }

    if (btnEl) btnEl.disabled = true;

    try {
        const initData = window.Telegram?.WebApp?.initData || '';

        const res = await fetch('/api/znx-wallet/convert', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'X-Telegram-Init-Data': initData,
                'X-Telegram-User-Id': USER_ID
            },
            body: JSON.stringify({ 
                user_id: USER_ID, 
                tg_id: USER_ID,
                initData: initData,
                amount: amount 
            })
        });

        const result = await res.json();

        if (result.success) {
            const gained = result.data?.znx_gained || result.znx_gained || 0;
            alert(`تم التحويل بنجاح! حصلت على ${gained} ZNX`);
            inputEl.value = '';
            onInputChange();
            await initApp();
        } else {
            alert(`تنبيه: ${result.message || result.error || "تعذر إجراء التحويل"}`);
        }
    } catch (err) {
        console.error("❌ خطأ أثناء التحويل:", err);
        alert("حدث خطأ أثناء الاتصال بالسيرفر لإجراء التحويل.");
    } finally {
        if (btnEl) btnEl.disabled = false;
    }
}

function renderTiersUI(tiers) {
    const container = document.getElementById('tiersContainer');
    if (!container) return;

    container.innerHTML = '';
    if (!tiers || !Array.isArray(tiers)) return;

    tiers.forEach(t => {
        const isCurrent = currentTier && (currentTier.tier === t.tier || currentTier.name === t.name);
        const safeName = escapeHTML(t.name);
        
        container.innerHTML += `
            <div class="tier-item ${isCurrent ? 'current' : ''}">
                <div>
                    <strong>${safeName}</strong> 
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

function renderLeaderboardUI(list, myRank) {
    const podium = document.getElementById('podiumContainer');
    const rankings = document.getElementById('rankingsContainer');
    const rankBadge = document.getElementById('myRankBadge');

    if (rankBadge && myRank !== undefined) {
        rankBadge.innerText = `ترتيبك: ${myRank}`;
    }

    if (!podium || !rankings) return;

    podium.innerHTML = '';
    rankings.innerHTML = '';

    if (!list || !Array.isArray(list) || list.length === 0) {
        rankings.innerHTML = '<div style="text-align:center; padding:15px; color:var(--text-muted);">لا يوجد متصدرين حالياً</div>';
        return;
    }

    if (list.length >= 1) podium.innerHTML += createPodiumCard(list[0], 1, 'podium-1');
    if (list.length >= 2) podium.innerHTML += createPodiumCard(list[1], 2, 'podium-2');
    if (list.length >= 3) podium.innerHTML += createPodiumCard(list[2], 3, 'podium-3');

    for (let i = 3; i < list.length; i++) {
        const safeName = escapeHTML(list[i].name || list[i].first_name || 'لاعب');
        rankings.innerHTML += `
            <div class="leader-row">
                <span>#${i + 1} ${safeName}</span>
                <span style="color:var(--accent-blue); font-weight:bold;">${formatCoins(list[i].total_znx_earned || 0, 4)} ZNX</span>
            </div>
        `;
    }
}

function createPodiumCard(item, rank, pClass) {
    const safeName = escapeHTML(item.name || item.first_name || 'لاعب');
    return `
        <div class="podium-item ${pClass}">
            <div style="font-size:0.72rem; color:var(--text-muted);">المركز #${rank}</div>
            <div style="font-weight:bold; font-size:0.82rem; margin:3px 0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${safeName}</div>
            <div style="color:var(--accent-blue); font-weight:bold; font-size:0.78rem;">${formatCoins(item.total_znx_earned || 0, 4)} ZNX</div>
        </div>
    `;
}

window.selectOption = selectOption;
window.onInputChange = onInputChange;
window.submitConvert = submitConvert;
window.initZnxWallet = initApp;
window.loadZnxWalletData = initApp;

function startZnxModule() {
    if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.ready();
        window.Telegram.WebApp.expand();
    }
    USER_ID = getUserId();
    initApp();

    if (livePriceInterval) clearInterval(livePriceInterval);
    livePriceInterval = setInterval(tickLivePrice, 1000);
}

if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(startZnxModule, 50);
} else {
    document.addEventListener('DOMContentLoaded', startZnxModule);
}

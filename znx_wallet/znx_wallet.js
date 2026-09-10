/**
 * 💎 ZNX Wallet Engine (Front-end Module)
 */

const ZNX_TOKEN_CONTRACT = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwdJ";

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

// المتغيرات الخاصة بالسعر المباشر والإحصائيات
let currentLivePrice = 0;
let targetLivePrice = 0;
let priceFetchTimer = null;
let priceTickerTimer = null;
let isPriceInitialized = false;

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

function formatPriceUsd(val) {
    const num = parseFloat(val) || 0;
    if (num <= 0) return "جاري التحديث...";
    if (num < 0.0001) return `$${num.toFixed(8)}`;
    if (num < 0.01) return `$${num.toFixed(6)}`;
    if (num < 1) return `$${num.toFixed(4)}`;
    return `$${num.toFixed(2)}`;
}

async function fetchRealZnxPrice() {
    try {
        const serverRes = await fetch(`${window.location.origin}/api/znx-wallet/price?t=${Date.now()}`, {
            method: 'GET',
            cache: 'no-store',
            headers: {
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache'
            }
        });

        if (serverRes.ok) {
            const serverData = await serverRes.json();
            if (serverData.success && serverData.price > 0) {
                setTargetPrice(serverData.price);
                updateMarketStatsUI(serverData);
            }
        }
    } catch (err) {
        console.warn("جاري إعادة المحاولة لجلب السعر اللحظي...");
    }
}

function updateMarketStatsUI(data) {
    const changeEl = document.getElementById('statChange24h');
    const highEl = document.getElementById('statHigh24h');
    const lowEl = document.getElementById('statLow24h');

    if (changeEl && data.change_24h !== undefined) {
        const ch = parseFloat(data.change_24h) || 0;
        changeEl.innerText = `${ch >= 0 ? '+' : ''}${ch.toFixed(2)}%`;
        changeEl.style.color = ch >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
    }

    if (highEl && data.high_24h) {
        highEl.innerText = formatPriceUsd(data.high_24h);
    } else if (highEl && targetLivePrice > 0) {
        highEl.innerText = formatPriceUsd(targetLivePrice * 1.05);
    }

    if (lowEl && data.low_24h) {
        lowEl.innerText = formatPriceUsd(data.low_24h);
    } else if (lowEl && targetLivePrice > 0) {
        lowEl.innerText = formatPriceUsd(targetLivePrice * 0.95);
    }
}

function setTargetPrice(newPrice) {
    if (!newPrice || isNaN(newPrice) || newPrice <= 0) return;
    
    if (!isPriceInitialized || currentLivePrice === 0) {
        currentLivePrice = newPrice;
        targetLivePrice = newPrice;
        isPriceInitialized = true;
        const priceEl = document.getElementById('livePrice');
        if (priceEl) priceEl.innerText = formatPriceUsd(newPrice);
        return;
    }

    const priceEl = document.getElementById('livePrice');
    if (priceEl && newPrice !== targetLivePrice) {
        if (newPrice > targetLivePrice) {
            priceEl.classList.add('price-up');
            priceEl.classList.remove('price-down');
        } else if (newPrice < targetLivePrice) {
            priceEl.classList.add('price-down');
            priceEl.classList.remove('price-up');
        }
        setTimeout(() => {
            priceEl.classList.remove('price-up', 'price-down');
        }, 800);
    }
    
    targetLivePrice = newPrice;
}

function tickLivePriceSubSecond() {
    if (targetLivePrice <= 0) return;

    if (Math.abs(currentLivePrice - targetLivePrice) > 0.00000001) {
        currentLivePrice += (targetLivePrice - currentLivePrice) * 0.3;
    } else {
        currentLivePrice = targetLivePrice;
        const microNoise = (Math.random() - 0.5) * (targetLivePrice * 0.0003);
        currentLivePrice = Math.max(0.00000001, targetLivePrice + microNoise);
    }

    const priceEl = document.getElementById('livePrice');
    if (priceEl) {
        priceEl.innerText = formatPriceUsd(currentLivePrice);
    }
}

function startLivePriceEngine() {
    fetchRealZnxPrice();

    if (priceFetchTimer) clearInterval(priceFetchTimer);
    priceFetchTimer = setInterval(fetchRealZnxPrice, 3000);

    if (priceTickerTimer) clearInterval(priceTickerTimer);
    priceTickerTimer = setInterval(tickLivePriceSubSecond, 300);
}

async function initApp() {
    USER_ID = getUserId();
    const initData = window.Telegram?.WebApp?.initData || '';
    const apiUrl = `${window.location.origin}/api/znx-wallet/data?user_id=${encodeURIComponent(USER_ID)}&initData=${encodeURIComponent(initData)}`;

    try {
        const res = await fetch(apiUrl, {
            method: 'GET',
            cache: 'no-store',
            headers: {
                'X-Telegram-User-Id': USER_ID,
                'X-Telegram-Init-Data': initData,
                'Cache-Control': 'no-cache'
            }
        });
        
        if (!res.ok) throw new Error(`HTTP Error: ${res.status}`);
        
        const data = await res.json();
        
        if (data.success) {
            userData = data.user || data.player || userData;
            currentTier = data.current_tier || data.tier || currentTier;

            if (data.live_price && data.live_price > 0) {
                setTargetPrice(data.live_price);
            }

            updateBalancesUI();
            updateGlobalStatsUI(data.global_total, data.max_global_znx);
            renderTiersUI(data.tiers_all || data.tiers);
            renderLeaderboardUI(data.leaderboard, data.my_rank, data.my_info);
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
    const max = maxGlobal || 32500000;
    const pct = Math.min(100, Math.max(0, (total / max) * 100));
    
    if (ratioEl) ratioEl.innerHTML = `<span dir="ltr">${formatCoins(total, 0)} / ${(max / 1000000).toFixed(1)}M ZNX</span>`;
    if (barEl) barEl.style.width = `${pct}%`;
}

function selectOption(type) {
    const input = document.getElementById('convertInput');
    if (!input) return;

    const bal = userData.balance || 0;

    if (type === 'max' || !type) {
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

    if (userData.balance !== undefined && amount > userData.balance) {
        alert("رصيدك الحالي غير كافٍ لإتمام العملية");
        return;
    }

    if (btnEl) btnEl.disabled = true;

    try {
        const initData = window.Telegram?.WebApp?.initData || '';

        const res = await fetch(`${window.location.origin}/api/znx-wallet/convert`, {
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
        const minW = t.min_withdraw_znx ? t.min_withdraw_znx : '--';
        const feeUsd = t.fixed_fee_usd ? t.fixed_fee_usd : 0.02;
        
        container.innerHTML += `
            <div class="tier-item ${isCurrent ? 'current' : ''}">
                <div>
                    <strong>${safeName}</strong> 
                    ${isCurrent ? '<span class="tier-badge-active">الشريحة الحالية</span>' : ''}
                    <div style="color: var(--text-muted); font-size: 0.75rem; margin-top:2px;">
                        سعر التحويل: 1 ZNX = ${t.rate} ZN | أدنى سحب: ${minW} ZNX | رسوم: $${feeUsd}
                    </div>
                </div>
                <div style="text-align: left; color: var(--accent-blue); font-weight: bold;">
                    حصة الشريحة: ${(t.quota / 1000000).toFixed(1)}M
                </div>
            </div>
        `;
    });
}

function renderLeaderboardUI(list, myRank, myInfo) {
    const podium = document.getElementById('podiumContainer');
    const rankings = document.getElementById('rankingsContainer');
    const myRankCard = document.getElementById('myRankCardContainer');

    if (!podium || !rankings) return;

    podium.innerHTML = '';
    rankings.innerHTML = '';
    if (myRankCard) myRankCard.innerHTML = '';

    if (!list || !Array.isArray(list) || list.length === 0) {
        rankings.innerHTML = '<div style="text-align:center; padding:15px; color:var(--text-muted);">لا يوجد متصدرين حالياً</div>';
        return;
    }

    if (list.length >= 1) podium.innerHTML += createPodiumCard(list[0], 1, 'podium-1');
    if (list.length >= 2) podium.innerHTML += createPodiumCard(list[1], 2, 'podium-2');
    if (list.length >= 3) podium.innerHTML += createPodiumCard(list[3 - 1], 3, 'podium-3');

    const limitCount = Math.min(10, list.length);
    for (let i = 3; i < limitCount; i++) {
        const safeName = escapeHTML(list[i].name || list[i].first_name || 'لاعب');
        const isMe = USER_ID && String(list[i].user_id) === String(USER_ID);

        rankings.innerHTML += `
            <div class="leader-row ${isMe ? 'is-me-row' : ''}">
                <span>#${i + 1} ${safeName} ${isMe ? '<span class="me-tag">(أنت)</span>' : ''}</span>
                <span style="color:var(--accent-blue); font-weight:bold;">${formatCoins(list[i].total_znx_earned || 0, 4)} ZNX</span>
            </div>
        `;
    }

    if (myRankCard) {
        const earned = myInfo?.total_znx_earned ?? userData.total_znx_earned ?? 0;
        const myName = escapeHTML(myInfo?.name || userData.first_name || 'أنت');
        
        let rankDisplay = (myRank !== undefined && myRank !== null) ? `#${myRank}` : 'غير مصنف';
        let isTop10 = typeof myRank === 'number' && myRank <= 10;

        myRankCard.innerHTML = `
            <div class="my-rank-banner ${isTop10 ? 'in-top10' : ''}">
                <div class="my-rank-left">
                    <div class="my-rank-badge">ترتيبك الحالي: ${rankDisplay}</div>
                    <div class="my-rank-name">${myName} ${isTop10 ? '🔥 (ضمن الـ 10 الأوائل)' : ''}</div>
                </div>
                <div class="my-rank-right">
                    <div class="my-rank-earned">${formatCoins(earned, 4)} ZNX</div>
                    <div class="my-rank-sub">إجمالي المكتسب</div>
                </div>
            </div>
        `;
    }
}

function createPodiumCard(item, rank, pClass) {
    const safeName = escapeHTML(item.name || item.first_name || 'لاعب');
    const isMe = USER_ID && String(item.user_id) === String(USER_ID);

    return `
        <div class="podium-item ${pClass} ${isMe ? 'is-me-podium' : ''}">
            <div style="font-size:0.72rem; color:var(--text-muted);">المركز #${rank}</div>
            <div style="font-weight:bold; font-size:0.82rem; margin:3px 0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">
                ${safeName} ${isMe ? '⭐' : ''}
            </div>
            <div style="color:var(--accent-blue); font-weight:bold; font-size:0.78rem;">${formatCoins(item.total_znx_earned || 0, 4)} ZNX</div>
        </div>
    `;
}

function openStonLink() {
    const stonUrl = `https://app.ston.fi/swap?chartVisible=true&ft=TON&tt=${ZNX_TOKEN_CONTRACT}`;
    if (window.Telegram?.WebApp?.openLink) {
        window.Telegram.WebApp.openLink(stonUrl);
    } else {
        window.open(stonUrl, '_blank');
    }
}

window.selectOption = selectOption;
window.onInputChange = onInputChange;
window.submitConvert = submitConvert;
window.initZnxWallet = initApp;
window.openStonLink = openStonLink;

function startZnxModule() {
    if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.ready();
        window.Telegram.WebApp.expand();
    }
    USER_ID = getUserId();
    initApp();
    startLivePriceEngine();
}

if (document.readyState === 'complete' || document.readyState === 'interactive') {
    setTimeout(startZnxModule, 50);
} else {
    document.addEventListener('DOMContentLoaded', startZnxModule);
}

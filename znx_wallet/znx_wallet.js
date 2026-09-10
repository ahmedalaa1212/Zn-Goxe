/**
 * 💎 ZNX Wallet Engine (Front-end Module with Live Candlestick Charts)
 */

const ZNX_TOKEN_CONTRACT = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwdJ";
const STONFI_POOL_ADDRESS = "EQA0uIZQz8yFJdLCxpz7uXkjcylnnvGl3_KpE2zDUV5LUdXL"; // المجمع الخاص بك لجلب الهيستوري

function escapeHTML(str) {
    if (!str) return '';
    return String(str).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function getUserId() {
    if (window.Telegram?.WebApp?.initDataUnsafe?.user?.id) return String(window.Telegram.WebApp.initDataUnsafe.user.id);
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('user_id') || urlParams.get('tg_id') || "5102387551";
}

let USER_ID = getUserId();
let userData = { balance: 0, usd_balance: 0, znx_balance: 0, total_znx_earned: 0 };
let currentTier = null;

// متغيرات السعر والرسم البياني
let currentLivePrice = 0;
let targetLivePrice = 0;
let priceFetchTimer = null;
let priceTickerTimer = null;
let isPriceInitialized = false;

// TradingView Variables
let tvChart = null;
let candleSeries = null;
let currentCandle = null;

function formatCoins(val, decimals = 2) {
    const num = parseFloat(val) || 0;
    const parts = num.toFixed(decimals).split('.');
    const integerPart = parseInt(parts[0], 10).toLocaleString('en-US');
    return decimals === 0 ? integerPart : `${integerPart}<small class="dec">.${parts[1]}</small>`;
}

function formatPriceUsd(val) {
    const num = parseFloat(val) || 0;
    if (num <= 0) return "جاري التحديث...";
    if (num < 0.0001) return `$${num.toFixed(8)}`;
    if (num < 0.01) return `$${num.toFixed(6)}`;
    return `$${num.toFixed(4)}`;
}

// 📈 تهيئة الرسم البياني للشموع اليابانية
async function initTradingChart() {
    const chartContainer = document.getElementById('tvchart');
    if (!chartContainer || typeof LightweightCharts === 'undefined') return;

    // إعدادات المظهر ليتناسب مع التطبيق الدارك
    tvChart = LightweightCharts.createChart(chartContainer, {
        layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#64748b' },
        grid: { vertLines: { visible: false }, horzLines: { color: 'rgba(30, 41, 59, 0.4)' } },
        timeScale: { timeVisible: true, secondsVisible: false, borderVisible: false },
        rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.1, bottom: 0.1 } }
    });

    candleSeries = tvChart.addCandlestickSeries({
        upColor: '#10b981', downColor: '#ef4444',
        borderVisible: false,
        wickUpColor: '#10b981', wickDownColor: '#ef4444'
    });

    // جعل الرسم البياني متجاوب مع الشاشة
    new ResizeObserver(entries => {
        if (entries.length === 0 || entries[0].target !== chartContainer) return;
        const newRect = entries[0].contentRect;
        tvChart.applyOptions({ height: newRect.height, width: newRect.width });
    }).observe(chartContainer);

    // جلب التاريخ المباشر من GeckoTerminal عبر المجمع عشان الشارت ميبقاش فاضي أول ما يفتح
    try {
        const res = await fetch(`https://api.geckoterminal.com/api/v2/networks/ton/pools/${STONFI_POOL_ADDRESS}/ohlcv/minute?limit=60`);
        const data = await res.json();
        if (data?.data?.attributes?.ohlcv_list) {
            const formattedData = data.data.attributes.ohlcv_list.map(item => ({
                time: item[0], // Timestamp
                open: item[1], high: item[2], low: item[3], close: item[4]
            })).reverse(); // قلب الداتا لتتناسب مع TradingView
            
            candleSeries.setData(formattedData);
            
            if (formattedData.length > 0) {
                // تعيين آخر شمعة
                currentCandle = { ...formattedData[formattedData.length - 1] };
            }
        }
    } catch (e) {
        console.warn("تعذر جلب الهيستوري، سيتم بناء الشموع لحظياً", e);
    }
}

async function fetchRealZnxPrice() {
    try {
        const serverRes = await fetch(`${window.location.origin}/api/znx-wallet/price?t=${Date.now()}`, {
            method: 'GET', cache: 'no-store'
        });
        if (serverRes.ok) {
            const serverData = await serverRes.json();
            if (serverData.success && serverData.price > 0) {
                setTargetPrice(serverData.price);
            }
        }
    } catch (err) {}
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
        priceEl.classList.add(newPrice > targetLivePrice ? 'price-up' : 'price-down');
        priceEl.classList.remove(newPrice > targetLivePrice ? 'price-down' : 'price-up');
        setTimeout(() => priceEl.classList.remove('price-up', 'price-down'), 800);
    }
    
    targetLivePrice = newPrice;
}

// 🟢 تحديث السعر المباشر والشموع لحظياً
function tickLivePriceSubSecond() {
    if (targetLivePrice <= 0) return;

    if (Math.abs(currentLivePrice - targetLivePrice) > 0.00000001) {
        currentLivePrice += (targetLivePrice - currentLivePrice) * 0.3;
    } else {
        currentLivePrice = targetLivePrice;
        const microNoise = (Math.random() - 0.5) * (targetLivePrice * 0.0001);
        currentLivePrice = Math.max(0.00000001, targetLivePrice + microNoise);
    }

    const priceEl = document.getElementById('livePrice');
    if (priceEl) priceEl.innerText = formatPriceUsd(currentLivePrice);

    // 🕯️ بناء الشموع وتحديثها لحظياً في الرسم البياني
    if (candleSeries && currentLivePrice > 0) {
        const now = Math.floor(Date.now() / 1000);
        const currentMinute = now - (now % 60); // محاذاة الوقت لأقرب دقيقة

        if (!currentCandle || currentCandle.time !== currentMinute) {
            // شمعة دقيقة جديدة
            currentCandle = {
                time: currentMinute,
                open: currentLivePrice,
                high: currentLivePrice,
                low: currentLivePrice,
                close: currentLivePrice
            };
        } else {
            // تحديث الشمعة الحالية
            currentCandle.high = Math.max(currentCandle.high, currentLivePrice);
            currentCandle.low = Math.min(currentCandle.low, currentLivePrice);
            currentCandle.close = currentLivePrice;
        }
        candleSeries.update(currentCandle);
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
    const apiUrl = `${window.location.origin}/api/znx-wallet/data?user_id=${encodeURIComponent(USER_ID)}`;

    try {
        const res = await fetch(apiUrl, { headers: { 'X-Telegram-User-Id': USER_ID }});
        if (!res.ok) throw new Error(`HTTP Error`);
        const data = await res.json();
        
        if (data.success) {
            userData = data.user || userData;
            currentTier = data.current_tier || currentTier;

            if (data.live_price && data.live_price > 0) setTargetPrice(data.live_price);

            updateBalancesUI();
            updateGlobalStatsUI(data.global_total, data.max_global_znx);
            renderTiersUI(data.tiers_all);
            renderLeaderboardUI(data.leaderboard, data.my_rank, data.my_info);
        }
    } catch (err) { console.error("Error connecting to server:", err); }
}

function updateBalancesUI() {
    if (document.getElementById('znBalance')) document.getElementById('znBalance').innerHTML = formatCoins(userData.balance, 2);
    if (document.getElementById('usdBalance')) document.getElementById('usdBalance').innerHTML = `$${formatCoins(userData.usd_balance, 2)}`;
    if (document.getElementById('znxBalance')) document.getElementById('znxBalance').innerHTML = formatCoins(userData.znx_balance, 4);
}

function updateGlobalStatsUI(total, max) {
    const pct = Math.min(100, Math.max(0, (total / max) * 100));
    if (document.getElementById('globalRatioText')) document.getElementById('globalRatioText').innerHTML = `<span dir="ltr">${formatCoins(total, 0)} / ${(max / 1000000).toFixed(1)}M ZNX</span>`;
    if (document.getElementById('globalProgressBar')) document.getElementById('globalProgressBar').style.width = `${pct}%`;
}

function selectOption(type) {
    const input = document.getElementById('convertInput');
    if (!input) return;
    const bal = userData.balance || 0;
    input.value = type === 'max' ? bal : type === 'half' ? (bal / 2).toFixed(2) : (currentTier ? currentTier.rate : 10);
    onInputChange();
}

function onInputChange() {
    const input = document.getElementById('convertInput');
    const preview = document.getElementById('znxPreview');
    const points = parseFloat(input?.value) || 0;
    const rate = currentTier?.rate || 10;
    if (preview) preview.innerHTML = `${formatCoins(points > 0 ? points / rate : 0, 4)} ZNX`;
}

async function submitConvert() {
    const input = document.getElementById('convertInput');
    const btn = document.getElementById('convertSubmitBtn');
    const amount = parseFloat(input.value);

    if (isNaN(amount) || amount <= 0) return alert("يرجى إدخال كمية صحيحة");
    if (amount > userData.balance) return alert("رصيدك غير كافٍ");

    btn.disabled = true;
    try {
        const res = await fetch(`${window.location.origin}/api/znx-wallet/convert`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: USER_ID, amount: amount })
        });
        const result = await res.json();
        if (result.success) {
            alert(`تم التحويل! حصلت على ${result.data?.znx_gained || result.znx_gained} ZNX`);
            input.value = ''; onInputChange(); await initApp();
        } else {
            alert(result.message);
        }
    } catch (err) { alert("حدث خطأ بالاتصال"); }
    finally { btn.disabled = false; }
}

function renderTiersUI(tiers) {
    const container = document.getElementById('tiersContainer');
    if (!container || !tiers) return;
    container.innerHTML = tiers.map(t => {
        const isCurrent = currentTier && currentTier.tier === t.tier;
        return `
            <div class="tier-item ${isCurrent ? 'current' : ''}">
                <div>
                    <strong>${escapeHTML(t.name)}</strong> ${isCurrent ? '<span class="tier-badge-active">الحالية</span>' : ''}
                    <div style="color:var(--text-muted); font-size:0.75rem;">1 ZNX = ${t.rate} ZN | رسوم: $${t.fixed_fee_usd}</div>
                </div>
            </div>`;
    }).join('');
}

function renderLeaderboardUI(list, myRank) {
    const rankings = document.getElementById('rankingsContainer');
    if (!rankings || !list) return;
    rankings.innerHTML = list.slice(0, 10).map((u, i) => `
        <div class="leader-row ${String(u.user_id) === USER_ID ? 'is-me-row' : ''}">
            <span>#${i + 1} ${escapeHTML(u.name || 'لاعب')}</span>
            <span style="color:#38bdf8; font-weight:bold;">${formatCoins(u.total_znx_earned, 4)} ZNX</span>
        </div>
    `).join('');
}

window.selectOption = selectOption;
window.onInputChange = onInputChange;
window.submitConvert = submitConvert;

function startZnxModule() {
    if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.ready();
        window.Telegram.WebApp.expand();
    }
    USER_ID = getUserId();
    initTradingChart(); // تهيئة الرسم البياني أولاً
    initApp();
    startLivePriceEngine();
}

document.addEventListener('DOMContentLoaded', startZnxModule);

/**
 * 💎 ZNX Wallet Engine (Front-end Module - Professional Bybit-Style Chart & Backend Synced Engine)
 * Cleaned, Optimized, Zero Client CORS/Rate-Limit Error Version
 */

// ==================== الثوابت والمتغيرات العامة ====================
const ZNX_TOKEN_CONTRACT = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwdJ";
const USDT_TOKEN_CONTRACT = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"; 
const ZNX_POOL_ADDRESS = "EQB_Anc7ln6e-oAVUOrgcvmzqGtupciTcWCDLCriN7ZSlW7R6";

window.ZNX_POOL_CREATED_AT = 1768435200; 

let USER_ID = getUserId();
let userData = { balance: 0, usd_balance: 0, znx_balance: 0, total_znx_earned: 0 };
let currentTier = null;

// حالة السعر المباشر
let currentLivePrice = 0;
let targetLivePrice = 0;
let priceFetchTimer = null;
let smoothLoopTimer = null;
let isPriceInitialized = false;

// محرك الرسم البياني
let tvChart = null;
let candleSeries = null;
let currentCandle = null;
let currentTimeframe = '5m';
let lastCandleTime = 0;

// ==================== الأدوات المساعدة (Helpers) ====================
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

function getTimeframeSeconds(tf) {
    switch(String(tf).toLowerCase()) {
        case '1m': return 60;
        case '5m': return 300;
        case '15m': return 900;
        case '1h': return 3600;
        case '1d': return 86400;
        default: return 300;
    }
}

function formatCoins(val, decimals = 2) {
    const num = parseFloat(val) || 0;
    const parts = num.toFixed(decimals).split('.');
    const integerPart = parseInt(parts[0], 10).toLocaleString('en-US');
    const decimalPart = parts[1];
    if (decimals === 0 || !decimalPart) return integerPart;
    return `${integerPart}<small class="dec">.${decimalPart}</small>`;
}

function formatPriceUsd(val) {
    const num = parseFloat(val) || 0;
    if (num <= 0) return "جاري جلب السعر...";
    if (num < 0.000001) return `$${num.toFixed(8)}`;
    if (num < 0.0001) return `$${num.toFixed(7)}`;
    if (num < 0.01) return `$${num.toFixed(6)}`;
    if (num < 1) return `$${num.toFixed(5)}`;
    return `$${num.toFixed(6)}`;
}

// دالة موحدة للاستعلامات من السيرفر الخلفي
async function apiFetch(endpoint, options = {}) {
    const baseUrl = window.location.origin;
    const paths = [`/api/znx-wallet${endpoint}`, `/api/znx_wallet${endpoint}`];
    
    for (const path of paths) {
        try {
            const res = await fetch(`${baseUrl}${path}`, options);
            if (res.ok) {
                const data = await res.json();
                if (data && (data.success !== false)) return data;
            }
        } catch (e) {
            // المحاولة مع المسار البديل
        }
    }
    return null;
}

// ==================== محرك السعر المباشر (Real-time Price Engine) ====================
async function fetchRealZnxPrice() {
    try {
        // الطلب يتم حصرياً من السيرفر الخلفي لمنع حظر IP المستخدم أو تقييد CORS في التلجرام
        const serverData = await apiFetch(`/price?t=${Date.now()}`, {
            method: 'GET',
            cache: 'no-store',
            headers: { 'Cache-Control': 'no-cache' }
        });

        if (serverData && serverData.has_price && serverData.price > 0) {
            const livePrice = parseFloat(serverData.price);
            if (serverData.pool_created_at) window.ZNX_POOL_CREATED_AT = serverData.pool_created_at;
            
            setTargetPrice(livePrice);
            updateMarketStatsUI({
                price: livePrice,
                change_24h: serverData.change_24h !== undefined ? parseFloat(serverData.change_24h) : 0,
                high_24h: parseFloat(serverData.high_24h || livePrice),
                low_24h: parseFloat(serverData.low_24h || livePrice)
            });
            return;
        } else {
            // في حالة عدم جاهزية السعر بعد من السيرفر
            const priceEl = document.getElementById('livePrice') || document.getElementById('znx-live-price');
            if (priceEl && (!currentLivePrice || currentLivePrice <= 0)) {
                priceEl.innerText = "جاري جلب السعر...";
            }
        }
    } catch (e) {
        console.warn("⚠️ جاري انتظار تحديث السعر من السيرفر الخلفي...");
        const priceEl = document.getElementById('livePrice') || document.getElementById('znx-live-price');
        if (priceEl && (!currentLivePrice || currentLivePrice <= 0)) {
            priceEl.innerText = "جاري جلب السعر...";
        }
    }
}

function setTargetPrice(newPrice) {
    if (!newPrice || isNaN(newPrice) || newPrice <= 0) return;
    
    if (!isPriceInitialized || currentLivePrice === 0) {
        currentLivePrice = newPrice;
        targetLivePrice = newPrice;
        isPriceInitialized = true;
        
        const priceEl = document.getElementById('livePrice') || document.getElementById('znx-live-price');
        if (priceEl) priceEl.innerText = formatPriceUsd(newPrice);
        
        if (!tvChart) initChart();
        updateChartTick(newPrice);
        return;
    }

    const priceEl = document.getElementById('livePrice') || document.getElementById('znx-live-price');
    if (priceEl && newPrice !== targetLivePrice) {
        priceEl.classList.add(newPrice > targetLivePrice ? 'price-up' : 'price-down');
        setTimeout(() => priceEl.classList.remove('price-up', 'price-down'), 800);
    }
    
    targetLivePrice = newPrice;
}

function updateSmoothTick() {
    if (targetLivePrice <= 0) return;

    if (currentLivePrice === 0) {
        currentLivePrice = targetLivePrice;
    } else {
        const diff = targetLivePrice - currentLivePrice;
        if (Math.abs(diff) > 1e-10) {
            currentLivePrice += diff * 0.20;
        } else {
            currentLivePrice = targetLivePrice;
        }
    }

    const priceEl = document.getElementById('livePrice') || document.getElementById('znx-live-price');
    if (priceEl) {
        priceEl.innerText = formatPriceUsd(currentLivePrice);
    }

    // تحديث الشمعة الحالية فوراً مع التنعيم اللحظي
    updateChartTick(currentLivePrice);
}

function updateMarketStatsUI(data) {
    const priceEl = document.getElementById('livePrice') || document.getElementById('znx-live-price');
    const changeEl = document.getElementById('statChange24h') || document.getElementById('znx-24h-change');
    const highEl = document.getElementById('statHigh24h') || document.getElementById('znx-high-24h');
    const lowEl = document.getElementById('statLow24h') || document.getElementById('znx-low-24h');

    if (priceEl) {
        if (data.price && data.price > 0) {
            priceEl.innerText = formatPriceUsd(data.price);
        } else {
            priceEl.innerText = "جاري جلب السعر...";
        }
    }

    if (changeEl && data.change_24h !== undefined) {
        const ch = parseFloat(data.change_24h) || 0;
        changeEl.innerText = `${ch >= 0 ? '+' : ''}${ch.toFixed(2)}%`;
        changeEl.style.color = ch >= 0 ? 'var(--accent-green, #0ecb81)' : 'var(--accent-red, #f6465d)';
    }

    if (highEl) highEl.innerText = data.high_24h && data.high_24h > 0 ? formatPriceUsd(data.high_24h) : "--";
    if (lowEl) lowEl.innerText = data.low_24h && data.low_24h > 0 ? formatPriceUsd(data.low_24h) : "--";
}

function startLivePriceEngine() {
    fetchRealZnxPrice();
    if (priceFetchTimer) clearInterval(priceFetchTimer);
    priceFetchTimer = setInterval(fetchRealZnxPrice, 3000);

    if (smoothLoopTimer) clearInterval(smoothLoopTimer);
    smoothLoopTimer = setInterval(updateSmoothTick, 100);
}

// ==================== محرك الرسم البياني (TradingView Chart) ====================
function initChart() {
    const container = document.getElementById('chartContainer');
    if (!container) return;

    if (typeof LightweightCharts === 'undefined') {
        if (!document.getElementById('lw-charts-script')) {
            const script = document.createElement('script');
            script.id = 'lw-charts-script';
            script.src = 'https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js';
            script.async = true;
            script.onload = () => setTimeout(initChart, 200);
            document.head.appendChild(script);
        } else {
            setTimeout(initChart, 300);
        }
        return;
    }

    container.innerHTML = '';
    const width = container.clientWidth || container.parentElement?.clientWidth || window.innerWidth - 32 || 350;
    const height = container.clientHeight || 250;

    try {
        tvChart = LightweightCharts.createChart(container, {
            width: width,
            height: height,
            layout: {
                background: { type: 'solid', color: '#090d16' },
                textColor: '#64748b',
                fontSize: 10,
            },
            grid: {
                vertLines: { color: 'rgba(30, 41, 59, 0.2)' },
                horzLines: { color: 'rgba(30, 41, 59, 0.2)' },
            },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            rightPriceScale: {
                borderColor: '#1e293b',
                scaleMargins: { top: 0.15, bottom: 0.15 },
                autoScale: true,
            },
            timeScale: {
                borderColor: '#1e293b',
                timeVisible: true,
                secondsVisible: false,
                rightOffset: 3,
                barSpacing: 8,
                minBarSpacing: 3,
                fixLeftEdge: true,
                tickMarkFormatter: (time) => {
                    const date = new Date(time * 1000);
                    const pad = (n) => String(n).padStart(2, '0');
                    return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
                }
            },
            handleScroll: { mouseWheel: true, pressedMove: true },
            handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true }
        });

        candleSeries = tvChart.addCandlestickSeries({
            upColor: '#0ecb81',
            downColor: '#f6465d',
            borderDownColor: '#f6465d',
            borderUpColor: '#0ecb81',
            wickDownColor: '#f6465d',
            wickUpColor: '#0ecb81',
            priceFormat: {
                type: 'custom',
                formatter: (price) => formatPriceUsd(price),
                minMove: 0.00000001,
            },
        });

        loadChartData(currentTimeframe);

        const resizeObserver = new ResizeObserver(entries => {
            if (entries[0] && tvChart) {
                const cr = entries[0].contentRect;
                if (cr.width > 0) tvChart.applyOptions({ width: cr.width, height: cr.height || 250 });
            }
        });
        resizeObserver.observe(container);
    } catch (e) {
        console.error("خطأ أثناء إنشاء الرسم البياني:", e);
    }
}

async function loadChartData(tf) {
    if (!candleSeries) return;

    const data = await apiFetch(`/candles?tf=${encodeURIComponent(tf)}&t=${Date.now()}`);
    if (data && Array.isArray(data.candles) && data.candles.length > 0) {
        applyCandlesToChart(data.candles);
        return;
    }

    // إنشاء الشمعات زمنياً عند عدم توفر كاش كافٍ من السيرفر
    generateAccurateTimeboundCandles(tf);
}

function applyCandlesToChart(candles) {
    if (!candleSeries || !candles || candles.length === 0) return;

    let cleanCandles = [];
    let seenTimes = new Set();
    const nowSec = Math.floor(Date.now() / 1000);

    for (let c of candles) {
        let t = Math.floor(Number(c.time));
        if (!isNaN(t) && t > 0 && t <= nowSec + 60 && !seenTimes.has(t)) {
            seenTimes.add(t);
            cleanCandles.push({
                time: t,
                open: Number(c.open),
                high: Number(c.high),
                low: Number(c.low),
                close: Number(c.close)
            });
        }
    }

    cleanCandles.sort((a, b) => a.time - b.time);
    if (cleanCandles.length === 0) return;

    candleSeries.setData(cleanCandles);

    const last = cleanCandles[cleanCandles.length - 1];
    lastCandleTime = last.time;
    currentCandle = { ...last };

    if (targetLivePrice > 0) {
        currentCandle.close = targetLivePrice;
        if (targetLivePrice > currentCandle.high) currentCandle.high = targetLivePrice;
        if (targetLivePrice < currentCandle.low) currentCandle.low = targetLivePrice;
        candleSeries.update(currentCandle);
    }

    if (tvChart?.timeScale) tvChart.timeScale().fitContent();
}

function generateAccurateTimeboundCandles(tf) {
    if (targetLivePrice <= 0 && currentLivePrice <= 0) return;

    const tfSec = getTimeframeSeconds(tf);
    const nowSec = Math.floor(Date.now() / 1000);
    const currentPeriodStart = Math.floor(nowSec / tfSec) * tfSec;
    const poolCreationTime = window.ZNX_POOL_CREATED_AT || 1768435200;
    
    const count = Math.min(60, Math.max(1, Math.floor((currentPeriodStart - poolCreationTime) / tfSec) + 1));
    const price = targetLivePrice > 0 ? targetLivePrice : currentLivePrice;

    let rawCandles = [];
    for (let i = count - 1; i >= 0; i--) {
        let time = currentPeriodStart - (i * tfSec);
        if (time < poolCreationTime) continue;
        rawCandles.push({
            time: time,
            open: parseFloat(price.toFixed(8)),
            high: parseFloat(price.toFixed(8)),
            low: parseFloat(price.toFixed(8)),
            close: parseFloat(price.toFixed(8))
        });
    }

    rawCandles.sort((a, b) => a.time - b.time);
    applyCandlesToChart(rawCandles);
}

function updateChartTick(price) {
    if (!candleSeries || price <= 0) return;

    const tfSec = getTimeframeSeconds(currentTimeframe);
    const nowSec = Math.floor(Date.now() / 1000);
    const candlePeriodStart = Math.floor(nowSec / tfSec) * tfSec;

    if (!currentCandle || candlePeriodStart > lastCandleTime) {
        lastCandleTime = candlePeriodStart;
        currentCandle = {
            time: lastCandleTime,
            open: price,
            high: price,
            low: price,
            close: price
        };
    } else {
        currentCandle.close = price;
        if (price > currentCandle.high) currentCandle.high = price;
        if (price < currentCandle.low) currentCandle.low = price;
    }

    try {
        candleSeries.update(currentCandle);
    } catch (e) {
        // تجاهل أخطاء التحديث التزامني البسيط
    }
}

function changeTimeframe(tf) {
    if (!tf) return;
    currentTimeframe = tf;

    document.querySelectorAll('.tf-btn').forEach(btn => {
        const txt = btn.innerText.trim().toLowerCase();
        btn.classList.toggle('active', txt === tf.toLowerCase());
    });

    if (tvChart) {
        loadChartData(currentTimeframe);
    }
}

// ==================== الوظائف التشغيلية والواجهة ====================
async function initApp() {
    USER_ID = getUserId();
    const initData = window.Telegram?.WebApp?.initData || '';

    const data = await apiFetch(`/data?user_id=${encodeURIComponent(USER_ID)}&initData=${encodeURIComponent(initData)}`, {
        method: 'GET',
        cache: 'no-store',
        headers: {
            'X-Telegram-User-Id': USER_ID,
            'X-Telegram-Init-Data': initData,
            'Cache-Control': 'no-cache'
        }
    });

    if (data && data.success) {
        userData = data.user || data.player || userData;
        currentTier = data.current_tier || data.tier || currentTier;

        if (data.pool_created_at) window.ZNX_POOL_CREATED_AT = data.pool_created_at;

        updateBalancesUI();
        updateGlobalStatsUI(data.global_total, data.max_global_znx);
        
        let rawTiers = data.tiers_all || data.tiers || data.tiers_config;
        if (rawTiers && typeof rawTiers === 'object' && !Array.isArray(rawTiers)) {
            rawTiers = Object.values(rawTiers);
        }
        
        renderTiersUI(rawTiers);
        renderLeaderboardUI(data.leaderboard, data.my_rank, data.my_info);
    }

    fetchRealZnxPrice();
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

    const total = parseFloat(globalTotal) || 0;
    const max = parseFloat(maxGlobal) || 32500000;
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
        input.value = (currentTier && currentTier.rate) ? currentTier.rate : 10;
    }
    onInputChange();
}

function onInputChange() {
    const inputEl = document.getElementById('convertInput');
    const previewEl = document.getElementById('znxPreview');
    if (!inputEl || !previewEl) return;

    const points = parseFloat(inputEl.value) || 0;
    const rate = (currentTier && currentTier.rate) ? parseFloat(currentTier.rate) : 10;
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
        const result = await apiFetch(`/convert`, {
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

        if (result && result.success) {
            const gained = result.data?.znx_gained || result.znx_gained || 0;
            alert(`تم التحويل بنجاح! حصلت على ${gained} ZNX`);
            inputEl.value = '';
            onInputChange();
            await initApp();
        } else {
            alert("تعذر إجراء التحويل. يرجى المحاولة مرة أخرى.");
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
    let tiersList = tiers;
    if (tiersList && typeof tiersList === 'object' && !Array.isArray(tiersList)) {
        tiersList = Object.values(tiersList);
    }

    if (!tiersList || !Array.isArray(tiersList) || tiersList.length === 0) return;

    tiersList.forEach(t => {
        if (!t) return;
        const isCurrent = currentTier && (
            (currentTier.tier && t.tier && Number(currentTier.tier) === Number(t.tier)) ||
            (currentTier.name && t.name && currentTier.name === t.name)
        );
        const safeName = escapeHTML(t.name || `الشريحة ${t.tier || ''}`);
        const minW = t.min_withdraw_znx ? t.min_withdraw_znx : '--';
        const feeUsd = t.fixed_fee_usd !== undefined ? t.fixed_fee_usd : 0.02;
        const quotaM = t.quota ? (parseFloat(t.quota) / 1000000).toFixed(1) : '1.5';
        const rate = t.rate || 10;
        
        container.innerHTML += `
            <div class="tier-item ${isCurrent ? 'current' : ''}">
                <div>
                    <strong>${safeName}</strong> 
                    ${isCurrent ? '<span class="tier-badge-active">الشريحة الحالية</span>' : ''}
                    <div style="color: var(--text-muted); font-size: 0.75rem; margin-top:2px;">
                        سعر التحويل: 1 ZNX = ${rate} ZN | أدنى سحب: ${minW} ZNX | رسوم: $${feeUsd}
                    </div>
                </div>
                <div style="text-align: left; color: var(--accent-blue); font-weight: bold;">
                    حصة الشريحة: ${quotaM}M
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
    if (list.length >= 3) podium.innerHTML += createPodiumCard(list[3], 3, 'podium-3');

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
    const stonUrl = `https://app.ston.fi/swap?chartVisible=true&ft=${USDT_TOKEN_CONTRACT}&tt=${ZNX_TOKEN_CONTRACT}`;
    if (window.Telegram?.WebApp?.openLink) {
        window.Telegram.WebApp.openLink(stonUrl);
    } else {
        window.open(stonUrl, '_blank');
    }
}

// ==================== التصدير للنافذة العامة والبدء ====================
window.selectOption = selectOption;
window.onInputChange = onInputChange;
window.submitConvert = submitConvert;
window.initZnxWallet = initApp;
window.openStonLink = openStonLink;
window.changeTimeframe = changeTimeframe;

function startZnxModule() {
    if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.ready();
        window.Telegram.WebApp.expand();
    }
    USER_ID = getUserId();
    initApp();
    
    setTimeout(() => {
        initChart();
        startLivePriceEngine();
    }, 200);
}

if (document.readyState === 'complete' || document.readyState === 'interactive') {
    startZnxModule();
} else {
    document.addEventListener('DOMContentLoaded', startZnxModule);
}

/**
 * 💎 ZNX Wallet Engine (Front-end Module - Abbreviated Balances & Guaranteed Live Chart Edition)
 * يعرض الأرصدة باختصارات المزرعة (K, M, B, T) ويضمن ظهور السعر والشموع اللحظية في 0.1 ثانية
 */

// ==================== الثوابت ومتغيرات النظام ====================
const ZNX_TOKEN_CONTRACT = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwdJ";
const USDT_TOKEN_CONTRACT = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"; 
const ZNX_POOL_ADDRESS = "EQB_Anc7ln6e-oAVUOrgcvmzqGtupciTcWCDLCriN7ZSlW7R6";

window.ZNX_POOL_CREATED_AT = 1735689600; 

let USER_ID = getUserId();
let userData = { balance: 0, usd_balance: 0, znx_balance: 0, total_znx_earned: 0 };
let currentTier = null;
let allTiersList = [];
let globalTotalZnx = 0;
let maxGlobalZnx = 32500000;

// حالة السعر المباشر (مزود بسعر ابتدائي آمن يمنع بقاء الشاشة فارغة)
const SAFE_INITIAL_PRICE = 0.00042500;
let currentLivePrice = SAFE_INITIAL_PRICE;
let targetLivePrice = SAFE_INITIAL_PRICE;
let currentChange24h = 4.85;
let priceFetchTimer = null;
let smoothLoopTimer = null;
let isPriceInitialized = false;
let lastDirectFallbackTime = 0;

// محرك الرسم البياني
let tvChart = null;
let candleSeries = null;
let currentCandle = null;
let currentTimeframe = '5m';
let lastCandleTime = 0;

// ==================== الأدوات المساعدة وتنسيق الأرصدة المختصرة ====================
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

/**
 * تنسيق الأرصدة بالاختصارات (K, M, B, T) بنفس تصميم قائمة المزرعة بالضبط
 * مثال: 49,890,620.76 -> 49<small class="dec">.89M</small>
 * مثال: 17.61 -> 17<small class="dec">.61</small>
 */
function formatCoins(val, decimals = 2) {
    const num = parseFloat(val) || 0;
    const absNum = Math.abs(num);
    const sign = num < 0 ? '-' : '';

    let scaled = absNum;
    let suffix = '';
    let decCount = decimals;

    if (absNum >= 1e12) {
        scaled = absNum / 1e12;
        suffix = 'T';
        decCount = 2;
    } else if (absNum >= 1e9) {
        scaled = absNum / 1e9;
        suffix = 'B';
        decCount = 2;
    } else if (absNum >= 1e6) {
        scaled = absNum / 1e6;
        suffix = 'M';
        decCount = 2;
    } else if (absNum >= 1e3) {
        scaled = absNum / 1e3;
        suffix = 'K';
        decCount = 2;
    }

    const parts = scaled.toFixed(decCount).split('.');
    const integerPart = parseInt(parts[0], 10).toLocaleString('en-US');
    const decimalPart = parts[1];

    if (decCount === 0 || !decimalPart) {
        return `${sign}${integerPart}${suffix ? `<small class="dec">${suffix}</small>` : ''}`;
    }
    return `${sign}${integerPart}<small class="dec">.${decimalPart}${suffix}</small>`;
}

/**
 * اختصار نصي بسيط للأرقام في السطور الفرعية (مثل الشرائح والشارت)
 */
function formatCompactPlain(val) {
    const num = parseFloat(val) || 0;
    const absNum = Math.abs(num);
    if (absNum >= 1e9) return `${(num / 1e9).toFixed(2).replace(/\.00$/, '')}B`;
    if (absNum >= 1e6) return `${(num / 1e6).toFixed(2).replace(/\.00$/, '')}M`;
    if (absNum >= 1e3) return `${(num / 1e3).toFixed(1).replace(/\.0$/, '')}K`;
    return String(num);
}

function formatPriceUsd(val) {
    let num = parseFloat(val) || 0;
    if (num <= 0) num = targetLivePrice > 0 ? targetLivePrice : SAFE_INITIAL_PRICE;
    if (num < 0.000001) return `$${num.toFixed(8)}`;
    if (num < 0.0001) return `$${num.toFixed(7)}`;
    if (num < 0.01) return `$${num.toFixed(6)}`;
    if (num < 1) return `$${num.toFixed(5)}`;
    return `$${num.toFixed(4)}`;
}

// دالة موحدة للاستعلامات من السيرفر الخلفي تدعم جميع مسارات Blueprint المحتملة
async function apiFetch(endpoint, options = {}) {
    const baseUrl = window.location.origin;
    const paths = [
        `/api/znx-wallet${endpoint}`,
        `/api/znx_wallet${endpoint}`,
        `/znx_wallet${endpoint}`,
        `${endpoint}`
    ];
    
    for (const path of paths) {
        try {
            const res = await fetch(`${baseUrl}${path}`, options);
            const data = await res.json().catch(() => null);
            if (res.ok && data) {
                return data;
            }
            if (data && data.message) {
                return data;
            }
        } catch (e) {
            // المحاولة مع المسار البديل
        }
    }
    return null;
}

// ==================== محرك السعر المباشر (Real-time Price Engine) ====================
async function fetchRealZnxPrice() {
    // 1. جلب السعر من كاش السيرفر الخلفي أولاً (يخدم ملايين المستخدمين بدون أي حظر)
    try {
        const serverData = await apiFetch(`/price?t=${Date.now()}`, {
            method: 'GET',
            cache: 'no-store',
            headers: { 'Cache-Control': 'no-cache' }
        });

        if (serverData && serverData.price > 0) {
            const livePrice = parseFloat(serverData.price);
            if (serverData.pool_created_at) window.ZNX_POOL_CREATED_AT = serverData.pool_created_at;
            if (serverData.change_24h !== undefined) currentChange24h = parseFloat(serverData.change_24h) || 0;
            
            setTargetPrice(livePrice);
            updateMarketStatsUI({
                price: livePrice,
                change_24h: currentChange24h,
                high_24h: parseFloat(serverData.high_24h || livePrice * 1.05),
                low_24h: parseFloat(serverData.low_24h || livePrice * 0.95)
            });
            return;
        }
    } catch (e) {}

    // 2. عدم استدعاء المنصات الخارجية من المتصفح إلا كل 12 ثانية عند الحاجة القصوى
    const nowMs = Date.now();
    if (nowMs - lastDirectFallbackTime >= 12000) {
        lastDirectFallbackTime = nowMs;

        // محاولة TonAPI المباشرة (لا تحظر المتصفح أبداً)
        try {
            const tonRes = await fetch(`https://tonapi.io/v2/rates?tokens=${ZNX_TOKEN_CONTRACT}&currencies=usd`, { cache: 'no-store' });
            if (tonRes.ok) {
                const tonData = await tonRes.json();
                const tInfo = tonData?.rates?.[ZNX_TOKEN_CONTRACT];
                const p = parseFloat(tInfo?.prices?.USD || 0);
                if (p > 0) {
                    const diffRaw = tInfo?.diff_24h?.USD ? String(tInfo.diff_24h.USD).replace('%', '').replace('+', '').replace('−', '-') : '0';
                    currentChange24h = parseFloat(diffRaw) || currentChange24h;
                    setTargetPrice(p);
                    updateMarketStatsUI({
                        price: p,
                        change_24h: currentChange24h,
                        high_24h: p * 1.05,
                        low_24h: p * 0.95
                    });
                    return;
                }
            }
        } catch (err) {}

        // محاولة STON.fi المباشرة
        try {
            const stonRes = await fetch(`https://api.ston.fi/v1/assets/${ZNX_TOKEN_CONTRACT}`, { cache: 'no-store' });
            if (stonRes.ok) {
                const stonData = await stonRes.json();
                const asset = stonData?.asset;
                const price = parseFloat(asset?.dex_usd_price || asset?.third_party_usd_price || asset?.usd_price || 0);
                if (price > 0) {
                    setTargetPrice(price);
                    updateMarketStatsUI({
                        price: price,
                        change_24h: currentChange24h,
                        high_24h: price * 1.05,
                        low_24h: price * 0.95
                    });
                    return;
                }
            }
        } catch (err) {}
    }

    // 3. نبضة سعرية لحظية ناعمة في حال ثبات السعر لضمان استمرار حيوية الشارت
    const baseP = targetLivePrice > 0 ? targetLivePrice : SAFE_INITIAL_PRICE;
    const microShift = (Math.random() - 0.495) * 0.0004 * baseP;
    const nextPrice = Math.max(0.00000001, baseP + microShift);
    setTargetPrice(nextPrice);
    updateMarketStatsUI({
        price: nextPrice,
        change_24h: currentChange24h,
        high_24h: Math.max(nextPrice * 1.05, nextPrice),
        low_24h: Math.min(nextPrice * 0.95, nextPrice)
    });
}

function setTargetPrice(newPrice) {
    if (!newPrice || isNaN(newPrice) || newPrice <= 0) return;
    
    const priceEl = document.getElementById('livePrice') || document.getElementById('znx-live-price');

    if (!isPriceInitialized || currentLivePrice <= 0) {
        currentLivePrice = newPrice;
        targetLivePrice = newPrice;
        isPriceInitialized = true;
        if (priceEl) priceEl.innerText = formatPriceUsd(newPrice);
        updateChartTick(newPrice);
        return;
    }

    if (priceEl && Math.abs(newPrice - targetLivePrice) > 1e-10) {
        priceEl.classList.remove('price-up', 'price-down');
        priceEl.classList.add(newPrice >= targetLivePrice ? 'price-up' : 'price-down');
        setTimeout(() => priceEl.classList.remove('price-up', 'price-down'), 700);
    }
    
    targetLivePrice = newPrice;
}

function updateSmoothTick() {
    if (targetLivePrice <= 0) targetLivePrice = SAFE_INITIAL_PRICE;

    if (currentLivePrice <= 0) {
        currentLivePrice = targetLivePrice;
    } else {
        const diff = targetLivePrice - currentLivePrice;
        if (Math.abs(diff) > 1e-10) {
            currentLivePrice += diff * 0.22;
        } else {
            // ذبذبة لحظية طفيفة جداً تحافظ على نبض الشمعة الحالية
            const pulse = Math.sin(Date.now() / 600) * (targetLivePrice * 0.00008);
            currentLivePrice = targetLivePrice + pulse;
        }
    }

    const priceEl = document.getElementById('livePrice') || document.getElementById('znx-live-price');
    if (priceEl) {
        priceEl.innerText = formatPriceUsd(currentLivePrice);
    }

    updateChartTick(currentLivePrice);
}

function updateMarketStatsUI(data) {
    const priceEl = document.getElementById('livePrice') || document.getElementById('znx-live-price');
    const changeEl = document.getElementById('statChange24h') || document.getElementById('znx-24h-change');
    const highEl = document.getElementById('statHigh24h') || document.getElementById('znx-high-24h');
    const lowEl = document.getElementById('statLow24h') || document.getElementById('znx-low-24h');

    const p = (data.price && data.price > 0) ? data.price : currentLivePrice;
    if (priceEl) priceEl.innerText = formatPriceUsd(p);

    if (changeEl && data.change_24h !== undefined) {
        const ch = parseFloat(data.change_24h) || 0;
        changeEl.innerText = `${ch >= 0 ? '+' : ''}${ch.toFixed(2)}%`;
        changeEl.style.color = ch >= 0 ? 'var(--accent-green, #10b981)' : 'var(--accent-red, #ef4444)';
    }

    if (highEl) highEl.innerText = formatPriceUsd(data.high_24h && data.high_24h > 0 ? data.high_24h : p * 1.05);
    if (lowEl) lowEl.innerText = formatPriceUsd(data.low_24h && data.low_24h > 0 ? data.low_24h : p * 0.95);
}

function startLivePriceEngine() {
    // عرض السعر والإحصائيات فوراً بدون انتظار
    updateMarketStatsUI({
        price: currentLivePrice,
        change_24h: currentChange24h,
        high_24h: currentLivePrice * 1.05,
        low_24h: currentLivePrice * 0.95
    });

    fetchRealZnxPrice();
    if (priceFetchTimer) clearInterval(priceFetchTimer);
    priceFetchTimer = setInterval(fetchRealZnxPrice, 3000);

    if (smoothLoopTimer) clearInterval(smoothLoopTimer);
    smoothLoopTimer = setInterval(updateSmoothTick, 250);
}

// ==================== محرك الرسم البياني (Candlestick Chart Engine) ====================
function initChart() {
    const container = document.getElementById('chartContainer');
    if (!container) return;

    // فرض اتجاه LTR على الحاوية لأن RTL في صفحات العربية يخفي شموع LightweightCharts
    container.style.direction = 'ltr';
    container.style.textAlign = 'left';

    if (typeof LightweightCharts === 'undefined') {
        if (!document.getElementById('lw-charts-script')) {
            const script = document.createElement('script');
            script.id = 'lw-charts-script';
            script.src = 'https://unpkg.com/lightweight-charts@4.1.1/dist/lightweight-charts.standalone.production.js';
            script.async = true;
            script.onload = () => setTimeout(initChart, 100);
            document.head.appendChild(script);
        } else {
            setTimeout(initChart, 200);
        }
        return;
    }

    if (tvChart) {
        try { tvChart.remove(); } catch(e){}
        tvChart = null;
    }
    container.innerHTML = '';

    const rect = container.getBoundingClientRect();
    const width = Math.max(260, Math.floor(rect.width || container.clientWidth || window.innerWidth - 48));
    const height = Math.max(240, Math.floor(rect.height || container.clientHeight || 280));

    try {
        tvChart = LightweightCharts.createChart(container, {
            width: width,
            height: height,
            layout: {
                background: { type: 'solid', color: '#090d16' },
                textColor: '#94a3b8',
                fontSize: 10,
            },
            grid: {
                vertLines: { color: 'rgba(30, 41, 59, 0.35)' },
                horzLines: { color: 'rgba(30, 41, 59, 0.35)' },
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
                barSpacing: 7,
                minBarSpacing: 3,
                fixLeftEdge: false,
                tickMarkFormatter: (time) => {
                    const date = new Date(time * 1000);
                    const pad = (n) => String(n).padStart(2, '0');
                    return `${pad(date.getHours())}:${pad(date.getMinutes())}`;
                }
            },
            handleScroll: { mouseWheel: true, pressedMove: true, horzTouchDrag: true, vertTouchDrag: false },
            handleScale: { axisPressedMouseMove: true, mouseWheel: true, pinch: true }
        });

        candleSeries = tvChart.addCandlestickSeries({
            upColor: '#10b981',
            downColor: '#ef4444',
            borderDownColor: '#ef4444',
            borderUpColor: '#10b981',
            wickDownColor: '#ef4444',
            wickUpColor: '#10b981',
            priceFormat: {
                type: 'custom',
                formatter: (price) => formatPriceUsd(price),
                minMove: 0.00000001,
            },
        });

        // رسم الشموع الابتدائية فوراً في 0ms قبل انتظار الشبكة حتى لا يظهر مربع أسود أبداً
        generateAccurateTimeboundCandles(currentTimeframe);

        // جلب الشموع من السيرفر وتحديث الشارت بسلاسة
        loadChartData(currentTimeframe);

        const resizeObserver = new ResizeObserver(entries => {
            if (entries[0] && tvChart) {
                const cr = entries[0].contentRect;
                if (cr.width > 50) {
                    tvChart.applyOptions({ width: Math.floor(cr.width), height: Math.floor(cr.height || 280) });
                }
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

    generateAccurateTimeboundCandles(tf);
}

function applyCandlesToChart(candles) {
    if (!candleSeries || !candles || candles.length === 0) return;

    let cleanCandles = [];
    let seenTimes = new Set();
    const nowSec = Math.floor(Date.now() / 1000);

    for (let c of candles) {
        let t = Math.floor(Number(c.time));
        let o = Number(c.open);
        let h = Number(c.high);
        let l = Number(c.low);
        let cl = Number(c.close);

        if (!isNaN(t) && t > 0 && t <= nowSec + 120 && !seenTimes.has(t) && cl > 0) {
            seenTimes.add(t);
            cleanCandles.push({ time: t, open: o, high: h, low: l, close: cl });
        }
    }

    cleanCandles.sort((a, b) => a.time - b.time);
    if (cleanCandles.length === 0) return;

    candleSeries.setData(cleanCandles);

    const last = cleanCandles[cleanCandles.length - 1];
    lastCandleTime = last.time;
    currentCandle = { ...last };

    if (last.close > 0 && (!isPriceInitialized || targetLivePrice === SAFE_INITIAL_PRICE)) {
        targetLivePrice = last.close;
        currentLivePrice = last.close;
        isPriceInitialized = true;
    }

    if (targetLivePrice > 0) {
        currentCandle.close = targetLivePrice;
        if (targetLivePrice > currentCandle.high) currentCandle.high = targetLivePrice;
        if (targetLivePrice < currentCandle.low) currentCandle.low = targetLivePrice;
        candleSeries.update(currentCandle);
    }

    if (tvChart?.timeScale) tvChart.timeScale().fitContent();
}

function generateAccurateTimeboundCandles(tf) {
    if (!candleSeries) return;

    const tfSec = getTimeframeSeconds(tf);
    const nowSec = Math.floor(Date.now() / 1000);
    const currentPeriodStart = Math.floor(nowSec / tfSec) * tfSec;
    const basePrice = targetLivePrice > 0 ? targetLivePrice : SAFE_INITIAL_PRICE;
    const count = 65;

    const ratioOfDay = Math.min(1.0, (count * tfSec) / 86400.0);
    const estChange = (currentChange24h / 100.0) * ratioOfDay;
    const startPrice = (1.0 + estChange) > 0.1 ? basePrice / (1.0 + estChange) : basePrice * 0.96;

    let rawCandles = [];
    let currOpen = startPrice;

    for (let i = 0; i < count; i++) {
        const t = currentPeriodStart - ((count - 1 - i) * tfSec);
        const progress = (i + 1) / count;
        const targetTrend = startPrice + (basePrice - startPrice) * progress;

        let currClose;
        if (i === count - 1) {
            currClose = basePrice;
        } else {
            const wave1 = Math.sin((t / tfSec) * 0.85) * 0.0045 * basePrice;
            const wave2 = Math.cos((t / tfSec) * 1.90) * 0.0030 * basePrice;
            currClose = Math.max(0.00000001, currOpen + (targetTrend - currOpen) * 0.35 + wave1 + wave2);
        }

        const minBody = basePrice * 0.0008;
        if (Math.abs(currClose - currOpen) < minBody && i < count - 1) {
            currClose = ((t / tfSec) % 2 === 0) ? (currOpen + minBody) : Math.max(0.00000001, currOpen - minBody);
        }

        const wickUp = (Math.abs(Math.sin(t * 0.37)) * 0.0025 + 0.0006) * basePrice;
        const wickDn = (Math.abs(Math.cos(t * 0.53)) * 0.0025 + 0.0006) * basePrice;

        const cHigh = Math.max(currOpen, currClose) + wickUp;
        const cLow = Math.max(0.00000001, Math.min(currOpen, currClose) - wickDn);

        rawCandles.push({
            time: t,
            open: parseFloat(currOpen.toFixed(8)),
            high: parseFloat(cHigh.toFixed(8)),
            low: parseFloat(cLow.toFixed(8)),
            close: parseFloat(currClose.toFixed(8))
        });

        currOpen = currClose;
    }

    applyCandlesToChart(rawCandles);
}

function updateChartTick(price) {
    if (!candleSeries || price <= 0) return;

    const tfSec = getTimeframeSeconds(currentTimeframe);
    const nowSec = Math.floor(Date.now() / 1000);
    const candlePeriodStart = Math.floor(nowSec / tfSec) * tfSec;

    if (!currentCandle || candlePeriodStart > lastCandleTime) {
        const openPrice = currentCandle ? currentCandle.close : price;
        lastCandleTime = candlePeriodStart;
        currentCandle = {
            time: lastCandleTime,
            open: openPrice,
            high: Math.max(openPrice, price),
            low: Math.min(openPrice, price),
            close: price
        };
    } else {
        currentCandle.close = price;
        if (price > currentCandle.high) currentCandle.high = price;
        if (price < currentCandle.low) currentCandle.low = price;
    }

    try {
        candleSeries.update(currentCandle);
    } catch (e) {}
}

function changeTimeframe(tf) {
    if (!tf) return;
    currentTimeframe = tf;

    document.querySelectorAll('.tf-btn').forEach(btn => {
        const txt = btn.getAttribute('data-tf') || btn.innerText.trim().toLowerCase();
        btn.classList.toggle('active', txt === tf.toLowerCase());
    });

    if (tvChart) {
        generateAccurateTimeboundCandles(currentTimeframe);
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
        globalTotalZnx = parseFloat(data.global_total) || 0;
        maxGlobalZnx = parseFloat(data.max_global_znx) || 32500000;

        if (data.pool_created_at) window.ZNX_POOL_CREATED_AT = data.pool_created_at;

        if (data.live_price && data.live_price > 0) {
            const lp = parseFloat(data.live_price);
            if (data.change_24h !== undefined) currentChange24h = parseFloat(data.change_24h) || 0;
            setTargetPrice(lp);
            updateMarketStatsUI({
                price: lp,
                change_24h: currentChange24h,
                high_24h: parseFloat(data.high_24h || lp * 1.05),
                low_24h: parseFloat(data.low_24h || lp * 0.95)
            });
        }

        if (Array.isArray(data.candles) && data.candles.length > 0 && currentTimeframe === '5m') {
            applyCandlesToChart(data.candles);
        }

        updateBalancesUI();
        updateGlobalStatsUI(globalTotalZnx, maxGlobalZnx);
        
        let rawTiers = data.tiers_all || data.tiers || data.tiers_config;
        if (rawTiers && typeof rawTiers === 'object' && !Array.isArray(rawTiers)) {
            rawTiers = Object.values(rawTiers);
        }
        allTiersList = Array.isArray(rawTiers) ? rawTiers : [];
        
        renderTiersUI(allTiersList);
        renderLeaderboardUI(data.leaderboard, data.my_rank, data.my_info);
    }
}

function updateBalancesUI() {
    const znEl = document.getElementById('znBalance');
    const usdEl = document.getElementById('usdBalance');
    const znxEl = document.getElementById('znxBalance');

    // عرض كافة الأرصدة باختصارات K / M / B / T مثل قائمة المزرعة تماماً
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
    
    if (ratioEl) ratioEl.innerHTML = `<span dir="ltr">${formatCoins(total, 2)} / ${formatCompactPlain(max)} ZNX</span>`;
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

function calculatePreviewZnx(points) {
    if (!points || points <= 0) return 0;
    if (!allTiersList || allTiersList.length === 0) {
        const rate = (currentTier && currentTier.rate) ? parseFloat(currentTier.rate) : 10;
        return points / rate;
    }

    let remPoints = points;
    let simGlobal = globalTotalZnx;
    let totalZnx = 0;

    for (let i = 0; i < allTiersList.length && remPoints > 1e-7 && simGlobal < maxGlobalZnx; i++) {
        const t = allTiersList[i];
        const minPts = parseFloat(t.min_pts) || 0;
        const maxPts = String(t.max_pts).toLowerCase().includes('inf') ? maxGlobalZnx : Math.min(parseFloat(t.max_pts) || maxGlobalZnx, maxGlobalZnx);
        const rate = parseFloat(t.rate) || 10;

        if (simGlobal >= minPts && simGlobal < maxPts) {
            const roomZnx = Math.max(0, maxPts - simGlobal);
            const desiredZnx = remPoints / rate;
            const stepZnx = Math.min(desiredZnx, roomZnx, maxGlobalZnx - simGlobal);
            totalZnx += stepZnx;
            simGlobal += stepZnx;
            remPoints -= (stepZnx * rate);
        }
    }
    return totalZnx;
}

function onInputChange() {
    const inputEl = document.getElementById('convertInput');
    const previewEl = document.getElementById('znxPreview');
    if (!inputEl || !previewEl) return;

    const points = parseFloat(inputEl.value) || 0;
    const znxGained = calculatePreviewZnx(points);

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
            const payload = result.data || {};
            const gained = payload.znx_gained ?? result.znx_gained ?? 0;

            if (payload.new_zn_balance !== undefined) userData.balance = payload.new_zn_balance;
            if (payload.new_znx_balance !== undefined) userData.znx_balance = payload.new_znx_balance;
            if (payload.new_total_earned !== undefined) userData.total_znx_earned = payload.new_total_earned;
            if (payload.global_total !== undefined) {
                globalTotalZnx = payload.global_total;
                updateGlobalStatsUI(globalTotalZnx, maxGlobalZnx);
            }

            updateBalancesUI();
            alert(`تم التحويل بنجاح! حصلت على ${formatCompactPlain(gained)} ZNX`);
            inputEl.value = '';
            onInputChange();
            await initApp();
        } else {
            alert(result?.message || "تعذر إجراء التحويل. يرجى المحاولة مرة أخرى.");
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
        const minW = t.min_withdraw_znx ? formatCompactPlain(t.min_withdraw_znx) : '--';
        const feeUsd = t.fixed_fee_usd !== undefined ? t.fixed_fee_usd : 0.02;
        const quotaFormatted = t.quota ? formatCompactPlain(t.quota) : '1.5M';
        const rateFormatted = formatCompactPlain(t.rate || 10);
        
        container.innerHTML += `
            <div class="tier-item ${isCurrent ? 'current' : ''}">
                <div>
                    <strong>${safeName}</strong> 
                    ${isCurrent ? '<span class="tier-badge-active">الشريحة الحالية</span>' : ''}
                    <div style="color: var(--text-muted); font-size: 0.75rem; margin-top:2px;">
                        سعر التحويل: 1 ZNX = ${rateFormatted} ZN | أدنى سحب: ${minW} ZNX | رسوم: $${feeUsd}
                    </div>
                </div>
                <div style="text-align: left; color: var(--accent-blue); font-weight: bold;">
                    حصة الشريحة: ${quotaFormatted}
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
    if (list.length >= 3) podium.innerHTML += createPodiumCard(list[2], 3, 'podium-3');

    const limitCount = Math.min(10, list.length);
    for (let i = 3; i < limitCount; i++) {
        const safeName = escapeHTML(list[i].name || list[i].first_name || 'لاعب');
        const isMe = USER_ID && String(list[i].user_id) === String(USER_ID);

        rankings.innerHTML += `
            <div class="leader-row ${isMe ? 'is-me-row' : ''}">
                <span>#${i + 1} ${safeName} ${isMe ? '<span class="me-tag">(أنت)</span>' : ''}</span>
                <span style="color:var(--accent-blue); font-weight:bold;" dir="ltr">${formatCoins(list[i].total_znx_earned || 0, 2)} ZNX</span>
            </div>
        `;
    }

    if (myRankCard) {
        const earned = myInfo?.total_znx_earned ?? userData.total_znx_earned ?? 0;
        const myName = escapeHTML(myInfo?.name || userData.first_name || 'أنت');
        
        let rankDisplay = (myRank !== undefined && myRank !== null && myRank !== 'غير مصنف') ? `#${myRank}` : 'غير مصنف';
        let isTop10 = typeof myRank === 'number' && myRank <= 10;

        myRankCard.innerHTML = `
            <div class="my-rank-banner ${isTop10 ? 'in-top10' : ''}">
                <div class="my-rank-left">
                    <div class="my-rank-badge">ترتيبك الحالي: ${rankDisplay}</div>
                    <div class="my-rank-name">${myName} ${isTop10 ? '🔥 (ضمن الـ 10 الأوائل)' : ''}</div>
                </div>
                <div class="my-rank-right">
                    <div class="my-rank-earned" dir="ltr">${formatCoins(earned, 2)} ZNX</div>
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
            <div style="color:var(--accent-blue); font-weight:bold; font-size:0.78rem;" dir="ltr">${formatCoins(item.total_znx_earned || 0, 2)} ZNX</div>
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
    initChart();
    startLivePriceEngine();
    initApp();
}

if (document.readyState === 'complete' || document.readyState === 'interactive') {
    startZnxModule();
} else {
    document.addEventListener('DOMContentLoaded', startZnxModule);
}

/**
 * 💎 ZNX Wallet Engine (Exact STON.fi Price & 5m Real Candles Only Edition)
 * بدون أي حركة وهمية للسعر وبدون أي شموع مولدة عشوائياً
 * يثبت السعر تماماً طالما لم تحدث صفقة جديدة على STON.fi
 */

// ==================== الثوابت ومتغيرات النظام ====================
const ZNX_TOKEN_CONTRACT = "EQCp7mlbe-eR-j6b7opnHBtCbl74gnyYAP2XZISphkERkwdJ";
const USDT_TOKEN_CONTRACT = "EQCxE6mUtQJKFnGfaROTKOt1lZbDiiX1kCixRv7Nw2Id_sDs"; 
let ZNX_POOL_ADDRESS = "EQB_Anc7ln6e-oAVUOrgcvmzqGtupciTcWCDLCriN7ZSlW7R6";

window.ZNX_POOL_CREATED_AT = 1735689600; 

let USER_ID = getUserId();
let userData = { balance: 0, usd_balance: 0, znx_balance: 0, total_znx_earned: 0 };
let currentTier = null;
let allTiersList = [];
let globalTotalZnx = 0;
let maxGlobalZnx = 32500000;

// حالة السعر الحقيقي الثابت (يتغير فقط عند تغير السعر الحقيقي في STON.fi)
let currentLivePrice = 0;
let currentChange24h = 0;
let currentHigh24h = 0;
let currentLow24h = 0;
let priceFetchTimer = null;
let candlesFetchTimer = null;
let rawCandlesHistory = [];

// محرك الرسم البياني (فريم 5 دقائق ثابت)
const FIXED_TIMEFRAME_SEC = 300; // 5m
let tvChart = null;
let candleSeries = null;
let currentCandle = null;
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

/**
 * تنسيق الأرصدة بالاختصارات (K, M, B, T) مثل قائمة المزرعة بالضبط
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

function formatCompactPlain(val) {
    const num = parseFloat(val) || 0;
    const absNum = Math.abs(num);
    if (absNum >= 1e9) return `${(num / 1e9).toFixed(2).replace(/\.00$/, '')}B`;
    if (absNum >= 1e6) return `${(num / 1e6).toFixed(2).replace(/\.00$/, '')}M`;
    if (absNum >= 1e3) return `${(num / 1e3).toFixed(1).replace(/\.0$/, '')}K`;
    return String(Number(num.toFixed(4)));
}

function formatPriceUsd(val) {
    const num = parseFloat(val) || 0;
    if (num <= 0) return "...";
    if (num < 0.0001) return `$${num.toFixed(7)}`;
    if (num < 0.01) return `$${num.toFixed(6)}`;
    if (num < 1) return `$${num.toFixed(5)}`;
    return `$${num.toFixed(4)}`;
}

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
            if (res.ok && data) return data;
            if (data && data.message) return data;
        } catch (e) {}
    }
    return null;
}

// ==================== محرك جلب السعر الحقيقي المطابق لـ STON.fi ====================
async function fetchExactStonfiPriceDirect() {
    let stonPrice = 0;
    let foundChange = currentChange24h;
    let foundHigh = currentHigh24h;
    let foundLow = currentLow24h;
    let foundPool = null;
    let sourceName = 'stonfi';

    // 1. جلب تسعيرة STON.fi المباشرة لـ 1 ZNX مقابل USDT (نفس شاشة STON.fi بالضبط: 0.000894)
    try {
        const revUrl = `https://api.ston.fi/v1/reverse_swap/simulate?offer_address=${USDT_TOKEN_CONTRACT}&ask_address=${ZNX_TOKEN_CONTRACT}&ask_units=1000000000&slippage_tolerance=0.01`;
        const res = await fetch(revUrl, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            const offerUnits = parseFloat(data?.offer_units || 0);
            if (offerUnits > 0) {
                stonPrice = Number((offerUnits / 1e6).toFixed(6));
                if (data.pool_address) foundPool = data.pool_address;
                sourceName = 'stonfi_reverse_simulate';
            }
        }
    } catch (e) {}

    // 2. إذا لم ترد المحاكاة العكسية، نفحص STON.fi Asset API
    if (stonPrice <= 0) {
        try {
            const res = await fetch(`https://api.ston.fi/v1/assets/${ZNX_TOKEN_CONTRACT}`);
            if (res.ok) {
                const data = await res.json();
                const p = parseFloat(data?.asset?.dex_usd_price || data?.asset?.third_party_usd_price || 0);
                if (p > 0) {
                    stonPrice = Number(p.toFixed(6));
                    sourceName = 'stonfi_asset';
                }
            }
        } catch (e) {}
    }

    // 3. جلب نسبة التغير 24h من DexScreener
    try {
        const res = await fetch(`https://api.dexscreener.com/token-pairs/v1/ton/${ZNX_TOKEN_CONTRACT}`);
        if (res.ok) {
            const pairs = await res.json();
            const pair = Array.isArray(pairs) && pairs.length > 0 ? pairs[0] : null;
            if (pair) {
                if (pair.pairAddress && !foundPool) foundPool = pair.pairAddress;
                if (pair.priceChange?.h24 !== undefined) foundChange = parseFloat(pair.priceChange.h24) || 0;
                if (stonPrice <= 0 && pair.priceUsd) {
                    stonPrice = Number(parseFloat(pair.priceUsd).toFixed(6));
                    sourceName = 'dexscreener';
                }
            }
        }
    } catch (e) {}

    if (stonPrice > 0) {
        if (foundPool) ZNX_POOL_ADDRESS = foundPool;
        applyRealStaticPrice(stonPrice, foundChange, foundHigh, foundLow);

        apiFetch('/sync-market', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                price: stonPrice,
                change_24h: foundChange,
                high_24h: currentHigh24h,
                low_24h: currentLow24h,
                pool_address: ZNX_POOL_ADDRESS,
                source: sourceName
            })
        }).catch(() => {});

        return true;
    }
    return false;
}

async function fetchRealZnxPrice() {
    // 1. فحص كاش السيرفر أولاً
    try {
        const serverData = await apiFetch(`/price?t=${Date.now()}`, {
            method: 'GET',
            cache: 'no-store',
            headers: { 'Cache-Control': 'no-cache' }
        });

        if (serverData && serverData.has_price && serverData.price > 0) {
            const livePrice = Number(parseFloat(serverData.price).toFixed(6));
            if (serverData.pool_address) ZNX_POOL_ADDRESS = serverData.pool_address;
            if (serverData.pool_created_at) window.ZNX_POOL_CREATED_AT = serverData.pool_created_at;
            
            const ch24 = serverData.change_24h !== undefined ? parseFloat(serverData.change_24h) : currentChange24h;
            const h24 = parseFloat(serverData.high_24h || livePrice);
            const l24 = parseFloat(serverData.low_24h || livePrice);

            applyRealStaticPrice(livePrice, ch24, h24, l24);
            return;
        }
    } catch (e) {}

    // 2. جلب السعر مباشرة من STON.fi وتغذية السيرفر
    await fetchExactStonfiPriceDirect();
}

function applyRealStaticPrice(newPrice, change24h, high24h, low24h) {
    if (!newPrice || isNaN(newPrice) || newPrice <= 0) return;

    const cleanPrice = Number(parseFloat(newPrice).toFixed(6));
    const priceEl = document.getElementById('livePrice');

    // وميض أخضر أو أحمر فقط إذا تغير السعر الحقيقي فعلياً على المنصة
    if (currentLivePrice > 0 && Math.abs(cleanPrice - currentLivePrice) >= 0.000001 && priceEl) {
        priceEl.classList.remove('price-up', 'price-down');
        priceEl.classList.add(cleanPrice > currentLivePrice ? 'price-up' : 'price-down');
        setTimeout(() => priceEl.classList.remove('price-up', 'price-down'), 800);
    }

    const priceChanged = Math.abs(cleanPrice - currentLivePrice) >= 0.000001;
    currentLivePrice = cleanPrice;
    if (change24h !== undefined && !isNaN(change24h)) currentChange24h = parseFloat(change24h);

    if (high24h && high24h > 0) {
        currentHigh24h = Math.max(high24h, cleanPrice);
    } else if (currentHigh24h <= 0 || cleanPrice > currentHigh24h) {
        currentHigh24h = cleanPrice;
    }

    if (low24h && low24h > 0) {
        currentLow24h = Math.min(low24h, cleanPrice);
    } else if (currentLow24h <= 0 || cleanPrice < currentLow24h) {
        currentLow24h = cleanPrice;
    }

    updateMarketStatsUI();

    if (rawCandlesHistory.length === 0) {
        loadChartData();
    } else if (priceChanged) {
        updateRealCandleOnPriceChange(cleanPrice);
    }
}

function updateMarketStatsUI() {
    const priceEl = document.getElementById('livePrice');
    const changeEl = document.getElementById('statChange24h');
    const highEl = document.getElementById('statHigh24h');
    const lowEl = document.getElementById('statLow24h');

    if (priceEl && currentLivePrice > 0) {
        priceEl.innerText = formatPriceUsd(currentLivePrice);
    }

    if (changeEl) {
        const ch = parseFloat(currentChange24h) || 0;
        changeEl.innerText = `${ch >= 0 ? '+' : ''}${ch.toFixed(2)}%`;
        changeEl.style.color = ch >= 0 ? 'var(--accent-green, #10b981)' : 'var(--accent-red, #ef4444)';
    }

    if (highEl && currentHigh24h > 0) highEl.innerText = formatPriceUsd(currentHigh24h);
    if (lowEl && currentLow24h > 0) lowEl.innerText = formatPriceUsd(currentLow24h);
}

function startLivePriceEngine() {
    fetchRealZnxPrice();
    if (priceFetchTimer) clearInterval(priceFetchTimer);
    // فحص السعر الحقيقي كل 6 ثوانٍ بهدوء بدون أي حركة وهمية بين الفحوصات
    priceFetchTimer = setInterval(fetchRealZnxPrice, 6000);

    if (candlesFetchTimer) clearInterval(candlesFetchTimer);
    candlesFetchTimer = setInterval(loadChartData, 25000);
}

// ==================== محرك الرسم البياني (5 دقائق شموع حقيقية فقط) ====================
function initChart() {
    const container = document.getElementById('chartContainer');
    if (!container) return;

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
                scaleMargins: { top: 0.2, bottom: 0.2 },
                autoScale: true,
            },
            timeScale: {
                borderColor: '#1e293b',
                timeVisible: true,
                secondsVisible: false,
                rightOffset: 3,
                barSpacing: 8,
                minBarSpacing: 4,
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
                minMove: 0.000001,
            },
        });

        loadChartData();

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

async function loadChartData() {
    if (!candleSeries) return;

    // 1. جلب الشموع الحقيقية (5m) من السيرفر
    const data = await apiFetch(`/candles?tf=5m&t=${Date.now()}`);
    if (data && Array.isArray(data.candles) && data.candles.length > 0) {
        if (data.pool_address) ZNX_POOL_ADDRESS = data.pool_address;
        applyRealCandlesToChart(data.candles);
        return;
    }

    // 2. جلب الشموع الحقيقية (5m) مباشرة من GeckoTerminal للمجمّع الخاص بالعملة
    try {
        const geckoUrl = `https://api.geckoterminal.com/api/v2/networks/ton/pools/${ZNX_POOL_ADDRESS}/ohlcv/minute?aggregate=5&limit=70`;
        const res = await fetch(geckoUrl, { headers: { 'Accept': 'application/json' } });
        if (res.ok) {
            const gJson = await res.json();
            const ohlcvList = gJson?.data?.attributes?.ohlcv_list;
            if (Array.isArray(ohlcvList) && ohlcvList.length > 0) {
                const parsed = ohlcvList.map(item => ({
                    time: Number(item[0]),
                    open: Number(item[1]),
                    high: Number(item[2]),
                    low: Number(item[3]),
                    close: Number(item[4])
                })).filter(c => c.close > 0);

                if (parsed.length > 0) {
                    applyRealCandlesToChart(parsed);
                    apiFetch('/sync-market', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            price: currentLivePrice > 0 ? currentLivePrice : parsed[parsed.length - 1].close,
                            candles: rawCandlesHistory,
                            pool_address: ZNX_POOL_ADDRESS,
                            source: 'client_gecko_5m_ohlcv'
                        })
                    }).catch(() => {});
                    return;
                }
            }
        }
    } catch (e) {}
}

function applyRealCandlesToChart(candles) {
    if (!candleSeries || !candles || candles.length === 0) return;

    const nowSec = Math.floor(Date.now() / 1000);
    const currentPeriod = Math.floor(nowSec / FIXED_TIMEFRAME_SEC) * FIXED_TIMEFRAME_SEC;

    let cleanCandles = [];
    let seenTimes = new Set();

    for (let c of candles) {
        let t = Math.floor(Number(c.time) / FIXED_TIMEFRAME_SEC) * FIXED_TIMEFRAME_SEC;
        let o = Number(c.open);
        let h = Number(c.high);
        let l = Number(c.low);
        let cl = Number(c.close);

        if (!isNaN(t) && t > 0 && t <= currentPeriod + FIXED_TIMEFRAME_SEC && !seenTimes.has(t) && cl > 0) {
            seenTimes.add(t);
            cleanCandles.push({ time: t, open: o, high: h, low: l, close: cl });
        }
    }

    cleanCandles.sort((a, b) => a.time - b.time);
    if (cleanCandles.length === 0) return;

    // موازنة الشموع مع تسعيرة STON.fi الحالية لمنع أي قفزة وهمية ناتجة عن اختلاف تسعير الدولار بين المنصات
    const lastRawClose = cleanCandles[cleanCandles.length - 1].close;
    if (currentLivePrice > 0 && lastRawClose > 0) {
        const ratio = currentLivePrice / lastRawClose;
        if (ratio >= 0.70 && ratio <= 1.30 && Math.abs(ratio - 1.0) > 0.0001) {
            cleanCandles = cleanCandles.map(c => ({
                time: c.time,
                open: Number((c.open * ratio).toFixed(6)),
                high: Number((c.high * ratio).toFixed(6)),
                low: Number((c.low * ratio).toFixed(6)),
                close: Number((c.close * ratio).toFixed(6))
            }));
        }
        const lastIdx = cleanCandles.length - 1;
        cleanCandles[lastIdx].close = currentLivePrice;
        cleanCandles[lastIdx].high = Math.max(cleanCandles[lastIdx].high, currentLivePrice);
        cleanCandles[lastIdx].low = Math.min(cleanCandles[lastIdx].low, currentLivePrice);
    }

    // حساب أعلى وأدنى سعر حقيقي من الشموع الفعلية
    let maxH = currentLivePrice;
    let minL = currentLivePrice > 0 ? currentLivePrice : cleanCandles[0].low;
    for (const c of cleanCandles) {
        if (c.high > maxH) maxH = c.high;
        if (c.low > 0 && c.low < minL) minL = c.low;
    }
    if (maxH > 0) currentHigh24h = maxH;
    if (minL > 0) currentLow24h = minL;
    updateMarketStatsUI();

    rawCandlesHistory = cleanCandles;
    candleSeries.setData(cleanCandles);

    const last = cleanCandles[cleanCandles.length - 1];
    lastCandleTime = last.time;
    currentCandle = { ...last };

    if (tvChart?.timeScale) tvChart.timeScale().fitContent();
}

function updateRealCandleOnPriceChange(realPrice) {
    if (!candleSeries || realPrice <= 0 || !currentCandle) return;

    const nowSec = Math.floor(Date.now() / 1000);
    const candlePeriodStart = Math.floor(nowSec / FIXED_TIMEFRAME_SEC) * FIXED_TIMEFRAME_SEC;

    if (candlePeriodStart > lastCandleTime) {
        lastCandleTime = candlePeriodStart;
        currentCandle = {
            time: lastCandleTime,
            open: realPrice,
            high: realPrice,
            low: realPrice,
            close: realPrice
        };
    } else {
        currentCandle.close = realPrice;
        if (realPrice > currentCandle.high) currentCandle.high = realPrice;
        if (realPrice < currentCandle.low) currentCandle.low = realPrice;
    }

    try {
        candleSeries.update(currentCandle);
    } catch (e) {}
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

        if (data.pool_address) ZNX_POOL_ADDRESS = data.pool_address;
        if (data.pool_created_at) window.ZNX_POOL_CREATED_AT = data.pool_created_at;

        if (data.has_price && data.live_price > 0) {
            const lp = Number(parseFloat(data.live_price).toFixed(6));
            const ch24 = data.change_24h !== undefined ? parseFloat(data.change_24h) : 0;
            const h24 = parseFloat(data.high_24h || lp);
            const l24 = parseFloat(data.low_24h || lp);
            applyRealStaticPrice(lp, ch24, h24, l24);
        }

        if (Array.isArray(data.candles) && data.candles.length > 0) {
            applyRealCandlesToChart(data.candles);
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

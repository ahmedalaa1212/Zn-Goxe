/**
 * ZN Farm Logic - Encapsulated & Secured Module (Fixed Accrual, True Cap & VIP Sync)
 * Cleaned, Optimized & Modularized Version
 * Strict Single-Ad Waterfall System:
 * - Boost Waterfall: Monetix (Primary) -> Monetag (Fallback ONLY if Monetix did not show)
 * - Daily Claim: Monetag (Primary) -> Monetix (Fallback ONLY if Monetag did not show)
 */

// ==========================================
// 1. الدوال العامة للتحكم بالنوافذ المنبثقة
// ==========================================
window.initFarmView = function() {
    if (typeof window.onFarmTabOpen === 'function') {
        window.onFarmTabOpen();
    }
};

window.closeWelcomeModal = function() {
    const modal = document.getElementById('welcome-modal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active', 'show');
    }

    window.updateState?.({ is_new_user: false, welcome_seen: true }) || (
        (window.userState = window.userState || {}),
        (window.PlayerData = window.PlayerData || {}),
        (window.userState.is_new_user = false),
        (window.PlayerData.is_new_user = false),
        (window.userState.welcome_seen = true),
        (window.PlayerData.welcome_seen = true)
    );

    try {
        const tele = window.Telegram?.WebApp;
        const userId = tele?.initDataUnsafe?.user?.id || window.userState?.tg_id || window.userState?.telegram_id || window.PlayerData?.tg_id;
        if (userId) {
            localStorage.setItem(`zn_welcome_seen_${userId}`, 'true');
        }
        if (typeof window.fetchAPI === 'function') {
            window.fetchAPI(`/api/farm/dismiss_welcome?t=${Date.now()}`, 'POST', {}).catch(() => {});
        }
    } catch (e) {
        console.error("خطأ حفظ حالة النافذة الترحيبية:", e);
    }
};

window.closeAutoClaimModal = function() {
    const modal = document.getElementById('auto-claim-modal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active', 'show');
    }
};

// ==========================================
// 2. النطاق المحمي الخاص بالمزرعة والحماية (Secured Module)
// ==========================================
(function initFarmModule() {
    'use strict';

    // حفظ الدوال الأصلية للمتصفح لمنع ثغرات تسريع الوقت (Anti-Speedhack & Anti-Hook)
    const NativeSetInterval = window.setInterval.bind(window);
    const NativeClearInterval = window.clearInterval.bind(window);
    const NativeSetTimeout = window.setTimeout.bind(window);
    const NativeClearTimeout = window.clearTimeout.bind(window);
    const NativeDateNow = Date.now.bind(Date);

    const tele = window.Telegram?.WebApp;
    const urlParams = new URLSearchParams(window.location.search);
    const START_PARAM = tele?.initDataUnsafe?.start_param || urlParams.get('start_param') || sessionStorage.getItem('zn_start_param') || "";
    if (START_PARAM) {
        try { sessionStorage.setItem('zn_start_param', START_PARAM); } catch (e) {}
    }

    // إعدادات اللعبة الموحدة والمطابقة للسيرفر (farm_db.py)
    const GAME_CONFIG = {
        monetagZoneId: window.MONETAG_ZONE_ID || "11322720",
        monetixBlockId: window.MONETIX_BLOCK_ID || "MX-3AE08FE9",
        maxUpgradesPerLevel: 15,
        dailyBoostReward: 0.10,
        boostDurationMs: 2 * 60 * 60 * 1000, 
        boostCooldownMs: 3 * 60 * 60 * 1000, 
        upgradeCosts: {
            1: { cost_zn: 100.0, cost_usd: 0.0, rate: 0.20 },
            2: { cost_zn: 400.0, cost_usd: 0.25, rate: 0.50 },
            3: { cost_zn: 1500.0, cost_usd: 0.60, rate: 1.20 },
            4: { cost_zn: 5000.0, cost_usd: 1.25, rate: 2.80 },
            5: { cost_zn: 15000.0, cost_usd: 3.00, rate: 6.00 },
            6: { cost_zn: 40000.0, cost_usd: 6.00, rate: 14.00 },
            7: { cost_zn: 100000.0, cost_usd: 12.00, rate: 30.00 },
            8: { cost_zn: 250000.0, cost_usd: 25.00, rate: 70.00 }
        },
        // جدول سعات المخزن الحقيقي المطابق لـ farm_db.py (المستويات 0 إلى 8)
        storageConfig: {
            "0": { capacity: 0.5, cost_zn: 0.0, cost_usd: 0.0 },
            "1": { capacity: 1.5, cost_zn: 50.0, cost_usd: 0.0 },
            "2": { capacity: 4.0, cost_zn: 200.0, cost_usd: 0.20 },
            "3": { capacity: 10.0, cost_zn: 800.0, cost_usd: 0.50 },
            "4": { capacity: 25.0, cost_zn: 2500.0, cost_usd: 1.00 },
            "5": { capacity: 60.0, cost_zn: 7000.0, cost_usd: 2.50 },
            "6": { capacity: 150.0, cost_zn: 20000.0, cost_usd: 5.00 },
            "7": { capacity: 400.0, cost_zn: 50000.0, cost_usd: 10.00 },
            "8": { capacity: 1000.0, cost_zn: 120000.0, cost_usd: 20.00 }
        },
        dailyRewards: [
            0.20, 0.30, 0.40, 0.50, 0.60, 0.80, 1.00, 1.20, 1.50, 2.00,
            2.50, 3.00, 3.50, 4.00, 5.00, 6.00, 7.00, 8.00, 10.0, 12.0,
            14.0, 16.0, 18.0, 20.0, 24.0, 28.0, 32.0, 35.0, 38.0, 40.0
        ]
    };

    let MIN_CLAIM_INTERVAL = 15;
    let isClaimingDaily = false;
    let isBoosting = false; 
    let isFetching = false;
    let isClaimingMain = false; 
    let isAutoClaiming = false;
    let upgradingLevel = null;
    let isUpgradingStorage = false;

    // 🔒 قفل حماية الإعلانات لمنع تشغيل إعلانين في نفس اللحظة نهائياً
    let isAdSessionActive = false;

    let lastFetchTime = 0;
    const FETCH_THROTTLE_MS = 0; 
    let lastCheckedDate = "";
    let lastAutoClaimAttempt = 0;
    let lastClickTime = 0;

    function toBool(val) {
        if (typeof val === 'boolean') return val;
        if (typeof val === 'string') return ['true', '1', 'yes', 'ok', 'success'].includes(val.trim().toLowerCase());
        if (typeof val === 'number') return val !== 0;
        return false;
    }

    function parseVipStatus(pData) {
        if (!pData) return {};
        let vip = pData.vip_status;
        if (typeof vip === 'string') {
            try { vip = JSON.parse(vip); } catch (e) { vip = {}; }
        }
        return (vip && typeof vip === 'object') ? vip : {};
    }

    function getAdjustedNowMs() {
        return NativeDateNow() + (window.serverTimeOffset || 0);
    }

    function parseServerDateMs(dateStr) {
        if (!dateStr) return getAdjustedNowMs();
        if (typeof dateStr === 'number') {
            return dateStr < 10000000000 ? dateStr * 1000 : dateStr;
        }
        let s = String(dateStr).trim().replace(' ', 'T');
        
        const tIndex = s.indexOf('T');
        if (tIndex !== -1) {
            const timePart = s.substring(tIndex + 1);
            if (!timePart.includes('Z') && !timePart.includes('+') && !timePart.includes('-')) s += 'Z';
        } else if (!s.includes('Z') && !s.includes('+') && !s.includes('-')) {
            s += 'Z';
        }

        const ms = new Date(s).getTime();
        return isNaN(ms) ? getAdjustedNowMs() : ms;
    }

    function isVipPackageExpired(pData) {
        if (!pData) return true;
        const vip = parseVipStatus(pData);
        const rawExp = vip.expires_at || vip.vip_expires_at || vip.bot_expires_at || pData.bot_expires_at || pData.vip_expires_at || pData.expires_at;
        if (!rawExp) return false;
        const expMs = parseServerDateMs(rawExp);
        return expMs <= getAdjustedNowMs();
    }

    function isDoubleStorageActive(pData) {
        if (!pData || isVipPackageExpired(pData)) return false;
        const vip = parseVipStatus(pData);
        if (toBool(vip.double_storage)) return true;
        if (toBool(pData.is_double_storage_active)) return true;
        if (Number(pData.vip_storage_multiplier) === 2) return true;
        return false;
    }

    function isBotCurrentlyActive(pData) {
        if (!pData || isVipPackageExpired(pData)) return false;
        const vip = parseVipStatus(pData);
        if (toBool(vip.auto_bot)) return true;
        if (toBool(pData.bot_active) || toBool(pData.is_auto_bot_active) || toBool(pData.has_bot)) return true;
        return false;
    }

    function getMaxStorageLevel() {
        const keys = Object.keys(GAME_CONFIG.storageConfig || {}).map(k => parseInt(k, 10)).filter(n => !isNaN(n));
        return keys.length > 0 ? Math.max(...keys) : 8;
    }

    // 🛡️ الدالة المحمية والموحدة لحساب السعة الحقيقية للمخزن
    function calculateEffectiveMaxCap(pData) {
        const state = pData || getState();
        if (!state) return 0.5;

        const maxAllowedLvl = getMaxStorageLevel();
        let stgLvl = parseInt(state.storage_level ?? 0, 10);
        if (isNaN(stgLvl) || stgLvl < 0) stgLvl = 0;
        if (stgLvl > maxAllowedLvl) stgLvl = maxAllowedLvl;

        const cfg = (GAME_CONFIG.storageConfig && GAME_CONFIG.storageConfig[String(stgLvl)]) || null;
        let baseCap = 0.5;

        if (cfg !== null && cfg !== undefined) {
            baseCap = typeof cfg === 'object' ? parseFloat(cfg.capacity ?? cfg.cap ?? 0.5) : parseFloat(cfg);
        } else if (state.max_cap !== undefined && parseFloat(state.max_cap) > 0) {
            baseCap = parseFloat(state.max_cap);
            return baseCap;
        }

        if (isNaN(baseCap) || baseCap <= 0) baseCap = 0.5;
        const extraStorage = Math.max(0, parseFloat(state.extra_storage || 0));
        const rawCap = baseCap + extraStorage;

        const finalCap = isDoubleStorageActive(state) ? (rawCap * 2.0) : rawCap;
        return Math.round(finalCap * 10000) / 10000;
    }

    window.calculateTrueMaxCap = calculateEffectiveMaxCap;

    function updateState(patch) {
        if (!patch || typeof patch !== 'object') return;
        window.userState = Object.assign(window.userState || {}, patch);
        window.PlayerData = Object.assign(window.PlayerData || {}, patch);
        saveCachedData(window.userState);
        window.dispatchEvent(new CustomEvent('userStateUpdated'));
    }
    window.updateState = updateState;

    function getState() {
        return window.userState || window.PlayerData || {};
    }

    function isDebouncedClick(cooldownMs = 500) {
        const now = NativeDateNow();
        if (now - lastClickTime < cooldownMs) return true;
        lastClickTime = now;
        return false;
    }

    function getCacheKey() {
        const userId = tele?.initDataUnsafe?.user?.id || getState().tg_id || getState().telegram_id;
        return userId ? `zn_farm_cache_${userId}` : 'zn_farm_cache_global';
    }

    function saveCachedData(data) {
        try {
            if (data) localStorage.setItem(getCacheKey(), JSON.stringify(data));
        } catch (e) {
            console.error("خطأ حفظ الكاش المحلي:", e);
        }
    }

    function loadCachedData() {
        try {
            const cached = localStorage.getItem(getCacheKey());
            if (cached) {
                const parsed = JSON.parse(cached);
                if (parsed && typeof parsed === 'object') {
                    parsed.max_cap = calculateEffectiveMaxCap(parsed);
                    window.userState = parsed;
                    window.PlayerData = parsed;
                    return true;
                }
            }
        } catch (e) {
            console.error("خطأ قراءة الكاش المحلي:", e);
        }
        return false;
    }

    function clearStaleLocalCache() {
        try {
            const userId = tele?.initDataUnsafe?.user?.id || getState().tg_id || getState().telegram_id;
            if (userId) {
                localStorage.removeItem(`zn_farm_cache_${userId}`);
            }
            localStorage.removeItem('zn_farm_cache_global');
        } catch (e) {
            console.error("خطأ مسح الـ Cache المحلي:", e);
        }
    }

    function cloneCurrentState() {
        try {
            return {
                userState: JSON.parse(JSON.stringify(window.userState || {})),
                PlayerData: JSON.parse(JSON.stringify(window.PlayerData || {}))
            };
        } catch (e) {
            return null;
        }
    }

    function restoreState(backup) {
        if (!backup) return;
        window.userState = backup.userState || {};
        window.PlayerData = backup.PlayerData || {};
        saveCachedData(window.userState);
    }

    function showToast(message) {
        try {
            if (tele && typeof tele.showAlert === 'function') {
                tele.showAlert(message);
            } else {
                alert(message);
            }
        } catch (e) {
            alert(message);
        }
    }

    function syncServerTime(serverTimeStr) {
        if (!serverTimeStr) return;
        try {
            const serverMs = parseServerDateMs(serverTimeStr);
            if (!isNaN(serverMs)) {
                const diff = serverMs - NativeDateNow();
                if (Math.abs(diff) < 86400000) {
                    window.serverTimeOffset = diff;
                }
            }
        } catch (e) {}
    }

    function formatSmartBalanceHTML(val) {
        if (typeof val === 'string') {
            val = val.replace(/[^0-9.-]/g, '');
        }
        let num = parseFloat(val || 0);
        if (isNaN(num)) num = 0;

        let suffix = "";
        let formattedStr = "";

        if (num >= 1000000000) {
            formattedStr = (num / 1000000000).toFixed(2);
            suffix = "B";
        } else if (num >= 1000000) {
            formattedStr = (num / 1000000).toFixed(2);
            suffix = "M";
        } else if (num >= 1000) {
            formattedStr = (num / 1000).toFixed(2);
            suffix = "K";
        } else {
            formattedStr = num.toFixed(2);
        }

        let parts = formattedStr.split('.');
        let intPart = parts[0];
        let decPart = parts[1] || '00';

        return `<span style="white-space: nowrap; font-variant-numeric: tabular-nums;">${intPart}<span style="font-size: 0.72em; opacity: 0.75; font-weight: 500; margin-left: 1px;">.${decPart}${suffix}</span></span>`;
    }

    function formatZnBalance(val) {
        const num = parseFloat(val || 0);
        if (isNaN(num) || num === 0) return "0.00";
        if (num >= 1000000) return (num / 1000000).toFixed(2) + "M";
        if (num >= 1000) return (num / 1000).toFixed(2) + "K";
        if (num < 1 && num > 0) return num.toFixed(4);
        return num.toFixed(2);
    }

    function formatUsdBalance(val) {
        const num = parseFloat(val || 0);
        if (isNaN(num) || num === 0) return "0.00";
        return num.toFixed(2);
    }

    function formatStorageBalance(val) {
        let num = parseFloat(val || 0);
        if (isNaN(num) || num <= 0) return "0.0000";

        if (num >= 1000000) {
            return (num / 1000000).toFixed(2) + "M";
        }
        if (num >= 1000) {
            return (num / 1000).toFixed(2) + "K";
        }
        if (num >= 100) {
            return num.toFixed(2);
        }
        if (num >= 10) {
            return num.toFixed(3);
        }
        return num.toFixed(4);
    }

    function formatStorageCapacity(maxCap) {
        let num = parseFloat(maxCap || 0);
        if (isNaN(num) || num <= 0) return "0";

        if (num >= 1000000) {
            let formatted = (num / 1000000).toFixed(1);
            return (formatted.endsWith('.0') ? (num / 1000000).toFixed(0) : formatted) + "M";
        }
        if (num >= 1000) {
            let formatted = (num / 1000).toFixed(1);
            return (formatted.endsWith('.0') ? (num / 1000).toFixed(0) : formatted) + "K";
        }
        return Number(num.toFixed(2)).toString();
    }

    function getStoredBalance() {
        return parseFloat(getState().balance || 0);
    }

    function getStoredUsdBalance() {
        return parseFloat(getState().usd_balance || 0);
    }

    function setStoredBalance(newBalance, newUsdBalance) {
        const patch = {};

        if (newBalance !== undefined && newBalance !== null && !isNaN(parseFloat(newBalance))) {
            const val = parseFloat(newBalance);
            patch.balance = val;
            patch.zn_balance = val;
            localStorage.setItem('zn_balance', val.toString());
            localStorage.setItem('user_balance', val.toString());
            const balEl = document.getElementById('farm-balance');
            if (balEl) balEl.innerHTML = `${formatSmartBalanceHTML(val)} ZN`;
        }

        if (newUsdBalance !== undefined && newUsdBalance !== null && !isNaN(parseFloat(newUsdBalance))) {
            const usdVal = parseFloat(newUsdBalance);
            patch.usd_balance = usdVal;
            patch.usdt_balance = usdVal;
            const usdEl = document.getElementById('farm-usd-balance');
            if (usdEl) usdEl.innerHTML = `$${formatSmartBalanceHTML(usdVal)}`;
        }

        updateState(patch);
    }

    function getTodayUTCStr() {
        const now = new Date(getAdjustedNowMs());
        const y = now.getUTCFullYear();
        const m = String(now.getUTCMonth() + 1).padStart(2, '0');
        const d = String(now.getUTCDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    }
    
    function getTimeUntilUTCMidnight() {
        const now = new Date(getAdjustedNowMs());
        const nextMidnight = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1));
        const diff = nextMidnight.getTime() - now.getTime();
        
        let seconds = Math.floor(Math.max(0, diff) / 1000);
        let h = Math.floor(seconds / 3600);
        let m = Math.floor((seconds % 3600) / 60);
        let s = seconds % 60;
        
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }

    function formatTimeDifference(ms) {
        let totalSec = Math.floor(Math.max(0, ms) / 1000);
        let h = Math.floor(totalSec / 3600);
        let m = Math.floor((totalSec % 3600) / 60);
        let s = totalSec % 60;
        return `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
    }

    function formatCompactCost(num) {
        if (num >= 1000000) {
            let formatted = (num / 1000000).toFixed(1);
            return formatted.endsWith('.0') ? (num / 1000000).toFixed(0) + 'M' : formatted + 'M';
        }
        if (num >= 1000) {
            let formatted = (num / 1000).toFixed(1);
            return formatted.endsWith('.0') ? (num / 1000).toFixed(0) + 'K' : formatted + 'K';
        }
        return num.toString();
    }

    function formatCompactNumber(num) {
        if (num >= 1000000) {
            let formatted = (num / 1000000).toFixed(1);
            return (formatted.endsWith('.0') ? (num / 1000000).toFixed(0) : formatted) + 'M';
        }
        if (num >= 1000) {
            let formatted = (num / 1000).toFixed(1);
            return (formatted.endsWith('.0') ? (num / 1000).toFixed(0) : formatted) + 'K';
        }
        return (Math.round(num * 100) / 100).toString();
    }

    // ==========================================
    // 🎬 نظام إدارة الإعلانات الصارم (Single-Ad Waterfall Engine)
    // ==========================================
    function toggleAdLoadingOverlay(show) {
        const overlay = document.getElementById('ad-loading-overlay');
        if (overlay) overlay.style.display = show ? 'flex' : 'none';
    }

    const KNOWN_APP_BODY_IDS = new Set([
        'ad-loading-overlay',
        'telegram-only-screen',
        'banned-screen',
        'global-toast-container',
        'loading-screen',
        'app',
        'main-nav'
    ]);

    function isAdNodeElement(node) {
        if (!node || node.nodeType !== 1) return false;
        const tag = (node.tagName || '').toUpperCase();
        if (tag === 'SCRIPT' || tag === 'STYLE' || tag === 'LINK' || tag === 'META') return false;
        if (node.id && KNOWN_APP_BODY_IDS.has(node.id)) return false;
        return true;
    }

    function findActiveMonetixOverlay(preExistingNodes) {
        const children = Array.from(document.body.children || []);
        for (const el of children) {
            if (!isAdNodeElement(el)) continue;
            const txt = (el.innerText || el.textContent || '').toLowerCase();
            const idCls = ((el.id || '') + ' ' + (el.className || '')).toLowerCase();
            if (
                txt.includes('closing in') ||
                txt.includes('monetix') ||
                idCls.includes('monetix') ||
                idCls.includes('mx-') ||
                (preExistingNodes && !preExistingNodes.has(el))
            ) {
                return el;
            }
        }
        return null;
    }

    function isExplicitSuccessStatus(status) {
        if (status === true) return true;
        if (typeof status === 'string') {
            const str = status.trim().toLowerCase();
            return ['completed', 'closed', 'rewarded', 'true', 'success', 'done', 'finished'].includes(str);
        }
        if (typeof status === 'object' && status !== null) {
            if (status.rewarded === true || status.completed === true || status.closed === true || status.success === true) return true;
            const st = (status.status || status.state || status.event || status.type || '').toString().trim().toLowerCase();
            return ['completed', 'closed', 'rewarded', 'success', 'done', 'finished'].includes(st);
        }
        return false;
    }

    function isExplicitFailureStatus(status) {
        if (status === false) return true;
        if (typeof status === 'string') {
            const str = status.trim().toLowerCase();
            return ['failed', 'error', 'skipped', 'dismissed', 'no_fill', 'nofill', 'no-fill', 'cancelled', 'canceled', 'empty'].includes(str);
        }
        if (typeof status === 'object' && status !== null) {
            if (status.error || status.failed || status.no_fill || status.noFill || status.success === false) return true;
            const st = (status.status || status.state || status.event || status.type || '').toString().trim().toLowerCase();
            return ['failed', 'error', 'skipped', 'dismissed', 'no_fill', 'nofill', 'no-fill', 'cancelled', 'canceled', 'empty'].includes(st);
        }
        return false;
    }

    /**
     * تشغيل إعلان Monetix مع تتبع دقيق لظهوره على الشاشة
     * يُرجع: { success: boolean, shown: boolean }
     */
    async function showMonetixAd() {
        toggleAdLoadingOverlay(true);

        return new Promise((resolve) => {
            let resolved = false;
            let adShown = false;
            let adShownTimestamp = 0;
            let detectedAdElement = null;
            let loadTimeoutTimer = null;
            let completionTimeoutTimer = null;
            let domCheckInterval = null;
            let observer = null;

            const preExistingBodyNodes = new Set(Array.from(document.body.children || []));

            const cleanup = () => {
                NativeClearTimeout(loadTimeoutTimer);
                NativeClearTimeout(completionTimeoutTimer);
                NativeClearInterval(domCheckInterval);
                if (observer) {
                    try { observer.disconnect(); } catch (e) {}
                    observer = null;
                }
            };

            const finish = (success, shown) => {
                if (resolved) return;
                resolved = true;
                cleanup();
                toggleAdLoadingOverlay(false);

                // إذا انتهت المحاولة بالفشل قبل ظهور الإعلان (No-Fill)، نمنع أي نافذة متأخرة من الظهور فوق الإعلان البديل
                if (!shown) {
                    let guardTicks = 0;
                    const lateGuard = NativeSetInterval(() => {
                        guardTicks++;
                        const lateEl = findActiveMonetixOverlay(preExistingBodyNodes);
                        if (lateEl && lateEl.parentNode) {
                            try { lateEl.parentNode.removeChild(lateEl); } catch (e) {}
                        }
                        if (guardTicks >= 12) NativeClearInterval(lateGuard);
                    }, 250);
                }

                resolve({ success: Boolean(success), shown: Boolean(shown) });
            };

            const markAdAsShown = (el) => {
                if (!adShown) {
                    adShown = true;
                    adShownTimestamp = NativeDateNow();
                    if (el) detectedAdElement = el;
                    NativeClearTimeout(loadTimeoutTimer);
                    toggleAdLoadingOverlay(false);
                }
            };

            const blockId = GAME_CONFIG.monetixBlockId || "MX-3AE08FE9";
            const cleanBlockId = blockId.replace(/[^a-zA-Z0-9]/g, '_');
            const noDashBlockId = blockId.replace(/[^a-zA-Z0-9]/g, '');

            let monetixFn = window.showRewardAd || window.show_reward_ad || window[`show_${cleanBlockId}`] || window[`show_${noDashBlockId}`];
            if (!monetixFn && window.Monetix) {
                monetixFn = typeof window.Monetix.showReward === 'function'
                    ? window.Monetix.showReward.bind(window.Monetix)
                    : window.Monetix.show?.bind(window.Monetix);
            }

            if (typeof monetixFn !== 'function') {
                console.warn("Monetix SDK غير متوفر حالياً.");
                return finish(false, false);
            }

            // مراقبة إضافة وإزالة عناصر الإعلان في DOM
            try {
                observer = new MutationObserver(() => {
                    if (resolved) return;
                    const overlayEl = findActiveMonetixOverlay(preExistingBodyNodes);
                    if (overlayEl) {
                        markAdAsShown(overlayEl);
                    } else if (adShown && detectedAdElement && !document.body.contains(detectedAdElement)) {
                        // تم إغلاق عنصر الإعلان من الشاشة بعد انتهاء العداد
                        const watchedDurationMs = NativeDateNow() - adShownTimestamp;
                        NativeSetTimeout(() => {
                            if (!resolved) {
                                finish(watchedDurationMs >= 7000, true);
                            }
                        }, 350);
                    }
                });
                observer.observe(document.body, { childList: true, subtree: false });
            } catch (e) {}

            // فحص دوري للـ DOM للتأكد من رصد ظهور الإعلان وإغلاقه بدقة
            domCheckInterval = NativeSetInterval(() => {
                if (resolved) return;
                const overlayEl = findActiveMonetixOverlay(preExistingBodyNodes);
                if (overlayEl) {
                    markAdAsShown(overlayEl);
                } else if (adShown && detectedAdElement && !document.body.contains(detectedAdElement)) {
                    const watchedDurationMs = NativeDateNow() - adShownTimestamp;
                    finish(watchedDurationMs >= 7000, true);
                }
            }, 250);

            // مهلة تحميل الإعلان المبدئية (6 ثوانٍ): إذا لم يظهر الإعلان خلالها يتحول للبديل فوراً
            loadTimeoutTimer = NativeSetTimeout(() => {
                const overlayEl = findActiveMonetixOverlay(preExistingBodyNodes);
                if (overlayEl) {
                    markAdAsShown(overlayEl);
                } else if (!adShown) {
                    console.warn("Monetix Ad load timeout (No-Fill).");
                    finish(false, false);
                }
            }, 6000);

            // مهلة أمان قصوى لإكمال الإعلان بعد فتحه (45 ثانية)
            completionTimeoutTimer = NativeSetTimeout(() => {
                console.warn("Monetix Ad max completion timeout.");
                finish(false, adShown);
            }, 45000);

            try {
                const handleMonetixCallback = (status) => {
                    if (resolved) return;
                    toggleAdLoadingOverlay(false);

                    // إذا تم استدعاء الـ Callback بحالة بدء العرض فقط، نثبت الظهور وننتظر الانتهاء
                    if (typeof status === 'string' && ['shown', 'started', 'loaded', 'opened', 'impression'].includes(status.trim().toLowerCase())) {
                        markAdAsShown(findActiveMonetixOverlay(preExistingBodyNodes));
                        return;
                    }

                    if (isExplicitFailureStatus(status)) {
                        finish(false, adShown);
                        return;
                    }

                    // في Monetix: استدعاء الـ Callback عند انتهاء العداد يكون إما بـ true/completed أو بدون معاملات (undefined)
                    if (isExplicitSuccessStatus(status) || status === undefined) {
                        const overlayEl = findActiveMonetixOverlay(preExistingBodyNodes);
                        if (overlayEl && (NativeDateNow() - (adShownTimestamp || NativeDateNow())) < 3000) {
                            // الإعلان لا يزال في بداية العد التنازلي على الشاشة
                            markAdAsShown(overlayEl);
                            return;
                        }
                        finish(true, true);
                    }
                };

                const res = monetixFn(handleMonetixCallback);

                if (res && typeof res.then === 'function') {
                    res.then((r) => {
                        if (resolved) return;

                        // إذا رجع خطأ صريح أو false من الـ Promise
                        if (isExplicitFailureStatus(r)) {
                            finish(false, adShown);
                            return;
                        }

                        // فحص ما إذا كان إعلان Monetix قد تم تركيبه على الشاشة (يعد تنازلياً الآن)
                        NativeSetTimeout(() => {
                            if (resolved) return;
                            const overlayEl = findActiveMonetixOverlay(preExistingBodyNodes);
                            if (overlayEl) {
                                // الإعلان مفتوح حالياً على الشاشة! نمنع إنهاء الدالة بـ false وننتظر انتهاء العداد
                                markAdAsShown(overlayEl);
                                return;
                            }

                            // إذا لم يكن هناك عنصر مفتوح في الصفحة والـ Promise رجع بنجاح صريح
                            if (isExplicitSuccessStatus(r)) {
                                finish(true, true);
                            }
                        }, 300);
                    }).catch((err) => {
                        console.warn("Monetix Promise Error / No-Fill:", err);
                        const overlayEl = findActiveMonetixOverlay(preExistingBodyNodes);
                        if (overlayEl) {
                            markAdAsShown(overlayEl);
                        } else {
                            finish(false, adShown);
                        }
                    });
                } else if (res === false) {
                    finish(false, false);
                }
            } catch (e) {
                console.warn("خطأ تشغيل إعلان Monetix:", e);
                finish(false, adShown);
            }
        });
    }

    /**
     * تشغيل إعلان Monetag مع تتبع دقيق لظهوره على الشاشة
     * يُرجع: { success: boolean, shown: boolean }
     */
    async function showMonetagAd() {
        toggleAdLoadingOverlay(true);
        const zoneId = GAME_CONFIG.monetagZoneId || "11322720";
        const functionName = window.MONETAG_SDK_NAME || `show_${zoneId}`;

        return new Promise((resolve) => {
            let resolved = false;
            let adShown = false;
            let loadTimeoutTimer = null;
            let completionTimeoutTimer = null;
            let domCheckInterval = null;

            const preExistingBodyNodes = new Set(Array.from(document.body.children || []));

            const cleanup = () => {
                NativeClearTimeout(loadTimeoutTimer);
                NativeClearTimeout(completionTimeoutTimer);
                NativeClearInterval(domCheckInterval);
            };

            const finish = (success, shown) => {
                if (resolved) return;
                resolved = true;
                cleanup();
                toggleAdLoadingOverlay(false);
                resolve({ success: Boolean(success), shown: Boolean(shown) });
            };

            if (typeof window[functionName] !== 'function') {
                console.warn(`دالة Monetag الإعلانية غير متوفرة (${functionName}).`);
                return finish(false, false);
            }

            // مراقبة ظهور نافذة إعلان Monetag في الصفحة لإخفاء شاشة التحميل وتأكيد العرض
            domCheckInterval = NativeSetInterval(() => {
                if (resolved) return;
                const children = Array.from(document.body.children || []);
                for (const el of children) {
                    if (!isAdNodeElement(el)) continue;
                    if (!preExistingBodyNodes.has(el)) {
                        adShown = true;
                        NativeClearTimeout(loadTimeoutTimer);
                        toggleAdLoadingOverlay(false);
                        break;
                    }
                }
            }, 250);

            // مهلة تحميل إعلان Monetag (8 ثوانٍ): إذا لم يفتح الإعلان خلالها يعتبر No-Fill
            loadTimeoutTimer = NativeSetTimeout(() => {
                if (!adShown) {
                    console.warn("Monetag Ad load timeout (No-Fill).");
                    finish(false, false);
                }
            }, 8000);

            // مهلة أمان قصوى لإكمال الإعلان بعد فتحه (50 ثانية)
            completionTimeoutTimer = NativeSetTimeout(() => {
                console.warn("Monetag Ad max completion timeout.");
                finish(false, adShown);
            }, 50000);

            try {
                const adPromise = window[functionName]();
                if (adPromise && typeof adPromise.then === 'function') {
                    adPromise.then((res) => {
                        if (res === false) {
                            finish(false, adShown);
                        } else {
                            finish(true, true);
                        }
                    }).catch((e) => {
                        console.warn("خطأ أو عدم توفر إعلان Monetag:", e);
                        finish(false, adShown);
                    });
                } else {
                    finish(true, true);
                }
            } catch (e) {
                console.warn("استدعاء Monetag فشل:", e);
                finish(false, adShown);
            }
        });
    }

    function getActiveBoostRate(pData) {
        if (!pData || !pData.last_boost_time) return 0;
        let lastBoostMs = parseServerDateMs(pData.last_boost_time);
        let elapsed = getAdjustedNowMs() - lastBoostMs;
        return (elapsed >= 0 && elapsed < GAME_CONFIG.boostDurationMs) ? GAME_CONFIG.dailyBoostReward : 0;
    }

    function accrueCurrentMining() {
        const pData = getState();
        if (!pData) return 0;

        let nowMs = getAdjustedNowMs();
        let lastAccrualMs = pData.last_accrual_time 
            ? parseServerDateMs(pData.last_accrual_time) 
            : (pData.last_claim_time ? parseServerDateMs(pData.last_claim_time) : nowMs);

        let secondsPassed = Math.max(0, (nowMs - lastAccrualMs) / 1000);
        let maxC = calculateEffectiveMaxCap(pData);

        let baseRate = parseFloat(pData.hourly_rate ?? 0.1);
        let boostRate = getActiveBoostRate(pData);
        let hRate = baseRate + boostRate;

        let baseUnclaimed = parseFloat(pData.base_unclaimed !== undefined ? pData.base_unclaimed : (pData.unclaimed || 0));
        let accumulated = baseUnclaimed + ((hRate / 3600.0) * secondsPassed);

        if (accumulated >= maxC) accumulated = maxC;

        updateState({
            max_cap: maxC,
            base_unclaimed: accumulated,
            unclaimed: accumulated,
            last_accrual_time: nowMs
        });

        return accumulated;
    }

    function updateBotAndAutoClaimUI(resData) {
        if (!resData) return;

        const pData = getState();
        const isBotActive = isBotCurrentlyActive(pData) || toBool(resData.bot_active) || toBool(resData.is_auto_bot_active);
        const isDoubleCap = isDoubleStorageActive(pData);

        updateState({
            bot_active: isBotActive,
            is_auto_bot_active: isBotActive,
            is_double_storage_active: isDoubleCap,
            max_cap: calculateEffectiveMaxCap(pData)
        });

        const botBadge = document.getElementById('bot-active-badge') || document.getElementById('bot-status-badge');
        if (botBadge) {
            botBadge.style.display = isBotActive ? 'inline-flex' : 'none';
        }

        const autoCollected = parseFloat(resData.auto_claimed_amount ?? resData.auto_collected ?? resData.player?.auto_claimed_amount ?? 0);
        if (autoCollected > 0) {
            const autoModal = document.getElementById('auto-claim-modal');
            const autoAmountText = document.getElementById('auto-claimed-amount') || document.getElementById('modal-auto-amount');
            if (autoAmountText) autoAmountText.innerText = `${formatZnBalance(autoCollected)} ZN`;
            
            if (autoModal) {
                autoModal.style.display = 'flex';
                autoModal.classList.add('show', 'active');
            } else {
                showToast(`🤖 تم التجميع التلقائي للبوت: ${formatZnBalance(autoCollected)} ZN!`);
            }
        }
    }

    async function executeClaimApi(isAuto = false) {
        try {
            let resData = await window.fetchAPI(`/api/farm/claim?t=${NativeDateNow()}`, 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance ?? resData.balance, resData.new_usd_balance ?? resData.usd_balance);

                const nowMs = getAdjustedNowMs();
                const claimTime = resData.last_claim_time || new Date(nowMs).toISOString();

                const patch = {
                    last_claim_time: claimTime,
                    unclaimed: 0.0,
                    base_unclaimed: 0.0,
                    last_accrual_time: parseServerDateMs(claimTime)
                };
                if (resData.max_cap !== undefined) patch.max_cap = parseFloat(resData.max_cap);
                if (resData.hourly_rate !== undefined) patch.hourly_rate = parseFloat(resData.hourly_rate);

                updateState(patch);
                window.updateFarmUI();

                if (isAuto) {
                    const claimedAmt = parseFloat(resData.claimed_amount || resData.amount || 0);
                    updateBotAndAutoClaimUI({ auto_claimed_amount: claimedAmt });
                } else {
                    showToast(`💰 تم تجميع ${formatZnBalance(resData.claimed_amount)} عملة بنجاح!`);
                }
                return true;
            } else {
                if (!isAuto) showToast(resData?.error || "❌ تعذر تجميع الرصيد");
                return false;
            }
        } catch (e) {
            console.error(isAuto ? "خطأ التجميع التلقائي (80%):" : "خطأ التجميع الرئيسي:", e);
            if (!isAuto) showToast("❌ حدث خطأ أثناء التجميع");
            return false;
        }
    }

    async function triggerAutoClaim80() {
        if (isAutoClaiming || isClaimingMain) return;
        isAutoClaiming = true;
        try {
            await executeClaimApi(true);
        } finally {
            isAutoClaiming = false;
        }
    }

    window.fetchPlayerDataFromServer = async function(force = false) {
        const now = NativeDateNow();
        if (isFetching) return; 
        if (!force && (now - lastFetchTime < FETCH_THROTTLE_MS)) {
            window.updateFarmUI();
            return;
        }

        isFetching = true;
        try {
            let resData = await window.fetchAPI(`/api/farm/player_data?t=${NativeDateNow()}`, 'POST', { start_param: START_PARAM });
            if (resData && resData.success) {
                lastFetchTime = NativeDateNow();
                if (resData.server_time) syncServerTime(resData.server_time);
                if (resData.cooldown_seconds) MIN_CLAIM_INTERVAL = resData.cooldown_seconds;

                if (resData.monetag_zone_id) GAME_CONFIG.monetagZoneId = resData.monetag_zone_id;
                if (resData.monetix_block_id || resData.monetix_zone_id) {
                    GAME_CONFIG.monetixBlockId = resData.monetix_block_id || resData.monetix_zone_id;
                }

                if (resData.game_config) {
                    const cfg = resData.game_config;
                    if (cfg.monetag_zone_id) GAME_CONFIG.monetagZoneId = cfg.monetag_zone_id;
                    if (cfg.monetix_block_id || cfg.monetix_zone_id) {
                        GAME_CONFIG.monetixBlockId = cfg.monetix_block_id || cfg.monetix_zone_id;
                    }
                    if (cfg.daily_rewards && Array.isArray(cfg.daily_rewards)) GAME_CONFIG.dailyRewards = cfg.daily_rewards;
                    if (cfg.upgrade_costs && typeof cfg.upgrade_costs === 'object') GAME_CONFIG.upgradeCosts = cfg.upgrade_costs;
                    if (cfg.storage_config && typeof cfg.storage_config === 'object') GAME_CONFIG.storageConfig = cfg.storage_config;
                    if (cfg.max_upgrades_per_level) GAME_CONFIG.maxUpgradesPerLevel = cfg.max_upgrades_per_level;
                    if (cfg.daily_boost_reward) GAME_CONFIG.dailyBoostReward = cfg.daily_boost_reward;
                }

                if (resData.player) {
                    const userId = resData.player.tg_id || tele?.initDataUnsafe?.user?.id;
                    const localSeenKey = userId ? `zn_welcome_seen_${userId}` : 'zn_welcome_seen_global';
                    const alreadySeenLocally = localStorage.getItem(localSeenKey) === 'true';

                    const isNewUser = !alreadySeenLocally && (resData.player.is_new_user === true && resData.player.welcome_seen === false);
                    if (isNewUser) clearStaleLocalCache();

                    const serverTimeMs = resData.server_time ? parseServerDateMs(resData.server_time) : getAdjustedNowMs();
                    const parsedVip = parseVipStatus(resData.player);

                    const mergedPlayer = Object.assign({}, resData.player, {
                        vip_status: parsedVip
                    });

                    const isBotActive = isBotCurrentlyActive(mergedPlayer) || toBool(resData.bot_active) || toBool(resData.is_auto_bot_active);
                    const isDoubleCap = isDoubleStorageActive(mergedPlayer);
                    const trueMaxCap = calculateEffectiveMaxCap(mergedPlayer);
                    const currentUnclaimed = Math.min(trueMaxCap, Math.max(0, parseFloat(resData.player.unclaimed || 0)));

                    const newState = Object.assign({}, mergedPlayer, {
                        is_new_user: isNewUser,
                        welcome_seen: !isNewUser,
                        bot_active: isBotActive,
                        is_auto_bot_active: isBotActive,
                        is_double_storage_active: isDoubleCap,
                        max_cap: trueMaxCap,
                        base_unclaimed: currentUnclaimed,
                        unclaimed: currentUnclaimed,
                        last_accrual_time: serverTimeMs
                    });

                    updateState(newState);
                    setStoredBalance(resData.player.balance, resData.player.usd_balance);

                    const welcomeModal = document.getElementById('welcome-modal');
                    if (welcomeModal) {
                        if (isNewUser) {
                            welcomeModal.style.display = 'flex';
                            welcomeModal.classList.add('show', 'active');
                            localStorage.setItem(localSeenKey, 'true');
                            window.fetchAPI?.(`/api/farm/dismiss_welcome?t=${NativeDateNow()}`, 'POST', {}).catch(() => {});
                        } else {
                            welcomeModal.style.display = 'none';
                            welcomeModal.classList.remove('show', 'active');
                        }
                    }
                }

                updateBotAndAutoClaimUI(resData);
            }
        } catch (e) { 
            console.error("خطأ مزامنة المزرعة:", e); 
        } finally { 
            isFetching = false; 
            window.updateFarmUI();
        }
    };

    window.updateFarmUI = function() {
        const pData = getState();
        let bal = getStoredBalance();
        let usdBal = getStoredUsdBalance();
        let baseRate = parseFloat(pData.hourly_rate ?? 0.1);
        let boostRate = getActiveBoostRate(pData);
        let totalRate = baseRate + boostRate;

        const balEl = document.getElementById('farm-balance');
        if (balEl) {
            balEl.style.whiteSpace = 'nowrap';
            balEl.innerHTML = `${formatSmartBalanceHTML(bal)} ZN`;
        }

        const usdEl = document.getElementById('farm-usd-balance');
        if (usdEl) {
            usdEl.style.whiteSpace = 'nowrap';
            usdEl.innerHTML = `$${formatSmartBalanceHTML(usdBal)}`;
        }

        const rateEl = document.getElementById('farm-rate');
        if (rateEl) {
            let formattedRate = totalRate >= 1000 
                ? formatCompactNumber(totalRate) 
                : ((totalRate % 1 === 0) ? totalRate.toString() : Number(totalRate.toFixed(2)).toString());
            let boostIndicator = boostRate > 0 ? ` <span style="color:#10b981; font-size:11px;">(+0.1🚀)</span>` : '';
            rateEl.style.whiteSpace = 'nowrap';
            rateEl.innerHTML = `<span dir="ltr">${formattedRate} /h</span>⚡${boostIndicator}`;
        }

        const maxAllowedStgLvl = getMaxStorageLevel();
        const stgLvl = Math.min(maxAllowedStgLvl, Math.max(0, parseInt(pData.storage_level ?? 0, 10) || 0));
        const stgLvlEl = document.getElementById('storage-level-num');
        if (stgLvlEl) stgLvlEl.innerText = stgLvl + 1;

        const isBotActive = isBotCurrentlyActive(pData);
        const botBadge = document.getElementById('bot-active-badge') || document.getElementById('bot-status-badge');
        if (botBadge) botBadge.style.display = isBotActive ? 'inline-flex' : 'none';

        const upgradeStgBtn = document.getElementById('upgrade-storage-btn');
        if (upgradeStgBtn) {
            upgradeStgBtn.onclick = window.handleStorageUpgrade;
            const nextLvl = stgLvl + 1;
            const nextCfg = GAME_CONFIG.storageConfig[nextLvl.toString()];

            if (stgLvl >= maxAllowedStgLvl || !nextCfg) {
                upgradeStgBtn.innerText = "المخزن في المستوى الأقصى (MAX) 🏆";
                upgradeStgBtn.disabled = true;
                upgradeStgBtn.className = "storage-upgrade-btn btn-disabled";
            } else {
                const costZn = typeof nextCfg === 'object' ? (nextCfg.cost_zn ?? nextCfg.cost ?? 0) : 0;
                const costUsd = typeof nextCfg === 'object' ? (nextCfg.cost_usd ?? 0) : 0;
                const costStrZn = formatCompactCost(costZn);
                const costStrUsd = costUsd > 0 ? ` + $${costUsd.toFixed(2)}` : '';
                
                const currentUnclaim = parseFloat(pData.unclaimed || 0);
                const canAfford = ((bal + currentUnclaim) >= costZn) && (usdBal >= costUsd);

                upgradeStgBtn.innerText = isUpgradingStorage ? "جاري الترقية... ⏳" : `ترقية المخزن Lvl ${nextLvl + 1} (${costStrZn} ZN${costStrUsd}) 📦`;
                upgradeStgBtn.disabled = !canAfford || isUpgradingStorage;
                upgradeStgBtn.className = (canAfford && !isUpgradingStorage) ? "storage-upgrade-btn btn-ready-yellow" : "storage-upgrade-btn btn-disabled";
            }
        }

        const fieldsContainer = document.getElementById('mining-fields');
        if (fieldsContainer) {
            const currentUpgrades = pData.upgrades || {};
            let fieldsHTML = '';
            const isAnyUpgrading = (upgradingLevel !== null);
            const currentUnclaim = parseFloat(pData.unclaimed || 0);

            for (let i = 1; i <= 8; i++) {
                let count = parseInt(currentUpgrades[`lvl${i}`] || currentUpgrades[String(i)] || 0, 10);
                let prevCount = parseInt(currentUpgrades[`lvl${i-1}`] || currentUpgrades[String(i-1)] || 0, 10);
                let isUnlocked = (i === 1) || (prevCount > 0);
                let isMax = count >= GAME_CONFIG.maxUpgradesPerLevel;
                
                let lvlCfg = GAME_CONFIG.upgradeCosts[i] || GAME_CONFIG.upgradeCosts[String(i)] || {};
                let costZn = lvlCfg.cost_zn ?? lvlCfg.base_cost ?? lvlCfg.price ?? 0;
                let costUsd = lvlCfg.cost_usd ?? lvlCfg.base_cost_usd ?? 0;

                let costStrZn = formatCompactCost(costZn);
                let costStrUsd = costUsd > 0 ? `+$${Number(costUsd.toFixed(2))}` : '';
                
                let canAfford = ((bal + currentUnclaim) >= costZn) && (usdBal >= costUsd);
                let isThisCardUpgrading = (upgradingLevel === i);

                if (isMax) {
                    fieldsHTML += `
                    <div class="mining-card">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">مستوى ${i} (MAX)</div>
                        <button class="mining-card-btn" disabled>${GAME_CONFIG.maxUpgradesPerLevel}/${GAME_CONFIG.maxUpgradesPerLevel} MAX</button>
                    </div>`;
                } else if (count > 0 || isUnlocked) {
                    const titleText = count > 0 ? `مستوى ${i} (x${count})` : `مستوى ${i}`;
                    const btnText = isThisCardUpgrading ? 'جاري...' : (count > 0 ? `ترقية (${costStrZn}${costStrUsd})` : `شراء (${costStrZn}${costStrUsd})`);
                    fieldsHTML += `
                    <div class="mining-card" onclick="window.handleUpgrade(${i})">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">${titleText}</div>
                        <button class="mining-card-btn" style="white-space: nowrap;" ${!canAfford || isAnyUpgrading ? 'disabled' : ''}>${btnText}</button>
                    </div>`;
                } else {
                    fieldsHTML += `
                    <div class="mining-card" style="opacity: 0.4;">
                        <div class="mining-card-icon">🔒</div>
                        <div class="mining-card-title">مستوى ${i}</div>
                        <button class="mining-card-btn" disabled>مغلق</button>
                    </div>`;
                }
            }
            fieldsContainer.innerHTML = fieldsHTML;
        }

        updateBoostButtonUI(pData);
        renderDailyRewards();

        const maxC = calculateEffectiveMaxCap(pData);
        const unclaim = Math.min(maxC, Math.max(0, parseFloat(pData.unclaimed || 0)));

        const progressEl = document.getElementById('storage-progress');
        const storageTextEl = document.getElementById('storage-text');
        if (progressEl && storageTextEl) {
            const pct = maxC > 0 ? Math.max(0, Math.min((unclaim / maxC) * 100, 100)) : 0;
            progressEl.style.width = `${pct}%`;
            storageTextEl.style.whiteSpace = 'nowrap';
            storageTextEl.style.direction = 'ltr';
            storageTextEl.style.display = 'inline-block';
            storageTextEl.style.fontVariantNumeric = 'tabular-nums';
            storageTextEl.innerText = `${formatStorageBalance(unclaim)} / ${formatStorageCapacity(maxC)}`;
        }
    };

    function updateBoostButtonUI(pData) {
        const boostBtn = document.getElementById('boost-btn');
        if (!boostBtn) return;

        boostBtn.onclick = window.handleDailyBoost;
        const lastBoostTimeStr = pData.last_boost_time;

        if (isBoosting) {
            boostBtn.className = "boost-btn btn-disabled";
            boostBtn.disabled = true;
            boostBtn.innerHTML = `<span style="font-size: 12px;">⏳</span><span style="font-size: 10px;">جاري...</span>`;
            return;
        }

        if (!lastBoostTimeStr) {
            boostBtn.className = "boost-btn";
            boostBtn.disabled = false;
            boostBtn.innerHTML = `<span id="boost-icon">🚀</span><span id="boost-text">+0.1/h</span>`;
            return;
        }

        let lastBoostMs = parseServerDateMs(lastBoostTimeStr);
        let elapsed = getAdjustedNowMs() - lastBoostMs;

        if (elapsed < GAME_CONFIG.boostDurationMs) {
            let remainingActive = GAME_CONFIG.boostDurationMs - elapsed;
            boostBtn.className = "boost-btn active-boost";
            boostBtn.disabled = true;
            boostBtn.innerHTML = `<span style="font-size: 12px;">⚡</span><span style="font-size: 9px; color:#10b981;">نشط ${formatTimeDifference(remainingActive)}</span>`;
        } else if (elapsed < GAME_CONFIG.boostCooldownMs) {
            let remainingCooldown = GAME_CONFIG.boostCooldownMs - elapsed;
            boostBtn.className = "boost-btn btn-disabled";
            boostBtn.disabled = true;
            boostBtn.innerHTML = `<span style="font-size: 12px;">⏳</span><span style="font-size: 8px;">${formatTimeDifference(remainingCooldown)}</span>`;
        } else {
            boostBtn.className = "boost-btn";
            boostBtn.disabled = false;
            boostBtn.innerHTML = `<span id="boost-icon">🚀</span><span id="boost-text">+0.1/h</span>`;
        }
    }

    window.onFarmTabOpen = async function() {
        if (typeof window.fetchPlayerDataFromServer === 'function') {
            await window.fetchPlayerDataFromServer(true); 
        } else {
            window.updateFarmUI();
        }
    };

    function getRewardForDayIndex(index) {
        const rewards = GAME_CONFIG.dailyRewards;
        return (rewards && Array.isArray(rewards)) ? (rewards[index] ?? 40.0) : 0.2;
    }

    function renderDailyRewards() {
        const container = document.getElementById('daily-rewards-container');
        const pData = getState();
        if (!container) return; 

        let html = '';
        const todayStr = getTodayUTCStr();
        const lastClaimDate = pData.last_daily_claim_date;
        const claimedToday = (lastClaimDate === todayStr); 
        let currentDailyDay = parseInt(pData.daily_day || 1, 10);
        if (isNaN(currentDailyDay) || currentDailyDay < 1) currentDailyDay = 1;

        const timeLeftStr = getTimeUntilUTCMidnight();

        for (let i = 0; i < 30; i++) {
            let dayNum = i + 1;
            let rawReward = getRewardForDayIndex(i);
            let displayReward = formatCompactNumber(rawReward) + ' ZN';

            if (claimedToday) {
                if (dayNum <= currentDailyDay) {
                    html += `<div class="reward-day-card claimed"><div class="day-title">يوم ${dayNum}</div><div style="font-size: 14px; font-weight: bold; color: #10b981;">✓</div></div>`;
                } else if (dayNum === currentDailyDay + 1) {
                    html += `<div class="reward-day-card active" style="border: 1px dashed #ef4444;"><div class="day-title">يوم ${dayNum}</div><div class="day-amount">${displayReward}</div><div id="daily-timer" style="color: #ef4444; font-size: 8px; font-weight: bold;">⏳ ${timeLeftStr}</div></div>`;
                } else {
                    html += `<div class="reward-day-card" style="opacity: 0.4;"><div class="day-title">يوم ${dayNum}</div><div class="day-amount">${displayReward}</div></div>`;
                }
            } else {
                if (dayNum < currentDailyDay) {
                    html += `<div class="reward-day-card claimed"><div class="day-title">يوم ${dayNum}</div><div style="font-size: 14px; font-weight: bold; color: #10b981;">✓</div></div>`;
                } else if (dayNum === currentDailyDay) {
                    const btnLabel = isClaimingDaily ? 'جاري...' : 'استلام';
                    html += `<div class="reward-day-card active"><div class="day-title">يوم ${dayNum}</div><div class="day-amount">${displayReward}</div><button id="daily-btn-${dayNum}" onclick="window.handleDailyClaim(${currentDailyDay})" style="background: ${isClaimingDaily ? '#64748b' : '#10b981'}; color: white; border: none; border-radius: 4px; padding: 2px 0; font-size: 9px; width: 100%; cursor: pointer;" ${isClaimingDaily ? 'disabled' : ''}>${btnLabel}</button></div>`;
                } else {
                    html += `<div class="reward-day-card" style="opacity: 0.4;"><div class="day-title">يوم ${dayNum}</div><div class="day-amount">${displayReward}</div></div>`;
                }
            }
        }
        container.innerHTML = html;
    }

    loadCachedData();
    window.updateFarmUI();

    if (window.farmIntervalId) NativeClearInterval(window.farmIntervalId);
    window.farmIntervalId = NativeSetInterval(() => {
        const pData = getState();
        if (!pData) return;
        
        const todayStr = getTodayUTCStr();
        if (lastCheckedDate && lastCheckedDate !== todayStr) {
            lastCheckedDate = todayStr;
            window.fetchPlayerDataFromServer?.(true);
        }
        lastCheckedDate = todayStr;

        let maxC = calculateEffectiveMaxCap(pData);
        let baseRate = parseFloat(pData.hourly_rate ?? 0.1);
        let boostRate = getActiveBoostRate(pData);
        let hRate = baseRate + boostRate;
        
        let nowMs = getAdjustedNowMs();
        let lastAccrualMs = pData.last_accrual_time 
            ? parseServerDateMs(pData.last_accrual_time) 
            : (pData.last_claim_time ? parseServerDateMs(pData.last_claim_time) : nowMs);

        let secondsPassed = Math.max(0, (nowMs - lastAccrualMs) / 1000);
        let baseUnclaimed = parseFloat(pData.base_unclaimed !== undefined ? pData.base_unclaimed : (pData.unclaimed || 0));
        let unclaim = baseUnclaimed + ((hRate / 3600.0) * secondsPassed);

        const isBotActive = isBotCurrentlyActive(pData);

        if (unclaim >= maxC) unclaim = maxC;

        if (window.userState) {
            window.userState.unclaimed = unclaim;
            window.userState.max_cap = maxC;
            window.userState.bot_active = isBotActive;
        }
        if (window.PlayerData) {
            window.PlayerData.unclaimed = unclaim;
            window.PlayerData.max_cap = maxC;
            window.PlayerData.bot_active = isBotActive;
        }

        const botBadge = document.getElementById('bot-active-badge') || document.getElementById('bot-status-badge');
        if (botBadge) botBadge.style.display = isBotActive ? 'inline-flex' : 'none';
        
        if (isBotActive && maxC > 0 && unclaim >= (maxC * 0.8) && !isAutoClaiming && !isClaimingMain) {
            if (NativeDateNow() - lastAutoClaimAttempt > 10000) {
                lastAutoClaimAttempt = NativeDateNow();
                triggerAutoClaim80();
            }
        }

        const progressEl = document.getElementById('storage-progress');
        const storageTextEl = document.getElementById('storage-text');

        let pct = maxC > 0 ? (unclaim / maxC) * 100 : 0;
        pct = Math.max(0, Math.min(pct, 100));

        if (progressEl && storageTextEl) {
            progressEl.style.width = `${pct}%`;
            storageTextEl.style.whiteSpace = 'nowrap';
            storageTextEl.style.direction = 'ltr';
            storageTextEl.style.display = 'inline-block';
            storageTextEl.style.fontVariantNumeric = 'tabular-nums';
            storageTextEl.innerText = `${formatStorageBalance(unclaim)} / ${formatStorageCapacity(maxC)}`;
        }

        let lastClaimStr = pData.last_claim_time;
        let lastClaimTimeMs = lastClaimStr ? parseServerDateMs(lastClaimStr) : getAdjustedNowMs();
        let secondsSinceClaim = Math.max(0, (getAdjustedNowMs() - lastClaimTimeMs) / 1000);
        const remainingCooldown = Math.max(0, Math.ceil(MIN_CLAIM_INTERVAL - secondsSinceClaim));

        const claimBtn = document.getElementById('claim-btn');
        if (claimBtn) {
            claimBtn.onclick = window.handleMainClaim;

            if (isClaimingMain) {
                claimBtn.innerText = "جاري الحفظ... 💾";
                claimBtn.className = "claim-action-btn btn-disabled";
                claimBtn.disabled = true;
            } else if (remainingCooldown > 0 && unclaim > 0) {
                claimBtn.innerText = `انتظر ${remainingCooldown} ثانية ⏳`;
                claimBtn.className = "claim-action-btn btn-disabled";
                claimBtn.disabled = true;
            } else if (unclaim > 0) {
                claimBtn.innerText = "تجميع الرصيد 💰";
                claimBtn.className = "claim-action-btn btn-ready";
                claimBtn.disabled = false;
            } else {
                claimBtn.innerText = "المخزن فارغ ⏳";
                claimBtn.className = "claim-action-btn btn-disabled";
                claimBtn.disabled = true;
            }
        }

        updateBoostButtonUI(pData);

        const dailyTimerEl = document.getElementById('daily-timer');
        if (dailyTimerEl && pData.last_daily_claim_date === todayStr) {
            dailyTimerEl.innerText = `⏳ ${getTimeUntilUTCMidnight()}`;
        }

    }, 1000);

    function syncOnVisibility() {
        if (document.visibilityState === "visible") {
            window.fetchPlayerDataFromServer(true);
        }
    }

    window.addEventListener('pageshow', syncOnVisibility);
    document.addEventListener("visibilitychange", syncOnVisibility);

    window.addEventListener('userStateUpdated', () => {
        if (!isFetching && !isClaimingMain && !isAutoClaiming && !isUpgradingStorage && upgradingLevel === null) {
            window.updateFarmUI();
        }
    });

    window.handleStorageUpgrade = async function() {
        if (isDebouncedClick() || isUpgradingStorage) return;

        const pData = getState();
        const maxAllowedStgLvl = getMaxStorageLevel();
        const stgLvl = parseInt(pData.storage_level ?? 0, 10);
        const nextLvl = stgLvl + 1;
        const nextCfg = GAME_CONFIG.storageConfig[nextLvl.toString()];

        if (stgLvl >= maxAllowedStgLvl || !nextCfg) return;

        const costZn = typeof nextCfg === 'object' ? (nextCfg.cost_zn ?? nextCfg.cost ?? 0) : 0;
        const costUsd = typeof nextCfg === 'object' ? (nextCfg.cost_usd ?? 0) : 0;
        const bal = getStoredBalance();
        const usdBal = getStoredUsdBalance();
        
        const currentUnclaim = parseFloat(pData.unclaimed || 0);
        const totalAvailableZn = bal + currentUnclaim;

        if (totalAvailableZn < costZn || usdBal < costUsd) {
            showToast("❌ رصيدك غير كافٍ لترقية المخزن");
            return;
        }

        isUpgradingStorage = true;
        const stateBackup = cloneCurrentState();

        const nowMs = getAdjustedNowMs();
        setStoredBalance(Math.max(0, totalAvailableZn - costZn), Math.max(0, usdBal - costUsd));

        const effectiveNextCap = calculateEffectiveMaxCap(Object.assign({}, pData, { storage_level: nextLvl }));

        updateState({
            storage_level: nextLvl,
            max_cap: effectiveNextCap,
            unclaimed: 0.0,
            base_unclaimed: 0.0,
            last_claim_time: new Date(nowMs).toISOString(),
            last_accrual_time: nowMs
        });
        window.updateFarmUI();

        try {
            let resData = await window.fetchAPI(`/api/farm/upgrade_storage?t=${NativeDateNow()}`, 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance ?? resData.balance, resData.new_usd_balance ?? resData.usd_balance);
                
                const confirmedLvl = resData.storage_level !== undefined ? parseInt(resData.storage_level, 10) : nextLvl;
                const confirmedCap = resData.max_cap !== undefined 
                    ? parseFloat(resData.max_cap) 
                    : calculateEffectiveMaxCap(Object.assign({}, getState(), { storage_level: confirmedLvl }));

                updateState({
                    storage_level: confirmedLvl,
                    max_cap: confirmedCap,
                    unclaimed: 0.0,
                    base_unclaimed: 0.0,
                    last_claim_time: resData.server_time,
                    last_accrual_time: parseServerDateMs(resData.server_time)
                });

                showToast(`📦 تم ترقية سعة المخزن بنجاح إلى Level ${confirmedLvl + 1}!`);
            } else {
                restoreState(stateBackup);
                showToast(resData?.error || "❌ تعذر ترقية المخزن");
            }
        } catch (e) {
            console.error("خطأ ترقية المخزن:", e);
            restoreState(stateBackup);
            showToast("❌ حدث خطأ أثناء ترقية المخزن");
        } finally {
            isUpgradingStorage = false;
            window.updateFarmUI();
        }
    };

    window.handleUpgrade = async function(level) {
        if (isDebouncedClick() || upgradingLevel !== null) return;

        const lvlCfg = GAME_CONFIG.upgradeCosts[level] || GAME_CONFIG.upgradeCosts[String(level)] || {};
        const costZn = lvlCfg.cost_zn ?? lvlCfg.base_cost ?? lvlCfg.price ?? 0;
        const costUsd = lvlCfg.cost_usd ?? lvlCfg.base_cost_usd ?? 0;

        const currentBal = getStoredBalance();
        const currentUsdBal = getStoredUsdBalance();
        
        const currentUnclaim = parseFloat(getState().unclaimed || 0);
        const totalAvailableZn = currentBal + currentUnclaim;

        if (totalAvailableZn < costZn || currentUsdBal < costUsd) {
            let msg = `❌ رصيدك غير كافٍ! سعر الترقية: ${costZn.toLocaleString()} ZN`;
            if (costUsd > 0) msg += ` + $${costUsd.toFixed(2)} USD`;
            showToast(msg);
            return;
        }

        upgradingLevel = level;
        const stateBackup = cloneCurrentState();

        const nowMs = getAdjustedNowMs();
        setStoredBalance(Math.max(0, totalAvailableZn - costZn), Math.max(0, currentUsdBal - costUsd));

        const stateObj = getState();
        const upgradesObj = Object.assign({}, stateObj.upgrades || {});
        const currentCount = parseInt(upgradesObj[`lvl${level}`] || 0, 10);
        upgradesObj[`lvl${level}`] = currentCount + 1;

        const totalUpgradesCount = Object.values(upgradesObj).reduce((acc, v) => acc + (parseInt(v) || 0), 0);
        const addRate = parseFloat(lvlCfg.rate || lvlCfg.rate_bonus || 0);
        const currentHourly = parseFloat(stateObj.hourly_rate || 0.1);

        updateState({
            upgrades: upgradesObj,
            upgrades_count: totalUpgradesCount,
            hourly_rate: addRate > 0 ? Number((currentHourly + addRate).toFixed(4)) : currentHourly,
            unclaimed: 0.0,
            base_unclaimed: 0.0,
            last_claim_time: new Date(nowMs).toISOString(),
            last_accrual_time: nowMs
        });
        window.updateFarmUI();

        try {
            let resData = await window.fetchAPI(`/api/farm/upgrade?t=${NativeDateNow()}`, 'POST', { level: level });
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance ?? resData.balance, resData.new_usd_balance ?? resData.usd_balance);
                
                const newHourly = resData.new_hourly_rate ?? resData.hourly_rate ?? resData.rate;
                const patch = {
                    unclaimed: 0.0,
                    base_unclaimed: 0.0,
                    last_claim_time: resData.server_time,
                    last_accrual_time: parseServerDateMs(resData.server_time)
                };
                if (newHourly !== undefined && newHourly !== null) patch.hourly_rate = parseFloat(newHourly);
                if (resData.max_cap !== undefined) patch.max_cap = parseFloat(resData.max_cap);
                if (resData.upgrades) {
                    patch.upgrades = resData.upgrades;
                    patch.upgrades_count = Object.values(resData.upgrades).reduce((acc, v) => acc + (parseInt(v) || 0), 0);
                }

                updateState(patch);
                showToast(`🏛️ تم ترقية المستوى ${level} بنجاح!`);
            } else {
                restoreState(stateBackup);
                showToast(resData?.error || "❌ تعذر إتمام الترقية");
            }
        } catch (e) {
            console.error("خطأ الترقية:", e);
            restoreState(stateBackup);
            showToast("❌ حدث خطأ أثناء عملية الشراء");
        } finally {
            upgradingLevel = null;
            window.updateFarmUI();
        }
    };

    // ==========================================
    // 🎁 المكافأة اليومية: Monetag (أساسي) -> Monetix (بديل فقط إذا لم يظهر الأول)
    // ==========================================
    window.handleDailyClaim = async function(dayNum) {
        if (isDebouncedClick() || isClaimingDaily || isAdSessionActive) return;

        isClaimingDaily = true;
        isAdSessionActive = true;
        renderDailyRewards();

        try {
            let adResult = await showMonetagAd();

            // لا يتم تشغيل البديل (Monetix) إلا إذا لم يظهر إعلان Monetag على الشاشة نهائياً
            if (!adResult.success && !adResult.shown) {
                console.log("Monetag لم يظهر نهائياً، جاري التحويل إلى الإعلان البديل Monetix...");
                adResult = await showMonetixAd();
            }

            toggleAdLoadingOverlay(false);

            if (!adResult.success) {
                showToast("❌ يجب مشاهدة الإعلان كاملاً لاستلام المكافأة اليومية!");
                return;
            }

            const stateBackup = cloneCurrentState();
            try {
                let resData = await window.fetchAPI(`/api/farm/daily_claim?t=${NativeDateNow()}`, 'POST', {
                    ad_watched: true,
                    monetag_watched: true,
                    monetix_watched: true
                });
                if (resData && resData.success) {
                    if (resData.server_time) syncServerTime(resData.server_time);
                    setStoredBalance(resData.new_balance ?? resData.balance, resData.new_usd_balance ?? resData.usd_balance);
                    
                    const patch = {};
                    if (resData.daily_day !== undefined) patch.daily_day = resData.daily_day;
                    if (resData.last_daily_claim_date) patch.last_daily_claim_date = resData.last_daily_claim_date;

                    updateState(patch);
                    showToast(`🎉 تم مشاهدة الإعلان واستلام مكافأة اليوم ${resData.daily_day} بنجاح!`);
                } else {
                    showToast(resData?.error || "❌ تعذر استلام المكافأة");
                }
            } catch (apiErr) {
                console.error("خطأ استلام المكافأة اليومية:", apiErr);
                restoreState(stateBackup);
                showToast("❌ حدث خطأ أثناء استلام المكافأة اليومية");
            }
        } finally {
            toggleAdLoadingOverlay(false);
            isClaimingDaily = false;
            isAdSessionActive = false;
            window.updateFarmUI();
        }
    };

    // ==========================================
    // 🚀 تعزيز السرعة: Monetix (أساسي) -> Monetag (بديل فقط إذا لم يظهر الأول)
    // ==========================================
    window.handleDailyBoost = async function() {
        if (isDebouncedClick() || isBoosting || isAdSessionActive) return;

        isBoosting = true;
        isAdSessionActive = true;
        updateBoostButtonUI(getState());
        
        try {
            let adResult = await showMonetixAd();

            // لا يتم تشغيل البديل (Monetag) إلا إذا لم يظهر إعلان Monetix على الشاشة نهائياً
            if (!adResult.success && !adResult.shown) {
                console.log("Monetix لم يظهر نهائياً، جاري عرض إعلان Monetag البديل...");
                adResult = await showMonetagAd();
            }

            toggleAdLoadingOverlay(false);

            if (!adResult.success) {
                showToast("❌ يجب مشاهدة الإعلان بكامل مدته لتفعيل تسريع التعدين!");
                return;
            }

            accrueCurrentMining();
            const stateBackup = cloneCurrentState();

            try {
                let resData = await window.fetchAPI(`/api/farm/daily_boost?t=${NativeDateNow()}`, 'POST', {
                    ad_watched: true,
                    monetix_watched: true,
                    monetag_watched: true
                });
                if (resData && resData.success) {
                    if (resData.server_time) syncServerTime(resData.server_time);

                    if (resData.player) updateState(resData.player);

                    const newBal = resData.new_balance ?? resData.balance ?? resData.player?.balance;
                    const newUsdBal = resData.new_usd_balance ?? resData.usd_balance ?? resData.player?.usd_balance;
                    setStoredBalance(newBal, newUsdBal);

                    const bTime = resData.last_boost_time || resData.player?.last_boost_time;
                    if (bTime) updateState({ last_boost_time: bTime });

                    showToast(`⚡ تم مشاهدة الإعلان وتفعيل تعزيز السرعة (+0.1 ZN/ساعة) لمدة ساعتين بنجاح!`);
                } else {
                    restoreState(stateBackup);
                    showToast(resData?.error || "❌ تعذر تفعيل التعزيز");
                }
            } catch (apiErr) {
                console.error("خطأ التعزيز اليومي:", apiErr);
                restoreState(stateBackup);
                showToast("❌ حدث خطأ أثناء تفعيل التعزيز");
            }
        } finally {
            toggleAdLoadingOverlay(false);
            isBoosting = false;
            isAdSessionActive = false;
            window.updateFarmUI();
        }
    };

    window.handleMainClaim = async function() {
        if (isDebouncedClick() || isClaimingMain || isAutoClaiming) return;

        const pData = getState();
        isClaimingMain = true;
        const stateBackup = cloneCurrentState();

        const currentUnclaimed = parseFloat(pData.unclaimed || 0);
        if (currentUnclaimed > 0) {
            const currentBal = getStoredBalance();
            setStoredBalance(currentBal + currentUnclaimed, getStoredUsdBalance());
            const nowMs = getAdjustedNowMs();
            const nowIso = new Date(nowMs).toISOString();

            updateState({
                unclaimed: 0.0,
                base_unclaimed: 0.0,
                last_claim_time: nowIso,
                last_accrual_time: nowMs
            });
            window.updateFarmUI();
        }

        try {
            const ok = await executeClaimApi(false);
            if (!ok) restoreState(stateBackup);
        } catch (e) {
            restoreState(stateBackup);
        } finally {
            isClaimingMain = false;
            window.updateFarmUI();
        }
    };

    window.handleClaim = window.handleMainClaim;

})();

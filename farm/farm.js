/**
 * ZN Farm Logic - Encapsulated & Secured Module (Fixed Accrual & Retroactive Jumps)
 * Cleaned, Optimized & Modularized Version
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
// 2. النطاق المحمي الخاص بالمزرعة (Module)
// ==========================================
(function initFarmModule() {
    'use strict';

    const tele = window.Telegram?.WebApp;
    const urlParams = new URLSearchParams(window.location.search);
    const START_PARAM = tele?.initDataUnsafe?.start_param || urlParams.get('start_param') || sessionStorage.getItem('zn_start_param') || "";
    if (START_PARAM) {
        try { sessionStorage.setItem('zn_start_param', START_PARAM); } catch (e) {}
    }

    // إعدادات اللعبة
    const GAME_CONFIG = {
        monetagZoneId: window.MONETAG_ZONE_ID || "11322720",
        monetixBlockId: window.MONETIX_BLOCK_ID || "MX-3AE08FE9",
        maxUpgradesPerLevel: 15,
        dailyBoostReward: 0.10,
        boostDurationMs: 2 * 60 * 60 * 1000, 
        boostCooldownMs: 3 * 60 * 60 * 1000, 
        upgradeCosts: {
            1: { cost_zn: 0, cost_usd: 0.0, rate: 0.1 },
            2: { cost_zn: 100, cost_usd: 0.0, rate: 0.2 },
            3: { cost_zn: 400, cost_usd: 0.25, rate: 0.5 },
            4: { cost_zn: 1500, cost_usd: 0.60, rate: 1.2 },
            5: { cost_zn: 5000, cost_usd: 1.25, rate: 2.8 },
            6: { cost_zn: 15000, cost_usd: 3.00, rate: 6.0 },
            7: { cost_zn: 40000, cost_usd: 6.00, rate: 14.0 },
            8: { cost_zn: 100000, cost_usd: 12.00, rate: 30.0 }
        },
        storageConfig: {
            "0": { capacity: 0.5, cost_zn: 0, cost_usd: 0.0 },
            "1": { capacity: 1.5, cost_zn: 50, cost_usd: 0.0 },
            "2": { capacity: 4.0, cost_zn: 200, cost_usd: 0.20 },
            "3": { capacity: 10.0, cost_zn: 800, cost_usd: 0.50 },
            "4": { capacity: 25.0, cost_zn: 2500, cost_usd: 1.00 },
            "5": { capacity: 60.0, cost_zn: 7000, cost_usd: 2.50 },
            "6": { capacity: 150.0, cost_zn: 20000, cost_usd: 5.00 },
            "7": { capacity: 400.0, cost_zn: 50000, cost_usd: 10.00 },
            "8": { capacity: 1000.0, cost_zn: 120000, cost_usd: 20.00 }
        },
        dailyRewards: [
            0.2, 0.4, 0.6, 0.8, 1.0,     
            1.2, 1.5, 1.8, 2.0, 2.5,     
            3.0, 3.5, 4.0, 4.5, 5.0,     
            6.0, 7.0, 8.0, 9.0, 10.0,    
            12.0, 14.0, 16.0, 18.0, 20.0,  
            22.0, 25.0, 30.0, 35.0, 40.0   
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

    let lastFetchTime = 0;
    const FETCH_THROTTLE_MS = 0; 
    let lastCheckedDate = "";
    let lastAutoClaimAttempt = 0;
    let lastClickTime = 0;

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
        const now = Date.now();
        if (now - lastClickTime < cooldownMs) return true;
        lastClickTime = now;
        return false;
    }

    function parseServerDateMs(dateStr) {
        if (!dateStr) return getAdjustedNowMs();
        if (typeof dateStr === 'number') return dateStr;
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
                localStorage.removeItem(`zn_welcome_seen_${userId}`);
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

    function getAdjustedNowMs() {
        return Date.now() + (window.serverTimeOffset || 0);
    }

    function syncServerTime(serverTimeStr) {
        if (!serverTimeStr) return;
        try {
            const serverMs = parseServerDateMs(serverTimeStr);
            if (!isNaN(serverMs)) {
                const diff = serverMs - Date.now();
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
            return (formatted.endsWith('.0') ? (num / 1000000).toFixed(0) : formatted) + "K";
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

        if (newBalance !== undefined && newBalance !== null) {
            const val = parseFloat(newBalance);
            patch.balance = val;
            patch.zn_balance = val;
            localStorage.setItem('zn_balance', val.toString());
            localStorage.setItem('user_balance', val.toString());
            const balEl = document.getElementById('farm-balance');
            if (balEl) balEl.innerHTML = `${formatSmartBalanceHTML(val)} ZN`;
        }

        if (newUsdBalance !== undefined && newUsdBalance !== null) {
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

    function toggleAdLoadingOverlay(show) {
        const overlay = document.getElementById('ad-loading-overlay');
        if (overlay) overlay.style.display = show ? 'flex' : 'none';
    }

    async function showMonetagAd() {
        toggleAdLoadingOverlay(true);
        const zoneId = GAME_CONFIG.monetagZoneId || "11322720";
        const functionName = window.MONETAG_SDK_NAME || `show_${zoneId}`;

        return new Promise((resolve) => {
            let resolved = false;

            const finish = (result) => {
                if (!resolved) {
                    resolved = true;
                    clearTimeout(timeoutTimer);
                    toggleAdLoadingOverlay(false);
                    resolve(result);
                }
            };

            const timeoutTimer = setTimeout(() => {
                console.warn("Monetag Ad timeout.");
                finish(false);
            }, 60000);

            if (typeof window[functionName] === 'function') {
                try {
                    const adPromise = window[functionName]();
                    if (adPromise && typeof adPromise.then === 'function') {
                        adPromise.then((res) => finish(res !== false)).catch((e) => {
                            console.error("خطأ تشغيل إعلان Monetag:", e);
                            finish(false);
                        });
                    } else {
                        finish(true);
                    }
                } catch (e) {
                    console.error("استدعاء Monetag فشل:", e);
                    finish(false);
                }
            } else {
                console.warn(`دالة Monetag الإعلانية غير متوفرة (${functionName}).`);
                finish(false);
            }
        });
    }

    async function showMonetixAd() {
        toggleAdLoadingOverlay(true);

        return new Promise((resolve) => {
            let resolved = false;
            let startHideTimer = null;

            const finish = (result) => {
                if (!resolved) {
                    resolved = true;
                    clearTimeout(timeoutTimer);
                    clearTimeout(startHideTimer);
                    toggleAdLoadingOverlay(false);
                    resolve(result);
                }
            };

            const timeoutTimer = setTimeout(() => {
                console.warn("Monetix Ad timeout.");
                finish(false);
            }, 60000);

            const blockId = GAME_CONFIG.monetixBlockId || "MX-3AE08FE9";
            const cleanBlockId = blockId.replace(/[^a-zA-Z0-9]/g, '_');
            const noDashBlockId = blockId.replace(/[^a-zA-Z0-9]/g, '');

            let monetixFn = window.showRewardAd || window.show_reward_ad || window[`show_${cleanBlockId}`] || window[`show_${noDashBlockId}`];
            if (!monetixFn && window.Monetix) {
                monetixFn = typeof window.Monetix.showReward === 'function' ? window.Monetix.showReward.bind(window.Monetix) : window.Monetix.show?.bind(window.Monetix);
            }

            if (monetixFn) {
                try {
                    const checkSuccessStatus = (status) => {
                        if (status === true) return true;
                        if (typeof status === 'string') {
                            const str = status.toLowerCase();
                            return ['completed', 'closed', 'rewarded', 'true'].includes(str);
                        }
                        if (typeof status === 'object' && status !== null) {
                            if (status.rewarded || status.completed || status.closed) return true;
                            const st = (status.status || status.state || status.event || status.type || '').toString().toLowerCase();
                            return ['completed', 'closed', 'rewarded'].includes(st);
                        }
                        return false;
                    };

                    const handleMonetixCallback = (status) => {
                        toggleAdLoadingOverlay(false);
                        if (checkSuccessStatus(status)) finish(true);
                        else if (status === false || (typeof status === 'string' && ['failed', 'error', 'skipped', 'dismissed'].includes(status))) {
                            finish(false);
                        }
                    };

                    const res = monetixFn(handleMonetixCallback);
                    startHideTimer = setTimeout(() => toggleAdLoadingOverlay(false), 500);

                    if (res && typeof res.then === 'function') {
                        res.then((r) => {
                            toggleAdLoadingOverlay(false);
                            if (checkSuccessStatus(r)) finish(true);
                            else if (r === false) finish(false);
                        }).catch((err) => {
                            console.error("Monetix Promise Error:", err);
                            finish(false);
                        });
                    }
                } catch (e) {
                    console.error("خطأ تشغيل إعلان Monetix:", e);
                    finish(false);
                }
            } else {
                console.warn("Monetix SDK غير متوفر.");
                finish(false);
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

        let maxC = parseFloat(pData.max_cap ?? 0.5);
        let baseRate = parseFloat(pData.hourly_rate ?? 0.1);
        let boostRate = getActiveBoostRate(pData);
        let hRate = baseRate + boostRate;

        let baseUnclaimed = parseFloat(pData.base_unclaimed !== undefined ? pData.base_unclaimed : (pData.unclaimed || 0));
        let accumulated = baseUnclaimed + ((hRate / 3600.0) * secondsPassed);

        if (accumulated >= maxC) accumulated = maxC;

        updateState({
            base_unclaimed: accumulated,
            unclaimed: accumulated,
            last_accrual_time: nowMs
        });

        return accumulated;
    }

    function updateBotAndAutoClaimUI(resData) {
        if (!resData) return;

        const isBotActive = (resData.bot_active !== undefined) 
            ? resData.bot_active 
            : (resData.player?.bot_active !== undefined 
                ? resData.player.bot_active 
                : (resData.player?.is_auto_bot_active === true));

        updateState({ bot_active: isBotActive });

        const botBadge = document.getElementById('bot-active-badge') || document.getElementById('bot-status-badge');
        if (botBadge) {
            botBadge.style.display = isBotActive ? 'inline-flex' : 'none';
        }

        const autoCollected = parseFloat(resData.auto_claimed_amount || resData.auto_collected || 0);
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
            let resData = await window.fetchAPI(`/api/farm/claim?t=${Date.now()}`, 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance ?? resData.balance, resData.new_usd_balance ?? resData.usd_balance);

                const nowMs = getAdjustedNowMs();
                const claimTime = resData.last_claim_time || new Date(nowMs).toISOString();

                updateState({
                    last_claim_time: claimTime,
                    unclaimed: 0.0,
                    base_unclaimed: 0.0,
                    last_accrual_time: parseServerDateMs(claimTime)
                });

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
        const now = Date.now();
        if (isFetching) return; 
        if (!force && (now - lastFetchTime < FETCH_THROTTLE_MS)) {
            window.updateFarmUI();
            return;
        }

        isFetching = true;
        try {
            let resData = await window.fetchAPI(`/api/farm/player_data?t=${Date.now()}`, 'POST', { start_param: START_PARAM });
            if (resData && resData.success) {
                lastFetchTime = Date.now();
                if (resData.server_time) syncServerTime(resData.server_time);
                if (resData.cooldown_seconds) MIN_CLAIM_INTERVAL = resData.cooldown_seconds;

                if (resData.monetag_zone_id) GAME_CONFIG.monetagZoneId = resData.monetag_zone_id;
                if (resData.monetix_block_id) GAME_CONFIG.monetixBlockId = resData.monetix_block_id;

                if (resData.game_config) {
                    const cfg = resData.game_config;
                    if (cfg.monetag_zone_id) GAME_CONFIG.monetagZoneId = cfg.monetag_zone_id;
                    if (cfg.monetix_block_id) GAME_CONFIG.monetixBlockId = cfg.monetix_block_id;
                    if (cfg.daily_rewards && Array.isArray(cfg.daily_rewards)) GAME_CONFIG.dailyRewards = cfg.daily_rewards;
                    if (cfg.upgrade_costs) GAME_CONFIG.upgradeCosts = cfg.upgrade_costs;
                    if (cfg.storage_config) GAME_CONFIG.storageConfig = cfg.storage_config;
                    if (cfg.max_upgrades_per_level) GAME_CONFIG.maxUpgradesPerLevel = cfg.max_upgrades_per_level;
                    if (cfg.daily_boost_reward) GAME_CONFIG.dailyBoostReward = cfg.daily_boost_reward;
                }

                if (resData.player) {
                    const isNewUser = resData.player.is_new_user === true || resData.player.welcome_seen === false;
                    if (isNewUser) clearStaleLocalCache();

                    const isBotActive = (resData.bot_active !== undefined)
                        ? resData.bot_active
                        : (resData.player.bot_active !== undefined ? resData.player.bot_active : (resData.player.is_auto_bot_active === true));

                    const serverTimeMs = resData.server_time ? parseServerDateMs(resData.server_time) : getAdjustedNowMs();

                    const newState = Object.assign({}, resData.player, {
                        bot_active: isBotActive,
                        base_unclaimed: parseFloat(resData.player.unclaimed || 0),
                        unclaimed: parseFloat(resData.player.unclaimed || 0),
                        last_accrual_time: serverTimeMs
                    });

                    updateState(newState);
                    setStoredBalance(resData.player.balance, resData.player.usd_balance);

                    const welcomeModal = document.getElementById('welcome-modal');
                    if (welcomeModal) {
                        welcomeModal.style.display = isNewUser ? 'flex' : 'none';
                        welcomeModal.classList.toggle('show', isNewUser);
                        welcomeModal.classList.toggle('active', isNewUser);
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

        const stgLvl = parseInt(pData.storage_level ?? 0, 10);
        const stgLvlEl = document.getElementById('storage-level-num');
        if (stgLvlEl) stgLvlEl.innerText = stgLvl + 1;

        const isBotActive = (pData.bot_active === true || pData.is_auto_bot_active === true);
        const botBadge = document.getElementById('bot-active-badge') || document.getElementById('bot-status-badge');
        if (botBadge) botBadge.style.display = isBotActive ? 'inline-flex' : 'none';

        const upgradeStgBtn = document.getElementById('upgrade-storage-btn');
        if (upgradeStgBtn) {
            upgradeStgBtn.onclick = window.handleStorageUpgrade;
            const nextLvl = stgLvl + 1;
            const nextCfg = GAME_CONFIG.storageConfig[nextLvl.toString()];
            if (stgLvl >= 8 || !nextCfg) {
                upgradeStgBtn.innerText = "المخزن في المستوى الأقصى (MAX) 🏆";
                upgradeStgBtn.disabled = true;
                upgradeStgBtn.className = "storage-upgrade-btn btn-disabled";
            } else {
                const costZn = typeof nextCfg === 'object' ? (nextCfg.cost_zn ?? nextCfg.cost ?? 0) : 0;
                const costUsd = typeof nextCfg === 'object' ? (nextCfg.cost_usd ?? 0) : 0;
                const costStrZn = formatCompactCost(costZn);
                const costStrUsd = costUsd > 0 ? ` + $${costUsd.toFixed(2)}` : '';
                
                const currentUnclaim = parseFloat(getState().unclaimed || 0);
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
                let count = parseInt(currentUpgrades[`lvl${i}`] || 0);
                let prevCount = parseInt(currentUpgrades[`lvl${i-1}`] || 0);
                let isUnlocked = (i === 1) || (prevCount > 0);
                let isMax = count >= GAME_CONFIG.maxUpgradesPerLevel;
                
                let lvlCfg = GAME_CONFIG.upgradeCosts[i] || {};
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
                        <button class="mining-card-btn" disabled>15/15 MAX</button>
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
    };

    function updateBoostButtonUI(pData) {
        const boostBtn = document.getElementById('boost-btn');
        if (!boostBtn) return;

        boostBtn.onclick = window.handleDailyBoost;
        const lastBoostTimeStr = pData.last_boost_time;

        if (!lastBoostTimeStr) {
            boostBtn.className = isBoosting ? "boost-btn btn-disabled" : "boost-btn";
            boostBtn.disabled = isBoosting;
            boostBtn.innerHTML = isBoosting 
                ? `<span style="font-size: 12px;">⏳</span><span style="font-size: 10px;">تفعيل...</span>`
                : `<span id="boost-icon">🚀</span><span id="boost-text">+0.1/h</span>`;
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
            boostBtn.className = isBoosting ? "boost-btn btn-disabled" : "boost-btn";
            boostBtn.disabled = isBoosting;
            boostBtn.innerHTML = isBoosting 
                ? `<span style="font-size: 12px;">⏳</span><span style="font-size: 10px;">تفعيل...</span>`
                : `<span id="boost-icon">🚀</span><span id="boost-text">+0.1/h</span>`;
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
                    html += `<div class="reward-day-card active"><div class="day-title">يوم ${dayNum}</div><div class="day-amount">${displayReward}</div><button id="daily-btn-${dayNum}" onclick="window.handleDailyClaim(${currentDailyDay})" style="background: #10b981; color: white; border: none; border-radius: 4px; padding: 2px 0; font-size: 9px; width: 100%; cursor: pointer;" ${isClaimingDaily ? 'disabled' : ''}>استلام</button></div>`;
                } else {
                    html += `<div class="reward-day-card" style="opacity: 0.4;"><div class="day-title">يوم ${dayNum}</div><div class="day-amount">${displayReward}</div></div>`;
                }
            }
        }
        container.innerHTML = html;
    }

    loadCachedData();
    window.updateFarmUI();

    if (window.farmIntervalId) clearInterval(window.farmIntervalId);
    window.farmIntervalId = setInterval(() => {
        const pData = getState();
        if (!pData) return;
        
        const todayStr = getTodayUTCStr();
        if (lastCheckedDate && lastCheckedDate !== todayStr) {
            lastCheckedDate = todayStr;
            window.fetchPlayerDataFromServer?.(true);
        }
        lastCheckedDate = todayStr;

        let maxC = parseFloat(pData.max_cap ?? 0.5);
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

        if (unclaim >= maxC) unclaim = maxC;
        updateState({ unclaimed: unclaim });

        const isBotActive = (pData.bot_active === true || pData.is_auto_bot_active === true);
        if (isBotActive && maxC > 0 && unclaim >= (maxC * 0.8) && !isAutoClaiming && !isClaimingMain) {
            if (Date.now() - lastAutoClaimAttempt > 10000) {
                lastAutoClaimAttempt = Date.now();
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
            window.fetchPlayerDataFromServer(false);
        }
    }

    window.addEventListener('pageshow', syncOnVisibility);
    document.addEventListener("visibilitychange", syncOnVisibility);

    window.addEventListener('userStateUpdated', (e) => {
        if (!isFetching && !isClaimingMain && !isAutoClaiming && !isUpgradingStorage && upgradingLevel === null) {
            window.updateFarmUI();
        }
    });

    window.handleStorageUpgrade = async function() {
        if (isDebouncedClick() || isUpgradingStorage) return;

        const pData = getState();
        const stgLvl = parseInt(pData.storage_level ?? 0, 10);
        const nextLvl = stgLvl + 1;
        const nextCfg = GAME_CONFIG.storageConfig[nextLvl.toString()];

        if (stgLvl >= 8 || !nextCfg) return;

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
        updateState({
            storage_level: nextLvl,
            max_cap: nextCfg.capacity !== undefined ? parseFloat(nextCfg.capacity) : getState().max_cap,
            unclaimed: 0.0,
            base_unclaimed: 0.0,
            last_claim_time: new Date(nowMs).toISOString(),
            last_accrual_time: nowMs
        });
        window.updateFarmUI();

        try {
            let resData = await window.fetchAPI(`/api/farm/upgrade_storage?t=${Date.now()}`, 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance ?? resData.balance, resData.new_usd_balance ?? resData.usd_balance);
                
                updateState({
                    storage_level: resData.storage_level !== undefined ? resData.storage_level : nextLvl,
                    unclaimed: 0.0,
                    base_unclaimed: 0.0,
                    last_claim_time: resData.server_time,
                    last_accrual_time: parseServerDateMs(resData.server_time)
                });

                showToast(`📦 تم ترقية سعة المخزن بنجاح إلى Level ${parseInt(resData.storage_level || nextLvl) + 1}!`);
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

        const lvlCfg = GAME_CONFIG.upgradeCosts[level] || {};
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
        const addRate = parseFloat(lvlCfg.rate || 0);
        const currentHourly = parseFloat(stateObj.hourly_rate || 0.1);

        updateState({
            upgrades: upgradesObj,
            upgrades_count: totalUpgradesCount,
            hourly_rate: addRate > 0 ? (currentHourly + addRate) : currentHourly,
            unclaimed: 0.0,
            base_unclaimed: 0.0,
            last_claim_time: new Date(nowMs).toISOString(),
            last_accrual_time: nowMs
        });
        window.updateFarmUI();

        try {
            let resData = await window.fetchAPI(`/api/farm/upgrade?t=${Date.now()}`, 'POST', { level: level });
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

    window.handleDailyClaim = async function(dayNum) {
        if (isDebouncedClick() || isClaimingDaily) return;
        
        const adSuccess = await showMonetagAd();
        if (!adSuccess) {
            showToast("❌ يجب مشاهدة الإعلان كاملاً لاستلام المكافأة اليومية!");
            return;
        }

        isClaimingDaily = true;
        const stateBackup = cloneCurrentState();

        try {
            let resData = await window.fetchAPI(`/api/farm/daily_claim?t=${Date.now()}`, 'POST', {});
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
        } catch (e) {
            console.error("خطأ استلام المكافأة اليومية:", e);
            restoreState(stateBackup);
            showToast("❌ حدث خطأ أثناء استلام المكافأة اليومية");
        } finally {
            isClaimingDaily = false;
            window.updateFarmUI();
        }
    };

    window.handleDailyBoost = async function() {
        if (isDebouncedClick() || isBoosting) return;

        const adSuccess = await showMonetixAd();
        if (!adSuccess) {
            showToast("❌ يجب مشاهدة إعلان Monetix بكامل مدته لتفعيل تسريع التعدين!");
            return;
        }

        isBoosting = true;
        accrueCurrentMining();
        const stateBackup = cloneCurrentState();

        try {
            let resData = await window.fetchAPI(`/api/farm/daily_boost?t=${Date.now()}`, 'POST', {});
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
        } catch (e) {
            console.error("خطأ التعزيز اليومي:", e);
            restoreState(stateBackup);
            showToast("❌ حدث خطأ أثناء تفعيل التعزيز");
        } finally {
            isBoosting = false;
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
            await executeClaimApi(false);
        } catch (e) {
            restoreState(stateBackup);
        } finally {
            isClaimingMain = false;
            window.updateFarmUI();
        }
    };

    window.handleClaim = window.handleMainClaim;

})();

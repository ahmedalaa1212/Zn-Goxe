window.initFarmView = function() {
    if (typeof window.onFarmTabOpen === 'function') {
        window.onFarmTabOpen();
    }
};

window.closeWelcomeModal = function() {
    const modal = document.getElementById('welcome-modal') || document.getElementById('auto-claim-modal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active', 'show');
    }

    if (!window.userState) window.userState = {};
    if (!window.PlayerData) window.PlayerData = {};

    window.userState.is_new_user = false;
    window.PlayerData.is_new_user = false;
    window.userState.welcome_seen = true;
    window.PlayerData.welcome_seen = true;

    try {
        const tele = window.Telegram?.WebApp;
        const userId = tele?.initDataUnsafe?.user?.id || window.userState?.tg_id || window.userState?.telegram_id || window.PlayerData?.tg_id || window.PlayerData?.telegram_id;
        if (userId) {
            localStorage.setItem(`zn_welcome_seen_${userId}`, 'true');
        }
        if (typeof window.fetchAPI === 'function') {
            window.fetchAPI('/api/farm/dismiss_welcome', 'POST', {}).catch(() => {});
        }
    } catch (e) {
        console.error("خطأ حفظ حالة النافذة الترحيبية:", e);
    }
};

(function initFarm() {
    const tele = window.Telegram?.WebApp;
    const START_PARAM = tele?.initDataUnsafe?.start_param || "";

    const GAME_CONFIG = {
        adsgramBlockId: window.ADSGRAM_BLOCK_ID || "",
        maxUpgradesPerLevel: 15,
        dailyBoostReward: 0.10, // زيادة السرعة بمقدار 0.1 ZN/ساعة
        boostDurationMs: 2 * 60 * 60 * 1000, // تعمل لمدة 2 ساعة
        boostCooldownMs: 3 * 60 * 60 * 1000, // تتجدد كل 3 ساعات
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
    let isCheckingAd = false; 
    let upgradingLevel = null;
    let isUpgradingStorage = false;

    let lastFetchTime = 0;
    const FETCH_THROTTLE_MS = 3000;
    let lastCheckedDate = "";

    function parseServerDateMs(dateStr) {
        if (!dateStr) return getAdjustedNowMs();
        if (typeof dateStr === 'number') return dateStr;
        let s = String(dateStr).trim().replace(' ', 'T');
        if (!s.endsWith('Z') && !s.includes('+') && !s.includes('-')) {
            s += 'Z';
        }
        const ms = new Date(s).getTime();
        return isNaN(ms) ? getAdjustedNowMs() : ms;
    }

    function getStorageAdKey() {
        const userId = tele?.initDataUnsafe?.user?.id || window.userState?.tg_id || window.userState?.telegram_id || window.PlayerData?.tg_id || window.PlayerData?.telegram_id;
        return userId ? `zn_last_claim_ad_${userId}` : 'zn_last_claim_ad_global';
    }

    function getCacheKey() {
        const userId = tele?.initDataUnsafe?.user?.id || window.userState?.tg_id || window.userState?.telegram_id || window.PlayerData?.tg_id;
        return userId ? `zn_farm_cache_${userId}` : 'zn_farm_cache_global';
    }

    function saveCachedData(data) {
        try {
            if (!data) return;
            const key = getCacheKey();
            localStorage.setItem(key, JSON.stringify(data));
        } catch (e) {
            console.error("خطأ حفظ الكاش المحلي:", e);
        }
    }

    function loadCachedData() {
        try {
            const key = getCacheKey();
            const cached = localStorage.getItem(key);
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
            const userId = tele?.initDataUnsafe?.user?.id || window.userState?.tg_id || window.userState?.telegram_id || window.PlayerData?.tg_id;
            if (userId) {
                localStorage.removeItem(`zn_farm_cache_${userId}`);
                localStorage.removeItem(`zn_last_claim_ad_${userId}`);
                localStorage.removeItem(`zn_welcome_seen_${userId}`);
            }
            localStorage.removeItem('zn_farm_cache_global');
            localStorage.removeItem('zn_last_claim_ad_global');
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
                window.serverTimeOffset = serverMs - Date.now();
            }
        } catch (e) {
            console.error("خطأ مزامنة وقت السيرفر:", e);
        }
    }

    function formatUsdBalance(val) {
        const num = parseFloat(val || 0);
        if (isNaN(num) || Math.abs(num) < 0.000001) return "$0.00";
        
        let str = num.toFixed(6).replace(/\.?0+$/, '');
        const parts = str.split('.');
        if (!parts[1]) {
            return `$${parts[0]}.00`;
        } else if (parts[1].length === 1) {
            return `$${parts[0]}.${parts[1]}0`;
        } else {
            return `$${str}`;
        }
    }

    function formatZnBalance(val) {
        const num = parseFloat(val || 0);
        if (isNaN(num) || num === 0) return "0.00";
        
        let fixed = num.toFixed(6);
        let parts = fixed.split('.');
        let decimals = parts[1].replace(/0+$/, '');
        if (decimals.length < 2) decimals = (decimals + '00').slice(0, 2);
        return `${parts[0]}.${decimals}`;
    }

    function formatStorageBalance(val) {
        const num = parseFloat(val || 0);
        if (isNaN(num) || num === 0) return "0.000000";
        
        let fixed = num.toFixed(6);
        let parts = fixed.split('.');
        let decimals = parts[1].replace(/0+$/, '');
        if (decimals.length < 3) decimals = (decimals + '000').slice(0, 3);
        return `${parts[0]}.${decimals}`;
    }

    function getStoredBalance() {
        if (window.userState && window.userState.balance !== undefined) {
            return parseFloat(window.userState.balance || 0);
        }
        return parseFloat(window.PlayerData?.balance || 0);
    }

    function getStoredUsdBalance() {
        if (window.userState && window.userState.usd_balance !== undefined) {
            return parseFloat(window.userState.usd_balance || 0);
        }
        return parseFloat(window.PlayerData?.usd_balance || 0);
    }

    function setStoredBalance(newBalance, newUsdBalance) {
        if (!window.userState) window.userState = {};
        if (!window.PlayerData) window.PlayerData = {};

        if (newBalance !== undefined && newBalance !== null) {
            const val = parseFloat(newBalance);
            window.userState.balance = val; 
            window.PlayerData.balance = val;
            const balEl = document.getElementById('farm-balance');
            if (balEl) balEl.innerText = `${formatZnBalance(val)} ZN`;
        }

        if (newUsdBalance !== undefined && newUsdBalance !== null) {
            const usdVal = parseFloat(newUsdBalance);
            window.userState.usd_balance = usdVal;
            window.PlayerData.usd_balance = usdVal;
            const usdEl = document.getElementById('farm-usd-balance');
            if (usdEl) usdEl.innerText = formatUsdBalance(usdVal);
        }

        saveCachedData(window.userState);
    }

    function getTodayUTCStr() {
        const adjustedNow = new Date(getAdjustedNowMs());
        return adjustedNow.toISOString().split('T')[0];
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
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000 && num % 1000 === 0) return (num / 1000) + 'K';
        return (Math.round(num * 100) / 100).toString();
    }

    function toggleAdLoadingOverlay(show) {
        const overlay = document.getElementById('ad-loading-overlay');
        if (overlay) {
            overlay.style.display = show ? 'flex' : 'none';
        }
    }

    async function ensureAdsgramLoaded() {
        if (window.Adsgram) return true;
        return new Promise((resolve) => {
            const script = document.createElement('script');
            script.src = 'https://sad.adsgram.ai/js/sad.min.js';
            script.async = true;
            script.onload = () => resolve(true);
            script.onerror = () => resolve(false);
            document.head.appendChild(script);
        });
    }

    async function showAdsgramAd() {
        toggleAdLoadingOverlay(true);
        
        const isLoaded = await ensureAdsgramLoaded();
        const blockId = window.ADSGRAM_BLOCK_ID || GAME_CONFIG.adsgramBlockId || "";

        if (!window.Adsgram || !isLoaded) {
            console.error("Adsgram SDK لم يتم تحميلة.");
            toggleAdLoadingOverlay(false);
            return false;
        }

        if (!blockId || blockId.trim() === "") {
            console.error("Adsgram Block ID missing!");
            toggleAdLoadingOverlay(false);
            return false;
        }

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
                console.log("Adsgram timeout reached.");
                finish(false);
            }, 10000);

            try {
                const AdController = window.Adsgram.init({ blockId: blockId.trim() });
                AdController.show().then(() => {
                    console.log("تمت مشاهدة إعلان Adsgram بنجاح!");
                    finish(true);
                }).catch((err) => {
                    console.error("خطأ أو تخطي إعلان Adsgram:", err);
                    finish(false);
                });
            } catch (e) {
                console.error("استثناء تنفيذ Adsgram:", e);
                finish(false);
            }
        });
    }

    function showMonetagAd() {
        return new Promise((resolve) => {
            if (typeof window.show_11322720 === 'function') {
                toggleAdLoadingOverlay(true);
                window.show_11322720().then(() => {
                    toggleAdLoadingOverlay(false);
                    resolve(true);
                }).catch((e) => {
                    console.error("Monetag Ad Error:", e);
                    toggleAdLoadingOverlay(false);
                    resolve(true); 
                });
            } else {
                console.warn("Monetag script not found.");
                resolve(true);
            }
        });
    }

    function getActiveBoostRate(pData) {
        if (!pData || !pData.last_boost_time) return 0;
        let lastBoostMs = parseServerDateMs(pData.last_boost_time);
        let elapsed = getAdjustedNowMs() - lastBoostMs;
        if (elapsed >= 0 && elapsed < GAME_CONFIG.boostDurationMs) {
            return GAME_CONFIG.dailyBoostReward; // +0.1 ZN/h
        }
        return 0;
    }

    function accrueCurrentMining() {
        const pData = window.userState || window.PlayerData;
        if (!pData) return;

        let maxC = parseFloat(pData.max_cap ?? 0.5);
        let baseRate = parseFloat(pData.hourly_rate ?? 0.1);
        let boostRate = getActiveBoostRate(pData);
        let hRate = baseRate + boostRate;

        let lastClaimStr = pData.last_claim_time;
        let lastClaimTimeMs = lastClaimStr ? parseServerDateMs(lastClaimStr) : getAdjustedNowMs();
        let secondsPassed = Math.max(0, (getAdjustedNowMs() - lastClaimTimeMs) / 1000);
        
        let baseUnclaimed = parseFloat(pData.base_unclaimed || 0);
        let accumulated = baseUnclaimed + (hRate / 3600.0) * secondsPassed;
        if (accumulated >= maxC) accumulated = maxC;

        pData.base_unclaimed = accumulated;
        pData.unclaimed = accumulated;
        pData.last_claim_time = new Date(getAdjustedNowMs()).toISOString();

        if (window.userState) {
            window.userState.base_unclaimed = accumulated;
            window.userState.unclaimed = accumulated;
            window.userState.last_claim_time = pData.last_claim_time;
        }
        if (window.PlayerData) {
            window.PlayerData.base_unclaimed = accumulated;
            window.PlayerData.unclaimed = accumulated;
            window.PlayerData.last_claim_time = pData.last_claim_time;
        }
    }

    // تحديث الواجهة الخاصة ببادج البوت ونافذة التجميع التلقائي القادمة من السيرفر
    function updateBotAndAutoClaimUI(resData) {
        if (!resData) return;

        // 1. تحديث إظهار شريط البوت النشط أعلى قائمة التعدين
        const isBotActive = resData.bot_active || resData.player?.bot_active || false;
        const botBadge = document.getElementById('bot-active-badge') || document.getElementById('bot-status-badge');
        if (botBadge) {
            botBadge.style.display = isBotActive ? 'inline-flex' : 'none';
        }

        // 2. معالجة وتنبيه التجميع التلقائي قادماً من السيرفر
        const autoCollected = parseFloat(resData.auto_claimed_amount || resData.auto_collected || 0);
        if (autoCollected > 0) {
            const autoModal = document.getElementById('auto-claim-modal') || document.getElementById('welcome-modal');
            const autoAmountText = document.getElementById('auto-claimed-amount') || document.getElementById('modal-auto-amount');
            if (autoAmountText) {
                autoAmountText.innerText = `${formatZnBalance(autoCollected)} ZN`;
            }
            if (autoModal) {
                autoModal.style.display = 'flex';
                autoModal.classList.add('show', 'active');
            } else {
                showToast(`🤖 تم التجميع التلقائي للبوت: ${formatZnBalance(autoCollected)} ZN!`);
            }
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
            let resData = await window.fetchAPI('/api/farm/player_data', 'POST', { start_param: START_PARAM });
            if (resData && resData.success) {
                lastFetchTime = Date.now();
                if (resData.server_time) syncServerTime(resData.server_time);
                if (resData.cooldown_seconds) MIN_CLAIM_INTERVAL = resData.cooldown_seconds;

                if (resData.adsgram_block_id) {
                    GAME_CONFIG.adsgramBlockId = resData.adsgram_block_id;
                    window.ADSGRAM_BLOCK_ID = resData.adsgram_block_id;
                }

                if (resData.game_config) {
                    if (resData.game_config.adsgram_block_id) {
                        GAME_CONFIG.adsgramBlockId = resData.game_config.adsgram_block_id;
                        window.ADSGRAM_BLOCK_ID = resData.game_config.adsgram_block_id;
                    }
                    if (resData.game_config.daily_rewards && Array.isArray(resData.game_config.daily_rewards)) {
                        GAME_CONFIG.dailyRewards = resData.game_config.daily_rewards;
                    }
                    if (resData.game_config.upgrade_costs) {
                        GAME_CONFIG.upgradeCosts = resData.game_config.upgrade_costs;
                    }
                    if (resData.game_config.storage_config) {
                        GAME_CONFIG.storageConfig = resData.game_config.storage_config;
                    }
                    if (resData.game_config.max_upgrades_per_level) {
                        GAME_CONFIG.maxUpgradesPerLevel = resData.game_config.max_upgrades_per_level;
                    }
                    if (resData.game_config.daily_boost_reward) {
                        GAME_CONFIG.dailyBoostReward = resData.game_config.daily_boost_reward;
                    }
                }

                if (resData.player) {
                    const adKey = getStorageAdKey();
                    const isNewUser = resData.player.is_new_user === true || resData.player.welcome_seen === false || !resData.player.last_claim_ad_date;

                    if (isNewUser) {
                        clearStaleLocalCache();
                    }

                    window.userState = {};
                    window.PlayerData = {};

                    Object.assign(window.PlayerData, resData.player);
                    Object.assign(window.userState, resData.player);

                    window.userState.base_unclaimed = parseFloat(resData.player.unclaimed || 0);
                    window.PlayerData.base_unclaimed = parseFloat(resData.player.unclaimed || 0);

                    if (resData.player.last_claim_ad_date) {
                        localStorage.setItem(adKey, resData.player.last_claim_ad_date);
                    } else {
                        window.userState.last_claim_ad_date = null;
                        window.PlayerData.last_claim_ad_date = null;
                        localStorage.removeItem(adKey);
                    }

                    saveCachedData(window.userState);
                    setStoredBalance(resData.player.balance, resData.player.usd_balance);

                    const welcomeModal = document.getElementById('welcome-modal');
                    if (welcomeModal) {
                        if (isNewUser) {
                            welcomeModal.style.display = 'flex';
                            welcomeModal.classList.add('show', 'active');
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
        const pData = window.userState || window.PlayerData || {};
        let bal = getStoredBalance();
        let usdBal = getStoredUsdBalance();
        let baseRate = parseFloat(pData.hourly_rate ?? 0.1);
        let boostRate = getActiveBoostRate(pData);
        let totalRate = baseRate + boostRate;

        const balEl = document.getElementById('farm-balance');
        if (balEl) balEl.innerText = `${formatZnBalance(bal)} ZN`;

        const usdEl = document.getElementById('farm-usd-balance');
        if (usdEl) usdEl.innerText = formatUsdBalance(usdBal);

        const rateEl = document.getElementById('farm-rate');
        if (rateEl) {
            let formattedRate = (totalRate % 1 === 0) ? totalRate.toString() : Number(totalRate.toFixed(4)).toString();
            let boostIndicator = boostRate > 0 ? ` <span style="color:#10b981; font-size:11px;">(+0.1🚀)</span>` : '';
            rateEl.innerHTML = `<span dir="ltr">${formattedRate} /h</span>⚡${boostIndicator}`;
        }

        const stgLvl = parseInt(pData.storage_level ?? 0, 10);
        const stgLvlEl = document.getElementById('storage-level-num');
        if (stgLvlEl) stgLvlEl.innerText = stgLvl + 1;

        const isBotActive = pData.bot_active === true;
        const botBadge = document.getElementById('bot-active-badge') || document.getElementById('bot-status-badge');
        if (botBadge) {
            botBadge.style.display = isBotActive ? 'inline-flex' : 'none';
        }

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
                
                const canAfford = (bal >= costZn) && (usdBal >= costUsd);
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

            for (let i = 1; i <= 8; i++) {
                let count = parseInt(currentUpgrades[`lvl${i}`] || 0);
                let prevCount = parseInt(currentUpgrades[`lvl${i-1}`] || 0);
                let isUnlocked = (i === 1) || (prevCount > 0);
                let isMax = count >= GAME_CONFIG.maxUpgradesPerLevel;
                
                let lvlCfg = GAME_CONFIG.upgradeCosts[i] || {};
                let costZn = lvlCfg.cost_zn ?? lvlCfg.base_cost ?? lvlCfg.price ?? 0;
                let costUsd = lvlCfg.cost_usd ?? lvlCfg.base_cost_usd ?? 0;

                let costStrZn = formatCompactCost(costZn);
                let costStrUsd = costUsd > 0 ? `+$${costUsd.toFixed(2)}` : '';
                let canAfford = (bal >= costZn) && (usdBal >= costUsd);
                let isThisCardUpgrading = (upgradingLevel === i);

                if (isMax) {
                    fieldsHTML += `
                    <div class="mining-card">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">مستوى ${i} (MAX)</div>
                        <button class="mining-card-btn" disabled>15/15 MAX</button>
                    </div>`;
                } else if (count > 0) {
                    fieldsHTML += `
                    <div class="mining-card" onclick="window.handleUpgrade(${i})">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">مستوى ${i} (x${count})</div>
                        <button class="mining-card-btn" ${!canAfford || isAnyUpgrading ? 'disabled' : ''}>${isThisCardUpgrading ? 'جاري...' : `ترقية (${costStrZn}${costStrUsd})`}</button>
                    </div>`;
                } else if (isUnlocked) {
                    fieldsHTML += `
                    <div class="mining-card" onclick="window.handleUpgrade(${i})">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">مستوى ${i}</div>
                        <button class="mining-card-btn" ${!canAfford || isAnyUpgrading ? 'disabled' : ''}>${isThisCardUpgrading ? 'جاري...' : `شراء (${costStrZn}${costStrUsd})`}</button>
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
            if (!isBoosting) {
                boostBtn.className = "boost-btn";
                boostBtn.disabled = false;
                boostBtn.innerHTML = `<span id="boost-icon">🚀</span><span id="boost-text">+0.1/h</span>`;
            } else {
                boostBtn.className = "boost-btn btn-disabled";
                boostBtn.disabled = true;
                boostBtn.innerHTML = `<span style="font-size: 12px;">⏳</span><span style="font-size: 10px;">تفعيل...</span>`;
            }
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
            if (!isBoosting) {
                boostBtn.className = "boost-btn";
                boostBtn.disabled = false;
                boostBtn.innerHTML = `<span id="boost-icon">🚀</span><span id="boost-text">+0.1/h</span>`;
            } else {
                boostBtn.className = "boost-btn btn-disabled";
                boostBtn.disabled = true;
                boostBtn.innerHTML = `<span style="font-size: 12px;">⏳</span><span style="font-size: 10px;">تفعيل...</span>`;
            }
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
        if (!rewards || !Array.isArray(rewards)) return 0.2;
        return rewards[index] ?? 40.0;
    }

    function renderDailyRewards() {
        const container = document.getElementById('daily-rewards-container');
        const pData = window.userState || window.PlayerData || {};
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
        const pData = window.userState || window.PlayerData;
        if (!pData) return;
        
        const todayStr = getTodayUTCStr();

        if (lastCheckedDate && lastCheckedDate !== todayStr) {
            lastCheckedDate = todayStr;
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                window.fetchPlayerDataFromServer(true);
            }
        }
        lastCheckedDate = todayStr;

        let maxC = parseFloat(pData.max_cap ?? 0.5);
        let baseRate = parseFloat(pData.hourly_rate ?? 0.1);
        let boostRate = getActiveBoostRate(pData);
        let hRate = baseRate + boostRate;
        
        let lastClaimStr = pData.last_claim_time;
        let lastClaimTimeMs = lastClaimStr ? parseServerDateMs(lastClaimStr) : getAdjustedNowMs();
        
        let secondsPassed = Math.max(0, (getAdjustedNowMs() - lastClaimTimeMs) / 1000);
        let baseUnclaimed = parseFloat(pData.base_unclaimed || 0);
        let unclaim = baseUnclaimed + (hRate / 3600.0) * secondsPassed;

        if (unclaim >= maxC) unclaim = maxC;
        pData.unclaimed = unclaim;
        if (window.userState) window.userState.unclaimed = unclaim;
        if (window.PlayerData) window.PlayerData.unclaimed = unclaim;

        const progressEl = document.getElementById('storage-progress');
        const storageTextEl = document.getElementById('storage-text');

        let pct = maxC > 0 ? (unclaim / maxC) * 100 : 0;
        pct = Math.max(0, Math.min(pct, 100));

        if (progressEl && storageTextEl) {
            progressEl.style.width = `${pct}%`;
            storageTextEl.innerText = `${formatStorageBalance(unclaim)} / ${maxC.toLocaleString('en-US', {maximumFractionDigits: 2})}`;
        }

        const remainingCooldown = Math.max(0, Math.ceil(MIN_CLAIM_INTERVAL - secondsPassed));

        // التجميع التلقائي فور إملاء المخزن بنسبة 80% أو أكثر
        if (pct >= 80 && !isClaimingMain && !isCheckingAd && remainingCooldown <= 0 && unclaim > 0) {
            console.log("وصل المخزن إلى 80% أو أكثر، جارٍ التجميع التلقائي...");
            window.handleMainClaim();
        }

        const claimBtn = document.getElementById('claim-btn');
        if (claimBtn) {
            claimBtn.onclick = window.handleMainClaim;

            if (isCheckingAd) {
                claimBtn.innerText = "جاري فحص الإعلان... ⏳";
                claimBtn.className = "claim-action-btn btn-disabled";
                claimBtn.disabled = true;
            } else if (isClaimingMain) {
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
        const lastDailyClaim = pData.last_daily_claim_date;
        if (dailyTimerEl && lastDailyClaim === todayStr) {
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

    window.handleStorageUpgrade = async function() {
        if (isUpgradingStorage) return;

        const pData = window.userState || window.PlayerData || {};
        const stgLvl = parseInt(pData.storage_level ?? 0, 10);
        const nextLvl = stgLvl + 1;
        const nextCfg = GAME_CONFIG.storageConfig[nextLvl.toString()];

        if (stgLvl >= 8 || !nextCfg) return;

        const costZn = typeof nextCfg === 'object' ? (nextCfg.cost_zn ?? nextCfg.cost ?? 0) : 0;
        const costUsd = typeof nextCfg === 'object' ? (nextCfg.cost_usd ?? 0) : 0;
        const bal = getStoredBalance();
        const usdBal = getStoredUsdBalance();

        if (bal < costZn || usdBal < costUsd) {
            showToast("❌ رصيدك غير كافٍ لترقية المخزن");
            return;
        }

        isUpgradingStorage = true;
        const stateBackup = cloneCurrentState();

        accrueCurrentMining();

        setStoredBalance(Math.max(0, bal - costZn), Math.max(0, usdBal - costUsd));
        window.userState.storage_level = nextLvl;
        window.PlayerData.storage_level = nextLvl;
        if (nextCfg.capacity !== undefined) {
            window.userState.max_cap = parseFloat(nextCfg.capacity);
            window.PlayerData.max_cap = parseFloat(nextCfg.capacity);
        }
        window.updateFarmUI();

        try {
            let resData = await window.fetchAPI('/api/farm/upgrade_storage', 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance ?? resData.balance, resData.new_usd_balance ?? resData.usd_balance);
                
                if (resData.storage_level !== undefined) {
                    window.userState.storage_level = resData.storage_level;
                    window.PlayerData.storage_level = resData.storage_level;
                }
                if (resData.max_cap !== undefined) {
                    window.userState.max_cap = parseFloat(resData.max_cap);
                    window.PlayerData.max_cap = parseFloat(resData.max_cap);
                }
                if (resData.last_claim_time) {
                    window.userState.last_claim_time = resData.last_claim_time;
                    window.PlayerData.last_claim_time = resData.last_claim_time;
                }
                if (resData.unclaimed !== undefined) {
                    window.userState.unclaimed = parseFloat(resData.unclaimed);
                    window.PlayerData.unclaimed = parseFloat(resData.unclaimed);
                    window.userState.base_unclaimed = parseFloat(resData.unclaimed);
                    window.PlayerData.base_unclaimed = parseFloat(resData.unclaimed);
                }
                saveCachedData(window.userState);
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
        if (upgradingLevel !== null) return;

        const lvlCfg = GAME_CONFIG.upgradeCosts[level] || {};
        const costZn = lvlCfg.cost_zn ?? lvlCfg.base_cost ?? lvlCfg.price ?? 0;
        const costUsd = lvlCfg.cost_usd ?? lvlCfg.base_cost_usd ?? 0;

        const currentBal = getStoredBalance();
        const currentUsdBal = getStoredUsdBalance();

        if (currentBal < costZn || currentUsdBal < costUsd) {
            let msg = `❌ رصيدك غير كافٍ! سعر الترقية: ${costZn.toLocaleString()} ZN`;
            if (costUsd > 0) msg += ` + $${costUsd.toFixed(2)} USD`;
            showToast(msg);
            return;
        }

        upgradingLevel = level;
        const stateBackup = cloneCurrentState();

        accrueCurrentMining();

        setStoredBalance(Math.max(0, currentBal - costZn), Math.max(0, currentUsdBal - costUsd));

        if (!window.userState.upgrades) window.userState.upgrades = {};
        if (!window.PlayerData.upgrades) window.PlayerData.upgrades = {};
        const currentCount = parseInt(window.userState.upgrades[`lvl${level}`] || 0, 10);
        window.userState.upgrades[`lvl${level}`] = currentCount + 1;
        window.PlayerData.upgrades[`lvl${level}`] = currentCount + 1;

        const addRate = parseFloat(lvlCfg.rate || 0);
        if (addRate > 0) {
            const currentHourly = parseFloat(window.userState.hourly_rate || 0.1);
            window.userState.hourly_rate = currentHourly + addRate;
            window.PlayerData.hourly_rate = currentHourly + addRate;
        }
        window.updateFarmUI();

        try {
            let resData = await window.fetchAPI('/api/farm/upgrade', 'POST', { level: level });
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance ?? resData.balance, resData.new_usd_balance ?? resData.usd_balance);
                
                const newHourly = resData.new_hourly_rate ?? resData.hourly_rate ?? resData.rate;
                if (newHourly !== undefined && newHourly !== null) {
                    window.userState.hourly_rate = parseFloat(newHourly);
                    window.PlayerData.hourly_rate = parseFloat(newHourly);
                }
                if (resData.upgrades) {
                    window.userState.upgrades = resData.upgrades;
                    window.PlayerData.upgrades = resData.upgrades;
                }
                if (resData.last_claim_time) {
                    window.userState.last_claim_time = resData.last_claim_time;
                    window.PlayerData.last_claim_time = resData.last_claim_time;
                }
                if (resData.unclaimed !== undefined) {
                    window.userState.unclaimed = parseFloat(resData.unclaimed);
                    window.PlayerData.unclaimed = parseFloat(resData.unclaimed);
                    window.userState.base_unclaimed = parseFloat(resData.unclaimed);
                    window.PlayerData.base_unclaimed = parseFloat(resData.unclaimed);
                }

                saveCachedData(window.userState);
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
        if (isClaimingDaily) return;
        isClaimingDaily = true;
        const stateBackup = cloneCurrentState();

        try {
            await showMonetagAd();

            let resData = await window.fetchAPI('/api/farm/daily_claim', 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance ?? resData.balance, resData.new_usd_balance ?? resData.usd_balance);
                
                if (!window.userState) window.userState = {};
                if (!window.PlayerData) window.PlayerData = {};

                if (resData.daily_day !== undefined) {
                    window.userState.daily_day = resData.daily_day;
                    window.PlayerData.daily_day = resData.daily_day;
                }
                if (resData.last_daily_claim_date) {
                    window.userState.last_daily_claim_date = resData.last_daily_claim_date;
                    window.PlayerData.last_daily_claim_date = resData.last_daily_claim_date;
                }
                saveCachedData(window.userState);
                showToast(`🎉 تم استلام مكافأة اليوم ${resData.daily_day} بنجاح!`);
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
        if (isBoosting) return;
        isBoosting = true;
        const stateBackup = cloneCurrentState();

        try {
            await showMonetagAd();

            let resData = await window.fetchAPI('/api/farm/daily_boost', 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);

                if (resData.player) {
                    Object.assign(window.PlayerData, resData.player);
                    Object.assign(window.userState, resData.player);
                }

                const newBal = resData.new_balance ?? resData.balance ?? resData.player?.balance;
                const newUsdBal = resData.new_usd_balance ?? resData.usd_balance ?? resData.player?.usd_balance;
                setStoredBalance(newBal, newUsdBal);

                if (resData.last_boost_time || resData.player?.last_boost_time) {
                    const bTime = resData.last_boost_time || resData.player?.last_boost_time;
                    window.userState.last_boost_time = bTime;
                    window.PlayerData.last_boost_time = bTime;
                }

                if (resData.last_claim_time) {
                    window.userState.last_claim_time = resData.last_claim_time;
                    window.PlayerData.last_claim_time = resData.last_claim_time;
                }
                if (resData.unclaimed !== undefined) {
                    window.userState.unclaimed = parseFloat(resData.unclaimed);
                    window.PlayerData.unclaimed = parseFloat(resData.unclaimed);
                    window.userState.base_unclaimed = parseFloat(resData.unclaimed);
                    window.PlayerData.base_unclaimed = parseFloat(resData.unclaimed);
                }

                showToast(`⚡ تم تفعيل تعزيز السرعة (+0.1 ZN/ساعة) لمدة ساعتين بنجاح!`);
                saveCachedData(window.userState);
            } else {
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
        if (isClaimingMain || isCheckingAd) return;

        const pData = window.userState || window.PlayerData || {};
        const todayStr = getTodayUTCStr(); 
        const adKey = getStorageAdKey();

        let lastAdDate = pData.last_claim_ad_date || null;
        let adsWatched = parseInt(pData.ads_watched || 0, 10);

        let needsAdToday = (!lastAdDate) || (lastAdDate !== todayStr) || (adsWatched === 0);
        let adShown = false;

        if (needsAdToday) {
            isCheckingAd = true; 
            window.updateFarmUI();
            try {
                adShown = await showAdsgramAd(); 
                if (!adShown) {
                    console.warn("لم يتم عرض الإعلان بنجاح، سيتم السماح بالتجميع مع إعادة محاولة الإعلان المرة القادمة.");
                }
            } catch(e) {
                console.error("Ad Check Error:", e);
                adShown = false;
            }
            isCheckingAd = false;
        }

        isClaimingMain = true;
        const stateBackup = cloneCurrentState();

        const currentUnclaimed = parseFloat(pData.unclaimed || 0);
        if (currentUnclaimed > 0) {
            const currentBal = getStoredBalance();
            setStoredBalance(currentBal + currentUnclaimed, getStoredUsdBalance());
            window.userState.unclaimed = 0.0;
            window.PlayerData.unclaimed = 0.0;
            window.userState.base_unclaimed = 0.0;
            window.PlayerData.base_unclaimed = 0.0;
            window.updateFarmUI();
        }

        try {
            let resData = await window.fetchAPI('/api/farm/claim', 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance ?? resData.balance, resData.new_usd_balance ?? resData.usd_balance);
                
                if (!window.userState) window.userState = {};
                if (!window.PlayerData) window.PlayerData = {};

                if (resData.last_claim_time) {
                    window.userState.last_claim_time = resData.last_claim_time;
                    window.PlayerData.last_claim_time = resData.last_claim_time;
                }

                if (resData.ads_watched !== undefined) {
                    window.userState.ads_watched = resData.ads_watched;
                    window.PlayerData.ads_watched = resData.ads_watched;
                }

                if (adShown) {
                    const savedAdDate = resData.last_claim_ad_date || todayStr;
                    window.userState.last_claim_ad_date = savedAdDate;
                    window.PlayerData.last_claim_ad_date = savedAdDate;
                    localStorage.setItem(adKey, savedAdDate);
                }

                window.userState.unclaimed = 0.0;
                window.PlayerData.unclaimed = 0.0;
                window.userState.base_unclaimed = 0.0;
                window.PlayerData.base_unclaimed = 0.0;

                saveCachedData(window.userState);
                
                showToast(`💰 تم تجميع ${formatZnBalance(resData.claimed_amount)} عملة بنجاح!`);
            } else {
                restoreState(stateBackup);
                showToast(resData?.error || "❌ تعذر تجميع الرصيد");
            }
        } catch (e) {
            console.error("خطأ التجميع الرئيسي:", e);
            restoreState(stateBackup);
            showToast("❌ حدث خطأ أثناء التجميع");
        } finally {
            isClaimingMain = false;
            toggleAdLoadingOverlay(false);
            window.updateFarmUI();
        }
    };

    window.handleClaim = window.handleMainClaim;

})();

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
        maxUpgradesPerLevel: 15,
        dailyBoostReward: 0.15,
        maxDailyBoostRate: 4.5,
        boostMaxRewardCoins: 35.0,
        upgradeCosts: {
            1: { cost_zn: 600, cost_usd: 0.0, rate: 1.0 },
            2: { cost_zn: 1500, cost_usd: 0.10, rate: 2.5 },
            3: { cost_zn: 3800, cost_usd: 0.15, rate: 6.0 },
            4: { cost_zn: 10000, cost_usd: 0.20, rate: 15.0 },
            5: { cost_zn: 28000, cost_usd: 0.25, rate: 40.0 },
            6: { cost_zn: 75000, cost_usd: 0.30, rate: 100.0 },
            7: { cost_zn: 200000, cost_usd: 0.35, rate: 250.0 },
            8: { cost_zn: 500000, cost_usd: 0.40, rate: 600.0 },
            9: { cost_zn: 1400000, cost_usd: 0.50, rate: 1500.0 }
        },
        storageConfig: {
            "0": { capacity: 30.0, cost_zn: 0, cost_usd: 0.0 },
            "1": { capacity: 150.0, cost_zn: 400, cost_usd: 0.0 },
            "2": { capacity: 500.0, cost_zn: 1200, cost_usd: 0.05 },
            "3": { capacity: 1500.0, cost_zn: 3500, cost_usd: 0.10 },
            "4": { capacity: 4000.0, cost_zn: 10000, cost_usd: 0.15 },
            "5": { capacity: 10000.0, cost_zn: 25000, cost_usd: 0.20 },
            "6": { capacity: 25000.0, cost_zn: 65000, cost_usd: 0.25 },
            "7": { capacity: 70000.0, cost_zn: 180000, cost_usd: 0.30 },
            "8": { capacity: 200000.0, cost_zn: 500000, cost_usd: 0.35 },
            "9": { capacity: 600000.0, cost_zn: 1500000, cost_usd: 0.40 }
        },
        dailyRewards: [
            5, 10, 15, 20, 25, 30, 40, 45, 50, 60,
            65, 70, 75, 90, 100, 110, 120, 130, 140, 160,
            180, 200, 220, 240, 270, 300, 330, 360, 400, 450
        ]
    };

    let MIN_CLAIM_INTERVAL = 15;

    let isClaimingDaily = false;
    let isBoosting = false; 
    let isFetching = false;
    let isClaimingMain = false; 
    let isUpgrading = false;
    let isUpgradingStorage = false;

    let lastFetchTime = 0;
    const FETCH_THROTTLE_MS = 3000;
    let lastCheckedDate = "";

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
                    if (!window.userState) window.userState = {};
                    if (!window.PlayerData) window.PlayerData = {};
                    Object.assign(window.userState, parsed);
                    Object.assign(window.PlayerData, parsed);
                    return true;
                }
            }
        } catch (e) {
            console.error("خطأ قراءة الكاش المحلي:", e);
        }
        return false;
    }

    function showToast(message) {
        if (tele && tele.showAlert) tele.showAlert(message);
        else alert(message);
    }

    function getAdjustedNowMs() {
        return Date.now() + (window.serverTimeOffset || 0);
    }

    function syncServerTime(serverTimeStr) {
        if (!serverTimeStr) return;
        try {
            const serverMs = new Date(serverTimeStr).getTime();
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

    // دالة تنسيق رصيد ZN المحدثة: تعرض حتى 6 خانات عشرية بدقة دون حذف الكسر
    function formatZnBalance(val) {
        const num = parseFloat(val || 0);
        if (isNaN(num) || num === 0) return "0.00";
        
        let str = num.toFixed(6).replace(/\.?0+$/, '');
        if (!str.includes('.')) return str + '.00';
        if (str.split('.')[1].length === 1) return str + '0';
        return str;
    }

    // دالة جديدة مخصصة لتنسيق سعة التخزين المؤقت بـ 3 أرقام عشرية فقط
    function formatStorageBalance(val) {
        const num = parseFloat(val || 0);
        if (isNaN(num) || num === 0) return "0.000";
        return num.toFixed(3);
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
        return num.toString();
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

                if (resData.game_config) {
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
                    if (resData.game_config.max_daily_boost_rate) {
                        GAME_CONFIG.maxDailyBoostRate = resData.game_config.max_daily_boost_rate;
                    }
                    if (resData.game_config.boost_max_reward_coins) {
                        GAME_CONFIG.boostMaxRewardCoins = resData.game_config.boost_max_reward_coins;
                    }
                    if (resData.game_config.adsgram_block_id) {
                        window.ADSGRAM_BLOCK_ID = resData.game_config.adsgram_block_id;
                    }
                }

                if (!window.PlayerData) window.PlayerData = {};
                if (!window.userState) window.userState = {};

                if (resData.player) {
                    Object.assign(window.PlayerData, resData.player);
                    Object.assign(window.userState, resData.player);
                    saveCachedData(resData.player);
                    setStoredBalance(resData.player.balance, resData.player.usd_balance);

                    const isNew = resData.player.is_new_user === true || resData.player.welcome_seen === false;
                    const welcomeModal = document.getElementById('welcome-modal');
                    if (welcomeModal) {
                        if (isNew) {
                            welcomeModal.style.display = 'flex';
                            welcomeModal.classList.add('show', 'active');
                        } else {
                            welcomeModal.style.display = 'none';
                            welcomeModal.classList.remove('show', 'active');
                        }
                    }
                }
                
                window.updateFarmUI();
            }
        } catch (e) { 
            console.error("خطأ مزامنة المزرعة:", e); 
        } finally { 
            isFetching = false; 
        }
    };

    window.updateFarmUI = function() {
        const pData = window.userState || window.PlayerData || {};
        let bal = getStoredBalance();
        let usdBal = getStoredUsdBalance();
        let hRate = parseFloat(pData.hourly_rate ?? 0.05);

        const balEl = document.getElementById('farm-balance');
        if (balEl) balEl.innerText = `${formatZnBalance(bal)} ZN`;

        const usdEl = document.getElementById('farm-usd-balance');
        if (usdEl) usdEl.innerText = formatUsdBalance(usdBal);

        const rateEl = document.getElementById('farm-rate');
        if (rateEl) {
            let formattedRate = (hRate % 1 === 0) ? hRate.toString() : Number(hRate.toFixed(4)).toString();
            rateEl.innerHTML = `<span dir="ltr">${formattedRate} /h</span> ⚡`;
        }

        const stgLvl = parseInt(pData.storage_level ?? 0, 10);
        const stgLvlEl = document.getElementById('storage-level-num');
        if (stgLvlEl) stgLvlEl.innerText = stgLvl;

        const upgradeStgBtn = document.getElementById('upgrade-storage-btn');
        if (upgradeStgBtn) {
            upgradeStgBtn.onclick = window.handleStorageUpgrade;
            const nextLvl = stgLvl + 1;
            const nextCfg = GAME_CONFIG.storageConfig[nextLvl.toString()];
            if (stgLvl >= 9 || !nextCfg) {
                upgradeStgBtn.innerText = "المخزن في المستوى الأقصى (MAX) 🏆";
                upgradeStgBtn.disabled = true;
                upgradeStgBtn.className = "storage-upgrade-btn btn-disabled";
            } else {
                const costZn = typeof nextCfg === 'object' ? (nextCfg.cost_zn ?? nextCfg.cost ?? 0) : 0;
                const costUsd = typeof nextCfg === 'object' ? (nextCfg.cost_usd ?? 0) : 0;
                
                const costStrZn = formatCompactCost(costZn);
                const costStrUsd = costUsd > 0 ? ` + $${costUsd.toFixed(2)}` : '';
                
                const canAfford = (bal >= costZn) && (usdBal >= costUsd);
                upgradeStgBtn.innerText = `ترقية المخزن Lvl ${nextLvl} (${costStrZn} ZN${costStrUsd}) 📦`;
                upgradeStgBtn.disabled = !canAfford || isUpgradingStorage;
                upgradeStgBtn.className = canAfford ? "storage-upgrade-btn btn-ready-yellow" : "storage-upgrade-btn btn-disabled";
            }
        }

        const fieldsContainer = document.getElementById('mining-fields');
        if (fieldsContainer) {
            const currentUpgrades = pData.upgrades || {};
            let fieldsHTML = '';
            for (let i = 1; i <= 9; i++) {
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
                        <button class="mining-card-btn" ${!canAfford || isUpgrading ? 'disabled' : ''}>ترقية (${costStrZn}${costStrUsd})</button>
                    </div>`;
                } else if (isUnlocked) {
                    fieldsHTML += `
                    <div class="mining-card" onclick="window.handleUpgrade(${i})">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">مستوى ${i}</div>
                        <button class="mining-card-btn" ${!canAfford || isUpgrading ? 'disabled' : ''}>شراء (${costStrZn}${costStrUsd})</button>
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

        const boostBtn = document.getElementById('boost-btn');
        if (boostBtn) {
            const todayStr = getTodayUTCStr();
            const lastBoost = pData.last_boost_date;
            const currentDailyBoostRate = parseFloat(pData.daily_boost_rate || 0);

            if (lastBoost === todayStr) {
                boostBtn.className = "boost-btn btn-disabled";
                boostBtn.disabled = true;
                boostBtn.innerHTML = `<span style="font-size: 12px;">⏳</span><span style="font-size: 8px;">${getTimeUntilUTCMidnight()}</span>`;
            } else {
                if (!isBoosting) {
                    boostBtn.className = "boost-btn";
                    boostBtn.disabled = false;
                    const boostText = (currentDailyBoostRate >= GAME_CONFIG.maxDailyBoostRate) ? `+${GAME_CONFIG.boostMaxRewardCoins} ZN` : `+${GAME_CONFIG.dailyBoostReward}/h`;
                    boostBtn.innerHTML = `<span id="boost-icon">🚀</span><span id="boost-text">${boostText}</span>`; 
                }
            }
        }

        renderDailyRewards(); 
    };

    window.onFarmTabOpen = async function() {
        if (typeof window.fetchPlayerDataFromServer === 'function') {
            await window.fetchPlayerDataFromServer(true);
        } else {
            window.updateFarmUI();
        }
    };

    function getRewardForDayIndex(index) {
        const rewards = GAME_CONFIG.dailyRewards;
        if (!rewards || !Array.isArray(rewards)) return 5;
        return rewards[index] ?? 450;
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
            let displayReward = formatCompactNumber(rawReward);

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

        let maxC = parseFloat(pData.max_cap ?? 30.0);
        let hRate = parseFloat(pData.hourly_rate ?? 0.05);
        
        let lastClaimStr = pData.last_claim_time;
        let lastClaimTimeMs = lastClaimStr ? new Date(lastClaimStr).getTime() : getAdjustedNowMs();
        
        let secondsPassed = Math.max(0, (getAdjustedNowMs() - lastClaimTimeMs) / 1000);
        let unclaim = (hRate / 3600.0) * secondsPassed;

        if (unclaim >= maxC) unclaim = maxC;
        pData.unclaimed = unclaim;

        const progressEl = document.getElementById('storage-progress');
        const storageTextEl = document.getElementById('storage-text');

        if (progressEl && storageTextEl) {
            let pct = maxC > 0 ? (unclaim / maxC) * 100 : 0;
            pct = Math.max(0, Math.min(pct, 100)); 
            progressEl.style.width = `${pct}%`;
            // استخدام formatStorageBalance لتقييد العرض بـ 3 أرقام عشرية فقط
            storageTextEl.innerText = `${formatStorageBalance(unclaim)} / ${maxC.toLocaleString('en-US', {maximumFractionDigits: 2})}`;
        }

        const claimBtn = document.getElementById('claim-btn');
        if (claimBtn) {
            claimBtn.onclick = window.handleMainClaim;
            const remainingCooldown = Math.max(0, Math.ceil(MIN_CLAIM_INTERVAL - secondsPassed));

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

        const timeLeftStr = getTimeUntilUTCMidnight();
        
        const boostBtn = document.getElementById('boost-btn');
        if (boostBtn) {
            boostBtn.onclick = window.handleDailyBoost;
            const lastBoost = pData.last_boost_date;
            const currentDailyBoostRate = parseFloat(pData.daily_boost_rate || 0);

            if (lastBoost === todayStr) {
                boostBtn.className = "boost-btn btn-disabled";
                boostBtn.disabled = true;
                boostBtn.innerHTML = `<span style="font-size: 12px;">⏳</span><span style="font-size: 8px;">${timeLeftStr}</span>`;
            } else {
                if (!isBoosting) {
                    boostBtn.className = "boost-btn";
                    boostBtn.disabled = false;
                    const boostText = (currentDailyBoostRate >= GAME_CONFIG.maxDailyBoostRate) ? `+${GAME_CONFIG.boostMaxRewardCoins} ZN` : `+${GAME_CONFIG.dailyBoostReward}/h`;
                    boostBtn.innerHTML = `<span id="boost-icon">🚀</span><span id="boost-text">${boostText}</span>`; 
                }
            }
        }

        const dailyTimerEl = document.getElementById('daily-timer');
        const lastDailyClaim = pData.last_daily_claim_date;
        if (dailyTimerEl && lastDailyClaim === todayStr) {
            dailyTimerEl.innerText = `⏳ ${timeLeftStr}`;
        }

    }, 1000);

    function syncOnVisibility() {
        if (document.visibilityState === "visible") {
            window.fetchPlayerDataFromServer(true);
        }
    }

    window.addEventListener('pageshow', syncOnVisibility);
    document.addEventListener("visibilitychange", syncOnVisibility);

    function showAdsgramAd() {
        return new Promise((resolve) => {
            const blockId = window.ADSGRAM_BLOCK_ID;
            if (window.Adsgram && blockId) {
                try {
                    const AdController = window.Adsgram.init({ blockId: blockId });
                    AdController.show()
                        .then(() => resolve(true))
                        .catch((err) => {
                            console.warn("Adsgram failure or skipped:", err);
                            resolve(true);
                        });
                } catch (e) {
                    console.error("Adsgram exception:", e);
                    resolve(true);
                }
            } else {
                resolve(true);
            }
        });
    }

    function showTelegramAd() {
        return new Promise((resolve) => {
            if (typeof window.show_11322720 === 'function') {
                try {
                    window.show_11322720()
                        .then(() => resolve(true))
                        .catch((err) => {
                            console.warn("فشل أو تم إغلاق الإعلان:", err);
                            showToast("⚠️ يجب مشاهدة الإعلان حتى النهاية للحصول على المكافأة!");
                            resolve(false);
                        });
                } catch (e) {
                    console.error("استثناء في الإعلانات:", e);
                    showToast("❌ تعذر عرض الإعلان. حاول مرة أخرى.");
                    resolve(false);
                }
            } else {
                showToast("⚠️ الإعلانات غير متوفرة حالياً، يرجى إعادة المحاولة لاحقاً.");
                resolve(false);
            }
        });
    }

    window.handleStorageUpgrade = async function() {
        if (isUpgradingStorage) return;

        isUpgradingStorage = true;
        try {
            let resData = await window.fetchAPI('/api/farm/upgrade_storage', 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance, resData.new_usd_balance);
                
                if (!window.userState) window.userState = {};
                if (!window.PlayerData) window.PlayerData = {};

                if (resData.storage_level !== undefined) {
                    window.userState.storage_level = resData.storage_level;
                    window.PlayerData.storage_level = resData.storage_level;
                }
                if (resData.max_cap !== undefined) {
                    window.userState.max_cap = resData.max_cap;
                    window.PlayerData.max_cap = resData.max_cap;
                }
                if (resData.last_claim_time) {
                    window.userState.last_claim_time = resData.last_claim_time;
                    window.PlayerData.last_claim_time = resData.last_claim_time;
                }
                if (resData.unclaimed !== undefined) {
                    window.userState.unclaimed = resData.unclaimed;
                    window.PlayerData.unclaimed = resData.unclaimed;
                }
                saveCachedData(window.userState);
                showToast(`📦 تم ترقية سعة المخزن بنجاح إلى Level ${resData.storage_level}!`);
                window.updateFarmUI();
            } else {
                showToast(resData?.error || "❌ تعذر ترقية المخزن");
            }
        } catch (e) {
            console.error("خطأ ترقية المخزن:", e);
            showToast("❌ حدث خطأ أثناء ترقية المخزن");
        } finally {
            isUpgradingStorage = false;
        }
    };

    window.handleUpgrade = async function(level) {
        if (isUpgrading) return;

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

        isUpgrading = true;

        try {
            let resData = await window.fetchAPI('/api/farm/upgrade', 'POST', { level: level });
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance, resData.new_usd_balance);
                
                if (!window.userState) window.userState = {};
                if (!window.PlayerData) window.PlayerData = {};

                if (resData.new_hourly_rate !== undefined) {
                    window.userState.hourly_rate = resData.new_hourly_rate;
                    window.PlayerData.hourly_rate = resData.new_hourly_rate;
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
                    window.userState.unclaimed = resData.unclaimed;
                    window.PlayerData.unclaimed = resData.unclaimed;
                }

                saveCachedData(window.userState);
                showToast(`🏛️ تم ترقية المستوى ${level} بنجاح!`);
                window.updateFarmUI();
            } else {
                showToast(resData?.error || "❌ تعذر إتمام الترقية");
            }
        } catch (e) {
            console.error("خطأ الترقية:", e);
            showToast("❌ حدث خطأ أثناء عملية الشراء");
        } finally {
            isUpgrading = false;
        }
    };

    window.handleDailyClaim = async function(dayNum) {
        if (isClaimingDaily) return;
        isClaimingDaily = true;

        try {
            const adWatched = await showTelegramAd();
            if (!adWatched) {
                isClaimingDaily = false;
                return;
            }

            let resData = await window.fetchAPI('/api/farm/daily_claim', 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance, resData.new_usd_balance);
                
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
                window.updateFarmUI();
            } else {
                showToast(resData?.error || "❌ تعذر استلام المكافأة");
            }
        } catch (e) {
            console.error("خطأ استلام المكافأة اليومية:", e);
            showToast("❌ حدث خطأ أثناء استلام المكافأة اليومية");
        } finally {
            isClaimingDaily = false;
        }
    };

    window.handleDailyBoost = async function() {
        if (isBoosting) return;
        isBoosting = true;

        try {
            const adWatched = await showTelegramAd();
            if (!adWatched) {
                isBoosting = false;
                return;
            }

            let resData = await window.fetchAPI('/api/farm/daily_boost', 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance, resData.new_usd_balance);

                if (!window.userState) window.userState = {};
                if (!window.PlayerData) window.PlayerData = {};

                if (resData.type === 'speed') {
                    if (resData.new_rate !== undefined) {
                        window.userState.hourly_rate = resData.new_rate;
                        window.PlayerData.hourly_rate = resData.new_rate;
                    }
                    if (resData.daily_boost_rate !== undefined) {
                        window.userState.daily_boost_rate = resData.daily_boost_rate;
                        window.PlayerData.daily_boost_rate = resData.daily_boost_rate;
                    }
                    if (resData.last_claim_time) {
                        window.userState.last_claim_time = resData.last_claim_time;
                        window.PlayerData.last_claim_time = resData.last_claim_time;
                    }
                    if (resData.unclaimed !== undefined) {
                        window.userState.unclaimed = resData.unclaimed;
                        window.PlayerData.unclaimed = resData.unclaimed;
                    }
                    showToast(`⚡ تم زيادة سرعة التعدين بمقدار +${resData.boost_amount || GAME_CONFIG.dailyBoostReward}/h وحفظ المحصول المعدن!`);
                } else if (resData.type === 'balance') {
                    showToast(`💰 تهانينا! تمت إضافة ${resData.reward_coins || GAME_CONFIG.boostMaxRewardCoins} عملة ZN إلى رصيدك مباشرة!`);
                }

                if (resData.last_boost_date) {
                    window.userState.last_boost_date = resData.last_boost_date;
                    window.PlayerData.last_boost_date = resData.last_boost_date;
                }
                saveCachedData(window.userState);
                window.updateFarmUI();
            } else {
                showToast(resData?.error || "❌ تعذر تفعيل التعزيز");
            }
        } catch (e) {
            console.error("خطأ التعزيز اليومي:", e);
            showToast("❌ حدث خطأ أثناء تفعيل التعزيز");
        } finally {
            isBoosting = false;
        }
    };

    window.handleMainClaim = async function() {
        if (isClaimingMain) return;
        isClaimingMain = true;

        try {
            const pData = window.userState || window.PlayerData || {};
            const todayStr = getTodayUTCStr();
            const uId = tele?.initDataUnsafe?.user?.id || pData.tg_id || pData.telegram_id;
            const storageKey = uId ? `zn_last_claim_ad_${uId}` : 'zn_last_claim_ad_global';
            const lastClaimAdDate = pData.last_claim_ad_date || localStorage.getItem(storageKey);

            if (lastClaimAdDate !== todayStr) {
                await showAdsgramAd();
                pData.last_claim_ad_date = todayStr;
                if (window.userState) window.userState.last_claim_ad_date = todayStr;
                if (window.PlayerData) window.PlayerData.last_claim_ad_date = todayStr;
                localStorage.setItem(storageKey, todayStr);
            }

            let resData = await window.fetchAPI('/api/farm/claim', 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                setStoredBalance(resData.new_balance, resData.new_usd_balance);
                
                if (!window.userState) window.userState = {};
                if (!window.PlayerData) window.PlayerData = {};

                if (resData.last_claim_time) {
                    window.userState.last_claim_time = resData.last_claim_time;
                    window.PlayerData.last_claim_time = resData.last_claim_time;
                }
                window.userState.unclaimed = 0.0;
                window.PlayerData.unclaimed = 0.0;

                saveCachedData(window.userState);
                showToast(`💰 تم تجميع ${formatZnBalance(resData.claimed_amount)} عملة بنجاح!`);
                window.updateFarmUI();
            } else {
                showToast(resData?.error || "❌ تعذر تجميع الرصيد");
            }
        } catch (e) {
            console.error("خطأ التجميع الرئيسي:", e);
            showToast("❌ حدث خطأ أثناء التجميع");
        } finally {
            isClaimingMain = false;
        }
    };

    window.handleClaim = window.handleMainClaim;

})();

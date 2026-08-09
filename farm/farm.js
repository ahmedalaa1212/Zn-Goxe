window.initFarmView = function() {
    if (typeof window.onFarmTabOpen === 'function') {
        window.onFarmTabOpen();
    }
};

(function initFarm() {
    const tele = window.Telegram?.WebApp;
    const START_PARAM = tele?.initDataUnsafe?.start_param || "";

    const GAME_CONFIG = {
        maxUpgradesPerLevel: 10,
        dailyBoostReward: 0.5,
        maxDailyBoostRate: 15.0,
        boostMaxRewardCoins: 50.0,
        upgradeCosts: {
            1: 3500, 2: 11500, 3: 28000, 4: 68000, 5: 165000,
            6: 390000, 7: 950000, 8: 2300000, 9: 5500000
        },
        dailyRewards: [
            100, 150, 200, 250, 300, 350, 400, 450, 500, 550,
            600, 600, 650, 650, 700, 700, 750, 750, 800, 800,
            850, 850, 900, 900, 950, 950, 1000, 1000, 1100, 1250
        ]
    };

    let MIN_CLAIM_INTERVAL = 15;

    let isClaimingDaily = false;
    let isBoosting = false; 
    let isFetching = false;
    let isClaimingMain = false; 
    let isUpgrading = false;

    let lastFetchTime = 0;
    const FETCH_THROTTLE_MS = 10000;
    let lastCheckedDate = "";

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

    function getStoredBalance() {
        if (window.userState && window.userState.balance !== undefined) {
            return parseFloat(window.userState.balance || 0);
        }
        return parseFloat(window.PlayerData?.balance || 0);
    }

    function setStoredBalance(newBalance) {
        if (newBalance !== undefined && newBalance !== null) {
            const val = parseFloat(newBalance);
            if (!window.userState) window.userState = {};
            window.userState.balance = val; 
            if (window.PlayerData) window.PlayerData.balance = val;
            const balEl = document.getElementById('farm-balance');
            if (balEl) balEl.innerText = `${val.toFixed(2)} ZN`;
        }
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
        if (num >= 1000000) return (num / 1000000).toFixed(1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(0) + 'K';
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

                if (!window.PlayerData) window.PlayerData = {};
                Object.assign(window.PlayerData, resData.player);

                if (!window.userState) window.userState = {};
                
                if (resData.player) {
                    if (resData.player.balance !== undefined) setStoredBalance(resData.player.balance);
                    if (resData.player.hourly_rate !== undefined) window.userState.hourly_rate = resData.player.hourly_rate;
                    if (resData.player.daily_boost_rate !== undefined) window.userState.daily_boost_rate = resData.player.daily_boost_rate;
                    if (resData.player.ads_watched !== undefined) window.userState.ads_watched = resData.player.ads_watched;
                    if (resData.player.max_cap !== undefined) window.userState.max_cap = resData.player.max_cap;
                    if (resData.player.extra_storage !== undefined) window.userState.extra_storage = resData.player.extra_storage;
                    if (resData.player.storage_level !== undefined) window.userState.storage_level = resData.player.storage_level;
                    if (resData.player.upgrades !== undefined) window.userState.upgrades = resData.player.upgrades;
                    if (resData.player.last_claim_time !== undefined) window.userState.last_claim_time = resData.player.last_claim_time;
                    if (resData.player.daily_day !== undefined) window.userState.daily_day = resData.player.daily_day;
                    if (resData.player.last_daily_claim_date !== undefined) window.userState.last_daily_claim_date = resData.player.last_daily_claim_date;
                    if (resData.player.last_boost_date !== undefined) window.userState.last_boost_date = resData.player.last_boost_date;
                }
                
                if (resData.game_config) {
                    if (resData.game_config.daily_rewards && Array.isArray(resData.game_config.daily_rewards)) {
                        GAME_CONFIG.dailyRewards = resData.game_config.daily_rewards;
                    }
                    if (resData.game_config.upgrade_costs) {
                        GAME_CONFIG.upgradeCosts = resData.game_config.upgrade_costs;
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
        const pData = window.PlayerData || window.userState || {};
        let bal = getStoredBalance();
        let hRate = parseFloat(window.userState?.hourly_rate || pData.hourly_rate || 0);

        const balEl = document.getElementById('farm-balance');
        if (balEl) balEl.innerText = `${bal.toFixed(2)} ZN`;

        const rateEl = document.getElementById('farm-rate');
        if (rateEl) {
            let formattedRate = (hRate % 1 === 0) ? hRate.toString() : Number(hRate.toFixed(2)).toString();
            rateEl.innerHTML = `<span dir="ltr">${formattedRate} /h</span> ⚡`;
        }
        
        const fieldsContainer = document.getElementById('mining-fields');
        if (fieldsContainer) {
            const currentUpgrades = window.userState?.upgrades || pData.upgrades || {};
            let fieldsHTML = '';
            for (let i = 1; i <= 9; i++) {
                let count = parseInt(currentUpgrades[`lvl${i}`] || 0);
                let prevCount = parseInt(currentUpgrades[`lvl${i-1}`] || 0);
                let isUnlocked = (i === 1) || (prevCount > 0);
                let isMax = count >= GAME_CONFIG.maxUpgradesPerLevel;
                let cost = GAME_CONFIG.upgradeCosts[i] || 0;
                let costStr = formatCompactCost(cost);
                let canAfford = bal >= cost;
                
                if (isMax) {
                    fieldsHTML += `
                    <div class="mining-card">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">مستوى ${i}</div>
                        <button class="mining-card-btn" disabled>MAX</button>
                    </div>`;
                } else if (count > 0) {
                    fieldsHTML += `
                    <div class="mining-card" onclick="window.handleUpgrade(${i})">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">مستوى ${i} (x${count})</div>
                        <button class="mining-card-btn" ${!canAfford || isUpgrading ? 'disabled' : ''}>ترقية (${costStr})</button>
                    </div>`;
                } else if (isUnlocked) {
                    fieldsHTML += `
                    <div class="mining-card" onclick="window.handleUpgrade(${i})">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">مستوى ${i}</div>
                        <button class="mining-card-btn" ${!canAfford || isUpgrading ? 'disabled' : ''}>شراء (${costStr})</button>
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
        renderDailyRewards(); 
    };

    window.onFarmTabOpen = function() {
        window.updateFarmUI();
        if (typeof window.fetchPlayerDataFromServer === 'function') {
            window.fetchPlayerDataFromServer();
        }
    };

    function getRewardForDayIndex(index) {
        const rewards = GAME_CONFIG.dailyRewards;
        if (!rewards || !Array.isArray(rewards)) return 100;
        return rewards[index] ?? 1250;
    }

    function renderDailyRewards() {
        const container = document.getElementById('daily-rewards-container');
        const pData = window.PlayerData || window.userState || {};
        if (!container) return; 

        let html = '';
        const todayStr = getTodayUTCStr();
        const lastClaimDate = pData.last_daily_claim_date || window.userState?.last_daily_claim_date;
        const claimedToday = (lastClaimDate === todayStr); 
        let currentDailyDay = parseInt(pData.daily_day || window.userState?.daily_day || 1, 10);
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

    if (window.farmIntervalId) clearInterval(window.farmIntervalId);
    window.farmIntervalId = setInterval(() => {
        const pData = window.PlayerData || window.userState;
        if (!pData) return;
        
        const todayStr = getTodayUTCStr();

        if (lastCheckedDate && lastCheckedDate !== todayStr) {
            lastCheckedDate = todayStr;
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                window.fetchPlayerDataFromServer(true);
            }
        }
        lastCheckedDate = todayStr;

        let maxC = parseFloat(window.userState?.max_cap ?? pData.max_cap ?? 100);
        let hRate = parseFloat(window.userState?.hourly_rate ?? pData.hourly_rate ?? 0);
        
        let lastClaimStr = window.userState?.last_claim_time || pData.last_claim_time;
        let lastClaimTimeMs = lastClaimStr ? new Date(lastClaimStr).getTime() : getAdjustedNowMs();
        
        let secondsPassed = Math.max(0, (getAdjustedNowMs() - lastClaimTimeMs) / 1000);
        let unclaim = (hRate / 3600.0) * secondsPassed;

        if (unclaim >= maxC) unclaim = maxC;
        if (window.PlayerData) window.PlayerData.unclaimed = unclaim;
        if (window.userState) window.userState.unclaimed = unclaim;

        const progressEl = document.getElementById('storage-progress');
        const storageTextEl = document.getElementById('storage-text');

        if (progressEl && storageTextEl) {
            let pct = maxC > 0 ? (unclaim / maxC) * 100 : 0;
            pct = Math.max(0, Math.min(pct, 100)); 
            progressEl.style.width = `${pct}%`;
            storageTextEl.innerText = `${unclaim.toFixed(2)} / ${maxC.toLocaleString('en-US', {maximumFractionDigits: 2})}`;
        }

        const claimBtn = document.getElementById('claim-btn');
        if (claimBtn) {
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
            const lastBoost = pData.last_boost_date || window.userState?.last_boost_date;
            const currentDailyBoostRate = parseFloat(pData.daily_boost_rate || window.userState?.daily_boost_rate || 0);

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
        const lastDailyClaim = pData.last_daily_claim_date || window.userState?.last_daily_claim_date;
        if (dailyTimerEl && lastDailyClaim === todayStr) {
            dailyTimerEl.innerText = `⏳ ${timeLeftStr}`;
        }

    }, 1000);

    function syncOnVisibility() {
        if (document.visibilityState === "visible") {
            window.updateFarmUI();
            window.fetchPlayerDataFromServer();
        }
    }

    window.addEventListener('pageshow', syncOnVisibility);
    document.addEventListener("visibilitychange", syncOnVisibility);

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

    window.handleUpgrade = async function(level) {
        if (isUpgrading) return;

        const cost = GAME_CONFIG.upgradeCosts[level] || 0;
        const currentBal = getStoredBalance();
        if (currentBal < cost) {
            showToast(`❌ رصيدك غير كافٍ! سعر الترقية ${cost.toLocaleString()} ZN`);
            return;
        }

        isUpgrading = true;

        try {
            let resData = await window.fetchAPI('/api/farm/upgrade', 'POST', { level: level });
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                if (resData.new_balance !== undefined) setStoredBalance(resData.new_balance);
                if (resData.new_hourly_rate !== undefined) {
                    if (!window.userState) window.userState = {};
                    window.userState.hourly_rate = resData.new_hourly_rate;
                }
                if (resData.upgrades) {
                    if (!window.userState) window.userState = {};
                    window.userState.upgrades = resData.upgrades;
                }
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
                if (resData.new_balance !== undefined) setStoredBalance(resData.new_balance);
                if (resData.daily_day !== undefined) {
                    if (!window.userState) window.userState = {};
                    window.userState.daily_day = resData.daily_day;
                }
                if (resData.last_daily_claim_date) {
                    if (!window.userState) window.userState = {};
                    window.userState.last_daily_claim_date = resData.last_daily_claim_date;
                }
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
                
                if (resData.new_balance !== undefined) setStoredBalance(resData.new_balance);

                if (resData.type === 'speed') {
                    if (resData.new_rate !== undefined) {
                        if (!window.userState) window.userState = {};
                        window.userState.hourly_rate = resData.new_rate;
                    }
                    if (resData.daily_boost_rate !== undefined) {
                        if (!window.userState) window.userState = {};
                        window.userState.daily_boost_rate = resData.daily_boost_rate;
                    }
                    if (resData.last_claim_time) {
                        if (!window.userState) window.userState = {};
                        window.userState.last_claim_time = resData.last_claim_time;
                        window.userState.unclaimed = 0.0;
                    }
                    showToast(`⚡ تم زيادة سرعة التعدين بمقدار +${resData.boost_amount || GAME_CONFIG.dailyBoostReward}/h وحفظ المحصول المعدن!`);
                } else if (resData.type === 'balance') {
                    showToast(`💰 تهانينا! تمت إضافة ${resData.reward_coins || GAME_CONFIG.boostMaxRewardCoins} عملة ZN إلى رصيدك مباشرة!`);
                }

                if (resData.last_boost_date) {
                    if (!window.userState) window.userState = {};
                    window.userState.last_boost_date = resData.last_boost_date;
                }
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
            let resData = await window.fetchAPI('/api/farm/claim', 'POST', {});
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                if (resData.new_balance !== undefined) setStoredBalance(resData.new_balance);
                if (resData.last_claim_time) {
                    if (!window.userState) window.userState = {};
                    window.userState.last_claim_time = resData.last_claim_time;
                    window.userState.unclaimed = 0.0;
                }
                showToast(`💰 تم تجميع ${resData.claimed_amount} عملة بنجاح!`);
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

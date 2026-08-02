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
        dailyBoostReward: 2.0,
        upgradeCosts: {
            1: 2000, 2: 7000, 3: 18000, 4: 45000, 5: 110000,
            6: 260000, 7: 600000, 8: 1400000, 9: 3200000
        },
        dailyRewards: [
            100, 150, 200, 250, 300, 350, 400, 450, 500, 550, 
            600, 600, 650, 650, 700, 700, 750, 750, 800, 800, 
            850, 850, 900, 900, 950, 950, 1000, 1000, 1100, 1250
        ]
    };

    const MIN_CLAIM_INTERVAL = 15;
    let serverTimeOffset = 0;

    let isClaimingDaily = false;
    let isBoosting = false; 
    let isFetching = false;
    let isClaimingMain = false; 
    let isUpgrading = false;

    let lastFetchTime = 0;
    const FETCH_THROTTLE_MS = 10000;

    function showToast(message) {
        if (tele && tele.showAlert) tele.showAlert(message);
        else alert(message);
    }

    function getAdjustedNowMs() {
        return Date.now() - serverTimeOffset;
    }

    function syncServerTime(serverTimeStr) {
        if (!serverTimeStr) return;
        try {
            const serverMs = new Date(serverTimeStr).getTime();
            if (!isNaN(serverMs)) {
                serverTimeOffset = Date.now() - serverMs;
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
        
        let seconds = Math.floor(diff / 1000);
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

                window.PlayerData = resData.player;
                if (!window.userState) window.userState = {};
                
                if (resData.player) {
                    if (resData.player.balance !== undefined) setStoredBalance(resData.player.balance);
                    if (resData.player.hourly_rate !== undefined) window.userState.hourly_rate = resData.player.hourly_rate;
                    if (resData.player.max_cap !== undefined) window.userState.max_cap = resData.player.max_cap;
                    if (resData.player.storage_level !== undefined) window.userState.storage_level = resData.player.storage_level;
                    if (resData.player.upgrades !== undefined) window.userState.upgrades = resData.player.upgrades;
                    if (resData.player.last_claim_time !== undefined) window.userState.last_claim_time = resData.player.last_claim_time;
                }
                
                if (resData.game_config) {
                    if (resData.game_config.daily_rewards) {
                        GAME_CONFIG.dailyRewards = resData.game_config.daily_rewards;
                    }
                    if (resData.game_config.upgrade_costs) {
                        GAME_CONFIG.upgradeCosts = resData.game_config.upgrade_costs;
                    }
                    if (resData.game_config.daily_boost_reward) {
                        GAME_CONFIG.dailyBoostReward = resData.game_config.daily_boost_reward;
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
        const pData = window.PlayerData || {};
        let bal = getStoredBalance();
        let hRate = parseFloat(window.userState?.hourly_rate || pData.hourly_rate || 0);
        
        const balEl = document.getElementById('farm-balance');
        if (balEl) {
            balEl.innerHTML = `<span dir="ltr">${bal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} ZN</span>`;
        }

        const rateEl = document.getElementById('farm-rate');
        if (rateEl) {
            rateEl.innerHTML = `<span dir="ltr">${Math.floor(hRate).toLocaleString()} /h</span> ⚡`;
        }
        
        const fieldsContainer = document.getElementById('mining-fields');
        if (fieldsContainer) {
            const currentUpgrades = window.userState?.upgrades || pData.upgrades || {};
            let fieldsHTML = '';
            for (let i = 1; i <= 9; i++) {
                let count = parseInt(currentUpgrades[`lvl${i}`] || 0);
                let isUnlocked = (i === 1) || (parseInt(currentUpgrades[`lvl${i-1}`] || 0) > 0);
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
                    <div class="mining-card" onclick="handleUpgrade(${i})">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">مستوى ${i} (x${count})</div>
                        <button class="mining-card-btn" ${!canAfford ? 'disabled' : ''}>ترقية (${costStr})</button>
                    </div>`;
                } else if (isUnlocked) {
                    fieldsHTML += `
                    <div class="mining-card" onclick="handleUpgrade(${i})">
                        <div class="mining-card-icon">🏛️</div>
                        <div class="mining-card-title">مستوى ${i}</div>
                        <button class="mining-card-btn" ${!canAfford ? 'disabled' : ''}>شراء (${costStr})</button>
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

    function formatCompactNumber(num) {
        if (num >= 1000000) return (num / 1000000).toFixed(0) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(0) + 'K';
        return num.toString();
    }

    function getRewardForDayIndex(index) {
        const rewards = GAME_CONFIG.dailyRewards;
        if (!rewards) return 100;
        return Array.isArray(rewards) ? (rewards[index] ?? 1250) : 1250;
    }

    function renderDailyRewards() {
        const container = document.getElementById('daily-rewards-container');
        const pData = window.PlayerData;
        if (!container || !pData) return; 

        let html = '';
        const todayStr = getTodayUTCStr();
        const canClaim = pData.last_daily_claim_date !== todayStr; 
        const currentDailyDay = parseInt(pData.daily_day || 1);
        const activeDayIndex = Math.min(currentDailyDay, 30);

        for (let i = 0; i < 30; i++) {
            let dayNum = i + 1;
            let rawReward = getRewardForDayIndex(i);
            let displayReward = formatCompactNumber(rawReward);

            if (dayNum < activeDayIndex) {
                html += `<div class="reward-day-card claimed"><div class="day-title">يوم ${dayNum}</div><div>✓</div></div>`;
            } else if (dayNum === activeDayIndex) {
                if (canClaim) {
                    html += `<div class="reward-day-card active"><div class="day-title">يوم ${dayNum}</div><div class="day-amount">${displayReward}</div><button id="daily-btn-${dayNum}" onclick="handleDailyClaim(${currentDailyDay})" style="background: #10b981; color: white; border: none; border-radius: 4px; padding: 2px 0; font-size: 9px; width: 100%;">استلام</button></div>`;
                } else {
                    html += `<div class="reward-day-card"><div class="day-title">يوم ${dayNum}</div><div class="day-amount">${displayReward}</div><div id="daily-timer" style="color: #ef4444; font-size: 8px;">⏳</div></div>`;
                }
            } else {
                html += `<div class="reward-day-card" style="opacity: 0.4;"><div class="day-title">يوم ${dayNum}</div><div class="day-amount">${displayReward}</div></div>`;
            }
        }
        container.innerHTML = html;
    }

    if (window.farmIntervalId) clearInterval(window.farmIntervalId);
    window.farmIntervalId = setInterval(() => {
        const pData = window.PlayerData;
        if (!pData) return;
        
        let maxC = parseFloat(window.userState?.max_cap || pData.max_cap || 200);
        let hRate = parseFloat(window.userState?.hourly_rate || pData.hourly_rate || 0);
        
        let lastClaimStr = window.userState?.last_claim_time || pData.last_claim_time;
        let lastClaimTimeMs = lastClaimStr ? new Date(lastClaimStr).getTime() : getAdjustedNowMs();
        
        let secondsPassed = Math.max(0, (getAdjustedNowMs() - lastClaimTimeMs) / 1000);
        let unclaim = (hRate / 3600.0) * secondsPassed;

        if (unclaim >= maxC) unclaim = maxC;
        pData.unclaimed = unclaim;

        const progressEl = document.getElementById('storage-progress');
        const storageTextEl = document.getElementById('storage-text');

        if (progressEl && storageTextEl) {
            let pct = (unclaim / maxC) * 100;
            pct = Math.max(0, Math.min(pct, 100)); 
            progressEl.style.width = `${pct}%`;
            storageTextEl.innerText = `${unclaim.toFixed(2)} / ${maxC.toLocaleString()}`;
        }

        const claimBtn = document.getElementById('claim-btn');
        if (claimBtn) {
            const remainingCooldown = Math.max(0, Math.ceil(MIN_CLAIM_INTERVAL - secondsPassed));

            if (isClaimingMain) {
                claimBtn.innerText = "جاري الحفظ... 💾";
                claimBtn.className = "claim-action-btn btn-disabled";
                claimBtn.disabled = true;
            } else if (remainingCooldown > 0) {
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

        const todayStr = getTodayUTCStr();
        const timeLeftStr = getTimeUntilUTCMidnight();
        
        const boostBtn = document.getElementById('boost-btn');
        if (boostBtn) {
            if (pData.last_boost_date === todayStr) {
                boostBtn.className = "boost-btn btn-disabled";
                boostBtn.disabled = true;
                boostBtn.innerHTML = `<span style="font-size: 12px;">⏳</span><span style="font-size: 8px;">${timeLeftStr}</span>`;
            } else {
                if (!isBoosting) {
                    boostBtn.className = "boost-btn";
                    boostBtn.disabled = false;
                    boostBtn.innerHTML = `<span id="boost-icon">🚀</span><span id="boost-text">+${GAME_CONFIG.dailyBoostReward}/h</span>`; 
                }
            }
        }

        const dailyTimerEl = document.getElementById('daily-timer');
        if (dailyTimerEl && pData.last_daily_claim_date === todayStr) {
            dailyTimerEl.innerText = timeLeftStr;
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

    function showTelegramAd(statusCallback) {
        return new Promise((resolve) => {
            if (typeof window.show_11322720 === 'function') {
                if (statusCallback) statusCallback();
                window.show_11322720().then(() => resolve(true)).catch(() => resolve(false));
            } else {
                showToast("⚠️ لم يتم تحميل الإعلان بعد.");
                resolve(false);
            }
        });
    }

    window.handleUpgrade = async function(level) {
        if (!window.PlayerData || isUpgrading) return;

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
                    if (window.PlayerData) window.PlayerData.hourly_rate = resData.new_hourly_rate;
                }
                if (resData.upgrades) {
                    if (!window.PlayerData) window.PlayerData = {};
                    window.PlayerData.upgrades = resData.upgrades;
                    if (!window.userState) window.userState = {};
                    window.userState.upgrades = resData.upgrades;
                }
                window.updateFarmUI();
                showToast(`⚡ تم التحديث للمستوى ${level}!`);
            }
        } catch (e) {
            console.error("خطأ الترقية:", e);
            showToast(e.message || "حدث خطأ أثناء الترقية.");
        } finally {
            isUpgrading = false;
        }
    };

    window.handleDailyBoost = async function() {
        if (!window.PlayerData || isBoosting) return;
        
        const pData = window.PlayerData;
        const todayStr = getTodayUTCStr();
        if (pData.last_boost_date === todayStr) return;

        const btn = document.getElementById('boost-btn');
        isBoosting = true;
        
        try {
            const adWatched = await showTelegramAd(() => {
                if (btn) { btn.innerHTML = `⏳`; btn.disabled = true; }
            });
            
            if (adWatched) {
                if (btn) btn.innerHTML = `💾`;
                let resData = await window.fetchAPI('/api/farm/daily_boost', 'POST');
                if (resData && resData.success) {
                    if (resData.server_time) syncServerTime(resData.server_time);
                    if (resData.new_rate !== undefined) {
                        pData.hourly_rate = resData.new_rate;
                        if (!window.userState) window.userState = {};
                        window.userState.hourly_rate = resData.new_rate;
                    }
                    if (resData.last_boost_date) pData.last_boost_date = resData.last_boost_date;
                    window.updateFarmUI();
                    showToast(`🚀 تمت زيادة معدل التعدين!`);
                }
            } else {
                window.updateFarmUI();
            }
        } catch (e) {
            console.error("خطأ تسريع التعدين:", e);
            showToast(e.message || "فشل التسريع.");
            window.updateFarmUI();
        } finally {
            isBoosting = false;
        }
    };

    window.handleDailyClaim = async function(day) {
        if (!window.PlayerData || isClaimingDaily) return;
        
        const pData = window.PlayerData;
        const todayStr = getTodayUTCStr();
        if (pData.last_daily_claim_date === todayStr) return;

        const btn = document.getElementById(`daily-btn-${Math.min(day, 30)}`);
        isClaimingDaily = true;
        
        try {
            const adWatched = await showTelegramAd(() => {
                if (btn) { btn.innerHTML = "⏳"; btn.disabled = true; }
            });
            
            if (adWatched) {
                if (btn) btn.innerHTML = "💾";
                let resData = await window.fetchAPI('/api/farm/daily_claim', 'POST');
                if (resData && resData.success) {
                    if (resData.server_time) syncServerTime(resData.server_time);
                    if (resData.new_balance !== undefined) setStoredBalance(resData.new_balance);
                    if (resData.daily_day !== undefined) pData.daily_day = resData.daily_day;
                    if (resData.last_daily_claim_date) pData.last_daily_claim_date = resData.last_daily_claim_date;
                    window.updateFarmUI();
                    showToast(`🎉 تم الاستلام!`);
                }
            } else {
                if (btn) { btn.innerHTML = "استلام"; btn.disabled = false; }
            }
        } catch (e) {
            console.error("خطأ المكافأة اليومية:", e);
            showToast(e.message || "فشل استلام المكافأة.");
            if (btn) { btn.innerHTML = "استلام"; btn.disabled = false; }
        } finally {
            isClaimingDaily = false;
        }
    };

    window.handleClaim = async function() {
        const pData = window.PlayerData;
        if (!pData || isClaimingMain) return;

        let lastClaimStr = window.userState?.last_claim_time || pData.last_claim_time;
        let lastClaimTimeMs = lastClaimStr ? new Date(lastClaimStr).getTime() : getAdjustedNowMs();
        let secondsPassed = Math.max(0, (getAdjustedNowMs() - lastClaimTimeMs) / 1000);

        if (secondsPassed < MIN_CLAIM_INTERVAL) {
            showToast(`⚠️ يجب الانتظار قبل التجميع مجدداً.`);
            return;
        }

        if (parseFloat(pData.unclaimed || 0) <= 0) return;

        isClaimingMain = true;
        const claimBtn = document.getElementById('claim-btn');
        if (claimBtn) {
            claimBtn.disabled = true;
            claimBtn.className = "claim-action-btn btn-disabled";
            claimBtn.innerText = "جاري الحفظ... 💾";
        }

        const unclaimedAmount = parseFloat(pData.unclaimed || 0);
        const currentBal = getStoredBalance();
        const optimisticNewBal = currentBal + unclaimedAmount;
        
        setStoredBalance(optimisticNewBal);
        pData.unclaimed = 0;
        
        const nowISO = new Date(getAdjustedNowMs()).toISOString();
        pData.last_claim_time = nowISO;
        if (!window.userState) window.userState = {};
        window.userState.last_claim_time = nowISO;
        
        window.updateFarmUI();

        try {
            let resData = await window.fetchAPI('/api/farm/claim', 'POST');
            if (resData && resData.success) {
                if (resData.server_time) syncServerTime(resData.server_time);
                if (resData.new_balance !== undefined) setStoredBalance(resData.new_balance);
                if (resData.last_claim_time) {
                    pData.last_claim_time = resData.last_claim_time;
                    window.userState.last_claim_time = resData.last_claim_time;
                }
                pData.unclaimed = 0;
            } else if (resData && resData.error) {
                showToast(resData.error);
            }
        } catch (e) {
            setStoredBalance(currentBal);
            showToast(e.message || "حدث خطأ في عملية التجميع");
        } finally {
            isClaimingMain = false;
            window.updateFarmUI();
        }
    };

    window.updateFarmUI();
    window.fetchPlayerDataFromServer(true);
})();

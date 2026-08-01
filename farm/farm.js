(function initFarm() {
    const tele = window.Telegram?.WebApp;
    const INIT_DATA = tele?.initData || "";
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

    let claimCooldown = 0; 
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
            window.userState.balance = val; // يقدّم تحديثاً سلسًا للرصيد عبر الـ Proxy
            if (window.PlayerData) window.PlayerData.balance = val;
        }
    }

    function getTodayUTCStr() {
        return new Date().toISOString().split('T')[0];
    }
    
    function getTimeUntilUTCMidnight() {
        const now = new Date();
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
                window.PlayerData = resData.player;
                if (!window.userState) window.userState = {};
                
                if (resData.player && resData.player.balance !== undefined) {
                    setStoredBalance(resData.player.balance);
                }
                if (resData.player && resData.player.hourly_rate !== undefined) {
                    window.userState.hourly_rate = resData.player.hourly_rate;
                }
                if (resData.player && resData.player.max_cap !== undefined) {
                    window.userState.max_cap = resData.player.max_cap;
                }
                if (resData.player && resData.player.storage_level !== undefined) {
                    window.userState.storage_level = resData.player.storage_level;
                }
                if (resData.player && resData.player.upgrades !== undefined) {
                    window.userState.upgrades = resData.player.upgrades;
                }
                
                // تحديث الإعدادات الديناميكية القادمة من السيرفر
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
            console.error("خطأ في مزامنة بيانات المزرعة:", e); 
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
            if (typeof window.formatNumberHTML === 'function') {
                balEl.innerHTML = `ZN: ${window.formatNumberHTML(bal, 0, 2)}`;
            } else {
                balEl.innerText = `ZN: ${bal.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 2})}`;
            }
        }

        const rateEl = document.getElementById('farm-rate');
        if (rateEl) rateEl.innerText = `⚡ ${Math.floor(hRate).toLocaleString()}/h`; 
        
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
                let btnStyle = canAfford ? "" : "background: #555; opacity: 0.8;";
                
                if (isMax) {
                    fieldsHTML += `<div class="mining-card" style="position: relative; overflow: hidden; opacity: 0.8;"><div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #f39c12; font-size: 14px; transform: rotate(-15deg); z-index: 2;">MAX</div><div style="font-size: 22px; margin-bottom: 4px; opacity: 0.3;">🏛️</div><div class="mining-card-title">مستوى ${i}</div><div class="mining-card-level">مكتمل</div></div>`;
                } else if (count > 0) {
                    fieldsHTML += `<div class="mining-card" onclick="handleUpgrade(${i})" style="cursor: pointer; border-color: #f39c12; position: relative;"><div style="position: absolute; top: -6px; right: -6px; background: #f39c12; color: #000; font-weight: bold; border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; font-size: 10px; border: 2px solid #121212;">x${count}</div><div style="width: 28px; height: 28px; background: #f39c12; border-radius: 50%; margin: 0 auto 5px auto; display: flex; align-items: center; justify-content: center;"><span style="font-size: 14px;">🏛️</span></div><div class="mining-card-title">مستوى ${i}</div><button class="mining-card-btn" style="${btnStyle}">ترقية (${costStr}) ⚡</button></div>`;
                } else if (isUnlocked) {
                    fieldsHTML += `<div class="mining-card" onclick="handleUpgrade(${i})" style="cursor: pointer; border: 1px dashed #555;"><div style="font-size: 20px; color: #777; margin-bottom: 4px;">🏛️</div><div class="mining-card-title">مستوى ${i}</div><button class="mining-card-btn" style="${btnStyle}">شراء (${costStr}) ⚡</button></div>`;
                } else {
                    fieldsHTML += `<div class="mining-card" style="opacity: 0.4; cursor: not-allowed;"><div style="font-size: 20px; color: #555; margin-bottom: 4px;">🔒</div><div class="mining-card-title">مستوى ${i}</div><div class="mining-card-level" style="color:#666;">مغلق</div></div>`;
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
        if (num >= 1000000) return (num / 1000000).toFixed(num % 1000000 === 0 ? 0 : 1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(num % 1000 === 0 ? 0 : 1) + 'K';
        return num.toString();
    }

    function getRewardForDayIndex(index) {
        const rewards = GAME_CONFIG.dailyRewards;
        if (!rewards) return 100;
        if (Array.isArray(rewards)) {
            return rewards[index] !== undefined ? rewards[index] : 1250;
        }
        return 1250;
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
                html += `<div class="reward-day-card claimed"><div class="day-title">يوم ${dayNum}</div><div style="font-size: 12px;">✔️</div><div style="font-size: 9px; font-weight: bold;">تم</div></div>`;
            } else if (dayNum === activeDayIndex) {
                if (canClaim) {
                    html += `<div class="reward-day-card active"><div class="day-title">يوم ${dayNum}${currentDailyDay > 30 ? '+' : ''}</div><div class="day-amount">${displayReward} ZN</div><button id="daily-btn-${dayNum}" onclick="handleDailyClaim(${currentDailyDay})" style="background: #2ecc71; color: white; border: none; border-radius: 4px; padding: 4px 0; font-size: 10px; cursor: pointer; width: 90%; animation: pulseGreen 2s infinite;">📺 استلام</button></div>`;
                } else {
                    html += `<div class="reward-day-card" style="border-color: #555;"><div class="day-title">يوم ${dayNum}${currentDailyDay > 30 ? '+' : ''}</div><div class="day-amount">${displayReward} ZN</div><div id="daily-timer" style="color: #e74c3c; font-size: 9px; font-weight: bold;">⏳</div></div>`;
                }
            } else {
                html += `<div class="reward-day-card" style="opacity: 0.5;"><div class="day-title">يوم ${dayNum}</div><div style="font-size: 12px; color: #555;">🔒</div><div class="day-amount">${displayReward}</div></div>`;
            }
        }
        container.innerHTML = html;
    }

    // العداد المحلي السلس المحسوب بناءً على Timestamp لتجنب أي استهلاك لـ Firebase
    if (window.farmIntervalId) clearInterval(window.farmIntervalId);
    window.farmIntervalId = setInterval(() => {
        const pData = window.PlayerData;
        if (!pData) return;
        
        let maxC = parseFloat(window.userState?.max_cap || pData.max_cap || 200);
        let hRate = parseFloat(window.userState?.hourly_rate || pData.hourly_rate || 0);
        
        // حساب الفارق الزمني من آخر تجميع للحصول على قيمة غير مجمعة دقيقة 100% محلياً
        let lastClaimTimeMs = pData.last_claim_time ? new Date(pData.last_claim_time).getTime() : Date.now();
        let secondsPassed = Math.max(0, (Date.now() - lastClaimTimeMs) / 1000);
        let unclaim = (hRate / 3600.0) * secondsPassed;

        if (unclaim >= maxC) unclaim = maxC;
        pData.unclaimed = unclaim;

        const progressEl = document.getElementById('storage-progress');
        const storageTextEl = document.getElementById('storage-text');
        if (progressEl && storageTextEl) {
            let pct = (unclaim / maxC) * 100;
            pct = Math.max(0, Math.min(pct, 100)); 
            progressEl.style.width = `${pct}%`;
            if (pct >= 100) progressEl.style.background = 'linear-gradient(90deg, #e74c3c, #c0392b)'; 
            else progressEl.style.background = 'linear-gradient(90deg, #f39c12, #f1c40f)';
            
            storageTextEl.innerText = `${Math.floor(unclaim).toLocaleString()} / ${maxC.toLocaleString()}`;
        }

        const claimBtn = document.getElementById('claim-btn');
        if (claimBtn) {
            if (claimCooldown > 0) {
                claimCooldown--;
                claimBtn.innerText = `انتظر ${claimCooldown} ثانية ⏳`;
                claimBtn.className = "btn-cooldown";
                claimBtn.disabled = true;
            } else if (!isClaimingMain) {
                claimBtn.innerText = "تجميع الرصيد 💰";
                if (unclaim > 0) {
                    claimBtn.className = "btn-ready";
                    claimBtn.disabled = false;
                } else {
                    claimBtn.className = "btn-cooldown";
                    claimBtn.disabled = true;
                }
            }
        }

        const todayStr = getTodayUTCStr();
        const timeLeftStr = getTimeUntilUTCMidnight();
        
        const boostBtn = document.getElementById('boost-btn');
        if (boostBtn) {
            if (pData.last_boost_date === todayStr) {
                boostBtn.className = "btn-cooldown";
                boostBtn.disabled = true;
                boostBtn.innerHTML = `<span style="font-size: 16px; margin-bottom:2px;">⏳</span><span class="timer-text">${timeLeftStr}</span>`;
            } else {
                if (!isBoosting) {
                    boostBtn.className = "";
                    boostBtn.disabled = false;
                    boostBtn.style.background = "linear-gradient(135deg, #f39c12, #e67e22)";
                    boostBtn.style.boxShadow = "0 4px 12px rgba(243, 156, 18, 0.4)";
                    boostBtn.innerHTML = `<span style="font-size: 20px; margin-bottom: 2px;">🚀</span><span style="font-size: 10px; font-weight: bold;">+${GAME_CONFIG.dailyBoostReward}/h</span>`; 
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
                showToast("⚠️ لم يتم تحميل الإعلان بعد. حاول مجدداً بعد ثوانٍ.");
                resolve(false);
            }
        });
    }

    window.handleUpgrade = async function(level) {
        if (!window.PlayerData || isUpgrading) return;

        const cost = GAME_CONFIG.upgradeCosts[level] || 0;
        const currentBal = getStoredBalance();
        if (currentBal < cost) {
            showToast(`❌ رصيدك غير كافٍ! سعر الترقية ${cost.toLocaleString()} ZN (رصيدك الحالي: ${Math.floor(currentBal).toLocaleString()} ZN)`);
            return;
        }

        isUpgrading = true;

        try {
            let resData = await window.fetchAPI('/api/farm/upgrade', 'POST', { level: level });
            if (resData && resData.success) {
                if (resData.new_balance !== undefined) {
                    setStoredBalance(resData.new_balance);
                }
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
                showToast(`⚡ تم التحديث بنجاح للمستوى ${level}!`);
            }
        } catch (e) {
            console.error("خطأ في شراء الترقية:", e);
            showToast(e.message || "حدث خطأ أثناء الاتصال بالخادم.");
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
                if (btn) {
                    btn.innerHTML = `<span style="font-size: 18px;">⏳</span>`;
                    btn.disabled = true;
                }
            });
            
            if (adWatched) {
                if (btn) btn.innerHTML = `<span style="font-size: 18px;">💾</span>`;
                let resData = await window.fetchAPI('/api/farm/daily_boost', 'POST');
                if (resData && resData.success) {
                    if (resData.new_rate !== undefined) {
                        pData.hourly_rate = resData.new_rate;
                        if (!window.userState) window.userState = {};
                        window.userState.hourly_rate = resData.new_rate;
                    }
                    if (resData.last_boost_date) {
                        pData.last_boost_date = resData.last_boost_date;
                    }
                    window.updateFarmUI();
                    showToast(`🚀 تمت زيادة معدل التعدين بنجاح بمقدار +${resData.added_rate || GAME_CONFIG.dailyBoostReward}/h دائماً!`);
                }
            } else {
                window.updateFarmUI();
            }
        } catch (e) {
            console.error("خطأ تسريع التعدين:", e);
            showToast(e.message || "فشل تفعيل التسريع.");
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
                if (btn) {
                    btn.innerHTML = "⏳";
                    btn.disabled = true;
                }
            });
            
            if (adWatched) {
                if (btn) btn.innerHTML = "💾";
                let resData = await window.fetchAPI('/api/farm/daily_claim', 'POST');
                if (resData && resData.success) {
                    if (resData.new_balance !== undefined) {
                        setStoredBalance(resData.new_balance);
                    }
                    if (resData.daily_day !== undefined) {
                        pData.daily_day = resData.daily_day;
                    }
                    if (resData.last_daily_claim_date) {
                        pData.last_daily_claim_date = resData.last_daily_claim_date;
                    }
                    window.updateFarmUI();
                    showToast(`🎉 استلمت ${resData.reward.toLocaleString()} ZN!`);
                }
            } else {
                if (btn) {
                    btn.innerHTML = "📺 استلام";
                    btn.disabled = false;
                }
            }
        } catch (e) {
            console.error("خطأ المكافأة اليومية:", e);
            showToast(e.message || "فشل استلام المكافأة اليومية.");
            if (btn) {
                btn.innerHTML = "📺 استلام";
                btn.disabled = false;
            }
        } finally {
            isClaimingDaily = false;
        }
    };

    window.handleClaim = async function() {
        const pData = window.PlayerData;
        if (!pData || parseFloat(pData.unclaimed || 0) <= 0 || claimCooldown > 0 || isClaimingMain) return;

        isClaimingMain = true;
        const claimBtn = document.getElementById('claim-btn');
        if (claimBtn) {
            claimBtn.disabled = true;
            claimBtn.className = "btn-cooldown";
            claimBtn.innerText = "جاري الحفظ... 💾";
        }

        const unclaimedAmount = parseFloat(pData.unclaimed || 0);
        const currentBal = getStoredBalance();
        const optimisticNewBal = currentBal + unclaimedAmount;
        
        setStoredBalance(optimisticNewBal);
        pData.unclaimed = 0;
        pData.last_claim_time = new Date().toISOString();
        window.updateFarmUI();

        try {
            let resData = await window.fetchAPI('/api/farm/claim', 'POST');
            if (resData && resData.success) {
                if (resData.new_balance !== undefined) {
                    setStoredBalance(resData.new_balance);
                }
                if (resData.last_claim_time) {
                    pData.last_claim_time = resData.last_claim_time;
                }
                pData.unclaimed = 0;
                claimCooldown = 5; 
            }
        } catch (e) {
            setStoredBalance(currentBal);
            showToast(e.message || "حدث خطأ في عملية التجميع");
            if (claimBtn) {
                claimBtn.disabled = false;
                claimBtn.innerText = "تجميع الرصيد 💰";
            }
        } finally {
            isClaimingMain = false;
        }
    };

    window.updateFarmUI();
    window.fetchPlayerDataFromServer(true);
})();

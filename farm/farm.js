(function initFarm() {
    const tele = window.Telegram?.WebApp;
    const INIT_DATA = tele?.initData || "";
    const START_PARAM = tele?.initDataUnsafe?.start_param || "";

    const GAME_CONFIG = {
        maxUpgradesPerLevel: 10,
        dailyRewards: [
            100, 150, 200, 250, 300, 
            350, 400, 450, 500, 550, 
            600, 600, 650, 650, 700, 
            700, 750, 750, 800, 800, 
            850, 850, 900, 900, 950, 
            950, 1000, 1000, 1100, 1250
        ]
    };

    let claimCooldown = 0; 
    let isClaimingDaily = false;
    let isBoosting = false; 
    let isFetching = false;
    let isClaimingMain = false; 
    let isUpgrading = false;

    function showToast(message) {
        if (tele && tele.showAlert) tele.showAlert(message);
        else alert(message);
    }

    function getStoredBalance() {
        return parseFloat(window.userState?.balance || 0);
    }

    function setStoredBalance(newBalance) {
        if (newBalance !== undefined && newBalance !== null) {
            if (!window.userState) window.userState = {};
            window.userState.balance = parseFloat(newBalance);
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

    window.fetchPlayerDataFromServer = async function() {
        if (!INIT_DATA || isFetching) return; 
        isFetching = true;
        try {
            let response = await fetch('/api/farm/player_data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: INIT_DATA, start_param: START_PARAM })
            });
            let resData = await response.json();
            if (response.ok && resData.success) {
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
                if (resData.game_config && resData.game_config.daily_rewards) {
                    GAME_CONFIG.dailyRewards = resData.game_config.daily_rewards;
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
        if (balEl) balEl.innerText = `ZN: ${Math.floor(bal).toLocaleString()}`;

        const rateEl = document.getElementById('farm-rate');
        if (rateEl) rateEl.innerText = `⚡ ${Math.floor(hRate).toLocaleString()}/h`; 
        
        const fieldsContainer = document.getElementById('mining-fields');
        if (fieldsContainer) {
            let fieldsHTML = '';
            for (let i = 1; i <= 9; i++) {
                let count = parseInt((pData.upgrades && pData.upgrades[`lvl${i}`]) || 0);
                let isUnlocked = (i === 1) || (parseInt((pData.upgrades && pData.upgrades[`lvl${i-1}`]) || 0) > 0);
                let isMax = count >= GAME_CONFIG.maxUpgradesPerLevel;
                
                if (isMax) {
                    fieldsHTML += `<div class="mining-card" style="position: relative; overflow: hidden; opacity: 0.8;"><div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #f39c12; font-size: 14px; transform: rotate(-15deg); z-index: 2;">MAX</div><div style="font-size: 22px; margin-bottom: 4px; opacity: 0.3;">🏛️</div><div class="mining-card-title">مستوى ${i}</div><div class="mining-card-level">مكتمل</div></div>`;
                } else if (count > 0) {
                    fieldsHTML += `<div class="mining-card" onclick="handleUpgrade(${i})" style="cursor: pointer; border-color: #f39c12; position: relative;"><div style="position: absolute; top: -6px; right: -6px; background: #f39c12; color: #000; font-weight: bold; border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; font-size: 10px; border: 2px solid #121212;">x${count}</div><div style="width: 28px; height: 28px; background: #f39c12; border-radius: 50%; margin: 0 auto 5px auto; display: flex; align-items: center; justify-content: center;"><span style="font-size: 14px;">🏛️</span></div><div class="mining-card-title">مستوى ${i}</div><button class="mining-card-btn">ترقية ⚡</button></div>`;
                } else if (isUnlocked) {
                    fieldsHTML += `<div class="mining-card" onclick="handleUpgrade(${i})" style="cursor: pointer; border: 1px dashed #555;"><div style="font-size: 20px; color: #777; margin-bottom: 4px;">🏛️</div><div class="mining-card-title">مستوى ${i}</div><button class="mining-card-btn">شراء ⚡</button></div>`;
                } else {
                    fieldsHTML += `<div class="mining-card" style="opacity: 0.4; cursor: not-allowed;"><div style="font-size: 20px; color: #555; margin-bottom: 4px;">🔒</div><div class="mining-card-title">مستوى ${i}</div><div class="mining-card-level" style="color:#666;">مغلق</div></div>`;
                }
            }
            fieldsContainer.innerHTML = fieldsHTML;
        }
        renderDailyRewards(); 
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

        if (typeof rewards === 'object') {
            const dayKey = `day_${index + 1}`;
            if (rewards[dayKey] !== undefined) return rewards[dayKey];
            if (rewards[index + 1] !== undefined) return rewards[index + 1];
            if (rewards[index] !== undefined) return rewards[index];
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

    if (window.farmIntervalId) clearInterval(window.farmIntervalId);
    window.farmIntervalId = setInterval(() => {
        const pData = window.PlayerData;
        if (!pData) return;
        
        let unclaim = parseFloat(pData.unclaimed || 0);
        let maxC = parseFloat(window.userState?.max_cap || pData.max_cap || 200);
        let hRate = parseFloat(window.userState?.hourly_rate || pData.hourly_rate || 0); 
        
        if (unclaim < maxC) {
            unclaim += hRate / 3600;
            if (unclaim >= maxC) unclaim = maxC;
        }
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
                if(!isBoosting) {
                    boostBtn.className = "";
                    boostBtn.disabled = false;
                    boostBtn.style.background = "linear-gradient(135deg, #f39c12, #e67e22)";
                    boostBtn.style.boxShadow = "0 4px 12px rgba(243, 156, 18, 0.4)";
                    boostBtn.innerHTML = `<span style="font-size: 20px; margin-bottom: 2px;">🚀</span><span style="font-size: 10px; font-weight: bold;">+2/h</span>`; 
                }
            }
        }

        const dailyTimerEl = document.getElementById('daily-timer');
        if (dailyTimerEl && pData.last_daily_claim_date === todayStr) {
            dailyTimerEl.innerText = timeLeftStr;
        }

    }, 1000);

    function syncOnVisibility() {
        window.updateFarmUI();
        window.fetchPlayerDataFromServer();
    }

    window.addEventListener('pageshow', syncOnVisibility);
    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") syncOnVisibility();
    });

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
        if (!window.PlayerData || isUpgrading || !INIT_DATA) return;
        isUpgrading = true;

        try {
            let response = await fetch('/api/farm/upgrade', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ initData: INIT_DATA, level: level })
            });
            let resData = await response.json();
            if (response.ok && resData.success) {
                if (resData.new_balance !== undefined) setStoredBalance(resData.new_balance);
                if (resData.new_hourly_rate !== undefined) window.userState.hourly_rate = resData.new_hourly_rate;
                
                // ⚡ تحديث الـ upgrades في الذاكرة لحظياً لظهور شارات x1, x2 فوراً
                if (resData.upgrades) {
                    if (!window.PlayerData) window.PlayerData = {};
                    window.PlayerData.upgrades = resData.upgrades;
                    
                    if (!window.userState) window.userState = {};
                    window.userState.upgrades = resData.upgrades;
                }

                // ⚡ تحديث الواجهة فوراً بدون تأخير
                window.updateFarmUI();

                showToast(`⚡ تم التحديث بنجاح للمستوى ${level}!`);
                await window.fetchPlayerDataFromServer();
            } else if (resData.error) {
                showToast(resData.error);
            }
        } catch (e) {
            console.error("خطأ في شراء الترقية:", e);
            showToast("حدث خطأ أثناء الاتصال بالخادم.");
        } finally {
            isUpgrading = false;
        }
    };

    window.handleDailyBoost = async function() {
        if (!window.PlayerData || isBoosting || !INIT_DATA) return;
        
        const pData = window.PlayerData;
        const todayStr = getTodayUTCStr();
        if (pData.last_boost_date === todayStr) return;

        const btn = document.getElementById('boost-btn');
        isBoosting = true;
        
        try {
            const adWatched = await showTelegramAd(() => {
                if (btn) {
                    btn.innerHTML = `<span style="font-size: 18px;">🎬</span>`;
                    btn.disabled = true;
                }
            });
            
            if (adWatched) {
                if (btn) btn.innerHTML = `<span style="font-size: 18px;">💾</span>`;
                let response = await fetch('/api/farm/daily_boost', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ initData: INIT_DATA })
                });
                let resData = await response.json();
                if (response.ok && resData.success) {
                    if (resData.new_balance !== undefined) setStoredBalance(resData.new_balance);
                    if (resData.new_rate !== undefined) window.userState.hourly_rate = resData.new_rate;
                    showToast(`🚀 تمت زيادة معدل التعدين بنجاح بمقدار +2/h دائماً!`);
                    await window.fetchPlayerDataFromServer(); 
                } else if (resData.error) {
                    showToast(resData.error);
                    await window.fetchPlayerDataFromServer();
                }
            }
        } catch (e) {
            console.error("خطأ تسريع التعدين:", e);
        } finally {
            isBoosting = false;
        }
    };

    window.handleDailyClaim = async function(day) {
        if (!window.PlayerData || isClaimingDaily || !INIT_DATA) return;
        
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
                let response = await fetch('/api/farm/daily_claim', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ initData: INIT_DATA })
                });
                let resData = await response.json();
                if (response.ok && resData.success) {
                    if (resData.new_balance !== undefined) setStoredBalance(resData.new_balance);
                    showToast(`🎉 استلمت ${resData.reward.toLocaleString()} ZN!`);
                    if (resData.reset_msg) showToast(resData.reset_msg);
                    await window.fetchPlayerDataFromServer(); 
                } else if (resData.error) {
                    showToast(resData.error);
                }
            } else {
                if (btn) {
                    btn.innerHTML = "📺 استلام";
                    btn.disabled = false;
                }
            }
        } catch (e) {
            console.error("خطأ المكافأة اليومية:", e);
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
        if (!pData || parseFloat(pData.unclaimed || 0) <= 0 || claimCooldown > 0 || !INIT_DATA || isClaimingMain) return;

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
        window.updateFarmUI();

        try {
            let response = await fetch('/api/farm/claim', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ initData: INIT_DATA })
            });
            let resData = await response.json();
            
            if (response.ok && resData.success) {
                if (resData.new_balance !== undefined) setStoredBalance(resData.new_balance);
                await window.fetchPlayerDataFromServer(); 
                claimCooldown = 5; 
            } else {
                setStoredBalance(currentBal);
                if (resData.error) showToast(resData.error);
                if (claimBtn) {
                    claimBtn.disabled = false;
                    claimBtn.innerText = "تجميع الرصيد 💰";
                }
            }
        } catch (e) {
            setStoredBalance(currentBal);
            if (claimBtn) {
                claimBtn.disabled = false;
                claimBtn.innerText = "تجميع الرصيد 💰";
            }
        } finally {
            isClaimingMain = false;
        }
    };

    window.updateFarmUI();
    window.fetchPlayerDataFromServer();
})();


// farm/farm.js
(function initFarm() {
    const INIT_DATA = (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) ? window.Telegram.WebApp.initData : "";

    const GAME_CONFIG = {
        maxUpgradesPerLevel: 10, 
        dailyRewards: [
            3000, 4000, 5000, 6000, 7500,          
            10000, 12000, 15000, 18000, 20000,     
            25000, 30000, 35000, 40000, 50000,     
            60000, 70000, 80000, 90000, 100000,    
            120000, 150000, 180000, 220000, 250000,
            300000, 400000, 500000, 750000, 1000000
        ]
    };

    let claimCooldown = 0; 
    let isClaimingDaily = false;
    let isBoosting = false; 
    let isFetching = false;
    let isClaimingMain = false; 

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
                body: JSON.stringify({ initData: INIT_DATA })
            });
            let resData = await response.json();
            if (response.ok && resData.success) {
                window.PlayerData = resData.player;
                if (resData.game_config && resData.game_config.daily_rewards) {
                    GAME_CONFIG.dailyRewards = resData.game_config.daily_rewards;
                }
                window.updateFarmUI();
            }
        } catch (e) { console.error("Error", e); } 
        finally { isFetching = false; }
    };

    window.fetchPlayerData = async function() { await window.fetchPlayerDataFromServer(); };

    window.updateFarmUI = function() {
        const pData = window.PlayerData || {};
        
        let bal = parseFloat(pData.balance || 0);
        let hRate = parseFloat(pData.hourly_rate || 0); // تم التعديل لتكون 0
        
        document.getElementById('farm-balance').innerText = `ZN: ${Math.floor(bal).toLocaleString()}`;
        document.getElementById('farm-rate').innerText = `⚡ ${Math.floor(hRate).toLocaleString()}/h`; // تم تعديل س إلى h
        
        const fieldsContainer = document.getElementById('mining-fields');
        if (fieldsContainer) {
            let fieldsHTML = '';
            for (let i = 1; i <= 9; i++) {
                let count = parseInt((pData.upgrades && pData.upgrades[`lvl${i}`]) || 0);
                let isUnlocked = (i === 1) || (parseInt((pData.upgrades && pData.upgrades[`lvl${i-1}`]) || 0) > 0);
                let isMax = count >= GAME_CONFIG.maxUpgradesPerLevel;
                
                if (isMax) fieldsHTML += `<div style="background: #222; border-radius: 12px; padding: 15px 8px; text-align: center; border: 1px solid #444; position: relative; overflow: hidden;"><div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; font-size: 16px; transform: rotate(-15deg);">MAX</div><div style="font-size: 24px; margin-bottom: 5px; opacity: 0.4;">🏛️</div><div style="color: #888; font-size: 12px; font-weight: bold;">مستوى ${i}</div></div>`;
                else if (count > 0) fieldsHTML += `<div style="background: #1c1c1c; border-radius: 12px; padding: 15px 8px; text-align: center; border: 1px solid #0088cc; position: relative;"><div style="position: absolute; top: -6px; right: -6px; background: #ffcc00; color: #000; font-weight: bold; border-radius: 50%; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-size: 10px; border: 2px solid #121212;">x${count}</div><div style="width: 32px; height: 32px; background: #ffcc00; border-radius: 50%; margin: 0 auto 6px auto; display: flex; align-items: center; justify-content: center;"><span style="font-size: 15px;">🏛️</span></div><div style="color: white; font-size: 12px; font-weight: bold;">مستوى ${i}</div></div>`;
                else if (isUnlocked) fieldsHTML += `<div style="background: #181818; border-radius: 12px; padding: 15px 8px; text-align: center; border: 1px dashed #555; cursor: pointer;"><div style="font-size: 22px; color: #777; margin-bottom: 5px;">🏛️</div><div style="color: #00bfff; font-size: 11px; font-weight: bold;">متاح للشراء</div></div>`;
                else fieldsHTML += `<div style="background: #141414; border-radius: 12px; padding: 15px 8px; text-align: center; border: 1px solid #222; opacity: 0.5;"><div style="font-size: 22px; color: #555; margin-bottom: 5px;">🔒</div><div style="color: #666; font-size: 11px; font-weight: bold;">مغلق</div></div>`;
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

    function renderDailyRewards() {
        const container = document.getElementById('daily-rewards-container');
        const pData = window.PlayerData || {};
        if (!container) return; 

        let html = '';
        const todayStr = getTodayUTCStr();
        const canClaim = pData.last_daily_claim_date !== todayStr; 
        const currentDailyDay = parseInt(pData.daily_day || 1);

        for (let i = 0; i < 30; i++) {
            let dayNum = i + 1;
            let rawReward = GAME_CONFIG.dailyRewards[i];
            let displayReward = formatCompactNumber(rawReward);

            if (dayNum < currentDailyDay) {
                html += `<div style="background: rgba(40, 167, 69, 0.08); border: 1px solid #28a745; border-radius: 8px; padding: 8px 2px; text-align: center;"><div style="color: #888; font-size: 10px; margin-bottom: 3px;">يوم ${dayNum}</div><div style="color: #28a745; font-size: 14px; margin-bottom: 3px;">✔️</div><div style="color: #28a745; font-size: 9px; font-weight: bold;">تم</div></div>`;
            } else if (dayNum === currentDailyDay) {
                if (canClaim) {
                    html += `<div style="background: #222; border: 2px solid #ffcc00; border-radius: 8px; padding: 6px 2px; text-align: center;"><div style="color: #fff; font-size: 10px; font-weight: bold; margin-bottom: 3px;">يوم ${dayNum}</div><div style="color: #ffcc00; font-size: 10px; font-weight: bold; margin-bottom: 4px;">${displayReward}</div><button id="daily-btn-${dayNum}" onclick="handleDailyClaim(${dayNum})" style="background: #28a745; color: white; border: none; border-radius: 4px; padding: 4px 0; font-size: 10px; cursor: pointer; width: 85%; animation: pulseGreen 2s infinite;">📺</button></div>`;
                } else {
                    html += `<div style="background: #222; border: 1px solid #555; border-radius: 8px; padding: 8px 2px; text-align: center;"><div style="color: #fff; font-size: 10px; margin-bottom: 3px;">يوم ${dayNum}</div><div style="color: #ffcc00; font-size: 10px; margin-bottom: 4px;">${displayReward}</div><div id="daily-timer" style="color: #ff4444; font-size: 10px; font-weight: bold;">⏳</div></div>`;
                }
            } else {
                html += `<div style="background: #141414; border: 1px solid #2a2a2a; border-radius: 8px; padding: 8px 2px; text-align: center; opacity: 0.5;"><div style="color: #777; font-size: 10px; margin-bottom: 3px;">يوم ${dayNum}</div><div style="color: #555; font-size: 14px; margin-bottom: 3px;">🔒</div><div style="color: #777; font-size: 9px;">${displayReward}</div></div>`;
            }
        }
        container.innerHTML = html;
    }

    if (window.farmIntervalId) clearInterval(window.farmIntervalId);
    window.farmIntervalId = setInterval(() => {
        const pData = window.PlayerData;
        if (!pData) return;
        
        let unclaim = parseFloat(pData.unclaimed || 0);
        let maxC = parseFloat(pData.max_cap || 10000);
        let hRate = parseFloat(pData.hourly_rate || 0); // تعديل لـ 0
        
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
            if (pct >= 100) progressEl.style.background = 'linear-gradient(90deg, #ff4444, #cc0000)'; 
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
                claimBtn.className = unclaim > 0 ? "btn-ready" : "";
                claimBtn.disabled = unclaim <= 0;
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
                    boostBtn.style.background = "linear-gradient(135deg, #ff8c00, #ff0080)";
                    boostBtn.innerHTML = `<span style="font-size: 22px; margin-bottom: 2px;">🚀</span><span style="font-size: 11px; font-weight: bold;">+1/h</span>`; // تم تعديل س إلى h
                }
            }
        }

        const dailyTimerEl = document.getElementById('daily-timer');
        if (dailyTimerEl && pData.last_daily_claim_date === todayStr) {
            dailyTimerEl.innerText = timeLeftStr;
        }

    }, 1000);

    setInterval(() => {
        if (!isBoosting && !isClaimingDaily && !isClaimingMain && claimCooldown === 0) {
            window.fetchPlayerDataFromServer();
        }
    }, 10000); 

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") window.fetchPlayerDataFromServer();
    });

    function showTelegramAd(statusCallback) {
        return new Promise((resolve) => {
            if (typeof window.show_11322720 === 'function') {
                if (statusCallback) statusCallback();
                window.show_11322720().then(() => resolve(true)).catch(() => resolve(false));
            } else {
                if (window.Telegram && window.Telegram.WebApp) window.Telegram.WebApp.showAlert("⚠️ عطل في تحميل الإعلان. تأكد من اتصالك بالإنترنت أو أوقف مانع الإعلانات.");
                resolve(false);
            }
        });
    }

    window.handleDailyBoost = async function() {
        if (isBoosting || !INIT_DATA) return;
        const btn = document.getElementById('boost-btn');
        isBoosting = true;
        
        const adWatched = await showTelegramAd(() => {
            btn.innerHTML = `<span style="font-size: 20px;">🎬</span>`;
        });
        
        if (adWatched) {
            btn.innerHTML = `<span style="font-size: 20px;">💾</span>`;
            try {
                let response = await fetch('/api/farm/daily_boost', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ initData: INIT_DATA })
                });
                let resData = await response.json();
                if (response.ok && resData.success) {
                    if (window.Telegram && window.Telegram.WebApp) window.Telegram.WebApp.showAlert(`🚀 تمت زيادة السرعة! العداد سيبدأ الآن.`);
                    await window.fetchPlayerData(); 
                } else if (resData.error && window.Telegram && window.Telegram.WebApp) {
                    window.Telegram.WebApp.showAlert(resData.error);
                }
            } catch (e) { console.error(e); }
        }
        isBoosting = false;
    };

    window.handleDailyClaim = async function(day) {
        if (isClaimingDaily || !INIT_DATA) return;
        const btn = document.getElementById(`daily-btn-${day}`);
        isClaimingDaily = true;
        
        const adWatched = await showTelegramAd(() => {
            if (btn) btn.innerHTML = "⏳";
        });
        
        if (adWatched) {
            if (btn) btn.innerHTML = "💾";
            try {
                let response = await fetch('/api/farm/daily_claim', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ initData: INIT_DATA })
                });
                let resData = await response.json();
                if (response.ok && resData.success) {
                    if (window.Telegram && window.Telegram.WebApp) {
                        window.Telegram.WebApp.showAlert(`🎉 استلمت ${resData.reward.toLocaleString()} ZN!`);
                        if (resData.reset_msg) window.Telegram.WebApp.showAlert(resData.reset_msg);
                    }
                    await window.fetchPlayerData(); 
                } else if (resData.error && window.Telegram && window.Telegram.WebApp) {
                    window.Telegram.WebApp.showAlert(resData.error);
                }
            } catch (e) { }
        } else {
            if (btn) btn.innerHTML = "📺";
        }
        isClaimingDaily = false;
    };

    window.handleClaim = async function() {
        const pData = window.PlayerData;
        if (!pData || parseFloat(pData.unclaimed || 0) <= 0 || claimCooldown > 0 || !INIT_DATA || isClaimingMain) return;

        isClaimingMain = true;
        const claimBtn = document.getElementById('claim-btn');
        claimBtn.disabled = true;
        claimBtn.innerText = "جاري الحفظ... 💾";
        
        try {
            let response = await fetch('/api/farm/claim', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ initData: INIT_DATA })
            });
            let resData = await response.json();
            
            if (response.ok && resData.success) {
                await window.fetchPlayerData(); 
                claimCooldown = 5; 
            } else {
                if (resData.error && window.Telegram && window.Telegram.WebApp) {
                    window.Telegram.WebApp.showAlert(resData.error);
                }
                claimBtn.disabled = false;
                claimBtn.innerText = "تجميع الرصيد 💰";
            }
        } catch (e) {
            claimBtn.disabled = false;
            claimBtn.innerText = "تجميع الرصيد 💰";
        }
        isClaimingMain = false;
    };

    window.fetchPlayerData();
})();

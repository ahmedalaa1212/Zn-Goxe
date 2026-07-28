// farm/farm.js
(function initFarm() {
    const tele = window.Telegram?.WebApp;
    const INIT_DATA = tele?.initData || "";
    const START_PARAM = tele?.initDataUnsafe?.start_param || "";

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

    function showToast(message) {
        if (tele && tele.showAlert) {
            tele.showAlert(message);
        } else {
            alert(message);
        }
    }

    // --- أدوات المزامنة الموحدة مع باقي الأقسام ---
    function getStoredBalance() {
        if (window.GameState && window.GameState.balance !== undefined && window.GameState.balance !== null) {
            return parseFloat(window.GameState.balance);
        }
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        return bal !== null ? parseFloat(bal) : 0;
    }

    function setStoredBalance(newBalance) {
        if (newBalance !== undefined && newBalance !== null) {
            const numVal = parseFloat(newBalance);
            if (typeof window.setBalance === 'function') {
                window.setBalance(numVal);
            } else {
                if (window.GameState) window.GameState.balance = numVal;
                localStorage.setItem('zn_balance', numVal.toString());
                localStorage.setItem('user_balance', numVal.toString());
            }
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
                body: JSON.stringify({ 
                    initData: INIT_DATA,
                    start_param: START_PARAM
                })
            });
            let resData = await response.json();
            if (response.ok && resData.success) {
                window.PlayerData = resData.player;
                if (resData.player && resData.player.balance !== undefined) {
                    setStoredBalance(resData.player.balance);
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

    window.fetchPlayerData = async function() { 
        await window.fetchPlayerDataFromServer(); 
    };

    window.updateFarmUI = function() {
        const pData = window.PlayerData || {};
        
        // قراءة الرصيد الأحدث فوراً
        let bal = getStoredBalance();
        if (window.PlayerData) window.PlayerData.balance = bal;

        let hRate = parseFloat(pData.hourly_rate || 0);
        
        const balEl = document.getElementById('farm-balance');
        if (balEl) balEl.innerText = `ZN: ${Math.floor(bal).toLocaleString()}`;
        
        if (typeof window.updateGlobalUI === 'function') {
            window.updateGlobalUI();
        }

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
                    fieldsHTML += `<div style="background: #222; border-radius: 12px; padding: 12px 6px; text-align: center; border: 1px solid #444; position: relative; overflow: hidden;"><div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #f39c12; font-size: 14px; transform: rotate(-15deg);">MAX</div><div style="font-size: 22px; margin-bottom: 4px; opacity: 0.3;">🏛️</div><div style="color: #888; font-size: 11px; font-weight: bold;">مستوى ${i}</div></div>`;
                } else if (count > 0) {
                    fieldsHTML += `<div style="background: #1c1c1c; border-radius: 12px; padding: 12px 6px; text-align: center; border: 1px solid #f39c12; position: relative;"><div style="position: absolute; top: -6px; right: -6px; background: #f39c12; color: #000; font-weight: bold; border-radius: 50%; width: 20px; height: 20px; display: flex; align-items: center; justify-content: center; font-size: 10px; border: 2px solid #121212;">x${count}</div><div style="width: 28px; height: 28px; background: #f39c12; border-radius: 50%; margin: 0 auto 5px auto; display: flex; align-items: center; justify-content: center;"><span style="font-size: 14px;">🏛️</span></div><div style="color: white; font-size: 11px; font-weight: bold;">مستوى ${i}</div></div>`;
                } else if (isUnlocked) {
                    fieldsHTML += `<div style="background: #181818; border-radius: 12px; padding: 12px 6px; text-align: center; border: 1px dashed #555;"><div style="font-size: 20px; color: #777; margin-bottom: 4px;">🏛️</div><div style="color: #f1c40f; font-size: 10px; font-weight: bold;">متاح للشراء</div></div>`;
                } else {
                    fieldsHTML += `<div style="background: #141414; border-radius: 12px; padding: 12px 6px; text-align: center; border: 1px solid #222; opacity: 0.4;"><div style="font-size: 20px; color: #555; margin-bottom: 4px;">🔒</div><div style="color: #666; font-size: 10px; font-weight: bold;">مغلق</div></div>`;
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

    function renderDailyRewards() {
        const container = document.getElementById('daily-rewards-container');
        const pData = window.PlayerData;
        if (!container || !pData) return; 

        let html = '';
        const todayStr = getTodayUTCStr();
        const canClaim = pData.last_daily_claim_date !== todayStr; 
        const currentDailyDay = parseInt(pData.daily_day || 1);

        for (let i = 0; i < 30; i++) {
            let dayNum = i + 1;
            let rawReward = GAME_CONFIG.dailyRewards[i] || 1000;
            let displayReward = formatCompactNumber(rawReward);

            if (dayNum < currentDailyDay) {
                html += `<div style="background: rgba(46, 204, 113, 0.08); border: 1px solid #2ecc71; border-radius: 8px; padding: 6px 2px; text-align: center;"><div style="color: #888; font-size: 9px; margin-bottom: 2px;">يوم ${dayNum}</div><div style="color: #2ecc71; font-size: 12px; margin-bottom: 2px;">✔️</div><div style="color: #2ecc71; font-size: 9px; font-weight: bold;">تم</div></div>`;
            } else if (dayNum === currentDailyDay) {
                if (canClaim) {
                    html += `<div style="background: #222; border: 2px solid #f39c12; border-radius: 8px; padding: 5px 2px; text-align: center;"><div style="color: #fff; font-size: 9px; font-weight: bold; margin-bottom: 2px;">يوم ${dayNum}</div><div style="color: #f39c12; font-size: 9px; font-weight: bold; margin-bottom: 4px;">${displayReward}</div><button id="daily-btn-${dayNum}" onclick="handleDailyClaim(${dayNum})" style="background: #2ecc71; color: white; border: none; border-radius: 4px; padding: 4px 0; font-size: 10px; cursor: pointer; width: 90%; animation: pulseGreen 2s infinite;">📺 استلام</button></div>`;
                } else {
                    html += `<div style="background: #222; border: 1px solid #555; border-radius: 8px; padding: 6px 2px; text-align: center;"><div style="color: #fff; font-size: 9px; margin-bottom: 2px;">يوم ${dayNum}</div><div style="color: #f39c12; font-size: 9px; margin-bottom: 3px;">${displayReward}</div><div id="daily-timer" style="color: #e74c3c; font-size: 9px; font-weight: bold;">⏳</div></div>`;
                }
            } else {
                html += `<div style="background: #141414; border: 1px solid #2a2a2a; border-radius: 8px; padding: 6px 2px; text-align: center; opacity: 0.5;"><div style="color: #777; font-size: 9px; margin-bottom: 2px;">يوم ${dayNum}</div><div style="color: #555; font-size: 12px; margin-bottom: 2px;">🔒</div><div style="color: #777; font-size: 8px;">${displayReward}</div></div>`;
            }
        }
        container.innerHTML = html;
    }

    if (window.farmIntervalId) clearInterval(window.farmIntervalId);
    window.farmIntervalId = setInterval(() => {
        const pData = window.PlayerData;
        if (!pData) return;
        
        let unclaim = parseFloat(pData.unclaimed || 0);
        let maxC = parseFloat(pData.max_cap || 100);
        let hRate = parseFloat(pData.hourly_rate || 0); 
        
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
                    boostBtn.innerHTML = `<span style="font-size: 20px; margin-bottom: 2px;">🚀</span><span style="font-size: 10px; font-weight: bold;">+1/h</span>`; 
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

    window.addEventListener('pageshow', () => {
        const stored = getStoredBalance();
        if (stored !== null) {
            if (!window.PlayerData) window.PlayerData = {};
            window.PlayerData.balance = stored;
        }
        window.updateFarmUI();
        window.fetchPlayerDataFromServer();
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            const stored = getStoredBalance();
            if (stored !== null) {
                if (!window.PlayerData) window.PlayerData = {};
                window.PlayerData.balance = stored;
            }
            window.updateFarmUI();
            window.fetchPlayerDataFromServer();
        }
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

    window.handleDailyBoost = async function() {
        if (!window.PlayerData || isBoosting || !INIT_DATA) return;
        
        const pData = window.PlayerData;
        const todayStr = getTodayUTCStr();
        if (pData.last_boost_date === todayStr) return;

        const btn = document.getElementById('boost-btn');
        isBoosting = true;
        
        try {
            const adWatched = await showTelegramAd(() => {
                btn.innerHTML = `<span style="font-size: 18px;">🎬</span>`;
                btn.disabled = true;
            });
            
            if (adWatched) {
                btn.innerHTML = `<span style="font-size: 18px;">💾</span>`;
                let response = await fetch('/api/farm/daily_boost', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ initData: INIT_DATA })
                });
                let resData = await response.json();
                if (response.ok && resData.success) {
                    if (resData.new_balance !== undefined) setStoredBalance(resData.new_balance);
                    showToast(`🚀 تمت زيادة معدل التعدين بنجاح!`);
                    await window.fetchPlayerData(); 
                } else if (resData.error) {
                    showToast(resData.error);
                    await window.fetchPlayerData();
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

        const btn = document.getElementById(`daily-btn-${day}`);
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
                    await window.fetchPlayerData(); 
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
        claimBtn.disabled = true;
        claimBtn.className = "btn-cooldown";
        claimBtn.innerText = "جاري الحفظ... 💾";

        // تحديث متفائل (Optimistic Update)
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
                await window.fetchPlayerData(); 
                claimCooldown = 5; 
            } else {
                // التراجع عند الخطأ
                setStoredBalance(currentBal);
                if (resData.error) showToast(resData.error);
                claimBtn.disabled = false;
                claimBtn.innerText = "تجميع الرصيد 💰";
            }
        } catch (e) {
            setStoredBalance(currentBal);
            claimBtn.disabled = false;
            claimBtn.innerText = "تجميع الرصيد 💰";
        } finally {
            isClaimingMain = false;
        }
    };

    // البدء برصيد الذاكرة فوراً
    const cachedBal = getStoredBalance();
    window.PlayerData = { balance: cachedBal, unclaimed: 0, hourly_rate: 0 };
    window.updateFarmUI();

    // جلب البيانات الأصلية في الخلفية
    window.fetchPlayerData();
})();

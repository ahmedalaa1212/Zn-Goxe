// farm/farm.js
(function initFarm() {
    // الحماية العامة للمتغيرات لمنع أي انهيار في الـ JavaScript
    if (!window.userState) {
        window.userState = { balance: 0, hourly_rate: 0 };
    }

    const tele = window.Telegram?.WebApp;
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
    let isUpgrading = false;

    // دالة استدعاء الـ API المرنة لمنع التوقف إذا لم تكن window.fetchAPI معرّفة
    async function callAPI(endpoint, method = 'POST', body = {}) {
        try {
            if (typeof window.fetchAPI === 'function') {
                return await window.fetchAPI(endpoint, method, body);
            } else if (typeof fetchAPI === 'function') {
                return await fetchAPI(endpoint, method, body);
            } else {
                const res = await fetch(endpoint, {
                    method: method,
                    headers: { 'Content-Type': 'application/json' },
                    body: method === 'POST' ? JSON.stringify(body) : null
                });
                return await res.json();
            }
        } catch (err) {
            console.error("API Call Error:", err);
            return null;
        }
    }

    function showToast(message) {
        if (tele && tele.showAlert) {
            tele.showAlert(message);
        } else {
            alert(message);
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

    function formatCompactNumber(num) {
        if (num >= 1000000) return (num / 1000000).toFixed(num % 1000000 === 0 ? 0 : 1) + 'M';
        if (num >= 1000) return (num / 1000).toFixed(num % 1000 === 0 ? 0 : 1) + 'K';
        return num.toString();
    }

    // إتاحة الدوال فوراً للـ HTML لتجنب أخطاء onclick
    window.handleUpgrade = async function(level) {
        if (!window.PlayerData || isUpgrading) return;
        isUpgrading = true;
        try {
            let resData = await callAPI('/api/farm/upgrade', 'POST', { level: level });
            if (resData && resData.success) {
                if (resData.new_balance !== undefined) window.userState.balance = resData.new_balance;
                if (resData.new_hourly_rate !== undefined) window.userState.hourly_rate = resData.new_hourly_rate;
                showToast(`⚡ تم التحديث بنجاح للمستوى ${level}!`);
                await window.fetchPlayerData();
            } else if (resData && resData.error) {
                showToast(resData.error);
            }
        } catch (e) {
            console.error("خطأ في شراء الترقية:", e);
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
                    btn.innerHTML = `<span style="font-size: 18px;">🎬</span>`;
                    btn.disabled = true;
                }
            });
            if (adWatched) {
                if (btn) btn.innerHTML = `<span style="font-size: 18px;">💾</span>`;
                let resData = await callAPI('/api/farm/daily_boost', 'POST', {});
                if (resData && resData.success) {
                    if (resData.new_rate !== undefined) window.userState.hourly_rate = resData.new_rate;
                    showToast(`🚀 تمت زيادة معدل التعدين بنجاح!`);
                    await window.fetchPlayerData(); 
                } else if (resData && resData.error) {
                    showToast(resData.error);
                }
            }
        } catch (e) {
            console.error("خطأ تسريع التعدين:", e);
        } finally {
            isBoosting = false;
            window.updateFarmUI();
        }
    };

    window.handleDailyClaim = async function(day) {
        if (!window.PlayerData || isClaimingDaily) return;
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
                let resData = await callAPI('/api/farm/daily_claim', 'POST', {});
                if (resData && resData.success) {
                    if (resData.new_balance !== undefined) window.userState.balance = resData.new_balance;
                    showToast(`🎉 استلمت ${resData.reward.toLocaleString()} ZN!`);
                    if (resData.reset_msg) showToast(resData.reset_msg);
                    await window.fetchPlayerData(); 
                } else if (resData && resData.error) {
                    showToast(resData.error);
                }
            }
        } catch (e) {
            console.error("خطأ المكافأة اليومية:", e);
        } finally {
            isClaimingDaily = false;
            window.updateFarmUI();
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
        const currentBal = parseFloat(window.userState?.balance || 0);
        window.userState.balance = currentBal + unclaimedAmount;
        pData.unclaimed = 0;

        try {
            let resData = await callAPI('/api/farm/claim', 'POST', {});
            if (resData && resData.success) {
                if (resData.new_balance !== undefined) window.userState.balance = resData.new_balance;
                await window.fetchPlayerData(); 
                claimCooldown = 5; 
            } else if (resData && resData.error) {
                window.userState.balance = currentBal;
                showToast(resData.error);
            }
        } catch (e) {
            window.userState.balance = currentBal;
        } finally {
            isClaimingMain = false;
            window.updateFarmUI();
        }
    };

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
            let rawReward = GAME_CONFIG.dailyRewards[i] || 1000;
            let displayReward = formatCompactNumber(rawReward);

            if (dayNum < currentDailyDay) {
                html += `<div class="reward-day-card claimed"><div class="day-title">يوم ${dayNum}</div><div style="font-size: 12px;">✔️</div><div style="font-size: 9px; font-weight: bold;">تم</div></div>`;
            } else if (dayNum === currentDailyDay) {
                if (canClaim) {
                    html += `<div class="reward-day-card active"><div class="day-title">يوم ${dayNum}</div><div class="day-amount">${displayReward} ZN</div><button id="daily-btn-${dayNum}" onclick="handleDailyClaim(${dayNum})" style="background: #2ecc71; color: white; border: none; border-radius: 4px; padding: 4px 0; font-size: 10px; cursor: pointer; width: 90%; animation: pulseGreen 2s infinite;">📺 استلام</button></div>`;
                } else {
                    html += `<div class="reward-day-card" style="border-color: #555;"><div class="day-title">يوم ${dayNum}</div><div class="day-amount">${displayReward} ZN</div><div id="daily-timer" style="color: #e74c3c; font-size: 9px; font-weight: bold;">⏳</div></div>`;
                }
            } else {
                html += `<div class="reward-day-card" style="opacity: 0.5;"><div class="day-title">يوم ${dayNum}</div><div style="font-size: 12px; color: #555;">🔒</div><div class="day-amount">${displayReward}</div></div>`;
            }
        }
        container.innerHTML = html;
    }

    window.updateFarmUI = function() {
        try {
            if (!window.userState) window.userState = { balance: 0, hourly_rate: 0 };
            const pData = window.PlayerData || {};
            
            if (pData.balance !== undefined) window.userState.balance = pData.balance;
            if (pData.hourly_rate !== undefined) window.userState.hourly_rate = pData.hourly_rate;

            const rateSpan = document.querySelector('#farm-rate span');
            if (rateSpan) {
                rateSpan.innerText = parseFloat(window.userState.hourly_rate || 0).toLocaleString('en-US');
            }
            const balanceSpan = document.querySelector('#farm-balance span');
            if (balanceSpan) {
                balanceSpan.innerText = Math.floor(parseFloat(window.userState.balance || 0)).toLocaleString('en-US');
            }

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
        } catch (err) {
            console.error("UI Update error:", err);
        }
    };

    window.fetchPlayerDataFromServer = async function() {
        if (isFetching) return; 
        isFetching = true;
        try {
            let resData = await callAPI('/api/farm/player_data', 'POST', { start_param: START_PARAM });
            if (resData && resData.success && resData.player) {
                const serverData = resData.player;
                if (!window.PlayerData) window.PlayerData = {};
                Object.assign(window.PlayerData, serverData);

                if (serverData.balance !== undefined) window.userState.balance = serverData.balance;
                if (serverData.hourly_rate !== undefined) window.userState.hourly_rate = serverData.hourly_rate;

                if (serverData.unclaimed !== undefined) {
                    const serverUnclaimed = parseFloat(serverData.unclaimed || 0);
                    if (claimCooldown > 0 || isClaimingMain) {
                        window.PlayerData.unclaimed = serverUnclaimed;
                    } else {
                        window.PlayerData.unclaimed = Math.max(parseFloat(window.PlayerData.unclaimed || 0), serverUnclaimed);
                    }
                }

                if (resData.game_config && resData.game_config.daily_rewards) {
                    GAME_CONFIG.dailyRewards = resData.game_config.daily_rewards;
                }
            }
        } catch (e) { 
            console.error("خطأ في مزامنة بيانات المزرعة:", e); 
        } finally { 
            isFetching = false; 
            window.updateFarmUI();
        }
    };

    window.fetchPlayerData = async function() { 
        await window.fetchPlayerDataFromServer(); 
    };

    // تهيئة بيانات افتراضية فورية لتجنب بقاء الواجهة فارغة أثناء التحميل
    if (!window.PlayerData) {
        window.PlayerData = {
            balance: window.userState.balance || 0,
            hourly_rate: window.userState.hourly_rate || 0,
            unclaimed: 0,
            max_cap: 100,
            upgrades: {},
            daily_day: 1
        };
    }

    // رسم الواجهة فوراً عند التشغيل
    window.updateFarmUI();

    // التحديث الدوري كل ثانية لنسبة التخزين والعدادات والأزرار
    if (window.farmIntervalId) clearInterval(window.farmIntervalId);
    window.farmIntervalId = setInterval(() => {
        try {
            const pData = window.PlayerData || {};
            let unclaim = parseFloat(pData.unclaimed || 0);
            let maxC = parseFloat(pData.max_cap || 100);
            let hRate = parseFloat(window.userState?.hourly_rate || 0); 
            
            if (unclaim < maxC && hRate > 0) {
                unclaim += hRate / 3600;
                if (unclaim >= maxC) unclaim = maxC;
            }
            pData.unclaimed = unclaim;

            const progressEl = document.getElementById('storage-progress');
            const storageTextEl = document.getElementById('storage-text');
            if (progressEl && storageTextEl) {
                let pct = maxC > 0 ? (unclaim / maxC) * 100 : 0;
                pct = Math.max(0, Math.min(pct, 100)); 
                progressEl.style.width = `${pct}%`;
                if (pct >= 100) progressEl.style.background = 'linear-gradient(90deg, #e74c3c, #c0392b)'; 
                else progressEl.style.background = 'linear-gradient(90deg, #f39c12, #f1c40f)';
                
                storageTextEl.innerHTML = `<span dir="ltr">${Math.floor(unclaim).toLocaleString('en-US')} / ${Math.floor(maxC).toLocaleString('en-US')}</span>`;
            }

            const rateSpan = document.querySelector('#farm-rate span');
            if (rateSpan) {
                rateSpan.innerText = parseFloat(window.userState?.hourly_rate || 0).toLocaleString('en-US');
            }
            const balanceSpan = document.querySelector('#farm-balance span');
            if (balanceSpan) {
                balanceSpan.innerText = Math.floor(parseFloat(window.userState?.balance || 0)).toLocaleString('en-US');
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
                } else if (!isBoosting) {
                    boostBtn.className = "";
                    boostBtn.disabled = false;
                    boostBtn.style.background = "linear-gradient(135deg, #f39c12, #e67e22)";
                    boostBtn.style.boxShadow = "0 4px 12px rgba(243, 156, 18, 0.4)";
                    boostBtn.innerHTML = `<span style="font-size: 20px; margin-bottom: 2px;">🚀</span><span style="font-size: 10px; font-weight: bold;">+1/h</span>`; 
                }
            }

            const dailyTimerEl = document.getElementById('daily-timer');
            if (dailyTimerEl && pData.last_daily_claim_date === todayStr) {
                dailyTimerEl.innerText = timeLeftStr;
            }
        } catch (err) {
            console.error("Interval error:", err);
        }
    }, 1000);

    if (window.farmSyncIntervalId) clearInterval(window.farmSyncIntervalId);
    window.farmSyncIntervalId = setInterval(() => {
        if (!isBoosting && !isClaimingDaily && !isClaimingMain && !isUpgrading && claimCooldown === 0) {
            window.fetchPlayerDataFromServer();
        }
    }, 10000); 

    window.addEventListener('pageshow', () => {
        window.updateFarmUI();
        window.fetchPlayerDataFromServer();
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            window.updateFarmUI();
            window.fetchPlayerDataFromServer();
        }
    });

    // طلب البيانات فوراً من السيرفر
    window.fetchPlayerDataFromServer();
})();

// farm/farm.js
(function initFarm() {
    
    const INIT_DATA = (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initData) ? window.Telegram.WebApp.initData : "";

    const GAME_CONFIG = {
        maxUpgradesPerLevel: 15,
        dailyRewards: [
            3000, 4000, 5000, 6000, 7500,          
            10000, 12000, 15000, 18000, 20000,     
            25000, 30000, 35000, 40000, 50000,     
            60000, 70000, 80000, 90000, 100000,    
            120000, 150000, 180000, 220000, 250000,
            300000, 400000, 500000, 750000, 1000000
        ],
        capacities: {0: 10000, 1: 20000, 2: 30000, 3: 50000, 4: 100000, 5: 200000, 6: 500000, 7: 1000000, 8: 2500000, 9: 5000000, 10: 10000000},
        miningRates: {1: 100, 2: 500, 3: 1500, 4: 4000, 5: 10000, 6: 25000, 7: 60000, 8: 150000, 9: 500000} 
    };

    let claimCooldown = 0; 
    let isClaimingDaily = false;

    window.fetchPlayerDataFromServer = async function() {
        if (!INIT_DATA) {
            window.PlayerData = {
                balance: 5000,
                hourly_rate: 1500,
                unclaimed: 2500,
                max_cap: 30000,
                upgrades: {lvl1: 5, lvl2: 1}, 
                daily_day: 3,
                last_daily_claim_time: Date.now() - (48 * 60 * 60 * 1000) 
            };
            window.updateFarmUI();
            return; 
        }

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
        } catch (e) {
            console.error("Error fetching player data:", e);
        }
    };

    window.fetchPlayerData = async function() {
        await window.fetchPlayerDataFromServer();
    };

    window.updateFarmUI = function() {
        const pData = window.PlayerData || {};
        
        let bal = parseFloat(pData.balance || 0);
        let hRate = parseFloat(pData.hourly_rate || 100);
        let unclaim = parseFloat(pData.unclaimed || 0);
        let maxC = parseFloat(pData.max_cap || 10000);

        const farmBalEl = document.getElementById('farm-balance');
        const farmRateEl = document.getElementById('farm-rate');
        
        if (farmBalEl) farmBalEl.innerText = `ZN: ${Math.floor(bal).toLocaleString()}`;
        if (farmRateEl) farmRateEl.innerText = `⚡ ${hRate.toLocaleString()}/س`;
        
        const progressEl = document.getElementById('storage-progress');
        const storageTextEl = document.getElementById('storage-text');
        
        if (progressEl && storageTextEl) {
            let pct = (unclaim / maxC) * 100;
            pct = Math.max(0, Math.min(pct, 100));
            progressEl.style.width = `${pct}%`;
            if (pct >= 100) {
                progressEl.style.background = 'linear-gradient(90deg, #ff4444, #cc0000)'; 
            } else {
                progressEl.style.background = 'linear-gradient(90deg, #0088cc, #00bfff)'; 
            }
            storageTextEl.innerText = `${Math.floor(unclaim).toLocaleString()} / ${maxC.toLocaleString()}`;
        }
        
        const fieldsContainer = document.getElementById('mining-fields');
        if (fieldsContainer) {
            let fieldsHTML = '';
            for (let i = 1; i <= 9; i++) {
                let count = parseInt((pData.upgrades && pData.upgrades[`lvl${i}`]) || 0);
                let isUnlocked = (i === 1) || (parseInt((pData.upgrades && pData.upgrades[`lvl${i-1}`]) || 0) > 0);
                let isMax = count >= GAME_CONFIG.maxUpgradesPerLevel;
                
                if (isMax) {
                    fieldsHTML += `
                        <div style="background: #222; border-radius: 12px; padding: 15px 8px; text-align: center; border: 1px solid #444; position: relative; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.2);">
                            <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.65); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; font-size: 16px; transform: rotate(-15deg);">MAX</div>
                            <div style="font-size: 24px; margin-bottom: 5px; opacity: 0.4;">🏛️</div>
                            <div style="color: #888; font-size: 12px; font-weight: bold;">مستوى ${i}</div>
                        </div>
                    `;
                } else if (count > 0) {
                    fieldsHTML += `
                        <div style="background: #1c1c1c; border-radius: 12px; padding: 15px 8px; text-align: center; border: 1px solid #0088cc; position: relative; box-shadow: 0 4px 8px rgba(0,136,204,0.15);">
                            <div style="position: absolute; top: -6px; right: -6px; background: #ffcc00; color: #000; font-weight: bold; border-radius: 50%; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; font-size: 10px; border: 2px solid #121212;">x${count}</div>
                            <div style="width: 32px; height: 32px; background: #ffcc00; border-radius: 50%; margin: 0 auto 6px auto; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 10px rgba(255, 204, 0, 0.3);">
                                <span style="font-size: 15px;">🏛️</span>
                            </div>
                            <div style="color: white; font-size: 12px; font-weight: bold;">مستوى ${i}</div>
                        </div>
                    `;
                } else if (isUnlocked) {
                    fieldsHTML += `
                        <div style="background: #181818; border-radius: 12px; padding: 15px 8px; text-align: center; border: 1px dashed #555; cursor: pointer;">
                            <div style="font-size: 22px; color: #777; margin-bottom: 5px;">🏛️</div>
                            <div style="color: #00bfff; font-size: 11px; font-weight: bold;">متاح للشراء</div>
                        </div>
                    `;
                } else {
                    fieldsHTML += `
                        <div style="background: #141414; border-radius: 12px; padding: 15px 8px; text-align: center; border: 1px solid #222; opacity: 0.5;">
                            <div style="font-size: 22px; color: #555; margin-bottom: 5px;">🔒</div>
                            <div style="color: #666; font-size: 11px; font-weight: bold;">مغلق</div>
                        </div>
                    `;
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
        const pData = window.PlayerData || {};
        if (!container) return; 

        let html = '';
        let nowOffset = Date.now() + (window.timeOffset || 0);
        const lastClaim = new Date(pData.last_daily_claim_time || 0).getTime();
        const timePassed = nowOffset - lastClaim;
        const canClaim = timePassed >= (24 * 60 * 60 * 1000) || !pData.last_daily_claim_time; 
        const currentDailyDay = parseInt(pData.daily_day || 1);

        for (let i = 0; i < 30; i++) {
            let dayNum = i + 1;
            let rawReward = GAME_CONFIG.dailyRewards[i];
            let displayReward = formatCompactNumber(rawReward);

            if (dayNum < currentDailyDay) {
                html += `
                    <div style="background: rgba(40, 167, 69, 0.08); border: 1px solid #28a745; border-radius: 8px; padding: 8px 2px; text-align: center;">
                        <div style="color: #888; font-size: 10px; margin-bottom: 3px;">يوم ${dayNum}</div>
                        <div style="color: #28a745; font-size: 14px; margin-bottom: 3px;">✔️</div>
                        <div style="color: #28a745; font-size: 9px; font-weight: bold;">تم</div>
                    </div>
                `;
            } else if (dayNum === currentDailyDay) {
                if (canClaim) {
                    html += `
                        <div style="background: #222; border: 2px solid #ffcc00; border-radius: 8px; padding: 6px 2px; text-align: center; box-shadow: 0 0 6px rgba(255, 204, 0, 0.25);">
                            <div style="color: #fff; font-size: 10px; font-weight: bold; margin-bottom: 3px;">يوم ${dayNum}</div>
                            <div style="color: #ffcc00; font-size: 10px; font-weight: bold; margin-bottom: 4px;">${displayReward}</div>
                            <button id="daily-btn-${dayNum}" onclick="handleDailyClaim(${dayNum})" style="background: #28a745; color: white; border: none; border-radius: 4px; padding: 4px 0; font-size: 10px; cursor: pointer; width: 85%; animation: pulseGreen 2s infinite;">📺</button>
                        </div>
                    `;
                } else {
                    html += `
                        <div style="background: #222; border: 1px solid #555; border-radius: 8px; padding: 8px 2px; text-align: center;">
                            <div style="color: #fff; font-size: 10px; margin-bottom: 3px;">يوم ${dayNum}</div>
                            <div style="color: #ffcc00; font-size: 10px; margin-bottom: 4px;">${displayReward}</div>
                            <div style="color: #ff4444; font-size: 10px; font-weight: bold;">⏳</div>
                        </div>
                    `;
                }
            } else {
                html += `
                    <div style="background: #141414; border: 1px solid #2a2a2a; border-radius: 8px; padding: 8px 2px; text-align: center; opacity: 0.5;">
                        <div style="color: #777; font-size: 10px; margin-bottom: 3px;">يوم ${dayNum}</div>
                        <div style="color: #555; font-size: 14px; margin-bottom: 3px;">🔒</div>
                        <div style="color: #777; font-size: 9px;">${displayReward}</div>
                    </div>
                `;
            }
        }
        container.innerHTML = html;
    }

    if (window.farmIntervalId) {
        clearInterval(window.farmIntervalId);
    }

    window.farmIntervalId = setInterval(() => {
        const pData = window.PlayerData;
        if (!pData) return;
        
        let unclaim = parseFloat(pData.unclaimed || 0);
        let maxC = parseFloat(pData.max_cap || 10000);
        let hRate = parseFloat(pData.hourly_rate || 100);
        
        unclaim = Math.max(0, Math.min(unclaim, maxC));

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
            if (pct >= 100) {
                progressEl.style.background = 'linear-gradient(90deg, #ff4444, #cc0000)'; 
            } else {
                progressEl.style.background = 'linear-gradient(90deg, #0088cc, #00bfff)'; 
            }
            storageTextEl.innerText = `${Math.floor(unclaim).toLocaleString()} / ${maxC.toLocaleString()}`;
        }

        const claimBtn = document.getElementById('claim-btn');
        if (claimBtn) {
            if (claimCooldown > 0) {
                claimCooldown--;
                claimBtn.innerText = `انتظر ${claimCooldown} ثانية ⏳`;
                claimBtn.className = "btn-cooldown";
                claimBtn.disabled = true;
            } else {
                claimBtn.innerText = "تجميع الرصيد 📺";
                claimBtn.className = unclaim > 0 ? "btn-ready" : "";
                claimBtn.disabled = unclaim <= 0;
            }
        }
    }, 1000);

    // 📢 دالة تشغيل إعلان Monetag (للمكافآت اليومية)
    function showTelegramAd(statusCallback) {
        return new Promise((resolve) => {
            if (typeof window.show_11322720 === 'function') {
                if (statusCallback) statusCallback("جارٍ فتح الإعلان... ⏳");
                window.show_11322720().then(() => {
                    resolve(true);
                }).catch((error) => {
                    console.warn("تم إغلاق الإعلان أو حدث خطأ:", error);
                    let msg = "⚠️ لم تقم بمشاهدة الإعلان للنهاية، لذلك لم يتم منح المكافأة.";
                    if (window.Telegram && window.Telegram.WebApp) {
                        window.Telegram.WebApp.showAlert(msg);
                    } else {
                        alert(msg);
                    }
                    resolve(false); 
                });
            } else {
                let msg = "⚠️ عذراً، تعذر تحميل الإعلان. يرجى إيقاف مانع الإعلانات (Ad Blocker) والمحاولة مرة أخرى.";
                if (window.Telegram && window.Telegram.WebApp) {
                    window.Telegram.WebApp.showAlert(msg);
                } else {
                    alert(msg);
                }
                resolve(false);
            }
        });
    }

    // التسجيل اليومي يستخدم إعلانات Monetag
    window.handleDailyClaim = async function(day) {
        if (isClaimingDaily) return;
        
        if (!INIT_DATA) {
            alert("وضع المعاينة: تم استلام المكافأة اليومية بنجاح!");
            return;
        }

        const btn = document.getElementById(`daily-btn-${day}`);
        const originalHtml = btn ? btn.innerHTML : '';
        
        isClaimingDaily = true;
        
        const adWatched = await showTelegramAd((msg) => {
            if (btn) {
                btn.disabled = true;
                btn.innerHTML = "⏳";
            }
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
                    const successMsg = `🎉 مبروك! لقد استلمت ${resData.reward.toLocaleString()} ZN بنجاح!`;
                    if (window.Telegram && window.Telegram.WebApp) {
                        window.Telegram.WebApp.showAlert(successMsg);
                    } else {
                        alert(successMsg);
                    }
                    await window.fetchPlayerData(); 
                } else {
                    const errMsg = resData.error || "عفواً، لا يمكنك استلام المكافأة الآن.";
                    if (window.Telegram && window.Telegram.WebApp) {
                        window.Telegram.WebApp.showAlert(errMsg);
                    } else {
                        alert(errMsg);
                    }
                    if (btn) {
                        btn.disabled = false;
                        btn.innerHTML = originalHtml;
                    }
                }
            } catch (e) {
                if (btn) {
                    btn.disabled = false;
                    btn.innerHTML = originalHtml;
                }
            }
        } else {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalHtml;
            }
        }
        isClaimingDaily = false;
    };

    // زر تجميع الرصيد (مرتبط بـ OnClickA عبر الـ ID مباشرة)
    window.handleClaim = async function() {
        const pData = window.PlayerData;
        if (!pData || parseFloat(pData.unclaimed || 0) <= 0 || claimCooldown > 0) return;
        
        if (!INIT_DATA) {
            alert("وضع المعاينة: تم التجميع بنجاح!");
            claimCooldown = 5;
            window.PlayerData.unclaimed = 0;
            return;
        }

        const claimBtn = document.getElementById('claim-btn');

        // ⚠️ تأخير الكود 800 ملي ثانية (أقل من ثانية) 
        // عشان يدي فرصة لسكريبت OnClickA الموجود في ملف index إنه يلقط الضغطة الأول
        setTimeout(async () => {
            
            if (claimBtn) {
                claimBtn.disabled = true;
                claimBtn.innerText = "جاري الحفظ... 💾";
            }
            
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
                    if (claimBtn) {
                        claimBtn.disabled = false;
                        claimBtn.innerText = "تجميع الرصيد 📺";
                    }
                }
            } catch (e) {
                if (claimBtn) {
                    claimBtn.disabled = false;
                    claimBtn.innerText = "تجميع الرصيد 📺";
                }
            }
        }, 800); 
    };

    window.fetchPlayerData();

})();

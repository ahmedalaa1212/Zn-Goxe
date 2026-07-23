(function initFarm() {
    
    if (typeof window.Telegram === 'undefined' || !window.Telegram.WebApp.initData || !window.Telegram.WebApp.initDataUnsafe.user) {
        document.body.innerHTML = `
            <div style='color:#ff4444; text-align:center; padding:60px 20px; font-size:22px; font-weight:bold; background:#121212; height:100vh; display:flex; align-items:center; justify-content:center; flex-direction:column;'>
                <div style='font-size: 50px; margin-bottom: 20px;'>🚫</div>
                يجب فتح اللعبة من داخل تطبيق تيليجرام فقط!
            </div>
        `;
        return; 
    }

    const INIT_DATA = window.Telegram.WebApp.initData;

    const GAME_CONFIG = {
        maxUpgradesPerLevel: 15,
        dailyRewards: [3000, 6000, 10000, 15000, 25000, 40000, 100000],
        capacities: {0: 10000, 1: 20000, 2: 30000, 3: 50000, 4: 100000, 5: 200000, 6: 500000, 7: 1000000, 8: 2500000, 9: 5000000, 10: 10000000},
        miningRates: {1: 100, 2: 500, 3: 1500, 4: 4000, 5: 10000, 6: 25000, 7: 60000, 8: 150000, 9: 500000} 
    };

    let claimCooldown = 0; 
    let isClaimingDaily = false;

    window.fetchPlayerData = async function() {
        if (typeof window.fetchPlayerDataFromServer === 'function') {
            await window.fetchPlayerDataFromServer();
        }
    };

    window.updateFarmUI = function() {
        const pData = window.PlayerData;
        if (!pData) return;
        
        let bal = parseFloat(pData.balance || 0);
        let hRate = parseFloat(pData.hourly_rate || 0);
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
        
        // 🏛️ رسم الـ 9 كروت الخاصة بمستويات التعدين
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

    // 📅 نظام التسجيل اليومي (Check-in)
    function renderDailyRewards() {
        const container = document.getElementById('daily-rewards-container');
        const pData = window.PlayerData;
        if (!container || !pData) return;

        let html = '';
        let nowOffset = Date.now() + (window.timeOffset || 0);
        const lastClaim = new Date(pData.last_daily_claim_time || 0).getTime();
        const timePassed = nowOffset - lastClaim;
        const canClaim = timePassed >= (24 * 60 * 60 * 1000); 
        const currentDailyDay = parseInt(pData.daily_day || 1);

        for (let i = 0; i < 7; i++) {
            let dayNum = i + 1;
            let reward = GAME_CONFIG.dailyRewards[i].toLocaleString();

            if (dayNum < currentDailyDay) {
                html += `
                    <div style="min-width: 80px; background: rgba(40, 167, 69, 0.08); border: 1px solid #28a745; border-radius: 10px; padding: 10px; text-align: center;">
                        <div style="color: #888; font-size: 11px; margin-bottom: 4px;">اليوم ${dayNum}</div>
                        <div style="color: #28a745; font-size: 16px; margin-bottom: 4px;">✔️</div>
                        <div style="color: #28a745; font-size: 10px; font-weight: bold;">تم الاستلام</div>
                    </div>
                `;
            } else if (dayNum === currentDailyDay) {
                if (canClaim) {
                    html += `
                        <div style="min-width: 80px; background: #222; border: 2px solid #ffcc00; border-radius: 10px; padding: 10px; text-align: center; box-shadow: 0 0 10px rgba(255, 204, 0, 0.2);">
                            <div style="color: #fff; font-size: 11px; font-weight: bold; margin-bottom: 4px;">اليوم ${dayNum}</div>
                            <div style="color: #ffcc00; font-size: 12px; font-weight: bold; margin-bottom: 6px;">${reward}</div>
                            <button id="daily-btn-${dayNum}" onclick="handleDailyClaim(${dayNum})" style="background: #28a745; color: white; border: none; border-radius: 5px; padding: 5px; font-size: 10px; font-weight: bold; cursor: pointer; width: 100%; animation: pulseGreen 2s infinite;">استلام 📺</button>
                        </div>
                    `;
                } else {
                    html += `
                        <div style="min-width: 80px; background: #222; border: 1px solid #555; border-radius: 10px; padding: 10px; text-align: center;">
                            <div style="color: #fff; font-size: 11px; margin-bottom: 4px;">اليوم ${dayNum}</div>
                            <div style="color: #ffcc00; font-size: 12px; margin-bottom: 6px;">${reward}</div>
                            <div style="color: #ff4444; font-size: 10px; font-weight: bold;">انتظر ⏳</div>
                        </div>
                    `;
                }
            } else {
                html += `
                    <div style="min-width: 80px; background: #141414; border: 1px solid #2a2a2a; border-radius: 10px; padding: 10px; text-align: center; opacity: 0.5;">
                        <div style="color: #777; font-size: 11px; margin-bottom: 4px;">اليوم ${dayNum}</div>
                        <div style="color: #555; font-size: 16px; margin-bottom: 4px;">🔒</div>
                        <div style="color: #777; font-size: 10px;">${reward}</div>
                    </div>
                `;
            }
        }
        container.innerHTML = html;
    }

    // عداد التعدين بالثانية المحلي
    setInterval(() => {
        const pData = window.PlayerData;
        if (!pData) return;
        
        let unclaim = parseFloat(pData.unclaimed || 0);
        let maxC = parseFloat(pData.max_cap || 10000);
        let hRate = parseFloat(pData.hourly_rate || 0);
        
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

        const timerEl = document.getElementById('daily-timer');
        if (timerEl && pData.last_daily_claim_time) {
            let nowOffset = Date.now() + (window.timeOffset || 0);
            const lastDaily = new Date(pData.last_daily_claim_time).getTime();
            const timePassed = nowOffset - lastDaily;
            const timeLeft = (24 * 60 * 60 * 1000) - timePassed;
            
            if (timeLeft > 0) {
                timerEl.style.display = 'block';
                let h = Math.floor((timeLeft / (1000 * 60 * 60)) % 24).toString().padStart(2, '0');
                let m = Math.floor((timeLeft / 1000 / 60) % 60).toString().padStart(2, '0');
                let s = Math.floor((timeLeft / 1000) % 60).toString().padStart(2, '0');
                timerEl.innerText = `${h}:${m}:${s}`;
            } else {
                if (timerEl.style.display !== 'none') {
                    timerEl.style.display = 'none';
                    renderDailyRewards(); 
                }
            }
        }
    }, 1000);

    function showTelegramAd() {
        return new Promise((resolve) => {
            if (typeof window.show_11322720 !== 'function') {
                console.warn("[Monetag] الإعلانات محجوبة.");
                if (window.Telegram && window.Telegram.WebApp) {
                    window.Telegram.WebApp.showAlert("⚠️ يرجى إيقاف مانع الإعلانات (AdBlocker) لمشاهدة الإعلان والحصول على المكافأة!");
                } else {
                    alert("⚠️ يرجى إيقاف مانع الإعلانات للحصول على المكافأة!");
                }
                resolve(false); 
                return;
            }

            try {
                window.show_11322720().then(() => {
                    resolve(true); 
                }).catch(() => {
                    if (window.Telegram && window.Telegram.WebApp) {
                        window.Telegram.WebApp.showAlert("⚠️ يجب مشاهدة الإعلان بالكامل للحصول على المكافأة!");
                    } else {
                        alert("⚠️ يجب مشاهدة الإعلان بالكامل للحصول على المكافأة!");
                    }
                    resolve(false); 
                });
            } catch (err) {
                resolve(false);
            }
        });
    }

    window.handleDailyClaim = async function(day) {
        if (isClaimingDaily) return;
        const btn = document.getElementById(`daily-btn-${day}`);
        if (btn) {
            btn.disabled = true;
            btn.innerText = "جاري فتح الإعلان... ⏳";
        }
        
        isClaimingDaily = true;
        const adWatched = await showTelegramAd();
        
        if (adWatched) {
            if (btn) btn.innerText = "جاري الاستلام... ⏳";
            try {
                let response = await fetch('/api/daily_claim', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ initData: INIT_DATA })
                });

                let resData = await response.json();
                if (response.ok && resData.success) {
                    const successMsg = `🎉 مبروك! لقد استلمت ${resData.reward.toLocaleString()} ZN بنجاح!`;
                    if (window.Telegram && window.Telegram.WebApp) window.Telegram.WebApp.showAlert(successMsg);
                    else alert(successMsg);
                    
                    await window.fetchPlayerDataFromServer(); 
                } else {
                    const errMsg = resData.error || "عفواً، لا يمكنك استلام المكافأة الآن.";
                    if (window.Telegram && window.Telegram.WebApp) window.Telegram.WebApp.showAlert(errMsg);
                    else alert(errMsg);
                    if (btn) {
                        btn.disabled = false;
                        btn.innerText = "استلام 📺";
                    }
                }
            } catch (e) {
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = "استلام 📺";
                }
            }
        } else {
            if (btn) {
                btn.disabled = false;
                btn.innerText = "استلام 📺";
            }
        }
        isClaimingDaily = false;
    };

    window.handleClaim = async function() {
        const pData = window.PlayerData;
        if (!pData || parseFloat(pData.unclaimed || 0) <= 0 || claimCooldown > 0) return;
        
        const claimBtn = document.getElementById('claim-btn');
        if (claimBtn) {
            claimBtn.disabled = true;
            claimBtn.innerText = "جاري فتح الإعلان... ⏳";
        }

        const adWatched = await showTelegramAd();
        
        if (adWatched) {
            try {
                let response = await fetch('/api/claim', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ initData: INIT_DATA })
                });
                
                if (response.ok) {
                    await window.fetchPlayerDataFromServer(); 
                    claimCooldown = 60; 
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
        } else {
            if (claimBtn) {
                claimBtn.disabled = false;
                claimBtn.innerText = "تجميع الرصيد 📺";
            }
        }
    };

    window.updateFarmUI();
})();

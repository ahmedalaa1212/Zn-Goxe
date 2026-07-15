(function initFarm() {
    
    // حماية اللعبة: تعمل من داخل تليجرام فقط
    if (typeof window.Telegram === 'undefined' || !window.Telegram.WebApp.initDataUnsafe || !window.Telegram.WebApp.initDataUnsafe.user) {
        document.body.innerHTML = `
            <div style='color:#ff4444; text-align:center; padding:60px 20px; font-size:22px; font-weight:bold; background:#121212; height:100vh; display:flex; align-items:center; justify-content:center; flex-direction:column;'>
                <div style='font-size: 50px; margin-bottom: 20px;'>🚫</div>
                يجب فتح اللعبة من داخل تطبيق تيليجرام فقط!
            </div>
        `;
        return; 
    }

    const TELEGRAM_ID = window.Telegram.WebApp.initDataUnsafe.user.id.toString();

    // إعدادات اللعبة
    const GAME_CONFIG = {
        maxUpgradesPerLevel: 15,
        dailyRewards: [3000, 6000, 10000, 15000, 25000, 40000, 100000],
        capacities: {0: 10000, 1: 20000, 2: 30000, 3: 50000, 4: 100000, 5: 200000, 6: 500000, 7: 1000000, 8: 2500000, 9: 5000000, 10: 10000000},
        miningRates: {1: 100, 2: 500, 3: 1500, 4: 4000, 5: 10000, 6: 25000, 7: 60000, 8: 150000, 9: 500000} 
    };

    let claimCooldown = 0; 
    let currentDailyDay = parseInt(localStorage.getItem('zn_daily_day')) || 1;
    let lastDailyTime = parseInt(localStorage.getItem('zn_daily_time')) || 0;

    // جلب البيانات الأساسية من الفايربيس (السيرفر)
    window.fetchPlayerData = async function() {
        try {
            const response = await fetch(`/api/user_data?telegramId=${TELEGRAM_ID}`);
            const result = await response.json();
            
            if (result.success) {
                const dbData = result.data;
                
                // حساب سرعة التعدين
                let hRate = 0;
                let upgs = {};
                for(let i = 1; i <= 9; i++) {
                    let count = dbData[`lvl${i}_count`] || 0;
                    upgs[`lvl${i}`] = count;
                    hRate += count * GAME_CONFIG.miningRates[i];
                }
                
                let maxCap = GAME_CONFIG.capacities[dbData.storage_level || 0] || 10000;
                
                // حساب التعدين وتجنب الأرقام السالبة
                let unclaimed = 0;
                if (dbData.last_claim_time) {
                    let lastClaim = new Date(dbData.last_claim_time).getTime();
                    let now = Date.now();
                    let diffHours = Math.max(0, (now - lastClaim) / (1000 * 60 * 60)); // يمنع الوقت السالب
                    unclaimed = diffHours * hRate;
                    if (unclaimed > maxCap) unclaimed = maxCap;
                }

                window.PlayerData = {
                    tg_id: dbData.telegram_id,
                    balance: dbData.balance || 0,
                    hourly_rate: hRate,
                    max_cap: maxCap,
                    unclaimed: unclaimed,
                    upgrades: upgs,
                    storage_level: dbData.storage_level || 0
                };
                
                window.updateFarmUI();
            }
        } catch (e) {
            console.error("خطأ في الاتصال بالخادم:", e);
        }
    };

    window.updateFarmUI = function() {
        const pData = window.PlayerData;
        if (!pData) return;
        
        document.getElementById('farm-balance').innerText = `ZN: ${Math.floor(pData.balance).toLocaleString()}`;
        document.getElementById('farm-rate').innerText = `⚡ ${pData.hourly_rate.toLocaleString()}/س`;
        
        const fieldsContainer = document.getElementById('mining-fields');
        if (fieldsContainer) {
            let fieldsHTML = '';
            for (let i = 1; i <= 9; i++) {
                let count = (pData.upgrades && pData.upgrades[`lvl${i}`]) || 0;
                let isUnlocked = (i === 1) || (((pData.upgrades && pData.upgrades[`lvl${i-1}`]) || 0) > 0);
                let isMax = count >= GAME_CONFIG.maxUpgradesPerLevel;
                
                if (isMax) {
                    fieldsHTML += `
                        <div style="background: #333; border-radius: 10px; padding: 15px 5px; text-align: center; border: 1px solid #555; position: relative; overflow: hidden;">
                            <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; font-size: 18px; transform: rotate(-20deg);">MAX</div>
                            <div style="font-size: 24px; margin-bottom: 5px; opacity: 0.3;">🏛️</div>
                            <div style="color: #888; font-size: 12px; font-weight: bold;">LV ${i}</div>
                        </div>
                    `;
                } else if (count > 0) {
                    fieldsHTML += `
                        <div style="background: #1c1c1c; border-radius: 10px; padding: 15px 5px; text-align: center; border: 1px solid #0088cc; position: relative;">
                            <div style="position: absolute; top: -5px; right: -5px; background: #ffcc00; color: #000; font-weight: bold; border-radius: 50%; padding: 2px 6px; font-size: 11px; border: 2px solid #121212;">x${count}</div>
                            <div style="width: 30px; height: 30px; background: #ffcc00; border-radius: 50%; margin: 0 auto 5px auto; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 10px rgba(255, 204, 0, 0.3);">
                                <span style="font-size: 14px;">🏛️</span>
                            </div>
                            <div style="color: white; font-size: 12px; font-weight: bold;">LV ${i}</div>
                        </div>
                    `;
                } else if (isUnlocked) {
                    fieldsHTML += `
                        <div style="background: #1c1c1c; border-radius: 10px; padding: 15px 5px; text-align: center; border: 1px dashed #555;">
                            <div style="font-size: 20px; color: #555; margin-bottom: 5px;">🏛️</div>
                            <div style="color: #666; font-size: 11px; font-weight: bold;">متاح للشراء</div>
                        </div>
                    `;
                } else {
                    fieldsHTML += `
                        <div style="background: #151515; border-radius: 10px; padding: 15px 5px; text-align: center; border: 1px solid #222;">
                            <div style="font-size: 20px; color: #ffcc00; margin-bottom: 5px;">🔒</div>
                            <div style="color: #666; font-size: 12px; font-weight: bold;">مغلق</div>
                        </div>
                    `;
                }
            }
            fieldsContainer.innerHTML = fieldsHTML;
        }
        renderDailyRewards(); 
    };

    function renderDailyRewards() {
        const container = document.getElementById('daily-rewards-container');
        if (!container) return;

        let html = '';
        const now = Date.now();
        const timePassed = now - lastDailyTime;
        const canClaim = timePassed >= (24 * 60 * 60 * 1000); 

        for (let i = 0; i < 7; i++) {
            let dayNum = i + 1;
            let reward = GAME_CONFIG.dailyRewards[i].toLocaleString();

            if (dayNum < currentDailyDay) {
                html += `
                    <div style="min-width: 85px; background: rgba(40, 167, 69, 0.1); border: 1px solid #28a745; border-radius: 10px; padding: 10px; text-align: center;">
                        <div style="color: #888; font-size: 11px; margin-bottom: 5px;">اليوم ${dayNum}</div>
                        <div style="color: #28a745; font-size: 18px; margin-bottom: 5px;">✔️</div>
                        <div style="color: #28a745; font-size: 10px; font-weight: bold;">تم الاستلام</div>
                    </div>
                `;
            } else if (dayNum === currentDailyDay) {
                if (canClaim) {
                    html += `
                        <div style="min-width: 85px; background: #2a2a2a; border: 2px solid #ffcc00; border-radius: 10px; padding: 10px; text-align: center; box-shadow: 0 0 10px rgba(255, 204, 0, 0.3);">
                            <div style="color: #fff; font-size: 12px; font-weight: bold; margin-bottom: 5px;">اليوم ${dayNum}</div>
                            <div style="color: #ffcc00; font-size: 13px; font-weight: bold; margin-bottom: 8px;">${reward}</div>
                            <button onclick="handleDailyClaim(${dayNum}, ${GAME_CONFIG.dailyRewards[i]})" style="background: #28a745; color: white; border: none; border-radius: 5px; padding: 6px; font-size: 11px; font-weight: bold; cursor: pointer; width: 100%; animation: pulseGreen 2s infinite;">استلام 📺</button>
                        </div>
                    `;
                } else {
                    html += `
                        <div style="min-width: 85px; background: #2a2a2a; border: 1px solid #555; border-radius: 10px; padding: 10px; text-align: center;">
                            <div style="color: #fff; font-size: 11px; margin-bottom: 5px;">اليوم ${dayNum}</div>
                            <div style="color: #ffcc00; font-size: 13px; margin-bottom: 8px;">${reward}</div>
                            <div style="color: #ff4444; font-size: 10px; font-weight: bold;">انتظر ⏳</div>
                        </div>
                    `;
                }
            } else {
                html += `
                    <div style="min-width: 85px; background: #151515; border: 1px solid #333; border-radius: 10px; padding: 10px; text-align: center; opacity: 0.6;">
                        <div style="color: #777; font-size: 11px; margin-bottom: 5px;">اليوم ${dayNum}</div>
                        <div style="color: #555; font-size: 18px; margin-bottom: 5px;">🔒</div>
                        <div style="color: #777; font-size: 11px;">${reward}</div>
                    </div>
                `;
            }
        }
        container.innerHTML = html;
    }

    // لوب الواجهة (تم تعديل الخزان ليقف عند الحد الأقصى ولا يظهر سالب)
    setInterval(() => {
        const pData = window.PlayerData;
        if (!pData) return;
        
        // قفل رياضي يمنع أي رقم سالب ويمنع تخطي الحد الأقصى
        pData.unclaimed = Math.max(0, Math.min(pData.unclaimed, pData.max_cap));

        if (pData.unclaimed < pData.max_cap) {
            pData.unclaimed += pData.hourly_rate / 3600;
            // تأكيد مرة أخرى بعد الزيادة الوهمية
            if (pData.unclaimed >= pData.max_cap) {
                pData.unclaimed = pData.max_cap;
            }
        }

        const progressEl = document.getElementById('storage-progress');
        const storageTextEl = document.getElementById('storage-text');
        
        if (progressEl && storageTextEl) {
            let pct = (pData.unclaimed / pData.max_cap) * 100;
            pct = Math.max(0, Math.min(pct, 100)); // نسبة مئوية مضبوطة 100% كحد أقصى
            
            progressEl.style.width = `${pct}%`;
            if (pct >= 100) {
                progressEl.style.background = 'linear-gradient(90deg, #ff4444, #cc0000)'; 
            } else {
                progressEl.style.background = 'linear-gradient(90deg, #0088cc, #00bfff)'; 
            }
            storageTextEl.innerText = `${Math.floor(pData.unclaimed).toLocaleString()} / ${pData.max_cap.toLocaleString()}`;
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
                claimBtn.className = pData.unclaimed > 0 ? "btn-ready" : "";
                claimBtn.disabled = pData.unclaimed <= 0;
            }
        }

        const timerEl = document.getElementById('daily-timer');
        if (timerEl && currentDailyDay <= 7) {
            const now = Date.now();
            const timePassed = now - lastDailyTime;
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
            console.log("جارِ عرض الإعلان...");
            setTimeout(() => resolve(true), 2000); 
        });
    }

    window.handleDailyClaim = async function(day, rewardAmount) {
        const adWatched = await showTelegramAd();
        if (adWatched) {
            try {
                let response = await fetch('/api/daily_claim', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ telegramId: TELEGRAM_ID, reward: rewardAmount })
                });

                if (response.ok) {
                    currentDailyDay = day + 1;
                    lastDailyTime = Date.now();
                    localStorage.setItem('zn_daily_day', currentDailyDay);
                    localStorage.setItem('zn_daily_time', lastDailyTime);
                    
                    alert(`🎉 مبروك! استلمت ${rewardAmount.toLocaleString()} ZN بنجاح.`);
                    await window.fetchPlayerData(); 
                }
            } catch (e) {
                console.error("خطأ في المكافأة اليومية", e);
            }
        }
    };

    window.handleClaim = async function() {
        const pData = window.PlayerData;
        if (!pData || pData.unclaimed <= 0 || claimCooldown > 0) return;
        
        const adWatched = await showTelegramAd();
        if (adWatched) {
            try {
                let response = await fetch('/api/claim', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ telegramId: pData.tg_id, addedAmount: pData.unclaimed })
                });
                
                if (response.ok) {
                    await window.fetchPlayerData(); 
                    claimCooldown = 60; 
                }
            } catch (e) {
                console.error("خطأ في التجميع", e);
            }
        }
    };

    window.fetchPlayerData();
})();

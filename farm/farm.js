(function initFarm() {
    
    // إعدادات اللعبة الثابتة
    const GAME_CONFIG = {
        maxUpgradesPerLevel: 15,
        dailyRewards: [3000, 6000, 10000, 15000, 25000, 40000, 100000] // جوائز الـ 7 أيام
    };

    let claimCooldown = 0; 
    
    // قراءة حالة المكافأة اليومية من المتصفح (للتجربة حالياً)
    let currentDailyDay = parseInt(localStorage.getItem('zn_daily_day')) || 1;
    let lastDailyTime = parseInt(localStorage.getItem('zn_daily_time')) || 0;

    // دالة تحديث الواجهة الرئيسية (رصيد + تعدين)
    window.updateFarmUI = function() {
        const pData = window.PlayerData;
        if (!pData) return;
        
        document.getElementById('farm-balance').innerText = `ZN: ${Math.floor(pData.balance).toLocaleString()}`;
        document.getElementById('farm-rate').innerText = `⚡ ${pData.hourly_rate.toLocaleString()}/س`;
        
        const progressEl = document.getElementById('storage-progress');
        const storageTextEl = document.getElementById('storage-text');
        
        if (progressEl && storageTextEl) {
            let pct = (pData.unclaimed / pData.max_cap) * 100;
            if (pct >= 100) {
                pct = 100;
                progressEl.style.background = 'linear-gradient(90deg, #ff4444, #cc0000)'; 
            } else {
                progressEl.style.background = 'linear-gradient(90deg, #0088cc, #00bfff)'; 
            }
            progressEl.style.width = `${pct}%`;
            storageTextEl.innerText = `${Math.floor(pData.unclaimed).toLocaleString()} / ${pData.max_cap.toLocaleString()}`;
        }
        
        // رسم الخانات الـ 9
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
                    // تم الشراء ولسه مش ماكس
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
                    // مفتوح بس مشتروش لسه
                    fieldsHTML += `
                        <div style="background: #1c1c1c; border-radius: 10px; padding: 15px 5px; text-align: center; border: 1px dashed #555;">
                            <div style="font-size: 20px; color: #555; margin-bottom: 5px;">🏛️</div>
                            <div style="color: #666; font-size: 11px; font-weight: bold;">متاح للشراء</div>
                        </div>
                    `;
                } else {
                    // مقفول
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

        renderDailyRewards(); // تحديث مكافآت الـ 7 أيام
    };

    // دالة رسم الـ 7 أيام
    function renderDailyRewards() {
        const container = document.getElementById('daily-rewards-container');
        if (!container) return;

        let html = '';
        const now = Date.now();
        const timePassed = now - lastDailyTime;
        const canClaim = timePassed >= (24 * 60 * 60 * 1000); // عدى 24 ساعة؟

        for (let i = 0; i < 7; i++) {
            let dayNum = i + 1;
            let reward = GAME_CONFIG.dailyRewards[i].toLocaleString();

            if (dayNum < currentDailyDay) {
                // أيام سابقة (تم الاستلام)
                html += `
                    <div style="min-width: 85px; background: rgba(40, 167, 69, 0.1); border: 1px solid #28a745; border-radius: 10px; padding: 10px; text-align: center;">
                        <div style="color: #888; font-size: 11px; margin-bottom: 5px;">اليوم ${dayNum}</div>
                        <div style="color: #28a745; font-size: 18px; margin-bottom: 5px;">✔️</div>
                        <div style="color: #28a745; font-size: 10px; font-weight: bold;">تم الاستلام</div>
                    </div>
                `;
            } else if (dayNum === currentDailyDay) {
                // اليوم الحالي
                if (canClaim) {
                    // متاح للاستلام
                    html += `
                        <div style="min-width: 85px; background: #2a2a2a; border: 2px solid #ffcc00; border-radius: 10px; padding: 10px; text-align: center; box-shadow: 0 0 10px rgba(255, 204, 0, 0.3);">
                            <div style="color: #fff; font-size: 12px; font-weight: bold; margin-bottom: 5px;">اليوم ${dayNum}</div>
                            <div style="color: #ffcc00; font-size: 13px; font-weight: bold; margin-bottom: 8px;">${reward}</div>
                            <button onclick="handleDailyClaim(${dayNum}, ${GAME_CONFIG.dailyRewards[i]})" style="background: #28a745; color: white; border: none; border-radius: 5px; padding: 6px; font-size: 11px; font-weight: bold; cursor: pointer; width: 100%; animation: pulseGreen 2s infinite;">استلام 📺</button>
                        </div>
                    `;
                } else {
                    // منتظر الـ 24 ساعة
                    html += `
                        <div style="min-width: 85px; background: #2a2a2a; border: 1px solid #555; border-radius: 10px; padding: 10px; text-align: center;">
                            <div style="color: #fff; font-size: 11px; margin-bottom: 5px;">اليوم ${dayNum}</div>
                            <div style="color: #ffcc00; font-size: 13px; margin-bottom: 8px;">${reward}</div>
                            <div style="color: #ff4444; font-size: 10px; font-weight: bold;">انتظر ⏳</div>
                        </div>
                    `;
                }
            } else {
                // أيام قادمة (مقفولة)
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

    // دالة التعامل مع وقت الـ 24 ساعة
    setInterval(() => {
        const pData = window.PlayerData;
        if (!pData) return;
        
        // 1. زيادة التخزين الوهمية أمام اللاعب
        if (pData.unclaimed < pData.max_cap) {
            pData.unclaimed += pData.hourly_rate / 3600;
            if (pData.unclaimed > pData.max_cap) pData.unclaimed = pData.max_cap;
            
            // تحديث الشريط فقط بدون إعادة رسم كل حاجة عشان الأداء
            const progressEl = document.getElementById('storage-progress');
            const storageTextEl = document.getElementById('storage-text');
            if (progressEl && storageTextEl) {
                let pct = (pData.unclaimed / pData.max_cap) * 100;
                progressEl.style.width = `${pct}%`;
                storageTextEl.innerText = `${Math.floor(pData.unclaimed).toLocaleString()} / ${pData.max_cap.toLocaleString()}`;
            }
        }

        // 2. معالجة زر التجميع (الـ 60 ثانية)
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

        // 3. معالجة عداد الـ 24 ساعة للمكافأة اليومية
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
                    renderDailyRewards(); // إعادة الرسم فوراً لما الوقت يخلص
                }
            }
        }
    }, 1000);

    function showTelegramAd() {
        return new Promise((resolve) => {
            console.log("جارِ عرض الإعلان...");
            setTimeout(() => resolve(true), 2000); // الإعلان الوهمي 
        });
    }

    // استلام المكافأة اليومية
    window.handleDailyClaim = async function(day, rewardAmount) {
        const adWatched = await showTelegramAd();
        if (adWatched) {
            // تحديث البيانات محلياً
            currentDailyDay = day + 1;
            lastDailyTime = Date.now();
            localStorage.setItem('zn_daily_day', currentDailyDay);
            localStorage.setItem('zn_daily_time', lastDailyTime);

            // إضافة الرصيد (ملاحظة: هذا للواجهة فقط، سيتم حذفه عند التحديث من السيرفر)
            if (window.PlayerData) {
                window.PlayerData.balance += rewardAmount;
                window.updateFarmUI();
            }

            alert(`🎉 مبروك! استلمت ${rewardAmount.toLocaleString()} ZN بنجاح.`);
            renderDailyRewards();
        }
    };

    window.handleClaim = async function() {
        const pData = window.PlayerData;
        if (pData.unclaimed <= 0 || claimCooldown > 0) return;
        
        const adWatched = await showTelegramAd();
        if (adWatched) {
            try {
                let response = await fetch('/api/claim', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ tg_id: pData.tg_id })
                });
                
                if (response.ok) {
                    await pData.fetchUpdates();
                    claimCooldown = 60; 
                }
            } catch (e) {
                console.error("خطأ في التجميع", e);
            }
        }
    };

    // إضافة رصيد وهمي للتجربة (بناءً على طلبك)
    window.addTestBalance = function() {
        if(window.PlayerData) {
            window.PlayerData.balance += 50000;
            window.updateFarmUI();
            alert("تم إضافة 50,000 ZN للتجربة!\n⚠️ ملحوظة هامة: هذا الرصيد في الواجهة فقط، لكي تتمكن من 'الشراء الفعلي' يجب تعديل رصيدك داخل الفيربيس لأن المتجر يتأكد من السيرفر.");
        }
    };
    
    setTimeout(window.updateFarmUI, 500);
})();

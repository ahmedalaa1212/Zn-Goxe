(function initFarm() {
    // 💡 هذا المتغير يسهل عليك تعديل أي سرعة مستقبلاً من مكان واحد
    const GAME_CONFIG = {
        maxUpgradesPerLevel: 15,
        levelsBaseRate: {
            1: 2,   // مستوى 1 يعطي 2 في الساعة لكل ترقية
            2: 8,   // مستوى 2 يعطي 8
            3: 15,  // مستوى 3 يعطي 15
            4: 30,  // الأرقام دي أمثلة تقدر تغيرها براحتك
            5: 60,
            6: 120,
            7: 250,
            8: 500,
            9: 1000
        }
    };

    let claimCooldown = 0; // عداد الـ 60 ثانية

    window.updateFarmUI = function() {
        const pData = window.PlayerData;
        if (!pData) return;
        
        // 1. تحديث الرصيد والسرعة
        document.getElementById('farm-balance').innerText = `ZN: ${Math.floor(pData.balance).toLocaleString()}`;
        document.getElementById('farm-rate').innerText = `⚡ ${pData.hourly_rate.toLocaleString()}/س`;
        
        // 2. تحديث شريط التخزين (يتغير للأحمر لو فل)
        const progressEl = document.getElementById('storage-progress');
        const storageTextEl = document.getElementById('storage-text');
        
        if (progressEl && storageTextEl) {
            let pct = (pData.unclaimed / pData.max_cap) * 100;
            if (pct >= 100) {
                pct = 100;
                progressEl.style.background = 'linear-gradient(90deg, #ff4444, #cc0000)'; // لون أحمر
            } else {
                progressEl.style.background = 'linear-gradient(90deg, #0088cc, #00bfff)'; // لون أزرق
            }
            progressEl.style.width = `${pct}%`;
            storageTextEl.innerText = `${Math.floor(pData.unclaimed).toLocaleString()} / ${pData.max_cap.toLocaleString()}`;
        }
        
        // 3. رسم شبكة الـ 9 مستويات (3 عواميد)
        const fieldsContainer = document.getElementById('mining-fields');
        if (fieldsContainer) {
            let fieldsHTML = '';
            for (let i = 1; i <= 9; i++) {
                let count = pData.upgrades[`lvl${i}`] || 0;
                let isUnlocked = (i === 1) || ((pData.upgrades[`lvl${i-1}`] || 0) > 0);
                let isMax = count >= GAME_CONFIG.maxUpgradesPerLevel;
                
                if (isMax) {
                    // تصميم المستوى المكتمل (MAX - رمادي)
                    fieldsHTML += `
                        <div style="background: #333; border-radius: 10px; padding: 15px 5px; text-align: center; border: 1px solid #555; position: relative; overflow: hidden;">
                            <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.6); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; font-size: 18px; transform: rotate(-20deg);">MAX</div>
                            <div style="font-size: 24px; margin-bottom: 5px; opacity: 0.3;">🏛️</div>
                            <div style="color: #888; font-size: 12px; font-weight: bold;">LV ${i}</div>
                        </div>
                    `;
                } else if (isUnlocked) {
                    // تصميم المستوى المفتوح
                    fieldsHTML += `
                        <div style="background: #1c1c1c; border-radius: 10px; padding: 15px 5px; text-align: center; border: 1px solid #333;">
                            <div style="width: 30px; height: 30px; background: #ffcc00; border-radius: 50%; margin: 0 auto 5px auto; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 10px rgba(255, 204, 0, 0.3);">
                                <span style="font-size: 14px;">🏛️</span>
                            </div>
                            <div style="color: white; font-size: 12px; font-weight: bold; margin-bottom: 2px;">LV ${i}</div>
                            <div style="color: #0088cc; font-size: 14px; font-weight: bold;">x${count}</div>
                        </div>
                    `;
                } else {
                    // تصميم المستوى المغلق
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
    };

    // العداد البصري لزيادة التخزين وتحديث زر التجميع
    setInterval(() => {
        const pData = window.PlayerData;
        if (!pData) return;
        
        // زيادة التخزين أمام اللاعب
        if (pData.unclaimed < pData.max_cap) {
            pData.unclaimed += pData.hourly_rate / 3600;
            if (pData.unclaimed > pData.max_cap) pData.unclaimed = pData.max_cap;
            window.updateFarmUI(); // تحديث الشريط
        }

        // معالجة زر التجميع (الـ 60 ثانية)
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
    }, 1000);

    // دالة محاكاة تشغيل إعلان تليجرام
    function showTelegramAd() {
        return new Promise((resolve) => {
            // هنا هيتم ربط كود مزود الإعلانات (زي Adsgram) مستقبلاً
            // حالياً هنعمل محاكاة كأن الإعلان بيظهر لمدة 3 ثواني
            console.log("جارِ عرض الإعلان...");
            setTimeout(() => {
                console.log("انتهى الإعلان.");
                resolve(true); // اللاعب شاهد الإعلان بنجاح
            }, 3000); 
        });
    }

    // دالة زر التجميع (إعلان -> سيرفر -> 60 ثانية)
    window.handleClaim = async function() {
        const pData = window.PlayerData;
        if (pData.unclaimed <= 0 || claimCooldown > 0) return;
        
        // 1. تشغيل الإعلان أولاً
        const adWatched = await showTelegramAd();
        
        if (adWatched) {
            // 2. إذا شاهد الإعلان، نكلم السيرفر يضيف الرصيد
            try {
                let response = await fetch('/api/claim', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ tg_id: pData.tg_id })
                });
                
                if (response.ok) {
                    await pData.fetchUpdates();
                    // 3. تفعيل عداد الـ 60 ثانية
                    claimCooldown = 60; 
                }
            } catch (e) {
                console.error("خطأ في التجميع", e);
            }
        }
    };

    // دالة استلام المكافأة اليومية
    window.handleDaily = async function() {
        // تشغيل الإعلان للمكافأة اليومية
        const adWatched = await showTelegramAd();
        if (adWatched) {
            alert("تم استلام المكافأة اليومية بنجاح! (سيتم ربطها بالباك إند في الخطوة القادمة)");
            // سنضيف كود الباك إند الخاص بها لاحقاً
        }
    };
    
    // تشغيل أولي
    setTimeout(window.updateFarmUI, 500);
})();

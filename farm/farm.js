(function initFarm() {
    // دالة لتحديث الواجهة بناءً على البيانات العالمية المجلوبة من السيرفر
    window.updateFarmUI = function() {
        const pData = window.PlayerData;
        
        const balanceEl = document.getElementById('farm-balance');
        const rateEl = document.getElementById('farm-rate');
        const storageTextEl = document.getElementById('storage-text');
        const progressEl = document.getElementById('storage-progress');
        const fieldsContainer = document.getElementById('mining-fields');
        
        if (balanceEl) balanceEl.innerText = `ZN: ${pData.balance.toLocaleString()}`;
        if (rateEl) rateEl.innerText = `⚡ ${pData.hourly_rate.toLocaleString()}/س`;
        
        // حساب نسبة امتلاء المخزن
        if (storageTextEl && progressEl) {
            let pct = (pData.unclaimed / pData.max_cap) * 100;
            if (pct > 100) pct = 100;
            progressEl.style.width = `${pct}%`;
            storageTextEl.innerText = `${Math.floor(pData.unclaimed).toLocaleString()} / ${pData.max_cap.toLocaleString()}`;
        }
        
        // رندر الحقول الـ 10 بناءً على ترقيات اللاعب الحقيقية من الفايربيس
        if (fieldsContainer) {
            let fieldsHTML = '';
            for (let i = 1; i <= 10; i++) {
                let count = pData.upgrades[`lvl${i}`] || 0;
                // الحقل يفتح إذا كان المستوى الأول أو تم شراء ترقية واحدة على الأقل من المستوى السابق
                let isUnlocked = (i === 1) || ((pData.upgrades[`lvl${i-1}`] || 0) > 0);
                
                fieldsHTML += `
                    <div style="background: ${isUnlocked ? '#1c1c1c' : '#111'}; padding: 15px; border-radius: 10px; border: 1px solid ${isUnlocked ? '#444' : '#222'}; color: ${isUnlocked ? '#fff' : '#555'};">
                        ${isUnlocked ? `
                            <div style="font-size: 20px; color: #ffcc00; margin-bottom: 5px;">🪙</div>
                            <div style="font-size: 14px; font-weight: bold;">LV ${i}</div>
                            <div style="font-size: 12px; color: #0088cc;">x${count}</div>
                        ` : `
                            <div style="font-size: 20px; margin-bottom: 5px;">🔒</div>
                            <div style="font-size: 12px;">مغلق</div>
                        `}
                    </div>
                `;
            }
            fieldsContainer.innerHTML = fieldsHTML;
        }
    };

    // عداد بصري يزود الرصيد المستحق للتجميع ثانية بثانية أمام عين اللاعب للإثارة الحماسية
    setInterval(() => {
        const pData = window.PlayerData;
        if (!pData.tg_id) return;
        
        let ratePerSecond = pData.hourly_rate / 3600;
        if (pData.unclaimed < pData.max_cap) {
            pData.unclaimed += ratePerSecond;
            if (pData.unclaimed > pData.max_cap) pData.unclaimed = pData.max_cap;
            
            const storageTextEl = document.getElementById('storage-text');
            const progressEl = document.getElementById('storage-progress');
            if (storageTextEl && progressEl) {
                let pct = (pData.unclaimed / pData.max_cap) * 100;
                progressEl.style.width = `${pct}%`;
                storageTextEl.innerText = `${Math.floor(pData.unclaimed).toLocaleString()} / ${pData.max_cap.toLocaleString()}`;
            }
        }
    }, 1000);

    // دالة كليك لتجميع الأرباح وإرسالها للسيرفر
    window.triggerClaimFromBtn = async function() {
        const pData = window.PlayerData;
        if (!pData.tg_id || pData.unclaimed <= 0) return;
        
        const btn = document.getElementById('claim-btn');
        if (btn) btn.disabled = true;
        
        try {
            let response = await fetch('/api/claim', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ tg_id: pData.tg_id })
            });
            if (response.ok) {
                await pData.fetchUpdates();
            }
        } catch (e) {
            console.error(e);
        } finally {
            if (btn) btn.disabled = false;
        }
    };
    
    // تشغيل أولي
    window.updateFarmUI();
})();

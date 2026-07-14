(function initShop() {
    
    // 💡 لوحة التحكم في الأرقام (تعدل الأسعار براحتك من هنا)
    const SHOP_CONFIG = {
        maxUpgrades: 15, // الحد الأقصى 15 مرة 
        
        // أسعار مستويات التعدين الـ 9 
        miningPrices: {
            1: 1000, 2: 5000, 3: 15000, 4: 40000, 5: 100000,
            6: 250000, 7: 600000, 8: 1500000, 9: 5000000
        },
        
        // أسعار المخازن الـ 10 
        storagePrices: {
            1: 500, 2: 2500, 3: 8000, 4: 20000, 5: 50000,
            6: 120000, 7: 300000, 8: 750000, 9: 2000000, 10: 5000000
        },
        
        // رابط محفظة التليجرام الخاصة بك للإيداع
        walletDepositLink: "https://t.me/wallet" 
    };

    // التبديل بين التعدين والمخازن
    window.switchShopTab = function(tab) {
        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');
        const btnMining = document.getElementById('tab-mining');
        const btnStorage = document.getElementById('tab-storage');

        if (tab === 'mining') {
            miningSec.style.display = 'grid';
            storageSec.style.display = 'none';
            btnMining.style.background = '#0088cc';
            btnStorage.style.background = '#333';
        } else {
            miningSec.style.display = 'none';
            storageSec.style.display = 'grid';
            btnMining.style.background = '#333';
            btnStorage.style.background = '#0088cc';
        }
    };

    // توجيه اللاعب لمحفظة التليجرام
    window.buyWithUSDT = function(amount) {
        alert(`جاري توجيهك لشراء باقة ${amount} USDT...`);
        window.open(SHOP_CONFIG.walletDepositLink, '_blank');
    };

    // تحديث واجهة المتجر
    window.updateShopUI = function() {
        const pData = window.PlayerData;
        if (!pData) return;

        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');

        // رسم مستويات التعدين (9 مستويات)
        if (miningSec) {
            let html = '';
            for (let i = 1; i <= 9; i++) {
                let count = pData.upgrades[`lvl${i}`] || 0;
                let price = SHOP_CONFIG.miningPrices[i];
                let isMax = count >= SHOP_CONFIG.maxUpgrades;
                let canAfford = pData.balance >= price;

                html += `
                    <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 10px; padding: 12px; text-align: center; position: relative; overflow: hidden;">
                        ${isMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; font-size: 20px; z-index: 10;">الحد الأقصى MAX</div>` : ''}
                        <div style="font-size: 24px; margin-bottom: 5px;">🏛️</div>
                        <div style="color: #fff; font-weight: bold; font-size: 14px;">مستوى ${i}</div>
                        <div style="color: #0088cc; font-size: 12px; margin-bottom: 10px;">تم الشراء: ${count} / ${SHOP_CONFIG.maxUpgrades}</div>
                        <button onclick="buyShopItem('speed', ${i}, ${price})" 
                            style="width: 100%; padding: 8px; background: ${canAfford ? '#ffcc00' : '#444'}; color: ${canAfford ? '#000' : '#888'}; border: none; border-radius: 6px; font-weight: bold; cursor: ${canAfford ? 'pointer' : 'not-allowed'};">
                            ${price.toLocaleString()} ZN
                        </button>
                    </div>
                `;
            }
            miningSec.innerHTML = html;
        }

        // رسم المخازن (10 مخازن)
        if (storageSec) {
            let html = '';
            for (let i = 1; i <= 10; i++) {
                let count = (pData.storage_upgrades && pData.storage_upgrades[`store${i}`]) || 0;
                let price = SHOP_CONFIG.storagePrices[i];
                let isMax = count >= SHOP_CONFIG.maxUpgrades;
                let canAfford = pData.balance >= price;

                html += `
                    <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 10px; padding: 12px; text-align: center; position: relative; overflow: hidden;">
                        ${isMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; font-size: 20px; z-index: 10;">الحد الأقصى MAX</div>` : ''}
                        <div style="font-size: 24px; margin-bottom: 5px;">📦</div>
                        <div style="color: #fff; font-weight: bold; font-size: 14px;">مخزن ${i}</div>
                        <div style="color: #0088cc; font-size: 12px; margin-bottom: 10px;">تم الشراء: ${count} / ${SHOP_CONFIG.maxUpgrades}</div>
                        <button onclick="buyShopItem('storage', ${i}, ${price})" 
                            style="width: 100%; padding: 8px; background: ${canAfford ? '#0088cc' : '#444'}; color: ${canAfford ? '#fff' : '#888'}; border: none; border-radius: 6px; font-weight: bold; cursor: ${canAfford ? 'pointer' : 'not-allowed'};">
                            ${price.toLocaleString()} ZN
                        </button>
                    </div>
                `;
            }
            storageSec.innerHTML = html;
        }
    };

    // دالة الشراء مربوطة بالباك إند
    window.buyShopItem = async function(type, level, price) {
        const pData = window.PlayerData;
        if (!pData || pData.balance < price) return; 

        try {
            let response = await fetch('/api/buy', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    tg_id: pData.tg_id,
                    type: type, 
                    level: level,
                    price: price 
                })
            });

            if (response.ok) {
                await pData.fetchUpdates(); 
                window.updateShopUI(); 
                // تحديث المزرعة لو كانت موجودة
                if (typeof window.updateFarmUI === 'function') {
                    window.updateFarmUI(); 
                }
            } else {
                alert("حدث خطأ أثناء الشراء، تأكد من رصيدك.");
            }
        } catch (e) {
            console.error(e);
        }
    };

    // تشغيل أولي
    setTimeout(window.updateShopUI, 500);
})();

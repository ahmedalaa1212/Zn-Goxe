(function initShop() {
    
    const SHOP_CONFIG = {
        maxMiningUpgrades: 15, 
        miningPrices: { 1: 1000, 2: 5000, 3: 15000, 4: 40000, 5: 100000, 6: 250000, 7: 600000, 8: 1500000, 9: 5000000 },
        storagePrices: { 1: 500, 2: 2500, 3: 8000, 4: 20000, 5: 50000, 6: 120000, 7: 300000, 8: 750000, 9: 2000000, 10: 5000000 },
        storageCapacities: { 1: 20000, 2: 30000, 3: 50000, 4: 100000, 5: 200000, 6: 500000, 7: 1000000, 8: 2500000, 9: 5000000, 10: 10000000 }
    };

    window.updateShopUI = function() {
        const pData = window.PlayerData; // البيانات اللي راجعة من الفيربيس
        if (!pData) return;

        // تحديث الرصيد والسرعة فوق خالص
        document.getElementById('shop-balance').innerText = `ZN: ${Math.floor(pData.balance).toLocaleString()}`;
        document.getElementById('shop-rate').innerText = `⚡ ${pData.hourly_rate.toLocaleString()}/س`;

        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');

        // 1. رسم مستويات التعدين
        if (miningSec) {
            let html = '';
            for (let i = 1; i <= 9; i++) {
                let count = (pData.upgrades && pData.upgrades[`lvl${i}`]) || 0;
                let price = SHOP_CONFIG.miningPrices[i];
                let isMax = count >= SHOP_CONFIG.maxMiningUpgrades;
                let canAfford = pData.balance >= price;

                html += `
                    <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 10px; padding: 12px; text-align: center; position: relative;">
                        ${isMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.75); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00;">MAX</div>` : ''}
                        <div style="font-size: 24px; margin-bottom: 5px;">🏛️</div>
                        <div style="color: #fff; font-weight: bold;">مستوى ${i}</div>
                        <div style="color: #0088cc; font-size: 12px; margin-bottom: 10px;">تم الشراء: ${count}/${SHOP_CONFIG.maxMiningUpgrades}</div>
                        <button onclick="buyShopItem('speed', ${i}, ${price})" 
                            style="width: 100%; padding: 8px; background: ${canAfford && !isMax ? '#ffcc00' : '#444'}; color: ${canAfford && !isMax ? '#000' : '#888'}; border: none; border-radius: 6px; font-weight: bold;" ${isMax ? 'disabled' : ''}>
                            ${price.toLocaleString()} ZN
                        </button>
                    </div>
                `;
            }
            miningSec.innerHTML = html;
        }

        // 2. رسم المخازن بالمنطق الجديد للفيربيس (يقفل الأقل تلقائياً بلون رمادي)
        if (storageSec) {
            let html = '';
            let currentStorageLvl = pData.storage_level || 1; 

            for (let i = 1; i <= 10; i++) {
                let price = SHOP_CONFIG.storagePrices[i];
                let capacity = SHOP_CONFIG.storageCapacities[i];
                let isPassedOrMax = i <= currentStorageLvl;
                let canAfford = pData.balance >= price;

                html += `
                    <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 10px; padding: 12px; text-align: center; position: relative;">
                        ${isPassedOrMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.75); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00;">انتهاء MAX</div>` : ''}
                        <div style="font-size: 24px; margin-bottom: 5px;">📦</div>
                        <div style="color: #fff; font-weight: bold;">مخزن ${i}</div>
                        <div style="color: #0088cc; font-size: 11px; margin-bottom: 10px;">السعة: ${capacity.toLocaleString()} ZN</div>
                        <button onclick="buyShopItem('storage', ${i}, ${price})" 
                            style="width: 100%; padding: 8px; background: ${canAfford && !isPassedOrMax ? '#0088cc' : '#444'}; color: ${canAfford && !isPassedOrMax ? '#fff' : '#888'}; border: none; border-radius: 6px; font-weight: bold;" ${isPassedOrMax ? 'disabled' : ''}>
                            ${price.toLocaleString()} ZN
                        </button>
                    </div>
                `;
            }
            storageSec.innerHTML = html;
        }
    };

    window.buyShopItem = async function(type, level, price) {
        const pData = window.PlayerData;
        if (!pData || pData.balance < price) return; 

        try {
            let response = await fetch('/api/buy', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ tg_id: pData.tg_id, type: type, level: level })
            });

            if (response.ok) {
                let resData = await response.json();
                window.PlayerData = resData.user; // تحديث الكاش المحلي فوراً ببيانات الفيربيس الجديدة
                window.updateShopUI(); 
                if (typeof window.updateFarmUI === 'function') window.updateFarmUI(); 
            } else {
                alert("فشلت العملية، السيرفر رفض الشراء.");
            }
        } catch (e) {
            console.error(e);
        }
    };

    setTimeout(window.updateShopUI, 500);
})();

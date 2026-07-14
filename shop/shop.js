(function initShop() {
    // 💡 مطابقة تماماً للـ CONFIG الموجود في السيرفر بتاعك
    const SHOP_CONFIG = {
        maxMiningUpgrades: 15,
        miningPrices: { 1: 1000, 2: 5000, 3: 15000, 4: 40000, 5: 100000, 6: 250000, 7: 600000, 8: 1500000, 9: 5000000 },
        storagePrices: { 1: 500, 2: 2500, 3: 8000, 4: 20000, 5: 50000, 6: 120000, 7: 300000, 8: 750000, 9: 2000000, 10: 5000000 },
        storageCapacities: { 1: 20000, 2: 30000, 3: 50000, 4: 100000, 5: 200000, 6: 500000, 7: 1000000, 8: 2500000, 9: 5000000, 10: 10000000 }
    };

    window.updateShopUI = function() {
        const pData = window.PlayerData;
        if (!pData) return;

        // تحديث الرصيد والسرعة
        document.getElementById('shop-balance').innerText = `ZN: ${Math.floor(pData.balance || 0).toLocaleString()}`;
        document.getElementById('shop-rate').innerText = `⚡ ${ (pData.hourly_rate || 0).toLocaleString()}/س`;

        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');

        // 1. رسم مستويات التعدين (9 مستويات)
        if (miningSec) {
            let html = '';
            for (let i = 1; i <= 9; i++) {
                let count = (pData.upgrades && pData.upgrades[`lvl${i}`]) || 0;
                let price = SHOP_CONFIG.miningPrices[i];
                let isMax = count >= SHOP_CONFIG.maxMiningUpgrades;
                let canAfford = pData.balance >= price;

                html += `
                    <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 10px; padding: 12px; text-align: center; position: relative;">
                        ${isMax ? `<div style="position: absolute; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); display:flex; align-items:center; justify-content:center; color:#ffcc00; font-weight:bold; z-index:10;">MAX</div>` : ''}
                        <div style="font-size: 20px;">🏛️</div>
                        <div style="color: #fff; font-size: 13px;">مستوى ${i}</div>
                        <div style="color: #0088cc; font-size: 11px; margin-bottom: 5px;">${count}/${SHOP_CONFIG.maxMiningUpgrades}</div>
                        <button onclick="buyShopItem('speed', ${i}, ${price})" 
                            style="width: 100%; padding: 6px; background: ${canAfford && !isMax ? '#ffcc00' : '#444'}; color: ${canAfford && !isMax ? '#000' : '#888'}; border:none; border-radius: 5px; font-weight:bold; cursor:pointer;" ${isMax ? 'disabled' : ''}>
                            ${price.toLocaleString()} ZN
                        </button>
                    </div>`;
            }
            miningSec.innerHTML = html;
        }

        // 2. رسم المخازن (10 مستويات) - اللوجيك: اللي أقل من الحالي رمادي
        if (storageSec) {
            let html = '';
            let currentLvl = pData.storage_level || 1;

            for (let i = 1; i <= 10; i++) {
                let price = SHOP_CONFIG.storagePrices[i];
                let cap = SHOP_CONFIG.storageCapacities[i];
                let isPassed = i <= currentLvl;
                let canAfford = pData.balance >= price;

                html += `
                    <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 10px; padding: 12px; text-align: center; position: relative;">
                        ${isPassed ? `<div style="position: absolute; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.8); display:flex; align-items:center; justify-content:center; color:#ffcc00; font-weight:bold; z-index:10;">MAX</div>` : ''}
                        <div style="font-size: 20px;">📦</div>
                        <div style="color: #fff; font-size: 13px;">مخزن ${i}</div>
                        <div style="color: #0088cc; font-size: 11px; margin-bottom: 5px;">السعة: ${cap.toLocaleString()}</div>
                        <button onclick="buyShopItem('storage', ${i}, ${price})" 
                            style="width: 100%; padding: 6px; background: ${canAfford && !isPassed ? '#0088cc' : '#444'}; color: ${canAfford && !isPassed ? '#fff' : '#888'}; border:none; border-radius: 5px; font-weight:bold; cursor:pointer;" ${isPassed ? 'disabled' : ''}>
                            ${price.toLocaleString()} ZN
                        </button>
                    </div>`;
            }
            storageSec.innerHTML = html;
        }
    };

    window.buyShopItem = async function(type, level, price) {
        const pData = window.PlayerData;
        if (!pData || pData.balance < price) return alert("رصيد غير كافي!");

        try {
            let response = await fetch('/api/buy', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ tg_id: pData.tg_id, type: type, level: level })
            });

            if (response.ok) {
                let res = await response.json();
                window.PlayerData = res.user; // تحديث البيانات
                window.updateShopUI();
                if (window.updateFarmUI) window.updateFarmUI();
            } else {
                alert("خطأ في السيرفر!");
            }
        } catch (e) {
            console.error(e);
        }
    };

    setTimeout(window.updateShopUI, 500);
})();

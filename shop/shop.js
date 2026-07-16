(function initShop() {
    
    if (typeof window.Telegram === 'undefined' || !window.Telegram.WebApp.initDataUnsafe || !window.Telegram.WebApp.initDataUnsafe.user) {
        return; 
    }

    const TELEGRAM_ID = window.Telegram.WebApp.initDataUnsafe.user.id.toString();

    const SHOP_CONFIG = {
        maxMiningUpgrades: 15, 
        miningPrices: {
            1: 1000, 2: 5000, 3: 15000, 4: 40000, 5: 100000,
            6: 250000, 7: 600000, 8: 1500000, 9: 5000000
        },
        miningRates: { 
            1: 100, 2: 500, 3: 1500, 4: 4000, 5: 10000, 
            6: 25000, 7: 60000, 8: 150000, 9: 500000
        },
        storagePrices: {
            1: 500, 2: 2500, 3: 8000, 4: 20000, 5: 50000,
            6: 120000, 7: 300000, 8: 750000, 9: 2000000, 10: 5000000
        },
        storageCapacities: {
            1: 20000,  2: 30000,  3: 50000,  4: 100000, 5: 200000,
            6: 500000, 7: 1000000, 8: 2500000, 9: 5000000, 10: 10000000
        },
        walletDepositLink: "https://t.me/wallet" 
    };

    let isBuying = false; 

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

    window.buyWithUSDT = function(amount) {
        alert(`جاري توجيهك لشراء باقة ${amount} USDT...`);
        window.open(SHOP_CONFIG.walletDepositLink, '_blank');
    };

    window.updateShopUI = function() {
        const pData = window.PlayerData;
        if (!pData) return;

        let totalBal = parseFloat(pData.balance || 0) + parseFloat(pData.unclaimed || 0);

        document.getElementById('shop-balance').innerText = `ZN: ${Math.floor(pData.balance || 0).toLocaleString()}`;
        document.getElementById('shop-rate').innerText = `⚡ ${(pData.hourly_rate || 0).toLocaleString()}/س`;

        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');

        if (miningSec) {
            let html = '';
            for (let i = 1; i <= 9; i++) {
                let count = parseInt((pData.upgrades && pData.upgrades[`lvl${i}`]) || 0);
                let price = parseFloat(SHOP_CONFIG.miningPrices[i]);
                let speed = parseFloat(SHOP_CONFIG.miningRates[i]); 
                let isMax = count >= SHOP_CONFIG.maxMiningUpgrades;
                let canAfford = totalBal >= price;

                html += `
                    <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 10px; padding: 12px; text-align: center; position: relative; overflow: hidden;">
                        ${isMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; font-size: 16px; z-index: 10; transform: rotate(-10deg);">MAX</div>` : ''}
                        <div style="font-size: 24px; margin-bottom: 5px;">🏛️</div>
                        <div style="color: #fff; font-weight: bold; font-size: 14px;">مستوى ${i}</div>
                        <div style="color: #28a745; font-size: 11px; margin-bottom: 3px;">⚡ السرعة: +${speed.toLocaleString()}/س</div>
                        <div style="color: #0088cc; font-size: 12px; margin-bottom: 10px;">تم الشراء: ${count} / ${SHOP_CONFIG.maxMiningUpgrades}</div>
                        <button id="btn-speed-${i}" onclick="buyShopItem('speed', ${i}, ${price})" 
                            style="width: 100%; padding: 8px; background: ${canAfford && !isMax ? '#ffcc00' : '#444'}; color: ${canAfford && !isMax ? '#000' : '#888'}; border: none; border-radius: 6px; font-weight: bold; cursor: ${canAfford && !isMax ? 'pointer' : 'not-allowed'};" ${isMax ? 'disabled' : ''}>
                            ${price.toLocaleString()} ZN
                        </button>
                    </div>
                `;
            }
            miningSec.innerHTML = html;
        }

        if (storageSec) {
            let html = '';
            let currentStorageLvl = parseInt(pData.storage_level || 0); 

            for (let i = 1; i <= 10; i++) {
                let price = parseFloat(SHOP_CONFIG.storagePrices[i]);
                let capacity = parseFloat(SHOP_CONFIG.storageCapacities[i]);
                
                let isPassedOrMax = i <= currentStorageLvl;
                let canAfford = totalBal >= price;

                html += `
                    <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 10px; padding: 12px; text-align: center; position: relative; overflow: hidden;">
                        ${isPassedOrMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.75); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; font-size: 16px; z-index: 10;">انتهاء MAX</div>` : ''}
                        <div style="font-size: 24px; margin-bottom: 5px;">📦</div>
                        <div style="color: #fff; font-weight: bold; font-size: 14px;">مخزن ${i}</div>
                        <div style="color: #0088cc; font-size: 11px; margin-bottom: 10px;">السعة: ${capacity.toLocaleString()} ZN</div>
                        <button id="btn-storage-${i}" onclick="buyShopItem('storage', ${i}, ${price})" 
                            style="width: 100%; padding: 8px; background: ${canAfford && !isPassedOrMax ? '#0088cc' : '#444'}; color: ${canAfford && !isPassedOrMax ? '#fff' : '#888'}; border: none; border-radius: 6px; font-weight: bold; cursor: ${canAfford && !isPassedOrMax ? 'pointer' : 'not-allowed'};" ${isPassedOrMax ? 'disabled' : ''}>
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
        let numPrice = parseFloat(price);
        let totalBal = parseFloat((pData && pData.balance) || 0) + parseFloat((pData && pData.unclaimed) || 0);

        if (!pData || totalBal < numPrice || isBuying) {
            if (pData && totalBal < numPrice) alert("الرصيد غير كافي!");
            return; 
        }

        isBuying = true;
        const btnId = `btn-${type}-${level}`;
        const btnEl = document.getElementById(btnId);
        if (btnEl) {
            btnEl.disabled = true;
            btnEl.innerText = "جاري الشراء... ⏳";
            btnEl.style.background = "#555";
        }

        let apiType = (type === 'speed') ? 'mining' : 'storage';

        try {
            let response = await fetch('/api/upgrade', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    telegramId: TELEGRAM_ID,
                    type: apiType, 
                    level_num: level 
                })
            });

            let resData = await response.json();

            if (response.ok && resData.success) {
                if (typeof window.fetchPlayerData === 'function') {
                    await window.fetchPlayerData(); 
                }
            } else {
                alert(resData.error || "حدث خطأ أثناء الشراء.");
                if (typeof window.fetchPlayerData === 'function') {
                    await window.fetchPlayerData(); 
                }
            }
        } catch (e) {
            console.error(e);
            alert("فشل الاتصال بالسيرفر.");
        } finally {
            isBuying = false; 
        }
    };

    setTimeout(window.updateShopUI, 1000);
})();

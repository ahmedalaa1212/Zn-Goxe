(function initShop() {
    
    if (typeof window.Telegram === 'undefined' || !window.Telegram.WebApp.initData) {
        console.warn("Telegram WebApp Environment Not Detected.");
    }

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
            if (miningSec) miningSec.style.display = 'grid';
            if (storageSec) storageSec.style.display = 'none';
            if (btnMining) btnMining.style.background = '#0088cc';
            if (btnStorage) btnStorage.style.background = '#333';
        } else {
            if (miningSec) miningSec.style.display = 'none';
            if (storageSec) storageSec.style.display = 'grid';
            if (btnMining) btnMining.style.background = '#333';
            if (btnStorage) btnStorage.style.background = '#0088cc';
        }
    };

    window.buyWithUSDT = function(amount) {
        alert(`جاري توجيهك لشراء باقة ${amount} USDT...`);
        window.open(SHOP_CONFIG.walletDepositLink, '_blank');
    };

    window.updateShopUI = function() {
        const pData = window.PlayerData;
        if (!pData) return;

        let totalBal = parseFloat(pData.balance || 0);

        const shopBalEl = document.getElementById('shop-balance');
        const shopRateEl = document.getElementById('shop-rate');

        if (shopBalEl) shopBalEl.innerHTML = `<span>🪙</span> <span>ZN: ${Math.floor(totalBal).toLocaleString()}</span>`;
        if (shopRateEl) shopRateEl.innerHTML = `<span>⚡</span> <span>${(pData.hourly_rate || 0).toLocaleString()}/س</span>`;

        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');

        // بناء قائمة ترقيات سرعة التعدين
        if (miningSec) {
            let html = '';
            for (let i = 1; i <= 9; i++) {
                let count = parseInt((pData.upgrades && pData.upgrades[`lvl${i}`]) || 0);
                let price = parseFloat(SHOP_CONFIG.miningPrices[i]);
                let speed = parseFloat(SHOP_CONFIG.miningRates[i]); 
                let isMax = count >= SHOP_CONFIG.maxMiningUpgrades;
                let canAfford = totalBal >= price;

                html += `
                    <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 12px; text-align: center; position: relative; overflow: hidden; display: flex; flex-direction: column; justify-content: space-between;">
                        ${isMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; font-size: 18px; z-index: 10; transform: rotate(-10deg);">مكتمل MAX</div>` : ''}
                        <div>
                            <div style="font-size: 26px; margin-bottom: 5px;">🏛️</div>
                            <div style="color: #fff; font-weight: bold; font-size: 14px;">مستوى ${i}</div>
                            <div style="color: #28a745; font-size: 12px; margin: 4px 0;">⚡ +${speed.toLocaleString()}/س</div>
                            <div style="color: #888; font-size: 11px; margin-bottom: 10px;">تم الشراء: ${count} / ${SHOP_CONFIG.maxMiningUpgrades}</div>
                        </div>
                        <button id="btn-speed-${i}" onclick="buyShopItem('speed', ${i}, ${price})" 
                            style="width: 100%; padding: 9px; background: ${canAfford && !isMax ? '#ffcc00' : '#333'}; color: ${canAfford && !isMax ? '#000' : '#888'}; border: none; border-radius: 6px; font-weight: bold; cursor: ${canAfford && !isMax ? 'pointer' : 'not-allowed'}; transition: background 0.2s;" ${isMax || !canAfford ? 'disabled' : ''}>
                            ${price.toLocaleString()} ZN
                        </button>
                    </div>
                `;
            }
            miningSec.innerHTML = html;
        }

        // بناء قائمة ترقيات المخازن
        if (storageSec) {
            let html = '';
            let currentStorageLvl = parseInt(pData.storage_level || 0); 

            for (let i = 1; i <= 10; i++) {
                let price = parseFloat(SHOP_CONFIG.storagePrices[i]);
                let capacity = parseFloat(SHOP_CONFIG.storageCapacities[i]);
                
                let isOwned = i <= currentStorageLvl;
                let isNextUpgrade = i === currentStorageLvl + 1;
                let canAfford = totalBal >= price;

                let btnBg = '#333';
                let btnColor = '#888';
                let btnText = `${price.toLocaleString()} ZN`;
                let isDisabled = true;

                if (isOwned) {
                    btnBg = '#28a745';
                    btnColor = '#fff';
                    btnText = 'تم الشراء ✔️';
                    isDisabled = true;
                } else if (isNextUpgrade) {
                    if (canAfford) {
                        btnBg = '#0088cc';
                        btnColor = '#fff';
                        isDisabled = false;
                    } else {
                        btnBg = '#333';
                        btnColor = '#888';
                        isDisabled = true;
                    }
                } else {
                    btnText = 'مغلق 🔒';
                    isDisabled = true;
                }

                html += `
                    <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 12px; text-align: center; position: relative; overflow: hidden; display: flex; flex-direction: column; justify-content: space-between;">
                        <div>
                            <div style="font-size: 26px; margin-bottom: 5px;">📦</div>
                            <div style="color: #fff; font-weight: bold; font-size: 14px;">مخزن مستوى ${i}</div>
                            <div style="color: #0088cc; font-size: 12px; margin: 4px 0 10px 0;">السعة: ${capacity.toLocaleString()} ZN</div>
                        </div>
                        <button id="btn-storage-${i}" onclick="buyShopItem('storage', ${i}, ${price})" 
                            style="width: 100%; padding: 9px; background: ${btnBg}; color: ${btnColor}; border: none; border-radius: 6px; font-weight: bold; cursor: ${!isDisabled ? 'pointer' : 'not-allowed'}; transition: background 0.2s;" ${isDisabled ? 'disabled' : ''}>
                            ${btnText}
                        </button>
                    </div>
                `;
            }
            storageSec.innerHTML = html;
        }
    };

    window.buyShopItem = async function(type, level, price) {
        const pData = window.PlayerData;
        const initData = window.Telegram?.WebApp?.initData; 

        if (!initData) {
            alert("⚠️ عذراً، يجب فتح اللعبة من داخل تطبيق تليجرام.");
            return;
        }

        if (isBuying) return;

        let numPrice = parseFloat(price);
        let totalBal = parseFloat((pData && pData.balance) || 0);

        if (!pData || totalBal < numPrice) {
            alert("⚠️ الرصيد غير كافي لشراء هذا التطوير!");
            return; 
        }

        isBuying = true;
        const btnId = `btn-${type === 'speed' ? 'speed' : 'storage'}-${level}`;
        const btnEl = document.getElementById(btnId);
        
        let oldBtnText = "";
        if (btnEl) {
            oldBtnText = btnEl.innerText;
            btnEl.disabled = true;
            btnEl.innerText = "جاري الشراء... ⏳";
            btnEl.style.background = "#555";
        }

        let apiType = (type === 'speed') ? 'mining' : 'storage';

        try {
            let response = await fetch('/api/shop/buy', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({ 
                    initData: initData,
                    type: apiType, 
                    level_num: level 
                })
            });

            let resData = await response.json();

            if (response.ok && resData.success) {
                if (typeof window.fetchPlayerDataFromServer === 'function') {
                    await window.fetchPlayerDataFromServer(); 
                }
            } else {
                alert(resData.error || resData.message || "حدث خطأ أثناء الشراء.");
                if (typeof window.fetchPlayerDataFromServer === 'function') {
                    await window.fetchPlayerDataFromServer(); 
                }
            }
        } catch (e) {
            console.error("Shop Purchase Error:", e);
            alert("فشل الاتصال بالسيرفر. يرجى التحقق من الشبكة.");
            if (btnEl) {
                btnEl.disabled = false;
                btnEl.innerText = oldBtnText;
            }
        } finally {
            isBuying = false; 
        }
    };

    // التحديث الفوري للواجهة
    window.updateShopUI();
})();

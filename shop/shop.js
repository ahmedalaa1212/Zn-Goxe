(function initShop() {
    
    // إعدادات المتجر
    const SHOP_CONFIG = {
        maxMiningUpgrades: 10,
        miningPrices: {
            1: 310, 2: 820, 3: 2100, 4: 7000, 5: 10100,
            6: 14500, 7: 17300, 8: 21500, 9: 32150
        },
        miningRates: { 
            1: 2, 2: 5, 3: 11, 4: 23, 5: 56, 
            6: 76, 7: 84, 8: 98, 9: 110
        },
        storagePrices: { 
            1: 1000, 2: 2000, 3: 3000, 4: 4000, 5: 5000,
            6: 6000, 7: 7000, 8: 8000, 9: 9000, 10: 10000
        },
        storageCapacities: { 
            1: 20000,  2: 30000,  3: 50000,  4: 100000, 5: 200000,
            6: 500000, 7: 1000000, 8: 2500000, 9: 5000000, 10: 10000000
        },
        walletDepositLink: "https://t.me/wallet" 
    };

    let isBuying = false; 

    // ==========================================
    // 🎨 بناء رسالة التأكيد الاحترافية (Modal)
    // ==========================================
    const injectModalUI = () => {
        if (!document.getElementById('shop-modal-styles')) {
            const styleSheet = document.createElement("style");
            styleSheet.id = 'shop-modal-styles';
            styleSheet.innerHTML = `
                #shop-confirm-modal-overlay {
                    position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                    background: rgba(0, 0, 0, 0.8); backdrop-filter: blur(4px);
                    display: none; align-items: center; justify-content: center;
                    z-index: 99999; opacity: 0; transition: opacity 0.3s ease;
                }
                #shop-confirm-modal {
                    background: #1a1a1a; border: 1px solid #333; border-radius: 20px;
                    padding: 24px; width: 85%; max-width: 320px; text-align: center;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.8);
                    transform: translateY(30px) scale(0.95);
                    transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
                }
                .shop-modal-active { display: flex !important; opacity: 1 !important; }
                .shop-modal-active > #shop-confirm-modal { transform: translateY(0) scale(1); }
                .shop-modal-title { color: #fff; font-size: 20px; font-weight: bold; margin-bottom: 8px; }
                .shop-modal-desc { color: #aaa; font-size: 14px; margin-bottom: 15px; line-height: 1.5; }
                .shop-modal-price-box { 
                    background: #000; border-radius: 12px; padding: 12px; 
                    color: #ffcc00; font-weight: bold; font-size: 18px; margin-bottom: 20px;
                    border: 1px solid #333;
                }
                .shop-modal-actions { display: flex; gap: 12px; justify-content: center; }
                .shop-btn {
                    flex: 1; padding: 12px; border: none; border-radius: 10px;
                    font-weight: bold; font-size: 15px; cursor: pointer; transition: 0.2s;
                }
                .shop-btn-cancel { background: #333; color: #fff; }
                .shop-btn-cancel:hover { background: #444; }
                .shop-btn-confirm { background: #0088cc; color: #fff; }
                .shop-btn-confirm:hover { background: #0077b3; filter: brightness(1.2); }
            `;
            document.head.appendChild(styleSheet);
        }

        if (!document.getElementById('shop-confirm-modal-overlay')) {
            const modalHTML = `
                <div id="shop-confirm-modal-overlay">
                    <div id="shop-confirm-modal">
                        <div id="shop-modal-icon" style="font-size: 45px; margin-bottom: 10px; text-shadow: 0 0 15px rgba(255,255,255,0.2);">🛒</div>
                        <div class="shop-modal-title" id="shop-modal-title">تأكيد الشراء</div>
                        <div class="shop-modal-desc" id="shop-modal-desc">هل أنت متأكد من هذه العملية؟</div>
                        <div class="shop-modal-price-box" id="shop-modal-price">0 ZN</div>
                        <div class="shop-modal-actions">
                            <button class="shop-btn shop-btn-cancel" onclick="closeShopModal()">إلغاء</button>
                            <button class="shop-btn shop-btn-confirm" id="shop-modal-confirm-btn">شراء الآن</button>
                        </div>
                    </div>
                </div>
            `;
            document.body.insertAdjacentHTML('beforeend', modalHTML);
        }
    };

    window.closeShopModal = function() {
        const overlay = document.getElementById('shop-confirm-modal-overlay');
        if(overlay) {
            overlay.classList.remove('shop-modal-active');
            setTimeout(() => {
                if(!overlay.classList.contains('shop-modal-active')) {
                    overlay.style.display = 'none'; 
                }
            }, 300);
        }
    };

    injectModalUI();
    // ==========================================


    window.switchShopTab = function(tab) {
        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');
        const btnMining = document.getElementById('tab-mining');
        const btnStorage = document.getElementById('tab-storage');

        if (!miningSec || !storageSec) return;

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
        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');
        
        if (!miningSec || !storageSec) {
            setTimeout(window.updateShopUI, 500);
            return;
        }

        const pData = window.PlayerData || { balance: 0, hourly_rate: 0, upgrades: {}, storage_level: 0 };
        let totalBal = parseFloat(pData.balance || 0);

        const shopBalEl = document.getElementById('shop-balance-text');
        const shopRateEl = document.getElementById('shop-rate-text');
        if (shopBalEl) shopBalEl.innerText = `ZN: ${Math.floor(totalBal).toLocaleString()}`;
        if (shopRateEl) shopRateEl.innerText = `${(pData.hourly_rate || 0).toLocaleString()}/h`; // تم التعديل

        let miningHtml = '';
        for (let i = 1; i <= 9; i++) {
            let count = parseInt((pData.upgrades && pData.upgrades[`lvl${i}`]) || 0);
            let price = parseFloat(SHOP_CONFIG.miningPrices[i]);
            let speed = parseFloat(SHOP_CONFIG.miningRates[i]); 
            let isMax = count >= SHOP_CONFIG.maxMiningUpgrades;
            let canAfford = totalBal >= price;

            miningHtml += `
                <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 12px; text-align: center; position: relative; overflow: hidden; display: flex; flex-direction: column; justify-content: space-between;">
                    ${isMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; font-size: 18px; z-index: 10; transform: rotate(-10deg);">مكتمل MAX</div>` : ''}
                    <div>
                        <div style="font-size: 26px; margin-bottom: 5px;">🏛️</div>
                        <div style="color: #fff; font-weight: bold; font-size: 14px;">مستوى ${i}</div>
                        <div style="color: #28a745; font-size: 12px; margin: 4px 0;">⚡ +${speed.toLocaleString()}/h</div>
                        <div style="color: #888; font-size: 11px; margin-bottom: 10px;">تم الشراء: ${count} / ${SHOP_CONFIG.maxMiningUpgrades}</div>
                    </div>
                    <button id="btn-speed-${i}" onclick="requestShopPurchase('speed', ${i}, ${price})" 
                        style="width: 100%; padding: 9px; background: ${canAfford && !isMax ? '#ffcc00' : '#333'}; color: ${canAfford && !isMax ? '#000' : '#888'}; border: none; border-radius: 6px; font-weight: bold; cursor: ${canAfford && !isMax ? 'pointer' : 'not-allowed'};" ${isMax || (!canAfford && !isMax) ? 'disabled' : ''}>
                        ${price.toLocaleString()} ZN
                    </button>
                </div>
            `;
        }
        miningSec.innerHTML = miningHtml;

        let storageHtml = '';
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

            storageHtml += `
                <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 12px; text-align: center; position: relative; overflow: hidden; display: flex; flex-direction: column; justify-content: space-between;">
                    <div>
                        <div style="font-size: 26px; margin-bottom: 5px;">📦</div>
                        <div style="color: #fff; font-weight: bold; font-size: 14px;">مخزن مستوى ${i}</div>
                        <div style="color: #0088cc; font-size: 12px; margin: 4px 0 10px 0;">السعة: ${capacity.toLocaleString()} ZN</div>
                    </div>
                    <button id="btn-storage-${i}" onclick="requestShopPurchase('storage', ${i}, ${price})" 
                        style="width: 100%; padding: 9px; background: ${btnBg}; color: ${btnColor}; border: none; border-radius: 6px; font-weight: bold; cursor: ${!isDisabled ? 'pointer' : 'not-allowed'};" ${isDisabled ? 'disabled' : ''}>
                        ${btnText}
                    </button>
                </div>
            `;
        }
        storageSec.innerHTML = storageHtml;
    };


    window.requestShopPurchase = function(type, level, price) {
        const pData = window.PlayerData;
        const totalBal = parseFloat((pData && pData.balance) || 0);
        let numPrice = parseFloat(price);

        if (totalBal < numPrice) {
            alert("⚠️ الرصيد غير كافي لشراء هذا التطوير!");
            return; 
        }

        const overlay = document.getElementById('shop-confirm-modal-overlay');
        const titleEl = document.getElementById('shop-modal-title');
        const descEl = document.getElementById('shop-modal-desc');
        const priceEl = document.getElementById('shop-modal-price');
        const iconEl = document.getElementById('shop-modal-icon');
        const confirmBtn = document.getElementById('shop-modal-confirm-btn');

        if (type === 'speed') {
            iconEl.innerText = '⚡';
            titleEl.innerText = 'ترقية سرعة التعدين';
            descEl.innerText = `هل تريد شراء ترقية السرعة (مستوى ${level})؟`;
            confirmBtn.style.background = '#ffcc00';
            confirmBtn.style.color = '#000';
        } else {
            iconEl.innerText = '📦';
            titleEl.innerText = 'توسعة المخزن';
            descEl.innerText = `هل تريد ترقية مساحة المخزن الخاص بك إلى (مستوى ${level})؟`;
            confirmBtn.style.background = '#0088cc';
            confirmBtn.style.color = '#fff';
        }

        priceEl.innerText = `التكلفة: ${numPrice.toLocaleString()} ZN`;

        confirmBtn.onclick = function() {
            closeShopModal();
            executeActualPurchase(type, level, price);
        };

        overlay.style.display = 'flex';
        setTimeout(() => overlay.classList.add('shop-modal-active'), 10);
    };


    async function executeActualPurchase(type, level, price) {
        const initData = window.Telegram?.WebApp?.initData; 

        if (!initData) {
            alert("⚠️ عذراً، يجب فتح اللعبة من داخل تطبيق تليجرام.");
            return;
        }

        if (isBuying) return;
        isBuying = true;

        const btnId = `btn-${type === 'speed' ? 'speed' : 'storage'}-${level}`;
        const btnEl = document.getElementById(btnId);
        
        let oldBtnText = "";
        if (btnEl) {
            oldBtnText = btnEl.innerText;
            btnEl.disabled = true;
            btnEl.innerText = "جاري الشراء... ⏳";
            btnEl.style.background = "#555";
            btnEl.style.color = "#fff";
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
                if (window.PlayerData) {
                    window.PlayerData.balance = resData.balance;
                    window.PlayerData.last_claim_time = resData.last_claim_time; 
                    
                    if (apiType === 'mining') {
                        window.PlayerData.hourly_rate = resData.hourly_rate;
                        window.PlayerData.upgrades = resData.upgrades;
                    } else if (apiType === 'storage') {
                        window.PlayerData.storage_level = resData.storage_level;
                        window.PlayerData.max_cap = resData.max_cap;
                    }
                }
                
                window.updateShopUI();
                
                if (typeof window.updateFarmUI === 'function') {
                    window.updateFarmUI();
                }

            } else {
                alert(resData.error || resData.message || "حدث خطأ أثناء الشراء.");
            }
        } catch (e) {
            console.error("Shop Purchase Error:", e);
            alert("فشل الاتصال بالسيرفر. يرجى التحقق من الشبكة.");
        } finally {
            if (btnEl) {
                btnEl.disabled = false;
                btnEl.innerText = oldBtnText;
            }
            isBuying = false; 
            window.updateShopUI();
        }
    }

    window.updateShopUI();
    setInterval(window.updateShopUI, 1000);

})();

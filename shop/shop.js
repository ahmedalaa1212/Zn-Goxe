// shop/shop.js
(function initShop() {
    'use strict';

    // --- أدوات المزامنة الموحدة مع الذاكرة المحلية والواجهات ---
    function getStoredBalance() {
        if (window.GameState && window.GameState.balance !== undefined && window.GameState.balance !== null) {
            return parseFloat(window.GameState.balance);
        }
        if (window.PlayerData && window.PlayerData.balance !== undefined && window.PlayerData.balance !== null) {
            return parseFloat(window.PlayerData.balance);
        }
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        return bal !== null ? parseFloat(bal) : 0;
    }

    function getStoredUsdBalance() {
        if (window.GameState && window.GameState.usd_balance !== undefined && window.GameState.usd_balance !== null) {
            return parseFloat(window.GameState.usd_balance);
        }
        if (window.PlayerData && window.PlayerData.usd_balance !== undefined && window.PlayerData.usd_balance !== null) {
            return parseFloat(window.PlayerData.usd_balance);
        }
        const usd = localStorage.getItem('usd_balance');
        return usd !== null ? parseFloat(usd) : 0.0;
    }

    function setStoredBalance(newBalance) {
        if (newBalance !== undefined && newBalance !== null) {
            const numVal = parseFloat(newBalance);
            if (typeof window.setBalance === 'function') {
                window.setBalance(numVal);
            } else {
                if (window.GameState) window.GameState.balance = numVal;
                if (window.PlayerData) window.PlayerData.balance = numVal;
                localStorage.setItem('zn_balance', numVal.toString());
                localStorage.setItem('user_balance', numVal.toString());
            }
        }
    }

    // أداة اهتزاز اللمس لتطبيقات تليجرام (Haptic Feedback)
    function triggerHaptic(type = 'impact', style = 'medium') {
        if (window.Telegram?.WebApp?.HapticFeedback) {
            if (type === 'impact') {
                window.Telegram.WebApp.HapticFeedback.impactOccurred(style);
            } else if (type === 'notification') {
                window.Telegram.WebApp.HapticFeedback.notificationOccurred(style);
            }
        }
    }

    // إعدادات المتجر
    const SHOP_CONFIG = {
        maxMiningUpgrades: {
            1: 15, 2: 10, 3: 10, 4: 10, 5: 10, 
            6: 10, 7: 10, 8: 10, 9: 10
        },
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
            1: 100, 2: 300, 3: 600, 4: 1000, 5: 1500,
            6: 2500, 7: 3500, 8: 4500, 9: 5500, 10: 7000
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
                    background: rgba(0, 0, 0, 0.85); backdrop-filter: blur(4px);
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
                        <div id="shop-modal-icon" style="font-size: 45px; margin-bottom: 10px;">🛒</div>
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
        triggerHaptic('impact', 'light');
        const overlay = document.getElementById('shop-confirm-modal-overlay');
        if (overlay) {
            overlay.classList.remove('shop-modal-active');
            setTimeout(() => {
                if (!overlay.classList.contains('shop-modal-active')) {
                    overlay.style.display = 'none'; 
                }
            }, 300);
        }
    };

    injectModalUI();

    window.switchShopTab = function(tab) {
        triggerHaptic('impact', 'light');
        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');
        const btnMining = document.getElementById('tab-mining');
        const btnStorage = document.getElementById('tab-storage');

        if (!miningSec || !storageSec) return;

        if (tab === 'mining') {
            miningSec.style.display = 'grid';
            storageSec.style.display = 'none';
            if (btnMining) btnMining.style.background = '#0088cc';
            if (btnStorage) btnStorage.style.background = '#333';
        } else {
            miningSec.style.display = 'none';
            storageSec.style.display = 'grid';
            if (btnMining) btnMining.style.background = '#333';
            if (btnStorage) btnStorage.style.background = '#0088cc';
        }
    };

    window.buyWithUSDT = function(amount) {
        triggerHaptic('impact', 'medium');
        alert(`جاري توجيهك لشراء باقة ${amount} USDT...`);
        window.open(SHOP_CONFIG.walletDepositLink, '_blank');
    };

    window.updateShopUI = function() {
        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');
        
        if (!miningSec || !storageSec) return;

        const pData = window.PlayerData || window.GameState || { balance: 0, hourly_rate: 0, upgrades: {}, storage_level: 0, usd_balance: 0 };
        
        // جلب وقراءة الأرصادات المحدثة
        let totalBal = getStoredBalance();
        let totalUsd = getStoredUsdBalance();

        const shopBalEl = document.getElementById('shop-balance-text');
        const shopRateEl = document.getElementById('shop-rate-text');
        const shopUsdEl = document.getElementById('shop-usd-text');

        if (shopBalEl) shopBalEl.innerText = `${Math.floor(totalBal).toLocaleString()}`;
        if (shopRateEl) shopRateEl.innerText = `${(pData.hourly_rate || 0).toLocaleString()}/h`; 
        
        if (shopUsdEl) {
            let numUsd = Number(totalUsd) || 0;
            shopUsdEl.innerText = "$" + (numUsd > 0 && numUsd < 0.01 ? numUsd.toFixed(5) : numUsd.toFixed(2));
        }

        if (typeof window.updateGlobalUI === 'function') {
            window.updateGlobalUI();
        }

        // ----------------------------------------
        // بناء واجهة ترقيات السرعة والتعدين
        // ----------------------------------------
        let miningHtml = '';
        for (let i = 1; i <= 9; i++) {
            let count = parseInt((pData.upgrades && pData.upgrades[`lvl${i}`]) || 0);
            let price = parseFloat(SHOP_CONFIG.miningPrices[i]);
            let speed = parseFloat(SHOP_CONFIG.miningRates[i]); 
            let maxLimit = SHOP_CONFIG.maxMiningUpgrades[i];
            let isMax = count >= maxLimit;
            let canAfford = totalBal >= price;

            miningHtml += `
                <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 12px; text-align: center; position: relative; overflow: hidden; display: flex; flex-direction: column; justify-content: space-between;">
                    ${isMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; font-size: 18px; z-index: 10; transform: rotate(-10deg);">مكتمل MAX</div>` : ''}
                    <div>
                        <div style="font-size: 26px; margin-bottom: 5px;">🏛️</div>
                        <div style="color: #fff; font-weight: bold; font-size: 14px;">مستوى ${i}</div>
                        <div style="color: #00cc66; font-size: 12px; margin: 4px 0;">⚡ +${speed.toLocaleString()}/h</div>
                        <div style="color: #888; font-size: 11px; margin-bottom: 10px;">تم الشراء: ${count} / ${maxLimit}</div>
                    </div>
                    <button id="btn-speed-${i}" onclick="requestShopPurchase('speed', ${i}, ${price})" 
                        style="width: 100%; padding: 9px; background: ${canAfford && !isMax ? '#ffcc00' : '#333'}; color: ${canAfford && !isMax ? '#000' : '#888'}; border: none; border-radius: 6px; font-weight: bold; cursor: ${canAfford && !isMax ? 'pointer' : 'not-allowed'};" ${isMax || (!canAfford && !isMax) ? 'disabled' : ''}>
                        ZN ${price.toLocaleString()}
                    </button>
                </div>
            `;
        }
        miningSec.innerHTML = miningHtml;

        // ----------------------------------------
        // بناء واجهة المخازن
        // ----------------------------------------
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
            let btnText = `ZN ${price.toLocaleString()}`;
            let isDisabled = true;

            if (isOwned) {
                btnBg = '#00cc66';
                btnColor = '#000';
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
                        <div style="color: #0088cc; font-size: 12px; margin: 4px 0 10px 0;">السعة: ${capacity.toLocaleString()}</div>
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
        const totalBal = getStoredBalance();
        let numPrice = parseFloat(price);

        if (totalBal < numPrice) {
            triggerHaptic('notification', 'error');
            alert("⚠️ الرصيد غير كافي لشراء هذا التطوير!");
            return; 
        }

        triggerHaptic('impact', 'light');

        const overlay = document.getElementById('shop-confirm-modal-overlay');
        const titleEl = document.getElementById('shop-modal-title');
        const descEl = document.getElementById('shop-modal-desc');
        const priceEl = document.getElementById('shop-modal-price');
        const iconEl = document.getElementById('shop-modal-icon');
        const confirmBtn = document.getElementById('shop-modal-confirm-btn');

        if (type === 'speed') {
            if (iconEl) iconEl.innerText = '⚡';
            if (titleEl) titleEl.innerText = 'ترقية سرعة التعدين';
            if (descEl) descEl.innerText = `هل تريد شراء ترقية السرعة (مستوى ${level})؟`;
            if (confirmBtn) {
                confirmBtn.style.background = '#ffcc00';
                confirmBtn.style.color = '#000';
            }
        } else {
            if (iconEl) iconEl.innerText = '📦';
            if (titleEl) titleEl.innerText = 'توسعة المخزن';
            if (descEl) descEl.innerText = `هل تريد ترقية مساحة المخزن الخاص بك إلى (مستوى ${level})؟`;
            if (confirmBtn) {
                confirmBtn.style.background = '#0088cc';
                confirmBtn.style.color = '#fff';
            }
        }

        if (priceEl) priceEl.innerText = `التكلفة: ${numPrice.toLocaleString()} ZN`;

        if (confirmBtn) {
            confirmBtn.onclick = function() {
                closeShopModal();
                executeActualPurchase(type, level, price);
            };
        }

        if (overlay) {
            overlay.style.display = 'flex';
            setTimeout(() => overlay.classList.add('shop-modal-active'), 10);
        }
    };

    async function executeActualPurchase(type, level, price) {
        const initData = window.Telegram?.WebApp?.initData; 

        if (!initData) {
            triggerHaptic('notification', 'error');
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
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({ 
                    initData: initData,
                    type: apiType, 
                    level_num: level 
                })
            });

            let resData = await response.json();

            if (response.ok && resData.success) {
                triggerHaptic('notification', 'success');
                setStoredBalance(resData.balance);

                if (!window.PlayerData) window.PlayerData = {};
                window.PlayerData.balance = resData.balance;
                window.PlayerData.last_claim_time = resData.last_claim_time; 
                
                if (apiType === 'mining') {
                    window.PlayerData.hourly_rate = resData.hourly_rate;
                    window.PlayerData.upgrades = resData.upgrades;
                } else if (apiType === 'storage') {
                    window.PlayerData.storage_level = resData.storage_level;
                    window.PlayerData.max_cap = resData.max_cap;
                }
                
                window.updateShopUI();
                
                if (typeof window.updateFarmUI === 'function') {
                    window.updateFarmUI();
                }

            } else {
                triggerHaptic('notification', 'error');
                alert(resData.error || resData.message || "حدث خطأ أثناء الشراء.");
            }
        } catch (e) {
            console.error("Shop Purchase Error:", e);
            triggerHaptic('notification', 'error');
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

    // --- مستمعات التنقل والمزامنة اللحظية ---
    window.addEventListener('pageshow', () => {
        window.updateShopUI();
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            window.updateShopUI();
        }
    });

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        window.updateShopUI();
    } else {
        document.addEventListener('DOMContentLoaded', window.updateShopUI);
    }

})();

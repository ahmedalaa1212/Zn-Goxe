// shop/shop.js
(function initShop() {
    'use strict';

    let tonConnectUI = null;
    let isBuying = false;

    function getStoredBalance() {
        if (window.GameState && window.GameState.balance !== undefined) return parseFloat(window.GameState.balance);
        if (window.PlayerData && window.PlayerData.balance !== undefined) return parseFloat(window.PlayerData.balance);
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        return bal !== null ? parseFloat(bal) : 0;
    }

    function getStoredUsdBalance() {
        if (window.GameState && window.GameState.usd_balance !== undefined) return parseFloat(window.GameState.usd_balance);
        if (window.PlayerData && window.PlayerData.usd_balance !== undefined) return parseFloat(window.PlayerData.usd_balance);
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
            }
        }
    }

    function triggerHaptic(type = 'impact', style = 'medium') {
        if (window.Telegram?.WebApp?.HapticFeedback) {
            if (type === 'impact') window.Telegram.WebApp.HapticFeedback.impactOccurred(style);
            else if (type === 'notification') window.Telegram.WebApp.HapticFeedback.notificationOccurred(style);
        }
    }

    // تهيئة TonConnect المباشر للربط مع المحفظة
    function initTonConnect() {
        try {
            tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
                manifestUrl: `${window.location.origin}/tonconnect-manifest.json`,
                buttonRootId: 'ton-connect-btn'
            });
        } catch (e) {
            console.error("TonConnect Init Error:", e);
        }
    }

    // جلب الإعدادات والسعر اللحظي من الباك إند
    async function loadShopConfig() {
        try {
            const res = await fetch('/api/shop/get_config');
            const data = await res.json();
            if (data.success) {
                const rateEl = document.getElementById('ton-live-rate-text');
                if (rateEl) rateEl.innerText = `$${data.ton_price_usd.toFixed(2)}`;

                for (const [pkgId, pkg] of Object.entries(data.packages)) {
                    const el = document.getElementById(`ton-amt-${pkgId}`);
                    if (el) el.innerText = `~${pkg.ton_amount} TON`;
                }
            }
        } catch (e) {
            console.error("Error fetching config:", e);
        }
    }

    // الشراء والتفعيل التلقائي للباقة عند الدفع بـ TON
    window.buyPackageWithTon = async function(packageId) {
        if (!tonConnectUI || !tonConnectUI.connected) {
            triggerHaptic('notification', 'warning');
            alert("⚠️ يرجى ربط محفظة TON الخاصة بك أولاً عبر الزر الأعلى!");
            return;
        }

        const initData = window.Telegram?.WebApp?.initData;
        if (!initData) {
            alert("⚠️ يجب فتح التطبيق من داخل تليجرام.");
            return;
        }

        try {
            triggerHaptic('impact', 'medium');

            // 1. طلب حساب المعاملة بالـ NanoTON من السيرفر
            const prepRes = await fetch('/api/shop/prepare_ton_pay', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({ package_id: packageId })
            });

            const prepData = await prepRes.json();
            if (!prepData.success) {
                alert("خطأ: " + prepData.error);
                return;
            }

            // 2. فتح المحفظة وإرسال الدفع
            const transaction = {
                validUntil: Math.floor(Date.now() / 1000) + 600,
                messages: [{
                    address: prepData.recipient_address,
                    amount: prepData.nano_ton,
                    payload: prepData.payload_memo
                }]
            };

            const result = await tonConnectUI.sendTransaction(transaction);

            // 3. إرسال تأكيد المعاملة للسيرفر للتفعيل التلقائي الفوري
            const verifyRes = await fetch('/api/shop/verify_and_apply_package', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({
                    package_id: packageId,
                    boc: result.boc
                })
            });

            const verifyData = await verifyRes.json();
            if (verifyData.success) {
                triggerHaptic('notification', 'success');
                alert("🎉 تم الدفع بنجاح وتفعيل الباقة فوراً في حسابك!");

                if (window.PlayerData) {
                    window.PlayerData.balance = verifyData.result.balance;
                    window.PlayerData.hourly_rate = verifyData.result.hourly_rate;
                    window.PlayerData.max_cap = verifyData.result.max_cap;
                }
                setStoredBalance(verifyData.result.balance);
                window.updateShopUI();
            } else {
                alert("⚠️ " + verifyData.error);
            }

        } catch (e) {
            console.error("Payment Error:", e);
            triggerHaptic('notification', 'error');
            alert("❌ تم إلغاء المعاملة أو حدث خطأ أثناء الدفع.");
        }
    };

    const SHOP_CONFIG = {
        maxMiningUpgrades: { 1: 10, 2: 10, 3: 10, 4: 10, 5: 10, 6: 10, 7: 10, 8: 10, 9: 10 },
        miningPrices: { 1: 2000, 2: 7000, 3: 18000, 4: 45000, 5: 110000, 6: 260000, 7: 600000, 8: 1400000, 9: 3200000 },
        miningRates: { 1: 5, 2: 15, 3: 35, 4: 80, 5: 180, 6: 400, 7: 900, 8: 2000, 9: 4500 },
        storagePrices: { 1: 3000, 2: 10000, 3: 25000, 4: 65000, 5: 160000, 6: 400000, 7: 950000, 8: 2200000, 9: 5000000, 10: 12000000 },
        storageCapacities: { 1: 600, 2: 1500, 3: 3500, 4: 8000, 5: 18000, 6: 40000, 7: 90000, 8: 200000, 9: 450000, 10: 1000000 }
    };

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
                .shop-btn { flex: 1; padding: 12px; border: none; border-radius: 10px; font-weight: bold; font-size: 15px; cursor: pointer; }
                .shop-btn-cancel { background: #333; color: #fff; }
                .shop-btn-confirm { background: #0088cc; color: #fff; }
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
        if (overlay) overlay.classList.remove('shop-modal-active');
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

    window.updateShopUI = function() {
        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');
        if (!miningSec || !storageSec) return;

        const pData = window.PlayerData || window.GameState || { balance: 0, hourly_rate: 0, upgrades: {}, storage_level: 0, usd_balance: 0 };
        let totalBal = getStoredBalance();
        let totalUsd = getStoredUsdBalance();

        const shopBalEl = document.getElementById('shop-balance-text');
        const shopRateEl = document.getElementById('shop-rate-text');
        const shopUsdEl = document.getElementById('shop-usd-text');

        if (shopBalEl) shopBalEl.innerText = `${Math.floor(totalBal).toLocaleString()}`;
        if (shopRateEl) shopRateEl.innerText = `${(pData.hourly_rate || 0).toLocaleString()}/h`; 
        if (shopUsdEl) shopUsdEl.innerText = "$" + (totalUsd > 0 && totalUsd < 0.01 ? totalUsd.toFixed(5) : totalUsd.toFixed(2));

        // ترقيات السرعة
        let miningHtml = '';
        for (let i = 1; i <= 9; i++) {
            let count = parseInt((pData.upgrades && pData.upgrades[`lvl${i}`]) || 0);
            let price = parseFloat(SHOP_CONFIG.miningPrices[i]);
            let speed = parseFloat(SHOP_CONFIG.miningRates[i]); 
            let maxLimit = SHOP_CONFIG.maxMiningUpgrades[i];
            let isMax = count >= maxLimit;
            let canAfford = totalBal >= price;

            miningHtml += `
                <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 12px; text-align: center; position: relative; display: flex; flex-direction: column; justify-content: space-between;">
                    ${isMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00;">مكتمل MAX</div>` : ''}
                    <div>
                        <div style="font-size: 26px;">⚡</div>
                        <div style="color: #fff; font-weight: bold; font-size: 14px;">مستوى ${i}</div>
                        <div style="color: #00cc66; font-size: 12px; margin: 4px 0;">⚡ +${speed.toLocaleString()}/h</div>
                        <div style="color: #888; font-size: 11px; margin-bottom: 10px;">تم الشراء: ${count} / ${maxLimit}</div>
                    </div>
                    <button id="btn-speed-${i}" onclick="requestShopPurchase('speed', ${i}, ${price})" 
                        style="width: 100%; padding: 9px; background: ${canAfford && !isMax ? '#ffcc00' : '#333'}; color: ${canAfford && !isMax ? '#000' : '#888'}; border: none; border-radius: 6px; font-weight: bold; cursor: ${canAfford && !isMax ? 'pointer' : 'not-allowed'};" ${isMax || !canAfford ? 'disabled' : ''}>
                        ZN ${price.toLocaleString()}
                    </button>
                </div>
            `;
        }
        miningSec.innerHTML = miningHtml;

        // ترقيات المخزن
        let storageHtml = '';
        let currentStorageLvl = parseInt(pData.storage_level || 0); 

        for (let i = 1; i <= 10; i++) {
            let price = parseFloat(SHOP_CONFIG.storagePrices[i]);
            let capacity = parseFloat(SHOP_CONFIG.storageCapacities[i]);
            let isOwned = i <= currentStorageLvl;
            let isNextUpgrade = i === currentStorageLvl + 1;
            let canAfford = totalBal >= price;

            let btnBg = '#333', btnColor = '#888', btnText = `ZN ${price.toLocaleString()}`, isDisabled = true;

            if (isOwned) {
                btnBg = '#00cc66'; btnColor = '#000'; btnText = 'تم الشراء ✔️';
            } else if (isNextUpgrade) {
                if (canAfford) { btnBg = '#0088cc'; btnColor = '#fff'; isDisabled = false; }
            } else {
                btnText = 'مغلق 🔒';
            }

            storageHtml += `
                <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 12px; text-align: center; display: flex; flex-direction: column; justify-content: space-between;">
                    <div>
                        <div style="font-size: 26px;">📦</div>
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
        if (getStoredBalance() < parseFloat(price)) {
            triggerHaptic('notification', 'error');
            alert("⚠️ الرصيد غير كافي لشراء هذا التطوير!");
            return; 
        }

        triggerHaptic('impact', 'light');
        const overlay = document.getElementById('shop-confirm-modal-overlay');
        const confirmBtn = document.getElementById('shop-modal-confirm-btn');

        if (confirmBtn) {
            confirmBtn.onclick = function() {
                closeShopModal();
                executeActualPurchase(type, level, price);
            };
        }

        if (overlay) overlay.classList.add('shop-modal-active');
    };

    async function executeActualPurchase(type, level, price) {
        const initData = window.Telegram?.WebApp?.initData; 
        if (!initData) return alert("⚠️ يجب فتح اللعبة من داخل تليجرام.");

        if (isBuying) return;
        isBuying = true;

        let apiType = (type === 'speed') ? 'mining' : 'storage';

        try {
            let response = await fetch('/api/shop/buy', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${initData}`
                },
                body: JSON.stringify({ type: apiType, level_num: level })
            });

            let resData = await response.json();

            if (response.ok && resData.success) {
                triggerHaptic('notification', 'success');
                setStoredBalance(resData.balance);

                if (!window.PlayerData) window.PlayerData = {};
                window.PlayerData.balance = resData.balance;
                
                if (apiType === 'mining') {
                    window.PlayerData.hourly_rate = resData.hourly_rate;
                    window.PlayerData.upgrades = resData.upgrades;
                } else {
                    window.PlayerData.storage_level = resData.storage_level;
                    window.PlayerData.max_cap = resData.max_cap;
                }
                window.updateShopUI();
            } else {
                alert(resData.error || "حدث خطأ أثناء الشراء.");
            }
        } catch (e) {
            console.error("Shop Purchase Error:", e);
        } finally {
            isBuying = false; 
        }
    }

    document.addEventListener("DOMContentLoaded", () => {
        initTonConnect();
        loadShopConfig();
        window.updateShopUI();
    });

})();

(function initShop() {
    'use strict';

    let tonConnectUI = null;
    let isBuying = false;
    let shopDynamicSettings = null;

    function triggerHaptic(type = 'impact', style = 'medium') {
        if (window.Telegram?.WebApp?.HapticFeedback) {
            if (type === 'impact') window.Telegram.WebApp.HapticFeedback.impactOccurred(style);
            else if (type === 'notification') window.Telegram.WebApp.HapticFeedback.notificationOccurred(style);
        }
    }

    // تهيئة نظام الربط بالمحفظة تلقائياً مع محاولات إعادة التهيئة الآمنة
    function initTonConnect() {
        if (tonConnectUI) return tonConnectUI;

        try {
            if (window.TON_CONNECT_UI) {
                tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
                    manifestUrl: `${window.location.origin}/tonconnect-manifest.json`,
                    buttonRootId: 'ton-connect-btn'
                });
                console.log("✅ TonConnect UI Intialized!");
                return tonConnectUI;
            }
        } catch (e) {
            console.error("TonConnect Init Error:", e);
        }
        return null;
    }

    // الانتظار الآمن في حالة الضغط على الشراء وكانت المحفظة لم تكتمل في الخلفية
    async function ensureTonConnectReady() {
        if (tonConnectUI) return tonConnectUI;
        initTonConnect();
        if (tonConnectUI) return tonConnectUI;

        let retries = 0;
        while (!window.TON_CONNECT_UI && retries < 15) {
            await new Promise(res => setTimeout(res, 200));
            retries++;
        }

        return initTonConnect();
    }

    async function loadShopConfig() {
        try {
            const res = await fetch('/api/shop/get_config');
            const data = await res.json();
            if (data.success) {
                shopDynamicSettings = data.settings;
                
                // تحديث سعر TON المباشر في الصفحة
                const tonPriceElem = document.getElementById('ton-live-rate-text');
                if (tonPriceElem && data.ton_price_usd) {
                    tonPriceElem.innerText = `$${parseFloat(data.ton_price_usd).toFixed(2)}`;
                }

                // عرض الباقات المجلوبة ديناميكياً من قاعدة البيانات
                renderDynamicPackages(data.packages);

                // تحديث واجهة السرعات والمخازن بحسب قيم الداتا بيز
                window.updateShopUI();
            }
        } catch (e) {
            console.error("خطأ في تحميل إعدادات المتجر من الداتا بيز:", e);
        }
    }

    // بناء كروت الباقات المميزة ديناميكياً من الداتا بيز (حتى لو أضاف الأدمن باقة جديدة من البوت)
    function renderDynamicPackages(packages) {
        const container = document.getElementById('usdt-packages-container');
        if (!container || !packages) return;

        let html = '';
        const colorThemes = [
            { bg: 'linear-gradient(135deg, #1c1c1c, #2a2a2a)', border: 'var(--primary)', btn: 'var(--primary)', icon: '📦' },
            { bg: 'linear-gradient(135deg, #1c1c1c, #1f3a2b)', border: 'var(--accent-green)', btn: 'var(--accent-green)', icon: '🚀' },
            { bg: 'linear-gradient(135deg, #1c1c1c, #332b00)', border: 'var(--gold)', btn: 'var(--gold)', icon: '👑', textColor: '#000' },
            { bg: 'linear-gradient(135deg, #1c1c1c, #3a1c1c)', border: 'var(--accent-red)', btn: 'var(--accent-red)', icon: '🐋' }
        ];

        let index = 0;
        for (const [pkgId, pkg] of Object.entries(packages)) {
            const theme = colorThemes[index % colorThemes.length];
            const btnTextColor = theme.textColor || '#fff';

            html += `
                <div class="usdt-card" style="background: ${theme.bg}; border: 1px solid ${theme.border};">
                    <div>
                        <div style="font-size: 24px;">${theme.icon}</div>
                        <div style="color: #fff; font-weight: bold; font-size: 13px;">${pkg.title || 'باقة مميزة'}</div>
                        <div style="color: ${theme.border}; font-weight: bold; font-size: 15px; margin: 2px 0;">$${pkg.usdt}</div>
                        <div style="color: var(--ton-blue); font-size: 11px; font-weight: bold;">~${pkg.ton_amount} TON</div>
                    </div>
                    <div class="usdt-perks">
                        ⚡ +${Number(pkg.rate_add).toLocaleString()} ZN/h<br>
                        📦 +${Number(pkg.storage_add).toLocaleString()} مخزن<br>
                        🪙 +${Number(pkg.zn_add).toLocaleString()} ZN
                    </div>
                    <button class="btn-ton-pay" style="background: ${theme.btn}; color: ${btnTextColor};" onclick="buyPackageWithTon('${pkgId}')">شراء تلقائي</button>
                </div>
            `;
            index++;
        }

        container.innerHTML = html;
    }

    window.buyPackageWithTon = async function(packageId) {
        if (isBuying) return;

        const initData = window.Telegram?.WebApp?.initData;
        if (!initData) {
            alert("⚠️ يجب فتح التطبيق من داخل تليجرام.");
            return;
        }

        triggerHaptic('impact', 'medium');
        
        const tcInstance = await ensureTonConnectReady();
        if (!tcInstance) {
            alert("⚠️ جاري إعداد الاتصال بالمحفظة، يرجى المحاولة بعد ثوانٍ.");
            return;
        }

        try {
            if (!tcInstance.connected) {
                await tcInstance.openModal();

                let attempts = 0;
                while (!tcInstance.connected && attempts < 40) {
                    await new Promise(resolve => setTimeout(resolve, 500));
                    attempts++;
                }

                if (!tcInstance.connected) {
                    alert("⚠️ يجب ربط المحفظة إولاً لإتمام عملية الشراء.");
                    return;
                }
            }

            isBuying = true;

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
                isBuying = false;
                return;
            }

            const transaction = {
                validUntil: Math.floor(Date.now() / 1000) + 600,
                messages: [{
                    address: prepData.recipient_address,
                    amount: prepData.nano_ton,
                    payload: prepData.payload_memo
                }]
            };

            const result = await tcInstance.sendTransaction(transaction);

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
                alert("🎉 تم تأكيد الدفع وتفعيل الباقة وحفظ المعاملة بنجاح!");

                if (window.userState) {
                    window.userState.balance = verifyData.result.balance;
                    window.userState.hourly_rate = verifyData.result.hourly_rate;
                    window.userState.max_cap = verifyData.result.max_cap;
                    window.userState.usd_balance = verifyData.result.usd_balance;
                }

                window.updateShopUI();
            } else {
                alert("⚠️ " + verifyData.error);
            }

        } catch (e) {
            console.error("Payment Flow Error:", e);
            triggerHaptic('notification', 'error');
            alert("❌ تم إلغاء المعاملة أو حدث خطأ أثناء الاتصال بالمحفظة.");
        } finally {
            isBuying = false;
        }
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

        const pData = window.userState || { balance: 0, hourly_rate: 0, upgrades: {}, storage_level: 0, usd_balance: 0 };
        let totalBal = parseFloat(pData.balance || 0);

        // تحديث إحصائيات أعلى الصفحة المباشرة بما فيها الدولار USD
        const usdElem = document.getElementById('shop-usd-text');
        if (usdElem) {
            usdElem.innerText = `$${parseFloat(pData.usd_balance || 0).toFixed(2)}`;
        }
        const balElem = document.getElementById('shop-balance-text');
        if (balElem) balElem.innerText = Math.floor(totalBal).toLocaleString();
        
        const rateElem = document.getElementById('shop-rate-text');
        if (rateElem) rateElem.innerText = `${parseFloat(pData.hourly_rate || 0).toLocaleString()}/h`;

        // إعدادات الترقية من الداتا بيز
        const miningCfg = shopDynamicSettings?.mining_config || {
            "1": {"price": 2000, "rate": 5, "max": 10},
            "2": {"price": 7000, "rate": 15, "max": 10},
            "3": {"price": 18000, "rate": 35, "max": 10},
            "4": {"price": 45000, "rate": 80, "max": 10},
            "5": {"price": 110000, "rate": 180, "max": 10},
            "6": {"price": 260000, "rate": 400, "max": 10},
            "7": {"price": 600000, "rate": 900, "max": 10},
            "8": {"price": 1400000, "rate": 2000, "max": 10},
            "9": {"price": 3200000, "rate": 4500, "max": 10}
        };

        let miningHtml = '';
        for (const [i, cfg] of Object.entries(miningCfg)) {
            let count = parseInt((pData.upgrades && pData.upgrades[`lvl${i}`]) || 0);
            let price = parseFloat(cfg.price);
            let speed = parseFloat(cfg.rate); 
            let maxLimit = parseInt(cfg.max || 10);
            let isMax = count >= maxLimit;
            let canAfford = totalBal >= price;

            miningHtml += `
                <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 12px; text-align: center; position: relative; display: flex; flex-direction: column; justify-content: space-between;">
                    ${isMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; border-radius: 12px;">مكتمل MAX</div>` : ''}
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

        const storageCfg = shopDynamicSettings?.storage_config || {
            "1": {"price": 3000, "capacity": 600},
            "2": {"price": 10000, "capacity": 1500},
            "3": {"price": 25000, "capacity": 3500},
            "4": {"price": 65000, "capacity": 8000},
            "5": {"price": 160000, "capacity": 18000},
            "6": {"price": 400000, "capacity": 40000},
            "7": {"price": 950000, "capacity": 90000},
            "8": {"price": 2200000, "capacity": 200000},
            "9": {"price": 5000000, "capacity": 450000},
            "10": {"price": 12000000, "capacity": 1000000}
        };

        let storageHtml = '';
        let currentStorageLvl = parseInt(pData.storage_level || 0); 

        for (const [iStr, cfg] of Object.entries(storageCfg)) {
            let i = parseInt(iStr);
            let price = parseFloat(cfg.price);
            let capacity = parseFloat(cfg.capacity);
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
        const curBal = parseFloat(window.userState?.balance || 0);
        if (curBal < parseFloat(price)) {
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

                if (window.userState) {
                    window.userState.balance = resData.balance;
                    if (apiType === 'mining') {
                        window.userState.hourly_rate = resData.hourly_rate;
                        window.userState.upgrades = resData.upgrades;
                    } else {
                        window.userState.storage_level = resData.storage_level;
                        window.userState.max_cap = resData.max_cap;
                    }
                    if (resData.usd_balance !== undefined) {
                        window.userState.usd_balance = resData.usd_balance;
                    }
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
    });

})();

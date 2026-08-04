// shop/shop.js
// =================================================================
// 🛒 ZN Goxe - Shop Module (Optimized Layout & Safe Formatting)
// =================================================================

(function initShop() {
    'use strict';

    let tonConnectUI = null;
    let isBuying = false;
    let shopDynamicSettings = null;
    let cachedPackagesData = null;
    let lastConfigFetchTime = 0;
    const CONFIG_CACHE_TTL = 300000;

    function triggerHaptic(type = 'impact', style = 'medium') {
        if (window.Telegram?.WebApp?.HapticFeedback) {
            if (type === 'impact') window.Telegram.WebApp.HapticFeedback.impactOccurred(style);
            else if (type === 'notification') window.Telegram.WebApp.HapticFeedback.notificationOccurred(style);
        }
    }

    // =================================================================
    // 🧮 0. تنسيق الأرقام مع إجبار العرض الأفقي المباشر لحل التكدس العمودي
    // =================================================================
    function renderFormattedBalanceHTML(val, decimals = 2, prefix = '', suffix = '') {
        let num = parseFloat(val);
        if (isNaN(num)) num = 0;

        if (num >= 1000000000) {
            return `<span dir="ltr" style="white-space:nowrap; display:inline !important;">${prefix}${(num / 1000000000).toFixed(2)}B${suffix}</span>`;
        }
        if (num >= 10000000) { 
            return `<span dir="ltr" style="white-space:nowrap; display:inline !important;">${prefix}${(num / 1000000).toFixed(2)}M${suffix}</span>`;
        }

        const parts = num.toFixed(decimals).split('.');
        const intFormatted = Math.floor(parts[0]).toLocaleString('en-US');

        if (decimals === 0 || !parts[1]) {
            return `<span dir="ltr" style="white-space:nowrap; display:inline !important;">${prefix}<span class="int-part" style="display:inline !important; font-size:1em; font-weight:800;">${intFormatted}</span>${suffix}</span>`;
        }

        return `<span dir="ltr" style="white-space:nowrap; display:inline !important;">${prefix}<span class="int-part" style="display:inline !important; font-size:1em; font-weight:800;">${intFormatted}</span>.<span class="dec-part" style="display:inline !important; font-size:0.78em; opacity:0.75; font-weight:600;">${parts[1]}</span>${suffix}</span>`;
    }

    // =================================================================
    // 🧮 1. دالة التحديث البصري التدريجي للأرقام
    // =================================================================
    function animateValue(element, start, end, duration = 800, decimals = 2, prefix = '', suffix = '') {
        if (!element) return;
        if (isNaN(start)) start = 0;
        if (isNaN(end)) end = 0;

        if (Math.abs(start - end) < 0.001) {
            element.innerHTML = renderFormattedBalanceHTML(end, decimals, prefix, suffix);
            element.dataset.currentVal = end;
            return;
        }

        let startTimestamp = null;
        const step = (timestamp) => {
            if (!startTimestamp) startTimestamp = timestamp;
            const progress = Math.min((timestamp - startTimestamp) / duration, 1);
            const current = start + (end - start) * progress;

            element.innerHTML = renderFormattedBalanceHTML(current, decimals, prefix, suffix);

            if (progress < 1) {
                window.requestAnimationFrame(step);
            } else {
                element.innerHTML = renderFormattedBalanceHTML(end, decimals, prefix, suffix);
                element.dataset.currentVal = end;
            }
        };
        window.requestAnimationFrame(step);
    }

    function initTonConnect() {
        if (tonConnectUI) return tonConnectUI;
        try {
            if (window.TON_CONNECT_UI) {
                tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
                    manifestUrl: `${window.location.origin}/tonconnect-manifest.json`,
                    buttonRootId: 'ton-connect-btn'
                });
                return tonConnectUI;
            }
        } catch (e) {
            console.error("TonConnect Init Error:", e);
        }
        return null;
    }

    async function ensureTonConnectReady() {
        if (tonConnectUI) return tonConnectUI;
        initTonConnect();
        if (tonConnectUI) return tonConnectUI;

        let retries = 0;
        while (!window.TON_CONNECT_UI && retries < 10) {
            await new Promise(res => setTimeout(res, 200));
            retries++;
        }

        return initTonConnect();
    }

    // =================================================================
    // 📦 2. تحميل إعدادات المتجر
    // =================================================================
    async function loadShopConfig(forceFetch = false) {
        const now = Date.now();

        if (!forceFetch && !shopDynamicSettings) {
            try {
                const cached = sessionStorage.getItem('zn_shop_config');
                const cachedTime = sessionStorage.getItem('zn_shop_config_time');
                if (cached && cachedTime && (now - parseInt(cachedTime) < CONFIG_CACHE_TTL)) {
                    const parsed = JSON.parse(cached);
                    shopDynamicSettings = parsed.settings;
                    cachedPackagesData = parsed.packages;
                    applyConfigToUI(parsed);
                    return;
                }
            } catch (e) {
                console.warn("فشل قراءة كاش المتجر المحلي:", e);
            }
        }

        if (!forceFetch && shopDynamicSettings && (now - lastConfigFetchTime < CONFIG_CACHE_TTL)) {
            if (cachedPackagesData) {
                renderDynamicPackages(cachedPackagesData);
            }
            window.updateShopUI();
            return;
        }

        try {
            const res = await fetch('/api/shop/get_config');
            const data = await res.json();
            if (data && data.success) {
                shopDynamicSettings = data.settings;
                cachedPackagesData = data.packages;
                lastConfigFetchTime = now;

                try {
                    sessionStorage.setItem('zn_shop_config', JSON.stringify(data));
                    sessionStorage.setItem('zn_shop_config_time', now.toString());
                } catch (e) {}

                applyConfigToUI(data);
            }
        } catch (e) {
            console.error("خطأ في تحميل إعدادات المتجر:", e);
        }
    }

    function applyConfigToUI(data) {
        const tonPriceElem = document.getElementById('ton-live-rate-text');
        if (tonPriceElem) {
            const livePrice = data.ton_price_usd || window.tonPrice || window.userState?.ton_price;
            if (livePrice) {
                tonPriceElem.innerText = `$${parseFloat(livePrice).toFixed(2)}`;
            }
        }

        if (data.packages) {
            cachedPackagesData = data.packages;
            renderDynamicPackages(data.packages);
        }
        
        window.updateShopUI();
    }

    function renderDynamicPackages(packages) {
        let container = document.getElementById('usdt-packages-container');
        if (!container) return;

        if (!packages || (typeof packages !== 'object')) {
            container.innerHTML = '<div style="color: #aaaaaa; text-align: center; width: 100%; padding: 10px;">لا توجد باقات متاحة حالياً.</div>';
            return;
        }

        const entries = Array.isArray(packages) 
            ? packages.map((p, idx) => [`pkg_${idx + 1}`, p]) 
            : Object.entries(packages);

        if (entries.length === 0) {
            container.innerHTML = '<div style="color: #aaaaaa; text-align: center; width: 100%; padding: 10px;">لا توجد باقات متاحة حالياً.</div>';
            return;
        }

        let html = '';
        const colorThemes = [
            { bg: 'linear-gradient(135deg, #1c1c1c, #2a2a2a)', border: '#ffcc00', btn: '#ffcc00', icon: '📦', textColor: '#000000' },
            { bg: 'linear-gradient(135deg, #1c1c1c, #1f3a2b)', border: '#00cc66', btn: '#00cc66', icon: '🚀', textColor: '#000000' },
            { bg: 'linear-gradient(135deg, #1c1c1c, #332b00)', border: '#ffd700', btn: '#ffd700', icon: '👑', textColor: '#000000' },
            { bg: 'linear-gradient(135deg, #1c1c1c, #3a1c1c)', border: '#ff4444', btn: '#ff4444', icon: '🐋', textColor: '#ffffff' }
        ];

        let index = 0;
        for (const [pkgId, pkg] of entries) {
            if (!pkg) continue;
            const theme = colorThemes[index % colorThemes.length];
            const btnTextColor = theme.textColor || '#ffffff';

            const usdtPrice = parseFloat(pkg.usdt || 0).toFixed(2);
            const tonAmount = parseFloat(pkg.ton_amount || 0).toFixed(2);

            html += `
                <div class="usdt-card" style="background: ${theme.bg}; border: 1px solid ${theme.border};">
                    <div>
                        <div style="font-size: 24px;">${theme.icon}</div>
                        <div style="color: #ffffff; font-weight: bold; font-size: 13px;">${pkg.title || 'باقة مميزة'}</div>
                        <div style="color: ${theme.border}; font-weight: bold; font-size: 16px; margin: 4px 0;">$${usdtPrice}</div>
                        <div style="color: #0088cc; font-size: 11px; font-weight: bold; margin-bottom: 8px;">~${tonAmount} TON</div>
                    </div>
                    <div class="usdt-perks">
                        ⚡ +${Number(pkg.rate_add || 0).toLocaleString()} ZN/h<br>
                        📦 +${Number(pkg.storage_add || 0).toLocaleString()} مخزن<br>
                        🪙 +${Number(pkg.zn_add || 0).toLocaleString()} ZN
                    </div>
                    <button class="btn-ton-pay" style="background: ${theme.btn}; color: ${btnTextColor};" onclick="buyPackageWithTon('${pkgId}')">شراء تلقائي</button>
                </div>
            `;
            index++;
        }

        container.innerHTML = html;
    }

    // =================================================================
    // 💎 3. شراء الباقات بـ TON
    // =================================================================
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
                    alert("⚠️ يجب ربط المحفظة أولاً لإتمام عملية الشراء.");
                    return;
                }
            }

            isBuying = true;

            const prepRes = await fetch('/api/shop/prepare_ton_pay', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `twa ${initData}`
                },
                body: JSON.stringify({ 
                    package_id: packageId,
                    initData: initData 
                })
            });

            const prepData = await prepRes.json();
            if (!prepData.success) {
                alert("خطأ: " + (prepData.error || prepData.message));
                isBuying = false;
                return;
            }

            const cleanNanoTon = String(Math.floor(Number(prepData.nano_ton)));

            const transaction = {
                validUntil: Math.floor(Date.now() / 1000) + 600,
                messages: [{
                    address: prepData.recipient_address,
                    amount: cleanNanoTon
                }]
            };

            const result = await tcInstance.sendTransaction(transaction);
            
            let safeBoc = "TX_" + Date.now();
            if (result && result.boc) {
                safeBoc = String(result.boc).replace(/[^a-zA-Z0-9]/g, '').substring(0, 32);
            }

            const verifyRes = await fetch('/api/shop/verify_and_apply_package', {
                method: 'POST',
                headers: { 
                    'Content-Type': 'application/json',
                    'Authorization': `twa ${initData}`
                },
                body: JSON.stringify({
                    package_id: packageId,
                    boc: safeBoc,
                    initData: initData
                })
            });

            const verifyData = await verifyRes.json();
            if (verifyData.success && verifyData.result) {
                triggerHaptic('notification', 'success');
                alert("🎉 تم تأكيد الدفع وتفعيل الباقة بنجاح!");

                const res = verifyData.result;
                if (!window.userState) window.userState = {};
                if (res.balance !== undefined) window.userState.balance = res.balance;
                if (res.hourly_rate !== undefined) window.userState.hourly_rate = res.hourly_rate;
                if (res.extra_storage !== undefined) window.userState.extra_storage = res.extra_storage;
                if (res.max_cap !== undefined) window.userState.max_cap = res.max_cap;

                window.updateShopUI();
            } else {
                alert("⚠️ " + (verifyData.error || verifyData.message));
            }

        } catch (e) {
            console.error("Payment Flow Error:", e);
            triggerHaptic('notification', 'error');
            alert("❌ تم إلغاء المعاملة أو حدث خطأ أثناء الاتصال بالمحفظة.");
        } finally {
            isBuying = false;
        }
    };

    // =================================================================
    // 🎨 4. نافذة التأكيد (Modal UI)
    // =================================================================
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
                    background: #1a1a1a; border: 1px solid #333333; border-radius: 20px;
                    padding: 24px; width: 85%; max-width: 320px; text-align: center;
                    box-shadow: 0 10px 40px rgba(0,0,0,0.8);
                    transform: translateY(30px) scale(0.95);
                    transition: all 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275);
                }
                .shop-modal-active { display: flex !important; opacity: 1 !important; }
                .shop-modal-active > #shop-confirm-modal { transform: translateY(0) scale(1); }
                .shop-modal-title { color: #ffffff; font-size: 20px; font-weight: bold; margin-bottom: 8px; }
                .shop-modal-desc { color: #aaaaaa; font-size: 14px; margin-bottom: 15px; line-height: 1.5; }
                .shop-modal-price-box { 
                    background: #000000; border-radius: 12px; padding: 12px; 
                    color: #ffcc00; font-weight: bold; font-size: 18px; margin-bottom: 20px;
                    border: 1px solid #333333;
                }
                .shop-modal-actions { display: flex; gap: 12px; justify-content: center; }
                .shop-btn { flex: 1; padding: 12px; border: none; border-radius: 10px; font-weight: bold; font-size: 15px; cursor: pointer; }
                .shop-btn-cancel { background: #333333; color: #ffffff; }
                .shop-btn-confirm { background: #0088cc; color: #ffffff; }
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

    // =================================================================
    // 🔄 5. التبديل بين التبويبات
    // =================================================================
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
            if (btnStorage) btnStorage.style.background = '#333333';
        } else {
            miningSec.style.display = 'none';
            storageSec.style.display = 'grid';
            if (btnMining) btnMining.style.background = '#333333';
            if (btnStorage) btnStorage.style.background = '#0088cc';
        }
    };

    // =================================================================
    // 🔄 6. تحديث واجهة المتجر (Render UI)
    // =================================================================
    window.updateShopUI = function() {
        if (cachedPackagesData) {
            renderDynamicPackages(cachedPackagesData);
        }

        const miningSec = document.getElementById('shop-mining-section');
        const storageSec = document.getElementById('shop-storage-section');
        if (!miningSec || !storageSec) return;

        const pData = window.userState || {};
        let totalBal = parseFloat(pData.balance || 0);

        const usdElem = document.getElementById('shop-usd-text');
        if (usdElem) {
            const curUsd = parseFloat(usdElem.dataset.currentVal) || 0;
            animateValue(usdElem, curUsd, parseFloat(pData.usd_balance || 0), 600, 2, '$');
        }

        const balElem = document.getElementById('shop-balance-text');
        if (balElem) {
            const curBal = parseFloat(balElem.dataset.currentVal) || 0;
            animateValue(balElem, curBal, totalBal, 600, 2);
        }
        
        const rateElem = document.getElementById('shop-rate-text');
        if (rateElem) {
            const hRate = parseFloat(pData.hourly_rate || 0);
            rateElem.innerHTML = `<span dir="ltr" style="display:inline !important;">+${hRate.toFixed(2)}/h</span>`;
        }

        const defaultMiningCfg = {
            "1": {"price": 3500, "rate": 5, "max": 10},
            "2": {"price": 11500, "rate": 15, "max": 10},
            "3": {"price": 28000, "rate": 35, "max": 10},
            "4": {"price": 68000, "rate": 80, "max": 10},
            "5": {"price": 165000, "rate": 180, "max": 10},
            "6": {"price": 390000, "rate": 400, "max": 10},
            "7": {"price": 950000, "rate": 900, "max": 10},
            "8": {"price": 2300000, "rate": 2000, "max": 10},
            "9": {"price": 5500000, "rate": 4500, "max": 10}
        };

        const miningCfg = shopDynamicSettings?.mining_config || shopDynamicSettings?.speed_config || defaultMiningCfg;

        let miningHtml = '';
        for (const [key, cfg] of Object.entries(miningCfg)) {
            if (isNaN(parseInt(key))) continue;

            let i = parseInt(key);
            let count = parseInt((pData.upgrades && pData.upgrades[`lvl${i}`]) || 0);
            let price = parseFloat(cfg.price);
            let speed = parseFloat(cfg.rate); 
            let maxLimit = parseInt(cfg.max || 10);
            let isMax = count >= maxLimit;
            let canAfford = totalBal >= price;

            miningHtml += `
                <div style="background: #1a1a1a; border: 1px solid #333333; border-radius: 12px; padding: 12px; text-align: center; position: relative; display: flex; flex-direction: column; justify-content: space-between;">
                    ${isMax ? `<div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.85); display: flex; align-items: center; justify-content: center; font-weight: bold; color: #ffcc00; border-radius: 12px;">مكتمل MAX</div>` : ''}
                    <div>
                        <div style="font-size: 26px;">⚡</div>
                        <div style="color: #ffffff; font-weight: bold; font-size: 14px;">مستوى ${i}</div>
                        <div style="color: #00cc66; font-size: 12px; margin: 4px 0;" dir="ltr">⚡ +${speed.toLocaleString()}/h</div>
                        <div style="color: #888888; font-size: 11px; margin-bottom: 10px;">تم الشراء: ${count} / ${maxLimit}</div>
                    </div>
                    <button id="btn-speed-${i}" onclick="requestShopPurchase('speed', ${i}, ${price})" 
                        style="width: 100%; padding: 9px; background: ${canAfford && !isMax ? '#ffcc00' : '#333333'}; color: ${canAfford && !isMax ? '#000000' : '#888888'}; border: none; border-radius: 6px; font-weight: bold; cursor: ${canAfford && !isMax ? 'pointer' : 'not-allowed'};" ${isMax || !canAfford ? 'disabled' : ''}>
                        ZN ${price.toLocaleString()}
                    </button>
                </div>
            `;
        }
        miningSec.innerHTML = miningHtml;

        const defaultStorageCfg = {
            "1": {"capacity": 300, "price": 3000},
            "2": {"capacity": 800, "price": 8500},
            "3": {"capacity": 2000, "price": 25000},
            "4": {"capacity": 5000, "price": 70000},
            "5": {"capacity": 12000, "price": 180000},
            "6": {"capacity": 28000, "price": 450000},
            "7": {"capacity": 65000, "price": 1100000},
            "8": {"capacity": 150000, "price": 2800000},
            "9": {"capacity": 350000, "price": 7000000},
            "10": {"capacity": 800000, "price": 18000000}
        };

        const storageCfg = shopDynamicSettings?.storage_config || defaultStorageCfg;

        let storageHtml = '';
        let currentStorageLvl = parseInt(pData.storage_level || 0); 

        for (const [key, cfg] of Object.entries(storageCfg)) {
            if (isNaN(parseInt(key)) || key === "0") continue;

            let i = parseInt(key);
            let price = parseFloat(cfg.price);
            let capacity = parseFloat(cfg.capacity);
            let isOwned = i <= currentStorageLvl;
            let isNextUpgrade = i === currentStorageLvl + 1;
            let canAfford = totalBal >= price;

            let btnBg = '#333333', btnColor = '#888888', btnText = `ZN ${price.toLocaleString()}`, isDisabled = true;

            if (isOwned) {
                btnBg = '#00cc66'; btnColor = '#000000'; btnText = 'تم الشراء ✔️';
            } else if (isNextUpgrade) {
                if (canAfford) { btnBg = '#0088cc'; btnColor = '#ffffff'; isDisabled = false; }
            } else {
                btnText = 'مغلق 🔒';
            }

            storageHtml += `
                <div style="background: #1a1a1a; border: 1px solid #333333; border-radius: 12px; padding: 12px; text-align: center; display: flex; flex-direction: column; justify-content: space-between;">
                    <div>
                        <div style="font-size: 26px;">📦</div>
                        <div style="color: #ffffff; font-weight: bold; font-size: 14px;">مخزن مستوى ${i}</div>
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

    // =================================================================
    // ⚡ 7. طلب الشراء وتنفيذه
    // =================================================================
    window.requestShopPurchase = function(type, level, price) {
        const curBal = parseFloat(window.userState?.balance || 0);
        if (curBal < parseFloat(price)) {
            triggerHaptic('notification', 'error');
            alert("⚠️ الرصيد غير كافي لشراء هذا التطوير!");
            return; 
        }

        triggerHaptic('impact', 'light');

        const modalTitle = document.getElementById('shop-modal-title');
        const modalDesc = document.getElementById('shop-modal-desc');
        const modalPrice = document.getElementById('shop-modal-price');

        if (type === 'speed') {
            if (modalTitle) modalTitle.innerText = `تأكيد ترقية السرعة (مستوى ${level})`;
            if (modalDesc) modalDesc.innerText = `هل تريد إضافة هذه السرعة إلى معدل التعدين الخاص بك؟`;
        } else {
            if (modalTitle) modalTitle.innerText = `تأكيد ترقية المخزن (مستوى ${level})`;
            if (modalDesc) modalDesc.innerText = `هل تريد توسيع سعة التخزين للاحتفاظ بأرباح أكثر؟`;
        }

        if (modalPrice) {
            modalPrice.innerText = `${Number(price).toLocaleString()} ZN`;
        }

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
                    'Authorization': `twa ${initData}`
                },
                body: JSON.stringify({ 
                    type: apiType, 
                    level_num: level,
                    initData: initData 
                })
            });

            let resData = await response.json();

            if (response.ok && resData.success) {
                triggerHaptic('notification', 'success');

                if (!window.userState) window.userState = {};
                if (resData.balance !== undefined) window.userState.balance = resData.balance;
                if (resData.hourly_rate !== undefined) window.userState.hourly_rate = resData.hourly_rate;
                if (resData.upgrades !== undefined) window.userState.upgrades = resData.upgrades;
                if (resData.storage_level !== undefined) window.userState.storage_level = resData.storage_level;
                if (resData.extra_storage !== undefined) window.userState.extra_storage = resData.extra_storage;
                if (resData.max_cap !== undefined) window.userState.max_cap = resData.max_cap;
                if (resData.usd_balance !== undefined) window.userState.usd_balance = resData.usd_balance;
                if (resData.last_claim_time !== undefined) window.userState.last_claim_time = resData.last_claim_time;
                if (resData.unclaimed !== undefined) window.userState.unclaimed = resData.unclaimed;

                window.updateShopUI();
            } else {
                alert("⚠️ " + (resData.error || resData.message || "حدث خطأ أثناء الشراء."));
            }
        } catch (e) {
            console.error("Shop Purchase Error:", e);
            alert("❌ تعذر الاتصال بالسيرفر.");
        } finally {
            isBuying = false; 
        }
    }

    function boot() {
        initTonConnect();
        loadShopConfig(false);
    }

    if (document.readyState === 'loading') {
        document.addEventListener("DOMContentLoaded", boot);
    } else {
        boot();
    }

    window.addEventListener('userStateUpdated', () => {
        window.updateShopUI();
    });

})();

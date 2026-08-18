window.depositModule = (function () {
    let tonPriceUsd = 1.32;
    let packagesUnsubscribe = null;

    // الباقات الافتراضية للتحميل اللحظي الفوري
    let currentPackages = [
        { id: 1, usdt_amount: 0.5, name_ar: "باقة $0.5 USDT", is_active: true, sort_order: 1 },
        { id: 2, usdt_amount: 1.5, name_ar: "باقة $1.5 USDT", is_active: true, sort_order: 2 },
        { id: 3, usdt_amount: 5.0, name_ar: "باقة $5 USDT", is_active: true, sort_order: 3 },
        { id: 4, usdt_amount: 10.0, name_ar: "باقة $10 USDT", is_active: true, sort_order: 4 },
        { id: 5, usdt_amount: 15.0, name_ar: "باقة $15 USDT", is_active: true, sort_order: 5 }
    ];

    async function fetchTonLivePrice() {
        try {
            const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd');
            if (res.ok) {
                const data = await res.json();
                if (data['the-open-network']?.usd) {
                    tonPriceUsd = parseFloat(data['the-open-network'].usd);
                    const priceElem = document.getElementById('ton-live-price');
                    if (priceElem) priceElem.innerText = `$${tonPriceUsd.toFixed(2)}`;
                }
            }
        } catch (e) {
            console.warn("⚠️ استخدام السعر المرجعي لـ TON:", e);
        }
    }

    // الربط اللحظي المباشر مع Firebase Firestore
    function listenToFirebasePackages() {
        if (!window.db) return false;

        try {
            if (packagesUnsubscribe) {
                packagesUnsubscribe();
                packagesUnsubscribe = null;
            }

            packagesUnsubscribe = window.db.collection('settings').doc('deposit_settings')
                .onSnapshot(doc => {
                    if (doc.exists) {
                        const data = doc.data() || {};
                        const pkgs = data.packages || [];
                        const activePkgs = pkgs.filter(p => p.is_active !== false);
                        if (activePkgs.length > 0) {
                            activePkgs.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
                            currentPackages = activePkgs;
                            renderPackages(currentPackages);
                        }
                    }
                }, err => {
                    console.warn("⚠️ خطأ المزامنة اللحظية لباقات الإيداع:", err);
                });
            return true;
        } catch (e) {
            console.warn("⚠️ تعذر تشغيل مستمع الفايربيس للحظي:", e);
            return false;
        }
    }

    async function loadPackages() {
        // 1. عرض فوري للباقات الحالية
        renderPackages(currentPackages);

        // 2. تفعيل المزامنة اللحظية المباشرة مع الفايربيس
        const isRealtimeActive = listenToFirebasePackages();

        // 3. جلب الاحتياطي عبر API إذا لم يكن Firestore Realtime متصلاً
        if (!isRealtimeActive) {
            try {
                const res = await fetch('/api/wallet/deposit/packages');
                if (res.ok) {
                    const data = await res.json();
                    if (data.success && data.packages && data.packages.length > 0) {
                        currentPackages = data.packages;
                        renderPackages(data.packages);
                    }
                }
            } catch (err) {
                console.warn("⚠️ الاعتماد على باقات الإيداع المحمّلة إفتراضياً:", err);
            }
        }
    }

    function renderPackages(packages) {
        const grid = document.getElementById('deposit-packages-grid');
        if (!grid) return;

        grid.innerHTML = packages.map(pkg => {
            const usdtVal = parseFloat(pkg.usdt_amount || 0);
            const tonEst = (usdtVal / tonPriceUsd).toFixed(3);
            return `
                <div onclick="window.depositModule?.selectPackage(${pkg.id})" style="background: linear-gradient(145deg, rgba(255,255,255,0.06), rgba(15,23,42,0.7)); border: 1px solid rgba(0, 152, 234, 0.3); border-radius: 14px; padding: 14px 10px; text-align: center; cursor: pointer; transition: all 0.2s ease; position: relative; overflow: hidden;">
                    <div style="font-size: 22px; margin-bottom: 4px;">💵</div>
                    <div style="font-size: 16px; font-weight: 800; color: #34d399; margin-bottom: 2px;">+$${usdtVal} USDT</div>
                    <div style="font-size: 11px; color: #94a3b8; margin-bottom: 10px;">بشراء بعملة TON</div>
                    <div style="background: #0098EA; color: #fff; border-radius: 8px; padding: 6px 4px; font-size: 12px; font-weight: 700;">
                        ~ ${tonEst} TON
                    </div>
                </div>
            `;
        }).join('');
    }

    async function selectPackage(packageId) {
        // المطابقة المرنة لمنع الاختلاف بين الـ String والـ Number
        const pkg = currentPackages.find(p => String(p.id) === String(packageId));
        if (!pkg) {
            alert("الباقة غير متوفرة");
            return;
        }

        const tg = window.Telegram?.WebApp;
        const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || '';

        try {
            const headers = { 'Content-Type': 'application/json' };
            if (userId) headers['X-Telegram-User-Id'] = String(userId);
            if (tg?.initData) headers['X-Telegram-Init-Data'] = tg.initData;

            const res = await fetch('/api/wallet/deposit/create_invoice', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({ 
                    package_id: pkg.id, 
                    ton_price: tonPriceUsd, 
                    usdt_amount: pkg.usdt_amount,
                    user_id: userId
                })
            });

            const data = await res.json();
            if (data.success) {
                openModal(data);
            } else {
                alert(data.error || "تعذر إنشاء طلب الشحن");
            }
        } catch (e) {
            console.error("خطأ في إنشاء طلب الإيداع:", e);
            alert("حدث خطأ في الاتصال، يرجى المحاولة لاحقاً");
        }
    }

    function openModal(invoiceData) {
        const modal = document.getElementById('deposit-pay-modal');
        const tonAmountElem = document.getElementById('modal-ton-amount');
        const usdtAmountElem = document.getElementById('modal-usdt-amount');
        const payBtn = document.getElementById('modal-pay-tg-btn');

        if (tonAmountElem) tonAmountElem.innerText = `${invoiceData.ton_amount} TON`;
        if (usdtAmountElem) usdtAmountElem.innerText = `($${invoiceData.usdt_amount} USDT)`;

        if (payBtn) {
            payBtn.onclick = () => {
                const payUrl = invoiceData.pay_url;
                const tg = window.Telegram?.WebApp;

                try {
                    // فتح الرابط بأمان مع حماية البروتوكول
                    if (tg && typeof tg.openLink === 'function') {
                        tg.openLink(payUrl);
                    } else if (tg && typeof tg.openTelegramLink === 'function' && payUrl.startsWith('https://t.me/')) {
                        tg.openTelegramLink(payUrl);
                    } else {
                        window.location.href = payUrl;
                    }
                } catch (e) {
                    console.warn("فشل التحويل التلقائي عبر Telegram API، الانتقال المباشر:", e);
                    window.location.href = payUrl;
                }
            };
        }

        if (modal) modal.style.display = 'flex';
    }

    function closeModal() {
        const modal = document.getElementById('deposit-pay-modal');
        if (modal) modal.style.display = 'none';
    }

    function init() {
        fetchTonLivePrice();
        loadPackages();
    }

    return {
        init,
        selectPackage,
        closeModal
    };
})();

window.init_deposit_module = function () {
    if (window.depositModule) {
        window.depositModule.init();
    }
};

window.depositModule = (function () {
    let tonPriceUsd = 1.32;

    let currentPackages = [
        { id: 1, usdt_amount: 0.5, name_ar: "باقة $0.5 USDT" },
        { id: 2, usdt_amount: 1.5, name_ar: "باقة $1.5 USDT" },
        { id: 3, usdt_amount: 5.0, name_ar: "باقة $5 USDT" },
        { id: 4, usdt_amount: 10.0, name_ar: "باقة $10 USDT" },
        { id: 5, usdt_amount: 15.0, name_ar: "باقة $15 USDT" }
    ];

    async function fetchTonLivePrice() {
        try {
            const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd', { cache: 'no-store' });
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

    async function loadPackages() {
        try {
            // كسر الكاش بطلب طازج لمنع حفظ القوائم القديمة بدون استهلاك قراءات زائدة
            const res = await fetch(`/api/wallet/deposit/packages?_t=${Date.now()}`, {
                cache: 'no-store',
                headers: { 'Pragma': 'no-cache', 'Cache-Control': 'no-cache' }
            });
            
            if (res.ok) {
                const data = await res.json();
                if (data.success && data.packages && data.packages.length > 0) {
                    currentPackages = data.packages;
                    renderPackages(data.packages);
                }
            }
        } catch (err) {
            console.warn("⚠️ تعذر جلب الباقات المحدثة:", err);
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
        const pkg = currentPackages.find(p => String(p.id) === String(packageId));
        if (!pkg) {
            alert("الباقة غير متوفرة حالياً");
            return;
        }

        const tg = window.Telegram?.WebApp;
        const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || '';

        try {
            const headers = { 'Content-Type': 'application/json' };
            if (userId) headers['X-Telegram-User-Id'] = String(userId);

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
                    if (tg && typeof tg.openLink === 'function') {
                        tg.openLink(payUrl);
                    } else {
                        window.location.href = payUrl;
                    }
                } catch (e) {
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
        renderPackages(currentPackages);
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

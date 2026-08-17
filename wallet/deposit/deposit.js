window.depositModule = (function () {
    let tonPriceUsd = 1.32;
    let currentPackages = [];

    async function fetchTonLivePrice() {
        try {
            const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd');
            const data = await res.json();
            if (data['the-open-network']?.usd) {
                tonPriceUsd = parseFloat(data['the-open-network'].usd);
                const priceElem = document.getElementById('ton-live-price');
                if (priceElem) priceElem.innerText = `$${tonPriceUsd.toFixed(2)}`;
            }
        } catch (e) {
            console.warn("⚠️ استخدام السعر المرجعي الافتراضي لـ TON:", e);
        }
    }

    async function loadPackages() {
        const grid = document.getElementById('deposit-packages-grid');
        if (!grid) return;

        try {
            const res = await fetch('/api/wallet/deposit/packages');
            const data = await res.json();

            if (data.success && data.packages) {
                currentPackages = data.packages;
                renderPackages(data.packages);
            }
        } catch (err) {
            console.error("فشل جلب باقات الشحن:", err);
            if (grid) grid.innerHTML = `<div style="color:#ef4444; grid-column:1/-1; text-align:center; padding:15px;">فشل تحميل الباقات، حاول مجدداً</div>`;
        }
    }

    function renderPackages(packages) {
        const grid = document.getElementById('deposit-packages-grid');
        if (!grid) return;

        grid.innerHTML = packages.map(pkg => {
            const tonEst = (pkg.usdt_amount / tonPriceUsd).toFixed(3);
            return `
                <div onclick="window.depositModule?.selectPackage(${pkg.id})" style="background: linear-gradient(145deg, rgba(255,255,255,0.05), rgba(15,23,42,0.6)); border: 1px solid rgba(0, 152, 234, 0.25); border-radius: 14px; padding: 14px 10px; text-align: center; cursor: pointer; transition: all 0.2s ease; position: relative; overflow: hidden;" onmouseover="this.style.borderColor='#0098EA'; this.style.transform='translateY(-2px)';" onmouseout="this.style.borderColor='rgba(0, 152, 234, 0.25)'; this.style.transform='translateY(0)';">
                    <div style="font-size: 22px; margin-bottom: 4px;">💎</div>
                    <div style="font-size: 16px; font-weight: 800; color: #34d399; margin-bottom: 2px;">+$${pkg.usdt_amount} USDT</div>
                    <div style="font-size: 11px; color: #94a3b8; margin-bottom: 10px;">بشراء بعملة TON</div>
                    <div style="background: #0098EA; color: #fff; border-radius: 8px; padding: 6px 4px; font-size: 12px; font-weight: 700;">
                        ~ ${tonEst} TON
                    </div>
                </div>
            `;
        }).join('');
    }

    async function selectPackage(packageId) {
        const pkg = currentPackages.find(p => p.id === packageId);
        if (!pkg) return;

        const tg = window.Telegram?.WebApp;
        const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || '';

        try {
            const res = await fetch('/api/wallet/deposit/create_invoice', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-User-Id': String(userId)
                },
                body: JSON.stringify({ package_id: packageId, ton_price: tonPriceUsd })
            });

            const data = await res.json();
            if (data.success) {
                openModal(data);
            } else {
                alert(data.error || "تعذر إنشاء طلب الشحن");
            }
        } catch (e) {
            console.error("خطأ في إنشاء طلب الإيداع:", e);
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
                if (window.Telegram?.WebApp?.openTelegramLink && payUrl.startsWith('https://t.me/')) {
                    window.Telegram.WebApp.openTelegramLink(payUrl);
                } else {
                    window.open(payUrl, '_blank');
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

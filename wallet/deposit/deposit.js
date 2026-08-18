window.depositModule = (function () {
    let tonPriceUsd = 1.30;
    let currentPackages = [];
    let currentActiveInvoice = null;

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
        const grid = document.getElementById('deposit-packages-grid');
        if (grid) {
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #38bdf8; padding: 30px; font-weight: bold;">⏳ جاري جلب باقات الشحن...</div>`;
        }

        try {
            const res = await fetch(`/api/wallet/deposit/packages?_t=${Date.now()}`, {
                cache: 'no-store',
                headers: { 'Pragma': 'no-cache', 'Cache-Control': 'no-cache' }
            });
            
            const data = await res.json();

            if (res.ok && data.success) {
                currentPackages = data.packages || [];
                renderPackages(currentPackages);
            } else {
                const errText = data.error || "فشل جلب باقات الشحن من الفايربيس";
                if (grid) grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #ef4444; padding: 20px; font-weight: bold; background: rgba(239, 68, 68, 0.1); border-radius: 12px; border: 1px solid rgba(239, 68, 68, 0.3);">⚠️ ${errText}</div>`;
            }
        } catch (err) {
            console.error("❌ تعذر جلب باقات الفايربيس:", err);
            if (grid) grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #ef4444; padding: 20px; font-weight: bold; background: rgba(239, 68, 68, 0.1); border-radius: 12px; border: 1px solid rgba(239, 68, 68, 0.3);">⚠️ حدث خطأ في الاتصال بالخادم</div>`;
        }
    }

    function renderPackages(packages) {
        const grid = document.getElementById('deposit-packages-grid');
        if (!grid) {
            setTimeout(() => renderPackages(packages), 100);
            return;
        }

        if (!packages || packages.length === 0) {
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #94a3b8; padding: 20px; background: rgba(255,255,255,0.03); border-radius: 12px;">لا توجد باقات متاحة حالياً</div>`;
            return;
        }

        grid.innerHTML = packages.map(pkg => {
            const usdtVal = parseFloat(pkg.usdt_amount || 0);
            const tonEst = (usdtVal / tonPriceUsd).toFixed(3);
            const titleName = `باقة $${usdtVal} USDT`;

            return `
                <div onclick="window.depositModule?.selectPackage(${pkg.id})" style="background: linear-gradient(145deg, rgba(255,255,255,0.06), rgba(15,23,42,0.7)); border: 1px solid rgba(0, 152, 234, 0.3); border-radius: 14px; padding: 14px 10px; text-align: center; cursor: pointer; transition: all 0.2s ease; position: relative; overflow: hidden;">
                    <div style="font-size: 22px; margin-bottom: 4px;">💵</div>
                    <div style="font-size: 15px; font-weight: 800; color: #34d399; margin-bottom: 2px;">${titleName}</div>
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
        const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || 0;

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

            if (res.ok && data.success) {
                currentActiveInvoice = data;
                
                // فتح المحفظة بأمان تام لتجنب ERR_UNKNOWN_URL_SCHEME
                openTonTransferLink(data);

                // إظهار نافذة متابعة حالة التحويل
                showPendingModal();
            } else {
                alert(data.error || "تعذر إنشاء طلب الشحن");
            }
        } catch (e) {
            console.error("خطأ في إنشاء طلب الإيداع:", e);
            alert("حدث خطأ في الاتصال، يرجى المحاولة لاحقاً");
        }
    }

    function openTonTransferLink(invoiceData) {
        if (!invoiceData) return;
        const tg = window.Telegram?.WebApp;
        
        const tgUrl = invoiceData.tg_wallet_url || invoiceData.pay_url;
        const webUrl = invoiceData.web_url || invoiceData.tonkeeper_url;

        try {
            if (tg && typeof tg.openTelegramLink === 'function' && tgUrl && tgUrl.startsWith('https://t.me/')) {
                tg.openTelegramLink(tgUrl);
            } else if (tg && typeof tg.openLink === 'function' && webUrl) {
                tg.openLink(webUrl);
            } else if (tg && typeof tg.openLink === 'function' && tgUrl) {
                tg.openLink(tgUrl);
            } else if (webUrl) {
                window.open(webUrl, '_blank');
            } else if (tgUrl) {
                window.open(tgUrl, '_blank');
            }
        } catch (e) {
            console.warn("⚠️ تعذر فتح المحفظة تلقائياً:", e);
            if (webUrl) window.open(webUrl, '_blank');
        }
    }

    function showPendingModal() {
        const modal = document.getElementById('deposit-pay-modal');
        if (modal) modal.style.display = 'flex';
    }

    function reopenWallet() {
        if (currentActiveInvoice) {
            openTonTransferLink(currentActiveInvoice);
        }
    }

    async function verifyPayment() {
        if (!currentActiveInvoice) {
            alert("لا يوجد طلب شحن نشط حالياً.");
            return;
        }

        const tg = window.Telegram?.WebApp;
        const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || 0;

        try {
            const headers = { 'Content-Type': 'application/json' };
            if (userId) headers['X-Telegram-User-Id'] = String(userId);

            const res = await fetch('/api/wallet/deposit/confirm_payment', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    user_id: userId,
                    usdt_amount: currentActiveInvoice.usdt_amount,
                    memo: currentActiveInvoice.memo,
                    invoice_id: currentActiveInvoice.invoice_id
                })
            });

            const data = await res.json();
            if (res.ok && data.success) {
                alert(`✅ تمت عملية الدفع بنجاح وزيادة الرصيد!\nرصيد الدولار الجديد: $${parseFloat(data.new_balance).toFixed(2)} USDT`);
                
                if (window.userState) {
                    window.userState.usd_balance = data.new_balance;
                    window.userState.usdt_balance = data.new_balance;
                }
                
                const usdBalanceElems = document.querySelectorAll('#top-balance-usd, #usd-balance, .usd-balance, #usdt-balance, .usdt-balance');
                usdBalanceElems.forEach(el => {
                    el.innerText = `$${parseFloat(data.new_balance).toFixed(2)}`;
                });

                closeModal();
            } else {
                alert(`⚠️ ${data.error || 'لم يتم تأكيد وصول التحويل بعد، يرجى التأكد من إتمام الدفع في المحفظة.'}`);
            }
        } catch (e) {
            console.error("خطأ أثناء تأكيد الإيداع:", e);
            alert("حدث خطأ أثناء فحص المعاملة، يرجى المحاولة لاحقاً.");
        }
    }

    function closeModal() {
        const modal = document.getElementById('deposit-pay-modal');
        if (modal) modal.style.display = 'none';
        currentActiveInvoice = null;
    }

    function copyToClipboard(text, label) {
        if (!text) return;
        navigator.clipboard.writeText(text).then(() => {
            alert(`✅ تم نسخ ${label} بنجاح!`);
        }).catch(() => {
            alert(`القيم المراد نسخها: ${text}`);
        });
    }

    function init() {
        fetchTonLivePrice();
        loadPackages();
    }

    return {
        init,
        selectPackage,
        reopenWallet,
        verifyPayment,
        closeModal,
        copyToClipboard
    };
})();

window.init_deposit_module = function () {
    if (window.depositModule) {
        window.depositModule.init();
    }
};

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => window.depositModule?.init());
} else {
    window.depositModule?.init();
}

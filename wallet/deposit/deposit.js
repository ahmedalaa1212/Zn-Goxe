window.depositModule = (function () {
    let tonPriceUsd = 1.30;
    let currentPackages = [];
    let tcInstance = null;
    let lastSelectedPackageId = null;

    // 1. تهيئة TON Connect UI
    function initTonConnect() {
        if (tcInstance) return tcInstance;

        try {
            if (window.TON_CONNECT_UI) {
                const manifestUrl = `${window.location.origin}/tonconnect-manifest.json`;
                tcInstance = new TON_CONNECT_UI.TonConnectUI({
                    manifestUrl: manifestUrl,
                    buttonRootId: 'ton-connect-btn-container'
                });
            }
        } catch (e) {
            console.warn("⚠️ خطأ تهيئة مكتبة TON Connect UI:", e);
        }
        return tcInstance;
    }

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
                <div onclick="window.depositModule?.buyPackageWithTon(${pkg.id})" style="background: linear-gradient(145deg, rgba(255,255,255,0.06), rgba(15,23,42,0.7)); border: 1px solid rgba(0, 152, 234, 0.3); border-radius: 14px; padding: 14px 10px; text-align: center; cursor: pointer; transition: all 0.2s ease; position: relative; overflow: hidden;">
                    <div style="font-size: 22px; margin-bottom: 4px;">💵</div>
                    <div style="font-size: 15px; font-weight: 800; color: #34d399; margin-bottom: 2px;">${titleName}</div>
                    <div style="font-size: 11px; color: #94a3b8; margin-bottom: 10px;">دفع تلقائي بعملة TON</div>
                    <div style="background: #0098EA; color: #fff; border-radius: 8px; padding: 6px 4px; font-size: 12px; font-weight: 700;">
                        ~ ${tonEst} TON
                    </div>
                </div>
            `;
        }).join('');
    }

    // التنفيذ الفعلي لدورة الدفع التلقائي المكونة من 4 مراحل
    async function buyPackageWithTon(packageId) {
        lastSelectedPackageId = packageId;
        const pkg = currentPackages.find(p => String(p.id) === String(packageId));
        if (!pkg) {
            alert("الباقة غير متوفرة حالياً");
            return;
        }

        const tc = initTonConnect();
        const tg = window.Telegram?.WebApp;
        const initData = tg?.initData || '';
        const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || 0;

        // المرحلة 1: تهيئة الاتصال والمحفظة
        if (tc && !tc.connected) {
            try {
                await tc.openModal();
            } catch (e) {
                console.warn("إلغاء ربط المحفظة:", e);
                return;
            }
        }

        try {
            showModal("⏳ جاري تجهيز المعاملة وسعر الصرف...");

            // المرحلة 2: تجهيز بيانات المعاملة (Backend Prepare)
            const headers = { 'Content-Type': 'application/json' };
            if (userId) headers['X-Telegram-User-Id'] = String(userId);

            const prepRes = await fetch('/api/wallet/deposit/prepare_ton_pay', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    package_id: pkg.id,
                    initData: initData,
                    user_id: userId
                })
            });

            const prepData = await prepRes.json();
            if (!prepRes.ok || !prepData.success) {
                alert(prepData.error || "تعذر تجهيز طلب الشحن تلقائياً");
                closeModal();
                return;
            }

            // المرحلة 3: توقيع الدفع داخل تلجرام (Transaction Prompt)
            const transaction = {
                validUntil: Math.floor(Date.now() / 1000) + 600, // صلاحية المعاملة 10 دقائق
                messages: [
                    {
                        address: prepData.wallet_address,
                        amount: String(prepData.nano_ton),
                        payload: prepData.payload_memo || prepData.memo
                    }
                ]
            };

            showModal("📲 يرجى تأكيد المعاملة داخل المحفظة...");

            let txResult = null;
            if (tc) {
                txResult = await tc.sendTransaction(transaction);
            } else {
                throw new Error("لم يتم تحميل مكتبة TON Connect UI");
            }

            const boc = txResult?.boc;
            if (!boc) {
                throw new Error("لم يتم استلام كود إثبات المعاملة المشفر (BOC)");
            }

            // المرحلة 4: التحقق والتطبيق الآمن (Verify & Apply)
            showModal("⚡ جاري التحقق من المعاملة وإضافة الرصيد...");

            const verifyRes = await fetch('/api/wallet/deposit/verify_and_apply', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    boc: boc,
                    package_id: pkg.id,
                    memo: prepData.payload_memo || prepData.memo,
                    initData: initData,
                    user_id: userId
                })
            });

            const verifyData = await verifyRes.json();
            if (verifyRes.ok && verifyData.success) {
                alert(`✅ تمت عملية الدفع بنجاح وزيادة الرصيد!\nرصيد الدولار الجديد: $${parseFloat(verifyData.new_balance).toFixed(2)} USDT`);
                
                if (window.userState) {
                    window.userState.usd_balance = verifyData.new_balance;
                    window.userState.usdt_balance = verifyData.new_balance;
                }
                
                const usdBalanceElems = document.querySelectorAll('#top-balance-usd, #usd-balance, .usd-balance, #usdt-balance, .usdt-balance');
                usdBalanceElems.forEach(el => {
                    el.innerText = `$${parseFloat(verifyData.new_balance).toFixed(2)}`;
                });

                closeModal();
            } else {
                alert(`⚠️ ${verifyData.error || 'لم يتم تأكيد الشحن، يرجى المحاولة لاحقاً.'}`);
                closeModal();
            }

        } catch (e) {
            console.error("❌ خطأ عملية الشحن التلقائي:", e);
            if (e.message && e.message.includes('User rejected')) {
                alert("تم إلغاء عملية الدفع.");
            } else {
                alert(`حدث خطأ أثناء تنفيذ الدفع: ${e.message || 'خطأ غير معروف'}`);
            }
            closeModal();
        }
    }

    function showModal(msg) {
        const modal = document.getElementById('deposit-pay-modal');
        const statusEl = document.getElementById('deposit-modal-status');
        if (statusEl && msg) statusEl.innerText = msg;
        if (modal) modal.style.display = 'flex';
    }

    function closeModal() {
        const modal = document.getElementById('deposit-pay-modal');
        if (modal) modal.style.display = 'none';
    }

    function retrySelectedPackage() {
        if (lastSelectedPackageId) {
            buyPackageWithTon(lastSelectedPackageId);
        }
    }

    function init() {
        initTonConnect();
        fetchTonLivePrice();
        loadPackages();
    }

    return {
        init,
        selectPackage: buyPackageWithTon,
        buyPackageWithTon,
        retrySelectedPackage,
        closeModal
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

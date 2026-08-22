window.depositModule = (function () {
    let tonPriceUsd = 1.4500;
    let effectiveTonPrice = 1.3679; // السعر المحسوب للباقات شامل حد الأمان 6%
    let currentPackages = [];
    let tcInstance = null;
    let lastSelectedPackageId = null;
    let scriptLoadingPromise = null;
    let isInitializing = false;
    let priceRefreshTimer = null;

    function textToTonCommentBoc(text) {
        if (!text) return undefined;
        
        if (typeof text === 'string' && (text.startsWith('te6cc') || text.startsWith('b5ee'))) {
            return text;
        }

        try {
            const textBytes = new TextEncoder().encode(String(text));
            const dataBytes = new Uint8Array(4 + textBytes.length);
            dataBytes.set([0, 0, 0, 0], 0);
            dataBytes.set(textBytes, 4);

            const dataLen = dataBytes.length;
            const d1 = 0x00; 
            const d2 = dataLen * 2; 

            const cellBytes = new Uint8Array(2 + dataLen);
            cellBytes[0] = d1;
            cellBytes[1] = d2;
            cellBytes.set(dataBytes, 2);

            const header = new Uint8Array([
                0xb5, 0xee, 0x9c, 0x72,
                0x41,
                0x01,
                0x01,
                0x01,
                0x00,
                cellBytes.length,
                0x00
            ]);

            const bocWithoutCrc = new Uint8Array(header.length + cellBytes.length);
            bocWithoutCrc.set(header, 0);
            bocWithoutCrc.set(cellBytes, header.length);

            let crc = 0xFFFFFFFF;
            for (let i = 0; i < bocWithoutCrc.length; i++) {
                crc ^= bocWithoutCrc[i];
                for (let j = 0; j < 8; j++) {
                    crc = (crc & 1) ? ((crc >>> 1) ^ 0x82F63B78) : (crc >>> 1);
                }
            }
            crc = (crc ^ 0xFFFFFFFF) >>> 0;

            const finalBoc = new Uint8Array(bocWithoutCrc.length + 4);
            finalBoc.set(bocWithoutCrc, 0);
            finalBoc[bocWithoutCrc.length] = crc & 0xFF;
            finalBoc[bocWithoutCrc.length + 1] = (crc >> 8) & 0xFF;
            finalBoc[bocWithoutCrc.length + 2] = (crc >> 16) & 0xFF;
            finalBoc[bocWithoutCrc.length + 3] = (crc >> 24) & 0xFF;

            let binary = '';
            for (let i = 0; i < finalBoc.length; i++) {
                binary += String.fromCharCode(finalBoc[i]);
            }
            return btoa(binary);
        } catch (e) {
            console.error("⚠️ خطأ أثناء ترميز الميمو لـ BOC:", e);
            return undefined;
        }
    }

    function loadTonConnectScript() {
        if (window.TON_CONNECT_UI || window.TonConnectUI) {
            return Promise.resolve();
        }
        if (scriptLoadingPromise) {
            return scriptLoadingPromise;
        }

        scriptLoadingPromise = new Promise((resolve, reject) => {
            const existingScript = document.querySelector('script[src*="tonconnect-ui"]');
            if (existingScript) {
                if (window.TON_CONNECT_UI || window.TonConnectUI) {
                    resolve();
                    return;
                }
                existingScript.addEventListener('load', () => resolve());
                existingScript.addEventListener('error', (err) => reject(err));
                return;
            }

            const script = document.createElement('script');
            script.src = 'https://unpkg.com/@tonconnect/ui@latest/dist/tonconnect-ui.min.js';
            script.async = true;
            script.onload = () => {
                console.log("✅ تم تحميل مكتبة TON Connect UI بنجاح");
                resolve();
            };
            script.onerror = () => {
                scriptLoadingPromise = null;
                reject(new Error("فشل تحميل مكتبة TON Connect من الخادم الخارجي CDN"));
            };
            document.head.appendChild(script);
        });

        return scriptLoadingPromise;
    }

    async function initTonConnect() {
        try {
            await loadTonConnectScript();
            
            const TonConnectClass = window.TON_CONNECT_UI?.TonConnectUI || 
                                    window.TonConnectUI?.TonConnectUI || 
                                    window.TonConnectUI || 
                                    window.TON_CONNECT_UI;

            if (TonConnectClass) {
                const manifestUrl = `${window.location.origin}/tonconnect-manifest.json`;
                const btnContainer = document.getElementById('ton-connect-btn-container');

                if (!tcInstance) {
                    const options = { manifestUrl: manifestUrl };
                    if (btnContainer) {
                        options.buttonRootId = 'ton-connect-btn-container';
                    }
                    tcInstance = new TonConnectClass(options);
                } else if (btnContainer) {
                    tcInstance.uiOptions = { buttonRootId: 'ton-connect-btn-container' };
                }
            }
        } catch (e) {
            console.warn("⚠️ خطأ أثناء تهيئة مكتبة TON Connect UI:", e);
        }

        return tcInstance;
    }

    async function fetchTonLivePrice() {
        try {
            const res = await fetch(`/api/wallet/deposit/packages?_t=${Date.now()}`, {
                cache: 'no-store',
                headers: { 'Pragma': 'no-cache', 'Cache-Control': 'no-cache' }
            });
            if (res.ok) {
                const data = await res.json();
                if (data.success && data.ton_price) {
                    tonPriceUsd = parseFloat(data.ton_price);
                    effectiveTonPrice = parseFloat(data.effective_ton_price || (tonPriceUsd / 1.06));
                    
                    // تحديث السعر اللحظي على الشاشة بـ 4 أرقام عشرية
                    const priceElem = document.getElementById('ton-live-price');
                    if (priceElem) {
                        priceElem.innerText = `$${tonPriceUsd.toFixed(4)}`;
                    }

                    if (data.packages && data.packages.length > 0) {
                        currentPackages = data.packages;
                        renderPackages(currentPackages);
                    }
                }
            }
        } catch (e) {
            console.warn("⚠️ تعذر جلب سعر TON اللحظي من الخادم:", e);
        }
    }

    async function loadPackages() {
        const grid = document.getElementById('deposit-packages-grid');
        if (grid && (!currentPackages || currentPackages.length === 0)) {
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #38bdf8; padding: 30px; font-weight: bold;">⏳ جاري جلب باقات الشحن وسعر العملة...</div>`;
        }

        await fetchTonLivePrice();
    }

    function renderPackages(packages) {
        const grid = document.getElementById('deposit-packages-grid');
        if (!grid) return;

        if (!packages || packages.length === 0) {
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #94a3b8; padding: 20px; background: rgba(255,255,255,0.03); border-radius: 12px;">لا توجد باقات متاحة حالياً</div>`;
            return;
        }

        const effPrice = effectiveTonPrice > 0 ? effectiveTonPrice : (tonPriceUsd / 1.06);

        grid.innerHTML = packages.map(pkg => {
            const usdtVal = parseFloat(pkg.usdt_amount || 0);
            // حساب سعر الباقة بالتون بـ 4 أرقام عشرية مع إدراج حد الأمان 6%
            const tonEst = (usdtVal / effPrice).toFixed(4);
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

    async function buyPackageWithTon(packageId) {
        lastSelectedPackageId = packageId;
        const pkg = currentPackages.find(p => String(p.id) === String(packageId));
        if (!pkg) {
            alert("الباقة غير متوفرة حالياً");
            return;
        }

        showModal("⏳ جاري الاتصال بمكتبة المحفظة...");

        const tc = await initTonConnect();
        const tg = window.Telegram?.WebApp;
        const initData = tg?.initData || '';
        const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || window.userState?.id || localStorage.getItem('tg_id') || 0;

        if (!tc) {
            alert("تعذر الاتصال بمكتبة TON Connect. يرجى التحقق من الاتصال بالإنترنت والمحاولة مجدداً.");
            closeModal();
            return;
        }

        if (!tc.connected) {
            try {
                await tc.openModal();
            } catch (e) {
                console.warn("إلغاء نافذة الربط:", e);
                closeModal();
                return;
            }
        }

        try {
            showModal("⏳ جاري تجهيز بيانات المعاملة...");

            const headers = { 'Content-Type': 'application/json' };
            if (userId) headers['X-Telegram-User-Id'] = String(userId);

            const prepRes = await fetch('/api/wallet/deposit/prepare_ton_pay', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    package_id: pkg.id,
                    ton_price: tonPriceUsd,
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

            const rawMemo = prepData.payload_memo || prepData.memo;
            const validPayloadBoc = textToTonCommentBoc(rawMemo);

            const msg = {
                address: prepData.wallet_address,
                amount: String(prepData.nano_ton)
            };

            if (validPayloadBoc) {
                msg.payload = validPayloadBoc;
            }

            const transaction = {
                validUntil: Math.floor(Date.now() / 1000) + 600,
                messages: [msg]
            };

            showModal("📲 يرجى تأكيد العملية داخل المحفظة...");

            const txResult = await tc.sendTransaction(transaction);
            const boc = txResult?.boc;

            if (!boc) {
                throw new Error("لم يتم استلام كود إثبات المعاملة المشفر (BOC)");
            }

            showModal("⚡ جاري التحقق من التحويل وإضافة الرصيد...");

            const verifyRes = await fetch('/api/wallet/deposit/verify_and_apply', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    boc: boc,
                    package_id: pkg.id,
                    memo: rawMemo,
                    initData: initData,
                    user_id: userId
                })
            });

            const verifyData = await verifyRes.json();
            if (verifyRes.ok && verifyData.success) {
                const updatedBalance = parseFloat(verifyData.new_balance || verifyData.usd_balance || 0).toFixed(2);
                alert(`✅ تمت عملية الدفع بنجاح وزيادة الرصيد!\nرصيد الدولار الجديد: $${updatedBalance} USDT`);
                
                if (window.userState) {
                    window.userState.usd_balance = verifyData.new_balance;
                }
                
                const usdBalanceElems = document.querySelectorAll('#top-balance-usd, #usd-balance, .usd-balance, #user-balance');
                usdBalanceElems.forEach(el => {
                    el.innerText = `$${updatedBalance}`;
                });

                closeModal();
            } else {
                alert(`⚠️ ${verifyData.error || 'لم يتم تأكيد الشحن، يرجى المحاولة لاحقاً.'}`);
                closeModal();
            }

        } catch (e) {
            console.error("❌ خطأ عملية الشحن التلقائي:", e);
            if (e.message && (e.message.includes('User rejected') || e.message.includes('Canceled') || e.message.includes('Reject'))) {
                alert("تم إلغاء عملية الدفع من قبل المستخدم.");
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
        if (isInitializing) return;
        isInitializing = true;

        initTonConnect();
        loadPackages().finally(() => {
            isInitializing = false;
        });

        // مؤقت تحديث السعر اللحظي كل 15 ثانية تلقائياً
        if (priceRefreshTimer) clearInterval(priceRefreshTimer);
        priceRefreshTimer = setInterval(() => {
            fetchTonLivePrice();
        }, 15000);
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

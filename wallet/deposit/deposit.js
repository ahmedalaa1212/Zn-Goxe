window.depositModule = (function () {
    let tonPriceUsd = 1.30;
    let currentPackages = [];
    let tcInstance = null;
    let lastSelectedPackageId = null;
    let scriptLoadingPromise = null;

    // 🛠️ دالة ترميز الميمو إلى صيغة BoC القياسية المقبولة لدى محفظة تلجرام (@Wallet) وجميع المحافظ
    function textToTonCommentBoc(text) {
        if (!text) return undefined;
        
        // إذا كان النص مجهّزاً كـ BoC بالفعل من السيرفر
        if (typeof text === 'string' && (text.startsWith('te6cc') || text.startsWith('b5ee'))) {
            return text;
        }

        try {
            const textBytes = new TextEncoder().encode(String(text));
            
            // 4 أظرف أصفار (OpCode الخاص بالتعليقات النصية) + نص UTF-8
            const dataBytes = new Uint8Array(4 + textBytes.length);
            dataBytes.set([0, 0, 0, 0], 0);
            dataBytes.set(textBytes, 4);

            const dataLen = dataBytes.length;
            
            // وصف الخلية (d1 = 0 عدم وجود المراجع، d2 = مضاعف طول البيانات البايتية)
            const d1 = 0x00; 
            const d2 = dataLen * 2; 

            const cellBytes = new Uint8Array(2 + dataLen);
            cellBytes[0] = d1;
            cellBytes[1] = d2;
            cellBytes.set(dataBytes, 2);

            // الهيكل القياسي لـ TON BoC Header
            const header = new Uint8Array([
                0xb5, 0xee, 0x9c, 0x72, // Magic Prefix
                0x41,                   // Flags (has_crc32=1, size_bytes=1)
                0x01,                   // off_bytes=1
                0x01,                   // cells_num=1
                0x01,                   // roots_num=1
                0x00,                   // absent_num=0
                cellBytes.length,       // total cell length
                0x00                    // root_idx=0
            ]);

            const bocWithoutCrc = new Uint8Array(header.length + cellBytes.length);
            bocWithoutCrc.set(header, 0);
            bocWithoutCrc.set(cellBytes, header.length);

            // حساب CRC32-C لسلامة التوقيع داخل المحفظة
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

    // تحميل مكتبة TON Connect UI ديناميكياً في head الصفحة في حال عدم وجودها
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

    // تهيئة كائن المكتبة بأمان
    async function initTonConnect() {
        if (tcInstance) return tcInstance;

        try {
            await loadTonConnectScript();
            
            const TonConnectClass = window.TON_CONNECT_UI?.TonConnectUI || 
                                    window.TonConnectUI?.TonConnectUI || 
                                    window.TonConnectUI || 
                                    window.TON_CONNECT_UI;

            if (TonConnectClass) {
                const manifestUrl = `${window.location.origin}/tonconnect-manifest.json`;
                const btnContainer = document.getElementById('ton-connect-btn-container');
                
                const options = { manifestUrl: manifestUrl };
                if (btnContainer) {
                    options.buttonRootId = 'ton-connect-btn-container';
                }

                tcInstance = new TonConnectClass(options);
            } else {
                console.warn("⚠️ تعذر تحديد كلاس TonConnectUI في النطاق العام");
            }
        } catch (e) {
            console.warn("⚠️ خطأ أثناء تهيئة مكتبة TON Connect UI:", e);
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
        const userId = tg?.initDataUnsafe?.user?.id || window.userState?.tg_id || 0;

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
            if (e.message && (e.message.includes('User rejected') || e.message.includes('Canceled'))) {
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

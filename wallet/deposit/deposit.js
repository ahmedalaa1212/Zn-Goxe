window.depositModule = (function () {
    let tonPriceUsd = 1.4500;
    let effectiveTonPrice = 1.4077; 
    let currentPackages = [];
    let tcInstance = null;
    let lastSelectedPackageId = null;
    let scriptLoadingPromise = null;
    let isInitializing = false;
    let priceRefreshTimer = null;

    // القاعدة 4: منع الـ Undefined (Robust ID Fetching)
    function getValidUserId() {
        const tg = window.Telegram?.WebApp;
        let userId = tg?.initDataUnsafe?.user?.id || 
                     window.userState?.tg_id || 
                     window.userState?.id || 
                     localStorage.getItem('tg_id');
        return userId ? String(userId) : "0";
    }

    // القاعدة 6: الاعتماد على الكاش المؤقت (Local Fallback) للباقات ريثما يرد السيرفر
    function loadCachedPackages() {
        try {
            const cached = localStorage.getItem('deposit_packages_cache');
            if (cached) {
                currentPackages = JSON.parse(cached);
                renderPackages(currentPackages);
            }
        } catch (e) { console.warn("Cache parsing error", e); }
    }

    function saveCachedPackages(packages) {
        localStorage.setItem('deposit_packages_cache', JSON.stringify(packages));
    }

    function textToTonCommentBoc(text) {
        if (!text) return undefined;
        if (typeof text === 'string' && (text.startsWith('te6cc') || text.startsWith('b5ee'))) return text;
        try {
            const textBytes = new TextEncoder().encode(String(text));
            const dataBytes = new Uint8Array(4 + textBytes.length);
            dataBytes.set([0, 0, 0, 0], 0);
            dataBytes.set(textBytes, 4);
            const dataLen = dataBytes.length;
            const d1 = 0x00; 
            const d2 = dataLen * 2; 
            const cellBytes = new Uint8Array(2 + dataLen);
            cellBytes[0] = d1; cellBytes[1] = d2;
            cellBytes.set(dataBytes, 2);
            const header = new Uint8Array([0xb5, 0xee, 0x9c, 0x72, 0x41, 0x01, 0x01, 0x01, 0x00, cellBytes.length, 0x00]);
            const bocWithoutCrc = new Uint8Array(header.length + cellBytes.length);
            bocWithoutCrc.set(header, 0); bocWithoutCrc.set(cellBytes, header.length);
            let crc = 0xFFFFFFFF;
            for (let i = 0; i < bocWithoutCrc.length; i++) {
                crc ^= bocWithoutCrc[i];
                for (let j = 0; j < 8; j++) crc = (crc & 1) ? ((crc >>> 1) ^ 0x82F63B78) : (crc >>> 1);
            }
            crc = (crc ^ 0xFFFFFFFF) >>> 0;
            const finalBoc = new Uint8Array(bocWithoutCrc.length + 4);
            finalBoc.set(bocWithoutCrc, 0);
            finalBoc[bocWithoutCrc.length] = crc & 0xFF; finalBoc[bocWithoutCrc.length + 1] = (crc >> 8) & 0xFF;
            finalBoc[bocWithoutCrc.length + 2] = (crc >> 16) & 0xFF; finalBoc[bocWithoutCrc.length + 3] = (crc >> 24) & 0xFF;
            let binary = '';
            for (let i = 0; i < finalBoc.length; i++) binary += String.fromCharCode(finalBoc[i]);
            return btoa(binary);
        } catch (e) {
            console.error("⚠️ خطأ أثناء ترميز الميمو:", e);
            return undefined;
        }
    }

    function loadTonConnectScript() {
        if (window.TON_CONNECT_UI || window.TonConnectUI) return Promise.resolve();
        if (scriptLoadingPromise) return scriptLoadingPromise;
        scriptLoadingPromise = new Promise((resolve, reject) => {
            const existingScript = document.querySelector('script[src*="tonconnect-ui"]');
            if (existingScript) {
                existingScript.addEventListener('load', () => resolve());
                existingScript.addEventListener('error', (err) => reject(err));
                return;
            }
            const script = document.createElement('script');
            script.src = 'https://unpkg.com/@tonconnect/ui@latest/dist/tonconnect-ui.min.js';
            script.async = true;
            script.onload = () => resolve();
            script.onerror = () => { scriptLoadingPromise = null; reject(new Error("فشل تحميل TON Connect")); };
            document.head.appendChild(script);
        });
        return scriptLoadingPromise;
    }

    async function initTonConnect() {
        try {
            await loadTonConnectScript();
            const TonConnectClass = window.TON_CONNECT_UI?.TonConnectUI || window.TonConnectUI?.TonConnectUI || window.TonConnectUI || window.TON_CONNECT_UI;
            if (TonConnectClass) {
                const manifestUrl = `${window.location.origin}/tonconnect-manifest.json`;
                const btnContainer = document.getElementById('ton-connect-btn-container');
                if (!tcInstance) {
                    const options = { manifestUrl: manifestUrl };
                    if (btnContainer) options.buttonRootId = 'ton-connect-btn-container';
                    tcInstance = new TonConnectClass(options);
                } else if (btnContainer) {
                    tcInstance.uiOptions = { buttonRootId: 'ton-connect-btn-container' };
                }
            }
        } catch (e) { console.warn("⚠️ خطأ تهيئة TON Connect:", e); }
        return tcInstance;
    }

    async function fetchTonLivePrice(forceUpdate = false) {
        try {
            // إضافة Timestamp لمنع الكاش نهائياً من المتصفح
            const url = `/api/wallet/deposit/packages?_t=${Date.now()}&force=${forceUpdate}`;
            const res = await fetch(url, {
                cache: 'no-store',
                headers: { 'Pragma': 'no-cache', 'Cache-Control': 'no-cache, no-store, must-revalidate' }
            });
            
            if (res.ok) {
                const data = await res.json();
                if (data.success && data.ton_price) {
                    tonPriceUsd = parseFloat(data.ton_price);
                    effectiveTonPrice = parseFloat(data.effective_ton_price || (tonPriceUsd / 1.03));
                    
                    const priceElem = document.getElementById('ton-live-price');
                    if (priceElem) priceElem.innerText = `$${effectiveTonPrice.toFixed(4)}`;

                    if (data.packages && data.packages.length > 0) {
                        currentPackages = data.packages;
                        saveCachedPackages(currentPackages); // حفظ الكاش فوراً
                        renderPackages(currentPackages);
                    }
                }
            }
        } catch (e) {
            console.warn("⚠️ تعذر جلب البيانات، يتم عرض الكاش المحلي:", e);
        }
    }

    async function loadPackages() {
        const grid = document.getElementById('deposit-packages-grid');
        if (grid && (!currentPackages || currentPackages.length === 0)) {
            loadCachedPackages(); // استدعاء الكاش (0ms)
            if(currentPackages.length === 0) {
                grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #38bdf8; padding: 30px;">⏳ جاري جلب باقات الشحن...</div>`;
            }
        }
        await fetchTonLivePrice(true);
    }

    function renderPackages(packages) {
        const grid = document.getElementById('deposit-packages-grid');
        if (!grid) return;

        if (!packages || packages.length === 0) {
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #94a3b8; padding: 20px; background: rgba(255,255,255,0.03); border-radius: 12px;">لا توجد باقات متاحة حالياً</div>`;
            return;
        }

        const effPrice = effectiveTonPrice > 0 ? effectiveTonPrice : (tonPriceUsd / 1.03);

        grid.innerHTML = packages.map(pkg => {
            const usdtVal = parseFloat(pkg.usdt_amount || 0);
            const tonEst = (usdtVal / effPrice).toFixed(4);
            const titleName = pkg.name_ar || `باقة $${usdtVal} USDT`;

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
        if (!pkg) { alert("الباقة غير متوفرة حالياً"); return; }

        showModal("⏳ جاري الاتصال بمكتبة المحفظة...");
        const tc = await initTonConnect();
        const tg = window.Telegram?.WebApp;
        const initData = tg?.initData || '';
        const userId = getValidUserId(); // استخدام المعرف الصارم

        if (!tc) { alert("تعذر الاتصال بمكتبة المحفظة."); closeModal(); return; }
        if (!tc.connected) { try { await tc.openModal(); } catch (e) { closeModal(); return; } }

        try {
            showModal("⏳ جاري تجهيز بيانات المعاملة...");
            const headers = { 'Content-Type': 'application/json', 'X-Telegram-User-Id': userId };
            
            const prepRes = await fetch('/api/wallet/deposit/prepare_ton_pay', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({ package_id: pkg.id, usdt_amount: pkg.usdt_amount, ton_price: tonPriceUsd, initData: initData, user_id: userId })
            });

            const prepData = await prepRes.json();
            if (!prepRes.ok || !prepData.success) { throw new Error(prepData.error || "تعذر تجهيز الطلب"); }

            const rawMemo = prepData.payload_memo || prepData.memo;
            const validPayloadBoc = textToTonCommentBoc(rawMemo);
            const msg = { address: prepData.wallet_address, amount: String(prepData.nano_ton) };
            if (validPayloadBoc) msg.payload = validPayloadBoc;

            const transaction = { validUntil: Math.floor(Date.now() / 1000) + 600, messages: [msg] };
            showModal("📲 يرجى تأكيد العملية داخل المحفظة...");
            
            const txResult = await tc.sendTransaction(transaction);
            const boc = txResult?.boc;
            if (!boc) throw new Error("لم يتم استلام كود BOC");

            showModal("⚡ جاري التحقق من التحويل وإضافة الرصيد...");
            const verifyRes = await fetch('/api/wallet/deposit/verify_and_apply', {
                method: 'POST', headers: headers,
                body: JSON.stringify({ boc: boc, package_id: pkg.id, memo: rawMemo, initData: initData, user_id: userId })
            });

            const verifyData = await verifyRes.json();
            if (verifyRes.ok && verifyData.success) {
                const updatedBalance = parseFloat(verifyData.new_balance || verifyData.usd_balance || 0).toFixed(2);
                alert(`✅ تمت عملية الدفع بنجاح!\nرصيد الدولار الجديد: $${updatedBalance} USDT`);
                
                // القاعدة 2: البث اللحظي (Event Dispatching)
                if (!window.userState) window.userState = {};
                window.userState.usd_balance = updatedBalance;
                window.dispatchEvent(new CustomEvent('userStateUpdated', { detail: window.userState }));
                
                closeModal();
            } else { throw new Error(verifyData.error || 'فشل تأكيد الشحن.'); }

        } catch (e) {
            console.error("❌ خطأ الشحن:", e);
            alert(e.message.includes('User rejected') ? "تم إلغاء عملية الدفع." : `خطأ: ${e.message}`);
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

    function init() {
        if (isInitializing) return;
        isInitializing = true;

        initTonConnect();
        loadPackages().finally(() => { isInitializing = false; });

        // القاعدة 1 والقاعدة 3: الاستماع للأحداث وتحديث الـ DOM القسري
        window.addEventListener('userStateUpdated', (e) => {
            const state = e.detail || window.userState;
            if (state && state.usd_balance !== undefined) {
                const val = `$${parseFloat(state.usd_balance).toFixed(2)}`;
                document.querySelectorAll('#top-balance-usd, #usd-balance, .usd-balance, #user-balance').forEach(el => el.innerText = val);
            }
        });

        // القاعدة 5: التحديث عند العودة للتطبيق (Visibility Change)
        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible') {
                fetchTonLivePrice(true); // جلب البيانات فوراً عند فتح التطبيق
            }
        });

        // التحديث التلقائي اللحظي
        if (priceRefreshTimer) clearInterval(priceRefreshTimer);
        priceRefreshTimer = setInterval(() => fetchTonLivePrice(false), 15000);
    }

    return { init, selectPackage: buyPackageWithTon, buyPackageWithTon, retrySelectedPackage: () => lastSelectedPackageId && buyPackageWithTon(lastSelectedPackageId), closeModal };
})();

window.init_deposit_module = function () { if (window.depositModule) window.depositModule.init(); };
if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => window.depositModule?.init());
else window.depositModule?.init();

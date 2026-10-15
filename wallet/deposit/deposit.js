window.depositModule = (function () {
    let tonPriceUsd = 1.4500;
    let effectiveTonPrice = 1.4077;
    let currentPackages = [];
    let tcInstance = null;
    let statusUnsubscribe = null;
    let lastSelectedPackageId = null;
    let scriptLoadingPromise = null;
    let isInitializing = false;
    let priceRefreshTimer = null;
    let listenersBound = false;

    try {
        localStorage.removeItem('deposit_packages_cache');
    } catch (e) {}

    // استخراج شامل لمعرف المستخدم
    function getValidUserId() {
        const tg = window.Telegram?.WebApp;
        const urlParams = new URLSearchParams(window.location.search);
        const uid = tg?.initDataUnsafe?.user?.id ||
                    window.userState?.tg_id ||
                    window.userState?.user_id ||
                    window.userState?.id ||
                    urlParams.get('user_id') ||
                    urlParams.get('tg_id') ||
                    urlParams.get('uid') ||
                    localStorage.getItem('tg_user_id') ||
                    localStorage.getItem('tg_id') ||
                    localStorage.getItem('user_id') ||
                    sessionStorage.getItem('user_id');
        if (uid && String(uid) !== 'undefined' && String(uid) !== 'null') {
            return String(uid).trim();
        }
        return "0";
    }

    // تحديث عناصر الأرصدة في الواجهة فوراً
    function forceUpdateBalanceDOM(usdVal, znVal, znxVal) {
        if (usdVal !== undefined && usdVal !== null && !isNaN(parseFloat(usdVal))) {
            const formattedUsd = parseFloat(usdVal).toFixed(4);
            const formattedUsdShort = parseFloat(usdVal).toFixed(2);
            document.querySelectorAll('#top-balance-usd, #usd-balance, .usd-balance, #user-balance, #wallet-usd-balance, .usdt-balance-display').forEach(el => {
                el.innerText = el.id === 'top-balance-usd' ? `$${formattedUsdShort}` : `${formattedUsd} $`;
            });
            try { localStorage.setItem('cached_usd_balance', String(usdVal)); } catch (e) {}
        }
        if (znVal !== undefined && znVal !== null && !isNaN(parseFloat(znVal))) {
            document.querySelectorAll('#top-balance, .zn-balance-display, #header-zn-balance').forEach(el => {
                el.innerText = parseFloat(znVal).toLocaleString();
            });
        }
        if (znxVal !== undefined && znxVal !== null && !isNaN(parseFloat(znxVal))) {
            document.querySelectorAll('#znx-balance, .znx-balance-display').forEach(el => {
                el.innerText = `ZNX ${parseFloat(znxVal).toFixed(4)}`;
            });
        }
    }

    // تحديث قائمة السجلات تلقائياً بعد أي عملية إيداع
    function triggerHistoryRefresh() {
        try {
            if (window.historyModule) {
                if (typeof window.historyModule.refresh === 'function') {
                    window.historyModule.refresh();
                } else if (typeof window.historyModule.init === 'function') {
                    window.historyModule.init();
                }
            }
        } catch (e) {
            console.warn("⚠️ تعذر تحديث السجلات تلقائياً:", e);
        }
    }

    function formatShortAddress(address) {
        if (!address || typeof address !== 'string') return '';
        if (address.length <= 14) return address;
        return `${address.slice(0, 6)}...${address.slice(-6)}`;
    }

    function updateWalletUI(wallet) {
        const connectView = document.getElementById('deposit-connect-view');
        const contentView = document.getElementById('deposit-content-view');
        const walletNameEl = document.getElementById('connected-wallet-name');
        const walletAddrEl = document.getElementById('connected-wallet-address');

        const isConnected = Boolean(wallet && wallet.account && wallet.account.address);

        if (isConnected) {
            if (connectView) connectView.style.display = 'none';
            if (contentView) contentView.style.display = 'block';

            const appName = wallet.device?.appName || wallet.name || 'محفظة TON';
            const rawAddress = wallet.account.address;

            if (walletNameEl) walletNameEl.innerText = appName;
            if (walletAddrEl) walletAddrEl.innerText = formatShortAddress(rawAddress);

            loadPackages();
        } else {
            if (contentView) contentView.style.display = 'none';
            if (connectView) connectView.style.display = 'block';
            if (walletNameEl) walletNameEl.innerText = '';
            if (walletAddrEl) walletAddrEl.innerText = '';
        }
    }

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
                0x41, 0x01, 0x01, 0x01, 0x00,
                cellBytes.length, 0x00
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
            script.onload = () => resolve();
            script.onerror = () => {
                scriptLoadingPromise = null;
                reject(new Error("فشل تحميل مكتبة TON Connect من CDN"));
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

                if (!tcInstance) {
                    tcInstance = new TonConnectClass({
                        manifestUrl: manifestUrl
                    });
                }

                if (!statusUnsubscribe && typeof tcInstance.onStatusChange === 'function') {
                    statusUnsubscribe = tcInstance.onStatusChange((wallet) => {
                        updateWalletUI(wallet);
                    });
                }

                if (tcInstance.connectionRestored) {
                    await tcInstance.connectionRestored;
                }

                updateWalletUI(tcInstance.wallet || (tcInstance.connected ? { account: tcInstance.account, device: tcInstance.wallet?.device } : null));
            }
        } catch (e) {
            console.warn("⚠️ خطأ أثناء تهيئة TON Connect UI:", e);
            updateWalletUI(null);
        }
        return tcInstance;
    }

    async function openConnectModal() {
        const tc = await initTonConnect();
        if (!tc) {
            alert("تعذر تحميل مكتبة ربط المحافظ. يرجى التحقق من اتصال الإنترنت والمحاولة مرة أخرى.");
            return;
        }

        try {
            if (tc.connected) {
                updateWalletUI(tc.wallet);
                return;
            }
            await tc.openModal();
        } catch (e) {
            console.warn("⚠️ تعذر فتح نافذة اختيار المحفظة:", e);
        }
    }

    async function disconnectWallet() {
        try {
            const tc = await initTonConnect();
            if (tc && tc.connected) {
                await tc.disconnect();
            }
        } catch (e) {
            console.warn("⚠️ خطأ أثناء قطع اتصال المحفظة:", e);
        }

        try {
            Object.keys(localStorage).forEach((key) => {
                if (key.startsWith('ton-connect-storage') || key.startsWith('ton-connect-ui')) {
                    localStorage.removeItem(key);
                }
            });
        } catch (e) {}

        closeModal();
        updateWalletUI(null);
    }

    async function fetchTonLivePrice() {
        try {
            const res = await fetch(`/api/wallet/deposit/packages?_t=${Date.now()}`, {
                method: 'GET',
                cache: 'no-store',
                headers: {
                    'Accept': 'application/json',
                    'Pragma': 'no-cache',
                    'Cache-Control': 'no-cache, no-store, must-revalidate'
                }
            });

            if (res.ok) {
                const data = await res.json();
                if (data && data.success) {
                    if (data.ton_price) {
                        tonPriceUsd = parseFloat(data.ton_price);
                        effectiveTonPrice = parseFloat(data.effective_ton_price || (tonPriceUsd / 1.03));
                        const priceElem = document.getElementById('ton-live-price');
                        if (priceElem) {
                            priceElem.innerText = `$${effectiveTonPrice.toFixed(4)}`;
                        }
                    }

                    if (Array.isArray(data.packages) && data.packages.length > 0) {
                        currentPackages = data.packages;
                        renderPackages(currentPackages);
                    }
                }
            }
        } catch (e) {
            console.warn("⚠️ تعذر جلب باقات الشحن وسعر TON من الخادم:", e);
        }
    }

    async function loadPackages() {
        const grid = document.getElementById('deposit-packages-grid');
        if (grid && (!currentPackages || currentPackages.length === 0)) {
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #38bdf8; padding: 30px; font-weight: bold;">⏳ جاري جلب باقات الشحن وسعر العملة من Supabase...</div>`;
        } else if (grid && currentPackages.length > 0) {
            renderPackages(currentPackages);
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

        const effPrice = effectiveTonPrice > 0 ? effectiveTonPrice : (tonPriceUsd / 1.03);

        grid.innerHTML = packages.map(pkg => {
            const usdtVal = parseFloat(pkg.usdt_amount || 0);
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

    async function cancelPendingInvoiceOnServer(memo, status = 'cancelled', reason = null, deleteIfCancelled = true) {
        if (!memo) return;
        try {
            await fetch('/api/wallet/deposit/cancel_invoice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    memo: memo,
                    status: status,
                    reason: reason,
                    delete_if_cancelled: deleteIfCancelled
                })
            });
        } catch (err) {
            console.warn("⚠️ تعذر تحديث حالة الفاتورة الملغاة:", err);
        }
    }

    async function buyPackageWithTon(packageId) {
        lastSelectedPackageId = packageId;

        const tc = await initTonConnect();
        if (!tc || !tc.connected) {
            updateWalletUI(null);
            await openConnectModal();
            return;
        }

        const pkg = currentPackages.find(p => String(p.id) === String(packageId));
        if (!pkg) {
            alert("الباقة غير متوفرة حالياً");
            return;
        }

        const tg = window.Telegram?.WebApp;
        const initData = tg?.initData || '';
        const userId = getValidUserId();
        const senderWallet = tc.wallet?.account?.address || tc.account?.address || '';
        let createdMemo = null;

        try {
            showModal("⏳ جاري تجهيز بيانات المعاملة...");

            const headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            };
            if (userId && userId !== "0") {
                headers['X-Telegram-User-Id'] = String(userId);
            }

            const prepRes = await fetch('/api/wallet/deposit/prepare_ton_pay', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    package_id: pkg.id,
                    usdt_amount: pkg.usdt_amount,
                    ton_price: tonPriceUsd,
                    sender_wallet: senderWallet,
                    initData: initData,
                    user_id: userId
                })
            });

            const prepText = await prepRes.text();
            let prepData = {};
            try {
                prepData = JSON.parse(prepText);
            } catch (jsonErr) {
                throw new Error("استجابة غير صالحة من الخادم أثناء تجهيز الفاتورة");
            }

            if (!prepRes.ok || !prepData.success) {
                alert(prepData.error || "تعذر تجهيز طلب الشحن تلقائياً");
                closeModal();
                return;
            }

            const destinationWallet = String(prepData.wallet_address || '').trim();
            if (!destinationWallet) {
                alert("⚠️ لم يتم ضبط عنوان محفظة الاستلام (TON_WALLET_ADDRESS) في إعدادات Railway!");
                closeModal();
                return;
            }

            const rawMemo = prepData.payload_memo || prepData.memo;
            createdMemo = rawMemo;
            const validPayloadBoc = textToTonCommentBoc(rawMemo);

            const msg = {
                address: destinationWallet,
                amount: String(prepData.nano_ton)
            };

            if (validPayloadBoc) {
                msg.payload = validPayloadBoc;
            }

            const transaction = {
                validUntil: Math.floor(Date.now() / 1000) + 600,
                messages: [msg]
            };

            showModal("📲 يرجى تأكيد العملية داخل المحفظة المربوطة...");

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
                    usdt_amount: pkg.usdt_amount,
                    ton_amount: prepData.ton_amount,
                    sender_wallet: senderWallet,
                    memo: rawMemo,
                    initData: initData,
                    user_id: userId
                })
            });

            const verifyText = await verifyRes.text();
            let verifyData = {};
            try {
                verifyData = JSON.parse(verifyText);
            } catch (jsonErr) {
                throw new Error("استجابة غير صالحة من الخادم أثناء تأكيد الشحن");
            }

            if (verifyRes.ok && verifyData.success) {
                const newBal = parseFloat(verifyData.new_balance ?? verifyData.usd_balance ?? 0);
                alert(`✅ تمت عملية الدفع بنجاح وزيادة الرصيد!\nرصيد الدولار الجديد: $${newBal.toFixed(2)} USDT`);

                if (!window.userState) window.userState = {};
                window.userState.usd_balance = newBal;
                window.userState.usdt_balance = newBal;

                forceUpdateBalanceDOM(newBal);
                window.dispatchEvent(new CustomEvent('userStateUpdated', { detail: window.userState }));

                // تحديث قائمة السجلات فوراً لتظهر المعاملة الجديدة
                triggerHistoryRefresh();
                closeModal();
            } else {
                alert(`⚠️ ${verifyData.error || 'لم يتم تأكيد الشحن، يرجى المحاولة لاحقاً.'}`);
                triggerHistoryRefresh();
                closeModal();
            }

        } catch (e) {
            console.error("❌ خطأ عملية الشحن التلقائي:", e);
            const isUserCancel = e.message && (
                e.message.includes('User rejected') ||
                e.message.includes('Canceled') ||
                e.message.includes('Reject') ||
                e.message.includes('Interrupted')
            );

            if (isUserCancel) {
                // إذا ألغى المستخدم الدفع من المحفظة نحذف الفاتورة المبدئية حتى لا تعلق في السجلات
                await cancelPendingInvoiceOnServer(createdMemo, 'cancelled', 'تم إلغاء العملية من قبل المستخدم', true);
                alert("تم إلغاء عملية الدفع من قبل المستخدم.");
            } else {
                await cancelPendingInvoiceOnServer(createdMemo, 'failed', e.message || 'خطأ أثناء تنفيذ الدفع', false);
                alert(`حدث خطأ أثناء تنفيذ الدفع: ${e.message || 'خطأ غير معروف'}`);
            }
            triggerHistoryRefresh();
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

    function bindEventsOnce() {
        if (listenersBound) return;
        listenersBound = true;

        window.addEventListener('userStateUpdated', (e) => {
            const state = e.detail || window.userState;
            if (state) {
                const usd = state.usd_balance ?? state.usdt_balance;
                const zn = state.balance ?? state.zn_balance;
                const znx = state.znx_balance;
                forceUpdateBalanceDOM(usd, zn, znx);
            }
        });

        document.addEventListener('visibilitychange', () => {
            if (document.visibilityState === 'visible' && tcInstance?.connected) {
                fetchTonLivePrice();
            }
        });
    }

    function init() {
        bindEventsOnce();

        try {
            const cachedUsd = localStorage.getItem('cached_usd_balance');
            if (cachedUsd !== null && !window.userState?.usd_balance) {
                forceUpdateBalanceDOM(parseFloat(cachedUsd));
            }
        } catch (e) {}

        updateWalletUI(tcInstance?.wallet || null);

        if (isInitializing) return;
        isInitializing = true;

        initTonConnect().finally(() => {
            isInitializing = false;
        });

        if (priceRefreshTimer) clearInterval(priceRefreshTimer);
        priceRefreshTimer = setInterval(() => {
            if (tcInstance && tcInstance.connected) {
                fetchTonLivePrice();
            }
        }, 5000);
    }

    return {
        init,
        openConnectModal,
        disconnectWallet,
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

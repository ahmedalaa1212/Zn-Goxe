window.depositModule = (function () {
    let tonPriceUsd = 1.4500;
    let effectiveTonPrice = 1.4077;
    let currentPackages = [];
    let tcInstance = null;
    let statusUnsubscribe = null;
    let selectedPackageObj = null;
    let scriptLoadingPromise = null;
    let priceRefreshTimer = null;
    let listenersBound = false;

    // متغيرات التحكم في عداد الـ 15 ثانية وحالة الطلب النشط
    let countdownTimer = null;
    let countdownSeconds = 15;
    let activeOrderMemo = null;
    let isOrderCancelledByUser = false;
    let isPaymentVerifying = false;

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

    // تحديث قائمة السجلات تلقائياً بهدوء بعد اكتمال العملية
    function triggerHistoryRefresh() {
        setTimeout(() => {
            try {
                if (window.historyModule) {
                    if (typeof window.historyModule.refresh === 'function') {
                        window.historyModule.refresh(true);
                    } else if (typeof window.historyModule.init === 'function') {
                        window.historyModule.init();
                    }
                }
            } catch (e) {
                console.warn("⚠️ تعذر تحديث السجلات تلقائياً:", e);
            }
        }, 350);
    }

    function formatShortAddress(address) {
        if (!address || typeof address !== 'string') return '';
        if (address.length <= 14) return address;
        return `${address.slice(0, 6)}...${address.slice(-6)}`;
    }

    // دالة تحديث واجهة المحفظة: تظهر الباقات فورا إذا كان متصلا
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

                // انتظار استعادة الاتصال المخزن في المتصفح بقوة
                if (tcInstance.connectionRestored) {
                    await tcInstance.connectionRestored;
                }

                const currentWallet = tcInstance.wallet || (tcInstance.connected ? { account: tcInstance.account, device: tcInstance.wallet?.device } : null);
                updateWalletUI(currentWallet);
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
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align: center; color: #38bdf8; padding: 30px; font-weight: bold;">⏳ جاري تحميل باقات الشحن والأسعار...</div>`;
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

    // إيقاف العداد التنازلي
    function stopCountdownTimer() {
        if (countdownTimer) {
            clearInterval(countdownTimer);
            countdownTimer = null;
        }
    }

    // تشغيل العداد التنازلي من 15 ثانية إلى 0 ثم إظهار زر إلغاء الطلب
    function start15SecCountdown() {
        stopCountdownTimer();
        countdownSeconds = 15;

        const countdownBox = document.getElementById('deposit-countdown-box');
        const numEl = document.getElementById('deposit-countdown-num');
        const textEl = document.getElementById('deposit-countdown-text');
        const cancelWrap = document.getElementById('deposit-cancel-btn-wrap');

        if (countdownBox) countdownBox.style.display = 'block';
        if (cancelWrap) cancelWrap.style.display = 'none';
        if (numEl) numEl.innerText = '15';
        if (textEl) textEl.innerText = '15';

        countdownTimer = setInterval(() => {
            if (isPaymentVerifying) {
                stopCountdownTimer();
                if (countdownBox) countdownBox.style.display = 'none';
                if (cancelWrap) cancelWrap.style.display = 'none';
                return;
            }

            countdownSeconds -= 1;
            if (countdownSeconds > 0) {
                if (numEl) numEl.innerText = String(countdownSeconds);
                if (textEl) textEl.innerText = String(countdownSeconds);
            } else {
                stopCountdownTimer();
                if (countdownBox) countdownBox.style.display = 'none';
                if (cancelWrap && !isPaymentVerifying) {
                    cancelWrap.style.display = 'block';
                }
            }
        }, 1000);
    }

    // التبديل بين مراحل النافذة الثلاث (confirm | waiting | success)
    function switchModalStep(stepName) {
        const modal = document.getElementById('deposit-pay-modal');
        const stepConfirm = document.getElementById('deposit-step-confirm');
        const stepWaiting = document.getElementById('deposit-step-waiting');
        const stepSuccess = document.getElementById('deposit-step-success');

        if (stepConfirm) stepConfirm.style.display = stepName === 'confirm' ? 'block' : 'none';
        if (stepWaiting) stepWaiting.style.display = stepName === 'waiting' ? 'block' : 'none';
        if (stepSuccess) stepSuccess.style.display = stepName === 'success' ? 'block' : 'none';
        if (modal) modal.style.display = 'flex';
    }

    // الخطوة 1: نافذة الموافقة أولاً
    async function promptPackageConfirmation(packageId) {
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

        selectedPackageObj = pkg;
        const effPrice = effectiveTonPrice > 0 ? effectiveTonPrice : (tonPriceUsd / 1.03);
        const usdtVal = parseFloat(pkg.usdt_amount || 0);
        const tonEst = (usdtVal / effPrice).toFixed(4);

        const usdtEl = document.getElementById('confirm-pkg-usdt');
        const tonEl = document.getElementById('confirm-pkg-ton');

        if (usdtEl) usdtEl.innerText = `باقة $${usdtVal} USDT`;
        if (tonEl) tonEl.innerText = `المبلغ المطلوب: ~ ${tonEst} TON`;

        switchModalStep('confirm');
    }

    // الخطوة 2: عند ضغط المستخدم على "نعم، موافق" يبدأ الطلب ويظهر عداد 15 ثانية
    async function confirmAndStartPayment() {
        if (!selectedPackageObj) {
            closeModal();
            return;
        }

        const pkg = selectedPackageObj;
        const tc = await initTonConnect();
        if (!tc || !tc.connected) {
            closeModal();
            updateWalletUI(null);
            await openConnectModal();
            return;
        }

        isOrderCancelledByUser = false;
        isPaymentVerifying = false;
        activeOrderMemo = null;

        const waitingTitle = document.getElementById('deposit-waiting-title');
        const statusEl = document.getElementById('deposit-modal-status');
        if (waitingTitle) waitingTitle.innerText = 'منتظر الدفع...';
        if (statusEl) statusEl.innerText = 'جاري تجهيز المعاملة وتحويلك إلى المحفظة...';

        switchModalStep('waiting');
        start15SecCountdown();

        const tg = window.Telegram?.WebApp;
        const initData = tg?.initData || '';
        const userId = getValidUserId();
        const senderWallet = tc.wallet?.account?.address || tc.account?.address || '';

        try {
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

            if (isOrderCancelledByUser) return;

            const prepText = await prepRes.text();
            let prepData = {};
            try {
                prepData = JSON.parse(prepText);
            } catch (jsonErr) {
                throw new Error("استجابة غير صالحة من الخادم أثناء تجهيز الفاتورة");
            }

            if (!prepRes.ok || !prepData.success) {
                stopCountdownTimer();
                closeModal();
                alert(prepData.error || "تعذر تجهيز طلب الشحن تلقائياً");
                return;
            }

            const destinationWallet = String(prepData.wallet_address || '').trim();
            if (!destinationWallet) {
                stopCountdownTimer();
                closeModal();
                alert("⚠️ لم يتم ضبط عنوان محفظة الاستلام (TON_WALLET_ADDRESS) في إعدادات Railway!");
                return;
            }

            const rawMemo = prepData.payload_memo || prepData.memo;
            activeOrderMemo = rawMemo;
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

            if (statusEl) {
                statusEl.innerText = 'منتظر الدفع داخل المحفظة المربوطة...';
            }

            const txResult = await tc.sendTransaction(transaction);
            const boc = txResult?.boc;

            if (!boc) {
                throw new Error("لم يتم استلام كود إثبات المعاملة المشفر (BOC)");
            }

            isPaymentVerifying = true;
            stopCountdownTimer();
            const countdownBox = document.getElementById('deposit-countdown-box');
            const cancelWrap = document.getElementById('deposit-cancel-btn-wrap');
            if (countdownBox) countdownBox.style.display = 'none';
            if (cancelWrap) cancelWrap.style.display = 'none';

            if (waitingTitle) waitingTitle.innerText = '⚡ جاري تأكيد الإيداع...';
            if (statusEl) statusEl.innerText = 'تم الدفع! جاري التحقق من التحويل وإضافة الرصيد لحسابك...';

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
                const depositedAmount = parseFloat(pkg.usdt_amount || 0);
                const newBal = parseFloat(verifyData.new_balance ?? verifyData.usd_balance ?? 0);

                if (!window.userState) window.userState = {};
                window.userState.usd_balance = newBal;
                window.userState.usdt_balance = newBal;

                forceUpdateBalanceDOM(newBal);
                window.dispatchEvent(new CustomEvent('userStateUpdated', { detail: window.userState }));

                const depAmtEl = document.getElementById('success-deposited-amount');
                const newBalEl = document.getElementById('success-new-balance');
                if (depAmtEl) depAmtEl.innerText = `+$${depositedAmount} USDT`;
                if (newBalEl) newBalEl.innerText = `$${newBal.toFixed(4)} USDT`;

                switchModalStep('success');
                triggerHistoryRefresh();
            } else {
                closeModal();
                alert(`⚠️ ${verifyData.error || 'لم يتم تأكيد الشحن، يرجى المحاولة لاحقاً.'}`);
                triggerHistoryRefresh();
            }

        } catch (e) {
            if (isOrderCancelledByUser) {
                return;
            }
            console.error("❌ خطأ عملية الشحن:", e);
            stopCountdownTimer();
            closeModal();

            const isUserCancel = e.message && (
                e.message.includes('User rejected') ||
                e.message.includes('Canceled') ||
                e.message.includes('Reject') ||
                e.message.includes('Interrupted')
            );

            if (isUserCancel) {
                await cancelPendingInvoiceOnServer(activeOrderMemo, 'cancelled', 'تم إلغاء العملية من قبل المستخدم', true);
                alert("تم إلغاء عملية الدفع من قبل المستخدم.");
            } else {
                await cancelPendingInvoiceOnServer(activeOrderMemo, 'failed', e.message || 'خطأ أثناء تنفيذ الدفع', false);
                alert(`حدث خطأ أثناء تنفيذ الدفع: ${e.message || 'خطأ غير معروف'}`);
            }
            triggerHistoryRefresh();
        }
    }

    // إلغاء الطلب يدوياً بعد انتهاء الـ 15 ثانية
    async function cancelActiveOrder() {
        if (isPaymentVerifying) {
            return;
        }
        isOrderCancelledByUser = true;
        stopCountdownTimer();
        const memoToCancel = activeOrderMemo;
        activeOrderMemo = null;
        closeModal();

        if (memoToCancel) {
            await cancelPendingInvoiceOnServer(memoToCancel, 'cancelled', 'تم إلغاء الطلب من قبل المستخدم', true);
            triggerHistoryRefresh();
        }
    }

    function closeModal() {
        stopCountdownTimer();
        const modal = document.getElementById('deposit-pay-modal');
        if (modal) modal.style.display = 'none';
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

        // المستمع هذا يقوم بتحديث الواجهة بشكل فوري عند تغير حالة المحفظة من الخارج (مثال: فصل الربط من المحفظة)
        window.addEventListener('ton-connect-ui-wallet-change', (e) => {
            const wallet = e.detail || (tcInstance ? tcInstance.wallet : null);
            updateWalletUI(wallet);
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

        // إذا كانت الدالة تُستدعى من تنقل القوائم بدون تحديث الصفحة، نفحص حالة المحفظة الموجودة مسبقاً بقوة 
        // لضمان عرض الباقات فوراً وعدم إظهار واجهة الربط المبدئية الخاطئة.
        if (tcInstance) {
            const currentWallet = tcInstance.wallet || (tcInstance.connected ? { account: tcInstance.account, device: tcInstance.wallet?.device } : null);
            updateWalletUI(currentWallet);
        } else {
            updateWalletUI(null);
        }

        initTonConnect();

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
        selectPackage: promptPackageConfirmation,
        buyPackageWithTon: promptPackageConfirmation,
        confirmAndStartPayment,
        cancelActiveOrder,
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

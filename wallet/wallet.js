// ==========================================
// 💳 ZN Goxe - Wallet Module (wallet.js)
// ==========================================

// 1. الحالة العامة للمستند والمحفظة (State Management)
let playerData = {
    znBalance: 0,
    usdBalance: 0.00000,
    tgId: null 
};

let isWalletConnected = false;
let userWalletAddress = null;
let currentTonPriceUSD = 5.00; // سعر افتراضي لحين جلب السعر المباشر
let currentWalletTab = localStorage.getItem('lastWalletTab') || 'withdraw';
let tonConnectUI = null;

// ==========================================
// 🛠️ أدوات مساعدة وتفاعل التلجرام (Telegram WebApp Helpers)
// ==========================================
const tgApp = window.Telegram?.WebApp;
if (tgApp) {
    tgApp.ready(); // التأكد من تهيئة التلجرام
}

function showAppAlert(message) {
    if (tgApp && typeof tgApp.showAlert === 'function') {
        tgApp.showAlert(message);
    } else {
        alert(message);
    }
}

function triggerHapticFeedback(type = 'impact', style = 'medium') {
    if (tgApp && tgApp.HapticFeedback) {
        if (type === 'impact') {
            tgApp.HapticFeedback.impactOccurred(style);
        } else if (type === 'notification') {
            tgApp.HapticFeedback.notificationOccurred(style);
        }
    }
}

// ==========================================
// 🌐 0. جلب سعر عملة TON الفعلي واللحظي من السوق
// ==========================================
async function fetchLiveTonPrice() {
    try {
        const response = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT');
        if (!response.ok) throw new Error("فشل الاستجابة من Binance");
        const data = await response.json();
        
        if (data && data.price) {
            currentTonPriceUSD = parseFloat(data.price);
        }
    } catch (error) {
        console.warn("⚠️ لم نتمكن من جلب السعر من Binance، يتم المحاولة من مصدر احتياطي...", error);
        try {
            const fallbackRes = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd');
            const fallbackData = await fallbackRes.json();
            if (fallbackData && fallbackData['the-open-network'] && fallbackData['the-open-network'].usd) {
                currentTonPriceUSD = parseFloat(fallbackData['the-open-network'].usd);
            }
        } catch (fallbackErr) {
            console.error("❌ خطأ في جلب سعر TON المباشر من كل المصادر:", fallbackErr);
        }
    } finally {
        const tonPriceElem = document.getElementById('current-ton-price');
        if (tonPriceElem) {
            tonPriceElem.innerText = currentTonPriceUSD.toFixed(2);
        }
        
        if (typeof window.updateHeaderBalances === 'function') {
            window.updateHeaderBalances();
        }
    }
}

// ==========================================
// 🔗 1. تهيئة TonConnect بأمان تام
// ==========================================
async function initTonConnect() {
    // إنشاء الحاوية بشكل يسمح للمكتبة بالعمل بدون تشويه الواجهة
    let hiddenDiv = document.getElementById('hidden-ton-root');
    if (!hiddenDiv) {
        hiddenDiv = document.createElement('div');
        hiddenDiv.id = 'hidden-ton-root';
        // استخدام الإخفاء الآمن بدل display: none
        hiddenDiv.style.position = 'absolute';
        hiddenDiv.style.top = '-9999px';
        hiddenDiv.style.left = '-9999px';
        hiddenDiv.style.visibility = 'hidden';
        document.body.appendChild(hiddenDiv);
    }

    try {
        if (typeof window.TON_CONNECT_UI === 'undefined') {
            console.warn("⏳ مكتبة TON_CONNECT_UI غير محملة، سيتم إعادة المحاولة...");
            setTimeout(initTonConnect, 1000);
            return;
        }

        tonConnectUI = new window.TON_CONNECT_UI.TonConnectUI({
            manifestUrl: 'https://zn-goxe-production.up.railway.app/tonconnect-manifest.json',
            buttonRootId: 'hidden-ton-root'
        });

        // إعدادات الواجهة بطريقة آمنة
        tonConnectUI.uiOptions = {
            theme: 'DARK',
            colorsSet: {
                DARK: {
                    connectButton: { background: '#0088cc', foreground: '#ffffff' },
                    accent: '#0088cc', 
                    telegramButton: '#0088cc',
                    background: { primary: '#121212', secondary: '#1e1e1e', qr: '#ffffff' },
                    text: { primary: '#ffffff', secondary: '#aaaaaa' }
                }
            }
        };

        // مراقبة حالة الاتصال بالمحفظة
        tonConnectUI.onStatusChange(wallet => {
            if (wallet && wallet.account) {
                isWalletConnected = true;
                userWalletAddress = window.TON_CONNECT_UI.toUserFriendlyAddress(wallet.account.address);
                triggerHapticFeedback('notification', 'success');
            } else {
                isWalletConnected = false;
                userWalletAddress = null;
            }
            
            if (typeof window.renderWalletTab === 'function') {
                window.renderWalletTab(currentWalletTab); 
            }
        });
    } catch (e) {
        console.error("❌ خطأ أثناء تهيئة TonConnect:", e);
    }
}

window.connectCustomWallet = async function() {
    triggerHapticFeedback('impact', 'light');
    
    if (!tonConnectUI) {
        showAppAlert("⏳ جاري تحميل إعدادات المحفظة، يرجى الانتظار ثانية والمحاولة...");
        initTonConnect(); // محاولة التهيئة مجدداً في حال فشلها مسبقاً
        return;
    }
    
    try { 
        await tonConnectUI.openModal(); 
    } catch (e) { 
        console.log("تم إلغاء عملية الاتصال أو إغلاق النافذة:", e); 
    }
};

window.disconnectCustomWallet = async function() {
    triggerHapticFeedback('impact', 'medium');
    if (tonConnectUI) {
        try { 
            await tonConnectUI.disconnect(); 
            showAppAlert("✅ تم إلغاء ربط المحفظة بنجاح.");
        } catch (e) { 
            console.error("خطأ أثناء إلغاء ربط المحفظة:", e); 
        }
    }
};

// ==========================================
// 🔒 2. مزامنة الأرصدة الحقيقية مع الواجهة
// ==========================================
window.updateHeaderBalances = function() {
    const pData = window.PlayerData || playerData;
    
    const zn = parseFloat(pData.balance !== undefined ? pData.balance : pData.znBalance) || 0;
    const usd = parseFloat(pData.usd_balance !== undefined ? pData.usd_balance : pData.usdBalance) || 0;

    const znElem = document.getElementById('wallet-zn-balance');
    const usdElem = document.getElementById('wallet-usd-balance');
    const tonElem = document.getElementById('wallet-ton-estimate');

    if (znElem) znElem.innerText = Math.floor(zn).toLocaleString('ar-EG');
    if (usdElem) usdElem.innerText = usd.toFixed(5) + " $";
    
    let estimateTon = currentTonPriceUSD > 0 ? (usd / currentTonPriceUSD) : 0;
    if (tonElem) tonElem.innerText = "≈ " + estimateTon.toFixed(4) + " TON";
};

// ==========================================
// 🎨 3. عرض تبويبات المحفظة
// ==========================================
window.renderWalletTab = function(tab) {
    currentWalletTab = tab;
    localStorage.setItem('lastWalletTab', tab);

    const content = document.getElementById('wallet-content');
    if (!content) return;
    
    const tabs = ['withdraw', 'history', 'deposit'];
    tabs.forEach(t => {
        const btn = document.getElementById(`btn-${t}`);
        if (btn) {
            if (t === tab) btn.classList.add('active');
            else btn.classList.remove('active');
        }
    });

    if (tab === 'deposit') {
        if (!isWalletConnected) {
            content.innerHTML = `
                <div class="card locked-state" style="text-align: center; padding: 25px 15px;">
                    <div style="font-size: 40px; margin-bottom: 10px;">🔒</div>
                    <p style="color: #ccc; margin-bottom: 15px;">يجب ربط محفظة التليجرام أولاً لتتمكن من الإيداع</p>
                    <button onclick="window.connectCustomWallet()" class="action-btn btn-blue" style="width: 100%; max-width: 250px;">ربط المحفظة الآن</button>
                </div>`;
        } else {
            content.innerHTML = `
                <div class="card">
                    <div class="connected-state" style="background: rgba(0, 136, 204, 0.1); padding: 12px; border-radius: 10px; margin-bottom: 15px; border: 1px solid rgba(0,136,204,0.3); display: flex; justify-content: space-between; align-items: center;">
                        <div class="wallet-address-text" style="color: #00cc66; font-size: 12px; word-break: break-all;">
                            ✅ متصل:<br><b style="color: #fff;">${userWalletAddress}</b>
                        </div>
                        <button onclick="window.disconnectCustomWallet()" class="disconnect-btn" style="background: #ff4444; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 11px; cursor: pointer;">إلغاء الربط</button>
                    </div>
                    
                    <h3 style="margin-top:0; color:#fff; text-align:center; margin-bottom: 15px;">إيداع (شراء رصيد USD)</h3>
                    
                    <div class="input-group" style="margin-bottom: 15px;">
                        <label class="input-label" style="display:block; color:#aaa; margin-bottom:5px; font-size:13px;">المبلغ المطلوب إيداعه ($)</label>
                        <input type="number" id="deposit-usd-input" class="input-field" placeholder="مثال: 5" style="width:100%; padding:10px; border-radius:8px; border:1px solid #333; background:#1e1e1e; color:#fff;" oninput="window.calculateDepositTon()">
                    </div>
                    
                    <div id="deposit-calc-info" style="display:none; padding:10px; margin-bottom:15px; border-radius:8px; text-align:center; background:rgba(0, 136, 204, 0.1); border:1px solid #0088cc;">
                        مطلوب إرسال: <b id="required-ton-amount" style="color:#88ccff;">0</b> TON
                    </div>
                    
                    <button id="deposit-btn" onclick="window.executeDeposit()" class="action-btn btn-blue" style="width:100%;">متابعة الدفع بواسطة TON</button>
                </div>`;
        }
    } 
    else if (tab === 'history') {
        content.innerHTML = `
            <div class="card" style="text-align:center; color:#777; padding:30px;">
                <div style="font-size:30px; margin-bottom:10px;">⏳</div>
                جاري تحميل السجلات...
            </div>`;
        
        const initData = tgApp?.initData || '';
        fetch(`/api/get_history?initData=${encodeURIComponent(initData)}`)
            .then(res => res.json())
            .then(data => {
                if (data.success && data.history && data.history.length > 0) {
                    let html = `<div class="card" style="padding: 15px;">
                        <h3 style="margin-top:0; color:#fff; text-align:center; margin-bottom:15px;">📋 سجل المعاملات</h3>
                        <div style="display: flex; flex-direction: column; gap: 10px; max-height: 380px; overflow-y: auto;">`;
                    
                    data.history.forEach(item => {
                        const isDeposit = item.type === 'deposit';
                        const typeText = isDeposit ? '🟢 إيداع' : '🔴 سحب';
                        
                        let statusText = 'قيد المراجعة ⏳';
                        let statusColor = '#f0ad4e';
                        if (item.status === 'completed' || item.status === 'approved') {
                            statusText = 'مكتمل ✅';
                            statusColor = '#00cc66';
                        } else if (item.status === 'rejected' || item.status === 'cancelled') {
                            statusText = 'مرفوض ❌';
                            statusColor = '#ff4444';
                        }

                        const dateStr = item.created_at ? new Date(item.created_at).toLocaleString('ar-EG', {
                            month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                        }) : '';
                        
                        html += `
                            <div style="background: rgba(255,255,255,0.04); padding: 12px; border-radius: 10px; display: flex; justify-content: space-between; align-items: center; border: 1px solid rgba(255,255,255,0.08);">
                                <div>
                                    <div style="font-weight: bold; color: #fff; font-size: 14px;">${typeText}</div>
                                    <div style="font-size: 11px; color: #888; margin-top: 3px;">${dateStr}</div>
                                </div>
                                <div style="text-align: left;">
                                    <div style="color: ${isDeposit ? '#00cc66' : '#ff4444'}; font-weight: bold; font-size: 15px;">$${parseFloat(item.amount_usd || item.amount || 0).toFixed(2)}</div>
                                    <div style="font-size: 11px; color: ${statusColor}; margin-top: 3px;">${statusText}</div>
                                </div>
                            </div>`;
                    });

                    html += `</div></div>`;
                    content.innerHTML = html;
                } else {
                    content.innerHTML = `
                        <div class="card" style="text-align:center; color:#777; padding:40px 20px;">
                            <div style="font-size:40px; margin-bottom:10px;">📋</div>
                            لا توجد سجلات سحب أو إيداع حالياً
                        </div>`;
                }
            })
            .catch(err => {
                console.error("خطأ في جلب السجلات:", err);
                content.innerHTML = `
                    <div class="card" style="text-align:center; color:#ff4444; padding:30px 20px;">
                        ⚠️ خطأ في تحميل السجلات. تأكد من اتصالك بالإنترنت.
                    </div>`;
            });
    }
    else if (tab === 'withdraw') {
        let withdrawHtml = `
            <div class="card" style="margin-bottom: 15px;">
                <h3 style="margin-top:0; color:#fff; text-align:center; margin-bottom:10px;">🔄 تحويل النقاط إلى USD</h3>
                <label class="input-label" style="display:block; color:#aaa; margin-bottom:8px; font-size:12px; text-align:center;">
                    (كل 1,000,000 ZN = $1.00 USD)
                </label>
                <input type="number" id="zn-input" class="input-field" placeholder="أدخل كمية ZN المراد تحويلها" style="width:100%; padding:10px; border-radius:8px; border:1px solid #333; background:#1e1e1e; color:#fff; margin-bottom:15px;" oninput="window.calculateConversionPreview()">
                
                <div id="conversion-calc-info" style="display:none; padding:10px; margin-bottom:15px; text-align:center; color:#00cc66; background:rgba(0, 204, 102, 0.1); border:1px solid #00cc66; border-radius:8px;">
                    ستحصل على: <b id="expected-usd-amount">0.00000</b> $
                </div>

                <button id="convert-btn" onclick="window.convertManualPoints()" class="action-btn btn-green" style="width:100%;">تحويل النقاط الآن</button>
            </div>`;

        if (!isWalletConnected) {
            withdrawHtml += `
                <div class="card locked-state" style="text-align: center; padding: 25px 15px;">
                    <div style="font-size: 40px; margin-bottom: 10px;">🔒</div>
                    <p style="color: #ccc; margin-bottom: 15px;">يجب ربط محفظة التليجرام أولاً لتتمكن من السحب</p>
                    <button onclick="window.connectCustomWallet()" class="action-btn btn-blue" style="width:100%; max-width:250px;">ربط المحفظة الآن</button>
                </div>`;
        } else {
            withdrawHtml += `
                <div class="card">
                    <div class="connected-state" style="background: rgba(0, 136, 204, 0.1); padding: 12px; border-radius: 10px; margin-bottom: 15px; border: 1px solid rgba(0,136,204,0.3); display: flex; justify-content: space-between; align-items: center;">
                        <div class="wallet-address-text" style="color: #00cc66; font-size: 12px; word-break: break-all;">
                            ✅ متصل:<br><b style="color: #fff;">${userWalletAddress}</b>
                        </div>
                        <button onclick="window.disconnectCustomWallet()" class="disconnect-btn" style="background: #ff4444; color: #fff; border: none; padding: 6px 12px; border-radius: 6px; font-size: 11px; cursor: pointer;">إلغاء الربط</button>
                    </div>

                    <h3 style="margin-top:0; color:#fff; text-align:center; margin-bottom:15px;">📤 طلب سحب الأرباح</h3>
                    <div class="input-group" style="margin-bottom:15px;">
                        <label class="input-label" style="display:block; color:#aaa; margin-bottom:5px; font-size:13px;">المبلغ المراد سحبه ($)</label>
                        <input type="number" id="usd-withdraw" class="input-field" placeholder="المبلغ بالسنت أو الدولار ($)" style="width:100%; padding:10px; border-radius:8px; border:1px solid #333; background:#1e1e1e; color:#fff;" oninput="window.calculateWithdrawTon()">
                    </div>
                    
                    <div id="withdraw-calc-info" style="display:none; padding:10px; margin-bottom:15px; text-align:center; color:#aaa; font-size:13px; background:rgba(255,255,255,0.05); border-radius:8px;">
                        ستستلم على محفظتك: <b id="receive-ton-amount" style="color:#0088cc;">0</b> TON
                    </div>
                    
                    <button id="withdraw-btn" onclick="window.submitWithdrawal()" class="action-btn btn-blue" style="width:100%;">تقديم طلب سحب</button>
                </div>`;
        }
        content.innerHTML = withdrawHtml;
    }
};

// ==========================================
// 🧮 4. دالّات الحساب التلقائي (Real-time Calculators)
// ==========================================
window.calculateConversionPreview = function() {
    let inputElem = document.getElementById('zn-input');
    let infoDiv = document.getElementById('conversion-calc-info');
    let expectedElem = document.getElementById('expected-usd-amount');
    
    if (!inputElem || !infoDiv) return;
    
    let amount = parseFloat(inputElem.value);
    if (amount > 0) {
        let usdExpected = (amount / 1000000).toFixed(5);
        if (expectedElem) expectedElem.innerText = usdExpected;
        infoDiv.style.display = 'block';
    } else { 
        infoDiv.style.display = 'none'; 
    }
};

window.calculateDepositTon = function() {
    let inputElem = document.getElementById('deposit-usd-input');
    let infoDiv = document.getElementById('deposit-calc-info');
    let requiredElem = document.getElementById('required-ton-amount');

    if (!inputElem || !infoDiv) return;

    let usd = parseFloat(inputElem.value);
    if (usd > 0 && currentTonPriceUSD > 0) {
        let tonRequired = (usd / currentTonPriceUSD).toFixed(4);
        if (requiredElem) requiredElem.innerText = tonRequired;
        infoDiv.style.display = 'block';
    } else { 
        infoDiv.style.display = 'none'; 
    }
};

window.calculateWithdrawTon = function() {
    let inputElem = document.getElementById('usd-withdraw');
    let infoDiv = document.getElementById('withdraw-calc-info');
    let receiveElem = document.getElementById('receive-ton-amount');

    if (!inputElem || !infoDiv) return;

    let usd = parseFloat(inputElem.value);
    if (usd > 0 && currentTonPriceUSD > 0) {
        let tonReceive = (usd / currentTonPriceUSD).toFixed(4);
        if (receiveElem) receiveElem.innerText = tonReceive;
        infoDiv.style.display = 'block';
    } else { 
        infoDiv.style.display = 'none'; 
    }
};

// ==========================================
// 💸 5. تنفيذ العمليات (إيداع / تحويل / سحب)
// ==========================================
window.executeDeposit = async function() {
    triggerHapticFeedback('impact', 'medium');
    let depositBtn = document.getElementById('deposit-btn');
    let usdInput = document.getElementById('deposit-usd-input');
    
    let usdAmount = parseFloat(usdInput?.value);
    if (!usdAmount || usdAmount <= 0) {
        triggerHapticFeedback('notification', 'error');
        return showAppAlert("⚠️ يرجى إدخال مبلغ صحيح للإيداع بالدولار ($)");
    }

    let tonAmount = usdAmount / currentTonPriceUSD;
    let nanoTon = Math.floor(tonAmount * 1e9).toString(); 
    let projectWallet = "UQCkqSqgiw80Qz7ljESrhHppPAZU-lcTrmxyELN1Y-syVGtc"; 
    
    const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 360,
        messages: [{
            address: projectWallet,
            amount: nanoTon
        }]
    };

    try {
        if (depositBtn) {
            depositBtn.disabled = true;
            depositBtn.innerText = "⏳ جاري فتح المحفظة...";
        }

        const txResult = await tonConnectUI.sendTransaction(transaction);
        triggerHapticFeedback('notification', 'success');

        const initData = tgApp?.initData || null;
        if (initData) {
            await fetch('/api/wallet_deposit_report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    initData: initData,
                    usdAmount: usdAmount,
                    tonAmount: tonAmount,
                    boc: txResult.boc 
                })
            });
        }
        
        showAppAlert(`✅ تم إرسال المعاملة بنجاح للشبكة!\nسيتم إضافة $${usdAmount} لرصيدك بعد تأكيد البلوكشين.`);
        if (usdInput) usdInput.value = '';
        const calcInfo = document.getElementById('deposit-calc-info');
        if (calcInfo) calcInfo.style.display = 'none';

    } catch (e) {
        triggerHapticFeedback('notification', 'warning');
        if (e && e.message !== "User rejected the transaction") {
            console.error("خطأ الإيداع: ", e);
            showAppAlert("⚠️ حدث خطأ أثناء تنفيذ الدفع، أو تم إغلاق المحفظة.");
        } else {
            showAppAlert("ℹ️ تم إلغاء عملية الدفع بواسطة المستخدم.");
        }
    } finally {
        if (depositBtn) {
            depositBtn.disabled = false;
            depositBtn.innerText = "متابعة الدفع بواسطة TON";
        }
    }
};

window.convertManualPoints = async function() {
    triggerHapticFeedback('impact', 'medium');
    let convertBtn = document.getElementById('convert-btn');
    let znInput = document.getElementById('zn-input');

    let amount = parseFloat(znInput?.value);
    if (!amount || isNaN(amount) || amount <= 0) {
        triggerHapticFeedback('notification', 'error');
        return showAppAlert("⚠️ الرجاء إدخال كمية صحيحة من النقاط (ZN)");
    }
    
    const initData = tgApp?.initData || null;
    if (!initData) {
        triggerHapticFeedback('notification', 'error');
        return showAppAlert("⚠️ يجب فتح اللعبة من داخل التليجرام لحماية معاملتك.");
    }

    try {
        if (convertBtn) {
            convertBtn.disabled = true;
            convertBtn.innerText = "⏳ جاري التحويل...";
        }

        let response = await fetch('/api/wallet_convert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData, amount: amount })
        });
        let result = await response.json();
        
        if (result.success) {
            triggerHapticFeedback('notification', 'success');
            const usdGained = result.usd_gained || (amount / 1000000);
            
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                await window.fetchPlayerDataFromServer();
            } else {
                const pData = window.PlayerData || playerData;
                if (pData.balance !== undefined) pData.balance -= amount;
                if (pData.usd_balance !== undefined) pData.usd_balance = (pData.usd_balance || 0) + usdGained;
            }

            window.updateHeaderBalances();
            showAppAlert(`🎉 تم تحويل النقاط بنجاح!\nكسبت $${usdGained.toFixed(5)} USD`);
            
            if (znInput) znInput.value = '';
            const infoDiv = document.getElementById('conversion-calc-info');
            if (infoDiv) infoDiv.style.display = 'none';

        } else {
            triggerHapticFeedback('notification', 'error');
            showAppAlert("⚠️ فشل التحويل: " + (result.error || result.message || "سبب غير معروف"));
        }
    } catch (e) { 
        console.error("خطأ في الاتصال بالخادم عند تحويل النقاط:", e);
        triggerHapticFeedback('notification', 'error');
        showAppAlert("⚠️ حدث خطأ أثناء الاتصال بالسيرفر. حاول مرة أخرى."); 
    } finally {
        if (convertBtn) {
            convertBtn.disabled = false;
            convertBtn.innerText = "تحويل النقاط الآن";
        }
    }
};

window.submitWithdrawal = async function() {
    triggerHapticFeedback('impact', 'medium');
    let withdrawBtn = document.getElementById('withdraw-btn');
    let usdInput = document.getElementById('usd-withdraw');

    let usdAmount = parseFloat(usdInput?.value);
    if (!usdAmount || usdAmount <= 0) {
        triggerHapticFeedback('notification', 'error');
        return showAppAlert("⚠️ يرجى إدخال مبلغ صحيح للسحب ($)");
    }

    if (!userWalletAddress) {
        triggerHapticFeedback('notification', 'warning');
        return showAppAlert("⚠️ الرجاء ربط محفظة التليجرام أولاً لتحديد عنوان الاستلام.");
    }

    const initData = tgApp?.initData || null;
    if (!initData) {
        triggerHapticFeedback('notification', 'error');
        return showAppAlert("⚠️ غير مصرح بالعملية خارج التليجرام.");
    }

    try {
        if (withdrawBtn) {
            withdrawBtn.disabled = true;
            withdrawBtn.innerText = "⏳ جاري إرسال الطلب...";
        }

        let response = await fetch('/api/wallet_withdraw', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                initData: initData, 
                amount: usdAmount,
                walletAddress: userWalletAddress 
            })
        });
        let result = await response.json();
        
        if (result.success) {
            triggerHapticFeedback('notification', 'success');
            
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                await window.fetchPlayerDataFromServer();
            } else {
                const pData = window.PlayerData || playerData;
                if (pData.usd_balance !== undefined) pData.usd_balance -= usdAmount;
            }
            
            let expectedTon = (usdAmount / currentTonPriceUSD).toFixed(4);
            window.updateHeaderBalances();
            
            showAppAlert(`✅ تم تقديم طلب السحب بنجاح بقيمة $${usdAmount}.\nستصلك المعاملة (≈ ${expectedTon} TON) بعد فحص الإدارة.`);
            if (usdInput) usdInput.value = '';
            
            const infoDiv = document.getElementById('withdraw-calc-info');
            if (infoDiv) infoDiv.style.display = 'none';

        } else {
            triggerHapticFeedback('notification', 'error');
            showAppAlert("⚠️ رفض السيرفر طلب السحب: " + (result.error || result.message || "سبب غير معروف"));
        }
    } catch (e) { 
        console.error("خطأ أثناء السحب:", e);
        triggerHapticFeedback('notification', 'error');
        showAppAlert("⚠️ خطأ في معالجة طلب السحب. حاول لاحقاً."); 
    } finally {
        if (withdrawBtn) {
            withdrawBtn.disabled = false;
            withdrawBtn.innerText = "تقديم طلب سحب";
        }
    }
};

// ==========================================
// 🚀 6. التشغيل والتنفيذ التلقائي (Auto Initialization)
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    fetchLiveTonPrice();
    setInterval(fetchLiveTonPrice, 60000);
    initTonConnect();

    setTimeout(() => {
        if (typeof window.updateHeaderBalances === 'function') {
            window.updateHeaderBalances();
        }
        if (typeof window.renderWalletTab === 'function') {
            window.renderWalletTab(currentWalletTab);
        }
    }, 200);
});

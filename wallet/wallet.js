// ==========================================
// 💳 ZN Goxe - Wallet Module (wallet.js)
// ==========================================

let playerData = {
    znBalance: 0,
    usdBalance: 0.00000,
    tgId: null 
};

let isWalletConnected = false;
let userWalletAddress = null;
let currentTonPriceUSD = 5.00;
let currentWalletTab = localStorage.getItem('lastWalletTab') || 'withdraw';
let tonConnectUI = null;

// ==========================================
// 🌐 0. جلب سعر عملة TON الفعلي واللحظي من السوق
// ==========================================
async function fetchLiveTonPrice() {
    try {
        const response = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT');
        const data = await response.json();
        
        if (data && data.price) {
            currentTonPriceUSD = parseFloat(data.price);
            
            const tonPriceElem = document.getElementById('current-ton-price');
            if (tonPriceElem) {
                tonPriceElem.innerText = currentTonPriceUSD.toFixed(2);
            }
            
            window.updateHeaderBalances();
        }
    } catch (error) {
        console.error("خطأ في جلب سعر TON المباشر:", error);
    }
}

// ==========================================
// 🔗 1. تهيئة TonConnect بأمان تام
// ==========================================
async function initTonConnect() {
    if (!document.getElementById('hidden-ton-root')) {
        let hiddenDiv = document.createElement('div');
        hiddenDiv.id = 'hidden-ton-root';
        hiddenDiv.style.display = 'none';
        document.body.appendChild(hiddenDiv);
    }

    try {
        tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
            manifestUrl: 'https://zn-goxe-production.up.railway.app/tonconnect-manifest.json',
            buttonRootId: 'hidden-ton-root',
            uiPreferences: {
                theme: TON_CONNECT_UI.THEME.DARK,
                colorsSet: {
                    [TON_CONNECT_UI.THEME.DARK]: {
                        connectButton: { background: '#0088cc', foreground: '#ffffff' },
                        accent: '#0088cc', 
                        telegramButton: '#0088cc',
                        background: { primary: '#121212', secondary: '#1e1e1e', qr: '#ffffff' },
                        text: { primary: '#ffffff', secondary: '#aaaaaa' }
                    }
                }
            }
        });

        tonConnectUI.onStatusChange(wallet => {
            if (wallet) {
                isWalletConnected = true;
                userWalletAddress = TON_CONNECT_UI.toUserFriendlyAddress(wallet.account.address);
            } else {
                isWalletConnected = false;
                userWalletAddress = null;
            }
            window.renderWalletTab(currentWalletTab); 
        });
    } catch (e) {
        console.error("خطأ في تهيئة TonConnect:", e);
    }
}
initTonConnect(); 

window.connectCustomWallet = async function() {
    if (!tonConnectUI) {
        alert("⏳ جاري تحميل المحفظة، يرجى الانتظار ثانية والمحاولة مرة أخرى...");
        return;
    }
    try { await tonConnectUI.connectWallet(); } catch (e) { console.log("تم إلغاء الفتح:", e); }
};

window.disconnectCustomWallet = async function() {
    if (tonConnectUI) {
        try { await tonConnectUI.disconnect(); } catch (e) { console.error("خطأ أثناء الإلغاء:", e); }
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

    if (znElem) znElem.innerText = Math.floor(zn).toLocaleString();
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
        if(btn) {
            if(t === tab) btn.classList.add('active');
            else btn.classList.remove('active');
        }
    });

    if (tab === 'deposit') {
        if (!isWalletConnected) {
            content.innerHTML = `
                <div class="card locked-state">
                    <p>يجب ربط محفظة التليجرام أولاً لتتمكن من الإيداع</p>
                    <button onclick="window.connectCustomWallet()" class="action-btn btn-blue">ربط المحفظة الآن</button>
                </div>`;
        } else {
            content.innerHTML = `
                <div class="card">
                    <div class="connected-state">
                        <div class="wallet-address-text">✅ متصل:<br>${userWalletAddress}</div>
                        <button onclick="window.disconnectCustomWallet()" class="disconnect-btn">إلغاء الربط</button>
                    </div>
                    
                    <h3 style="margin-top:0; color:#fff; text-align:center;">إيداع (شراء ZN)</h3>
                    <div class="input-group">
                        <label class="input-label">المبلغ المطلوب إيداعه ($)</label>
                        <input type="number" id="deposit-usd-input" class="input-field" placeholder="مثال: 5" oninput="window.calculateDepositTon()">
                    </div>
                    
                    <div id="deposit-calc-info" style="display:none; padding:10px; margin-bottom:15px; border-radius:8px; text-align:center; background:rgba(0, 136, 204, 0.1); border:1px solid #0088cc;">
                        مطلوب إرسال: <b id="required-ton-amount" style="color:#88ccff;">0</b> TON
                    </div>
                    
                    <button onclick="window.executeDeposit()" class="action-btn btn-blue">متابعة الدفع بواسطة TON</button>
                </div>`;
        }
    } 
    else if (tab === 'history') {
        content.innerHTML = `
            <div class="card" style="text-align:center; color:#777; padding:20px;">
                <div style="font-size:30px; margin-bottom:10px;">⏳</div>
                جاري تحميل السجلات...
            </div>`;
        
        // أضفنا حماية للتأكد من وجود التليجرام أوبجيكت
        const initData = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp.initData : '';
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
                        if (item.status === 'completed') {
                            statusText = 'مكتمل ✅';
                            statusColor = '#00cc66';
                        } else if (item.status === 'rejected') {
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
                                    <div style="color: ${isDeposit ? '#00cc66' : '#ff4444'}; font-weight: bold; font-size: 15px;">$${parseFloat(item.amount_usd || 0).toFixed(2)}</div>
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
                console.error("Error fetching history:", err);
                content.innerHTML = `
                    <div class="card" style="text-align:center; color:#ff4444; padding:30px 20px;">
                        ⚠️ خطأ في تحميل السجلات. تأكد من اتصالك بالإنترنت.
                    </div>`;
            });
    }
    else if (tab === 'withdraw') {
        let withdrawHtml = `
            <div class="card">
                <label class="input-label">تحويل ZN إلى USD (كل 1,000,000 ZN = $1)</label>
                <input type="number" id="zn-input" class="input-field" placeholder="أدخل كمية ZN" style="margin-bottom:15px;" oninput="window.calculateConversionPreview()">
                
                <div id="conversion-calc-info" style="display:none; padding:10px; margin-bottom:15px; text-align:center; color:#00cc66; background:rgba(0, 204, 102, 0.1); border:1px solid #00cc66; border-radius:8px;">
                    ستحصل على: <b id="expected-usd-amount">0.00000</b> $
                </div>

                <button onclick="window.convertManualPoints()" class="action-btn btn-green">تحويل النقاط</button>
            </div>`;

        if (!isWalletConnected) {
            withdrawHtml += `
                <div class="card locked-state">
                    <p>يجب ربط محفظة التليجرام أولاً لتتمكن من السحب</p>
                    <button onclick="window.connectCustomWallet()" class="action-btn btn-blue">ربط المحفظة الآن</button>
                </div>`;
        } else {
            withdrawHtml += `
                <div class="card">
                    <div class="connected-state">
                        <div class="wallet-address-text">✅ متصل:<br>${userWalletAddress}</div>
                        <button onclick="window.disconnectCustomWallet()" class="disconnect-btn">إلغاء الربط</button>
                    </div>

                    <label class="input-label">سحب الأرباح</label>
                    <div class="input-group">
                        <input type="number" id="usd-withdraw" class="input-field" placeholder="المبلغ للسحب ($)" oninput="window.calculateWithdrawTon()">
                    </div>
                    
                    <div id="withdraw-calc-info" style="display:none; padding:10px; margin-bottom:15px; text-align:center; color:#aaa; font-size:13px;">
                        ستستلم على محفظتك: <b id="receive-ton-amount" style="color:#0088cc;">0</b> TON
                    </div>
                    
                    <button onclick="window.submitWithdrawal()" class="action-btn btn-blue">تقديم طلب سحب</button>
                </div>`;
        }
        content.innerHTML = withdrawHtml;
    }
};

// ==========================================
// 🧮 4. دالّات الحساب التلقائي
// ==========================================
window.calculateConversionPreview = function() {
    let amount = parseFloat(document.getElementById('zn-input').value);
    let infoDiv = document.getElementById('conversion-calc-info');
    if (amount > 0) {
        let usdExpected = (amount / 1000000).toFixed(5);
        document.getElementById('expected-usd-amount').innerText = usdExpected;
        infoDiv.style.display = 'block';
    } else { 
        infoDiv.style.display = 'none'; 
    }
};

window.calculateDepositTon = function() {
    let usd = parseFloat(document.getElementById('deposit-usd-input').value);
    let infoDiv = document.getElementById('deposit-calc-info');
    if (usd > 0) {
        document.getElementById('required-ton-amount').innerText = (usd / currentTonPriceUSD).toFixed(4);
        infoDiv.style.display = 'block';
    } else { infoDiv.style.display = 'none'; }
};

window.calculateWithdrawTon = function() {
    let usd = parseFloat(document.getElementById('usd-withdraw').value);
    let infoDiv = document.getElementById('withdraw-calc-info');
    if (usd > 0) {
        document.getElementById('receive-ton-amount').innerText = (usd / currentTonPriceUSD).toFixed(4);
        infoDiv.style.display = 'block';
    } else { infoDiv.style.display = 'none'; }
};

// ==========================================
// 💸 5. تنفيذ العمليات (إيداع / تحويل / سحب)
// ==========================================
window.executeDeposit = async function() {
    let usdAmount = parseFloat(document.getElementById('deposit-usd-input').value);
    if (!usdAmount || usdAmount <= 0) return alert("يرجى إدخال مبلغ صحيح للإيداع");

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
        const txResult = await tonConnectUI.sendTransaction(transaction);
        
        const initData = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp.initData : null;
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
        
        alert(`✅ تم إرسال المعاملة بنجاح للشبكة!\nسيتم إضافة $${usdAmount} لرصيدك بعد التأكيد.`);
        document.getElementById('deposit-usd-input').value = '';
        document.getElementById('deposit-calc-info').style.display = 'none';
        
    } catch (e) {
        if(e && e.message !== "User rejected the transaction") {
            console.error("Deposit Error: ", e);
            alert("حدث خطأ أثناء الدفع أو تم إلغاء العملية.");
        }
    }
};

window.convertManualPoints = async function() {
    let amount = parseFloat(document.getElementById('zn-input').value);
    
    if (!amount || isNaN(amount) || amount <= 0) return alert("الرجاء إدخال كمية صحيحة من النقاط");
    
    const initData = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp.initData : null;
    if (!initData) return alert("⚠️ يجب فتح اللعبة من تليجرام لحماية معاملتك.");

    try {
        let response = await fetch('/api/wallet_convert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData, amount: amount })
        });
        let result = await response.json();
        
        if (result.success) {
            const usdGained = result.usd_gained || (amount / 1000000);
            
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                await window.fetchPlayerDataFromServer();
            } else {
                const pData = window.PlayerData || playerData;
                if (pData.balance !== undefined) pData.balance -= amount;
                if (pData.usd_balance !== undefined) pData.usd_balance = (pData.usd_balance || 0) + usdGained;
            }

            window.updateHeaderBalances();

            alert(`✅ تم تحويل النقاط بنجاح! كسبت $${usdGained.toFixed(5)}`);
            document.getElementById('zn-input').value = '';
            
            const infoDiv = document.getElementById('conversion-calc-info');
            if (infoDiv) infoDiv.style.display = 'none';
        } else {
            alert("⚠️ فشل التحويل: " + (result.error || "خطأ غير معروف"));
        }
    } catch (e) { 
        console.error(e);
        alert("خطأ في الاتصال بالخادم."); 
    }
};

window.submitWithdrawal = async function() {
    let usdAmount = parseFloat(document.getElementById('usd-withdraw').value);
    if (!usdAmount || usdAmount <= 0) return alert("يرجى إدخال مبلغ صحيح للسحب");
    if (!userWalletAddress) return alert("الرجاء ربط المحفظة أولاً لتحديد عنوان السحب.");

    const initData = (window.Telegram && window.Telegram.WebApp) ? window.Telegram.WebApp.initData : null;
    if (!initData) return alert("⚠️ غير مصرح بالعملية خارج التليجرام.");

    try {
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
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                await window.fetchPlayerDataFromServer();
            } else {
                const pData = window.PlayerData || playerData;
                if (pData.usd_balance !== undefined) pData.usd_balance -= usdAmount;
            }
            
            let expectedTon = (usdAmount / currentTonPriceUSD).toFixed(4);
            window.updateHeaderBalances();
            alert(`✅ تم تقديم طلب السحب بنجاح بقيمة $${usdAmount}.\nستصلك المعاملة (≈ ${expectedTon} TON) بعد فحص الإدارة.`);
            document.getElementById('usd-withdraw').value = '';
            
            const infoDiv = document.getElementById('withdraw-calc-info');
            if (infoDiv) infoDiv.style.display = 'none';
        } else {
            alert("⚠️ رفض السيرفر طلب السحب: " + (result.error || "خطأ غير معروف"));
        }
    } catch (e) { alert("خطأ في معالجة طلب السحب."); }
};

// ==========================================
// 🚀 6. بدء التشغيل التلقائي
// ==========================================
fetchLiveTonPrice();
setInterval(fetchLiveTonPrice, 60000);

setTimeout(() => {
    window.updateHeaderBalances();
    window.renderWalletTab(currentWalletTab);
}, 300);

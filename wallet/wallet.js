// بيانات افتراضية (تتحول ديناميكياً لتطابق رصيد قاعدة البيانات)
let playerData = {
    znBalance: 0,
    usdBalance: 0.00000,
    tgId: null 
};

let isWalletConnected = false;
let userWalletAddress = null;
let currentTonPriceUSD = 5.00; 
let currentWalletTab = localStorage.getItem('lastWalletTab') || 'deposit';
let tonConnectUI = null;

async function initTonConnect() {
    if (!document.getElementById('hidden-ton-root')) {
        let hiddenDiv = document.createElement('div');
        hiddenDiv.id = 'hidden-ton-root';
        hiddenDiv.style.display = 'none';
        document.body.appendChild(hiddenDiv);
    }

    try {
        tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
            // 🚨 الرابط الخاص بمشروعك (هنا السر كله لحل مشكلة البطة)
            manifestUrl: 'https://zn-goxe-production.up.railway.app/tonconnect-manifest.json',
            buttonRootId: 'hidden-ton-root',
            // 🎨 تغيير الألوان للأزرق الداكن بدلاً من الأصفر
            uiPreferences: {
                theme: TON_CONNECT_UI.THEME.DARK,
                colorsSet: {
                    [TON_CONNECT_UI.THEME.DARK]: {
                        connectButton: {
                            background: '#0088cc', 
                            foreground: '#ffffff'
                        },
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
            renderWalletTab(currentWalletTab); 
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
}

window.disconnectCustomWallet = async function() {
    if (tonConnectUI) {
        try { await tonConnectUI.disconnect(); } catch (e) { console.error("خطأ أثناء الإلغاء:", e); }
    }
}

// 🔒 مزامنة الأرصدة الحقيقية المجلوبة من الخادم مع الحماية من NaN
function updateHeaderBalances() {
    const pData = window.PlayerData || playerData;
    
    // تأمين الأرقام وتحويلها بشكل صحيح
    const zn = parseFloat(pData.balance !== undefined ? pData.balance : pData.znBalance) || 0;
    const usd = parseFloat(pData.usd_balance !== undefined ? pData.usd_balance : pData.usdBalance) || 0;

    document.getElementById('wallet-zn-balance').innerText = Math.floor(zn).toLocaleString();
    document.getElementById('wallet-usd-balance').innerText = usd.toFixed(5) + " $";
    
    let estimateTon = usd / currentTonPriceUSD;
    document.getElementById('wallet-ton-estimate').innerText = "≈ " + estimateTon.toFixed(4) + " TON";
}

window.renderWalletTab = function(tab) {
    currentWalletTab = tab;
    localStorage.setItem('lastWalletTab', tab);

    const content = document.getElementById('wallet-content');
    if (!content) return;
    
    const tabs = ['deposit', 'history', 'withdraw'];
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
                    <button onclick="connectCustomWallet()" class="action-btn btn-blue">ربط المحفظة الآن</button>
                </div>`;
        } else {
            content.innerHTML = `
                <div class="card">
                    <div class="connected-state">
                        <div class="wallet-address-text">✅ متصل:<br>${userWalletAddress}</div>
                        <button onclick="disconnectCustomWallet()" class="disconnect-btn">إلغاء الربط</button>
                    </div>
                    
                    <h3 style="margin-top:0; color:#fff; text-align:center;">إيداع (شراء ZN)</h3>
                    <div class="input-group">
                        <label class="input-label">المبلغ المطلوب إيداعه ($)</label>
                        <input type="number" id="deposit-usd-input" class="input-field" placeholder="مثال: 5" oninput="calculateDepositTon()">
                    </div>
                    
                    <div id="deposit-calc-info" style="display:none; padding:10px; margin-bottom:15px; border-radius:8px; text-align:center; background:rgba(0, 136, 204, 0.1); border:1px solid #0088cc;">
                        مطلوب إرسال: <b id="required-ton-amount" style="color:#88ccff;">0</b> TON
                    </div>
                    
                    <button onclick="executeDeposit()" class="action-btn btn-blue">متابعة الدفع بواسطة TON</button>
                </div>`;
        }
    } 
    else if (tab === 'history') {
        content.innerHTML = `
            <div class="card" style="text-align:center; color:#777; padding:40px 20px;">
                <div style="font-size:40px; margin-bottom:10px;">📋</div>
                لا توجد سجلات سحب أو إيداع حالياً
            </div>`;
    }
    else if (tab === 'withdraw') {
        let withdrawHtml = `
            <div class="card">
                <label class="input-label">تحويل ZN إلى USD (كل 1,000,000 ZN = $1)</label>
                <input type="number" id="zn-input" class="input-field" placeholder="أدخل كمية ZN" style="margin-bottom:15px;" oninput="calculateConversionPreview()">
                
                <div id="conversion-calc-info" style="display:none; padding:10px; margin-bottom:15px; text-align:center; color:#00cc66; background:rgba(0, 204, 102, 0.1); border:1px solid #00cc66; border-radius:8px;">
                    ستحصل على: <b id="expected-usd-amount">0.00000</b> $
                </div>

                <button onclick="convertManualPoints()" class="action-btn btn-green">تحويل النقاط</button>
            </div>`;

        if (!isWalletConnected) {
            withdrawHtml += `
                <div class="card locked-state">
                    <p>يجب ربط محفظة التليجرام أولاً لتتمكن من السحب</p>
                    <button onclick="connectCustomWallet()" class="action-btn btn-blue">ربط المحفظة الآن</button>
                </div>`;
        } else {
            withdrawHtml += `
                <div class="card">
                    <div class="connected-state">
                        <div class="wallet-address-text">✅ متصل:<br>${userWalletAddress}</div>
                        <button onclick="disconnectCustomWallet()" class="disconnect-btn">إلغاء الربط</button>
                    </div>

                    <label class="input-label">سحب الأرباح</label>
                    <div class="input-group">
                        <input type="number" id="usd-withdraw" class="input-field" placeholder="المبلغ للسحب ($)" oninput="calculateWithdrawTon()">
                    </div>
                    
                    <div id="withdraw-calc-info" style="display:none; padding:10px; margin-bottom:15px; text-align:center; color:#aaa; font-size:13px;">
                        ستستلم على محفظتك: <b id="receive-ton-amount" style="color:#0088cc;">0</b> TON
                    </div>
                    
                    <button onclick="submitWithdrawal()" class="action-btn btn-blue">تقديم طلب سحب</button>
                </div>`;
        }
        content.innerHTML = withdrawHtml;
    }
}

// حساب توقعات الدولار أثناء الكتابة بناءً على: 1 مليون نقطة = 1 دولار
window.calculateConversionPreview = function() {
    let amount = document.getElementById('zn-input').value;
    let infoDiv = document.getElementById('conversion-calc-info');
    if (amount > 0) {
        let usdExpected = (amount / 1000000).toFixed(5);
        document.getElementById('expected-usd-amount').innerText = usdExpected;
        infoDiv.style.display = 'block';
    } else { 
        infoDiv.style.display = 'none'; 
    }
}

window.calculateDepositTon = function() {
    let usd = document.getElementById('deposit-usd-input').value;
    let infoDiv = document.getElementById('deposit-calc-info');
    if (usd > 0) {
        document.getElementById('required-ton-amount').innerText = (usd / currentTonPriceUSD).toFixed(4);
        infoDiv.style.display = 'block';
    } else { infoDiv.style.display = 'none'; }
}

window.calculateWithdrawTon = function() {
    let usd = document.getElementById('usd-withdraw').value;
    let infoDiv = document.getElementById('withdraw-calc-info');
    if (usd > 0) {
        document.getElementById('receive-ton-amount').innerText = (usd / currentTonPriceUSD).toFixed(4);
        infoDiv.style.display = 'block';
    } else { infoDiv.style.display = 'none'; }
}

// 🔒 تنفيذ الإيداع المالي ورفع بلاغ فوري مشفر للبايثون لتأكيد المعاملة
window.executeDeposit = async function() {
    let usdAmount = document.getElementById('deposit-usd-input').value;
    if (!usdAmount || usdAmount <= 0) return alert("يرجى إدخال مبلغ صحيح للإيداع");

    let tonAmount = usdAmount / currentTonPriceUSD;
    let nanoTon = Math.floor(tonAmount * 1e9).toString(); 
    let projectWallet = "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"; 
    
    const pData = window.PlayerData || playerData;
    const myId = pData.tg_id || (pData.tgId ? pData.tgId.toString() : "");

    const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 360,
        messages: [{
            address: projectWallet,
            amount: nanoTon,
            payload: TON_CONNECT_UI.getPayloadString(myId) 
        }]
    };

    try {
        const txResult = await tonConnectUI.sendTransaction(transaction);
        
        // رفع المعاملة فوراً للبايثون بطريقة آمنة جداً
        const initData = window.Telegram?.WebApp?.initData;
        if (initData) {
            await fetch('/api/wallet_deposit_report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    initData: initData,
                    usdAmount: parseFloat(usdAmount),
                    tonAmount: tonAmount,
                    boc: txResult.boc 
                })
            });
        }
        
        alert(`✅ تم إرسال المعاملة بنجاح للشبكة!\nسيتم إضافة ${usdAmount}$ لرصيدك بعد التأكيد التلقائي.`);
    } catch (e) {
        if(e.message !== "User rejected the transaction") alert("حدث خطأ أثناء الدفع أو تم إلغاء العملية.");
    }
}

// 🔒 تحويل النقاط بشكل حقيقي ومحمي على السيرفر
window.convertManualPoints = async function() {
    let amount = parseFloat(document.getElementById('zn-input').value);
    
    // التأكد من أن المستخدم أدخل رقماً
    if (!amount || isNaN(amount) || amount <= 0) return alert("الرجاء إدخال كمية صحيحة من النقاط");
    
    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) return alert("⚠️ يجب فتح اللعبة من تليجرام لحماية معاملتك.");

    try {
        let response = await fetch('/api/wallet_convert', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData, amount: amount })
        });
        let result = await response.json();
        
        if (result.success) {
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                await window.fetchPlayerDataFromServer();
            }
            updateHeaderBalances();
            alert(`✅ تم تحويل النقاط بنجاح! كسبت $${result.usd_gained ? result.usd_gained.toFixed(4) : (amount/1000000).toFixed(4)}`);
            document.getElementById('zn-input').value = '';
            document.getElementById('conversion-calc-info').style.display = 'none';
        } else {
            alert("⚠️ فشل التحويل من السيرفر: " + result.error);
        }
    } catch (e) { alert("خطأ في الاتصال بالخادم."); }
}

// 🔒 تقديم طلب سحب أرباح حقيقي وآمن بنسبة 100%
window.submitWithdrawal = async function() {
    let usdAmount = document.getElementById('usd-withdraw').value;
    if (!usdAmount || usdAmount <= 0) return alert("يرجى إدخال مبلغ صحيح للسحب");
    if (!userWalletAddress) return alert("الرجاء ربط المحفظة أولاً لتحديد عنوان السحب.");

    const initData = window.Telegram?.WebApp?.initData;
    if (!initData) return alert("⚠️ غير مصرح بالعملية خارج التليجرام.");

    try {
        let response = await fetch('/api/wallet_withdraw', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                initData: initData, 
                amount: parseFloat(usdAmount),
                walletAddress: userWalletAddress 
            })
        });
        let result = await response.json();
        
        if (result.success) {
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                await window.fetchPlayerDataFromServer();
            }
            let expectedTon = (usdAmount / currentTonPriceUSD).toFixed(4);
            updateHeaderBalances();
            alert(`✅ تم تقديم طلب السحب بنجاح بقيمة ${usdAmount}$.\nستصلك المعاملة (≈ ${expectedTon} TON) بعد فحص الإدارة.`);
            document.getElementById('usd-withdraw').value = '';
            document.getElementById('withdraw-calc-info').style.display = 'none';
        } else {
            alert("⚠️ رفض السيرفر طلب السحب: " + result.error);
        }
    } catch (e) { alert("خطأ في معالجة طلب السحب."); }
}

// تشغيل وتغذية البيانات اللحظية
setTimeout(() => {
    updateHeaderBalances();
    renderWalletTab(currentWalletTab);
}, 300);

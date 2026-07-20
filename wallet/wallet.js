// بيانات افتراضية للتجربة (هتتغير بعدين من الداتا بيز بتاعتك)
let playerData = {
    znBalance: 15400,
    usdBalance: 0.03080,
    tgId: 123456789 
};

// متغيرات النظام
let isWalletConnected = false;
let userWalletAddress = null;
let currentTonPriceUSD = 5.00; // سعر الـ TON بالدولار 
let currentWalletTab = localStorage.getItem('lastWalletTab') || 'deposit';
let tonConnectUI = null;

// 1. دالة تهيئة مكتبة TON Connect
function initTonConnect() {
    if (!tonConnectUI) {
        try {
            tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
                manifestUrl: 'https://raw.githubusercontent.com/ton-community/tutorials/main/03-client/test/public/tonconnect-manifest.json',
                buttonRootId: 'ton-connect-wrapper'
            });

            // مراقبة حالة المحفظة (اتربطت ولا اتلغت)
            tonConnectUI.onStatusChange(wallet => {
                if (wallet) {
                    isWalletConnected = true;
                    userWalletAddress = TON_CONNECT_UI.toUserFriendlyAddress(wallet.account.address);
                    renderWalletTab(currentWalletTab); // تحديث الشاشة
                } else {
                    isWalletConnected = false;
                    userWalletAddress = null;
                    renderWalletTab(currentWalletTab);
                }
            });
        } catch (e) {
            console.error("خطأ في تهيئة TonConnect:", e);
        }
    }
}

// 2. تحديث أرصدة الشاشة الرئيسية
function updateHeaderBalances() {
    document.getElementById('wallet-zn-balance').innerText = playerData.znBalance.toLocaleString();
    document.getElementById('wallet-usd-balance').innerText = playerData.usdBalance.toFixed(5) + " $";
    
    let estimateTon = playerData.usdBalance / currentTonPriceUSD;
    document.getElementById('wallet-ton-estimate').innerText = "≈ " + estimateTon.toFixed(4) + " TON";
}

// 3. الدالة الرئيسية لعرض التبويبات
function renderWalletTab(tab) {
    currentWalletTab = tab;
    localStorage.setItem('lastWalletTab', tab);

    const content = document.getElementById('wallet-content');
    if (!content) return;
    
    // تظبيط ألوان الأزرار العلوية
    const tabs = ['deposit', 'history', 'withdraw'];
    tabs.forEach(t => {
        const btn = document.getElementById(`btn-${t}`);
        if(btn) {
            if(t === tab) btn.classList.add('active');
            else btn.classList.remove('active');
        }
    });

    // قسم الإيداع
    if (tab === 'deposit') {
        content.innerHTML = `
            <div class="card">
                <h3 style="margin-top:0; color:#fff; text-align:center;">إيداع (شراء ZN)</h3>
                <p style="color:#aaa; font-size:13px; text-align:center; margin-bottom:20px;">
                    أدخل المبلغ الذي تريد إيداعه بالدولار، وسنحسب لك ما يعادله بعُملة TON.
                </p>
                <div class="input-group">
                    <label class="input-label">المبلغ المطلوب إيداعه ($)</label>
                    <input type="number" id="deposit-usd-input" class="input-field" placeholder="مثال: 5" oninput="calculateDepositTon()">
                </div>
                <!-- حساب الـ TON اللحظي بيظهر هنا -->
                <div id="deposit-calc-info" style="display:none; padding:10px; margin-bottom:15px; border-radius:8px; text-align:center; background:rgba(0, 136, 204, 0.1); border:1px solid #0088cc;">
                    مطلوب إرسال: <b id="required-ton-amount" style="color:#88ccff;">0</b> TON
                </div>
                ${!isWalletConnected ? `
                    <div style="padding:10px; margin-bottom:15px; border-radius:8px; text-align:center; background:rgba(255, 68, 68, 0.1); border:1px solid #ff4444; color:#ff4444;">يجب ربط محفظتك أولاً</div>
                    <div id="ton-connect-wrapper"></div>
                ` : `
                    <div style="padding:10px; margin-bottom:15px; border-radius:8px; text-align:center; background:rgba(0, 204, 102, 0.1); border:1px solid #00cc66; color:#00cc66;">المحفظة متصلة ✅</div>
                    <button onclick="executeDeposit()" class="action-btn btn-blue">متابعة الدفع بواسطة TON</button>
                `}
            </div>`;
            if (!isWalletConnected) setTimeout(initTonConnect, 100);
    } 
    // قسم السجلات
    else if (tab === 'history') {
        content.innerHTML = `
            <div class="card" style="text-align:center; color:#777; padding:40px 20px;">
                <div style="font-size:40px; margin-bottom:10px;">📋</div>
                لا توجد سجلات سحب أو إيداع حالياً
            </div>`;
    }
    // قسم السحب
    else if (tab === 'withdraw') {
        content.innerHTML = `
            <div>
                <!-- أداة التحويل -->
                <div class="card">
                    <label class="input-label">تحويل ZN إلى USD</label>
                    <input type="number" id="zn-input" class="input-field" placeholder="كمية ZN" style="margin-bottom:15px;">
                    <button onclick="convertManualPoints()" class="action-btn btn-green">تحويل النقاط</button>
                </div>

                <!-- أداة السحب -->
                <div class="card">
                    <label class="input-label">سحب الأرباح</label>
                    ${!isWalletConnected ? `
                        <div style="padding:10px; margin-bottom:15px; border-radius:8px; text-align:center; background:rgba(255, 68, 68, 0.1); border:1px solid #ff4444; color:#ff4444;">يجب ربط محفظة التليجرام أولاً</div>
                        <div id="ton-connect-wrapper"></div>
                    ` : `
                        <div style="padding:10px; margin-bottom:15px; border-radius:8px; text-align:center; background:rgba(0, 204, 102, 0.1); border:1px solid #00cc66; color:#00cc66; font-size:12px; word-break:break-all;">
                            ✅ مربوطة:<br>${userWalletAddress}
                        </div>
                    `}
                    <div class="input-group">
                        <input type="number" id="usd-withdraw" class="input-field" placeholder="المبلغ للسحب ($)" oninput="calculateWithdrawTon()" ${!isWalletConnected ? 'disabled' : ''}>
                    </div>
                    <!-- حساب الـ TON اللحظي للسحب بيظهر هنا -->
                    <div id="withdraw-calc-info" style="display:none; padding:10px; margin-bottom:15px; text-align:center; color:#aaa; font-size:13px;">
                        ستستلم على محفظتك: <b id="receive-ton-amount" style="color:#0088cc;">0</b> TON
                    </div>
                    <button onclick="submitWithdrawal()" class="action-btn ${isWalletConnected ? 'btn-blue' : 'btn-disabled'}" ${!isWalletConnected ? 'disabled' : ''}>
                        تقديم طلب سحب
                    </button>
                </div>
            </div>`;
            if (!isWalletConnected) setTimeout(initTonConnect, 100);
    }
}

// 4. حساب الـ TON المطلوب للإيداع أثناء الكتابة
window.calculateDepositTon = function() {
    let usd = document.getElementById('deposit-usd-input').value;
    let infoDiv = document.getElementById('deposit-calc-info');
    if (usd > 0) {
        document.getElementById('required-ton-amount').innerText = (usd / currentTonPriceUSD).toFixed(4);
        infoDiv.style.display = 'block';
    } else {
        infoDiv.style.display = 'none';
    }
}

// 5. حساب الـ TON المستلم للسحب أثناء الكتابة
window.calculateWithdrawTon = function() {
    let usd = document.getElementById('usd-withdraw').value;
    let infoDiv = document.getElementById('withdraw-calc-info');
    if (usd > 0) {
        document.getElementById('receive-ton-amount').innerText = (usd / currentTonPriceUSD).toFixed(4);
        infoDiv.style.display = 'block';
    } else {
        infoDiv.style.display = 'none';
    }
}

// 6. تنفيذ الإيداع عبر محفظة تليجرام
window.executeDeposit = async function() {
    let usdAmount = document.getElementById('deposit-usd-input').value;
    if (!usdAmount || usdAmount <= 0) return alert("يرجى إدخال مبلغ صحيح للإيداع");

    let tonAmount = usdAmount / currentTonPriceUSD;
    let nanoTon = Math.floor(tonAmount * 1e9).toString(); 
    let projectWallet = "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"; // حط عنوان محفظتك هنا

    const transaction = {
        validUntil: Math.floor(Date.now() / 1000) + 360,
        messages: [{
            address: projectWallet,
            amount: nanoTon,
            payload: TON_CONNECT_UI.getPayloadString(playerData.tgId.toString()) 
        }]
    };

    try {
        await tonConnectUI.sendTransaction(transaction);
        alert(`✅ تم الإيداع بنجاح!\nسيتم إضافة ${usdAmount}$ لرصيدك.`);
    } catch (e) {
        if(e.message !== "User rejected the transaction") alert("حدث خطأ أثناء الدفع");
    }
}

// 7. دالة تحويل النقاط (أصلية)
window.convertManualPoints = function() {
    let amount = document.getElementById('zn-input').value;
    if (!amount || amount < 5000) return alert("الحد الأدنى للتحويل هو 5000 ZN");
    if (amount > playerData.znBalance) return alert("رصيدك من ZN لا يكفي");
    
    let usd = (amount / 5000) * 0.01;
    playerData.znBalance -= amount;
    playerData.usdBalance += usd;
    updateHeaderBalances();
    alert(`✅ تم تحويل ${amount} ZN بنجاح إلى ${usd.toFixed(5)} $`);
    document.getElementById('zn-input').value = '';
}

// 8. طلب السحب
window.submitWithdrawal = function() {
    let usdAmount = document.getElementById('usd-withdraw').value;
    if (!usdAmount || usdAmount <= 0) return alert("يرجى إدخال مبلغ صحيح للسحب");
    if (usdAmount > playerData.usdBalance) return alert("رصيدك بالدولار لا يكفي");

    let expectedTon = (usdAmount / currentTonPriceUSD).toFixed(4);
    playerData.usdBalance -= usdAmount;
    updateHeaderBalances();
    alert(`✅ تم إرسال طلب سحب بقيمة ${usdAmount}$.\nستصلك ≈ ${expectedTon} TON على محفظتك.`);
    document.getElementById('usd-withdraw').value = '';
    document.getElementById('withdraw-calc-info').style.display = 'none';
}

// تشغيل الواجهة
updateHeaderBalances();
setTimeout(() => { renderWalletTab(currentWalletTab); }, 100);

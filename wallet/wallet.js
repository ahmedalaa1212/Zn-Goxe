// بيانات افتراضية
let playerData = {
    znBalance: 15400,
    usdBalance: 0.03080,
    tgId: 123456789 
};

// متغيرات النظام
let isWalletConnected = false;
let userWalletAddress = null;
let currentTonPriceUSD = 5.00; 
let currentWalletTab = localStorage.getItem('lastWalletTab') || 'deposit';
let tonConnectUI = null;

// 1. تهيئة المحفظة مرة واحدة فقط عند تحميل الصفحة
async function initTonConnect() {
    try {
        tonConnectUI = new TON_CONNECT_UI.TonConnectUI({
            manifestUrl: 'https://raw.githubusercontent.com/ton-community/tutorials/main/03-client/test/public/tonconnect-manifest.json'
            // شلنا الـ buttonRootId عشان هنتحكم في الفتح والقفل برمجياً
        });

        // المستمع اللحظي لحالة المحفظة (بيطبق على البوت كله)
        tonConnectUI.onStatusChange(wallet => {
            if (wallet) {
                isWalletConnected = true;
                userWalletAddress = TON_CONNECT_UI.toUserFriendlyAddress(wallet.account.address);
            } else {
                isWalletConnected = false;
                userWalletAddress = null;
            }
            // إعادة رسم الواجهة فوراً لتحديث الأزرار والمدخلات
            renderWalletTab(currentWalletTab); 
        });
    } catch (e) {
        console.error("خطأ في تهيئة TonConnect:", e);
    }
}
initTonConnect(); // تشغيل فوري

// 2. دوال التحكم اليدوي في المحفظة
window.connectCustomWallet = function() {
    if (tonConnectUI) tonConnectUI.openModal();
}
window.disconnectCustomWallet = async function() {
    if (tonConnectUI) {
        await tonConnectUI.disconnect();
        // الـ onStatusChange فوق هتلقط الفصل وتخفي الواجهة لوحدها
    }
}

// 3. تحديث أرصدة الشاشة الرئيسية
function updateHeaderBalances() {
    document.getElementById('wallet-zn-balance').innerText = playerData.znBalance.toLocaleString();
    document.getElementById('wallet-usd-balance').innerText = playerData.usdBalance.toFixed(5) + " $";
    
    let estimateTon = playerData.usdBalance / currentTonPriceUSD;
    document.getElementById('wallet-ton-estimate').innerText = "≈ " + estimateTon.toFixed(4) + " TON";
}

// 4. رسم الواجهة بناءً على حالة الربط
window.renderWalletTab = function(tab) {
    currentWalletTab = tab;
    localStorage.setItem('lastWalletTab', tab);

    const content = document.getElementById('wallet-content');
    if (!content) return;
    
    // تظبيط ألوان الأزرار
    const tabs = ['deposit', 'history', 'withdraw'];
    tabs.forEach(t => {
        const btn = document.getElementById(`btn-${t}`);
        if(btn) {
            if(t === tab) btn.classList.add('active');
            else btn.classList.remove('active');
        }
    });

    // --- قسم الإيداع ---
    if (tab === 'deposit') {
        if (!isWalletConnected) {
            // حالة عدم الربط: الواجهة مخفية وزر الربط فقط موجود
            content.innerHTML = `
                <div class="card locked-state">
                    <p>يجب ربط محفظة التليجرام أولاً لتتمكن من الإيداع</p>
                    <button onclick="connectCustomWallet()" class="action-btn btn-blue">ربط المحفظة الآن</button>
                </div>`;
        } else {
            // حالة الربط: إظهار خانة الإيداع
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
    // --- قسم السجلات ---
    else if (tab === 'history') {
        content.innerHTML = `
            <div class="card" style="text-align:center; color:#777; padding:40px 20px;">
                <div style="font-size:40px; margin-bottom:10px;">📋</div>
                لا توجد سجلات سحب أو إيداع حالياً
            </div>`;
    }
    // --- قسم السحب ---
    else if (tab === 'withdraw') {
        // قسم تحويل ZN إلى USD (داخلي فـ بيكون ظاهر دايماً ملوش علاقة بالمحفظة)
        let withdrawHtml = `
            <div class="card">
                <label class="input-label">تحويل ZN إلى USD</label>
                <input type="number" id="zn-input" class="input-field" placeholder="كمية ZN" style="margin-bottom:15px;">
                <button onclick="convertManualPoints()" class="action-btn btn-green">تحويل النقاط</button>
            </div>`;

        // قسم سحب الأرباح الفعلي
        if (!isWalletConnected) {
            // مخفي لو مش مربوط
            withdrawHtml += `
                <div class="card locked-state">
                    <p>يجب ربط محفظة التليجرام أولاً لتتمكن من السحب</p>
                    <button onclick="connectCustomWallet()" class="action-btn btn-blue">ربط المحفظة الآن</button>
                </div>`;
        } else {
            // ظاهر لو مربوط
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

// دوال الحساب اللحظية أثناء الكتابة
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

// تنفيذ الإيداع عبر محفظة تليجرام
window.executeDeposit = async function() {
    let usdAmount = document.getElementById('deposit-usd-input').value;
    if (!usdAmount || usdAmount <= 0) return alert("يرجى إدخال مبلغ صحيح للإيداع");

    let tonAmount = usdAmount / currentTonPriceUSD;
    let nanoTon = Math.floor(tonAmount * 1e9).toString(); 
    let projectWallet = "UQAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAJKZ"; // محفظتك

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

// تحويل النقاط
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

// طلب السحب
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

// تشغيل الواجهة المبدئية
updateHeaderBalances();
setTimeout(() => { renderWalletTab(currentWalletTab); }, 100);

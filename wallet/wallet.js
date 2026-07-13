// الأرصدة الوهمية للتجربة
let znBalance = 15400; 
let isWalletConnected = false; // حالة ربط المحفظة

// استرجاع آخر صفحة كان فاتحها اللاعب عشان متتمسحش
let currentWalletTab = localStorage.getItem('lastWalletTab') || 'deposit';

// الدالة الرئيسية لعرض المحتوى
function renderWalletTab(tab) {
    currentWalletTab = tab;
    localStorage.setItem('lastWalletTab', tab); // حفظ الاختيار

    const content = document.getElementById('wallet-content');
    if (!content) return; // حماية لو العنصر لسه محملش
    
    // تظبيط ألوان الأزرار
    const tabs = ['deposit', 'history', 'withdraw'];
    tabs.forEach(t => {
        const btn = document.getElementById(`btn-${t}`);
        if(btn) {
            btn.style.background = (t === tab) ? '#0088cc' : '#222';
        }
    });

    // 1. قسم الإيداع
    if (tab === 'deposit') {
        content.innerHTML = `
            <div style="text-align:center; padding:25px 20px; background:#1c1c1c; border-radius:10px; border:1px solid #333;">
                <p style="margin-bottom:15px; font-size:16px;">إيداع <b>USDT</b> مباشر</p>
                <button onclick="connectTonWallet()" style="width:100%; padding:15px; background:#0088cc; border:none; color:white; border-radius:8px; font-weight:bold; font-size:15px;">اتصال بمحفظة التليجرام (TonConnect)</button>
            </div>`;
    } 
    // 2. قسم السجلات
    else if (tab === 'history') {
        content.innerHTML = `
            <div style="text-align:center; padding:30px 20px; background:#1c1c1c; border-radius:10px; border:1px solid #333; color:#777;">
                لا توجد سجلات حالياً
            </div>`;
    }
    // 3. قسم السحب (فيه التحويل + ربط المحفظة)
    else if (tab === 'withdraw') {
        content.innerHTML = `
            <div>
                <!-- أداة التحويل -->
                <div style="background:#1c1c1c; padding:20px; border-radius:10px; margin-bottom:15px; border:1px solid #333;">
                    <p style="font-size:14px; color:#aaa; margin-bottom:10px; text-align:right;">تحويل ZN إلى USD</p>
                    <input type="number" id="zn-input" placeholder="كمية ZN" style="width:100%; padding:12px; margin-bottom:15px; border-radius:8px; border:none; background:#000; color:#fff; box-sizing:border-box;">
                    <button onclick="convertManualPoints()" style="width:100%; padding:12px; background:#00cc66; color:white; border:none; border-radius:8px; font-weight:bold; font-size:15px;">تحويل النقاط</button>
                </div>

                <!-- أداة السحب -->
                <div style="background:#1c1c1c; padding:20px; border-radius:10px; border:1px solid #333;">
                    <p style="font-size:14px; color:#aaa; margin-bottom:15px; text-align:right;">سحب الأرباح</p>
                    
                    <!-- التحقق من ربط المحفظة -->
                    ${!isWalletConnected ? `
                        <div style="text-align:center; margin-bottom:15px; padding:10px; background:#2a1111; border-radius:8px;">
                            <p style="color:#ff4444; font-size:13px; margin-bottom:10px;">يجب ربط محفظة التليجرام لتتمكن من السحب</p>
                            <button onclick="connectTonWallet()" style="width:100%; padding:10px; background:#0088cc; border:none; color:white; border-radius:8px; font-weight:bold;">ربط المحفظة الآن</button>
                        </div>
                    ` : `
                        <div style="text-align:center; margin-bottom:15px; color:#00cc66; font-size:14px; font-weight:bold;">
                            ✅ المحفظة مربوطة وجاهزة للسحب
                        </div>
                    `}

                    <input type="number" id="usd-withdraw" placeholder="المبلغ للسحب ($)" style="width:100%; padding:12px; margin-bottom:15px; border-radius:8px; border:none; background:#000; color:#fff; box-sizing:border-box;">
                    
                    <!-- زر السحب (يُغلق إذا لم تكن المحفظة مربوطة) -->
                    <button onclick="submitWithdrawal()" style="width:100%; padding:12px; background:${isWalletConnected ? '#ff4444' : '#555'}; border:none; color:white; border-radius:8px; font-weight:bold; font-size:15px;" ${!isWalletConnected ? 'disabled' : ''}>
                        تقديم طلب سحب
                    </button>
                </div>
            </div>`;
    }
}

// دالة التحويل 
function convertManualPoints() {
    let amount = document.getElementById('zn-input').value;
    if (!amount || amount < 5000) {
        alert("الحد الأدنى للتحويل هو 5000 ZN");
        return;
    }
    let usd = (amount / 5000) * 0.01;
    alert("تم تحويل " + amount + " ZN بنجاح إلى " + usd.toFixed(5) + " $");
}

// دالة ربط المحفظة
function connectTonWallet() {
    alert("جارِ فتح محفظة التليجرام (TonConnect)...");
    isWalletConnected = true; 
    renderWalletTab(currentWalletTab); // تحديث الواجهة لفتح زر السحب
}

// دالة السحب
function submitWithdrawal() {
    if (!isWalletConnected) {
        alert("يرجى ربط المحفظة أولاً");
        return;
    }
    let amount = document.getElementById('usd-withdraw').value;
    if (!amount || amount <= 0) {
         alert("يرجى إدخال مبلغ صحيح");
         return;
    }
    alert('تم إرسال طلب سحب بقيمة ' + amount + '$ للمراجعة');
}

// حل مشكلة الشاشة البيضاء - تشغيل الدالة فور تحميل الملف
setTimeout(() => {
    renderWalletTab(currentWalletTab);
}, 100);

// كود ربط المحفظة والتحقق منها
let isWalletConnected = false; // ستتغير قيمتها بعد الربط بـ API التليجرام

function showTab(tab) {
    const content = document.getElementById('wallet-content');
    
    // التبديل بين التبويبات (تحديث الكلاس النشط)
    document.querySelectorAll('button').forEach(btn => btn.classList.remove('active-tab'));
    
    if (tab === 'deposit') {
        content.innerHTML = `
            <div style="text-align:center; padding:20px; background:#1c1c1c; border-radius:10px;">
                ${!isWalletConnected ? `
                    <p style="color:#aaa;">يجب ربط محفظة التليجرام أولاً</p>
                    <button onclick="connectWallet()" style="background:#0088cc; border:none; padding:12px; width:100%; border-radius:5px; color:#fff; font-weight:bold;">ربط المحفظة الآن</button>
                ` : `
                    <p style="color:#00cc66; font-size:14px; margin-bottom:10px;">✅ محفظتك مربوطة بنجاح</p>
                    <p style="font-size:13px; color:#aaa;">أرسل العملات لعنوان المحفظة أدناه، وسيتم إضافتها تلقائياً:</p>
                    <div style="background:#000; padding:15px; margin:15px 0; border-radius:8px; border:1px solid #444; color:#00ff00; font-family:monospace;">UQAm...89xZ</div>
                    <button onclick="copyAddress()" style="background:#444; border:none; padding:8px 20px; border-radius:5px; color:#fff;">نسخ العنوان</button>
                `}
            </div>`;
    } 
    // ... (باقي التبويبات: التاريخ والسحب)
}

function connectWallet() {
    // هنا بيتم ربط API التليجرام
    // بعد نجاح الربط، بنغير الحالة ونعمل Refresh للواجهة
    isWalletConnected = true;
    alert("تم ربط المحفظة بنجاح!");
    showTab('deposit');
}

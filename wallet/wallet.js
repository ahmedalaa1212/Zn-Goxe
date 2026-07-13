let isWalletConnected = false; 

function openWalletTab(tab) {
    const content = document.getElementById('wallet-content');
    const tabs = ['deposit', 'history', 'withdraw'];
    
    // تحديث شكل الأزرار
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-${t}`);
        btn.style.background = (t === tab) ? '#0088cc' : '#222';
    });

    if (tab === 'deposit') {
        content.innerHTML = `
            <div style="text-align:center; padding:20px; background:#1c1c1c; border-radius:10px; border:1px solid #333;">
                ${!isWalletConnected ? 
                    `<p style="color:#aaa;">يجب ربط محفظة التليجرام أولاً</p>
                     <button onclick="connectWallet()" style="background:#0088cc; border:none; padding:12px 30px; border-radius:5px; color:white; cursor:pointer;">ربط المحفظة</button>` 
                    : 
                    `<p style="color:#00cc66;">✅ المحفظة مربوطة</p>
                     <p style="font-size:12px; color:#aaa;">أرسل العملات لهذا العنوان ليتم إضافتها تلقائياً:</p>
                     <div style="background:#000; padding:10px; margin:10px 0; border-radius:5px; color:#00ff00; font-family:monospace;">UQAm...89xZ</div>`
                }
            </div>`;
    } 
    else if (tab === 'history') {
        content.innerHTML = `
            <div style="background:#1c1c1c; padding:15px; border-radius:10px; border:1px solid #333;">
                <div style="display:flex; justify-content:space-between; margin-bottom:10px; font-size:12px; color:#aaa;">
                    <span>العملية</span><span>الحالة</span>
                </div>
                <div style="border-top:1px solid #444; padding-top:10px;">
                    <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                        <span>إيداع</span><span style="color:#00cc66;">مكتمل</span>
                    </div>
                </div>
            </div>`;
    } 
    else if (tab === 'withdraw') {
        content.innerHTML = `
            <div style="text-align:center; padding:20px; background:#1c1c1c; border-radius:10px; border:1px solid #333;">
                <input type="number" placeholder="أدخل المبلغ للسحب" style="width:100%; padding:10px; margin-bottom:15px; border-radius:5px; border:none; background:#000; color:#fff;">
                <button style="width:100%; padding:12px; background:#00cc66; border:none; color:white; border-radius:5px; font-weight:bold;">طلب سحب</button>
            </div>`;
    }
}

function connectWallet() {
    isWalletConnected = true;
    alert("تم ربط المحفظة بنجاح!");
    openWalletTab('deposit');
}

// تحميل الصفحة الافتراضية
openWalletTab('deposit');

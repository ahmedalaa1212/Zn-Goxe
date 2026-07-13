// حفظ حالة الصفحة
let activeTab = localStorage.getItem('lastTab') || 'deposit';

function render(tab = activeTab) {
    activeTab = tab;
    localStorage.setItem('lastTab', tab);
    
    const content = document.getElementById('wallet-content');
    updateButtons(tab);

    if (tab === 'deposit') {
        content.innerHTML = `
            <div style="text-align:center; padding:20px;">
                <p>إيداع عملة <b>USDT</b> عبر الشبكة</p>
                <button onclick="alert('جارِ الربط...')" style="width:100%; padding:15px; background:#0088cc; border:none; color:white; border-radius:8px;">اتصال بمحفظة التليجرام (TonConnect)</button>
            </div>`;
    } 
    else if (tab === 'history') {
        content.innerHTML = `<div style="text-align:center; padding:20px; color:#777;">سجل العمليات فارغ</div>`;
    }
    else if (tab === 'withdraw') {
        content.innerHTML = `
            <div style="padding:20px;">
                <div style="background:#111; padding:15px; border-radius:10px; margin-bottom:15px;">
                    <p style="font-size:12px; color:#aaa;">تحويل ZN إلى USD</p>
                    <input type="number" id="zn-input" placeholder="كمية ZN" style="width:100%; padding:10px; margin:5px 0; border-radius:5px; border:none;">
                    <button onclick="convertManual()" style="width:100%; padding:10px; background:#00cc66; color:white; border:none; border-radius:5px;">تحويل النقاط</button>
                </div>
                <input type="number" id="usd-withdraw" placeholder="المبلغ للسحب ($)" style="width:100%; padding:12px; margin-bottom:10px; border-radius:5px; border:none;">
                <button onclick="alert('تم إرسال طلب السحب للمراجعة')" style="width:100%; padding:12px; background:#ff4444; border:none; color:white; border-radius:5px;">تقديم طلب سحب</button>
            </div>`;
    }
}

function updateButtons(tab) {
    const buttons = { 'deposit': 'btn-deposit', 'history': 'btn-history', 'withdraw': 'btn-withdraw' };
    Object.keys(buttons).forEach(key => {
        document.getElementById(buttons[key]).style.background = (key === tab) ? '#0088cc' : '#222';
    });
}

function convertManual() {
    let amount = document.getElementById('zn-input').value;
    let usd = (amount / 5000) * 0.01;
    alert("تم تحويل " + amount + " ZN إلى " + usd.toFixed(5) + " $");
    // هنا بيتم تحديث الرصيد في قاعدة البيانات
}

// تشغيل عند فتح الصفحة
window.onload = () => render();

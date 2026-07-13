let znBalance = 15400; // مثال

function render(tab) {
    const content = document.getElementById('wallet-content');
    updateActiveButtons(tab);
    
    // معادلة التحويل الدقيقة (13000 -> 0.02600)
    let usdValue = (znBalance / 5000) * 0.01;
    document.getElementById('usd-balance').innerText = usdValue.toFixed(5);

    if (tab === 'deposit') {
        content.innerHTML = `
            <div style="background:#111; padding:20px; border-radius:10px; text-align:center;">
                <p>إيداع <b>USDT</b> مباشر</p>
                <button onclick="tgPay()" style="width:100%; padding:15px; background:#0088cc; border:none; color:white; border-radius:8px; font-weight:bold;">اتصال بمحفظة التليجرام (TonConnect)</button>
            </div>`;
    } 
    else if (tab === 'history') {
        content.innerHTML = `<div style="text-align:center; color:#777;">لا توجد سجلات حالياً</div>`;
    }
    else if (tab === 'withdraw') {
        content.innerHTML = `
            <div style="background:#111; padding:20px; border-radius:10px;">
                <input type="number" id="withdraw-amount" placeholder="المبلغ المراد سحبه بالدولار" style="width:100%; padding:12px; margin-bottom:10px; border-radius:5px; border:none;">
                <button onclick="processWithdraw()" style="width:100%; padding:12px; background:#ff4444; border:none; color:white; border-radius:5px; font-weight:bold;">تقديم طلب سحب</button>
            </div>`;
    }
}

function updateActiveButtons(tab) {
    document.querySelectorAll('.wallet-container button').forEach(btn => btn.style.background = '#222');
    document.getElementById(`btn-${tab}`).style.background = '#0088cc';
}

function tgPay() {
    alert("جارِ فتح محفظة التليجرام لإتمام الإيداع...");
    // هنا بيتم ربط TonConnect SDK
}

// تشغيل الصفحة
render('deposit');

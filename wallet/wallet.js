function openWalletTab(tab) {
    const content = document.getElementById('wallet-content');

    if (tab === 'deposit') {
        content.innerHTML = `
            <div style="background:#111; padding:20px; border-radius:10px; text-align:center;">
                <p>إيداع عملة <b>USDT</b></p>
                <div style="background:#000; padding:10px; border-radius:5px; color:#00ff00;">UQAm...89xZ</div>
                <p style="font-size:11px; color:#aaa; margin-top:10px;">يرجى التحويل من محفظتك المربوطة فقط</p>
            </div>`;
    } 
    else if (tab === 'convert') {
        content.innerHTML = `
            <div style="background:#111; padding:20px; border-radius:10px; text-align:center;">
                <p>كل 5,000 ZN = 0.01$</p>
                <input type="number" id="zn-amount" placeholder="كمية ZN للتحويل" style="width:100%; padding:10px; margin:10px 0;">
                <button onclick="convertZN()" style="width:100%; padding:10px; background:#00cc66; border:none; color:white;">تحويل إلى USD</button>
            </div>`;
    }
    else if (tab === 'withdraw') {
        content.innerHTML = `
            <div style="background:#111; padding:20px; border-radius:10px; text-align:center;">
                <p>سحب رصيد USD</p>
                <input type="number" id="usd-withdraw" placeholder="المبلغ ($)" style="width:100%; padding:10px; margin-bottom:10px;">
                <button style="width:100%; padding:10px; background:#ff4444; border:none; color:white;">سحب إلى محفظة USDT</button>
            </div>`;
    }
}

function convertZN() {
    const zn = document.getElementById('zn-amount').value;
    if(zn >= 5000) {
        const usd = (zn / 5000) * 0.01;
        alert("تم تحويل " + zn + " ZN إلى " + usd.toFixed(2) + "$");
        // هنا بتحدث الرصيد في الـ Database
    } else {
        alert("الحد الأدنى للتحويل 5000 ZN");
    }
}

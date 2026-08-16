window.initWalletView = function() {
    window.onWalletTabOpen();
};

window.onWalletTabOpen = async function() {
    try {
        const res = await window.fetchAPI('/api/wallet/info', 'GET');
        if (res && res.success) {
            const addrDisplay = document.getElementById('wallet-address-display');
            const connBtn = document.getElementById('connect-wallet-btn');
            
            if (res.wallet_address) {
                window.userState.wallet_address = res.wallet_address;
                if (addrDisplay) addrDisplay.innerText = `المحفظة: ${res.wallet_address.substring(0, 6)}...${res.wallet_address.slice(-4)}`;
                if (connBtn) connBtn.innerText = '⚙️ تغيير العنوان';
            } else {
                if (addrDisplay) addrDisplay.innerText = 'لم يتم ربط محفظة TON حتى الآن';
                if (connBtn) connBtn.innerText = '🔗 ربط محفظة TON';
            }
        }
    } catch (err) {
        console.error("خطأ في تحميل بيانات المحفظة:", err);
    }
};

window.handleWalletConnection = async function() {
    const currentAddr = window.userState?.wallet_address || '';
    const newAddr = prompt("أدخل عنوان محفظة TON الخاص بك:", currentAddr);
    
    if (newAddr !== null && newAddr.trim() !== '') {
        try {
            const res = await window.fetchAPI('/api/wallet/save_address', 'POST', { wallet_address: newAddr.trim() });
            if (res && res.success) {
                window.userState.wallet_address = newAddr.trim();
                alert("✅ تم حفظ عنوان المحفظة بنجاح!");
                window.onWalletTabOpen();
            } else {
                alert(res.error || "حدث خطأ أثناء حفظ المحفظة");
            }
        } catch (e) {
            alert("فشل الاتصال بالسيرفر للحفظ.");
        }
    }
};

window.switchWalletSubView = function(sub) {
    const container = document.getElementById('wallet-subview-container');
    if (!container) return;

    if (sub === 'deposit') {
        container.innerHTML = `<div style="padding:5px;"><h4>📥 قسم الإيداع</h4><p style="font-size:12px; color:#aaa;">قم بإرسال TON إلى العنوان المخصص لإعادة شحن رصيدك.</p></div>`;
    } else if (sub === 'withdraw') {
        container.innerHTML = `<div style="padding:5px;"><h4>📤 قسم السحب</h4><p style="font-size:12px; color:#aaa;">الحد الأدنى للسحب هو 1.00 TON.</p></div>`;
    } else if (sub === 'history') {
        container.innerHTML = `<div style="padding:5px;"><h4>📜 سجل المعاملات</h4><p style="font-size:12px; color:#aaa;">لا توجد معاملات سابقة حتى الآن.</p></div>`;
    }
};

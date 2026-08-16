// wallet/wallet.js

const tg = window.Telegram?.WebApp;

// 🎯 تهيئة الشاشة وتوسيعها فور التحميل
document.addEventListener('DOMContentLoaded', () => {
    if (tg) {
        tg.ready();
        tg.expand();
    }
    loadWalletData();
});

// 💳 جلب بيانات المحفظة الرئيسية وتحديث الأرصدة (النقاط + الـ USD)
async function loadWalletData() {
    const initData = tg?.initData || '';
    
    try {
        const response = await fetch('/api/wallet/info', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData })
        });

        const result = await response.json();

        if (result.success && result.wallet) {
            updateUIBalances(result.wallet);
        } else {
            console.warn("⚠️ لم يتم استرجاع بيانات المحفظة:", result.error);
        }
    } catch (error) {
        console.error("❌ خطأ أثناء جلب رصيد المحفظة:", error);
    }
}

// 🔢 تحديث الأرقام على الواجهة
function updateUIBalances(wallet) {
    const coinElem = document.getElementById('coin-balance');
    const usdElem = document.getElementById('usd-balance');

    if (coinElem) {
        coinElem.innerText = Number(wallet.balance || 0).toLocaleString('en-US');
    }
    if (usdElem) {
        usdElem.innerText = '$' + Number(wallet.usd_balance || 0).toFixed(2);
    }
}

// 🔘 التبديل بين الخيارات الثلاثة (إيداع - سحب - سجلات)
function switchTab(tabName) {
    // إلغاء تفعيل كافة الأزرار والأقسام
    document.querySelectorAll('.btn-tab').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.content-section').forEach(sec => sec.classList.remove('active'));

    // تفعيل الزر والقسم المختار
    const activeBtn = document.querySelector(`.btn-tab[onclick*="${tabName}"]`);
    const activeSec = document.getElementById(`${tabName}-section`);

    if (activeBtn) activeBtn.classList.add('active');
    if (activeSec) activeSec.classList.add('active');

    // تحميل محتوى القسم
    if (tabName === 'deposit') loadDepositData();
    if (tabName === 'withdraw') loadWithdrawData();
    if (tabName === 'history') loadHistoryData();
}

// 📥 تحميل بيانات قسم الإيداع
async function loadDepositData() {
    const container = document.getElementById('deposit-options');
    if (!container) return;

    try {
        const response = await fetch('/api/wallet/deposit/', { method: 'GET' });
        const data = await response.json();

        if (data.success && data.methods && data.methods.length > 0) {
            container.innerHTML = data.methods.map(m => `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #0f172a; border-radius: 10px; margin-bottom: 8px;">
                    <span>${m.name}</span>
                    <button onclick="initDeposit('${m.id}')" style="padding: 6px 12px; background: #10b981; color: #fff; border: none; border-radius: 6px; font-weight: bold; cursor: pointer;">شحن</button>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<div class="empty-msg">وسائل الإيداع المتاحة ستظهر هنا قريباً.</div>';
        }
    } catch (e) {
        container.innerHTML = '<div class="empty-msg">وسائل الشحن التلقائي قيد التجهيز.</div>';
    }
}

// 📤 تحميل واجهة تقديم طلب السحب
async function loadWithdrawData() {
    const container = document.getElementById('withdraw-form');
    if (!container) return;

    container.innerHTML = `
        <div style="display: flex; flex-direction: column; gap: 10px;">
            <input type="number" id="withdraw-amount" placeholder="المبلغ المراد سحبه ($)" style="padding: 12px; border-radius: 10px; border: 1px solid var(--border-color); background: #0f172a; color: #fff; font-size: 14px;">
            <input type="text" id="withdraw-address" placeholder="عنوان المحفظة (TON / Wallet Address)" style="padding: 12px; border-radius: 10px; border: 1px solid var(--border-color); background: #0f172a; color: #fff; font-size: 14px;">
            <button onclick="submitWithdraw()" style="padding: 12px; background: #2563eb; color: #fff; border: none; border-radius: 10px; font-weight: bold; cursor: pointer; font-size: 14px;">تأكيد طلب السحب</button>
        </div>
    `;
}

// 📜 تحميل سجل العمليات
async function loadHistoryData() {
    const container = document.getElementById('history-list');
    if (!container) return;

    try {
        const initData = tg?.initData || '';
        const response = await fetch('/api/wallet/history/', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData })
        });
        const data = await response.json();

        if (data.success && data.history && data.history.length > 0) {
            container.innerHTML = data.history.map(item => `
                <div style="display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--border-color); font-size: 13px;">
                    <span>${item.type === 'deposit' ? '📥 إيداع' : '📤 سحب'}</span>
                    <span style="font-weight: bold;">${item.amount}</span>
                    <span style="color: ${item.status === 'completed' ? 'var(--accent-green)' : 'var(--accent-gold)'};">${item.status}</span>
                </div>
            `).join('');
        } else {
            container.innerHTML = '<div class="empty-msg">لا توجد سجلات عمليات سابقة.</div>';
        }
    } catch (e) {
        container.innerHTML = '<div class="empty-msg">لا توجد عمليات سابقة حتى الآن.</div>';
    }
}

// ⚡ إرسال طلب السحب إلى الـ Backend
async function submitWithdraw() {
    const amount = document.getElementById('withdraw-amount')?.value;
    const address = document.getElementById('withdraw-address')?.value;

    if (!amount || !address) {
        const msg = "يرجى إدخال المبلغ وعنوان المحفظة بشكل صحيح!";
        if (tg) tg.showAlert(msg); else alert(msg);
        return;
    }

    try {
        const response = await fetch('/api/wallet/withdraw/request', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                initData: tg?.initData || '',
                amount: parseFloat(amount),
                address: address
            })
        });
        const res = await response.json();

        if (res.success) {
            const msg = "تم تقديم طلب السحب بنجاح!";
            if (tg) tg.showAlert(msg); else alert(msg);
            loadWalletData();
        } else {
            const msg = res.error || "فشل إرسال طلب السحب";
            if (tg) tg.showAlert(msg); else alert(msg);
        }
    } catch (err) {
        console.error("❌ Withdraw error:", err);
    }
}

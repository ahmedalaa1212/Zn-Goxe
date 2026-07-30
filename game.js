/* ==========================================
   1. Initial Setup & Telegram WebApp Bridge
   ========================================== */
const tg = window.Telegram?.WebApp;

if (tg) {
    tg.ready();
    tg.expand();
    if (tg.enableClosingConfirmation) {
        tg.enableClosingConfirmation();
    }
    // ضبط ألوان الشريط العلوي لمنح مظهراً متناسقاً
    if (tg.setHeaderColor) {
        tg.setHeaderColor('secondary_bg_color');
    }
}

// Global App State
let userState = {
    tg_id: null,
    first_name: "لاعب",
    balance: 0.0,
    usd_balance: 0.0,
    ad_balance: 0.0,
    hourly_rate: 0.0,
    mining_level: 1,
    wallet_address: null
};

/* ==========================================
   2. API Communication Utility
   ========================================== */
async function fetchAPI(endpoint, method = 'GET', bodyData = null) {
    const headers = {
        'Content-Type': 'application/json'
    };

    if (tg && tg.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData;
    }

    const options = { method, headers };
    if (bodyData) {
        options.body = JSON.stringify(bodyData);
    }

    try {
        const response = await fetch(endpoint, options);
        const result = await response.json();
        
        if (!response.ok) {
            if (response.status === 403 && result.error?.includes("محظور")) {
                alert("تم حظر حسابك من استخدام التطبيق.");
                if (tg) tg.close();
            }
            throw new Error(result.error || `Error HTTP ${response.status}`);
        }
        return result;
    } catch (err) {
        console.error(`[API Error] Path: ${endpoint} ->`, err);
        throw err;
    }
}

/* ==========================================
   3. UI Builders & Formatters
   ========================================== */
function formatNumber(num, decimals = 2) {
    const val = parseFloat(num);
    if (isNaN(val)) return "0.00";
    return val.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals
    });
}

function updateUI() {
    // تحديث الأرصدة في الواجهة
    const balanceEl = document.getElementById('user-balance');
    const usdEl = document.getElementById('user-usd-balance');
    const hourlyEl = document.getElementById('hourly-rate');

    if (balanceEl) balanceEl.innerText = formatNumber(userState.balance, 0);
    if (usdEl) usdEl.innerText = `$${formatNumber(userState.usd_balance, 4)}`;
    if (hourlyEl) hourlyEl.innerText = `+${formatNumber(userState.hourly_rate, 0)}/h`;
}

/* ==========================================
   4. Core Game & Wallet Actions
   ========================================== */

// 1. تحميل سجل المحفظة (Wallet History)
async function loadWalletHistory() {
    const historyList = document.getElementById('wallet-history-list');
    if (!historyList) return;

    historyList.innerHTML = `<div class="loading-spinner">جاري تحميل السجلات...</div>`;

    try {
        const data = await fetchAPI('/api/wallet/get_history');
        if (data.success && Array.isArray(data.history)) {
            if (data.history.length === 0) {
                historyList.innerHTML = `<div class="empty-msg">لا توجد معاملات سابقة حتى الآن.</div>`;
                return;
            }

            let html = '';
            data.history.forEach(tx => {
                let badgeClass = 'bg-secondary';
                let txTitle = 'عملية';
                let amountText = '';

                if (tx.type === 'withdraw') {
                    badgeClass = tx.status === 'completed' ? 'badge-success' : (tx.status === 'pending' ? 'badge-warning' : 'badge-danger');
                    txTitle = 'سحب أرباح';
                    amountText = `-$${formatNumber(tx.amount_usd || 0, 2)}`;
                } else if (tx.type === 'deposit') {
                    badgeClass = 'badge-success';
                    txTitle = 'إيداع رصيد';
                    amountText = `+$${formatNumber(tx.amount_usd || tx.gross_amount_usd || 0, 2)}`;
                } else if (tx.type === 'convert') {
                    badgeClass = 'badge-info';
                    txTitle = 'تحويل ZN إلى USD';
                    amountText = `+$${formatNumber(tx.amount_usd || 0, 4)}`;
                }

                const dateStr = tx.created_at ? new Date(tx.created_at).toLocaleString('ar-EG') : 'الآن';

                html += `
                    <div class="history-item">
                        <div class="history-info">
                            <span class="history-title">${txTitle}</span>
                            <span class="history-date">${dateStr}</span>
                        </div>
                        <div class="history-amount">
                            <span class="amount-text">${amountText}</span>
                            <span class="badge ${badgeClass}">${tx.status || 'مكتمل'}</span>
                        </div>
                    </div>
                `;
            });
            historyList.innerHTML = html;
        } else {
            historyList.innerHTML = `<div class="error-msg">فشل في جلب السجلات.</div>`;
        }
    } catch (e) {
        historyList.innerHTML = `<div class="error-msg">${e.message || 'خطأ في الاتصال بالشبكة'}</div>`;
    }
}

// 2. تحويل نقاط ZN إلى USD
async function executeConvertZN(amount) {
    try {
        const res = await fetchAPI('/api/wallet/wallet_convert', 'POST', { amount: parseFloat(amount) });
        if (res.success) {
            userState.usd_balance = res.new_usd_balance;
            userState.balance = res.new_balance;
            updateUI();
            alert(`تم تحويل ${formatNumber(amount, 0)} ZN بنجاح إلى $${formatNumber(res.usd_gained, 4)}!`);
            loadWalletHistory();
        }
    } catch (e) {
        alert(`فشل التحويل: ${e.message}`);
    }
}

// 3. طلب سحب USD
async function executeWithdraw(amountUSD, address) {
    try {
        const res = await fetchAPI('/api/wallet/wallet_withdraw', 'POST', { 
            amount: parseFloat(amountUSD), 
            walletAddress: address 
        });
        if (res.success) {
            userState.usd_balance = res.new_usd_balance;
            updateUI();
            alert(`تم إرسال طلب السحب بنجاح وهي قيد المعالجة!`);
            loadWalletHistory();
        }
    } catch (e) {
        alert(`فشل السحب: ${e.message}`);
    }
}

// 4. إرسال تقرير إيداع TON
async function executeDepositReport(usdAmount, tonAmount, boc) {
    try {
        const res = await fetchAPI('/api/wallet/wallet_deposit_report', 'POST', {
            usdAmount: parseFloat(usdAmount),
            tonAmount: parseFloat(tonAmount),
            boc: boc
        });
        if (res.success) {
            userState.usd_balance = res.new_usd_balance;
            updateUI();
            alert(`تم تأكيد الإيداع وإضافة $${formatNumber(res.net_usd_credited, 2)} لرصيدك!`);
            loadWalletHistory();
        }
    } catch (e) {
        alert(`خطأ أثناء تأكيد الإيداع: ${e.message}`);
    }
}

/* ==========================================
   5. Initialization Listener
   ========================================== */
document.addEventListener('DOMContentLoaded', () => {
    updateUI();
    
    // ربط زر المحفظة أو السجلات في حال كان موجوداً في الصفحة
    const historyBtn = document.getElementById('open-history-btn');
    if (historyBtn) {
        historyBtn.addEventListener('click', loadWalletHistory);
    }
});

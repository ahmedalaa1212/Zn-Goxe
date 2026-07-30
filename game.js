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
    if (tg.setHeaderColor) {
        tg.setHeaderColor('secondary_bg_color');
    }
}

// Global App State - كائن بيانات المستخدم الموحد
window.userState = {
    tg_id: null,
    first_name: "لاعب",
    balance: 0.0,
    usd_balance: 0.0,
    ad_balance: 0.0,
    hourly_rate: 0.0,
    mining_level: 1,
    storage_level: 1,
    upgrades: {},
    wallet_address: null
};

// استرجاع البيانات المخزنة محلياً فوراً لمنع اختفاء الرصيد أثناء التحميل
function loadLocalState() {
    try {
        const saved = localStorage.getItem('app_user_state');
        if (saved) {
            const parsed = JSON.parse(saved);
            window.userState = { ...window.userState, ...parsed };
        }
    } catch (e) {
        console.error("Error loading local state", e);
    }
}

// حفظ البيانات محلياً
function saveLocalState() {
    try {
        localStorage.setItem('app_user_state', JSON.stringify(window.userState));
    } catch (e) {
        console.error("Error saving local state", e);
    }
}

loadLocalState(); // تشغيل فوري

/* ==========================================
   2. API Communication Utility
   ========================================== */
async function fetchAPI(endpoint, method = 'GET', bodyData = null) {
    const headers = {
        'Content-Type': 'application/json'
    };

    if (tg && tg.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData;
        headers['Authorization'] = `Bearer ${tg.initData}`;
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

window.updateUI = function() {
    // تحديث الأرصدة في أي واجهة تحتوي على هذه الـ IDs
    const balanceEl = document.getElementById('user-balance') || document.getElementById('shop-balance-text');
    const usdEl = document.getElementById('user-usd-balance') || document.getElementById('shop-usd-text');
    const hourlyEl = document.getElementById('hourly-rate') || document.getElementById('shop-rate-text');

    if (balanceEl) balanceEl.innerText = formatNumber(window.userState.balance, 0);
    if (usdEl) usdEl.innerText = `$${formatNumber(window.userState.usd_balance, 4)}`;
    if (hourlyEl) hourlyEl.innerText = `+${formatNumber(window.userState.hourly_rate, 0)}/h`;

    // استدعاء تحديث المتجر إذا كنا في صفحة المتجر
    if (typeof window.updateShopUI === 'function') {
        window.updateShopUI();
    }
};

/* ==========================================
   4. Fetch Latest User Data from Server
   ========================================== */
window.loadUserData = async function() {
    if (!tg || !tg.initData) return;

    try {
        // جلب بيانات الحساب المحدثة من السيرفر
        const data = await fetchAPI('/api/user/info');
        if (data && data.success) {
            window.userState.balance = parseFloat(data.balance ?? window.userState.balance);
            window.userState.usd_balance = parseFloat(data.usd_balance ?? window.userState.usd_balance);
            window.userState.hourly_rate = parseFloat(data.hourly_rate ?? window.userState.hourly_rate);
            window.userState.storage_level = parseInt(data.storage_level ?? window.userState.storage_level);
            window.userState.upgrades = data.upgrades || window.userState.upgrades;
            window.userState.wallet_address = data.wallet_address || window.userState.wallet_address;

            saveLocalState();
            window.updateUI();
        }
    } catch (e) {
        console.log("استخدام البيانات المحلية المسجلة مسبقاً لحين توفر الاتصال.");
        window.updateUI();
    }
};

/* ==========================================
   5. Actions (Convert, Withdraw, Deposit)
   ========================================== */
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

async function executeConvertZN(amount) {
    try {
        const res = await fetchAPI('/api/wallet/wallet_convert', 'POST', { amount: parseFloat(amount) });
        if (res.success) {
            window.userState.usd_balance = res.new_usd_balance;
            window.userState.balance = res.new_balance;
            saveLocalState();
            window.updateUI();
            alert(`تم تحويل ${formatNumber(amount, 0)} ZN بنجاح إلى $${formatNumber(res.usd_gained, 4)}!`);
            loadWalletHistory();
        }
    } catch (e) {
        alert(`فشل التحويل: ${e.message}`);
    }
}

async function executeWithdraw(amountUSD, address) {
    try {
        const res = await fetchAPI('/api/wallet/wallet_withdraw', 'POST', { 
            amount: parseFloat(amountUSD), 
            walletAddress: address 
        });
        if (res.success) {
            window.userState.usd_balance = res.new_usd_balance;
            saveLocalState();
            window.updateUI();
            alert(`تم إرسال طلب السحب بنجاح وهي قيد المعالجة!`);
            loadWalletHistory();
        }
    } catch (e) {
        alert(`فشل السحب: ${e.message}`);
    }
}

/* ==========================================
   6. Initialization Listener
   ========================================== */
document.addEventListener('DOMContentLoaded', () => {
    window.updateUI();
    window.loadUserData(); // جلب البيانات الحقيقية فور تحميل الصفحة
    
    const historyBtn = document.getElementById('open-history-btn');
    if (historyBtn) {
        historyBtn.addEventListener('click', loadWalletHistory);
    }
});

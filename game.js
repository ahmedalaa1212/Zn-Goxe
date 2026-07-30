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

// الكائن الداخلي للبيانات
const rawUserState = {
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

// حفظ البيانات محلياً
function saveLocalState() {
    try {
        localStorage.setItem('app_user_state', JSON.stringify(window.userState));
    } catch (e) {
        console.error("Error saving local state", e);
    }
}

// إنشاء Proxy ذكي لـ window.userState لتحديث الشاشات فور تغيير أي قيمة من أي ملف آخر
window.userState = new Proxy(rawUserState, {
    set(target, prop, value) {
        target[prop] = value;
        if (['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'mining_level', 'storage_level'].includes(prop)) {
            saveLocalState();
            if (typeof window.updateUI === 'function') {
                window.updateUI();
            }
        }
        return true;
    }
});

// استرجاع البيانات المخزنة محلياً فوراً لمنع اختفاء الرصيد أثناء التحميل
function loadLocalState() {
    try {
        const saved = localStorage.getItem('app_user_state');
        if (saved) {
            const parsed = JSON.parse(saved);
            Object.assign(rawUserState, parsed);
        }
    } catch (e) {
        console.error("Error loading local state", e);
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
    const znFormatted = formatNumber(window.userState.balance, 0);
    const usdFormatted = `$${formatNumber(window.userState.usd_balance, 4)}`;
    const hourlyFormatted = `+${formatNumber(window.userState.hourly_rate, 0)}/h`;

    // قائمة بجميع الـ IDs للرصيد ZN عبر كافة القوائم (الرئيسية، المتجر، المهمات، المحفظة)
    const znElementIds = [
        'user-balance', 
        'shop-balance-text', 
        'top-zn-balance', 
        'wallet-zn-balance', 
        'task-zn-balance', 
        'farm-zn-balance',
        'zn-balance'
    ];

    znElementIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            if (el.tagName === 'INPUT') el.value = znFormatted;
            else el.innerText = znFormatted;
        }
    });

    // تحديث بالـ Class لضمان تغطية أية عناصر إضافية
    document.querySelectorAll('.zn-balance-display').forEach(el => {
        el.innerText = znFormatted;
    });

    // قائمة بجميع الـ IDs للرصيد USD عبر كافة القوائم
    const usdElementIds = [
        'user-usd-balance', 
        'shop-usd-text', 
        'top-usd-balance', 
        'wallet-usd-balance', 
        'usd-balance'
    ];

    usdElementIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            if (el.tagName === 'INPUT') el.value = usdFormatted;
            else el.innerText = usdFormatted;
        }
    });

    document.querySelectorAll('.usd-balance-display').forEach(el => {
        el.innerText = usdFormatted;
    });

    // قائمة بجميع الـ IDs لمعدل السرعة hourly_rate
    const hourlyElementIds = [
        'hourly-rate', 
        'shop-rate-text', 
        'user-hourly-rate', 
        'farm-rate-text'
    ];

    hourlyElementIds.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            if (el.tagName === 'INPUT') el.value = hourlyFormatted;
            else el.innerText = hourlyFormatted;
        }
    });

    // استدعاء دالة تحديث المتجر إذا كانت معرفة في ملف shop.js
    if (typeof window.updateShopUI === 'function') {
        window.updateShopUI();
    }

    // استدعاء دالة تحديث المهمات إذا كانت معرفة في ملف tasks.js
    if (typeof window.renderTasks === 'function') {
        window.renderTasks();
    }
};

/* ==========================================
   4. Fetch Latest User Data from Server
   ========================================== */
let isUserDataFetching = false;

window.loadUserData = async function() {
    if (!tg || !tg.initData) return;
    if (isUserDataFetching) return; 

    isUserDataFetching = true;

    try {
        // جلب بيانات الحساب المحدثة من السيرفر
        const data = await fetchAPI('/api/user/info');
        if (data && data.success) {
            // تحديث القيم مباشرة لتفعيل الـ Proxy والتحديث اللحظي
            if (data.balance !== undefined) window.userState.balance = parseFloat(data.balance);
            if (data.usd_balance !== undefined) window.userState.usd_balance = parseFloat(data.usd_balance);
            if (data.hourly_rate !== undefined) window.userState.hourly_rate = parseFloat(data.hourly_rate);
            if (data.storage_level !== undefined) window.userState.storage_level = parseInt(data.storage_level);
            if (data.upgrades !== undefined) window.userState.upgrades = data.upgrades;
            if (data.wallet_address !== undefined) window.userState.wallet_address = data.wallet_address;

            saveLocalState();
            window.updateUI();
        }
    } catch (e) {
        console.log("استخدام البيانات المحلية المسجلة مسبقاً لحين توفر الاتصال.");
        window.updateUI();
    } finally {
        isUserDataFetching = false;
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
   6. Realtime Auto-Sync & Event Listeners
   ========================================== */
document.addEventListener('DOMContentLoaded', () => {
    window.updateUI();
    window.loadUserData(); // جلب البيانات الحقيقية فور تحميل الصفحة
    
    const historyBtn = document.getElementById('open-history-btn');
    if (historyBtn) {
        historyBtn.addEventListener('click', loadWalletHistory);
    }

    // 1. مزامنة تلقائية حية كل 4 ثوانٍ لضمان استقبال أية نقاط أضيفت من السيرفر أو البوت بدون إغلاق التطبيق
    setInterval(() => {
        window.loadUserData();
    }, 4000);

    // 2. مزامنة فورية بمجرد عودة المستخدم لشاشة التطبيق
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            window.loadUserData();
        }
    });
});

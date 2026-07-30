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

// إنشاء Proxy ذكي لـ window.userState لتحديث الشاشات فور تغيير أي قيمة من أي ملف آخر أو من السيرفر
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
   3. UI Builders & Formatters (The Ultimate Fix)
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
    // تجهيز الأرقام المنسقة
    const rawBalance = window.userState.balance;
    const rawUsd = window.userState.usd_balance;
    
    const znFormatted = formatNumber(rawBalance, 0); 
    const usdFormatted = formatNumber(rawUsd, 4);
    const hourlyFormatted = `+${formatNumber(window.userState.hourly_rate, 0)}/h`;

    // 1. تحديث رصيد ZN في كل الصفحات (حتى لو الـ ID متكرر)
    const znSelectors = [
        '[id="user-balance"]', '[id="shop-balance-text"]', 
        '[id="top-zn-balance"]', '[id="wallet-zn-balance"]', 
        '[id="task-zn-balance"]', '[id="farm-zn-balance"]',
        '[id="zn-balance"]', '.zn-balance-display', '.balance-text'
    ];

    znSelectors.forEach(selector => {
        document.querySelectorAll(selector).forEach(el => {
            if (el.tagName === 'INPUT') {
                el.value = znFormatted;
            } else {
                // الحفاظ على كلمة ZN لو موجودة داخل العنصر لتطابق الصور
                const currentText = el.innerText || "";
                if (currentText.includes('رصيد ZN:')) {
                    el.innerText = `رصيد ZN: ${znFormatted}`;
                } else if (currentText.includes('ZN:')) {
                    el.innerText = `ZN: ${znFormatted}`;
                } else if (currentText.includes('ZN ')) {
                    el.innerText = `ZN ${znFormatted}`;
                } else {
                    el.innerText = znFormatted;
                }
            }
        });
    });

    // 2. تحديث رصيد USD في المحفظة والمتجر معاً وبدون تعليق
    const usdSelectors = [
        '[id="user-usd-balance"]', '[id="shop-usd-text"]', 
        '[id="wallet-usd-balance"]', '[id="usd-balance"]', 
        '.usd-balance-display'
    ];

    usdSelectors.forEach(selector => {
        document.querySelectorAll(selector).forEach(el => {
            if (el.tagName === 'INPUT') {
                el.value = usdFormatted;
            } else {
                const currentText = el.innerText || "";
                // لو العنصر فيه علامة الدولار مسبقاً بنحافظ عليها
                if (currentText.includes('$')) {
                    el.innerText = `$${usdFormatted}`;
                } else if (currentText.includes('USD')) {
                    el.innerText = `USD $${usdFormatted}`;
                } else {
                    el.innerText = `$${usdFormatted}`; // الشكل الافتراضي
                }
            }
        });
    });

    // 3. تحديث سرعة التعدين في كل مكان
    const hourlySelectors = [
        '[id="hourly-rate"]', '[id="shop-rate-text"]', 
        '[id="user-hourly-rate"]', '[id="farm-rate-text"]',
        '.hourly-rate-display'
    ];

    hourlySelectors.forEach(selector => {
        document.querySelectorAll(selector).forEach(el => {
            if (el.tagName === 'INPUT') {
                el.value = hourlyFormatted;
            } else {
                // حسب تصميمك في الصور، السرعة تظهر بالشكل التالي
                el.innerText = `h/${formatNumber(window.userState.hourly_rate, 0)}`;
            }
        });
    });

    // استدعاء الدوال الفرعية لو موجودة
    if (typeof window.updateShopUI === 'function') {
        window.updateShopUI();
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
        const data = await fetchAPI('/api/user/info');
        if (data && data.success) {
            // التعديل هنا سيطلق الـ Proxy ويحدث كل الشاشات فوراً
            if (data.balance !== undefined) window.userState.balance = parseFloat(data.balance);
            if (data.usd_balance !== undefined) window.userState.usd_balance = parseFloat(data.usd_balance);
            if (data.hourly_rate !== undefined) window.userState.hourly_rate = parseFloat(data.hourly_rate);
            if (data.storage_level !== undefined) window.userState.storage_level = parseInt(data.storage_level);
            if (data.upgrades !== undefined) window.userState.upgrades = data.upgrades;
            if (data.wallet_address !== undefined) window.userState.wallet_address = data.wallet_address;
        }
    } catch (e) {
        console.log("استخدام البيانات المحلية المسجلة مسبقاً لحين توفر الاتصال.");
        window.updateUI(); // استدعاء احتياطي
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
    window.updateUI(); // تحديث أولي سريع 
    window.loadUserData(); // جلب البيانات الحقيقية من السيرفر
    
    const historyBtn = document.getElementById('open-history-btn');
    if (historyBtn) {
        historyBtn.addEventListener('click', loadWalletHistory);
    }

    // مزامنة تلقائية حية كل 4 ثوانٍ لضمان استقبال أية نقاط أضيفت من الفايربيس، البوت أو السيرفر
    setInterval(() => {
        window.loadUserData();
    }, 4000);

    // مزامنة فورية بمجرد أن يفتح المستخدم التطبيق أو يرجع له من شاشة أخرى
    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            window.loadUserData();
        }
    });
});

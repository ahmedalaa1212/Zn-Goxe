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

function saveLocalState() {
    try {
        localStorage.setItem('app_user_state', JSON.stringify(window.userState));
    } catch (e) {}
}

// ==========================================
// Proxy الذكي والمحدث (القلب النابض للتطبيق)
// أي تغيير للرصيد في *أي* ملف أو ميزة (مزرعة، مهام، هدية، إحالة)
// سيقوم الـ Proxy تلقائياً بتحديث واجهة التطبيق بالكامل فوراً.
// ==========================================
window.userState = new Proxy(rawUserState, {
    set(target, prop, value) {
        target[prop] = value;
        // لو اتغير الرصيد، الدولار، أو سرعة التعدين من أي حتة في التطبيق
        if (['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'mining_level', 'storage_level'].includes(prop)) {
            saveLocalState();
            if (typeof window.updateUI === 'function') {
                window.updateUI();
            }
        }
        return true;
    }
});

function loadLocalState() {
    try {
        const saved = localStorage.getItem('app_user_state');
        if (saved) {
            Object.assign(rawUserState, JSON.parse(saved));
        }
    } catch (e) {}
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
window.updateUI = function() {
    try {
        const rawBalance = parseFloat(window.userState.balance || 0);
        const rawUsd = parseFloat(window.userState.usd_balance || 0);
        const rawRate = parseFloat(window.userState.hourly_rate || 0);
        
        const znFormatted = rawBalance.toLocaleString('en-US', {maximumFractionDigits: 0});
        const usdFormatted = rawUsd.toLocaleString('en-US', {minimumFractionDigits: 4, maximumFractionDigits: 4});
        const hourlyFormatted = rawRate.toLocaleString('en-US', {maximumFractionDigits: 0});

        // 1. تحديث رصيد ZN في كل الصفحات والقوائم بدون استثناء
        const allZnElements = document.querySelectorAll('[id*="balance"], [id*="zn"], .zn-balance, .balance-text');
        allZnElements.forEach(el => {
            if (el.tagName === 'INPUT') {
                el.value = znFormatted;
                return;
            }
            const text = el.innerText || "";
            if (text.includes('ZN') || el.id.includes('zn-balance') || el.id === 'user-balance' || el.id.includes('shop-balance')) {
                if (text.includes('رصيد ZN:')) el.innerText = `رصيد ZN: ${znFormatted}`;
                else if (text.includes('ZN:')) el.innerText = `ZN: ${znFormatted}`;
                else if (text.includes('ZN ')) el.innerText = `ZN ${znFormatted}`;
                else if (!text.includes('$') && !text.includes('USD')) el.innerText = znFormatted;
            }
        });

        // 2. تحديث رصيد USD
        const allUsdElements = document.querySelectorAll('[id*="usd"], .usd-balance');
        allUsdElements.forEach(el => {
            if (el.tagName === 'INPUT') {
                el.value = usdFormatted;
                return;
            }
            const text = el.innerText || "";
            if (text.includes('$') || text.includes('USD') || el.id.includes('usd')) {
                if (text.includes('USD $')) el.innerText = `USD $${usdFormatted}`;
                else el.innerText = `$${usdFormatted}`; 
            }
        });

        // 3. تحديث سرعة التعدين
        const allRateElements = document.querySelectorAll('[id*="rate"], [id*="speed"], [id*="hourly"]');
        allRateElements.forEach(el => {
            if (el.tagName === 'INPUT') {
                el.value = hourlyFormatted;
                return;
            }
            const text = el.innerText || "";
            if (text.includes('h/')) el.innerText = `h/${hourlyFormatted}`;
        });

        if (typeof window.updateShopUI === 'function') {
            window.updateShopUI();
        }
    } catch (error) {
        console.error("خطأ صامت في تحديث الواجهة لن يؤثر على المهام:", error);
    }
};

/* ==========================================
   4. Fetch Latest User Data from Server
   ========================================== */
let isUserDataFetching = false;

window.loadUserData = async function() {
    if (!tg || !tg.initData || isUserDataFetching) return;
    isUserDataFetching = true;

    try {
        const data = await fetchAPI('/api/user/info');
        if (data && data.success) {
            // تحديث القيم هنا سيقوم بتشغيل الProxy تلقائياً لتحديث كل الشاشات
            if (data.balance !== undefined) window.userState.balance = parseFloat(data.balance);
            if (data.usd_balance !== undefined) window.userState.usd_balance = parseFloat(data.usd_balance);
            if (data.hourly_rate !== undefined) window.userState.hourly_rate = parseFloat(data.hourly_rate);
            if (data.storage_level !== undefined) window.userState.storage_level = parseInt(data.storage_level);
            if (data.upgrades !== undefined) window.userState.upgrades = data.upgrades;
            if (data.wallet_address !== undefined) window.userState.wallet_address = data.wallet_address;
        }
    } catch (e) {
        console.log("استخدام البيانات المحلية لحين توفر الاتصال.");
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
                    amountText = `-$${(parseFloat(tx.amount_usd) || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}`;
                } else if (tx.type === 'deposit') {
                    badgeClass = 'badge-success';
                    txTitle = 'إيداع رصيد';
                    amountText = `+$${(parseFloat(tx.amount_usd || tx.gross_amount_usd) || 0).toLocaleString('en-US', {minimumFractionDigits: 2})}`;
                } else if (tx.type === 'convert') {
                    badgeClass = 'badge-info';
                    txTitle = 'تحويل ZN إلى USD';
                    amountText = `+$${(parseFloat(tx.amount_usd) || 0).toLocaleString('en-US', {minimumFractionDigits: 4})}`;
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
            // التعديل هنا هيحدث الواجهة في كل التطبيق تلقائياً عبر الـ Proxy
            window.userState.usd_balance = res.new_usd_balance;
            window.userState.balance = res.new_balance;
            alert(`تم تحويل ${parseFloat(amount).toLocaleString()} ZN بنجاح إلى $${parseFloat(res.usd_gained).toLocaleString('en-US', {minimumFractionDigits:4})}!`);
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
    window.updateUI(); 
    window.loadUserData(); 
    
    const historyBtn = document.getElementById('open-history-btn');
    if (historyBtn) {
        historyBtn.addEventListener('click', loadWalletHistory);
    }

    // مزامنة دورية لضمان جلب أي رصيد زاد من المهام، الإحالات، أو البوت الخارجي
    setInterval(() => {
        window.loadUserData();
    }, 5000); 

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            window.loadUserData();
        }
    });
});

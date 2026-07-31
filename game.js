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

// الكائن الداخلي للبيانات الموحدة
const rawUserState = {
    tg_id: null,
    first_name: "لاعب",
    balance: 0.0,
    usd_balance: 0.0,
    ad_balance: 0.0,
    hourly_rate: 0.0,
    energy: 100.0,
    mining_level: 1,
    storage_level: 1,
    upgrades: {},
    wallet_address: null
};

function saveLocalState() {
    try {
        localStorage.setItem('app_user_state', JSON.stringify(window.userState));
        localStorage.setItem('zn_balance', window.userState.balance.toString());
        localStorage.setItem('zngoxe_balance', window.userState.balance.toString());
        localStorage.setItem('zngoxe_usd_balance', window.userState.usd_balance.toString());
        localStorage.setItem('zngoxe_hourly_rate', window.userState.hourly_rate.toString());
    } catch (e) {
        console.warn("تعذر الحفظ في LocalStorage", e);
    }
}

function loadLocalState() {
    try {
        const saved = localStorage.getItem('app_user_state');
        if (saved) {
            const parsed = JSON.parse(saved);
            Object.assign(rawUserState, parsed);
        }
    } catch (e) {
        console.warn("تعذر تحميل البيانات المحلية", e);
    }
}

loadLocalState(); 

// ==========================================
// Proxy الذكي واللحظي
// ==========================================
window.userState = new Proxy(rawUserState, {
    set(target, prop, value) {
        const numericProps = ['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'energy', 'mining_level', 'storage_level'];
        if (numericProps.includes(prop)) {
            target[prop] = parseFloat(value) || 0;
        } else {
            target[prop] = value;
        }
        
        saveLocalState();
        
        if (typeof window.updateUI === 'function') {
            window.updateUI();
        }

        window.dispatchEvent(new CustomEvent('userStateUpdated', {
            detail: { prop, value: target[prop], state: target }
        }));

        return true;
    }
});

/* ==========================================
   2. API Communication Utility
   ========================================== */
window.fetchAPI = async function(endpoint, method = 'GET', bodyData = null) {
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
            if (response.status === 403 && result.error && result.error.includes("محظور")) {
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
};

/* ==========================================
   3. UI Builders & Formatters
   ========================================== */
window.updateUI = function() {
    try {
        const rawBalance = parseFloat(window.userState.balance || 0);
        const rawUsd = parseFloat(window.userState.usd_balance || 0);
        const rawAd = parseFloat(window.userState.ad_balance || 0);
        const rawRate = parseFloat(window.userState.hourly_rate || 0);
        const rawEnergy = parseFloat(window.userState.energy || 0);

        const znFormatted = Math.floor(rawBalance).toLocaleString('en-US');
        const usdFormatted = rawUsd.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
        const adFormatted = Math.floor(rawAd).toLocaleString('en-US');
        const hourlyFormatted = Number.isInteger(rawRate) ? rawRate.toString() : rawRate.toFixed(1);
        const energyFormatted = Math.floor(rawEnergy).toLocaleString('en-US');

        // 1. التحديث المباشر عبر وسم data-bind
        document.querySelectorAll('[data-bind="balance"]').forEach(el => {
            if (el.tagName === 'INPUT') el.value = znFormatted;
            else el.innerText = znFormatted;
        });

        document.querySelectorAll('[data-bind="usd_balance"]').forEach(el => {
            if (el.tagName === 'INPUT') el.value = usdFormatted;
            else el.innerText = `$${usdFormatted}`;
        });

        document.querySelectorAll('[data-bind="ad_balance"]').forEach(el => {
            if (el.tagName === 'INPUT') el.value = adFormatted;
            else el.innerText = adFormatted;
        });

        document.querySelectorAll('[data-bind="hourly_rate"]').forEach(el => {
            if (el.tagName === 'INPUT') el.value = hourlyFormatted;
            else el.innerText = hourlyFormatted;
        });

        document.querySelectorAll('[data-bind="energy"]').forEach(el => {
            if (el.tagName === 'INPUT') el.value = energyFormatted;
            else el.innerText = energyFormatted;
        });

        // 2. تحديث عناصر ZN التقليدية دون مسح أوسمة data-bind الابنة
        const allZnElements = document.querySelectorAll('[id*="balance"], [id*="zn"], .zn-balance, .balance-text, .zn-balance-display');
        allZnElements.forEach(el => {
            if (el.hasAttribute('data-bind') || el.querySelector('[data-bind]')) return;
            if (el.tagName === 'INPUT') {
                el.value = znFormatted;
                return;
            }
            const text = el.innerText || "";
            if (text.includes('ZN') || el.id.includes('zn-balance') || el.id === 'user-balance' || el.id.includes('shop-balance') || el.id === 'farm-balance') {
                if (text.includes('رصيد ZN:')) el.innerText = `رصيد ZN: ${znFormatted}`;
                else if (text.includes('ZN:')) el.innerText = `ZN: ${znFormatted}`;
                else if (text.includes('ZN ')) el.innerText = `ZN ${znFormatted}`;
                else if (!text.includes('$') && !text.includes('USD')) el.innerText = `ZN: ${znFormatted}`;
            }
        });

        // 3. تحديث عناصر USD المعرفة عبر المعرفات
        const allUsdElements = document.querySelectorAll('[id*="usd"], .usd-balance');
        allUsdElements.forEach(el => {
            if (el.hasAttribute('data-bind') || el.querySelector('[data-bind]')) return;
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

        // 4. تحديث سرعة التعدين
        const allRateElements = document.querySelectorAll('[id*="rate"], [id*="speed"], [id*="hourly"]');
        allRateElements.forEach(el => {
            if (el.hasAttribute('data-bind') || el.querySelector('[data-bind]')) return;
            if (el.tagName === 'INPUT') {
                el.value = hourlyFormatted;
                return;
            }
            const text = el.innerText || "";
            if (text.includes('h/') || text.includes('/h') || el.id === 'farm-rate') el.innerText = `⚡ ${hourlyFormatted}/h`;
        });

        // تشغيل خطافات الواجهات المفتوحة
        if (typeof window.updateShopUI === 'function') window.updateShopUI();
        if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
        if (typeof window.updateTasksUI === 'function') window.updateTasksUI();

    } catch (error) {
        console.error("خطأ صامت في تحديث الواجهة:", error);
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
        const data = await window.fetchAPI('/api/user/info');
        if (data && data.success) {
            if (data.balance !== undefined) window.userState.balance = parseFloat(data.balance);
            if (data.usd_balance !== undefined) window.userState.usd_balance = parseFloat(data.usd_balance);
            if (data.ad_balance !== undefined) window.userState.ad_balance = parseFloat(data.ad_balance);
            if (data.hourly_rate !== undefined && parseFloat(data.hourly_rate) > 0) {
                window.userState.hourly_rate = parseFloat(data.hourly_rate);
            }
            if (data.energy !== undefined) window.userState.energy = parseFloat(data.energy);
            if (data.storage_level !== undefined) window.userState.storage_level = parseInt(data.storage_level);
            if (data.mining_level !== undefined) window.userState.mining_level = parseInt(data.mining_level);
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
   5. Actions
   ========================================== */
window.loadWalletHistory = async function() {
    const historyList = document.getElementById('wallet-history-list');
    if (!historyList) return;

    historyList.innerHTML = `<div class="loading-spinner">جاري تحميل السجلات...</div>`;

    try {
        const data = await window.fetchAPI('/api/wallet/get_history');
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
};

window.executeConvertZN = async function(amount) {
    try {
        const res = await window.fetchAPI('/api/wallet/wallet_convert', 'POST', { amount: parseFloat(amount) });
        if (res.success) {
            window.userState.usd_balance = res.new_usd_balance;
            window.userState.balance = res.new_balance;
            alert(`تم تحويل ${parseFloat(amount).toLocaleString()} ZN بنجاح إلى $${parseFloat(res.usd_gained).toLocaleString('en-US', {minimumFractionDigits:4})}!`);
            window.loadWalletHistory();
        }
    } catch (e) {
        alert(`فشل التحويل: ${e.message}`);
    }
};

window.executeWithdraw = async function(amountUSD, address) {
    try {
        const res = await window.fetchAPI('/api/wallet/wallet_withdraw', 'POST', { 
            amount: parseFloat(amountUSD), 
            walletAddress: address 
        });
        if (res.success) {
            window.userState.usd_balance = res.new_usd_balance;
            alert(`تم إرسال طلب السحب بنجاح وهي قيد المعالجة!`);
            window.loadWalletHistory();
        }
    } catch (e) {
        alert(`فشل السحب: ${e.message}`);
    }
};

/* ==========================================
   6. Realtime Auto-Sync & Initialization
   ========================================== */
document.addEventListener('DOMContentLoaded', () => {
    window.updateUI(); 
    window.loadUserData(); 
    
    const historyBtn = document.getElementById('open-history-btn');
    if (historyBtn) {
        historyBtn.addEventListener('click', window.loadWalletHistory);
    }

    setInterval(() => {
        window.loadUserData();
    }, 5000); 

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            window.loadUserData();
        }
    });
});

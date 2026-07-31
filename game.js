const tg = window.Telegram?.WebApp;

if (tg) {
    tg.ready();
    tg.expand();
    if (tg.enableClosingConfirmation) tg.enableClosingConfirmation();
    if (tg.setHeaderColor) tg.setHeaderColor('secondary_bg_color');
}

window.currentTonPriceUSD = parseFloat(localStorage.getItem('last_ton_price')) || 0;

const rawUserState = {
    tg_id: null,
    first_name: "لاعب",
    balance: 0.0,
    usd_balance: 0.0,
    ad_balance: 0.0,
    hourly_rate: 0.0,
    energy: 100.0,
    storage_level: 0,
    upgrades: {},
    wallet_address: null
};

function saveLocalState() {
    try {
        localStorage.setItem('app_user_state', JSON.stringify(window.userState));
    } catch (e) {
        console.warn("تعذر الحفظ في LocalStorage", e);
    }
}

function loadLocalState() {
    try {
        const saved = localStorage.getItem('app_user_state');
        if (saved) Object.assign(rawUserState, JSON.parse(saved));
    } catch (e) {
        console.warn("تعذر تحميل البيانات المحلية", e);
    }
}

loadLocalState();

window.userState = new Proxy(rawUserState, {
    set(target, prop, value) {
        target[prop] = value;
        const monitoredProps = ['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'energy', 'storage_level'];
        
        if (monitoredProps.includes(prop)) {
            saveLocalState();
            if (typeof window.updateUI === 'function') window.updateUI();

            window.dispatchEvent(new CustomEvent('userStateUpdated', {
                detail: { prop, value, state: target }
            }));
        }
        return true;
    }
});

window.fetchAPI = async function(endpoint, method = 'GET', bodyData = null) {
    const headers = { 'Content-Type': 'application/json' };

    if (tg && tg.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData;
        headers['Authorization'] = `Bearer ${tg.initData}`;
    }

    const options = { method, headers };
    if (bodyData) options.body = JSON.stringify(bodyData);

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

window.globalFetchTonPrice = async function() {
    const apis = [
        async () => {
            let r = await fetch('https://tonapi.io/v2/rates?tokens=ton&currencies=usd');
            let d = await r.json();
            return parseFloat(d?.rates?.TON?.prices?.USD);
        },
        async () => {
            let r = await fetch('https://www.okx.com/api/v5/market/ticker?instId=TON-USDT');
            let d = await r.json();
            return parseFloat(d?.data?.[0]?.last);
        },
        async () => {
            let r = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd');
            let d = await r.json();
            return parseFloat(d['the-open-network']?.usd);
        }
    ];

    for (let fetchPrice of apis) {
        try {
            let price = await fetchPrice();
            if (price && price > 0.1 && price < 200) {
                window.currentTonPriceUSD = price;
                localStorage.setItem('last_ton_price', price.toString());
                
                if (typeof window.updateUI === 'function') window.updateUI();
                return price;
            }
        } catch (e) { continue; }
    }
};

window.updateUI = function() {
    try {
        const rawBalance = parseFloat(window.userState.balance || 0);
        const rawUsd = parseFloat(window.userState.usd_balance || 0);
        const rawAd = parseFloat(window.userState.ad_balance || 0);
        const rawRate = parseFloat(window.userState.hourly_rate || 0);
        const rawEnergy = parseFloat(window.userState.energy || 0);
        const rawTonPrice = parseFloat(window.currentTonPriceUSD || 0);

        const znFormatted = rawBalance.toLocaleString('en-US', { maximumFractionDigits: 0 });
        const usdFormatted = rawUsd.toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 });
        const adFormatted = rawAd.toLocaleString('en-US', { maximumFractionDigits: 0 });
        const hourlyFormatted = rawRate.toLocaleString('en-US', { maximumFractionDigits: 0 });
        const energyFormatted = rawEnergy.toLocaleString('en-US', { maximumFractionDigits: 0 });
        const tonPriceFormatted = rawTonPrice > 0 ? `$${rawTonPrice.toFixed(2)}` : 'جاري التحميل...';

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
            else el.innerText = `⚡ ${hourlyFormatted}/h`;
        });

        document.querySelectorAll('[data-bind="energy"]').forEach(el => {
            if (el.tagName === 'INPUT') el.value = energyFormatted;
            else el.innerText = energyFormatted;
        });

        document.querySelectorAll('[data-bind="ton_price"]').forEach(el => {
            if (el.tagName === 'INPUT') el.value = tonPriceFormatted;
            else el.innerText = tonPriceFormatted;
        });

        if (typeof window.updateShopUI === 'function') window.updateShopUI();
        if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
        if (typeof window.updateTasksUI === 'function') window.updateTasksUI();
        if (typeof window.updateWalletHeaderUI === 'function') window.updateWalletHeaderUI();

    } catch (error) {
        console.error("خطأ في تحديث الواجهة:", error);
    }
};

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
            if (data.hourly_rate !== undefined) window.userState.hourly_rate = parseFloat(data.hourly_rate);
            if (data.energy !== undefined) window.userState.energy = parseFloat(data.energy);
            if (data.storage_level !== undefined) window.userState.storage_level = parseInt(data.storage_level);
            if (data.upgrades !== undefined) window.userState.upgrades = data.upgrades;
            if (data.wallet_address !== undefined) window.userState.wallet_address = data.wallet_address;
        }
    } catch (e) {
        console.warn("تنبيه: تم الاعتماد على البيانات المحلية مؤقتاً لحين الاتصال.");
    } finally {
        isUserDataFetching = false;
        window.updateUI();
    }
};

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
            alert(`تم تحويل ${parseFloat(amount).toLocaleString()} ZN بنجاح!`);
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
            alert(`تم إرسال طلب السحب بنجاح!`);
            window.loadWalletHistory();
        }
    } catch (e) {
        alert(`فشل السحب: ${e.message}`);
    }
};

document.addEventListener('DOMContentLoaded', () => {
    const historyBtn = document.getElementById('open-history-btn');
    if (historyBtn) historyBtn.addEventListener('click', window.loadWalletHistory);

    window.globalFetchTonPrice();

    setInterval(() => {
        window.loadUserData();
        window.globalFetchTonPrice();
    }, 15000); 

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden) {
            window.loadUserData();
            window.globalFetchTonPrice();
        }
    });
});

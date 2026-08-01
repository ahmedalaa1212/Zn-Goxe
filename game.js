// ==========================================
// 1. التهيئة والتخزين المحلي (Local-First)
// ==========================================
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready(); tg.expand();
    if (tg.enableClosingConfirmation) tg.enableClosingConfirmation();
    if (tg.setHeaderColor) tg.setHeaderColor('secondary_bg_color');
}

window.currentTonPriceUSD = parseFloat(localStorage.getItem('last_ton_price')) || 0;

function getSavedState() {
    const base = {
        tg_id: tg?.initDataUnsafe?.user?.id || null,
        first_name: tg?.initDataUnsafe?.user?.first_name || "لاعب",
        balance: 0, usd_balance: 0, ad_balance: 0, hourly_rate: 0, energy: 100, storage_level: 0, upgrades: {}, wallet_address: null
    };
    try { return { ...base, ...JSON.parse(localStorage.getItem('app_user_state') || '{}') }; }
    catch { return base; }
}

let isFirebaseUpdating = false;
const lastLocalTimes = {};

window.userState = new Proxy(getSavedState(), {
    set(target, prop, value) {
        target[prop] = value;
        if (!isFirebaseUpdating) lastLocalTimes[prop] = Date.now();
        
        if (['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'energy', 'storage_level', 'upgrades'].includes(prop)) {
            try { localStorage.setItem('app_user_state', JSON.stringify(target)); } catch {}
            if (typeof window.updateUI === 'function') window.updateUI();
            window.dispatchEvent(new CustomEvent('userStateUpdated', { detail: { prop, value, state: target } }));
        }
        return true;
    }
});

// ==========================================
// 2. الاتصال بالسيرفر مع التحديث اللحظي المباشر
// ==========================================
window.fetchAPI = async function(endpoint, method = 'GET', bodyData = null) {
    const headers = { 'Content-Type': 'application/json' };
    if (tg?.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData;
        headers['Authorization'] = `Bearer ${tg.initData}`;
    }

    // زيادة الرصيد فوراً في الشاشة وفي LocalStorage عند التجميع
    if (endpoint.includes('/collect') || endpoint.includes('/claim')) {
        lastLocalTimes['balance'] = Date.now();
        let pending = parseFloat(window.uncollectedBalance || window.pendingBalance || 0);
        if (!pending) {
            document.querySelectorAll('iframe').forEach(f => {
                try {
                    const w = f.contentWindow;
                    if (w?.uncollectedBalance || w?.pendingBalance) {
                        pending = parseFloat(w.uncollectedBalance || w.pendingBalance || 0);
                        w.uncollectedBalance = 0; w.pendingBalance = 0;
                    }
                } catch {}
            });
        }
        if (pending > 0) {
            window.userState.balance += pending;
            window.uncollectedBalance = 0; window.pendingBalance = 0;
        }
    }

    try {
        const res = await fetch(endpoint, { method, headers, body: bodyData ? JSON.stringify(bodyData) : null });
        const data = await res.json();
        if (!res.ok) {
            if (res.status === 403 && data.error?.includes("محظور")) { alert("حسابك محظور."); tg?.close(); }
            throw new Error(data.error || `HTTP ${res.status}`);
        }
        if (data.new_balance !== undefined) window.userState.balance = parseFloat(data.new_balance);
        if (data.new_usd_balance !== undefined) window.userState.usd_balance = parseFloat(data.new_usd_balance);
        return data;
    } catch (err) {
        console.error(`API Error [${endpoint}]:`, err);
        throw err;
    }
};

// ==========================================
// 3. جلب سعر TON والمزامنة الذكية مع الفايربيس
// ==========================================
window.globalFetchTonPrice = async function() {
    const apis = [
        'https://tonapi.io/v2/rates?tokens=ton&currencies=usd',
        'https://www.okx.com/api/v5/market/ticker?instId=TON-USDT',
        'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd'
    ];
    for (const url of apis) {
        try {
            const r = await fetch(url);
            const d = await r.json();
            const p = parseFloat(d?.rates?.TON?.prices?.USD || d?.data?.[0]?.last || d['the-open-network']?.usd);
            if (p > 0.1 && p < 200) {
                window.currentTonPriceUSD = p;
                localStorage.setItem('last_ton_price', p.toString());
                if (typeof window.updateUI === 'function') window.updateUI();
                return p;
            }
        } catch {}
    }
};

window.initFirebaseRealtimeSync = function(userId) {
    if (!window.db || !userId) return;
    window.db.collection('users').doc(String(userId)).onSnapshot(doc => {
        if (!doc.exists) return;
        const d = doc.data();
        isFirebaseUpdating = true;

        if (d.balance !== undefined) {
            const fbBal = parseFloat(d.balance);
            if (Date.now() - (lastLocalTimes['balance'] || 0) > 5000 || fbBal >= window.userState.balance) {
                window.userState.balance = fbBal;
            }
        }
        if (d.usd_balance !== undefined) {
            const fbUsd = parseFloat(d.usd_balance);
            if (Date.now() - (lastLocalTimes['usd_balance'] || 0) > 5000 || fbUsd >= window.userState.usd_balance) {
                window.userState.usd_balance = fbUsd;
            }
        }
        ['ad_balance', 'hourly_rate', 'energy', 'storage_level', 'upgrades'].forEach(k => {
            if (d[k] !== undefined) window.userState[k] = d[k];
        });

        isFirebaseUpdating = false;
    }, err => console.error("Firebase Sync Error:", err));
};

// ==========================================
// 4. تحديث عناصر الواجهة القائمة والـ IFrames
// ==========================================
window.updateUI = function() {
    try {
        const s = window.userState;
        const fmt = {
            balance: parseFloat(s.balance || 0).toLocaleString('en-US', { maximumFractionDigits: 0 }),
            usd_balance: `$${parseFloat(s.usd_balance || 0).toLocaleString('en-US', { minimumFractionDigits: 4, maximumFractionDigits: 4 })}`,
            ad_balance: parseFloat(s.ad_balance || 0).toLocaleString('en-US', { maximumFractionDigits: 0 }),
            hourly_rate: `⚡ ${parseFloat(s.hourly_rate || 0).toLocaleString('en-US', { maximumFractionDigits: 0 })}/h`,
            energy: parseFloat(s.energy || 0).toLocaleString('en-US', { maximumFractionDigits: 0 }),
            ton_price: window.currentTonPriceUSD > 0 ? `$${window.currentTonPriceUSD.toFixed(2)}` : 'جاري التحميل...'
        };

        const updateDoc = (doc) => {
            Object.keys(fmt).forEach(key => {
                doc.querySelectorAll(`[data-bind="${key}"]`).forEach(el => {
                    if (el.tagName === 'INPUT') el.value = fmt[key].replace('$', '').replace('⚡ ', '').replace('/h', '');
                    else el.innerText = fmt[key];
                });
            });
        };

        updateDoc(document);
        document.querySelectorAll('iframe').forEach(f => {
            try { if (f.contentWindow?.document) updateDoc(f.contentWindow.document); } catch {}
        });

        ['updateShopUI', 'updateFarmUI', 'updateTasksUI', 'updateWalletHeaderUI'].forEach(fn => {
            if (typeof window[fn] === 'function') window[fn]();
        });
    } catch (e) { console.error("UI Update Error:", e); }
};

// ==========================================
// 5. جلب بيانات المستخدم وعمليات المحفظة
// ==========================================
let isFetchingUser = false;
window.loadUserData = async function() {
    if (!tg?.initData || isFetchingUser) return;
    isFetchingUser = true;
    try {
        const d = await window.fetchAPI('/api/user/info');
        if (d?.success) {
            ['tg_id', 'balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'energy', 'storage_level', 'upgrades', 'wallet_address'].forEach(k => {
                if (d[k] !== undefined) window.userState[k] = d[k];
            });
            if (d.upgrades && window.PlayerData) window.PlayerData.upgrades = d.upgrades;
        }
    } catch {} finally { isFetchingUser = false; window.updateUI(); }
};

window.loadWalletHistory = async function() {
    const el = document.getElementById('wallet-history-list');
    if (!el) return;
    el.innerHTML = `<div class="loading-spinner">جاري التحميل...</div>`;
    try {
        const d = await window.fetchAPI('/api/wallet/get_history');
        if (d.success && d.history?.length) {
            el.innerHTML = d.history.map(tx => {
                const isW = tx.type === 'withdraw', isD = tx.type === 'deposit';
                const badge = isW ? (tx.status === 'completed' ? 'badge-success' : 'badge-warning') : 'badge-success';
                const title = isW ? 'سحب أرباح' : (isD ? 'إيداع رصيد' : 'تحويل ZN إلى USD');
                const sign = isW ? '-' : '+';
                const amt = `${sign}$${parseFloat(tx.amount_usd || tx.gross_amount_usd || 0).toFixed(2)}`;
                return `<div class="history-item">
                    <div class="history-info"><span class="history-title">${title}</span><span class="history-date">${tx.created_at ? new Date(tx.created_at).toLocaleString('ar-EG') : 'الآن'}</span></div>
                    <div class="history-amount"><span class="amount-text">${amt}</span><span class="badge ${badge}">${tx.status || 'مكتمل'}</span></div>
                </div>`;
            }).join('');
        } else { el.innerHTML = `<div class="empty-msg">لا توجد معاملات سابقة.</div>`; }
    } catch (e) { el.innerHTML = `<div class="error-msg">${e.message}</div>`; }
};

window.executeConvertZN = async (amount) => {
    try {
        const res = await window.fetchAPI('/api/wallet/wallet_convert', 'POST', { amount: parseFloat(amount) });
        if (res.success) {
            window.userState.usd_balance = res.new_usd_balance;
            window.userState.balance = res.new_balance;
            alert(`تم التحويل بنجاح!`); window.loadWalletHistory();
        }
    } catch (e) { alert(`فشل التحويل: ${e.message}`); }
};

window.executeWithdraw = async (amountUSD, address) => {
    try {
        const res = await window.fetchAPI('/api/wallet/wallet_withdraw', 'POST', { amount: parseFloat(amountUSD), walletAddress: address });
        if (res.success) {
            window.userState.usd_balance = res.new_usd_balance;
            alert(`تم إرسال طلب السحب بنجاح!`); window.loadWalletHistory();
        }
    } catch (e) { alert(`فشل السحب: ${e.message}`); }
};

// ==========================================
// 6. تشغيل التطبيق والتزامن اللحظي
// ==========================================
document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('open-history-btn')?.addEventListener('click', window.loadWalletHistory);
    window.updateUI();
    window.globalFetchTonPrice();
    window.loadUserData().then(() => {
        const uid = window.userState.tg_id || tg?.initDataUnsafe?.user?.id;
        if (uid) window.initFirebaseRealtimeSync(uid);
    });
    setInterval(window.globalFetchTonPrice, 60000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) window.globalFetchTonPrice(); });
});

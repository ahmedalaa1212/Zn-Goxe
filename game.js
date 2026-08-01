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

function hideLoadingScreen() {
    const appEl = document.getElementById('app');
    const navEl = document.getElementById('main-nav');
    if (appEl) appEl.style.display = 'block';
    if (navEl) navEl.style.display = 'flex';

    const loaders = document.querySelectorAll('#loading-screen, .loading-screen, #loader, .loader-overlay');
    loaders.forEach(el => {
        el.style.opacity = '0';
        el.style.transition = 'opacity 0.3s ease';
        setTimeout(() => el.remove(), 300);
    });
}

function getSavedState() {
    const base = {
        tg_id: tg?.initDataUnsafe?.user?.id || null,
        first_name: tg?.initDataUnsafe?.user?.first_name || "لاعب",
        balance: 0, usd_balance: 0, ad_balance: 0, hourly_rate: 0, energy: 100, storage_level: 0, upgrades: {}, wallet_address: null, last_sync_time: Date.now()
    };
    try { 
        const saved = localStorage.getItem('app_user_state');
        if (saved) {
            const parsed = JSON.parse(saved);
            return {
                ...base,
                ...parsed,
                balance: (parsed.balance !== undefined && !isNaN(parseFloat(parsed.balance))) ? parseFloat(parsed.balance) : base.balance,
                usd_balance: (parsed.usd_balance !== undefined && !isNaN(parseFloat(parsed.usd_balance))) ? parseFloat(parsed.usd_balance) : base.usd_balance
            };
        }
        return base; 
    } catch { return base; }
}

let isFirebaseUpdating = false;
let lastSaveTime = 0;
const lastLocalTimes = {};

window.userState = new Proxy(getSavedState(), {
    set(target, prop, value) {
        const oldVal = target[prop];
        target[prop] = value;
        
        if (!isFirebaseUpdating) lastLocalTimes[prop] = Date.now();
        
        if (['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'energy', 'storage_level', 'upgrades'].includes(prop)) {
            const now = Date.now();
            if (now - lastSaveTime > 2000 && !isFirebaseUpdating) {
                try { localStorage.setItem('app_user_state', JSON.stringify(target)); } catch {}
                lastSaveTime = now;
            }
            
            if (typeof window.updateUI === 'function') window.updateUI();
            
            window.dispatchEvent(new CustomEvent('userStateUpdated', { 
                detail: { prop, value, oldVal, state: target } 
            }));
        }
        return true;
    }
});

// ==========================================
// 2. الاتصال بالسيرفر مع تحديث الرصيد اللحظي الشامل
// ==========================================
window.fetchAPI = async function(endpoint, method = 'GET', bodyData = null) {
    const headers = { 'Content-Type': 'application/json' };
    if (tg?.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData;
        headers['Authorization'] = `Bearer ${tg.initData}`;
    }

    try {
        const fetchOptions = { method, headers };
        if (method !== 'GET' && method !== 'HEAD' && bodyData) {
            fetchOptions.body = JSON.stringify(bodyData);
        }

        const res = await fetch(endpoint, fetchOptions);
        const data = await res.json();
        
        if (!res.ok) {
            if (res.status === 403 && data.error?.includes("محظور")) { alert("حسابك محظور."); tg?.close(); }
            throw new Error(data.error || `HTTP ${res.status}`);
        }

        const targetObj = data.user || data.player || data.data || data;
        
        isFirebaseUpdating = true;
        let incomingBal = data.new_balance ?? targetObj?.balance;
        if (incomingBal !== undefined && incomingBal !== null) {
            const numBal = parseFloat(incomingBal);
            if (!isNaN(numBal)) {
                window.userState.balance = numBal;
            }
        }

        let incomingUsd = data.new_usd_balance ?? targetObj?.usd_balance;
        if (incomingUsd !== undefined && incomingUsd !== null) {
            const numUsd = parseFloat(incomingUsd);
            if (!isNaN(numUsd)) {
                window.userState.usd_balance = numUsd;
            }
        }

        if (targetObj?.hourly_rate !== undefined) {
            const numRate = parseFloat(targetObj.hourly_rate);
            if (!isNaN(numRate)) window.userState.hourly_rate = numRate;
        }
        isFirebaseUpdating = false;

        return data;
    } catch (err) {
        console.error(`API Error [${endpoint}]:`, err);
        throw err;
    }
};

// ==========================================
// 3. جلب سعر TON والمزامنة المباشرة
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
        const d = doc.data() || {};
        
        try {
            isFirebaseUpdating = true;

            if (d.balance !== undefined) {
                const fbBal = parseFloat(d.balance);
                if (!isNaN(fbBal)) window.userState.balance = fbBal;
            }
            if (d.usd_balance !== undefined) {
                const fbUsd = parseFloat(d.usd_balance);
                if (!isNaN(fbUsd)) window.userState.usd_balance = fbUsd;
            }
            ['ad_balance', 'hourly_rate', 'energy', 'storage_level', 'upgrades'].forEach(k => {
                if (d[k] !== undefined) window.userState[k] = d[k];
            });
            window.userState.last_sync_time = Date.now();
        } finally {
            isFirebaseUpdating = false;
        }
    }, err => console.error("Firebase Sync Error:", err));
};

// ==========================================
// 4. دوال التنسيق ومحرك الحركة السلسة للعداد
// ==========================================

window.formatBalance = function(val) {
    if (val === undefined || val === null || isNaN(val)) return '0';
    const num = parseFloat(val);
    const hasDecimals = num % 1 !== 0;
    return num.toLocaleString('en-US', {
        minimumFractionDigits: hasDecimals ? 2 : 0,
        maximumFractionDigits: 2
    });
};

window.formatNumberHTML = function(val, minDec = 0, maxDec = 2) {
    if (val === undefined || val === null || isNaN(val)) return '0';
    let num = parseFloat(val);
    
    let suffix = '';
    if (num >= 1e9) { num = num / 1e9; suffix = 'B'; }
    else if (num >= 1e6) { num = num / 1e6; suffix = 'M'; }

    const hasDecimals = num % 1 !== 0;
    const minD = (minDec === 0 && hasDecimals) ? 2 : minDec;
    
    const formattedStr = num.toLocaleString('en-US', {
        minimumFractionDigits: (suffix === '') ? minD : 2,
        maximumFractionDigits: (suffix === '') ? maxDec : 2
    });

    const parts = formattedStr.split('.');
    let htmlResult = parts[0];
    if (parts.length > 1) {
        htmlResult += `<span class="small-decimal" style="font-size: 0.75em; opacity: 0.85;">.${parts[1]}</span>`;
    }
    if (suffix) {
        htmlResult += `<span class="suffix" style="font-weight: bold; margin-left: 2px;">${suffix}</span>`;
    }
    return htmlResult;
};

let visualBalance = null;
let lastTickTime = performance.now();

function startLocalMiningSimulator() {
    requestAnimationFrame(function tick(currentTime) {
        const deltaSec = (currentTime - lastTickTime) / 1000;
        lastTickTime = currentTime;

        if (window.userState && window.userState.hourly_rate > 0) {
            const ratePerSec = window.userState.hourly_rate / 3600;
            window.userState.balance += (ratePerSec * deltaSec);
        }
        
        renderSmoothBalance(window.userState.balance);
        requestAnimationFrame(tick);
    });
}

function renderSmoothBalance(targetVal) {
    if (visualBalance === null) {
        visualBalance = targetVal;
        applyBalanceToUI(visualBalance);
        return;
    }

    const diff = targetVal - visualBalance;
    visualBalance += diff * 0.1;

    if (Math.abs(targetVal - visualBalance) < 0.001) {
        visualBalance = targetVal;
    }

    applyBalanceToUI(visualBalance);
}

function applyBalanceToUI(val) {
    const plainFormatted = window.formatBalance(val);
    const htmlFormatted = window.formatNumberHTML(val, 0, 2);
    
    const updateTargetElements = (doc) => {
        doc.querySelectorAll('[data-bind="balance"]').forEach(el => {
            if (el.tagName === 'INPUT') {
                el.value = plainFormatted;
            } else {
                if (el.textContent.includes('ZN:')) {
                    el.innerHTML = `ZN: ${htmlFormatted}`;
                } else {
                    el.innerHTML = `${htmlFormatted} ZN`;
                }
            }
        });

        doc.querySelectorAll('#farm-balance, .farm-balance, #user-balance, .user-balance, .zn-balance-text, #top-balance-games').forEach(el => {
            if (el.tagName !== 'INPUT') {
                if (el.textContent.includes('ZN:')) {
                    el.innerHTML = `ZN: ${htmlFormatted}`;
                } else {
                    el.innerHTML = `${htmlFormatted} ZN`;
                }
            }
        });
    };

    updateTargetElements(document);
    document.querySelectorAll('iframe').forEach(f => {
        try { if (f.contentWindow?.document) updateTargetElements(f.contentWindow.document); } catch {}
    });
}

window._isUpdatingUI = false;

window.updateUI = function() {
    if (window._isUpdatingUI) return;
    window._isUpdatingUI = true;
    try {
        const s = window.userState;

        ['updateShopUI', 'updateFarmUI', 'updateTasksUI', 'updateWalletHeaderUI'].forEach(fn => {
            if (typeof window[fn] === 'function') {
                try { window[fn](); } catch (e) {}
            }
        });

        renderSmoothBalance(parseFloat(s.balance || 0));

        const fmtHTML = {
            usd_balance: `$${window.formatNumberHTML(s.usd_balance || 0, 2, 4)}`,
            ad_balance: window.formatNumberHTML(s.ad_balance, 0, 2),
            hourly_rate: `⚡ ${window.formatNumberHTML(s.hourly_rate, 0, 2)}/h`,
            energy: parseFloat(s.energy || 0).toLocaleString('en-US', { maximumFractionDigits: 0 }),
            ton_price: window.currentTonPriceUSD > 0 ? `$${window.formatNumberHTML(window.currentTonPriceUSD, 2, 2)}` : 'جاري التحميل...'
        };

        const fmtPlain = {
            usd_balance: window.formatBalance(s.usd_balance || 0),
            ad_balance: window.formatBalance(s.ad_balance),
            hourly_rate: window.formatBalance(s.hourly_rate),
            energy: parseFloat(s.energy || 0).toLocaleString('en-US', { maximumFractionDigits: 0 }),
            ton_price: window.currentTonPriceUSD > 0 ? window.currentTonPriceUSD.toFixed(2) : 'جاري التحميل...'
        };

        const updateDoc = (doc) => {
            Object.keys(fmtHTML).forEach(key => {
                doc.querySelectorAll(`[data-bind="${key}"]`).forEach(el => {
                    if (el.tagName === 'INPUT') {
                        el.value = fmtPlain[key];
                    } else {
                        el.innerHTML = fmtHTML[key];
                    }
                });
            });
        };

        updateDoc(document);
        document.querySelectorAll('iframe').forEach(f => {
            try { if (f.contentWindow?.document) updateDoc(f.contentWindow.document); } catch {}
        });

    } catch (e) { 
        console.error("UI Update Error:", e); 
    } finally {
        window._isUpdatingUI = false;
    }
};

// ==========================================
// 5. جلب بيانات المستخدم وعمليات المحفظة
// ==========================================
let isFetchingUser = false;
window.loadUserData = async function() {
    if (isFetchingUser) return;
    isFetchingUser = true;
    try {
        const d = await window.fetchAPI('/api/user/info');
        if (d?.success) {
            const u = d.user || d.player || d.data || d;
            ['tg_id', 'balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'energy', 'storage_level', 'upgrades', 'wallet_address'].forEach(k => {
                if (u[k] !== undefined && u[k] !== null) {
                    window.userState[k] = u[k];
                }
            });
            if (u.upgrades && window.PlayerData) window.PlayerData.upgrades = u.upgrades;
        }
    } catch (err) {
        console.error("Error loading user data:", err);
    } finally { 
        isFetchingUser = false; 
        window.updateUI();
        hideLoadingScreen();
    }
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
                const amtVal = parseFloat(tx.amount_usd || tx.gross_amount_usd || 0);
                const amt = `${sign}$${window.formatNumberHTML(amtVal, 2, 2)}`;
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
// 6. تشغيل التطبيق والاستماع المباشر
// ==========================================
function initApp() {
    document.getElementById('open-history-btn')?.addEventListener('click', window.loadWalletHistory);
    
    window.updateUI();
    window.globalFetchTonPrice();
    window.loadUserData().then(() => {
        const uid = window.userState.tg_id || tg?.initDataUnsafe?.user?.id;
        if (uid) window.initFirebaseRealtimeSync(uid);
    });
    
    startLocalMiningSimulator();
    setTimeout(hideLoadingScreen, 4000);

    setInterval(window.globalFetchTonPrice, 60000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) window.globalFetchTonPrice(); });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}

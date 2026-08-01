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

// نظام Proxy ذكي لتقليل الضغط على LocalStorage أثناء التعدين اللحظي
window.userState = new Proxy(getSavedState(), {
    set(target, prop, value) {
        target[prop] = value;
        
        if (['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'energy', 'storage_level', 'upgrades'].includes(prop)) {
            const now = Date.now();
            // حفظ في التخزين المحلي كل 2 ثانية كحد أقصى لتجنب تشنج المتصفح
            if (now - lastSaveTime > 2000 && !isFirebaseUpdating) {
                try { localStorage.setItem('app_user_state', JSON.stringify(target)); } catch {}
                lastSaveTime = now;
            }
            
            if (typeof window.updateUI === 'function') window.updateUI();
            
            window.dispatchEvent(new CustomEvent('userStateUpdated', { 
                detail: { prop, value, state: target } 
            }));
        }
        return true;
    }
});

// ==========================================
// 2. الاتصال بالسيرفر 
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
        
        isFirebaseUpdating = true; // لمنع التخزين المتكرر أثناء سحب البيانات
        if (targetObj?.balance !== undefined) window.userState.balance = parseFloat(targetObj.balance);
        if (targetObj?.usd_balance !== undefined) window.userState.usd_balance = parseFloat(targetObj.usd_balance);
        if (targetObj?.hourly_rate !== undefined) window.userState.hourly_rate = parseFloat(targetObj.hourly_rate);
        isFirebaseUpdating = false;

        return data;
    } catch (err) {
        console.error(`API Error [${endpoint}]:`, err);
        throw err;
    }
};

// ==========================================
// 3. مزامنة فايربيس (تم التعديل لتقليل القراءات)
// ==========================================
window.globalFetchTonPrice = async function() {
    const apis = [
        'https://tonapi.io/v2/rates?tokens=ton&currencies=usd',
        'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd'
    ];
    for (const url of apis) {
        try {
            const r = await fetch(url);
            const d = await r.json();
            const p = parseFloat(d?.rates?.TON?.prices?.USD || d['the-open-network']?.usd);
            if (p > 0.1) {
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
    
    // ملاحظة للحماية: السيرفر يجب ألا يحدث رصيد المستخدم في فايربيس باستمرار
    // بل يحدثه فقط عند عمليات السحب، الشراء، أو الضغط على "تجميع" لتجنب تجاوز 50 ألف قراءة.
    window.db.collection('users').doc(String(userId)).onSnapshot(doc => {
        if (!doc.exists) return;
        const d = doc.data() || {};
        
        try {
            isFirebaseUpdating = true;
            if (d.balance !== undefined) window.userState.balance = parseFloat(d.balance);
            if (d.usd_balance !== undefined) window.userState.usd_balance = parseFloat(d.usd_balance);
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
// 4. محرك الحركة السلسة للعداد (Visual Ticker)
// ==========================================

window.formatBalance = function(val) {
    if (isNaN(val)) return '0';
    return parseFloat(val).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
};

// اختصار الأرقام الكبيرة جداً للحفاظ على التصميم
window.formatNumberHTML = function(val, minDec = 0, maxDec = 2) {
    if (isNaN(val)) return '0';
    let num = parseFloat(val);
    
    // اختصار الملايين والمليارات إذا كان الرقم كبيراً
    let suffix = '';
    if (num >= 1e9) { num = num / 1e9; suffix = 'B'; }
    else if (num >= 1e6) { num = num / 1e6; suffix = 'M'; }

    const formattedStr = num.toLocaleString('en-US', {
        minimumFractionDigits: (suffix === '') ? minDec : 2,
        maximumFractionDigits: (suffix === '') ? maxDec : 2
    });

    const parts = formattedStr.split('.');
    let resultHTML = parts[0];
    if (parts.length > 1) {
        resultHTML += `<span class="small-decimal" style="font-size: 0.75em; opacity: 0.8;">.${parts[1]}</span>`;
    }
    return resultHTML + (suffix ? `<span class="suffix" style="font-weight: bold; margin-left: 2px;">${suffix}</span>` : '');
};

let visualBalance = null;
let lastTickTime = performance.now();

// محاكي التعدين المحلي (يضيف للرصيد المعروض فقط بناءً على سرعة الساعة بدون إرسال للسيرفر)
function startLocalMiningSimulator() {
    requestAnimationFrame(function tick(currentTime) {
        const deltaSec = (currentTime - lastTickTime) / 1000;
        lastTickTime = currentTime;

        if (window.userState && window.userState.hourly_rate > 0) {
            const ratePerSec = window.userState.hourly_rate / 3600;
            // زيادة الرصيد الأساسي بصمت
            window.userState.balance += (ratePerSec * deltaSec);
        }
        
        renderSmoothUIBalance(window.userState.balance);
        requestAnimationFrame(tick);
    });
}

function renderSmoothUIBalance(targetVal) {
    if (visualBalance === null) visualBalance = targetVal;
    
    // حركة انسيابية للوصول للرقم المستهدف
    const diff = targetVal - visualBalance;
    visualBalance += diff * 0.1; // سرعة استجابة العداد البصري

    if (Math.abs(targetVal - visualBalance) < 0.001) {
        visualBalance = targetVal;
    }

    applyBalanceToUI(visualBalance);
}

function applyBalanceToUI(val) {
    const htmlFormatted = window.formatNumberHTML(val, 0, 4);
    
    const updateTargetElements = (doc) => {
        doc.querySelectorAll('[data-bind="balance"], #farm-balance, .farm-balance, #user-balance, .user-balance, .zn-balance-text').forEach(el => {
            if (el.tagName !== 'INPUT') {
                if (el.textContent.includes('ZN:')) el.innerHTML = `ZN: ${htmlFormatted}`;
                else el.innerHTML = `${htmlFormatted} ZN`;
            }
        });
    };

    updateTargetElements(document);
}

window._isUpdatingUI = false;
window.updateUI = function() {
    if (window._isUpdatingUI) return;
    window._isUpdatingUI = true;
    try {
        const s = window.userState;
        
        const fmtHTML = {
            usd_balance: `$${window.formatNumberHTML(s.usd_balance || 0, 2, 4)}`,
            ad_balance: window.formatNumberHTML(s.ad_balance, 0, 2),
            hourly_rate: `⚡ ${window.formatNumberHTML(s.hourly_rate, 0, 2)}/h`,
            ton_price: window.currentTonPriceUSD > 0 ? `$${window.formatNumberHTML(window.currentTonPriceUSD, 2, 2)}` : '...'
        };

        const updateDoc = (doc) => {
            Object.keys(fmtHTML).forEach(key => {
                doc.querySelectorAll(`[data-bind="${key}"]`).forEach(el => {
                    if (el.tagName !== 'INPUT') el.innerHTML = fmtHTML[key];
                });
            });
        };

        updateDoc(document);
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
        await window.fetchAPI('/api/user/info');
    } catch (err) {
        console.error("Error loading user data:", err);
    } finally { 
        isFetchingUser = false; 
        window.updateUI();
        hideLoadingScreen();
    }
};

window.executeConvertZN = async (amount) => {
    try {
        const res = await window.fetchAPI('/api/wallet/wallet_convert', 'POST', { amount: parseFloat(amount) });
        if (res.success) {
            alert(`تم التحويل بنجاح!`); 
            // تحديث الرصيد يتم تلقائياً عبر fetchAPI
        }
    } catch (e) { alert(`فشل التحويل: ${e.message}`); }
};

window.executeWithdraw = async (amountUSD, address) => {
    try {
        const res = await window.fetchAPI('/api/wallet/wallet_withdraw', 'POST', { amount: parseFloat(amountUSD), walletAddress: address });
        if (res.success) alert(`تم إرسال طلب السحب بنجاح!`);
    } catch (e) { alert(`فشل السحب: ${e.message}`); }
};

// ==========================================
// 6. تشغيل التطبيق
// ==========================================
function initApp() {
    window.updateUI();
    window.globalFetchTonPrice();
    window.loadUserData().then(() => {
        const uid = window.userState.tg_id || tg?.initDataUnsafe?.user?.id;
        if (uid) window.initFirebaseRealtimeSync(uid);
    });
    
    startLocalMiningSimulator(); // تشغيل العداد البصري اللحظي
    setTimeout(hideLoadingScreen, 2000);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}

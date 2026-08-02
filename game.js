// ==========================================
// 1. التهيئة والتخزين المحلي (Local-First)
// ==========================================
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready(); 
    tg.expand();
    if (tg.enableClosingConfirmation) tg.enableClosingConfirmation();
    if (tg.setHeaderColor) tg.setHeaderColor('secondary_bg_color');
}

window.currentTonPriceUSD = parseFloat(localStorage.getItem('last_ton_price')) || 0;

function hideLoadingScreen() {
    const appEl = document.getElementById('app');
    const navEl = document.getElementById('main-nav');
    if (appEl) appEl.style.display = 'block';
    if (navEl) navEl.style.display = 'flex';

    const loaders = document.querySelectorAll('#loading-screen, .loading-screen, #loader');
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
            return { ...base, ...parsed };
        }
        return base; 
    } catch { return base; }
}

let isFirebaseUpdating = false;
let lastSaveTime = 0;

window.userState = new Proxy(getSavedState(), {
    set(target, prop, value) {
        target[prop] = value;
        if (['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'energy', 'storage_level', 'upgrades'].includes(prop)) {
            const now = Date.now();
            if (now - lastSaveTime > 2000 && !isFirebaseUpdating) {
                try { localStorage.setItem('app_user_state', JSON.stringify(target)); } catch {}
                lastSaveTime = now;
            }
            if (typeof window.updateUI === 'function') window.updateUI();
        }
        return true;
    }
});

// ==========================================
// 2. الاتصال بالسيرفر مع تحديث الرصيد اللحظي
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
// 3. الاستماع اللحظي بـ Firestore (1 Read لكل جلسة)
// ==========================================
window.initFirebaseRealtimeSync = function(userId) {
    if (!window.db || !userId) return;
    
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
// 4. تنسيق العداد والمحرك السلس (Local Math)
// ==========================================
window.formatBalance = function(val) {
    if (val === undefined || val === null || isNaN(val)) return '0';
    return parseFloat(val).toLocaleString('en-US', {
        minimumFractionDigits: (val % 1 !== 0) ? 2 : 0,
        maximumFractionDigits: 2
    });
};

window.formatNumberHTML = function(val) {
    if (val === undefined || val === null || isNaN(val)) return '0';
    let num = parseFloat(val);
    let suffix = '';
    if (num >= 1e9) { num /= 1e9; suffix = 'B'; }
    else if (num >= 1e6) { num /= 1e6; suffix = 'M'; }

    const formattedStr = num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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

function startLocalMiningSimulator() {
    requestAnimationFrame(function tick() {
        // تم إلغاء إضافة التعدين محلياً للرصيد الرئيسي حتى يظل ثابتاً كلياً ولا يزداد إلا عند الضغط على "تجميع"
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

    visualBalance += (targetVal - visualBalance) * 0.1;
    applyBalanceToUI(visualBalance);
}

function applyBalanceToUI(val) {
    const htmlFormatted = window.formatNumberHTML(val);
    document.querySelectorAll('[data-bind="balance"], #farm-balance, .user-balance').forEach(el => {
        if (el.tagName !== 'INPUT') {
            el.innerHTML = `${htmlFormatted} ZN`;
        }
    });
}

window.updateUI = function() {
    renderSmoothBalance(parseFloat(window.userState.balance || 0));
};

// ==========================================
// 5. محرك تحميل القوائم والتنقل الديناميكي (Dynamic Page Loader)
// ==========================================
const loadedModules = new Set();

window.switchView = async function(viewName) {
    // 1. تحديث الأزرار النشطة في الشريط السفلي
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
    const targetNav = document.getElementById(`nav-${viewName}`);
    if (targetNav) targetNav.classList.add('active');

    // 2. تحديث الحاويات
    document.querySelectorAll('.game-view').forEach(v => v.classList.remove('active'));
    const targetView = document.getElementById(`view-${viewName}`);
    if (!targetView) return;
    
    targetView.classList.add('active');

    // 3. التحقق مما إذا كان القسم قد تم تحميل محتواه سابقاً
    if (!loadedModules.has(viewName)) {
        try {
            // جلب ملف HTML المخصص من المجلد المخصص لكل قسم
            const res = await fetch(`${viewName}/${viewName}.html`);
            if (res.ok) {
                const htmlContent = await res.text();
                targetView.innerHTML = htmlContent;
                
                // جلب وتحميل سكريبت JS الخاص بالقسم
                await loadModuleScript(`${viewName}/${viewName}.js`);
                loadedModules.add(viewName);
            } else {
                console.warn(`تعذر تحميل الملف: ${viewName}/${viewName}.html`);
            }
        } catch (err) {
            console.error(`خطأ أثناء تحميل قسم ${viewName}:`, err);
        }
    }

    // 4. استدعاء دالة التهيئة المخصصة للقسم إن وجِدت
    const initFuncName = `init${viewName.charAt(0).toUpperCase() + viewName.slice(1)}View`;
    if (typeof window[initFuncName] === 'function') {
        window[initFuncName]();
    }
    
    window.updateUI();
};

function loadModuleScript(scriptUrl) {
    return new Promise((resolve) => {
        if (document.querySelector(`script[src="${scriptUrl}"]`)) {
            resolve();
            return;
        }
        const script = document.createElement('script');
        script.src = scriptUrl;
        script.onload = () => resolve();
        script.onerror = () => resolve(); 
        document.body.appendChild(script);
    });
}

// ==========================================
// 6. تحميل بيانات المستخدم وتشغيل التطبيق
// ==========================================
window.loadUserData = async function() {
    try {
        const d = await window.fetchAPI('/api/user/info');
        if (d?.success) {
            const u = d.user || d.data || {};
            Object.assign(window.userState, u);
        }
    } catch (err) {
        console.error("Error loading user data:", err);
    } finally { 
        window.updateUI();
        hideLoadingScreen();
    }
};

function initApp() {
    window.updateUI();
    // تحميل قسم المزرعة المبدئي افتراضياً
    window.switchView('farm');
    
    window.loadUserData().then(() => {
        const uid = window.userState.tg_id || tg?.initDataUnsafe?.user?.id;
        if (uid) window.initFirebaseRealtimeSync(uid);
    });
    startLocalMiningSimulator();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initApp);
} else {
    initApp();
}

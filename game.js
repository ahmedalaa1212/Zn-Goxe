// ==========================================
// 1. التهيئة والتخزين المحلي (Local-First Architecture)
// ==========================================
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready(); 
    tg.expand();
    if (tg.enableClosingConfirmation) tg.enableClosingConfirmation();
}

window.currentTonPriceUSD = parseFloat(localStorage.getItem('last_ton_price')) || 6.50;
window.serverTimeOffset = 0;

// دالة موحدة لتنسيق الوقت (باستخدام h للساعات، m للدقائق، s للثواني)
window.formatTime = function(seconds) {
    if (isNaN(seconds) || seconds <= 0) return '0s';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${s}s`;
    return `${s}s`;
};

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
    const startParam = tg?.initDataUnsafe?.start_param || null;
    const base = {
        tg_id: tg?.initDataUnsafe?.user?.id || null,
        first_name: tg?.initDataUnsafe?.user?.first_name || "لاعب",
        referred_by_param: startParam,
        balance: 0.00, 
        usd_balance: 0.00, 
        ad_balance: 0.00, 
        hourly_rate: 0.00, 
        energy: 100, 
        storage_level: 0, 
        extra_storage: 0.00, 
        max_cap: 100.00, 
        unclaimed: 0.00,
        daily_streak: 1, 
        daily_day: 1, 
        last_daily_claim_date: null, 
        upgrades: {}, 
        wallet_address: null, 
        boost_multiplier: 1, 
        boost_active: false, 
        boost_expires_at: null,
        last_claim_time: null, 
        last_sync_time: Date.now()
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

// ⚡ كائن إدارة الحالة الوحيد بالنمط الموحد (Single Source of Truth)
window.userState = new Proxy(getSavedState(), {
    set(target, prop, value) {
        if (['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'extra_storage', 'max_cap', 'unclaimed'].includes(prop)) {
            const num = parseFloat(value);
            target[prop] = isNaN(num) ? 0.0 : num;
        } else {
            target[prop] = value;
        }
        
        if (!window.PlayerData) window.PlayerData = {};
        window.PlayerData[prop] = target[prop];

        if (['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'energy', 'storage_level', 'extra_storage', 'max_cap', 'daily_streak', 'daily_day', 'upgrades', 'last_claim_time', 'unclaimed', 'boost_multiplier', 'boost_active', 'boost_expires_at'].includes(prop)) {
            const now = Date.now();
            if (now - lastSaveTime > 2000 && !isFirebaseUpdating) {
                try { localStorage.setItem('app_user_state', JSON.stringify(target)); } catch {}
                lastSaveTime = now;
            }
            if (typeof window.updateUI === 'function') window.updateUI();
            if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
            
            // ⚡ إرسال حدث موحد لجميع الموديولات الفرعية للتحديث الفوري
            window.dispatchEvent(new CustomEvent('userStateUpdated', { detail: target }));
        }
        return true;
    }
});

// حفظ إضافي مضمون عند إغلاق أو مغادرة التطبيق
window.addEventListener('beforeunload', () => {
    try {
        localStorage.setItem('app_user_state', JSON.stringify(window.userState));
    } catch {}
});

// ==========================================
// 2. الاتصال بالسيرفر ومعالجة الاستجابة المباشرة
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
            if (res.status === 403 && data.error?.includes("محظور")) { 
                alert("حسابك محظور."); 
                tg?.close(); 
            }
            throw new Error(data.error || `HTTP ${res.status}`);
        }

        if (data.server_time) {
            const serverMs = new Date(data.server_time).getTime();
            if (!isNaN(serverMs)) {
                window.serverTimeOffset = serverMs - Date.now();
            }
        }

        const targetObj = data.player || data.user || data.data || (data.balance !== undefined ? data : null);
        
        isFirebaseUpdating = true;
        if (targetObj) {
            if (targetObj.balance !== undefined && targetObj.balance !== null) {
                const b = parseFloat(targetObj.balance);
                if (!isNaN(b)) window.userState.balance = b;
            }
            if (targetObj.usd_balance !== undefined && targetObj.usd_balance !== null) {
                const u = parseFloat(targetObj.usd_balance);
                if (!isNaN(u)) window.userState.usd_balance = u;
            }
            if (targetObj.ad_balance !== undefined && targetObj.ad_balance !== null) {
                const a = parseFloat(targetObj.ad_balance);
                if (!isNaN(a)) window.userState.ad_balance = a;
            }
            if (targetObj.hourly_rate !== undefined) window.userState.hourly_rate = parseFloat(targetObj.hourly_rate) || 0;
            if (targetObj.storage_level !== undefined) window.userState.storage_level = parseInt(targetObj.storage_level) || 0;
            if (targetObj.extra_storage !== undefined) window.userState.extra_storage = parseFloat(targetObj.extra_storage) || 0;
            if (targetObj.max_cap !== undefined) window.userState.max_cap = parseFloat(targetObj.max_cap) || 100;
            if (targetObj.daily_streak !== undefined) window.userState.daily_streak = parseInt(targetObj.daily_streak) || 1;
            if (targetObj.daily_day !== undefined) window.userState.daily_day = parseInt(targetObj.daily_day) || 1;
            if (targetObj.last_daily_claim_date !== undefined) window.userState.last_daily_claim_date = targetObj.last_daily_claim_date;
            if (targetObj.last_claim_time !== undefined) window.userState.last_claim_time = targetObj.last_claim_time;
            if (targetObj.upgrades !== undefined) window.userState.upgrades = targetObj.upgrades;
            if (targetObj.unclaimed !== undefined) window.userState.unclaimed = parseFloat(targetObj.unclaimed) || 0;
            if (targetObj.boost_multiplier !== undefined) window.userState.boost_multiplier = parseInt(targetObj.boost_multiplier) || 1;
            if (targetObj.boost_active !== undefined) window.userState.boost_active = Boolean(targetObj.boost_active);
            if (targetObj.boost_expires_at !== undefined) window.userState.boost_expires_at = targetObj.boost_expires_at;
        }
        isFirebaseUpdating = false;

        return data;
    } catch (err) {
        console.error(`API Error [${endpoint}]:`, err);
        throw err;
    }
};

// ==========================================
// 3. جلب سعر TON المباشر وتحديث الباقات
// ==========================================
window.fetchTonPrice = async function() {
    try {
        const res = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd');
        if (res.ok) {
            const data = await res.json();
            if (data['the-open-network']?.usd) {
                const price = parseFloat(data['the-open-network'].usd);
                window.currentTonPriceUSD = price;
                localStorage.setItem('last_ton_price', price);
            }
        }
    } catch (err) {
        console.warn("⚠️ لم يتم جلب سعر TON من CoinGecko، تم استخدام السعر المحلي المسجل:", window.currentTonPriceUSD);
    } finally {
        window.updateTonPriceUI();
    }
};

window.updateTonPriceUI = function() {
    const formattedPrice = `$${window.currentTonPriceUSD.toFixed(2)}`;
    const tonContainers = document.querySelectorAll('#ton-price-display, .ton-price-val, [data-bind="ton_price"]');
    tonContainers.forEach(el => {
        el.innerHTML = `<span dir="ltr" style="white-space:nowrap; font-weight:bold; color:#0088cc;">${formattedPrice}</span>`;
    });

    const packagesStatus = document.querySelectorAll('#packages-loading-status, .packages-status');
    packagesStatus.forEach(el => {
        el.style.display = 'none';
    });
};

// ==========================================
// 4. مشاهدة الإعلانات والمكافآت
// ==========================================
window.watchMonetagAd = async function() {
    if (typeof window.show_11322720 !== 'function') {
        alert('جاري تحميل مكتبة الإعلانات، يرجى المحاولة بعد قليل...');
        return;
    }

    try {
        await window.show_11322720();
        const res = await window.fetchAPI('/api/farm/daily_boost', 'POST');
        if (res.success) {
            alert(`🎉 تم زيادة سرعة التعدين بنجاح!`);
        } else {
            alert(res.error || 'حدث خطأ أثناء إضافة المكافأة.');
        }
    } catch (err) {
        console.error("Ad cancelled or error:", err);
        alert('يجب إكمال الإعلان للنهاية للحصول على المكافأة.');
    }
};

window.claimDailyReward = async function() {
    try {
        const res = await window.fetchAPI('/api/farm/daily_claim', 'POST');
        if (res.success) {
            if (res.new_balance !== undefined) window.userState.balance = parseFloat(res.new_balance);
            if (res.daily_day !== undefined) {
                window.userState.daily_day = res.daily_day;
                window.userState.daily_streak = res.daily_day;
            }
            alert(`🎁 مبروك! استلمت مكافأة اليوم. اليوم الحالي: ${res.daily_day}`);
            if (typeof window.onFarmTabOpen === 'function') window.onFarmTabOpen();
        } else {
            alert(res.error || 'لا يمكنك الاستلام الآن.');
        }
    } catch (err) {
        alert(err.message || 'حدث خطأ أثناء استلام المكافأة.');
    }
};

window.activateTenXBoost = async function(durationHours = 1) {
    try {
        const res = await window.fetchAPI('/api/farm/activate_boost', 'POST', { duration_hours: durationHours });
        if (res.success || res.status === "success") {
            alert(`🚀 تم تفعيل مضاعف الأرباح 10x بنجاح لمدة ${durationHours}h!`);
            if (typeof window.loadUserData === 'function') window.loadUserData();
            return true;
        } else {
            alert(res.error || res.message || 'حدث خطأ أثناء تفعيل البوست.');
            return false;
        }
    } catch (err) {
        console.error("Boost activation error:", err);
        alert('حدث خطأ أثناء الاتصال بالسيرفر لتفعيل البوست.');
        return false;
    }
};

// ==========================================
// 5. الاستماع اللحظي Firestore (Realtime Sync & Global Event)
// ==========================================
window.initFirebaseRealtimeSync = function(userId) {
    if (!window.db || !userId) return;
    
    try {
        window.db.collection('users').doc(String(userId)).onSnapshot(doc => {
            if (!doc.exists) return;
            const d = doc.data() || {};
            
            try {
                isFirebaseUpdating = true;
                if (!window.PlayerData) window.PlayerData = {};
                
                Object.assign(window.PlayerData, d);

                if (d.balance !== undefined && d.balance !== null) {
                    const bal = parseFloat(d.balance);
                    if (!isNaN(bal)) window.userState.balance = bal;
                }
                if (d.usd_balance !== undefined) window.userState.usd_balance = parseFloat(d.usd_balance) || 0;
                
                ['ad_balance', 'hourly_rate', 'energy', 'storage_level', 'extra_storage', 'max_cap', 'daily_streak', 'daily_day', 'last_daily_claim_date', 'upgrades', 'last_claim_time', 'unclaimed', 'boost_multiplier', 'boost_active', 'boost_expires_at'].forEach(k => {
                    if (d[k] !== undefined) {
                        window.userState[k] = d[k];
                    }
                });
                window.userState.last_sync_time = Date.now();
            } finally {
                isFirebaseUpdating = false;
                window.updateUI();
                if (typeof window.updateFarmUI === 'function') {
                    window.updateFarmUI();
                }
                window.dispatchEvent(new CustomEvent('userStateUpdated', { detail: window.userState }));
            }
        }, err => console.error("Firebase Sync Error:", err));
    } catch (e) {
        console.warn("Realtime sync omitted:", e);
    }
};

// ==========================================
// 6. دالة إدارة عداد التجميع
// ==========================================
let claimCooldownTimer = null;

window.updateClaimButtonState = function() {
    const claimButtons = document.querySelectorAll('#claim-btn, .claim-btn, [data-action="claim"]');
    if (!claimButtons.length) return;

    const COOLDOWN_SECONDS = 15;
    const lastClaimStr = window.userState.last_claim_time;
    const unclaimed = parseFloat(window.userState?.unclaimed || 0);

    const isFarmTab = document.getElementById('view-farm')?.classList.contains('active');

    function renderButton(btn, disabled, text, className) {
        btn.disabled = disabled;
        btn.innerHTML = text;
        if (className) btn.className = className;
    }

    if (!lastClaimStr) {
        claimButtons.forEach(btn => {
            if (isFarmTab && unclaimed <= 0) {
                renderButton(btn, true, `المخزن فارغ ⏳`, "claim-action-btn btn-disabled");
            } else {
                renderButton(btn, false, `تجميع الرصيد 💰`, "claim-action-btn btn-ready");
            }
        });
        return;
    }

    const lastClaimMs = new Date(lastClaimStr).getTime();
    if (isNaN(lastClaimMs)) {
        claimButtons.forEach(btn => renderButton(btn, false, `تجميع الرصيد 💰`, "claim-action-btn btn-ready"));
        return;
    }

    const currentServerMs = Date.now() + (window.serverTimeOffset || 0);
    const secondsPassed = Math.floor((currentServerMs - lastClaimMs) / 1000);
    const remainingSeconds = COOLDOWN_SECONDS - secondsPassed;

    if (claimCooldownTimer) clearInterval(claimCooldownTimer);

    if (remainingSeconds > 0) {
        let currentCountdown = remainingSeconds;
        
        claimButtons.forEach(btn => {
            renderButton(btn, true, `انتظر ${window.formatTime(currentCountdown)} ⏳`, "claim-action-btn btn-disabled");
        });

        claimCooldownTimer = setInterval(() => {
            currentCountdown--;
            if (currentCountdown > 0) {
                claimButtons.forEach(btn => {
                    renderButton(btn, true, `انتظر ${window.formatTime(currentCountdown)} ⏳`, "claim-action-btn btn-disabled");
                });
            } else {
                clearInterval(claimCooldownTimer);
                claimCooldownTimer = null;
                const latestUnclaimed = parseFloat(window.userState?.unclaimed || 0);
                claimButtons.forEach(btn => {
                    if (isFarmTab && latestUnclaimed <= 0) {
                        renderButton(btn, true, `المخزن فارغ ⏳`, "claim-action-btn btn-disabled");
                    } else {
                        renderButton(btn, false, `تجميع الرصيد 💰`, "claim-action-btn btn-ready");
                    }
                });
            }
        }, 1000);
    } else {
        claimButtons.forEach(btn => {
            if (isFarmTab && unclaimed <= 0) {
                renderButton(btn, true, `المخزن فارغ ⏳`, "claim-action-btn btn-disabled");
            } else {
                renderButton(btn, false, `تجميع الرصيد 💰`, "claim-action-btn btn-ready");
            }
        });
    }
};

// ==========================================
// 7. العداد البصري التدريجي + تقييد الخانات العشرية (Max 2 Decimals)
// ==========================================
window.formatBalance = function(val) {
    if (val === undefined || val === null || isNaN(val)) return '0.00';
    const num = parseFloat(val);
    return num.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });
};

window.formatNumberHTML = function(val) {
    if (val === undefined || val === null || isNaN(val)) return '0.00';
    let num = parseFloat(val);
    let suffix = '';
    if (Math.abs(num) >= 1e9) { num /= 1e9; suffix = 'B'; }
    else if (Math.abs(num) >= 1e6) { num /= 1e6; suffix = 'M'; }

    const formattedStr = num.toLocaleString('en-US', { 
        minimumFractionDigits: 2, 
        maximumFractionDigits: 2 
    });
    return `${formattedStr}${suffix}`;
};

let visualBalance = null;
let animationFrameId = null;

function startLocalMiningSimulator() {
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    
    function tick() {
        const targetVal = parseFloat(window.userState?.balance || 0);
        renderSmoothBalance(targetVal);
        animationFrameId = requestAnimationFrame(tick);
    }
    animationFrameId = requestAnimationFrame(tick);
}

function renderSmoothBalance(targetVal) {
    if (isNaN(targetVal)) targetVal = 0;

    if (visualBalance === null || isNaN(visualBalance)) {
        visualBalance = targetVal;
        applyBalanceToUI(visualBalance);
        return;
    }

    const diff = targetVal - visualBalance;
    if (Math.abs(diff) < 0.005) {
        visualBalance = targetVal;
    } else {
        visualBalance += diff * 0.08;
    }
    applyBalanceToUI(visualBalance);
}

function applyBalanceToUI(val) {
    const formatted = window.formatNumberHTML(val);
    const rawFormatted = window.formatBalance(val);
    
    const selectors = '[data-bind="balance"], .user-balance, #farm-balance, #user-balance, #main-balance, #balance, .sync-balance, #top-balance-tasks, .user-balance-val, [data-bind="user_balance"]';
    
    document.querySelectorAll(selectors).forEach(el => {
        if (el.id === 'shop-balance-text' || el.id === 'top-balance-games') return;

        if (el.tagName === 'INPUT') {
            el.value = rawFormatted;
        } else if (el.id === 'top-balance-tasks') {
            el.innerText = `ZN ${rawFormatted}`;
        } else {
            if (el.classList.contains('plain-text')) {
                el.innerText = `${rawFormatted} ZN`;
            } else {
                el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">${formatted} ZN</span>`;
            }
        }
    });
}

window.updateUI = function() {
    window.updateClaimButtonState();
    window.updateTonPriceUI();

    const currentMaxCap = parseFloat(window.userState.max_cap ?? 100);
    document.querySelectorAll('#storage-max, .max-storage-val, [data-bind="max_cap"], #farm-storage-max').forEach(el => {
        if (el.tagName === 'INPUT') {
            el.value = currentMaxCap.toFixed(2);
        } else {
            el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">${window.formatBalance(currentMaxCap)}</span>`;
        }
    });

    const adBal = parseFloat(window.userState.ad_balance || 0);
    const formattedAd = window.formatBalance(adBal);
    document.querySelectorAll('#ad-balance-display, .ad-balance-val, [data-bind="ad_balance"]').forEach(el => {
        if (el.id === 'ad-balance-display') {
            el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">AdZN ${formattedAd}</span>`;
        } else {
            el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">${formattedAd}</span>`;
        }
    });

    const usdBal = parseFloat(window.userState.usd_balance || 0);
    const formattedUsd = window.formatBalance(usdBal);
    document.querySelectorAll('.usd-balance-val, [data-bind="usd_balance"]').forEach(el => {
        if (el.id === 'shop-usd-text') return;
        el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">$${formattedUsd}</span>`;
    });

    if (visualBalance === null && window.userState?.balance !== undefined) {
        visualBalance = parseFloat(window.userState.balance) || 0;
        applyBalanceToUI(visualBalance);
    }
};

// ==========================================
// 8. التنقل بين القوائم
// ==========================================
const loadedModules = new Set();

window.switchView = async function(viewName) {
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
    const targetNav = document.getElementById(`nav-${viewName}`);
    if (targetNav) targetNav.classList.add('active');

    document.querySelectorAll('.game-view').forEach(v => v.classList.remove('active'));
    const targetView = document.getElementById(`view-${viewName}`);
    if (!targetView) return;
    
    targetView.classList.add('active');

    if (!loadedModules.has(viewName)) {
        try {
            const res = await fetch(`${viewName}/${viewName}.html`);
            if (res.ok) {
                const htmlContent = await res.text();
                targetView.innerHTML = htmlContent;
                await loadModuleScript(`${viewName}/${viewName}.js`);
                loadedModules.add(viewName);
            }
        } catch (err) {
            console.error(`خطأ تحميل ${viewName}:`, err);
        }
    }

    if (viewName === 'farm' && typeof window.onFarmTabOpen === 'function') {
        window.onFarmTabOpen();
    }

    if (viewName === 'shop' && typeof window.updateShopUI === 'function') {
        window.updateShopUI();
    }

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
// 9. بدء التطبيق
// ==========================================
window.loadUserData = async function() {
    try {
        const startParam = tg?.initDataUnsafe?.start_param || null;
        const d = await window.fetchAPI('/api/farm/player_data', 'POST', {
            referrer_id: startParam,
            first_name: tg?.initDataUnsafe?.user?.first_name || "لاعب"
        });
        if (d?.success) {
            const u = d.player || d.user || d.data || {};
            Object.assign(window.userState, u);
        }
    } catch (err) {
        console.error("Error player_data:", err);
    } finally { 
        window.updateUI();
        if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
        hideLoadingScreen();
    }
};

function initApp() {
    window.updateUI();
    window.fetchTonPrice();
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

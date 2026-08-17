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
    if (appEl) {
        appEl.style.display = 'block';
        appEl.style.visibility = 'visible';
        appEl.style.opacity = '1';
    }
    if (navEl) {
        navEl.style.display = 'flex';
        navEl.style.visibility = 'visible';
        navEl.style.opacity = '1';
    }

    const loaders = document.querySelectorAll('#loading-screen, .loading-screen, #loader');
    loaders.forEach(el => {
        el.style.opacity = '0';
        el.style.transition = 'opacity 0.2s ease';
        setTimeout(() => {
            try { el.remove(); } catch(e){}
        }, 200);
    });
}
window.hideLoadingScreen = hideLoadingScreen;

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
let saveDebounceTimer = null;

function persistUserStateToLocalStorage(state) {
    try {
        localStorage.setItem('app_user_state', JSON.stringify(state));
    } catch (e) {
        console.warn("فشل الحفظ في localStorage:", e);
    }
}

window.userState = new Proxy(getSavedState(), {
    set(target, prop, value) {
        if (['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'extra_storage', 'max_cap', 'unclaimed'].includes(prop)) {
            const num = parseFloat(value);
            value = isNaN(num) ? 0.0 : num;
        }

        if (target[prop] === value && typeof value !== 'object') {
            return true;
        }

        target[prop] = value;
        
        if (!window.PlayerData) window.PlayerData = {};
        window.PlayerData[prop] = target[prop];

        if (['balance', 'usd_balance', 'ad_balance', 'hourly_rate', 'energy', 'storage_level', 'extra_storage', 'max_cap', 'daily_streak', 'daily_day', 'upgrades', 'last_claim_time', 'unclaimed', 'boost_multiplier', 'boost_active', 'boost_expires_at', 'wallet_address'].includes(prop)) {
            
            if (!isFirebaseUpdating) {
                if (saveDebounceTimer) clearTimeout(saveDebounceTimer);
                saveDebounceTimer = setTimeout(() => {
                    persistUserStateToLocalStorage(target);
                }, 400);
            }

            if (typeof window.updateUI === 'function') window.updateUI();
            if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
            
            window.dispatchEvent(new CustomEvent('userStateUpdated', { detail: target }));
        }
        return true;
    }
});

window.addEventListener('beforeunload', () => {
    persistUserStateToLocalStorage(window.userState);
});

// ==========================================
// 2. الاتصال بالسيرفر ومعالجة الاستجابة المباشرة
// ==========================================
window.fetchAPI = async function(endpoint, method = 'GET', bodyData = null) {
    const headers = { 'Content-Type': 'application/json' };
    
    if (window.userState?.tg_id) {
        headers['X-Telegram-User-Id'] = String(window.userState.tg_id);
    }
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
        
        if (targetObj) {
            isFirebaseUpdating = true;
            try {
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
                if (targetObj.wallet_address !== undefined) window.userState.wallet_address = targetObj.wallet_address;
            } finally {
                isFirebaseUpdating = false;
                persistUserStateToLocalStorage(window.userState);
            }
        }

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
// 5. الاستماع اللحظي المحصن Firestore (Realtime Sync & Cost Savings)
// ==========================================
window._firebaseUnsubscribe = null;

window.initFirebaseRealtimeSync = function(userId) {
    if (!window.db || !userId) return;
    
    if (window._firebaseUnsubscribe) {
        window._firebaseUnsubscribe();
        window._firebaseUnsubscribe = null;
    }

    try {
        window._firebaseUnsubscribe = window.db.collection('users').doc(String(userId)).onSnapshot(doc => {
            if (!doc.exists) return;
            const d = doc.data() || {};
            
            try {
                isFirebaseUpdating = true;
                if (!window.PlayerData) window.PlayerData = {};
                
                Object.assign(window.PlayerData, d);

                if (d.balance !== undefined && d.balance !== null) {
                    const bal = parseFloat(d.balance);
                    if (!isNaN(bal) && window.userState.balance !== bal) window.userState.balance = bal;
                }
                if (d.usd_balance !== undefined) {
                    const u = parseFloat(d.usd_balance) || 0;
                    if (window.userState.usd_balance !== u) window.userState.usd_balance = u;
                }
                
                ['ad_balance', 'hourly_rate', 'energy', 'storage_level', 'extra_storage', 'max_cap', 'daily_streak', 'daily_day', 'last_daily_claim_date', 'upgrades', 'last_claim_time', 'unclaimed', 'boost_multiplier', 'boost_active', 'boost_expires_at', 'wallet_address'].forEach(k => {
                    if (d[k] !== undefined && window.userState[k] !== d[k]) {
                        window.userState[k] = d[k];
                    }
                });
                window.userState.last_sync_time = Date.now();
            } finally {
                isFirebaseUpdating = false;
                persistUserStateToLocalStorage(window.userState);
                if (typeof window.updateUI === 'function') window.updateUI();
                if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
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
        if (claimCooldownTimer) { clearInterval(claimCooldownTimer); claimCooldownTimer = null; }
        return;
    }

    const lastClaimMs = new Date(lastClaimStr).getTime();
    if (isNaN(lastClaimMs)) {
        claimButtons.forEach(btn => renderButton(btn, false, `تجميع الرصيد 💰`, "claim-action-btn btn-ready"));
        if (claimCooldownTimer) { clearInterval(claimCooldownTimer); claimCooldownTimer = null; }
        return;
    }

    const currentServerMs = Date.now() + (window.serverTimeOffset || 0);
    const secondsPassed = Math.floor((currentServerMs - lastClaimMs) / 1000);
    const remainingSeconds = COOLDOWN_SECONDS - secondsPassed;

    if (remainingSeconds <= 0) {
        if (claimCooldownTimer) { clearInterval(claimCooldownTimer); claimCooldownTimer = null; }
        claimButtons.forEach(btn => {
            if (isFarmTab && unclaimed <= 0) {
                renderButton(btn, true, `المخزن فارغ ⏳`, "claim-action-btn btn-disabled");
            } else {
                renderButton(btn, false, `تجميع الرصيد 💰`, "claim-action-btn btn-ready");
            }
        });
        return;
    }

    if (!claimCooldownTimer) {
        claimCooldownTimer = setInterval(() => {
            const nowMs = Date.now() + (window.serverTimeOffset || 0);
            const passed = Math.floor((nowMs - lastClaimMs) / 1000);
            const rem = COOLDOWN_SECONDS - passed;

            if (rem > 0) {
                claimButtons.forEach(btn => {
                    renderButton(btn, true, `انتظر ${window.formatTime(rem)} ⏳`, "claim-action-btn btn-disabled");
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
    }
};

// ==========================================
// 7. العداد البصري التدريجي الموفر للطاقة
// ==========================================
window.formatBalance = function(val) {
    if (val === undefined || val === null || isNaN(val)) return '0.00';
    const num = parseFloat(val);
    
    return num.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 6
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
        maximumFractionDigits: 6 
    });
    return `${formattedStr}${suffix}`;
};

let visualBalance = null;
let animationFrameId = null;

function startLocalMiningSimulator() {
    if (animationFrameId) cancelAnimationFrame(animationFrameId);
    
    function tick() {
        if (!document.hidden) {
            const targetVal = parseFloat(window.userState?.balance || 0);
            renderSmoothBalance(targetVal);
        }
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
    if (Math.abs(diff) > 10 || Math.abs(diff) < 0.000001) {
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
// 8. تهيئة واجهة المحفظة والإعدادات
// ==========================================
window.initWalletView = function() {
    const walletView = document.getElementById('view-wallet');
    if (walletView) {
        const addrInput = walletView.querySelector('#wallet-address-input, #wallet-address, [name="wallet_address"]');
        if (addrInput && window.userState?.wallet_address) {
            addrInput.value = window.userState.wallet_address;
        }
    }
};
window.onWalletTabOpen = window.initWalletView;

window.initSettingsView = function() {
    const settingsView = document.getElementById('view-settings');
    if (settingsView) {
        const nameEl = settingsView.querySelector('#settings-user-name');
        const idEl = settingsView.querySelector('#settings-user-id');
        if (nameEl && window.userState?.first_name) nameEl.innerText = window.userState.first_name;
        if (idEl && window.userState?.tg_id) idEl.innerText = window.userState.tg_id;
    }
};

window.saveWalletAddress = async function() {
    const input = document.querySelector('#wallet-address-input, #wallet-address');
    if (input) {
        const addr = input.value.trim();
        if (!addr) {
            alert('يرجى إدخال عنوان محفظة صحيح');
            return;
        }
        try {
            const res = await window.fetchAPI('/api/wallet/save_address', 'POST', { wallet_address: addr });
            if (res && res.success) {
                window.userState.wallet_address = addr;
                alert('تم حفظ عنوان المحفظة بنجاح!');
            } else {
                alert(res?.error || 'فشل حفظ العنوان في السيرفر');
            }
        } catch (err) {
            window.userState.wallet_address = addr;
            alert('تم حفظ العنوان محلياً');
        }
    }
};

// ==========================================
// 9. التنقل الديناميكي المحصن
// ==========================================
const loadedModules = new Set();
const pendingLoads = new Map();

function renderDefaultViewContent(cleanViewName, targetView) {
    if (cleanViewName === 'settings') {
        targetView.innerHTML = `
            <div style="padding: 20px; color: #ffffff; text-align: center; direction: rtl; max-width: 500px; margin: 0 auto;">
                <h2 style="margin-bottom: 20px; color: #0088cc;"><i class="fas fa-cog"></i> الإعدادات (Settings)</h2>
                <div style="background: rgba(255, 255, 255, 0.08); padding: 20px; border-radius: 14px; text-align: right; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
                    <p style="margin-bottom: 12px; font-size: 15px;">👤 <b>اسم اللاعب:</b> <span id="settings-user-name">${window.userState?.first_name || 'لاعب'}</span></p>
                    <p style="margin-bottom: 12px; font-size: 15px;">🆔 <b>معرّف تليجرام:</b> <span id="settings-user-id">${window.userState?.tg_id || 'غير معروف'}</span></p>
                </div>
            </div>`;
    }
}

async function loadModuleScript(jsPath) {
    return new Promise((resolve) => {
        if (document.querySelector(`script[src="${jsPath}"]`)) {
            resolve(true);
            return;
        }
        const script = document.createElement('script');
        script.src = jsPath;
        script.onload = () => resolve(true);
        script.onerror = () => {
            console.warn(`فشل تحميل السكريبت: ${jsPath}`);
            resolve(false);
        };
        document.body.appendChild(script);
    });
}

window.switchView = async function(viewName) {
    if (!viewName) return;

    let cleanViewName = String(viewName).toLowerCase().replace('nav-', '').replace('view-', '');
    if (cleanViewName === 'wallets' || cleanViewName === 'tools' || cleanViewName === 'wallet') cleanViewName = 'wallet';
    if (cleanViewName === 'game') cleanViewName = 'games';
    if (cleanViewName === 'task') cleanViewName = 'tasks';
    if (cleanViewName === 'user' || cleanViewName === 'friends' || cleanViewName === 'friend') cleanViewName = 'friends';

    // 1. إخفاء شاشة التحميل فوراً
    hideLoadingScreen();

    // 2. تحديث إضاءة أزرار القائمة السفلى
    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
    const targetNav = document.getElementById(`nav-${cleanViewName}`) || 
                      document.querySelector(`[data-view="${cleanViewName}"]`) ||
                      document.querySelector(`[data-view="${viewName}"]`);
    if (targetNav) targetNav.classList.add('active');

    // 3. إخفاء الشاشات الأخرى وتفعيل الحاوية الحالية
    document.querySelectorAll('.game-view, [id^="view-"]').forEach(v => {
        v.classList.remove('active');
        v.style.display = 'none';
    });
    
    let targetView = document.getElementById(`view-${cleanViewName}`);
    
    if (!targetView) {
        const appContainer = document.getElementById('app') || document.body;
        targetView = document.createElement('div');
        targetView.id = `view-${cleanViewName}`;
        targetView.className = 'game-view';
        appContainer.appendChild(targetView);
    }
    
    targetView.classList.add('active');
    targetView.style.display = 'block';
    targetView.style.width = '100%';
    targetView.style.minHeight = '100vh';

    // 4. جلب المحتوى إن لم يكن موجوداً
    const hasRealContent = targetView.innerText.trim().length > 10 || targetView.querySelector('button, input, h1, h2, h3, h4');

    if (!loadedModules.has(cleanViewName) && !hasRealContent) {
        if (pendingLoads.has(cleanViewName)) {
            await pendingLoads.get(cleanViewName);
        } else {
            const loadPromise = (async () => {
                const cacheBuster = `?v=${Date.now()}`;
                let loadedSuccessfully = false;

                try {
                    const pathsToTry = [
                        `./${cleanViewName}/${cleanViewName}.html${cacheBuster}`,
                        `/${cleanViewName}/${cleanViewName}.html${cacheBuster}`,
                        `./${cleanViewName}.html${cacheBuster}`
                    ];
                    
                    let htmlContent = null;
                    for (const p of pathsToTry) {
                        try {
                            const res = await fetch(p);
                            if (res.ok) {
                                const txt = await res.text();
                                if (txt && txt.trim().length > 10) {
                                    htmlContent = txt;
                                    break;
                                }
                            }
                        } catch (e) {}
                    }

                    if (htmlContent) {
                        targetView.innerHTML = htmlContent;
                        
                        // إعادة تشغيل عناصر السكريبت المضمنة إن وجدت
                        const inlineScripts = targetView.querySelectorAll('script');
                        inlineScripts.forEach(s => {
                            const newScript = document.createElement('script');
                            if (s.src) newScript.src = s.src;
                            else newScript.textContent = s.textContent;
                            document.body.appendChild(newScript);
                        });

                        const jsPathsToTry = [
                            `./${cleanViewName}/${cleanViewName}.js${cacheBuster}`,
                            `/${cleanViewName}/${cleanViewName}.js${cacheBuster}`
                        ];
                        for (const jsP of jsPathsToTry) {
                            const loaded = await loadModuleScript(jsP);
                            if (loaded) break;
                        }

                        loadedModules.add(cleanViewName);
                        loadedSuccessfully = true;
                    }
                } catch (e) {
                    console.warn(`فشل جلب ملف ${cleanViewName} خارجي:`, e);
                }

                if (!loadedSuccessfully) {
                    renderDefaultViewContent(cleanViewName, targetView);
                }
            })();

            pendingLoads.set(cleanViewName, loadPromise);
            try {
                await loadPromise;
            } finally {
                pendingLoads.delete(cleanViewName);
            }
        }
    }

    // 5. تشغيل دالة التهيئة المخصصة للتبويب فورياً
    try {
        if (cleanViewName === 'farm' && typeof window.onFarmTabOpen === 'function') {
            window.onFarmTabOpen();
        } else if (cleanViewName === 'shop' && typeof window.updateShopUI === 'function') {
            window.updateShopUI();
        } else if (cleanViewName === 'games' && typeof window.onGamesTabOpen === 'function') {
            window.onGamesTabOpen();
        } else if (cleanViewName === 'friends') {
            if (typeof window.initFriendsView === 'function') window.initFriendsView();
            else if (typeof window.onFriendsTabOpen === 'function') window.onFriendsTabOpen();
        } else if (cleanViewName === 'wallet') {
            // تشغيل موديل المحفظة المخصص
            if (window.walletModule && typeof window.walletModule.init === 'function') {
                window.walletModule.init();
            }
            if (typeof window.initWallet === 'function') window.initWallet();
            if (typeof window.initWalletView === 'function') window.initWalletView();
            if (typeof window.onWalletTabOpen === 'function') window.onWalletTabOpen();
            if (typeof window.loadWalletData === 'function') window.loadWalletData();
        } else if (cleanViewName === 'settings') {
            if (typeof window.initSettingsView === 'function') window.initSettingsView();
        }
    } catch (err) {
        console.error("خطأ أثناء تشغيل تهيئة التبويب:", err);
    }

    if (typeof window.updateUI === 'function') window.updateUI();
};

// ==========================================
// 10. التشغيل المباشر عند بدء الصفحة
// ==========================================
document.addEventListener('DOMContentLoaded', async () => {
    hideLoadingScreen();
    startLocalMiningSimulator();
    window.fetchTonPrice();

    try {
        await window.fetchAPI('/api/user/info');
    } catch (e) {
        console.warn("⚠️ تعذر جلب بيانات المستخدم المبدئية عند الإقلاع:", e);
    }

    if (window.userState?.tg_id) {
        window.initFirebaseRealtimeSync(window.userState.tg_id);
    }

    document.querySelectorAll('.nav-item, [data-view]').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const view = btn.getAttribute('data-view') || btn.id.replace('nav-', '');
            if (view) window.switchView(view);
        });
    });

    window.switchView('farm');
});

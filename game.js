// ==========================================
// 1. التهيئة والتخزين المحلي (Local-First Architecture)
// ==========================================
const tg = window.Telegram?.WebApp;
if (tg) {
    tg.ready(); 
    tg.expand();
    if (tg.enableClosingConfirmation) tg.enableClosingConfirmation();
}

// دالة الحماية المباشرة ضد هجمات XSS وحقن النصوص
function escapeHTML(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
window.escapeHTML = escapeHTML;

// رابط السيرفر الأساسي لمنع أخطاء المسارات النسبية
window.API_BASE_URL = window.API_BASE_URL || 'https://zn-goxe-production.up.railway.app';
window.currentTonPriceUSD = parseFloat(localStorage.getItem('last_ton_price')) || 1.32;
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
    const user = tg?.initDataUnsafe?.user;
    const startParam = tg?.initDataUnsafe?.start_param || null;
    const base = {
        tg_id: user?.id || null,
        first_name: user?.first_name || (user?.username ? `@${user.username}` : "لاعب"),
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
    
    const currentTgId = window.userState?.tg_id || tg?.initDataUnsafe?.user?.id;
    if (currentTgId) {
        if (!window.userState.tg_id) window.userState.tg_id = currentTgId;
        headers['X-Telegram-User-Id'] = String(currentTgId);
    }

    if (tg?.initData) {
        headers['X-Telegram-Init-Data'] = tg.initData;
        headers['Authorization'] = `Bearer ${tg.initData}`;
    }

    let targetUrl = endpoint;
    if (endpoint.startsWith('/')) {
        const baseUrl = (window.API_BASE_URL || '').replace(/\/$/, '');
        targetUrl = baseUrl + endpoint;
    }

    try {
        const urlObj = new URL(targetUrl, window.location.href);
        if (tg?.initData) urlObj.searchParams.set('initData', tg.initData);
        if (currentTgId) urlObj.searchParams.set('tg_id', String(currentTgId));
        targetUrl = urlObj.toString();
    } catch (e) {}

    try {
        const fetchOptions = { method, headers };
        if (method !== 'GET' && method !== 'HEAD' && bodyData) {
            fetchOptions.body = JSON.stringify(bodyData);
        }

        const res = await fetch(targetUrl, fetchOptions);
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
                if (targetObj.telegram_id !== undefined && targetObj.telegram_id !== null) {
                    window.userState.tg_id = targetObj.telegram_id;
                }
                if (targetObj.first_name !== undefined) window.userState.first_name = targetObj.first_name;
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
        console.error(`API Error [${targetUrl}]:`, err);
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
        console.warn("⚠️ لم يتم جلب سعر TON، تم استخدام السعر المحلي:", window.currentTonPriceUSD);
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
    packagesStatus.forEach(el => { el.style.display = 'none'; });
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
// 5. الاستماع اللحظي المحصن Firestore
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

    if (claimCooldownTimer) {
        clearInterval(claimCooldownTimer);
        claimCooldownTimer = null;
    }

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

    if (remainingSeconds <= 0) {
        claimButtons.forEach(btn => {
            if (isFarmTab && unclaimed <= 0) {
                renderButton(btn, true, `المخزن فارغ ⏳`, "claim-action-btn btn-disabled");
            } else {
                renderButton(btn, false, `تجميع الرصيد 💰`, "claim-action-btn btn-ready");
            }
        });
        return;
    }

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
};

// ==========================================
// 7. العداد البصري التدريجي وتنسيق الأرقام
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
    if (val === undefined || val === null || isNaN(val)) {
        return `0<span style="font-size:0.8em; opacity:0.75; font-weight:normal;">.00</span>`;
    }
    let num = parseFloat(val);
    let suffix = '';
    if (Math.abs(num) >= 1e9) { num /= 1e9; suffix = 'B'; }
    else if (Math.abs(num) >= 1e6) { num /= 1e6; suffix = 'M'; }

    const formattedStr = num.toLocaleString('en-US', { 
        minimumFractionDigits: 2, 
        maximumFractionDigits: 6 
    });

    const parts = formattedStr.split('.');
    if (parts.length > 1) {
        return `${parts[0]}<span style="font-size:0.8em; opacity:0.75; font-weight:normal;">.${parts[1]}</span>${suffix}`;
    }
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
    
    const selectors = '[data-bind="balance"], [data-bind="znx_balance"], .user-balance, #farm-balance, #user-balance, #main-balance, #balance, .sync-balance, #top-balance-tasks, .user-balance-val, [data-bind="user_balance"]';
    
    document.querySelectorAll(selectors).forEach(el => {
        if (el.id === 'shop-balance-text' || el.id === 'top-balance-games') return;

        if (el.tagName === 'INPUT') {
            el.value = rawFormatted;
        } else if (el.id === 'top-balance-tasks') {
            el.innerHTML = `ZN ${formatted}`;
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
            el.value = window.formatBalance(currentMaxCap);
        } else {
            el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">${window.formatNumberHTML(currentMaxCap)}</span>`;
        }
    });

    const adBal = parseFloat(window.userState.ad_balance || 0);
    const formattedAd = window.formatNumberHTML(adBal);
    const rawAd = window.formatBalance(adBal);
    document.querySelectorAll('#ad-balance-display, .ad-balance-val, [data-bind="ad_balance"]').forEach(el => {
        if (el.tagName === 'INPUT') {
            el.value = rawAd;
        } else if (el.id === 'ad-balance-display') {
            el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">AdZN ${formattedAd}</span>`;
        } else {
            el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">${formattedAd}</span>`;
        }
    });

    const usdBal = parseFloat(window.userState.usd_balance || 0);
    const formattedUsd = window.formatNumberHTML(usdBal);
    const rawUsd = window.formatBalance(usdBal);
    document.querySelectorAll('.usd-balance-val, [data-bind="usd_balance"]').forEach(el => {
        if (el.id === 'shop-usd-text') return;
        if (el.tagName === 'INPUT') {
            el.value = rawUsd;
        } else {
            el.innerHTML = `<span dir="ltr" style="white-space:nowrap;">$${formattedUsd}</span>`;
        }
    });

    if (visualBalance === null && window.userState?.balance !== undefined) {
        visualBalance = parseFloat(window.userState.balance) || 0;
        applyBalanceToUI(visualBalance);
    }
};

// ==========================================
// 8. الإعدادات والعروض
// ==========================================
window.initSettingsView = function() {
    const settingsView = document.getElementById('view-settings');
    if (settingsView) {
        const nameEl = settingsView.querySelector('#settings-user-name');
        const idEl = settingsView.querySelector('#settings-user-id');
        if (nameEl && window.userState?.first_name) nameEl.innerText = window.escapeHTML(window.userState.first_name);
        if (idEl && window.userState?.tg_id) idEl.innerText = window.escapeHTML(window.userState.tg_id);
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

window.openOfferCategory = function(offerId) {
    if (window.offersModule && typeof window.offersModule.openCategory === 'function') {
        window.offersModule.openCategory(offerId);
    } else {
        window.dispatchEvent(new CustomEvent('openOfferCategory', { detail: { offerId } }));
    }
};

// ==========================================
// 9. دالة جلب وعرض بيانات محفظة ZNX والمتصدرين (/api/znx-wallet)
// ==========================================
window.loadZnxWalletData = async function() {
    const listContainer = document.getElementById('lb-list-container') || document.getElementById('znx-lb-list');
    const pod1Name = document.getElementById('pod1-name');
    const pod1Score = document.getElementById('pod1-score');
    const pod2Name = document.getElementById('pod2-name');
    const pod2Score = document.getElementById('pod2-score');
    const pod3Name = document.getElementById('pod3-name');
    const pod3Score = document.getElementById('pod3-score');
    const myRankVal = document.getElementById('my-rank-val');
    const myRankBalance = document.getElementById('my-rank-balance');

    if (listContainer) {
        listContainer.innerHTML = '<div style="text-align: center; padding: 20px; color: #888;">جاري تحميل بيانات محفظة ZNX والمتصدرين...</div>';
    }

    try {
        const res = await window.fetchAPI('/api/znx-wallet');
        if (!res || (!res.success && !Array.isArray(res.leaderboard))) {
            if (listContainer) listContainer.innerHTML = '<div style="text-align: center; padding: 20px; color: #ff4d4d;">فشل جلب قائمة محفظة ZNX.</div>';
            return;
        }

        const leaderboard = res.leaderboard || res.users || res.data || [];
        const myRank = res.my_rank ?? res.user_rank ?? '#--';
        const myBal = res.my_balance ?? res.balance ?? window.userState?.balance ?? 0;

        if (res.my_balance !== undefined && !isNaN(parseFloat(res.my_balance))) {
            window.userState.balance = parseFloat(res.my_balance);
        } else if (res.balance !== undefined && !isNaN(parseFloat(res.balance))) {
            window.userState.balance = parseFloat(res.balance);
        }

        if (myRankVal) myRankVal.innerText = (typeof myRank === 'number') ? `#${myRank}` : myRank;
        if (myRankBalance) myRankBalance.innerHTML = `${window.formatNumberHTML(myBal)} ZN`;

        if (pod1Name) pod1Name.innerText = '---';
        if (pod1Score) pod1Score.innerText = '0 ZN';
        if (pod2Name) pod2Name.innerText = '---';
        if (pod2Score) pod2Score.innerText = '0 ZN';
        if (pod3Name) pod3Name.innerText = '---';
        if (pod3Score) pod3Score.innerText = '0 ZN';

        if (leaderboard.length > 0) {
            const p1 = leaderboard[0];
            if (pod1Name) pod1Name.innerText = window.escapeHTML(p1.first_name || p1.username || `لاعب ${p1.telegram_id || 1}`);
            if (pod1Score) pod1Score.innerHTML = `${window.formatNumberHTML(p1.balance || 0)} ZN`;
        }
        if (leaderboard.length > 1) {
            const p2 = leaderboard[1];
            if (pod2Name) pod2Name.innerText = window.escapeHTML(p2.first_name || p2.username || `لاعب ${p2.telegram_id || 2}`);
            if (pod2Score) pod2Score.innerHTML = `${window.formatNumberHTML(p2.balance || 0)} ZN`;
        }
        if (leaderboard.length > 2) {
            const p3 = leaderboard[2];
            if (pod3Name) pod3Name.innerText = window.escapeHTML(p3.first_name || p3.username || `لاعب ${p3.telegram_id || 3}`);
            if (pod3Score) pod3Score.innerHTML = `${window.formatNumberHTML(p3.balance || 0)} ZN`;
        }

        if (listContainer) {
            if (leaderboard.length === 0) {
                listContainer.innerHTML = '<div style="text-align: center; padding: 20px; color: #888;">لا يوجد لاعبون حالياً.</div>';
                return;
            }

            let html = '';
            leaderboard.forEach((item, index) => {
                const rank = index + 1;
                const safeName = window.escapeHTML(item.first_name || item.username || `لاعب ${item.telegram_id || rank}`);
                const bal = parseFloat(item.balance || 0);
                const isMe = String(item.telegram_id) === String(window.userState?.tg_id);

                let rankBadge = `#${rank}`;
                if (rank === 1) rankBadge = '🥇';
                else if (rank === 2) rankBadge = '🥈';
                else if (rank === 3) rankBadge = '🥉';

                html += `
                    <div style="background: ${isMe ? 'rgba(0, 136, 204, 0.2)' : 'rgba(22, 27, 34, 0.8)'}; border: 1px solid ${isMe ? '#0088cc' : 'rgba(255,255,255,0.08)'}; border-radius: 12px; padding: 10px 14px; display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <span style="font-weight: bold; font-size: 14px; min-width: 28px; text-align: center; color: ${rank <= 3 ? '#ffb703' : '#a0a0a0'};">${rankBadge}</span>
                            <div style="text-align: right;">
                                <div style="font-weight: bold; font-size: 13px; color: #fff;">${safeName} ${isMe ? ' <span style="font-size:10px; color:#0088cc;">(أنت)</span>' : ''}</div>
                                <div style="font-size: 10px; color: #888;">ID: ${window.escapeHTML(item.telegram_id || '---')}</div>
                            </div>
                        </div>
                        <div style="font-weight: bold; font-size: 13px; color: #2ec4b6;">
                            ${window.formatNumberHTML(bal)} ZN
                        </div>
                    </div>
                `;
            });

            listContainer.innerHTML = html;
        }
    } catch (err) {
        console.error("فشل جلب بيانات محفظة ZNX والمتصدرين:", err);
        if (listContainer) {
            listContainer.innerHTML = '<div style="text-align: center; padding: 20px; color: #ff4d4d;">حدث خطأ أثناء تحميل محفظة ZNX.</div>';
        }
    }
};

// ربط المسميات القديمة والحديثة بـ ZNX Wallet
window.loadLeaderboardData = window.loadZnxWalletData;
window.onLeaderboardTabOpen = window.loadZnxWalletData;
window.initLeaderboardView = window.loadZnxWalletData;
window.initZnxWalletView = window.loadZnxWalletData;
if (typeof window.initZnxWallet !== 'function') {
    window.initZnxWallet = window.loadZnxWalletData;
}

// ==========================================
// 10. محرك التنقل والتحميل الديناميكي المدمج (loadZnxWalletView)
// ==========================================
window.loadZnxWalletView = async function() {
    const container = document.getElementById('view-znx_wallet') || document.getElementById('view-leaderboard');
    if (!container) return;

    try {
        // 1. جلب وحقن HTML إذا لم يكن محملاً
        if (!container.innerHTML.trim() || container.children.length === 0) {
            const res = await fetch('./znx_wallet/znx_wallet.html?v=4.2');
            if (res.ok) {
                container.innerHTML = await res.text();
            }
        }

        // 2. تحميل ملف js الخاص بالنموذج مع معالجة تأخير الـ DOM
        if (!document.getElementById('znx-wallet-script')) {
            const script = document.createElement('script');
            script.id = 'znx-wallet-script';
            script.src = './znx_wallet/znx_wallet.js?v=4.2';
            script.onload = () => {
                setTimeout(() => { 
                    if (typeof window.initZnxWallet === 'function') window.initZnxWallet(); 
                }, 100);
            };
            document.body.appendChild(script);
        } else {
            setTimeout(() => {
                if (typeof window.initZnxWallet === 'function') {
                    window.initZnxWallet();
                }
            }, 50);
        }
    } catch (err) {
        console.error("❌ خطأ تحميل شاشة ZNX Wallet:", err);
    }
};

const loadedModules = new Set();
const pendingLoads = new Map();

function renderDefaultViewContent(cleanViewName, targetView) {
    if (cleanViewName === 'settings') {
        targetView.innerHTML = `
            <div style="padding: 20px; color: #ffffff; text-align: center; direction: rtl; max-width: 500px; margin: 0 auto;">
                <h2 style="margin-bottom: 20px; color: #0088cc;"><i class="fas fa-cog"></i> الإعدادات (Settings)</h2>
                <div style="background: rgba(255, 255, 255, 0.08); padding: 20px; border-radius: 14px; text-align: right; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
                    <p style="margin-bottom: 12px; font-size: 15px;">👤 <b>اسم اللاعب:</b> <span id="settings-user-name">${window.escapeHTML(window.userState?.first_name || 'لاعب')}</span></p>
                    <p style="margin-bottom: 12px; font-size: 15px;">🆔 <b>معرّف تليجرام:</b> <span id="settings-user-id">${window.escapeHTML(window.userState?.tg_id || 'غير معروف')}</span></p>
                </div>
            </div>`;
    } else if (cleanViewName === 'offers') {
        targetView.innerHTML = `
            <div style="padding: 15px; color: #ffffff; text-align: center; direction: rtl; max-width: 500px; margin: 0 auto; padding-bottom: 90px;">
                <div style="background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 16px; padding: 12px 16px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center;">
                    <div style="display: flex; align-items: center; gap: 8px;">
                        <span style="font-size: 22px;">💰</span>
                        <div style="text-align: right;">
                            <div style="font-size: 11px; color: #a0a0a0;">الرصيد الحالي</div>
                            <div class="user-balance-val" style="font-weight: bold; font-size: 16px; color: #fff;">0.00 ZN</div>
                        </div>
                    </div>
                    <div style="background: rgba(255, 183, 3, 0.15); color: #ffb703; padding: 6px 12px; border-radius: 20px; font-size: 12px; font-weight: bold;">
                        أرباح العروض 🔥
                    </div>
                </div>

                <h2 style="margin-bottom: 5px; color: #ffb703; font-size: 20px;"><i class="fas fa-gift"></i> قائمة أرباح العروض</h2>
                <p style="color: #a0a0a0; font-size: 12px; margin-bottom: 20px;">اختر من العروض المتاحة أدناه للبدء في كسب مكافآت ZN المباشرة</p>

                <div id="offers-grid-container" style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; text-align: center;">
                    <div class="offer-card-item" onclick="window.openOfferCategory('offer_goxe')" style="background: #161b22; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 20px 10px; position: relative; cursor: pointer;">
                        <span style="position: absolute; top: 8px; right: 8px; background: rgba(255, 183, 3, 0.2); color: #ffb703; font-size: 10px; padding: 2px 8px; border-radius: 10px; font-weight: bold;">ترند✨</span>
                        <div style="font-size: 38px; margin: 10px 0 6px 0; color: #2ec4b6;"><i class="fas fa-cubes"></i></div>
                        <div style="font-weight: bold; font-size: 14px; color: #fff;">عرض Goxe</div>
                    </div>
                    <div class="offer-card-item" onclick="window.openOfferCategory('offer_fogo')" style="background: #161b22; border: 1px solid rgba(255,255,255,0.1); border-radius: 16px; padding: 20px 10px; position: relative; cursor: pointer;">
                        <span style="position: absolute; top: 8px; right: 8px; background: rgba(255, 77, 77, 0.2); color: #ff4d4d; font-size: 10px; padding: 2px 8px; border-radius: 10px; font-weight: bold;">حار🔥</span>
                        <div style="font-size: 38px; margin: 10px 0 6px 0; color: #ff4d4d;"><i class="fas fa-fire"></i></div>
                        <div style="font-weight: bold; font-size: 14px; color: #fff;">عرض fogo</div>
                    </div>
                </div>
            </div>`;
    } else if (cleanViewName === 'znx_wallet') {
        targetView.innerHTML = `
            <div style="padding: 20px; color: #ffffff; text-align: center; direction: rtl; max-width: 500px; margin: 0 auto; padding-bottom: 90px;">
                <h2 style="margin-bottom: 5px; color: #ffb703;"><i class="fas fa-wallet"></i> محفظة ZNX ومتصدرين التطبيق</h2>
                <p style="color: #a0a0a0; font-size: 13px; margin-bottom: 20px;">عرض الرصيد، تحويل العملات، وشاشة كبار المطورين والمستثمرين</p>

                <div style="display: flex; justify-content: center; align-items: flex-end; gap: 10px; margin-bottom: 25px;">
                    <div style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15); border-radius: 12px; padding: 12px 8px; flex: 1; text-align: center;">
                        <span style="font-size: 24px;">🥈</span>
                        <div id="pod2-name" style="font-size: 12px; font-weight: bold; margin: 4px 0; color: #ddd;">---</div>
                        <div id="pod2-score" style="font-size: 11px; color: #2ec4b6; font-weight: bold;">0 ZN</div>
                    </div>
                    <div style="background: rgba(255, 215, 0, 0.1); border: 1px solid #ffd700; border-radius: 12px; padding: 16px 8px; flex: 1.1; text-align: center; transform: translateY(-10px);">
                        <span style="font-size: 30px;">👑</span>
                        <div id="pod1-name" style="font-size: 13px; font-weight: bold; margin: 4px 0; color: #fff;">---</div>
                        <div id="pod1-score" style="font-size: 12px; color: #2ec4b6; font-weight: bold;">0 ZN</div>
                    </div>
                    <div style="background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.15); border-radius: 12px; padding: 12px 8px; flex: 1; text-align: center;">
                        <span style="font-size: 24px;">🥉</span>
                        <div id="pod3-name" style="font-size: 12px; font-weight: bold; margin: 4px 0; color: #ddd;">---</div>
                        <div id="pod3-score" style="font-size: 11px; color: #2ec4b6; font-weight: bold;">0 ZN</div>
                    </div>
                </div>

                <div id="lb-list-container" style="display: flex; flex-direction: column; gap: 8px; text-align: right;">
                    <div style="text-align: center; padding: 20px; color: #888;">جاري تحميل محفظة ZNX والتوب...</div>
                </div>

                <div style="position: fixed; bottom: 65px; left: 50%; transform: translateX(-50%); width: calc(100% - 30px); max-width: 470px; background: #0088cc; color: white; padding: 12px 20px; border-radius: 14px; display: flex; justify-content: space-between; align-items: center; box-shadow: 0 4px 15px rgba(0,0,0,0.4); z-index: 100;">
                    <span style="font-weight: bold; font-size: 14px;">ترتيبك الحالي: <span id="my-rank-val">#--</span></span>
                    <span style="font-weight: bold; font-size: 14px;">رصيدك: <span id="my-rank-balance">0.00 ZN</span></span>
                </div>
            </div>`;
    }
}

async function loadModuleScript(jsPath) {
    return new Promise((resolve) => {
        const cleanJsPath = jsPath.split('?')[0];
        const existing = Array.from(document.querySelectorAll('script')).find(s => s.src && s.src.includes(cleanJsPath));
        if (existing) {
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
    if (cleanViewName === 'wallets' || cleanViewName === 'tools') cleanViewName = 'wallet';
    if (cleanViewName === 'game') cleanViewName = 'games';
    if (cleanViewName === 'task') cleanViewName = 'tasks';
    if (cleanViewName === 'user' || cleanViewName === 'friends' || cleanViewName === 'friend') cleanViewName = 'friends';
    if (cleanViewName === 'offer' || cleanViewName === 'أرباح العروض' || cleanViewName === 'ارباح العروض') cleanViewName = 'offers';
    
    if (cleanViewName === 'leaderboard' || cleanViewName === 'znx_wallet' || cleanViewName === 'znx-wallet' || cleanViewName === 'znxwallet') {
        cleanViewName = 'znx_wallet';
    }

    hideLoadingScreen();

    document.querySelectorAll('.nav-item').forEach(btn => btn.classList.remove('active'));
    const targetNav = document.getElementById(`nav-${cleanViewName}`) || 
                      document.getElementById(`nav-leaderboard`) ||
                      document.querySelector(`[data-view="${cleanViewName}"]`) ||
                      document.querySelector(`[data-view="${viewName}"]`);
    if (targetNav) targetNav.classList.add('active');

    document.querySelectorAll('.game-view, [id^="view-"]').forEach(v => {
        v.classList.remove('active');
        v.style.display = 'none';
    });
    
    let targetView = document.getElementById(`view-${cleanViewName}`);
    if (!targetView && cleanViewName === 'znx_wallet') {
        targetView = document.getElementById('view-leaderboard');
    }

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

    if (cleanViewName === 'znx_wallet') {
        await window.loadZnxWalletView();
        return;
    }

    const hasPlaceholder = targetView.querySelector('.placeholder-container');
    const hasRealContent = !hasPlaceholder && (targetView.innerText.trim().length > 10 || targetView.querySelector('button, input, h1, h2, h3, h4'));

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
        } else if (cleanViewName === 'offers') {
            if (typeof window.onOffersTabOpen === 'function') await window.onOffersTabOpen();
            else if (typeof window.initOffersView === 'function') await window.initOffersView();
            else if (typeof window.loadOffersList === 'function') await window.loadOffersList();
        } else if (cleanViewName === 'settings') {
            if (typeof window.initSettingsView === 'function') window.initSettingsView();
        }
    } catch (err) {
        console.error("خطأ أثناء تشغيل تهيئة التبويب:", err);
    }

    if (typeof window.updateUI === 'function') window.updateUI();
};

// ==========================================
// 11. التشغيل المباشر عند الإقلاع
// ==========================================
document.addEventListener('DOMContentLoaded', async () => {
    hideLoadingScreen();
    startLocalMiningSimulator();
    window.fetchTonPrice();

    if (!window.userState.tg_id && tg?.initDataUnsafe?.user?.id) {
        window.userState.tg_id = tg.initDataUnsafe.user.id;
    }
    if ((!window.userState.first_name || window.userState.first_name === "لاعب") && tg?.initDataUnsafe?.user?.first_name) {
        window.userState.first_name = tg.initDataUnsafe.user.first_name;
    }

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

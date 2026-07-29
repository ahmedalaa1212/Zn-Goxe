// game.js - النسخة المؤقلمة والمحدثة بالكامل والمحصنة لـ ZN Goxe

// 1. استرجاع البيانات المحفوظة محلياً فوراً لمنع التأخير أثناء التحميل
const cachedBalance = parseFloat(localStorage.getItem('zn_balance')) || 0;
const cachedAdBalance = parseFloat(localStorage.getItem('zn_ad_balance')) || 0;
const cachedUsdBalance = parseFloat(localStorage.getItem('zn_usd_balance')) || 0.0;
const cachedEnergy = parseInt(localStorage.getItem('zn_energy')) || 1000;

// استخراج tg_id من رابط الصفحة في حال لم يتوفر initData المباشر
const urlParams = new URLSearchParams(window.location.search);
const queryTgId = urlParams.get('tg_id') || localStorage.getItem('zn_tg_id') || "";

if (queryTgId) {
    localStorage.setItem('zn_tg_id', queryTgId);
}

// البيانات المبدئية لحالة اللعبة
const initialData = {
    tg_id: queryTgId,
    userId: localStorage.getItem('zn_user_id') || queryTgId,
    username: localStorage.getItem('zn_username') || "",
    balance: cachedBalance,
    ad_balance: cachedAdBalance,
    usd_balance: cachedUsdBalance,
    energy: cachedEnergy
};

// استخدام Proxy لمراقبة التغييرات وتحديث المظهر والتخزين تلقائياً
window.GameState = new Proxy(initialData, {
    set(target, key, value) {
        // حماية: عدم تحويل النصوص (مثل الأسماء والمعرفات) إلى أرقام
        if (['balance', 'ad_balance', 'usd_balance', 'energy'].includes(key)) {
            target[key] = Number(value) || 0;
        } else {
            target[key] = value;
        }

        if (key === 'balance') {
            localStorage.setItem('zn_balance', target[key]);
            window.updateGlobalUI();
        } else if (key === 'ad_balance') {
            localStorage.setItem('zn_ad_balance', target[key]);
            window.updateGlobalUI();
        } else if (key === 'usd_balance') {
            localStorage.setItem('zn_usd_balance', target[key]);
            window.updateGlobalUI();
        } else if (key === 'energy') {
            localStorage.setItem('zn_energy', target[key]);
            window.updateGlobalUI();
        }
        return true;
    }
});

// 2. دالة الاتصال بالباك إيند الموحدة وآمنة
window.apiCall = async function(endpoint, method = 'GET', body = null) {
    const BASE_URL = ""; 
    const initData = window.Telegram?.WebApp?.initData || "";
    const tgId = window.GameState.tg_id || localStorage.getItem('zn_tg_id') || "";

    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${initData}`,
        'X-TG-ID': tgId
    };

    const config = { method, headers };

    // تجهيز البودي وإرفاق tg_id و initData دائماً ضماناً لعدم ضياع الحساب
    let payload = body ? { ...body } : {};
    payload.initData = initData;
    payload.tg_id = tgId;

    if (method !== 'GET') {
        config.body = JSON.stringify(payload);
    }

    try {
        const response = await fetch(`${BASE_URL}${endpoint}`, config);
        const data = await response.json();
        return data;
    } catch (error) {
        console.error(`❌ خطأ في الاتصال بالشبكة (${endpoint}):`, error);
        return { success: false, error: "Network Error" };
    }
};

// 3. تحديث كافة عناصر الواجهة في الصفحة بدون استثناء
window.updateGlobalUI = function() {
    const balanceVal = Number(window.GameState.balance) || 0;
    const adBalanceVal = Number(window.GameState.ad_balance) || 0;
    const usdBalanceVal = Number(window.GameState.usd_balance) || 0;
    
    // تنسيق الأرقام لعرض جمالي
    const formattedBalance = Math.floor(balanceVal).toLocaleString();
    const formattedAdBalance = Math.floor(adBalanceVal).toLocaleString();
    const formattedUsdBalance = usdBalanceVal.toFixed(2);
    
    // تحديث رصيد ZN الأساسي
    const balanceSelectors = [
        '.user-balance', '.zn-balance-display', '.balance-text',
        '#user-balance', '#farm-balance', '#game-balance',
        '#task-balance', '#wallet-balance', '#top-balance-tasks', '[data-balance]'
    ].join(', ');

    document.querySelectorAll(balanceSelectors).forEach(el => {
        if (el.id === 'top-balance-tasks') {
            el.innerText = `ZN ${formattedBalance}`;
        } else {
            el.innerText = formattedBalance;
        }
    });
    
    // تحديث رصيد الإعلانات AdZN
    const adBalanceSelectors = ['#ad-balance-display', '.ad-balance-text', '[data-ad-balance]'].join(', ');
    document.querySelectorAll(adBalanceSelectors).forEach(el => {
        el.innerText = `AdZN ${formattedAdBalance}`;
    });

    // تحديث رصيد USD
    const usdBalanceSelectors = ['#usd-balance-display', '.usd-balance-text', '[data-usd-balance]'].join(', ');
    document.querySelectorAll(usdBalanceSelectors).forEach(el => {
        el.innerText = `$${formattedUsdBalance}`;
    });

    // تحديث الطاقة
    const energySelectors = ['.user-energy', '#user-energy', '[data-energy]'].join(', ');
    document.querySelectorAll(energySelectors).forEach(el => {
        el.innerText = window.GameState.energy;
    });
};

// 4. دوال التعديل اللحظي (Optimistic Updates)
window.setBalance = function(newBalance) { window.GameState.balance = newBalance; };
window.addBalance = function(amount) { window.GameState.balance += amount; };
window.deductBalance = function(amount) { window.GameState.balance -= amount; };

// 5. مزامنة البيانات التلقائية مع السيرفر
window.initGameData = async function() {
    window.updateGlobalUI();

    const tgId = window.GameState.tg_id || localStorage.getItem('zn_tg_id');
    if (!tgId && !window.Telegram?.WebApp?.initData) {
        if (!localStorage.getItem('zn_balance')) window.setBalance(1000);
        return;
    }
    
    try {
        const res = await window.apiCall('/api/farm/sync', 'POST');
        
        if (res && res.success && res.data) {
            window.GameState.userId = res.data.id || tgId;
            window.GameState.username = res.data.first_name || res.data.username || "";
            
            localStorage.setItem('zn_user_id', window.GameState.userId);

            if (res.data.balance !== undefined) window.GameState.balance = res.data.balance;
            if (res.data.ad_balance !== undefined) window.GameState.ad_balance = res.data.ad_balance;
            if (res.data.usd_balance !== undefined) window.GameState.usd_balance = res.data.usd_balance;
            if (res.data.energy !== undefined) window.GameState.energy = res.data.energy;
        }
    } catch (err) {
        console.warn("⚠️ تنبيه: تم الاعتماد على الأرصدة المحلية لتعذر المزامنة الحالية.", err);
    }
};

// 6. الاستماع للتحميل والتنقلات داخل الـ Mini App
document.addEventListener('DOMContentLoaded', () => {
    window.initGameData();

    // إرسال تحديث للـ UI مع كل كليك على القوائم والأزرار
    document.querySelectorAll('.nav-item, .tab-btn, footer button, nav button, a').forEach(btn => {
        btn.addEventListener('click', () => {
            setTimeout(window.updateGlobalUI, 50);
            setTimeout(window.updateGlobalUI, 300);
        });
    });

    // مراقبة أي تغييرات في صفحة الـ HTML لتطبيق التحديثات فوراً
    const observer = new MutationObserver(() => window.updateGlobalUI());
    observer.observe(document.body, { childList: true, subtree: true });
});

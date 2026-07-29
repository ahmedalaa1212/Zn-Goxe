// game.js - النسخة المعدلة والمصلحة بالكامل لتعمل مع نظام المهام

// 1. استرجاع الرصيد، رصيد الإعلانات، والطاقة المحفوظين محلياً فوراً
const cachedBalance = parseFloat(localStorage.getItem('zn_balance')) || 0;
const cachedAdBalance = parseFloat(localStorage.getItem('zn_ad_balance')) || 0;
const cachedEnergy = parseInt(localStorage.getItem('zn_energy')) || 1000;

// استخدام Proxy لمراقبة أي تغيير في الأرصدة وتحديث الشاشة فوراً
const initialData = {
    userId: localStorage.getItem('zn_user_id') || null,
    username: localStorage.getItem('zn_username') || "",
    balance: cachedBalance,
    ad_balance: cachedAdBalance,
    energy: cachedEnergy,
    usd_balance: 0.00000 // ضفنا سطر صغير للـ USD عشان الجافاسكربت يراقبه
};

window.GameState = new Proxy(initialData, {
    set(target, key, value) {
        target[key] = Number(value); // تأكيد أن القيمة رقم لتجنب الأخطاء
        if (key === 'balance') {
            localStorage.setItem('zn_balance', target[key]);
            window.updateGlobalUI();
        } else if (key === 'ad_balance') {
            localStorage.setItem('zn_ad_balance', target[key]);
            window.updateGlobalUI();
        } else if (key === 'energy') {
            localStorage.setItem('zn_energy', target[key]);
            window.updateGlobalUI();
        } else if (key === 'usd_balance') {
            // تحديث واجهة المحفظة لما الـ USD يتغير
            if (window.updateHeaderBalances) window.updateHeaderBalances();
        }
        return true;
    }
});

// 2. دالة الاتصال بالباك إيند الموحدة
window.apiCall = async function(endpoint, method = 'GET', body = null) {
    const BASE_URL = ""; 
    const initData = window.Telegram?.WebApp?.initData || "";

    if (!initData && method !== 'GET') {
        console.warn("Preview Mode - Action blocked.");
        return { success: false, error: "Preview Mode" };
    }

    const headers = {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${initData}` 
    };

    const config = { method, headers };

    if (body) {
        body.initData = initData; 
        config.body = JSON.stringify(body);
    } else if (method === 'POST') {
        config.body = JSON.stringify({ initData });
    }

    try {
        const response = await fetch(`${BASE_URL}${endpoint}`, config);
        return await response.json();
    } catch (error) {
        console.error(`API Error (${endpoint}):`, error);
        return { success: false, error: "Network Error" };
    }
};

// 3. تحديث كافة الواجهات في جميع القوائم والتبويبات
window.updateGlobalUI = function() {
    const balanceVal = Number(window.GameState.balance) || 0;
    const adBalanceVal = Number(window.GameState.ad_balance) || 0;
    
    // تنسيق الرقم
    const formattedBalance = Math.floor(balanceVal).toLocaleString();
    const formattedAdBalance = Math.floor(adBalanceVal).toLocaleString();
    
    // تحديث رصيد ZN الأساسي
    const balanceSelectors = [
        '.user-balance', '.zn-balance-display', '.balance-text',
        '#user-balance', '#farm-balance', '#game-balance',
        '#task-balance', '#wallet-balance', '#top-balance-tasks', '[data-balance]'
    ].join(', ');

    document.querySelectorAll(balanceSelectors).forEach(el => {
        if(el.id === 'top-balance-tasks') {
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

// 5. مزامنة البيانات مع السيرفر
window.initGameData = async function() {
    window.updateGlobalUI();

    if (!window.Telegram?.WebApp?.initData) {
        if (!localStorage.getItem('zn_balance')) window.setBalance(5000);
        return;
    }
    
    try {
        const res = await window.apiCall('/api/user/sync', 'POST');
        
        if (res && res.success && res.data) {
            window.GameState.userId = res.data.id;
            window.GameState.username = res.data.username;
            
            localStorage.setItem('zn_user_id', res.data.id || "");
            localStorage.setItem('zn_username', res.data.username || "");

            if (res.data.balance !== undefined) window.GameState.balance = res.data.balance;
            if (res.data.ad_balance !== undefined) window.GameState.ad_balance = res.data.ad_balance;
            if (res.data.energy !== undefined) window.GameState.energy = res.data.energy;
            if (res.data.usd_balance !== undefined) window.GameState.usd_balance = res.data.usd_balance;
        }
    } catch (err) {
        console.warn("تنبيه: تعذر المزامنة مع السيرفر، تم الاعتماد على الرصيد المحلي.", err);
    }
};

// مراقبة التنقل
document.addEventListener('DOMContentLoaded', () => {
    window.initGameData();
    document.querySelectorAll('.nav-item, .tab-btn, footer button, nav button, a').forEach(btn => {
        btn.addEventListener('click', () => {
            setTimeout(window.updateGlobalUI, 50);
            setTimeout(window.updateGlobalUI, 300);
        });
    });

    const observer = new MutationObserver(() => window.updateGlobalUI());
    observer.observe(document.body, { childList: true, subtree: true });
});

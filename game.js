// game.js - النسخة المعدلة والمصلحة بالكامل

// 1. استرجاع الرصيد والطاقة المحفوظين محلياً فوراً
const cachedBalance = parseFloat(localStorage.getItem('zn_balance')) || 0;
const cachedEnergy = parseInt(localStorage.getItem('zn_energy')) || 1000;

// استخدام Proxy لمراقبة أي تغيير في الرصيد أو الطاقة وتحديث الشاشة فوراً
const initialData = {
    userId: localStorage.getItem('zn_user_id') || null,
    username: localStorage.getItem('zn_username') || "",
    balance: cachedBalance,
    energy: cachedEnergy
};

window.GameState = new Proxy(initialData, {
    set(target, key, value) {
        target[key] = value;
        if (key === 'balance') {
            localStorage.setItem('zn_balance', value);
            window.updateGlobalUI();
        } else if (key === 'energy') {
            localStorage.setItem('zn_energy', value);
            window.updateGlobalUI();
        }
        return true;
    }
});

// 2. دالة الاتصال بالباك إيند
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
    
    // تنسيق الرقم (مثلاً: 1,728.61 أو 1728)
    const formattedBalance = balanceVal.toLocaleString(undefined, {
        minimumFractionDigits: 0,
        maximumFractionDigits: 2
    });
    
    // شامل كافة المسميات والـ Classes المستخدمة في شاشات (المزرعة، الألعاب، المهام، المحفظة)
    const balanceSelectors = [
        '.user-balance',
        '.zn-balance-display',
        '.balance-text',
        '#user-balance',
        '#farm-balance',
        '#game-balance',
        '#task-balance',
        '#wallet-balance',
        '[data-balance]'
    ].join(', ');

    document.querySelectorAll(balanceSelectors).forEach(el => {
        el.innerText = formattedBalance;
    });
    
    const energySelectors = [
        '.user-energy',
        '#user-energy',
        '[data-energy]'
    ].join(', ');

    document.querySelectorAll(energySelectors).forEach(el => {
        el.innerText = window.GameState.energy;
    });
};

// 4. دوال التعديل اللحظي (Optimistic Updates)
window.setBalance = function(newBalance) {
    window.GameState.balance = Number(newBalance);
};

window.addBalance = function(amount) {
    window.GameState.balance = Number(window.GameState.balance) + Number(amount);
};

window.deductBalance = function(amount) {
    window.GameState.balance = Number(window.GameState.balance) - Number(amount);
};

// 5. مزامنة البيانات مع السيرفر
window.initGameData = async function() {
    window.updateGlobalUI();

    if (!window.Telegram?.WebApp?.initData) {
        if (!localStorage.getItem('zn_balance')) {
            window.setBalance(5000);
        }
        return;
    }
    
    try {
        const res = await window.apiCall('/api/user/sync', 'POST');
        
        if (res && res.success && res.data) {
            window.GameState.userId = res.data.id;
            window.GameState.username = res.data.username;
            
            localStorage.setItem('zn_user_id', res.data.id || "");
            localStorage.setItem('zn_username', res.data.username || "");

            // دمج وتحديث الرصيد من السيرفر
            // ملاحظة: التأكد أن السيرفر يرجع الإجمالي الكامل لرصيد المستخدم
            const serverBalance = res.data.balance !== undefined ? res.data.balance : res.data.ad_balance;
            if (serverBalance !== undefined) {
                window.GameState.balance = Number(serverBalance);
            }
            if (res.data.energy !== undefined) {
                window.GameState.energy = res.data.energy;
            }
        }
    } catch (err) {
        console.warn("تنبيه: تعذر المزامنة مع السيرفر، تم الاعتماد على الرصيد المحلي.", err);
    }
};

// مراقبة التنقل بين القوائم والتبويبات لتحديث الرصيد تلقائياً عند فتح أي قائمة
document.addEventListener('DOMContentLoaded', () => {
    window.initGameData();

    // 1. تحديث الواجهة فوراً عند النقر على أي زر تنقل (التبويبات السفلية)
    document.querySelectorAll('.nav-item, .tab-btn, footer button, nav button, a').forEach(btn => {
        btn.addEventListener('click', () => {
            setTimeout(window.updateGlobalUI, 50);
            setTimeout(window.updateGlobalUI, 300); // إعطاء مهلة لتغير الـ DOM
        });
    });

    // 2. مراقب لتغييرات الـ DOM (في حال تم إظهار/إخفاء تبويب ديناميكياً)
    const observer = new MutationObserver(() => {
        window.updateGlobalUI();
    });

    observer.observe(document.body, { childList: true, subtree: true });
});


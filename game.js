// game.js
// 1. استرجاع آخر رصيد وطاقة محفوظين على الموبايل فوراً (0 ثانية Delay)
const cachedBalance = parseFloat(localStorage.getItem('zn_balance')) || 0;
const cachedEnergy = parseInt(localStorage.getItem('zn_energy')) || 1000;

window.GameState = {
    userId: localStorage.getItem('zn_user_id') || null,
    username: localStorage.getItem('zn_username') || "",
    balance: cachedBalance,
    energy: cachedEnergy
};

// 2. دالة الاتصال بالباك إيند (مرفقة بحماية تليجرام)
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

// 3. تحديث كافة الواجهات على الشاشة فوراً
window.updateGlobalUI = function() {
    const formattedBalance = Number(window.GameState.balance).toLocaleString();
    
    // دعم كافة الكلاسات المعروضة في كل القوائم (المزرعة، المتجر، المهام...)
    document.querySelectorAll('.user-balance, .zn-balance-display, .balance-text, #user-balance').forEach(el => {
        el.innerText = formattedBalance;
    });
    
    document.querySelectorAll('.user-energy, #user-energy').forEach(el => {
        el.innerText = window.GameState.energy;
    });
};

// 4. دوال لمس مساعدة للتعديل اللحظي على الرصيد (Optimistic Updates)
window.setBalance = function(newBalance) {
    window.GameState.balance = Number(newBalance);
    localStorage.setItem('zn_balance', window.GameState.balance);
    window.updateGlobalUI();
};

window.addBalance = function(amount) {
    window.setBalance(window.GameState.balance + Number(amount));
};

window.deductBalance = function(amount) {
    window.setBalance(window.GameState.balance - Number(amount));
};

// 5. مزامنة البيانات مع السيرفر في الخلفية
window.initGameData = async function() {
    // ⚡ عرض الرصيد المحفوظ في ذاكرة الجهاز فوراً بديبيكة 0 ثانية
    window.updateGlobalUI();

    if (!window.Telegram?.WebApp?.initData) {
        if (!localStorage.getItem('zn_balance')) {
            window.setBalance(5000);
        }
        return;
    }
    
    // جلب أحدث رصيد من السيرفر في الخلفية دون تعطيل الشاشة
    try {
        const res = await window.apiCall('/api/user/sync', 'POST');
        
        if (res && res.success && res.data) {
            window.GameState.userId = res.data.id;
            window.GameState.username = res.data.username;
            
            localStorage.setItem('zn_user_id', res.data.id || "");
            localStorage.setItem('zn_username', res.data.username || "");

            // لو السيرفر رجّع رصيد مختلف، بنحدثه
            if (res.data.balance !== undefined) {
                window.setBalance(res.data.balance);
            }
            if (res.data.energy !== undefined) {
                window.GameState.energy = res.data.energy;
                localStorage.setItem('zn_energy', res.data.energy);
                window.updateGlobalUI();
            }
        }
    } catch (err) {
        console.warn("تنبيه: تعذر المزامنة مع السيرفر، تم الاعتماد على الرصيد المحلي.", err);
    }
};

// التشغيل الفوري أول ما عناصر الصفحة تجهز (بدون setTimeout)
document.addEventListener('DOMContentLoaded', () => {
    window.initGameData();
});

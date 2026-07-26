// game.js
window.GameState = {
    userId: null,
    username: "",
    balance: 0,
    energy: 1000
};

window.apiCall = async function(endpoint, method = 'GET', body = null) {
    // 🛡️ استخدام مسار نسبي ليعمل أوتوماتيكياً على Railway أو أي استضافة بدون مشاكل CORS
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

window.updateGlobalUI = function() {
    document.querySelectorAll('.user-balance').forEach(el => {
        el.innerText = window.GameState.balance.toLocaleString();
    });
    
    document.querySelectorAll('.user-energy').forEach(el => {
        el.innerText = window.GameState.energy;
    });
};

window.initGameData = async function() {
    if (!window.Telegram?.WebApp?.initData) {
        window.GameState.balance = 5000;
        window.updateGlobalUI();
        return;
    }
    
    // جلب البيانات الأساسية من السيرفر
    const res = await window.apiCall('/api/user/sync', 'POST');
    
    if (res && res.success) {
        window.GameState.userId = res.data.id;
        window.GameState.username = res.data.username;
        window.GameState.balance = res.data.balance || 0;
        window.updateGlobalUI();
    }
};

document.addEventListener('DOMContentLoaded', () => {
    // 500 ملي ثانية كافية جداً لتحميل التليجرام
    setTimeout(window.initGameData, 500);
});

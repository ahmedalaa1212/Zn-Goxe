// ==========================================
// ملف game.js - الذاكرة المؤقتة والمحرك الأساسي
// ==========================================

// 1. الذاكرة المؤقتة (Global State)
window.GameState = {
    userId: null,
    username: "",
    balance: 0,
    energy: 1000, // مثال لطاقة التعدين
    // نقدر نضيف هنا أي بيانات مشتركة بين القوائم
};

// 2. ساعي البريد الموثوق (API Caller)
// الدالة دي أي قائمة هتستخدمها عشان تكلم السيرفر بأمان
window.apiCall = async function(endpoint, method = 'GET', body = null) {
    // ⚠️ غير الرابط ده برابط Railway بتاعك بعدين
    const BASE_URL = "https://zn-goxe-production.up.railway.app/"; 
    
    // سحب بصمة الأمان الخاصة بتليجرام
    const initData = window.Telegram?.WebApp?.initData || "";

    // 🛡️ حماية المتصفح: منع أي محاولة لتعديل أو إضافة بيانات من خارج تليجرام
    if (!initData && method !== 'GET') {
        console.warn("أنت تتصفح وضع المعاينة. تم حظر إرسال البيانات الوهمية للخادم.");
        // بنرجع رد وهمي عشان اللعبة ماتعلقش أو تظهر خطأ للمراجع بتاع الإعلانات
        return { success: false, error: "Preview Mode" };
    }

    const headers = {
        'Content-Type': 'application/json',
        // إرسال البصمة في الهيدر كإثبات هوية
        'Authorization': `Bearer ${initData}` 
    };

    const config = {
        method: method,
        headers: headers
    };

    // لو بنبعت بيانات للسيرفر (زي سحب فلوس أو استلام نقاط)
    if (body) {
        body.initData = initData; // تأكيد البصمة داخل البيانات
        config.body = JSON.stringify(body);
    } else if (method === 'POST') {
        // لو POST فاضي، نبعت البصمة بس
        config.body = JSON.stringify({ initData: initData });
    }

    try {
        const response = await fetch(`${BASE_URL}${endpoint}`, config);
        const data = await response.json();
        return data;
    } catch (error) {
        console.error(`خطأ في الاتصال بالسيرفر (${endpoint}):`, error);
        return { success: false, error: "حدث خطأ في الاتصال بالشبكة" };
    }
};

// 3. تحديث الواجهة المركزي (UI Updater)
// الدالة دي بتلف على كل الشاشات وتحدث الأرقام مرة واحدة
window.updateGlobalUI = function() {
    // تحديث رصيد النقاط (أي عنصر واخد كلاس user-balance هيتحدث)
    const balanceElements = document.querySelectorAll('.user-balance');
    balanceElements.forEach(el => {
        // تنسيق الرقم عشان يظهر بشكل شيك (مثال: 1,000,000)
        el.innerText = window.GameState.balance.toLocaleString();
    });
    
    // تحديث الطاقة (لو عندك)
    const energyElements = document.querySelectorAll('.user-energy');
    energyElements.forEach(el => {
        el.innerText = window.GameState.energy;
    });
};

// 4. جلب بيانات اللاعب عند فتح البوت
window.initGameData = async function() {
    if (!window.Telegram?.WebApp?.initData) {
        console.warn("تم الدخول من المتصفح. تفعيل وضع المعاينة الوهمي.");
        // أرقام وهمية عشان مراجعين شركات الإعلانات يشوفوا اللعبة شغالة
        window.GameState.balance = 5000;
        window.updateGlobalUI();
        return;
    }
    
    // جلب البيانات الحقيقية من السيرفر لمستخدمي تليجرام
    const res = await window.apiCall('/api/user/sync', 'POST');
    
    if (res && res.success) {
        window.GameState.userId = res.data.id;
        window.GameState.username = res.data.username;
        window.GameState.balance = res.data.balance || 0;
        
        // تحديث الشاشة فوراً
        window.updateGlobalUI();
    }
};

// تشغيل التهيئة بعد تحميل الصفحة
document.addEventListener('DOMContentLoaded', () => {
    // تأخير بسيط ثانية واحدة لضمان تحميل تليجرام بالكامل
    setTimeout(window.initGameData, 1000);
});

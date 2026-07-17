// ==========================================
// الكائن العالمي الموحد لإدارة بيانات اللاعب (مصدر الحقيقة الوحيد)
// ==========================================
window.PlayerData = {
    tg_id: null,
    balance: 0,
    hourly_rate: 0,
    max_cap: 10000,
    unclaimed: 0,
    storage_level: 0,
    upgrades: {},
    daily_day: 1,
    last_daily_claim_time: "2000-01-01T00:00:00+00:00",
    last_claim_time: "2000-01-01T00:00:00+00:00",
    server_time: null,
    timeOffset: 0
};

// دالة جلب البيانات المركزية من السيرفر (تخدم كل الشاشات)
window.fetchPlayerDataFromServer = async function() {
    if (!window.PlayerData.tg_id) return;
    try {
        // بنبعت البارامترين لتفادي أي اختلاف في السيرفر (telegramId أو tg_id)
        let response = await fetch(`/api/user_data?telegramId=${window.PlayerData.tg_id}&tg_id=${window.PlayerData.tg_id}`);
        if (response.ok) {
            let result = await response.json();
            
            // التعامل مع شكل رد السيرفر سواء مباشر أو جوا كائن success
            let dbData = result.success ? result.data : result;
            
            if (dbData) {
                // حساب الفارق الزمني مع السيرفر لضبط العدادات بدقة
                if (dbData.server_time) {
                    let serverTime = new Date(dbData.server_time).getTime();
                    let clientTime = Date.now();
                    window.timeOffset = serverTime - clientTime;
                    window.PlayerData.server_time = dbData.server_time;
                }

                // تحديث القيم العامة في الكائن الموحد
                window.PlayerData.balance = parseFloat(dbData.balance || 0);
                window.PlayerData.hourly_rate = parseFloat(dbData.calculated_hourly_rate || dbData.hourly_rate || 0);
                window.PlayerData.max_cap = parseFloat(dbData.calculated_max_cap || dbData.max_cap || 10000);
                window.PlayerData.unclaimed = parseFloat(dbData.calculated_unclaimed || dbData.unclaimed || 0);
                window.PlayerData.storage_level = parseInt(dbData.storage_level || 0);
                window.PlayerData.daily_day = parseInt(dbData.daily_day || 1);
                window.PlayerData.last_daily_claim_time = dbData.last_daily_claim_time || "2000-01-01T00:00:00+00:00";
                window.PlayerData.last_claim_time = dbData.last_claim_time || new Date().toISOString();

                // تجميع مستويات المزرعة في كائن واحد
                let upgs = {};
                for (let i = 1; i <= 9; i++) {
                    upgs[`lvl${i}`] = parseInt(dbData[`lvl${i}_count`] || (dbData.upgrades && dbData.upgrades[`lvl${i}`]) || 0);
                }
                window.PlayerData.upgrades = upgs;

                // تحديث الواجهات فوراً في كل الشاشات النشطة
                window.triggerAllUIUpdates();
            }
        }
    } catch (e) {
        console.error("خطأ في مزامنة البيانات المركزية:", e);
    }
};

// دالة تحديث شاشات العرض كلها بالتوازي
window.triggerAllUIUpdates = function() {
    const pData = window.PlayerData;
    if (!pData) return;

    // 1. استدعاء دوال التحديث الخاصة بكل صفحة لو تم تحميل ملفاتها بنجاح
    if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
    if (typeof window.updateShopUI === 'function') window.updateShopUI();
    if (typeof window.updateGamesUI === 'function') window.updateGamesUI();

    // 2. تحديث الرصيد في أي عنصر يحمل الكلاسات أو الـ IDs المشتركة في التطبيق بالكامل
    const formattedBalance = Math.floor(pData.balance).toLocaleString();
    
    // لستة بالـ IDs المستخدمة في كل الصفحات لعرض الرصيد
    const possibleBalanceIds = [
        'farm-balance', 'shop-balance', 'top-balance-games', 
        'top-balance-farm', 'top-balance-shop', 'main-balance', 'user-balance'
    ];

    possibleBalanceIds.forEach(id => {
        let el = document.getElementById(id);
        if (el) {
            if (el.innerText.includes('ZN:')) {
                el.innerText = `ZN: ${formattedBalance}`;
            } else if (el.innerText.includes('ZN')) {
                el.innerText = `ZN ${formattedBalance}`;
            } else {
                el.innerText = formattedBalance;
            }
        }
    });

    // تحديث أي عنصر واخد كلاس مزامنة رصيد عام
    document.querySelectorAll('.sync-balance, .balance-display').forEach(el => {
        if (el.innerText.includes('ZN:')) {
            el.innerText = `ZN: ${formattedBalance}`;
        } else if (el.innerText.includes('ZN')) {
            el.innerText = `ZN ${formattedBalance}`;
        } else {
            el.innerText = formattedBalance;
        }
    });
};

// تهيئة الـ Telegram ID وتفعيل المزامنة اللحظية
document.addEventListener('DOMContentLoaded', () => {
    const tele = window.Telegram?.WebApp;
    if (tele) tele.ready();
    
    const urlParams = new URLSearchParams(window.location.search);
    
    // تحديد الهوية
    window.PlayerData.tg_id = tele?.initDataUnsafe?.user?.id?.toString() || urlParams.get('tg_id') || "5102387551";
    
    // جلب البيانات أول مرة عند الفتح
    window.fetchPlayerDataFromServer();
    
    // المزامنة اللحظية الحية كل 3 ثواني (لفحص الفايربيس باستمرار وبدون تقطيع)
    if (window.globalSyncInterval) clearInterval(window.globalSyncInterval);
    window.globalSyncInterval = setInterval(() => {
        window.fetchPlayerDataFromServer();
    }, 3000);
});

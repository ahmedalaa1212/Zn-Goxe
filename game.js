// ==========================================
// الكائن العالمي الموحد لإدارة بيانات اللاعب (مصدر الحقيقة الوحيد)
// ==========================================
window.PlayerData = {
    tg_id: null,
    balance: 0,
    ad_balance: 0, 
    hourly_rate: 0,
    max_cap: 10000,
    unclaimed: 0,
    storage_level: 0,
    upgrades: {},
    daily_day: 1,
    last_daily_claim_time: "2000-01-01T00:00:00+00:00",
    last_claim_time: "2000-01-01T00:00:00+00:00",
    server_time: null,
    timeOffset: 0,
    // حقول الأصدقاء
    pending_ref_earnings: 0,
    invited_friends_count: 0,
    claimed_ref_tasks: [],
    referred_users_list: [] // القائمة اللي هتعرض أسامي الصحاب
};

// دالة جلب البيانات المركزية من السيرفر (تخدم كل الشاشات)
window.fetchPlayerDataFromServer = async function() {
    if (!window.PlayerData.tg_id) return;
    try {
        const tele = window.Telegram?.WebApp;
        let startParam = tele?.initDataUnsafe?.start_param || "";
        let ref_id = startParam.replace('ref_', '');
        
        // استخراج اسم المستخدم لإرساله للسيرفر
        let teleUser = tele?.initDataUnsafe?.user;
        let userName = teleUser ? (teleUser.first_name + (teleUser.last_name ? " " + teleUser.last_name : "")) : "مستخدم";

        let url = `/api/user_data?telegramId=${window.PlayerData.tg_id}&tg_id=${window.PlayerData.tg_id}&user_name=${encodeURIComponent(userName)}`;
        if(ref_id) url += `&ref_id=${ref_id}`;

        let response = await fetch(url);
        if (response.ok) {
            let result = await response.json();
            let dbData = result.success ? result.data : result;
            
            if (dbData) {
                if (dbData.server_time) {
                    let serverTime = new Date(dbData.server_time).getTime();
                    let clientTime = Date.now();
                    window.timeOffset = serverTime - clientTime;
                    window.PlayerData.server_time = dbData.server_time;
                }

                window.PlayerData.balance = parseFloat(dbData.balance || 0);
                window.PlayerData.ad_balance = parseFloat(dbData.ad_balance || 0); 
                window.PlayerData.hourly_rate = parseFloat(dbData.calculated_hourly_rate || dbData.hourly_rate || 0);
                window.PlayerData.max_cap = parseFloat(dbData.calculated_max_cap || dbData.max_cap || 10000);
                window.PlayerData.unclaimed = parseFloat(dbData.calculated_unclaimed || dbData.unclaimed || 0);
                window.PlayerData.storage_level = parseInt(dbData.storage_level || 0);
                window.PlayerData.daily_day = parseInt(dbData.daily_day || 1);
                window.PlayerData.last_daily_claim_time = dbData.last_daily_claim_time || "2000-01-01T00:00:00+00:00";
                window.PlayerData.last_claim_time = dbData.last_claim_time || new Date().toISOString();

                // حقول الأصدقاء
                window.PlayerData.pending_ref_earnings = parseFloat(dbData.pending_ref_earnings || 0);
                window.PlayerData.invited_friends_count = parseInt(dbData.invited_friends_count || 0);
                window.PlayerData.claimed_ref_tasks = dbData.claimed_ref_tasks || [];
                window.PlayerData.referred_users_list = dbData.referred_users_list || [];

                let upgs = {};
                for (let i = 1; i <= 9; i++) {
                    upgs[`lvl${i}`] = parseInt(dbData[`lvl${i}_count`] || (dbData.upgrades && dbData.upgrades[`lvl${i}`]) || 0);
                }
                window.PlayerData.upgrades = upgs;

                // تحديث الواجهات فوراً في كل الشاشات
                window.triggerAllUIUpdates();
            }
        }
    } catch (e) {
        console.error("خطأ في مزامنة البيانات المركزية:", e);
    }
};

// دالة تحديث شاشات العرض كلها
window.triggerAllUIUpdates = function() {
    const pData = window.PlayerData;
    if (!pData) return;

    if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
    if (typeof window.updateShopUI === 'function') window.updateShopUI();
    if (typeof window.updateGamesUI === 'function') window.updateGamesUI();
    if (typeof window.updateTasksUI === 'function') window.updateTasksUI(); 
    if (typeof window.updateFriendsUI === 'function') window.updateFriendsUI();

    const formattedBalance = Math.floor(pData.balance).toLocaleString();
    
    const possibleBalanceIds = [
        'farm-balance', 'shop-balance', 'top-balance-games', 
        'top-balance-farm', 'top-balance-shop', 'main-balance', 'user-balance', 'top-balance-tasks', 'top-balance-friends'
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

    document.querySelectorAll('.sync-balance, .balance-display').forEach(el => {
        if (el.innerText.includes('ZN:')) {
            el.innerText = `ZN: ${formattedBalance}`;
        } else if (el.innerText.includes('ZN')) {
            el.innerText = `ZN ${formattedBalance}`;
        } else {
            el.innerText = formattedBalance;
        }
    });

    const formattedAdBalance = Math.floor(pData.ad_balance || 0).toLocaleString();
    const adBalDisplay = document.getElementById('ad-balance-display');
    if (adBalDisplay) {
        adBalDisplay.innerText = `AdZN ${formattedAdBalance}`;
    }
};

// دالة التهيئة والتشغيل الفوري
window.initCentralSystem = function() {
    function assignIdAndFetch() {
        const tele = window.Telegram?.WebApp;
        if (tele) tele.ready();
        
        const urlParams = new URLSearchParams(window.location.search);
        let id = tele?.initDataUnsafe?.user?.id?.toString() || urlParams.get('tg_id');
        
        if (id) {
            window.PlayerData.tg_id = id;
        } else if (!window.PlayerData.tg_id) {
            window.PlayerData.tg_id = "5102387551"; 
        }

        window.fetchPlayerDataFromServer();
    }

    assignIdAndFetch();
    
    if (window.globalSyncInterval) clearInterval(window.globalSyncInterval);
    window.globalSyncInterval = setInterval(() => {
        assignIdAndFetch();
    }, 3000);
};

window.initCentralSystem();

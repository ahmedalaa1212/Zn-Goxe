window.PlayerData = {
    tg_id: null,
    balance: 0,
    ad_balance: 0, 
    usd_balance: 0,
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
    pending_ref_earnings: 0,
    invited_friends_count: 0,
    claimed_ref_tasks: []
};

window.fetchPlayerDataFromServer = async function() {
    const tele = window.Telegram?.WebApp;
    const initData = tele?.initData || ""; 
    
    if (!initData) {
        console.warn("⚠️ لم يتم العثور على initData.");
        return; 
    }

    try {
        let startParam = tele?.initDataUnsafe?.start_param || "";
        let ref_id = startParam ? startParam.replace('ref_', '') : "";
        let firstName = tele?.initDataUnsafe?.user?.first_name || "صديق";

        let url = `/api/user_data?initData=${encodeURIComponent(initData)}&name=${encodeURIComponent(firstName)}&_t=${Date.now()}`;
        if(ref_id) url += `&ref_id=${ref_id}`;

        let response = await fetch(url, { cache: "no-store" });
        if (response.ok) {
            let result = await response.json();
            let dbData = result.success ? result.data : result;
            
            if (dbData) {
                window.PlayerData.balance = parseFloat(dbData.balance || 0);
                window.PlayerData.ad_balance = parseFloat(dbData.ad_balance || 0); 
                window.PlayerData.usd_balance = parseFloat(dbData.usd_balance || 0);
                window.PlayerData.hourly_rate = parseFloat(dbData.calculated_hourly_rate || 0);
                window.PlayerData.max_cap = parseFloat(dbData.calculated_max_cap || 10000);
                window.PlayerData.unclaimed = parseFloat(dbData.calculated_unclaimed || 0);
                window.PlayerData.storage_level = parseInt(dbData.storage_level || 0);
                window.PlayerData.daily_day = parseInt(dbData.daily_day || 1);
                window.PlayerData.pending_ref_earnings = parseFloat(dbData.pending_ref_earnings || 0);
                window.PlayerData.invited_friends_count = parseInt(dbData.invited_friends_count || 0);

                window.triggerAllUIUpdates();
            }
        }
    } catch (e) {
        console.error("❌ خطأ:", e);
    }
};

window.triggerAllUIUpdates = function() {
    const pData = window.PlayerData;
    if (!pData) return;

    if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
    if (typeof window.updateShopUI === 'function') window.updateShopUI();
    if (typeof window.updateHeaderBalances === 'function') window.updateHeaderBalances(); 

    const formattedBalance = Math.floor(pData.balance).toLocaleString();
    const possibleBalanceIds = ['farm-balance', 'shop-balance', 'main-balance', 'user-balance'];

    possibleBalanceIds.forEach(id => {
        let el = document.getElementById(id);
        if (el) el.innerText = `ZN ${formattedBalance}`;
    });
};

window.initCentralSystem = function() {
    const tele = window.Telegram?.WebApp;
    if (tele) tele.ready();
    
    let id = tele?.initDataUnsafe?.user?.id?.toString();
    if (id) window.PlayerData.tg_id = id;

    window.fetchPlayerDataFromServer();
    
    if (window.globalSyncInterval) clearInterval(window.globalSyncInterval);
    window.globalSyncInterval = setInterval(() => {
        window.fetchPlayerDataFromServer();
    }, 3000);
};

window.initCentralSystem();

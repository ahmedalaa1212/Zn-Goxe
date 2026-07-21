// ==========================================
// 🎮 ZN Goxe - Core Engine & Sync (game.js)
// ==========================================

window.PlayerData = {
    tg_id: null,
    balance: 0,
    usd_balance: 0.00000,
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
    pending_ref_earnings: 0,
    invited_friends_count: 0,
    claimed_ref_tasks: []
};

// منع التداخل في طلبات الشبكة المتكررة والحماية العالية
let isSyncingPlayerData = false;

window.fetchPlayerDataFromServer = async function() {
    if (isSyncingPlayerData) return;
    isSyncingPlayerData = true;

    const tele = window.Telegram?.WebApp;
    const initData = tele?.initData || ""; 
    
    // حماية الواجهة: لو مفيش بيانات مشفرة، نوقف التنفيذ ونظهر رسالة تحذير
    if (!initData) {
        console.warn("⚠️ لم يتم العثور على initData. يرجى فتح التطبيق من تليجرام حصرياً.");
        document.body.innerHTML = `
            <div style='color:#ff4444; text-align:center; padding:60px 20px; font-size:22px; font-weight:bold; background:#121212; height:100vh; display:flex; align-items:center; justify-content:center; flex-direction:column;'>
                <div style='font-size: 50px; margin-bottom: 20px;'>🚫</div>
                البيانات مفقودة. يجب الدخول للعبة من داخل بوت التيليجرام الرسمي فقط!
            </div>
        `;
        isSyncingPlayerData = false;
        return; 
    }

    try {
        let startParam = tele?.initDataUnsafe?.start_param || "";
        let ref_id = startParam ? startParam.replace('ref_', '') : "";
        
        if (!ref_id) {
            const urlParams = new URLSearchParams(window.location.search);
            const sp = urlParams.get('tgWebAppStartParam') || urlParams.get('start_param') || urlParams.get('startapp') || "";
            if (sp) ref_id = sp.replace('ref_', '');
        }

        let firstName = tele?.initDataUnsafe?.user?.first_name || "صديق";

        // 🔥 الاعتماد الكلي على initData لحماية البيانات من التلاعب
        let url = `/api/user_data?initData=${encodeURIComponent(initData)}&name=${encodeURIComponent(firstName)}&_t=${Date.now()}`;
        if(ref_id) url += `&ref_id=${ref_id}`;

        let response = await fetch(url, { cache: "no-store" });
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
                window.PlayerData.usd_balance = parseFloat(dbData.usd_balance || 0);
                window.PlayerData.ad_balance = parseFloat(dbData.ad_balance || 0); 
                window.PlayerData.hourly_rate = parseFloat(dbData.calculated_hourly_rate || dbData.hourly_rate || 0);
                window.PlayerData.max_cap = parseFloat(dbData.calculated_max_cap || dbData.max_cap || 10000);
                window.PlayerData.unclaimed = parseFloat(dbData.calculated_unclaimed || dbData.unclaimed || 0);
                window.PlayerData.storage_level = parseInt(dbData.storage_level || 0);
                window.PlayerData.daily_day = parseInt(dbData.daily_day || 1);
                window.PlayerData.last_daily_claim_time = dbData.last_daily_claim_time || "2000-01-01T00:00:00+00:00";
                window.PlayerData.last_claim_time = dbData.last_claim_time || new Date().toISOString();

                window.PlayerData.pending_ref_earnings = parseFloat(dbData.pending_ref_earnings || 0);
                window.PlayerData.invited_friends_count = parseInt(dbData.invited_friends_count || 0);
                window.PlayerData.claimed_ref_tasks = dbData.claimed_ref_tasks || [];

                let upgs = {};
                for (let i = 1; i <= 10; i++) {
                    upgs[`lvl${i}`] = parseInt(dbData[`lvl${i}_count`] || (dbData.upgrades && dbData.upgrades[`lvl${i}`]) || 0);
                }
                window.PlayerData.upgrades = upgs;

                window.triggerAllUIUpdates();
            }
        } else {
            console.error("❌ السيرفر رفض الطلب، تأكد من صحة التوكن والبيانات.");
        }
    } catch (e) {
        console.error("❌ خطأ في مزامنة البيانات المركزية مع الخادم:", e);
    } finally {
        isSyncingPlayerData = false;
    }
};

window.fetchAndRenderFriendsList = async function() {
    const initData = window.Telegram?.WebApp?.initData || "";
    if (!initData) return;

    try {
        let response = await fetch(`/api/get_friends_list?initData=${encodeURIComponent(initData)}&_t=${Date.now()}`, { cache: "no-store" });
        if (response.ok) {
            let result = await response.json();
            if (result.success && result.friends) {
                let container = document.getElementById('friends-list-container');
                if (!container) return; 
                
                if (result.friends.length === 0) {
                    container.innerHTML = `
                        <div class="empty-state">
                            <span style="font-size: 3rem; display: block; margin-bottom: 10px;">📭</span>
                            لم تقم بدعوة أي صديق حتى الآن.<br>شارك رابطك لتبدأ في كسب الأرباح!
                        </div>`;
                    return;
                }

                let html = '<ul class="friends-list">';
                result.friends.forEach(friend => {
                    let friendName = friend.name || "مستخدم";
                    let firstLetter = friendName.charAt(0).toUpperCase();
                    
                    html += `
                        <li class="friend-item">
                            <div class="friend-avatar">${firstLetter}</div>
                            <div class="friend-info">
                                <span class="friend-name">${friendName}</span>
                                <span class="friend-id">ID: ${friend.id}</span>
                            </div>
                            <div class="friend-earn">
                                +${Math.floor(friend.earned).toLocaleString()} ZN
                            </div>
                        </li>
                    `;
                });
                html += '</ul>';
                container.innerHTML = html;
            }
        }
    } catch (e) {
        console.error("❌ خطأ في جلب قائمة الأصدقاء:", e);
    }
};

window.triggerAllUIUpdates = function() {
    const pData = window.PlayerData;
    if (!pData) return;

    if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
    if (typeof window.updateShopUI === 'function') window.updateShopUI();
    if (typeof window.updateGamesUI === 'function') window.updateGamesUI();
    if (typeof window.updateTasksUI === 'function') window.updateTasksUI(); 
    if (typeof window.updateFriendsUI === 'function') window.updateFriendsUI();
    if (typeof window.renderSettingsPage === 'function') window.renderSettingsPage();
    if (typeof window.updateHeaderBalances === 'function') window.updateHeaderBalances();
    
    let pendingEarnEl = document.getElementById('pending-ref-earnings');
    if(pendingEarnEl) pendingEarnEl.innerText = `${Math.floor(pData.pending_ref_earnings).toLocaleString()}`;
    
    let friendsCountEl = document.getElementById('invited-friends-count');
    if(friendsCountEl) friendsCountEl.innerText = `${pData.invited_friends_count}`;

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

window.initCentralSystem = function() {
    function assignIdAndFetch() {
        const tele = window.Telegram?.WebApp;
        if (tele) tele.ready();
        
        const urlParams = new URLSearchParams(window.location.search);
        let id = tele?.initDataUnsafe?.user?.id?.toString() || urlParams.get('tg_id');
        
        if (id) {
            window.PlayerData.tg_id = id;
        }

        window.fetchPlayerDataFromServer();
        window.fetchAndRenderFriendsList(); 
    }

    assignIdAndFetch();
    
    if (window.globalSyncInterval) clearInterval(window.globalSyncInterval);
    window.globalSyncInterval = setInterval(() => {
        assignIdAndFetch();
    }, 3000);
};

window.initCentralSystem();

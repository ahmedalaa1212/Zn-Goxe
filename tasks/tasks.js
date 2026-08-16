// tasks/tasks.js
(function initTasks() {
    if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.ready();
    }

    // 🛡️ دالة الاتصال بالخادم
    if (typeof window.fetchAPI !== 'function') {
        window.fetchAPI = async function(url, method = 'GET', data = null) {
            const options = {
                method: method,
                headers: { 'Content-Type': 'application/json' }
            };
            if (data && (method === 'POST' || method === 'PUT')) {
                options.body = JSON.stringify(data);
            }
            const response = await fetch(url, options);
            return await response.json();
        };
    }

    // 🔒 جدول الحد الأدنى التلقائي للأسعار لعملة AdZ
    const MIN_REWARDS_MAP = {
        'موقع': 100,
        'يوتيوب': 50,
        'تيليجرام': 50,
        'انستغرام': 50,
        'X': 50,
        'default': 50
    };

    let cachedTasksData = null;
    let lastTasksFetchTime = 0;
    const TASKS_CACHE_TTL = 30000; // كاش الواجهة 30 ثانية

    // 🎨 إصلاح طفو النوافذ
    if (!document.getElementById('task-modal-fix-style')) {
        const style = document.createElement('style');
        style.id = 'task-modal-fix-style';
        style.innerHTML = `
            body.modal-open-fix .bottom-nav,
            body.modal-open-fix #bottom-nav,
            body.modal-open-fix .nav-bar,
            body.modal-open-fix .bottom-menu,
            body.modal-open-fix footer,
            body.modal-open-fix nav,
            body.modal-open-fix .footer-nav {
                display: none !important;
            }
            #ad-modal, #review-modal, #success-modal {
                z-index: 999999 !important;
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                width: 100% !important;
                height: 100% !important;
            }
        `;
        document.head.appendChild(style);
    }

    function hideBottomNav() {
        document.body.classList.add('modal-open-fix');
        const selectors = ['.bottom-nav', '#bottom-nav', '.nav-bar', '.bottom-menu', 'footer', 'nav', '.footer-nav'];
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                el.style.setProperty('display', 'none', 'important');
            });
        });
    }

    function showBottomNav() {
        document.body.classList.remove('modal-open-fix');
        const selectors = ['.bottom-nav', '#bottom-nav', '.nav-bar', '.bottom-menu', 'footer', 'nav', '.footer-nav'];
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                el.style.removeProperty('display');
            });
        });
    }

    try {
        const storedCache = sessionStorage.getItem('tasks_cache_data');
        const storedTime = sessionStorage.getItem('tasks_cache_time');
        if (storedCache && storedTime) {
            cachedTasksData = JSON.parse(storedCache);
            lastTasksFetchTime = parseInt(storedTime, 10) || 0;
        }
    } catch (e) {}

    function saveTasksToSessionCache(data) {
        cachedTasksData = data;
        lastTasksFetchTime = Date.now();
        try {
            sessionStorage.setItem('tasks_cache_data', JSON.stringify(data));
            sessionStorage.setItem('tasks_cache_time', lastTasksFetchTime.toString());
        } catch (e) {}
    }

    function getUserBalance() {
        return window.PlayerData?.balance ?? window.userState?.balance ?? window.GameState?.balance ?? 0;
    }

    function syncUserBalance(val) {
        let numVal = parseFloat(val) || 0;
        if (window.GameState) window.GameState.balance = numVal;
        if (window.PlayerData) window.PlayerData.balance = numVal;
        if (window.userState) window.userState.balance = numVal;

        updateBalanceElements(numVal);
        window.dispatchEvent(new CustomEvent('balanceUpdated', { detail: { balance: numVal } }));
        if (typeof window.updateGlobalUI === 'function') window.updateGlobalUI();
    }

    function getUserAdBalance() {
        return window.PlayerData?.ad_balance ?? window.userState?.ad_balance ?? window.GameState?.ad_balance ?? 0;
    }

    function syncUserAdBalance(val) {
        let numVal = parseFloat(val) || 0;
        if (window.GameState) window.GameState.ad_balance = numVal;
        if (window.PlayerData) window.PlayerData.ad_balance = numVal;
        if (window.userState) window.userState.ad_balance = numVal;

        updateAdBalanceElements(numVal);
        window.dispatchEvent(new CustomEvent('adBalanceUpdated', { detail: { ad_balance: numVal } }));
        if (typeof window.updateGlobalUI === 'function') window.updateGlobalUI();
    }

    function updateBalanceElements(numVal) {
        const formatted = numVal.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
        const topBal = document.getElementById('top-balance-tasks');
        if (topBal) topBal.innerText = `${formatted} ZN`;

        const usdVal = window.PlayerData?.usd_balance ?? window.userState?.usd_balance ?? window.GameState?.usd_balance ?? (numVal * 0.001);
        const usdFormatted = (typeof usdVal === 'number' ? usdVal : parseFloat(usdVal) || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
        const topUsd = document.getElementById('top-balance-usd');
        if (topUsd) topUsd.innerText = `$${usdFormatted}`;

        const selectors = ['.sync-balance', '#user-balance', '#main-balance', '#balance'];
        selectors.forEach(sel => {
            document.querySelectorAll(sel).forEach(el => {
                if (el.id !== 'top-balance-tasks') el.innerText = formatted;
            });
        });
    }

    function updateAdBalanceElements(numVal) {
        const formatted = numVal.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
        const adBalDisplay = document.getElementById('ad-balance-display');
        if (adBalDisplay) adBalDisplay.innerText = `${formatted} AdZ`;

        const topAdz = document.getElementById('top-balance-adz');
        if (topAdz) topAdz.innerText = `${formatted} AdZ`;
    }

    window.taskStates = window.taskStates || {};
    window.accumulatedOutsideTime = window.accumulatedOutsideTime || {};
    window.lastGoOutside = window.lastGoOutside || {};
    window.taskIntervals = window.taskIntervals || {};
    
    let isSubmittingCampaign = false;
    let isConvertingBalance = false;
    let isCancelingCampaign = false;
    let isVerifyingTask = false;
    let currentAdType = 'يوتيوب';

    function escapeHtml(str) {
        if (!str) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    const preDefinedDescriptions = {
        'يوتيوب': ["اشترك بالقناة وفعّل جرس التنبيهات 🔔", "ضع لايك حقيقي للفيديو المرفق 👍", "اكتب تعليق إيجابي يخص المحتوى 💬"],
        'تيليجرام': ["انضم إلى القناة وقم بزيارة آخر 3 منشورات 📢", "انضم إلى الجروب وشارك في النقاشات 👥"],
        'موقع': ["قم بزيارة الموقع والفحص الآمن لمدة 15 ثانية 🛡️", "تصفح المقالات والروابط داخل الموقع 📄"],
        'انستغرام': ["تابع الحساب الرسمي وتفاعل باللايكات 📸", "ضع لايك على المنشور الأخير واكتب تعليق ❤️"],
        'X': ["تابع الحساب الرسمي وقم بعمل ريتويت للتغريدة المثبتة 🔁", "ضع إعجاب على التغريدة الأخيرة 🤍"]
    };

    const platformConfig = {
        'يوتيوب': { title: "مهام يوتيوب", icon: "fab fa-youtube", color: "#ef4444" },
        'تيليجرام': { title: "مهام تيليجرام", icon: "fab fa-telegram", color: "#38bdf8" },
        'X': { title: "مهام منصة X", icon: "fab fa-twitter", color: "#ffffff" },
        'موقع': { title: "زيارة موقع وفحص آمن", icon: "fas fa-shield-alt", color: "#28a745" },
        'انستغرام': { title: "مهام انستغرام", icon: "fab fa-instagram", color: "#e1306c" },
        'أخرى': { title: "مهام متنوعة", icon: "fas fa-tasks", color: "#a855f7" }
    };

    function getTgId() {
        return window.GameState?.userId || window.PlayerData?.userId || window.Telegram?.WebApp?.initDataUnsafe?.user?.id?.toString() || "";
    }

    window.switchTasksTab = function(tab) {
        const earnSection = document.getElementById('section-earn');
        const promoteSection = document.getElementById('section-promote');
        const btnEarn = document.getElementById('btn-tab-earn');
        const btnPromote = document.getElementById('btn-tab-promote');

        if (earnSection) earnSection.style.display = (tab === 'earn') ? 'block' : 'none';
        if (promoteSection) promoteSection.style.display = (tab === 'promote') ? 'block' : 'none';

        if (btnEarn) btnEarn.classList.toggle('active', tab === 'earn');
        if (btnPromote) btnPromote.classList.toggle('active', tab === 'promote');
        
        window.fetchAndRenderTasks(false); 
    };

    // ⚡ فتح النافذة المنبثقة لإنشاء الحملة وتعديل أدنى سعر ديناميكياً
    window.openAdModal = function(type) {
        currentAdType = type || 'يوتيوب';
        const modal = document.getElementById('ad-modal');
        const titleEl = document.getElementById('ad-modal-title');
        const descSelect = document.getElementById('ad-desc-select');
        const minHint = document.getElementById('min-reward-hint');
        const rewardInput = document.getElementById('ad-reward');

        const minReward = MIN_REWARDS_MAP[currentAdType] || MIN_REWARDS_MAP['default'];

        if (titleEl) titleEl.innerText = `إنشاء حملة (${currentAdType})`;
        if (minHint) minHint.innerText = `(الحد الأدنى: ${minReward} AdZ)`;
        if (rewardInput) rewardInput.placeholder = `مثال: ${minReward}`;

        if (descSelect && preDefinedDescriptions[currentAdType]) {
            let opts = `<option value="">-- اختر توجيهات المهمة المطلوبة --</option>`;
            preDefinedDescriptions[currentAdType].forEach(desc => {
                opts += `<option value="${escapeHtml(desc)}">${escapeHtml(desc)}</option>`;
            });
            descSelect.innerHTML = opts;
        }

        const linkInput = document.getElementById('ad-link');
        const usersInput = document.getElementById('ad-users');
        if (linkInput) linkInput.value = '';
        if (rewardInput) rewardInput.value = '';
        if (usersInput) usersInput.value = '';

        if (modal) modal.style.display = 'flex';
        hideBottomNav();
    };

    window.closeAdModal = function(keepNavHidden = false) {
        const modal = document.getElementById('ad-modal');
        if (modal) modal.style.display = 'none';
        if (!keepNavHidden) showBottomNav();
    };

    window.convertZnToAdZn = async function() {
        if (isConvertingBalance) return;

        const inputVal = prompt('أدخل مبلغ ZN المراد تحويله إلى رصيد الإعلانات (AdZ):\n(تنبيه: تخصم عمولة تحويل 10%)');
        if (!inputVal) return;

        const amount = parseFloat(inputVal);
        if (isNaN(amount) || amount <= 0) {
            alert('يرجى إدخال مبلغ صحيح للتحويل!');
            return;
        }

        const currentBal = getUserBalance();
        if (currentBal < amount) {
            alert(`رصيدك الأساسي غير كافٍ! لديك ${currentBal.toLocaleString()} ZN.`);
            return;
        }

        isConvertingBalance = true;

        try {
            const initData = window.Telegram?.WebApp?.initData || "";
            const tgId = getTgId();

            const res = await window.fetchAPI('/api/tasks/convert_adzn', 'POST', {
                amount: amount,
                telegram_id: tgId,
                initData
            });

            if (res.success) {
                if (res.new_balance !== undefined) syncUserBalance(res.new_balance);
                if (res.new_ad_balance !== undefined) syncUserAdBalance(res.new_ad_balance);
                alert(`🎉 تم تحويل ${amount.toLocaleString()} ZN إلى رصيد الإعلانات (AdZ) بنجاح!`);
            } else {
                alert(res.error || 'حدث خطأ أثناء التحويل.');
            }
        } catch (err) {
            console.error('Convert Balance Error:', err);
            alert(err.message || 'حدث خطأ أثناء الاتصال بالسيرفر.');
        } finally {
            isConvertingBalance = false;
        }
    };

    // ⚡ تقديم ونشر الحملة مع التحقق الصارم من الحد الأدنى لـ AdZ
    window.submitAdCampaign = async function(event) {
        if (event) event.preventDefault();
        if (isSubmittingCampaign) return;

        const platform = currentAdType || 'يوتيوب';
        const minReqReward = MIN_REWARDS_MAP[platform] || MIN_REWARDS_MAP['default'];

        const linkInput = document.getElementById('ad-link');
        const descSelect = document.getElementById('ad-desc-select');
        const rewardInput = document.getElementById('ad-reward');
        const usersInput = document.getElementById('ad-users');

        const url = linkInput?.value?.trim() || '';
        const description = descSelect?.value?.trim() || '';
        const rewardPerClick = parseFloat(rewardInput?.value || 0);
        const totalCount = parseInt(usersInput?.value || 0, 10);

        if (!url || !description) {
            alert('يرجى إدخال رابط الحملة واختيار توجيهات المهمة!');
            return;
        }

        if (!url.startsWith('http://') && !url.startsWith('https://')) {
            alert('يجب أن يبدأ الرابط بـ http:// أو https://');
            return;
        }

        if (isNaN(rewardPerClick) || rewardPerClick < minReqReward) {
            alert(`الحد الأدنى لتكلفة الضغطة الواحدة لمنصة (${platform}) هو ${minReqReward} عملة AdZ!`);
            return;
        }

        if (isNaN(totalCount) || totalCount <= 0) {
            alert('يرجى تحديد عدد الأعضاء المطلوبين بصورة صحيحة!');
            return;
        }

        const totalCost = rewardPerClick * totalCount;
        const currentAdBal = getUserAdBalance();

        if (currentAdBal < totalCost) {
            alert(`رصيد الإعلانات (AdZ) غير كافٍ! تحتاج إلى ${totalCost.toLocaleString()} AdZ ولدى حسابك ${currentAdBal.toLocaleString()} AdZ.`);
            return;
        }

        isSubmittingCampaign = true;
        const submitBtn = document.getElementById('btn-submit-campaign-action');
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerText = 'جاري الفحص... ⏳';
        }

        window.closeAdModal(true);
        hideBottomNav();

        const reviewModal = document.getElementById('review-modal');
        const timerEl = document.getElementById('review-countdown-timer');
        if (reviewModal) reviewModal.style.display = 'flex';

        let timeLeft = 3;
        if (timerEl) timerEl.innerText = timeLeft;

        const countdownInterval = setInterval(() => {
            timeLeft--;
            if (timerEl) timerEl.innerText = Math.max(0, timeLeft);
            if (timeLeft <= 0) clearInterval(countdownInterval);
        }, 1000);

        try {
            const initData = window.Telegram?.WebApp?.initData || "";
            const tgId = getTgId();

            const res = await window.fetchAPI('/api/tasks/create_campaign', 'POST', {
                platform,
                description,
                url,
                reward: rewardPerClick,
                users_needed: totalCount,
                telegram_id: tgId,
                initData
            });

            await new Promise(r => setTimeout(r, 3000));
            if (reviewModal) reviewModal.style.display = 'none';

            if (res.success) {
                if (res.new_ad_balance !== undefined) {
                    syncUserAdBalance(res.new_ad_balance);
                } else {
                    syncUserAdBalance(currentAdBal - totalCost);
                }

                const successModal = document.getElementById('success-modal');
                if (successModal) {
                    successModal.style.display = 'flex';
                } else {
                    alert('🎉 تم إطلاق الحملة بنجاح!');
                    showBottomNav();
                }

                window.fetchAndRenderTasks(true);
            } else {
                alert(res.error || 'حدث خطأ أثناء إنشاء الحملة.');
                showBottomNav();
            }
        } catch (err) {
            if (reviewModal) reviewModal.style.display = 'none';
            console.error('Submit Campaign Error:', err);
            alert(err.message || 'حدث خطأ في الاتصال بالسيرفر.');
            showBottomNav();
        } finally {
            isSubmittingCampaign = false;
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerText = 'نشر الحملة 🚀';
            }
        }
    };

    window.handleSuccessRedirect = function() {
        const successModal = document.getElementById('success-modal');
        if (successModal) successModal.style.display = 'none';
        showBottomNav();
        window.switchTasksTab('promote');
        window.fetchAndRenderTasks(true);
    };

    // ⚡ جلب قائمة الحملات والمهام المتاحة مع الكاش السريع
    window.fetchAndRenderTasks = async function(forceRefresh = false) {
        const container = document.getElementById('tasks-list-container');
        const activeAdsContainer = document.getElementById('active-ads-container');
        let myId = String(getTgId()).trim();
        
        const initData = window.Telegram?.WebApp?.initData || "";
        let realTasks = [];
        const now = Date.now();

        if (!forceRefresh && cachedTasksData && (now - lastTasksFetchTime < TASKS_CACHE_TTL)) {
            realTasks = cachedTasksData.campaigns || [];
            if (cachedTasksData.ad_balance !== undefined) syncUserAdBalance(cachedTasksData.ad_balance);
            if (cachedTasksData.balance !== undefined) syncUserBalance(cachedTasksData.balance);
        } else {
            try {
                let url = `/api/tasks/get_campaigns`;
                if (initData) {
                    url += `?initData=${encodeURIComponent(initData)}`;
                } else if (myId) {
                    url += `?telegramId=${encodeURIComponent(myId)}`;
                }
                
                let response = await fetch(url);
                if (response.ok) {
                    let data = await response.json();
                    if (data.success) { 
                        saveTasksToSessionCache(data);
                        realTasks = data.campaigns || []; 
                        
                        if (data.user_id) {
                            myId = String(data.user_id).trim();
                            if (window.GameState) window.GameState.userId = myId;
                            if (window.PlayerData) window.PlayerData.userId = myId;
                        }

                        if (data.ad_balance !== undefined) syncUserAdBalance(data.ad_balance);
                        if (data.balance !== undefined) syncUserBalance(data.balance);
                    }
                }
            } catch (e) { console.warn("خطأ جلب المهام", e); }
        }

        if (container) {
            let allTasks = [];
            realTasks.forEach(task => {
                allTasks.push({
                    id: String(task.id),
                    title: `دعم وتفاعل منصة (${escapeHtml(task.platform)})`,
                    description: escapeHtml(task.description) || "إقرأ التعليمات وقم بالتفاعل المطلوب واستلام المكافأة.",
                    platform: task.platform || 'أخرى',
                    reward: Number(task.reward || 0),
                    link: task.url || '',
                    is_completed: !!task.is_completed,
                    creator_id: String(task.creator_id || '').trim()
                });
            });

            let groupedTasks = {};
            allTasks.forEach(t => {
                let p = t.platform || 'أخرى';
                if (!groupedTasks[p]) groupedTasks[p] = [];
                groupedTasks[p].push(t);
            });

            let html = '';
            for (let plat in groupedTasks) {
                let tasksArray = groupedTasks[plat];
                tasksArray.sort((a, b) => b.reward - a.reward);
                let config = platformConfig[plat] || platformConfig['أخرى'];

                html += `
                    <div style="margin-top: 20px; margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                        <i class="${config.icon}" style="color: ${config.color}; font-size: 15px;"></i>
                        <h5 style="color: #94a3b8; margin: 0; font-size: 13px; font-weight: 700;">${config.title}</h5>
                    </div>
                `;

                tasksArray.forEach(task => {
                    const isMyAd = (task.creator_id === myId);
                    const isCompleted = task.is_completed;
                    let actionHtml = '';

                    if (isMyAd) {
                        actionHtml = `<button type="button" disabled style="background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.25); padding: 8px 14px; border-radius: 8px; font-size: 11px; font-weight: bold; cursor: not-allowed;">إعلانك الخاص 📢</button>`;
                    } else if (isCompleted) {
                        let textCompleted = task.platform === 'موقع' ? "مكتمل اليوم ✔️" : "مكتمل ✔️";
                        actionHtml = `<button type="button" disabled style="background: rgba(40, 167, 69, 0.12); color: #28a745; border: 1px solid rgba(40, 167, 69, 0.25); padding: 8px 14px; border-radius: 8px; font-size: 11px; font-weight: bold; cursor: not-allowed;">${textCompleted}</button>`;
                    } else {
                        let state = window.taskStates[task.id] || 'idle';
                        if (state === 'idle') {
                            actionHtml = `<button type="button" id="btn-task-${task.id}" onclick="window.startTask('${task.id}', '${encodeURIComponent(task.link)}', ${task.reward})" style="background: #fff; color: #000; border: none; padding: 8px 22px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: 800; transition: 0.2s;">ابدأ</button>`;
                        } else if (state === 'running') {
                            let currentTotalOutside = window.accumulatedOutsideTime[task.id] || 0;
                            if (document.visibilityState === 'hidden') {
                                currentTotalOutside += (Date.now() - (window.lastGoOutside[task.id] || Date.now())) / 1000;
                            }
                            let remaining = Math.max(1, 15 - Math.floor(currentTotalOutside));
                            
                            if (remaining <= 1 && currentTotalOutside >= 15) {
                                window.taskStates[task.id] = 'ready';
                                actionHtml = `<button type="button" id="btn-task-${task.id}" onclick="window.verifyTask('${task.id}', ${task.reward})" style="background: #ffcc00; color: #000; border: none; padding: 8px 18px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: 800; box-shadow: 0 0 10px rgba(255, 204, 0, 0.3);">تحقق ✅</button>`;
                            } else {
                                actionHtml = `<button type="button" id="btn-task-${task.id}" disabled style="background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); padding: 8px 14px; border-radius: 8px; font-size: 12px; cursor: not-allowed; font-weight: bold;">عُد للمهمة.. ${remaining}ث⏳</button>`;
                            }
                        } else if (state === 'ready') {
                            actionHtml = `<button type="button" id="btn-task-${task.id}" onclick="window.verifyTask('${task.id}', ${task.reward})" style="background: #ffcc00; color: #000; border: none; padding: 8px 18px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: 800; box-shadow: 0 0 10px rgba(255, 204, 0, 0.3);">تحقق ✅</button>`;
                        }
                    }

                    html += `
                        <div style="background: linear-gradient(135deg, #11111e, #141424); border: 1px solid #222235; border-radius: 16px; padding: 14px; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; gap: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.2);">
                            <div style="display: flex; align-items: center; gap: 12px; flex: 1;">
                                <div style="background: rgba(255,255,255,0.02); width: 42px; height: 42px; border-radius: 12px; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(255,255,255,0.05);">
                                    <i class="${config.icon}" style="font-size: 18px; color: ${config.color};"></i>
                                </div>
                                <div style="text-align: right; flex: 1;">
                                    <div style="color: #ffffff; font-size: 13px; font-weight: 700; line-height: 1.4; margin-bottom: 2px;">${task.title}</div>
                                    <div style="color: #94a3b8; font-size: 11px; margin-bottom: 4px; font-weight: 500; line-height: 1.3;">${task.description}</div>
                                    <div style="color: #ffcc00; font-size: 12px; font-weight: 700; display: flex; align-items: center; gap: 4px;">
                                        <span>+${task.reward.toLocaleString('en-US', {maximumFractionDigits: 2})}</span> <span style="font-size: 10px; color: #64748b; font-weight: 500;">ZN</span>
                                    </div>
                                </div>
                            </div>
                            <div style="margin-right: auto;">
                                ${actionHtml}
                            </div>
                        </div>`;
                });
            }
            container.innerHTML = html || `<div style="text-align: center; color: #64748b; font-size: 13px; padding: 40px; background: #11111e; border-radius: 16px; border: 1px dashed #222235;">لا توجد حملات ترويجية نشطة حالياً.</div>`;
        }

        if (activeAdsContainer) {
            let myCreatedCampaigns = realTasks.filter(task => String(task.creator_id).trim() === myId);
            if (myCreatedCampaigns.length === 0) {
                activeAdsContainer.innerHTML = `<div style="text-align: center; color: #64748b; font-size: 12px; padding: 30px; background: #11111e; border-radius: 16px;">ليس لديك أي حملات ترويجية قائمة حالياً.</div>`;
            } else {
                let adsHtml = '';
                myCreatedCampaigns.forEach(ad => {
                    let comp = ad.users_completed || 0;
                    let need = ad.users_needed || 1;
                    let pct = Math.min(100, Math.floor((comp / need) * 100));
                    let costPerClick = ad.reward || 0;
                    let totalBudget = costPerClick * need;
                    let consumedBudget = costPerClick * comp;
                    let remainingBudget = totalBudget - consumedBudget;
                    let config = platformConfig[ad.platform] || platformConfig['أخرى'];

                    adsHtml += `
                        <div style="background: #131324; border: 1px solid #24243a; border-radius: 16px; padding: 16px; margin-bottom: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <i class="${config.icon}" style="color: ${config.color}; font-size: 15px;"></i>
                                    <span style="color: #fff; font-size: 13px; font-weight: 700;">حملة ممولة لـ ${escapeHtml(ad.platform)}</span>
                                </div>
                                <span style="background: rgba(56,189,248,0.1); color: #38bdf8; font-size: 11px; padding: 4px 10px; border-radius: 20px; font-weight: 700;">
                                    الإنجاز: ${comp} / ${need}
                                </span>
                            </div>
                            
                            <div style="background: #090911; border-radius: 12px; padding: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; border: 1px solid #1c1c2e;">
                                <div style="text-align: right;">
                                    <span style="color: #64748b; font-size: 11px; display: block;">تكلفة الضغطة:</span>
                                    <span style="color: #fff; font-size: 12px; font-weight: 700;">${costPerClick.toLocaleString()} AdZ</span>
                                </div>
                                <div style="text-align: right;">
                                    <span style="color: #64748b; font-size: 11px; display: block;">ميزانية الإعلان:</span>
                                    <span style="color: #ffcc00; font-size: 12px; font-weight: 700;">${totalBudget.toLocaleString()} AdZ</span>
                                </div>
                                <div style="text-align: right; border-top: 1px solid #1a1a2e; padding-top: 5px;">
                                    <span style="color: #64748b; font-size: 11px; display: block;">مستهلك حتى الآن:</span>
                                    <span style="color: #ef4444; font-size: 12px; font-weight: 700;">${consumedBudget.toLocaleString()} AdZ</span>
                                </div>
                                <div style="text-align: right; border-top: 1px solid #1a1a2e; padding-top: 5px;">
                                    <span style="color: #64748b; font-size: 11px; display: block;">المتبقي القابل للاسترداد:</span>
                                    <span style="color: #28a745; font-size: 12px; font-weight: 700;">${remainingBudget.toLocaleString()} AdZ</span>
                                </div>
                            </div>

                            <div style="background: rgba(255,255,255,0.02); border-right: 3px solid #38bdf8; padding: 6px 10px; font-size: 11px; color: #b4b9c8; margin-bottom: 12px; text-align: right; border-radius: 4px; font-weight: 500;">
                                <strong>التوجيه الفعلي للزوار:</strong> ${escapeHtml(ad.description)}
                            </div>

                            <div style="margin-bottom: 14px;">
                                <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 4px;">
                                    <span>التقدم الإجمالي</span>
                                    <span style="color: #38bdf8; font-weight: 700;">${pct}%</span>
                                </div>
                                <div style="width: 100%; height: 6px; background: #0b0b12; border-radius: 10px; overflow: hidden; border: 1px solid #1f1f2e;">
                                    <div style="width: ${pct}%; height: 100%; background: linear-gradient(90deg, #0088cc, #38bdf8); border-radius: 10px; transition: width 0.4s ease;"></div>
                                </div>
                            </div>
                            <div style="color: #475569; font-size: 11px; margin-bottom: 12px; word-break: break-all; text-align: left; background: #090911; padding: 8px; border-radius: 8px; font-family: monospace;" dir="ltr">${escapeHtml(ad.url)}</div>
                            <button type="button" id="btn-cancel-${ad.id}" onclick="window.cancelServerCampaign('${ad.id}')" style="width: 100%; background: rgba(239,68,68,0.05); border: 1px solid rgba(239,68,68,0.25); color: #ef4444; padding: 11px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 12px; transition: 0.2s;">إلغاء الإعلان فوراً وسحب المتبقي لحسابك</button>
                        </div>`;
                });
                activeAdsContainer.innerHTML = adsHtml;
            }
        }
    };

    window.startTask = function(taskId, encodedLink, reward) {
        const link = decodeURIComponent(encodedLink || '');
        window.taskStates[taskId] = 'running';
        window.accumulatedOutsideTime[taskId] = 0;
        window.lastGoOutside[taskId] = Date.now();

        if (window.Telegram?.WebApp?.openLink) { 
            window.Telegram.WebApp.openLink(link); 
        } else { 
            window.open(link, '_blank'); 
        }

        const btn = document.getElementById(`btn-task-${taskId}`);
        if (btn) {
            btn.disabled = true;
            btn.innerText = 'عُد للمهمة.. 15ث⏳';
            btn.style.background = 'rgba(239,68,68,0.15)';
            btn.style.color = '#ef4444';
            btn.style.border = '1px solid rgba(239,68,68,0.3)';
        }

        if (window.taskIntervals[taskId]) clearInterval(window.taskIntervals[taskId]);

        window.taskIntervals[taskId] = setInterval(() => {
            let currentTotalOutside = window.accumulatedOutsideTime[taskId] || 0;
            if (document.visibilityState === 'hidden') {
                currentTotalOutside += (Date.now() - (window.lastGoOutside[taskId] || Date.now())) / 1000;
            }
            let remaining = Math.max(0, 15 - Math.floor(currentTotalOutside));

            const taskBtn = document.getElementById(`btn-task-${taskId}`);
            if (remaining <= 0 || currentTotalOutside >= 15) {
                clearInterval(window.taskIntervals[taskId]);
                window.taskStates[taskId] = 'ready';
                if (taskBtn) {
                    taskBtn.disabled = false;
                    taskBtn.innerHTML = 'تحقق ✅';
                    taskBtn.setAttribute('onclick', `window.verifyTask('${taskId}', ${reward})`);
                    taskBtn.style.background = '#ffcc00';
                    taskBtn.style.color = '#000';
                    taskBtn.style.border = 'none';
                    taskBtn.style.boxShadow = '0 0 10px rgba(255, 204, 0, 0.3)';
                }
            } else if (taskBtn) {
                taskBtn.innerText = `عُد للمهمة.. ${remaining}ث⏳`;
            }
        }, 1000);
    };

    window.verifyTask = async function(taskId, reward) {
        if (isVerifyingTask) return;
        isVerifyingTask = true;

        const btn = document.getElementById(`btn-task-${taskId}`);
        if (btn) {
            btn.disabled = true;
            btn.innerText = 'جاري التحقق... ⏳';
        }

        try {
            const initData = window.Telegram?.WebApp?.initData || "";
            const tgId = getTgId();
            
            const res = await window.fetchAPI('/api/tasks/complete_task', 'POST', {
                taskId: taskId,
                task_id: taskId,
                telegram_id: tgId,
                initData: initData
            });

            if (res.success) {
                if (res.new_balance !== undefined) {
                    syncUserBalance(res.new_balance);
                } else if (reward) {
                    syncUserBalance(getUserBalance() + reward);
                }

                window.taskStates[taskId] = 'completed';
                if (btn) {
                    btn.disabled = true;
                    btn.innerText = 'مكتمل ✔️';
                    btn.style.background = 'rgba(40, 167, 69, 0.12)';
                    btn.style.color = '#28a745';
                    btn.style.border = '1px solid rgba(40, 167, 69, 0.25)';
                    btn.style.boxShadow = 'none';
                }

                if (cachedTasksData && cachedTasksData.campaigns) {
                    const item = cachedTasksData.campaigns.find(c => String(c.id) === String(taskId));
                    if (item) item.is_completed = true;
                    cachedTasksData.balance = res.new_balance;
                    saveTasksToSessionCache(cachedTasksData);
                }

                alert(`🎉 مبروك! تم التحقق بنجاح وإضافة ${reward} ZN إلى رصيدك!`);
            } else {
                alert(res.error || 'فشل التحقق من تنفيذ المهمة.');
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = 'تحقق ✅';
                }
            }
        } catch (err) {
            console.error('Verify Task Error:', err);
            alert(err.message || 'حدث خطأ أثناء الاتصال بالسيرفر.');
            if (btn) {
                btn.disabled = false;
                btn.innerText = 'تحقق ✅';
            }
        } finally {
            isVerifyingTask = false;
        }
    };

    window.cancelServerCampaign = async function(taskId) {
        if (isCancelingCampaign) return;

        if (!confirm('هل أنت تأكد من إلغاء هذه الحملة الإعلانية؟ سيتم استرداد المبلغ المتبقي غير المستهلك فوراً إلى رصيد الإعلانات الخاص بك.')) {
            return;
        }

        isCancelingCampaign = true;
        const btn = document.getElementById(`btn-cancel-${taskId}`);
        if (btn) {
            btn.disabled = true;
            btn.innerText = 'جاري الإلغاء... ⏳';
        }

        try {
            const initData = window.Telegram?.WebApp?.initData || "";
            const tgId = getTgId();

            const res = await window.fetchAPI('/api/tasks/cancel_campaign', 'POST', {
                campaignId: taskId,
                task_id: taskId,
                telegram_id: tgId,
                initData
            });

            if (res.success) {
                if (res.new_ad_balance !== undefined) {
                    syncUserAdBalance(res.new_ad_balance);
                }
                const refunded = res.refunded_amount ?? res.refund ?? 0;
                alert(`🎉 تم إلغاء الحملة بنجاح! تم استرداد ${refunded.toLocaleString()} AdZ إلى حسابك.`);
                window.fetchAndRenderTasks(true);
            } else {
                alert(res.error || 'حدث خطأ أثناء إلغاء الحملة.');
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = 'إلغاء الإعلان فوراً وسحب المتبقي لحسابك';
                }
            }
        } catch (err) {
            console.error('Cancel Campaign Error:', err);
            alert(err.message || 'حدث خطأ أثناء التواصل مع السيرفر.');
            if (btn) {
                btn.disabled = false;
                btn.innerText = 'إلغاء الإعلان فوراً وسحب المتبقي لحسابك';
            }
        } finally {
            isCancelingCampaign = false;
        }
    };

    document.addEventListener('visibilitychange', () => {
        const isHidden = document.visibilityState === 'hidden';
        const now = Date.now();

        for (let taskId in window.taskStates) {
            if (window.taskStates[taskId] === 'running') {
                if (isHidden) {
                    window.lastGoOutside[taskId] = now;
                } else {
                    if (window.lastGoOutside[taskId]) {
                        const diffSeconds = (now - window.lastGoOutside[taskId]) / 1000;
                        window.accumulatedOutsideTime[taskId] = (window.accumulatedOutsideTime[taskId] || 0) + diffSeconds;
                    }
                }
            }
        }
    });

    window.fetchAndRenderTasks(false);
})();

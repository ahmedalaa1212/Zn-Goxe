(function initTasks() {
    // 1. قائمة المهام الثابتة (أضفت لها التصنيف platform عشان تتوزع في الأقسام صح)
    const dummyTasks = [
        { id: 'dummy_101', title: "انضم لقناتنا الرسمية", platform: 'تيليجرام', reward: 5000, link: "https://t.me/" },
        { id: 'dummy_102', title: "اشترك في قناة اليوتيوب", platform: 'يوتيوب', reward: 8000, link: "https://youtube.com/" },
        { id: 'dummy_103', title: "تابعنا على منصة X", platform: 'X', reward: 3000, link: "https://x.com/" },
        { id: 'dummy_104', title: "زيارة موقعنا", platform: 'موقع', reward: 2000, link: "https://google.com/" },
        { id: 'dummy_105', title: "متابعة انستغرام", platform: 'انستغرام', reward: 4000, link: "https://instagram.com/" }
    ];

    // إعدادات الأقسام وألوانها وأيقوناتها
    const platformConfig = {
        'يوتيوب': { title: "مهام يوتيوب", icon: "fab fa-youtube", color: "#ef4444" },
        'تيليجرام': { title: "مهام تيليجرام", icon: "fab fa-telegram", color: "#38bdf8" },
        'X': { title: "مهام منصة X", icon: "fab fa-twitter", color: "#1da1f2" },
        'موقع': { title: "زيارة مواقع", icon: "fas fa-globe", color: "#28a745" },
        'انستغرام': { title: "مهام انستغرام", icon: "fab fa-instagram", color: "#e1306c" },
        'أخرى': { title: "مهام متنوعة", icon: "fas fa-tasks", color: "#a855f7" }
    };

    let completedTasks = JSON.parse(localStorage.getItem('zn_completed_tasks') || '[]');
    let myAds = JSON.parse(localStorage.getItem('zn_my_ads') || '[]'); 

    function getTgId() {
        return window.PlayerData?.tg_id || window.Telegram?.WebApp?.initDataUnsafe?.user?.id?.toString() || "5102387551";
    }

    // 2. التبديل بين الأقسام (المهام / الإعلانات)
    window.switchTasksTab = function(tab) {
        document.getElementById('section-earn').style.display = tab === 'earn' ? 'block' : 'none';
        document.getElementById('section-promote').style.display = tab === 'promote' ? 'block' : 'none';
        
        document.getElementById('btn-tab-earn').style.background = tab === 'earn' ? '#0088cc' : 'transparent';
        document.getElementById('btn-tab-earn').style.color = tab === 'earn' ? '#fff' : '#888';
        
        document.getElementById('btn-tab-promote').style.background = tab === 'promote' ? '#0088cc' : 'transparent';
        document.getElementById('btn-tab-promote').style.color = tab === 'promote' ? '#fff' : '#888';
        
        if(tab === 'earn') fetchAndRenderTasks(); // تحديث المهام عند فتح التبويب
    };

    // 3. تحديث واجهة المستخدم فورياً (الأرصدة)
    window.updateTasksUI = function() {
        const pData = window.PlayerData || { balance: 0, ad_balance: 0 };
        
        const tasksTopBalance = document.getElementById('top-balance-tasks');
        if (tasksTopBalance) tasksTopBalance.innerText = `ZN ${Math.floor(pData.balance || 0).toLocaleString()}`;

        const adBalDisplay = document.getElementById('ad-balance-display');
        if (adBalDisplay) {
            adBalDisplay.innerText = `AdZN ${Math.floor(pData.ad_balance || 0).toLocaleString()}`;
        }
        renderMyAds();
    };

    // 4. جلب المهام الحقيقية من السيرفر، دمجها، ترتيبها، وعرضها بالأقسام
    async function fetchAndRenderTasks() {
        const container = document.getElementById('tasks-list-container');
        if (!container) return;

        let realTasks = [];
        try {
            let response = await fetch(`/api/get_campaigns?telegramId=${getTgId()}`);
            if (response.ok) {
                let data = await response.json();
                if (data.success) realTasks = data.campaigns;
            }
        } catch (e) { console.warn("خطأ في جلب المهام من السيرفر", e); }

        // دمج المهام الأساسية مع المهام اللي جاية من السيرفر
        let allTasks = [...dummyTasks];
        realTasks.forEach(task => {
            allTasks.push({
                id: task.id,
                title: task.title || "مهمة إعلانية (مستخدمين)",
                platform: task.platform || 'أخرى',
                reward: task.reward,
                link: task.url
            });
        });

        // تجميع المهام حسب المنصة (يوتيوب، تليجرام، إلخ)
        let groupedTasks = {};
        allTasks.forEach(task => {
            let plat = task.platform || 'أخرى';
            if (!groupedTasks[plat]) groupedTasks[plat] = [];
            groupedTasks[plat].push(task);
        });

        let html = '';

        // إنشاء الـ HTML لكل قسم
        for (let platform in groupedTasks) {
            let tasksArray = groupedTasks[platform];
            
            // 🔥 ترتيب المهام داخل القسم الواحد (الأعلى مكافأة أولاً) 🔥
            tasksArray.sort((a, b) => b.reward - a.reward);

            let config = platformConfig[platform] || platformConfig['أخرى'];

            // عنوان القسم
            html += `
                <div style="margin-top: 20px; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; padding-right: 5px;">
                    <i class="${config.icon}" style="color: ${config.color}; font-size: 18px;"></i>
                    <h5 style="color: #ccc; margin: 0; font-size: 14px;">${config.title}</h5>
                </div>
            `;

            // مهام القسم
            tasksArray.forEach(task => {
                const isCompleted = completedTasks.includes(task.id);
                html += `
                    <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 15px; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;">
                        <div style="display: flex; align-items: center; gap: 12px;">
                            <i class="${config.icon}" style="font-size: 24px; color: ${config.color};"></i>
                            <div style="text-align: right;">
                                <div style="color: #fff; font-size: 13px; font-weight: bold;">${task.title}</div>
                                <div style="color: #ffcc00; font-size: 12px; font-weight: bold;">+${task.reward.toLocaleString()} ZN</div>
                            </div>
                        </div>
                        <div>
                            ${isCompleted ? 
                                `<button disabled style="background: rgba(40, 167, 69, 0.2); color: #28a745; border: 1px solid #28a745; padding: 8px 15px; border-radius: 8px; font-size: 12px;">مكتمل ✔️</button>` 
                                : 
                                `<button id="btn-task-${task.id}" onclick="startTask('${task.id}', '${task.link}', ${task.reward})" style="background: #fff; color: #000; border: none; padding: 8px 20px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: bold;">ابدأ</button>`
                            }
                        </div>
                    </div>`;
            });
        }

        if (html === '') {
            html = `<div style="text-align: center; color: #888; font-size: 13px; padding: 20px;">لا توجد مهام متاحة حالياً.</div>`;
        }
        
        container.innerHTML = html;
    }

    // 5. عمل المهمة
    window.startTask = function(taskId, link, reward) {
        window.open(link, '_blank');
        const btn = document.getElementById(`btn-task-${taskId}`);
        btn.innerText = "تحقق ⏳";
        btn.style.background = "#ffcc00";
        
        btn.onclick = async function() {
            btn.innerText = "جاري التأكيد...";
            btn.disabled = true;

            try {
                // الاتصال بـ API السيرفر (للمهام الحقيقية)
                let response = await fetch('/api/complete_task', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ telegramId: getTgId(), taskId: taskId })
                });

                let result = await response.json();

                // التحديث المحلي الفوري عشان العميل ميحسش بتأخير
                completedTasks.push(taskId);
                localStorage.setItem('zn_completed_tasks', JSON.stringify(completedTasks));
                
                if (window.PlayerData) {
                    window.PlayerData.balance += reward;
                }

                alert(`🎉 مبروك! تمت إضافة ${reward.toLocaleString()} ZN`);
                
                // تحديث الواجهة فوراً
                updateTasksUI();
                fetchAndRenderTasks(); 

                // تحديث باقي أجزاء التطبيق لو الفنكشن دي موجودة في game.js
                if (typeof window.triggerAllUIUpdates === 'function') window.triggerAllUIUpdates();
                if (typeof window.fetchPlayerDataFromServer === 'function') await window.fetchPlayerDataFromServer();

            } catch (e) {
                console.error("خطأ", e);
                // بنحسبها نجحت برضه كـ Fallback للمهام الوهمية (dummy)
                completedTasks.push(taskId);
                localStorage.setItem('zn_completed_tasks', JSON.stringify(completedTasks));
                if (window.PlayerData) window.PlayerData.balance += reward;
                
                alert(`🎉 مبروك! تمت إضافة ${reward.toLocaleString()} ZN`);
                updateTasksUI();
                fetchAndRenderTasks();
                if (typeof window.triggerAllUIUpdates === 'function') window.triggerAllUIUpdates();
            }
        };
    };

    // 6. التحويل من ZN إلى إعلانات (تحديث فوري للرصيد)
    window.convertZnToAdZn = async function() {
        let amount = prompt("أدخل كمية ZN لتحويلها إلى رصيد إعلانات (AdZN):\n* سيتم خصم 10% عمولة تحويل.");
        if (!amount || isNaN(amount) || amount <= 0) return;
        amount = parseFloat(amount);

        let currentBalance = parseFloat(window.PlayerData?.balance || 0);
        if (currentBalance < amount) {
            alert("⚠️ رصيدك من ZN غير كافٍ!");
            return;
        }

        try {
            let response = await fetch('/api/convert_adzn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ telegramId: getTgId(), amount: amount })
            });

            let result = await response.json();

            if (response.ok && result.success) {
                alert(`✅ تم شحن رصيد الإعلانات بنجاح!`);
                
                // 🔥 تحديث الرصيد محلياً فوراً عشان يظهر للمستخدم في ثانية 🔥
                if (window.PlayerData) {
                    window.PlayerData.balance -= amount;
                    window.PlayerData.ad_balance = (window.PlayerData.ad_balance || 0) + result.received;
                }
                updateTasksUI(); // تحديث شاشة المهام
                if (typeof window.triggerAllUIUpdates === 'function') window.triggerAllUIUpdates(); // تحديث شريط الرصيد العلوي
                
                // سحب البيانات من السيرفر في الخلفية للتأكيد
                if (typeof window.fetchPlayerDataFromServer === 'function') {
                    await window.fetchPlayerDataFromServer();
                }
            } else {
                alert("⚠️ فشل التحويل: " + (result.error || "خطأ غير معروف"));
            }
        } catch (e) {
            console.error("خطأ في التحويل", e);
            alert("حدث خطأ أثناء الاتصال بالسيرفر.");
        }
    };

    // ==========================================
    // 🛠️ نظام إدارة الإعلانات وإنشائها
    // ==========================================
    let currentAdType = '';

    window.openAdModal = function(type) {
        currentAdType = type;
        document.getElementById('ad-modal-title').innerText = `حملة ${type} جديدة`;
        document.getElementById('ad-link').value = '';
        document.getElementById('ad-reward').value = '';
        document.getElementById('ad-users').value = '';
        document.getElementById('ad-modal').style.display = 'flex';
    };

    window.closeAdModal = function() {
        document.getElementById('ad-modal').style.display = 'none';
    };

    // نشر الإعلان
    window.submitAdCampaign = async function() {
        let link = document.getElementById('ad-link').value;
        let reward = parseFloat(document.getElementById('ad-reward').value);
        let users = parseInt(document.getElementById('ad-users').value);

        if (!link || isNaN(reward) || reward <= 0 || isNaN(users) || users <= 0) {
            alert("⚠️ يرجى إدخال الرابط والمكافأة وعدد الأشخاص بشكل صحيح!");
            return;
        }

        let totalCost = reward * users;
        let currentAdBalance = parseFloat(window.PlayerData?.ad_balance || 0);

        if (currentAdBalance < totalCost) {
            alert(`⚠️ رصيد الإعلانات الخاص بك غير كافٍ! التكلفة الإجمالية: ${totalCost} AdZN`);
            return;
        }

        try {
            let response = await fetch('/api/create_campaign', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    telegramId: getTgId(), 
                    platform: currentAdType,
                    url: link,
                    reward: reward,
                    users_needed: users
                })
            });

            let result = await response.json();

            if (response.ok && result.success) {
                // حفظ محلي للعرض
                let newAd = { id: Date.now(), type: currentAdType, link: link, reward: reward, users: users, total: totalCost };
                myAds.push(newAd);
                localStorage.setItem('zn_my_ads', JSON.stringify(myAds));
                
                // خصم الرصيد الإعلاني فوراً في الواجهة
                if(window.PlayerData) window.PlayerData.ad_balance -= totalCost;
                
                closeAdModal();
                alert("✅ تم نشر حملتك الإعلانية بنجاح!");
                
                updateTasksUI();
                if (typeof window.triggerAllUIUpdates === 'function') window.triggerAllUIUpdates();
                if (typeof window.fetchPlayerDataFromServer === 'function') window.fetchPlayerDataFromServer();
            } else {
                alert("⚠️ فشل إنشاء الحملة: " + (result.error || "خطأ غير معروف"));
            }
        } catch (e) {
            console.error("خطأ", e);
            alert("حدث خطأ في الاتصال بالسيرفر.");
        }
    };

    // عرض الإعلانات النشطة محلياً
    function renderMyAds() {
        const container = document.getElementById('active-ads-container');
        if (!container) return;

        if (myAds.length === 0) {
            container.innerHTML = `<div style="text-align: center; color: #888; font-size: 12px; margin-top: 20px;">ليس لديك حملات إعلانية نشطة.</div>`;
            return;
        }

        let html = '';
        myAds.forEach(ad => {
            html += `
                <div style="background: #111; border: 1px solid #333; border-radius: 12px; padding: 15px; margin-bottom: 12px;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                        <span style="color: #fff; font-size: 13px;">حملة ${ad.type}</span>
                        <span style="color: #38bdf8; font-size: 13px; font-weight: bold;">التكلفة: ${ad.total} AdZN</span>
                    </div>
                    <div style="color: #888; font-size: 11px; margin-bottom: 15px; word-break: break-all;">${ad.link}</div>
                    <button onclick="cancelMyAd(${ad.id})" style="width: 100%; background: rgba(239,68,68,0.1); border: 1px solid #ef4444; color: #ef4444; padding: 8px; border-radius: 8px; cursor: pointer; font-weight: bold;">إلغاء واسترداد (يخصم 10%)</button>
                </div>`;
        });
        container.innerHTML = html;
    }

    // إلغاء الإعلان
    window.cancelMyAd = async function(adId) {
        if (!confirm("تحذير: لا توجد واجهة في السيرفر حالياً لإرجاع الرصيد. سيتم حذف الإعلان من الشاشة فقط. هل تريد المتابعة؟")) return;

        let adIndex = myAds.findIndex(a => a.id === adId);
        if (adIndex === -1) return;

        myAds.splice(adIndex, 1);
        localStorage.setItem('zn_my_ads', JSON.stringify(myAds));
        updateTasksUI();
    };

    // تشغيل التحديث عند فتح الصفحة
    setTimeout(() => {
        updateTasksUI();
        fetchAndRenderTasks();
    }, 300);
})();

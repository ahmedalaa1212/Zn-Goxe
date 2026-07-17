(function initTasks() {
    // 1. قائمة المهام الثابتة (للتجربة)
    const dummyTasks = [
        { id: 'dummy_101', title: "انضم لقناتنا الرسمية", platform: 'تيليجرام', reward: 5000, link: "https://t.me/" },
        { id: 'dummy_102', title: "اشترك في قناة اليوتيوب", platform: 'يوتيوب', reward: 8000, link: "https://youtube.com/" },
        { id: 'dummy_103', title: "تابعنا على منصة X", platform: 'X', reward: 3000, link: "https://x.com/" },
        { id: 'dummy_104', title: "زيارة موقعنا", platform: 'موقع', reward: 2000, link: "https://google.com/" },
        { id: 'dummy_105', title: "متابعة انستغرام", platform: 'انستغرام', reward: 4000, link: "https://instagram.com/" }
    ];

    // إعدادات الأقسام وألوانها وأيقوناتها لتنظيم المهام
    const platformConfig = {
        'يوتيوب': { title: "مهام يوتيوب", icon: "fab fa-youtube", color: "#ef4444" },
        'تيليجرام': { title: "مهام تيليجرام", icon: "fab fa-telegram", color: "#38bdf8" },
        'X': { title: "مهام منصة X", icon: "fab fa-twitter", color: "#1da1f2" },
        'موقع': { title: "زيارة مواقع", icon: "fas fa-globe", color: "#28a745" },
        'انستغرام': { title: "مهام انستغرام", icon: "fab fa-instagram", color: "#e1306c" },
        'أخرى': { title: "مهام متنوعة", icon: "fas fa-tasks", color: "#a855f7" }
    };

    let completedTasks = JSON.parse(localStorage.getItem('zn_completed_tasks') || '[]');

    function getTgId() {
        return window.PlayerData?.tg_id || window.Telegram?.WebApp?.initDataUnsafe?.user?.id?.toString() || "5102387551";
    }

    // 2. التبديل بين قسم (اكسب ZN) وقسم (روّج لقناتك)
    window.switchTasksTab = function(tab) {
        document.getElementById('section-earn').style.display = tab === 'earn' ? 'block' : 'none';
        document.getElementById('section-promote').style.display = tab === 'promote' ? 'block' : 'none';
        
        document.getElementById('btn-tab-earn').style.background = tab === 'earn' ? '#0088cc' : 'transparent';
        document.getElementById('btn-tab-earn').style.color = tab === 'earn' ? '#fff' : '#888';
        
        document.getElementById('btn-tab-promote').style.background = tab === 'promote' ? '#0088cc' : 'transparent';
        document.getElementById('btn-tab-promote').style.color = tab === 'promote' ? '#fff' : '#888';
        
        if(tab === 'earn' || tab === 'promote') {
            window.fetchAndRenderTasks(); 
        }
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
        
        window.fetchAndRenderTasks();
    };

    // 4. جلب المهام والإعلانات من السيرفر ورسمها للمستخدمين
    window.fetchAndRenderTasks = async function() {
        const container = document.getElementById('tasks-list-container');
        const activeAdsContainer = document.getElementById('active-ads-container');
        
        let realTasks = [];
        try {
            let response = await fetch(`/api/get_campaigns?telegramId=${getTgId()}`);
            if (response.ok) {
                let data = await response.json();
                if (data.success) {
                    realTasks = data.campaigns;
                }
            }
        } catch (e) { 
            console.warn("خطأ في جلب المهام من السيرفر", e); 
        }

        // ==========================================
        // 🟢 قسم: اكسب ZN (عرض المهام المتاحة للجميع)
        // ==========================================
        if (container) {
            let allTasks = [...dummyTasks];
            realTasks.forEach(task => {
                allTasks.push({
                    id: task.id,
                    title: `مهمة زيادة تفاعل (${task.platform})`,
                    platform: task.platform || 'أخرى',
                    reward: task.reward,
                    link: task.url,
                    is_completed: task.is_completed,
                    creator_id: task.creator_id
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
                
                // الترتيب التنازلي: الأغلى يظهر فوق
                tasksArray.sort((a, b) => b.reward - a.reward);
                
                let config = platformConfig[plat] || platformConfig['أخرى'];

                html += `
                    <div style="margin-top: 20px; margin-bottom: 10px; display: flex; align-items: center; gap: 8px;">
                        <i class="${config.icon}" style="color: ${config.color}; font-size: 16px;"></i>
                        <h5 style="color: #ccc; margin: 0; font-size: 13px;">${config.title}</h5>
                    </div>
                `;

                tasksArray.forEach(task => {
                    const isCompleted = task.is_completed || completedTasks.includes(task.id);
                    html += `
                        <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 15px; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <i class="${config.icon}" style="font-size: 22px; color: ${config.color};"></i>
                                <div style="text-align: right;">
                                    <div style="color: #fff; font-size: 13px; font-weight: bold;">${task.title}</div>
                                    <div style="color: #ffcc00; font-size: 12px; font-weight: bold;">+${task.reward.toLocaleString()} ZN</div>
                                </div>
                            </div>
                            <div>
                                ${isCompleted ? 
                                    `<button disabled style="background: rgba(40, 167, 69, 0.2); color: #28a745; border: 1px solid #28a745; padding: 8px 15px; border-radius: 8px; font-size: 12px;">مكتمل ✔️</button>` : 
                                    `<button id="btn-task-${task.id}" onclick="startTask('${task.id}', '${task.link}', ${task.reward})" style="background: #fff; color: #000; border: none; padding: 8px 20px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: bold;">ابدأ</button>`
                                }
                            </div>
                        </div>`;
                });
            }
            container.innerHTML = html || `<div style="text-align: center; color: #888; font-size: 12px; padding: 20px;">لا توجد مهام متاحة حالياً.</div>`;
        }

        // ==========================================
        // 🔵 قسم: روّج لقناتك (حماية الإعلانات النشطة)
        // ==========================================
        if (activeAdsContainer) {
            let myId = String(getTgId()).trim();
            // هنا الفلترة بتضمن إن مفيش مستخدم هيشوف إعلانات غيره في القسم ده
            let myCreatedCampaigns = realTasks.filter(task => String(task.creator_id).trim() === myId);

            if (myCreatedCampaigns.length === 0) {
                activeAdsContainer.innerHTML = `<div style="text-align: center; color: #888; font-size: 12px; margin-top: 20px;">ليس لديك حملات إعلانية نشطة.</div>`;
                return;
            }

            let adsHtml = '';
            myCreatedCampaigns.forEach(ad => {
                adsHtml += `
                    <div style="background: #111; border: 1px solid #333; border-radius: 12px; padding: 15px; margin-bottom: 12px;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                            <span style="color: #fff; font-size: 13px; font-weight: bold;">حملة ${ad.platform}</span>
                            <span style="color: #38bdf8; font-size: 12px;">مكتمل: ${ad.users_completed || 0}/${ad.users_needed || 0}</span>
                        </div>
                        <div style="color: #888; font-size: 11px; margin-bottom: 12px; word-break: break-all; text-align: left;" dir="ltr">${ad.url}</div>
                        <button onclick="cancelServerCampaign('${ad.id}')" style="width: 100%; background: rgba(239,68,68,0.1); border: 1px solid #ef4444; color: #ef4444; padding: 8px; border-radius: 8px; cursor: pointer; font-weight: bold; font-size: 12px;">إلغاء واسترداد المتبقي (يخصم 10%)</button>
                    </div>`;
            });
            activeAdsContainer.innerHTML = adsHtml;
        }
    };

    // 5. تنفيذ المهمة (للمستخدمين)
    window.startTask = function(taskId, link, reward) {
        window.open(link, '_blank');
        const btn = document.getElementById(`btn-task-${taskId}`);
        if (!btn) return;
        
        btn.innerText = "تحقق ⏳";
        btn.style.background = "#ffcc00";
        
        btn.onclick = async function() {
            btn.innerText = "جاري التأكيد...";
            btn.disabled = true;
            try {
                let response = await fetch('/api/complete_task', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ telegramId: getTgId(), taskId: taskId })
                });
                let result = await response.json();
                
                if (response.ok && result.success) {
                    completedTasks.push(taskId);
                    localStorage.setItem('zn_completed_tasks', JSON.stringify(completedTasks));
                    if (window.PlayerData) window.PlayerData.balance += reward;
                    alert(`🎉 مبروك! تمت إضافة ${reward.toLocaleString()} ZN`);
                } else {
                    alert("⚠️ فشل التحقق: " + (result.error || "تأكد من إتمام المهمة أولاً"));
                }
            } catch (e) {
                // وضع احتياطي للمهام الثابتة (للتجربة)
                completedTasks.push(taskId);
                localStorage.setItem('zn_completed_tasks', JSON.stringify(completedTasks));
                if (window.PlayerData) window.PlayerData.balance += reward;
                alert(`🎉 مبروك! تمت إضافة ${reward.toLocaleString()} ZN`);
            }
            
            window.fetchAndRenderTasks();
            if (typeof window.triggerAllUIUpdates === 'function') {
                window.triggerAllUIUpdates();
            } else {
                const pData = window.PlayerData || {};
                const topBal = document.getElementById('top-balance-tasks');
                if (topBal) topBal.innerText = `ZN ${Math.floor(pData.balance || 0).toLocaleString()}`;
            }
        };
    };

    // 6. زر الإلغاء (مرتبط بالسيرفر ومحمي)
    window.cancelServerCampaign = async function(campId) {
        if (!confirm("هل أنت متأكد من إلغاء الحملة واستعادة قيمة النقرات المتبقية إلى رصيدك الإعلاني بعد خصم العمولة (10%)؟")) return;
        
        try {
            let response = await fetch('/api/cancel_campaign', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ telegramId: getTgId(), campaignId: campId })
            });
            let result = await response.json();
            
            if (response.ok && result.success) {
                alert(`✅ تم إلغاء الحملة بنجاح واسترداد ${Math.floor(result.refund)} AdZN!`);
                if (typeof window.fetchPlayerDataFromServer === 'function') await window.fetchPlayerDataFromServer();
                window.fetchAndRenderTasks();
            } else {
                alert("⚠️ فشل الإلغاء: " + (result.error || "خطأ غير معروف"));
            }
        } catch (e) {
            alert("حدث خطأ في الاتصال بالسيرفر أثناء الإلغاء.");
        }
    };

    // 7. تحويل ZN إلى رصيد إعلانات AdZN
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
                
                if (window.PlayerData) {
                    window.PlayerData.balance -= amount;
                    window.PlayerData.ad_balance = (window.PlayerData.ad_balance || 0) + result.received;
                }
                
                const pData = window.PlayerData;
                const tasksTopBalance = document.getElementById('top-balance-tasks');
                if (tasksTopBalance) tasksTopBalance.innerText = `ZN ${Math.floor(pData.balance || 0).toLocaleString()}`;

                const adBalDisplay = document.getElementById('ad-balance-display');
                if (adBalDisplay) adBalDisplay.innerText = `AdZN ${Math.floor(pData.ad_balance || 0).toLocaleString()}`;
                
                if (typeof window.triggerAllUIUpdates === 'function') window.triggerAllUIUpdates();
                if (typeof window.fetchPlayerDataFromServer === 'function') await window.fetchPlayerDataFromServer();
            } else {
                alert("⚠️ فشل التحويل: " + (result.error || "تأكد من تجميع الرصيد أولاً"));
            }
        } catch (e) { 
            alert("حدث خطأ في الاتصال بالسيرفر أثناء التحويل."); 
        }
    };

    // ==========================================
    // 🛠️ نظام إنشاء الإعلانات والنوافذ المنبثقة
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

    window.submitAdCampaign = async function() {
        let link = document.getElementById('ad-link').value;
        let reward = parseFloat(document.getElementById('ad-reward').value);
        let users = parseInt(document.getElementById('ad-users').value);

        if (!link || isNaN(reward) || reward <= 0 || isNaN(users) || users <= 0) {
            alert("⚠️ يرجى إدخال البيانات بشكل صحيح!");
            return;
        }

        let totalCost = reward * users;
        let currentAdBalance = parseFloat(window.PlayerData?.ad_balance || 0);

        if (currentAdBalance < totalCost) {
            alert(`⚠️ رصيد الإعلانات غير كافٍ! التكلفة: ${totalCost} AdZN`);
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
                closeAdModal();
                alert("✅ تم نشر حملتك الإعلانية بنجاح على السيرفر!");
                
                // تحديث سريع للواجهة الأمامية
                if(window.PlayerData) window.PlayerData.ad_balance -= totalCost;
                const adBalDisplay = document.getElementById('ad-balance-display');
                if (adBalDisplay) adBalDisplay.innerText = `AdZN ${Math.floor(window.PlayerData.ad_balance || 0).toLocaleString()}`;
                
                if (typeof window.fetchPlayerDataFromServer === 'function') await window.fetchPlayerDataFromServer();
                window.fetchAndRenderTasks();
            } else {
                alert("⚠️ فشل إنشاء الحملة: " + (result.error || "خطأ غير معروف"));
            }
        } catch (e) { 
            alert("حدث خطأ في الاتصال بالسيرفر أثناء نشر الإعلان."); 
        }
    };

    // تشغيل مبدئي لتحديث الشاشة بمجرد تحميل الصفحة
    setTimeout(() => {
        if(typeof window.updateTasksUI === 'function') window.updateTasksUI();
    }, 400);

})();

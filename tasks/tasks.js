(function initTasks() {
    // حالة المهام لتشغيل العداد والتحقق
    window.activeTasksState = window.activeTasksState || {};
    window.taskTimers = window.taskTimers || {};

    // إعدادات الأقسام وألوانها وأيقوناتها لتنظيم المهام الحقيقية
    const platformConfig = {
        'يوتيوب': { title: "مهام يوتيوب", icon: "fab fa-youtube", color: "#ef4444" },
        'تيليجرام': { title: "مهام تيليجرام", icon: "fab fa-telegram", color: "#38bdf8" },
        'X': { title: "مهام منصة X", icon: "fab fa-twitter", color: "#1da1f2" },
        'موقع': { title: "زيارة مواقع", icon: "fas fa-globe", color: "#28a745" },
        'انستغرام': { title: "مهام انستغرام", icon: "fab fa-instagram", color: "#e1306c" },
        'أخرى': { title: "مهام متنوعة", icon: "fas fa-tasks", color: "#a855f7" }
    };

    function getTgId() {
        return window.PlayerData?.tg_id || window.Telegram?.WebApp?.initDataUnsafe?.user?.id?.toString() || "5102387551";
    }

    // التبديل بين قسم (اكسب ZN) وقسم (روّج لقناتك)
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

    // تحديث واجهة المستخدم فورياً (الأرصدة)
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

    // جلب المهام والإعلانات الحقيقية فقط من السيرفر ورسمها للمستخدمين
    window.fetchAndRenderTasks = async function() {
        const container = document.getElementById('tasks-list-container');
        const activeAdsContainer = document.getElementById('active-ads-container');
        let completedTasks = JSON.parse(localStorage.getItem('zn_completed_tasks') || '[]');
        let myId = String(getTgId()).trim();
        
        let realTasks = [];
        try {
            let response = await fetch(`/api/get_campaigns?telegramId=${myId}`);
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
        // 🟢 قسم: اكسب ZN (عرض المهام للجميع بما فيهم صاحب الإعلان)
        // ==========================================
        if (container) {
            let allTasks = [];
            realTasks.forEach(task => {
                // تم إزالة فلتر الحجب، الآن تظهر كل المهام
                allTasks.push({
                    id: task.id,
                    title: task.description || `مهمة دعم وتفاعل عبر (${task.platform})`,
                    platform: task.platform || 'أخرى',
                    reward: task.reward,
                    link: task.url,
                    is_completed: task.is_completed,
                    creator_id: String(task.creator_id).trim()
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
                tasksArray.sort((a, b) => b.reward - a.reward); // الأغلى أولاً
                let config = platformConfig[plat] || platformConfig['أخرى'];

                html += `
                    <div style="margin-top: 25px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                        <i class="${config.icon}" style="color: ${config.color}; font-size: 16px;"></i>
                        <h5 style="color: #ccc; margin: 0; font-size: 14px; font-weight: 600;">${config.title}</h5>
                    </div>
                `;

                tasksArray.forEach(task => {
                    const isMyAd = (task.creator_id === myId); // التحقق هل هذا إعلاني الشخصي؟
                    const isCompleted = task.is_completed || completedTasks.includes(task.id);
                    let actionHtml = '';

                    if (isMyAd) {
                        // 1. لو الإعلان بتاعي يظهر كإعلان خاص غير قابل للضغط
                        actionHtml = `<button disabled style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); padding: 8px 14px; border-radius: 8px; font-size: 11px; font-weight: bold; cursor: not-allowed;">إعلانك الخاص 📢</button>`;
                    } else if (isCompleted) {
                        // 2. لو المهمة اتعملت قبل كده تظهر مكتملة ولا تتكرر
                        actionHtml = `<button disabled style="background: rgba(40, 167, 69, 0.15); color: #28a745; border: 1px solid rgba(40, 167, 69, 0.4); padding: 8px 14px; border-radius: 8px; font-size: 12px; font-weight: bold; cursor: not-allowed;">مكتمل ✔️</button>`;
                    } else {
                        // 3. لو المهمة متاحة وجديدة للمستخدم
                        let state = window.activeTasksState[task.id] || 'idle';
                        if (state === 'idle') {
                            actionHtml = `<button id="btn-task-${task.id}" onclick="startTask('${task.id}', '${task.link}', ${task.reward})" style="background: #fff; color: #000; border: none; padding: 8px 22px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: bold; transition: 0.2s;">ابدأ</button>`;
                        } else if (state === 'running') {
                            actionHtml = `<button id="btn-task-${task.id}" disabled style="background: #333; color: #888; border: 1px solid #444; padding: 8px 14px; border-radius: 8px; font-size: 12px; cursor: not-allowed; font-weight: bold;">انتظر ${window.taskTimers[task.id]}⏳</button>`;
                        } else if (state === 'ready') {
                            actionHtml = `<button id="btn-task-${task.id}" onclick="verifyTask('${task.id}', ${task.reward})" style="background: #ffcc00; color: #000; border: none; padding: 8px 18px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: bold; box-shadow: 0 0 10px rgba(255, 204, 0, 0.4);">تحقق ✅</button>`;
                        }
                    }

                    html += `
                        <div style="background: #141414; border: 1px solid #262626; border-radius: 14px; padding: 16px; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; gap: 10px;">
                            <div style="display: flex; align-items: center; gap: 14px; flex: 1;">
                                <div style="background: rgba(255,255,255,0.03); width: 42px; height: 42px; border-radius: 10px; display: flex; align-items: center; justify-content: center; border: 1px solid #2d2d2d;">
                                    <i class="${config.icon}" style="font-size: 20px; color: ${config.color};"></i>
                                </div>
                                <div style="text-align: right; flex: 1;">
                                    <div style="color: #ffffff; font-size: 13px; font-weight: 600; line-height: 1.4; margin-bottom: 4px;">${task.title}</div>
                                    <div style="color: #ffcc00; font-size: 12px; font-weight: bold; display: flex; align-items: center; gap: 4px;">
                                        <span>+${task.reward.toLocaleString()}</span> <span style="font-size: 10px; color: #888;">ZN</span>
                                    </div>
                                </div>
                            </div>
                            <div style="margin-right: auto;">
                                ${actionHtml}
                            </div>
                        </div>`;
                });
            }
            container.innerHTML = html || `<div style="text-align: center; color: #666; font-size: 13px; padding: 30px; background: #111; border-radius: 12px; border: 1px dashed #222;">لا توجد مهام حقيقية نشطة حالياً.</div>`;
        }

        // ==========================================
        // 🔵 قسم: روّج لقناتك (تفاصيل شيك وموسعة للحملات النشطة)
        // ==========================================
        if (activeAdsContainer) {
            let myCreatedCampaigns = realTasks.filter(task => String(task.creator_id).trim() === myId);

            if (myCreatedCampaigns.length === 0) {
                activeAdsContainer.innerHTML = `<div style="text-align: center; color: #666; font-size: 12px; padding: 25px; background: #111; border-radius: 12px;">ليس لديك حملات إعلانية نشطة حالياً.</div>`;
                return;
            }

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
                    <div style="background: #161622; border: 1px solid #2a2a3a; border-radius: 16px; padding: 18px; margin-bottom: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <i class="${config.icon}" style="color: ${config.color}; font-size: 16px;"></i>
                                <span style="color: #fff; font-size: 14px; font-weight: bold;">حملة دقيقة لـ ${ad.platform}</span>
                            </div>
                            <span style="background: rgba(56,189,248,0.1); color: #38bdf8; font-size: 11px; padding: 4px 10px; border-radius: 20px; font-weight: bold;">
                                التفاعل: ${comp} / ${need}
                            </span>
                        </div>
                        
                        <div style="background: #0d0d16; border-radius: 10px; padding: 10px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; border: 1px solid #1f1f2e;">
                            <div style="text-align: right;">
                                <span style="color: #777; font-size: 11px; display: block;">تكلفة الفرد:</span>
                                <span style="color: #fff; font-size: 12px; font-weight: bold;">${costPerClick.toLocaleString()} AdZN</span>
                            </div>
                            <div style="text-align: right;">
                                <span style="color: #777; font-size: 11px; display: block;">الميزانية الكلية:</span>
                                <span style="color: #ffcc00; font-size: 12px; font-weight: bold;">${totalBudget.toLocaleString()} AdZN</span>
                            </div>
                            <div style="text-align: right; border-top: 1px solid #1a1a26; padding-top: 5px;">
                                <span style="color: #777; font-size: 11px; display: block;">المستهلك:</span>
                                <span style="color: #ef4444; font-size: 12px; font-weight: bold;">${consumedBudget.toLocaleString()} AdZN</span>
                            </div>
                            <div style="text-align: right; border-top: 1px solid #1a1a26; padding-top: 5px;">
                                <span style="color: #777; font-size: 11px; display: block;">المتبقي المسترد:</span>
                                <span style="color: #28a745; font-size: 12px; font-weight: bold;">${remainingBudget.toLocaleString()} AdZN</span>
                            </div>
                        </div>

                        ${ad.description ? `
                        <div style="background: rgba(255,255,255,0.02); border-right: 3px solid #38bdf8; padding: 6px 10px; font-size: 11px; color: #bbb; margin-bottom: 12px; text-align: right; border-radius: 4px;">
                            <strong>التوجيهات المرفقة:</strong> ${ad.description}
                        </div>` : ''}

                        <div style="margin-bottom: 14px;">
                            <div style="display: flex; justify-content: space-between; font-size: 11px; color: #888; margin-bottom: 4px;">
                                <span>نسبة الإنجاز</span>
                                <span style="color: #38bdf8; font-weight: bold;">${pct}%</span>
                            </div>
                            <div style="width: 100%; height: 6px; background: #222; border-radius: 10px; overflow: hidden;">
                                <div style="width: ${pct}%; height: 100%; background: linear-gradient(90deg, #0088cc, #38bdf8); border-radius: 10px; transition: width 0.4s ease;"></div>
                            </div>
                        </div>

                        <div style="color: #555; font-size: 10px; margin-bottom: 12px; word-break: break-all; text-align: left; background: #0b0b11; padding: 6px; border-radius: 6px;" dir="ltr">${ad.url}</div>
                        <button onclick="cancelServerCampaign('${ad.id}')" style="width: 100%; background: rgba(239,68,68,0.06); border: 1px solid rgba(239,68,68,0.3); color: #ef4444; padding: 10px; border-radius: 10px; cursor: pointer; font-weight: bold; font-size: 12px; transition: 0.2s;">إلغاء واسترداد المتبقي (يخصم 10%)</button>
                    </div>`;
            });
            activeAdsContainer.innerHTML = adsHtml;
        }
    };

    // زر ابدأ المهمة (يشغل العداد التنازلي)
    window.startTask = function(taskId, link, reward) {
        if (window.Telegram?.WebApp) {
            window.Telegram.WebApp.openLink(link);
        } else {
            window.open(link, '_blank');
        }
        
        window.activeTasksState[taskId] = 'running';
        window.taskTimers[taskId] = 10; // 10 ثواني انتظار للتأكد من الزيارة
        window.fetchAndRenderTasks();
        
        let interval = setInterval(() => {
            if (window.taskTimers[taskId] > 1) {
                window.taskTimers[taskId]--;
                let btn = document.getElementById(`btn-task-${taskId}`);
                if (btn) btn.innerText = `انتظر ${window.taskTimers[taskId]}⏳`;
            } else {
                clearInterval(interval);
                window.activeTasksState[taskId] = 'ready';
                window.fetchAndRenderTasks();
            }
        }, 1000);
    };

    // دالة التحقق المرتبطة بالسيرفر والـ API للتأكيد الفعلي
    window.verifyTask = async function(taskId, reward) {
        const btn = document.getElementById(`btn-task-${taskId}`);
        if(btn) {
            btn.innerText = "جاري التأكيد...";
            btn.disabled = true;
        }

        try {
            let response = await fetch('/api/complete_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ telegramId: getTgId(), taskId: taskId })
            });
            let result = await response.json();
            
            if (response.ok && result.success) {
                let completedTasks = JSON.parse(localStorage.getItem('zn_completed_tasks') || '[]');
                completedTasks.push(taskId);
                localStorage.setItem('zn_completed_tasks', JSON.stringify(completedTasks));
                if (window.PlayerData) window.PlayerData.balance += reward;
                alert(`🎉 مبروك! تمت إضافة ${reward.toLocaleString()} ZN ورصيدك المحدث جاهز!`);
            } else {
                alert("⚠️ فشل التحقق: " + (result.error || "تأكد من إتمام المهمة أولاً"));
                window.activeTasksState[taskId] = 'ready';
            }
        } catch (e) {
            alert("حدث خطأ في الاتصال بالسيرفر أثناء المراجعة الفنية.");
            window.activeTasksState[taskId] = 'ready';
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

    // زر الإلغاء
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
                alert(`✅ تم إلغاء الحملة بنجاح واسترداد المتبقي لـ حسابك!`);
                if (typeof window.fetchPlayerDataFromServer === 'function') await window.fetchPlayerDataFromServer();
                window.fetchAndRenderTasks();
            } else {
                alert("⚠️ فشل الإلغاء: " + (result.error || "خطأ غير معروف"));
            }
        } catch (e) {
            alert("حدث خطأ في الاتصال بالسيرفر أثناء الإلغاء.");
        }
    };

    // تحويل ZN إلى رصيد إعلانات AdZN
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
        document.getElementById('ad-desc').value = ''; 
        document.getElementById('ad-reward').value = '';
        document.getElementById('ad-users').value = '';
        document.getElementById('ad-modal').style.display = 'flex';
    };

    window.closeAdModal = function() {
        document.getElementById('ad-modal').style.display = 'none';
    };

    window.submitAdCampaign = async function() {
        let link = document.getElementById('ad-link').value;
        let desc = document.getElementById('ad-desc').value; 
        let reward = parseFloat(document.getElementById('ad-reward').value);
        let users = parseInt(document.getElementById('ad-users').value);

        if (!link || !desc || isNaN(reward) || reward <= 0 || isNaN(users) || users <= 0) {
            alert("⚠️ يرجى إدخال جميع البيانات والوصف التوضيحي بشكل صحيح!");
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
                    description: desc, 
                    reward: reward,
                    users_needed: users
                })
            });
            let result = await response.json();
            
            if (response.ok && result.success) {
                closeAdModal();
                alert("✅ تم نشر حملتك الإعلانية بنجاح على السيرفر ومتاحة للجميع!");
                
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

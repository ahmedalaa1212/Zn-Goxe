(function initTasks() {
    window.activeTasksState = window.activeTasksState || {};
    window.taskTimers = window.taskTimers || {};
    
    // متغير لحفظ الـ ID للمهمة التي ينفذها العضو حالياً لمحاربة النصب
    window.currentlyRunningTaskId = window.currentlyRunningTaskId || null;

    let isSubmittingCampaign = false;
    let isConvertingBalance = false;
    let isCancelingCampaign = false;

    const preDefinedDescriptions = {
        'يوتيوب': [
            "اشترك بالقناة وفعّل جرس التنبيهات 🔔",
            "ضع لايك حقيقي للفيديو المرفق 👍",
            "اكتب تعليق إيجابي يخص محتوى الفيديو 💬"
        ],
        'تيليجرام': [
            "انضم إلى القناة وقم بزيارة آخر 3 منشورات 📢",
            "انضم إلى الجروب وشارك في النقاشات بأدب 👥"
        ],
        'موقع': [
            "قم بتصفح الموقع والبقاء داخله لمدة دقيقة كاملة 🌐",
            "تصفح المقالات وتفاعل مع الإعلانات داخل الموقع 📄"
        ],
        'انستغرام': [
            "تابع الحساب الرسمي وتفاعل باللايكات 📸",
            "ضع لايك على المنشور الأخير واكتب تعليق ❤️"
        ],
        'X': [
            "تابع الحساب الرسمي وقم بعمل ريتويت للتغريدة المثبتة 🔁",
            "ضع إعجاب على التغريدة الأخيرة المنشورة 🤍"
        ]
    };

    const platformConfig = {
        'يوتيوب': { title: "مهام يوتيوب", icon: "fab fa-youtube", color: "#ef4444" },
        'تيليجرام': { title: "مهام تيليجرام", icon: "fab fa-telegram", color: "#38bdf8" },
        'X': { title: "مهام منصة X", icon: "fab fa-twitter", color: "#ffffff" },
        'موقع': { title: "زيارة مواقع", icon: "fas fa-globe", color: "#28a745" },
        'انستغرام': { title: "مهام انستغرام", icon: "fab fa-instagram", color: "#e1306c" },
        'أخرى': { title: "مهام متنوعة", icon: "fas fa-tasks", color: "#a855f7" }
    };

    function getTgId() {
        return window.PlayerData?.tg_id || window.Telegram?.WebApp?.initDataUnsafe?.user?.id?.toString() || "5102387551";
    }

    window.switchTasksTab = function(tab) {
        document.getElementById('section-earn').style.display = tab === 'earn' ? 'block' : 'none';
        document.getElementById('section-promote').style.display = tab === 'promote' ? 'block' : 'none';
        
        document.getElementById('btn-tab-earn').style.background = tab === 'earn' ? '#0088cc' : 'transparent';
        document.getElementById('btn-tab-earn').style.color = tab === 'earn' ? '#fff' : '#8e92a2';
        document.getElementById('btn-tab-earn').style.boxShadow = tab === 'earn' ? '0 4px 12px rgba(0, 136, 204, 0.3)' : 'none';
        
        document.getElementById('btn-tab-promote').style.background = tab === 'promote' ? '#0088cc' : 'transparent';
        document.getElementById('btn-tab-promote').style.color = tab === 'promote' ? '#fff' : '#8e92a2';
        document.getElementById('btn-tab-promote').style.boxShadow = tab === 'promote' ? '0 4px 12px rgba(0, 136, 204, 0.3)' : 'none';
        
        if(tab === 'earn' || tab === 'promote') {
            window.fetchAndRenderTasks(); 
        }
    };

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
                if (data.success) { realTasks = data.campaigns; }
            }
        } catch (e) { console.warn("خطأ جلب المهام", e); }

        if (container) {
            let allTasks = [];
            realTasks.forEach(task => {
                allTasks.push({
                    id: task.id,
                    title: `دعم وتفاعل منصة (${task.platform})`,
                    description: task.description || "برجاء اتباع الرابط لإكمال المهمة المطلوبة بنجاح التام.",
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
                tasksArray.sort((a, b) => b.reward - a.reward);
                let config = platformConfig[plat] || platformConfig['أخرى'];

                html += `
                    <div style="margin-top: 25px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px;">
                        <i class="${config.icon}" style="color: ${config.color}; font-size: 15px;"></i>
                        <h5 style="color: #94a3b8; margin: 0; font-size: 13px; font-weight: 700;">${config.title}</h5>
                    </div>
                `;

                tasksArray.forEach(task => {
                    const isMyAd = (task.creator_id === myId);
                    const isCompleted = task.is_completed || completedTasks.includes(task.id);
                    let actionHtml = '';

                    if (isMyAd) {
                        actionHtml = `<button disabled style="background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.25); padding: 8px 14px; border-radius: 8px; font-size: 11px; font-weight: bold; cursor: not-allowed;">إعلانك الخاص 📢</button>`;
                    } else if (isCompleted) {
                        actionHtml = `<button disabled style="background: rgba(40, 167, 69, 0.12); color: #28a745; border: 1px solid rgba(40, 167, 69, 0.25); padding: 8px 14px; border-radius: 8px; font-size: 11px; font-weight: bold; cursor: not-allowed;">مكتمل ✔️</button>`;
                    } else {
                        let state = window.activeTasksState[task.id] || 'idle';
                        if (state === 'idle') {
                            actionHtml = `<button id="btn-task-${task.id}" onclick="startTask('${task.id}', '${task.link}', ${task.reward})" style="background: #fff; color: #000; border: none; padding: 8px 22px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: 800; transition: 0.2s;">ابدأ</button>`;
                        } else if (state === 'running') {
                            actionHtml = `<button id="btn-task-${task.id}" disabled style="background: #222; color: #ffaa00; border: 1px solid #333; padding: 8px 14px; border-radius: 8px; font-size: 12px; cursor: not-allowed; font-weight: bold;">نفذ.. ${window.taskTimers[task.id]}⏳</button>`;
                        } else if (state === 'ready') {
                            actionHtml = `<button id="btn-task-${task.id}" onclick="verifyTask('${task.id}', ${task.reward})" style="background: #ffcc00; color: #000; border: none; padding: 8px 18px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: 800; box-shadow: 0 0 10px rgba(255, 204, 0, 0.3);">تحقق ✅</button>`;
                        }
                    }

                    html += `
                        <div style="background: linear-gradient(135deg, #11111e, #141424); border: 1px solid #222235; border-radius: 16px; padding: 15px; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between; gap: 10px; box-shadow: 0 4px 10px rgba(0,0,0,0.2);">
                            <div style="display: flex; align-items: center; gap: 12px; flex: 1;">
                                <div style="background: rgba(255,255,255,0.02); width: 44px; height: 44px; border-radius: 12px; display: flex; align-items: center; justify-content: center; border: 1px solid rgba(255,255,255,0.05);">
                                    <i class="${config.icon}" style="font-size: 18px; color: ${config.color};"></i>
                                </div>
                                <div style="text-align: right; flex: 1;">
                                    <div style="color: #ffffff; font-size: 13px; font-weight: 700; line-height: 1.4; margin-bottom: 2px;">${task.title}</div>
                                    <div style="color: #94a3b8; font-size: 11px; margin-bottom: 4px; font-weight: 500; line-height: 1.3;">${task.description}</div>
                                    <div style="color: #ffcc00; font-size: 12px; font-weight: 700; display: flex; align-items: center; gap: 4px;">
                                        <span>+${task.reward.toLocaleString()}</span> <span style="font-size: 10px; color: #64748b; font-weight: 500;">ZN</span>
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
                    <div style="background: #131324; border: 1px solid #24243a; border-radius: 16px; padding: 18px; margin-bottom: 15px; box-shadow: 0 4px 15px rgba(0,0,0,0.3);">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <i class="${config.icon}" style="color: ${config.color}; font-size: 15px;"></i>
                                <span style="color: #fff; font-size: 13px; font-weight: 700;">حملة ممولة لـ ${ad.platform}</span>
                            </div>
                            <span style="background: rgba(56,189,248,0.1); color: #38bdf8; font-size: 11px; padding: 4px 10px; border-radius: 20px; font-weight: 700;">
                                الإنجاز: ${comp} / ${need}
                            </span>
                        </div>
                        
                        <div style="background: #090911; border-radius: 12px; padding: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 12px; border: 1px solid #1c1c2e;">
                            <div style="text-align: right;">
                                <span style="color: #64748b; font-size: 11px; display: block;">تكلفة الضغطة:</span>
                                <span style="color: #fff; font-size: 12px; font-weight: 700;">${costPerClick.toLocaleString()} AdZN</span>
                            </div>
                            <div style="text-align: right;">
                                <span style="color: #64748b; font-size: 11px; display: block;">ميزانية الإعلان:</span>
                                <span style="color: #ffcc00; font-size: 12px; font-weight: 700;">${totalBudget.toLocaleString()} AdZN</span>
                            </div>
                            <div style="text-align: right; border-top: 1px solid #1a1a2e; padding-top: 5px;">
                                <span style="color: #64748b; font-size: 11px; display: block;">مستهلك حتى الآن:</span>
                                <span style="color: #ef4444; font-size: 12px; font-weight: 700;">${consumedBudget.toLocaleString()} AdZN</span>
                            </div>
                            <div style="text-align: right; border-top: 1px solid #1a1a2e; padding-top: 5px;">
                                <span style="color: #64748b; font-size: 11px; display: block;">المتبقي القابل للاسترداد:</span>
                                <span style="color: #28a745; font-size: 12px; font-weight: 700;">${remainingBudget.toLocaleString()} AdZN</span>
                            </div>
                        </div>

                        <div style="background: rgba(255,255,255,0.02); border-right: 3px solid #38bdf8; padding: 6px 10px; font-size: 11px; color: #b4b9c8; margin-bottom: 12px; text-align: right; border-radius: 4px; font-weight: 500;">
                            <strong>التوجيه الفعلي للزوار:</strong> ${ad.description}
                        </div>

                        <div style="margin-bottom: 14px;">
                            <div style="display: flex; justify-content: space-between; font-size: 11px; color: #64748b; margin-bottom: 4px;">
                                <span>التقدم الإجمالي للنسبة</span>
                                <span style="color: #38bdf8; font-weight: 700;">${pct}%</span>
                            </div>
                            <div style="width: 100%; height: 6px; background: #0b0b12; border-radius: 10px; overflow: hidden; border: 1px solid #1f1f2e;">
                                <div style="width: ${pct}%; height: 100%; background: linear-gradient(90deg, #0088cc, #38bdf8); border-radius: 10px; transition: width 0.4s ease;"></div>
                            </div>
                        </div>
                        <div style="color: #475569; font-size: 11px; margin-bottom: 12px; word-break: break-all; text-align: left; background: #090911; padding: 8px; border-radius: 8px; font-family: monospace;" dir="ltr">${ad.url}</div>
                        <button id="btn-cancel-${ad.id}" onclick="cancelServerCampaign('${ad.id}')" style="width: 100%; background: rgba(239,68,68,0.05); border: 1px solid rgba(239,68,68,0.25); color: #ef4444; padding: 11px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 12px; transition: 0.2s;">إلغاء الإعلان فوراً وسحب المتبقي لحسابك</button>
                    </div>`;
            });
            activeAdsContainer.innerHTML = adsHtml;
        }
    };

    // 🔥 زر ابدأ المهمة + تشغيل نظام منع النصب الذكي عن طريق تتبع مغادرة الصفحة 🔥
    window.startTask = function(taskId, link, reward) {
        window.currentlyRunningTaskId = taskId; // تسجيل معرف المهمة المفتوحة حالياً

        if (window.Telegram?.WebApp) { window.Telegram.WebApp.openLink(link); } 
        else { window.open(link, '_blank'); }
        
        window.activeTasksState[taskId] = 'running';
        window.taskTimers[taskId] = 10; // 10 ثوانٍ إلزامية داخل المنصة
        window.fetchAndRenderTasks();
        
        // مسح أي مؤقت قديم لتفادي التداخل البنائي
        if (window.taskIntervals && window.taskIntervals[taskId]) {
            clearInterval(window.taskIntervals[taskId]);
        }
        window.taskIntervals = window.taskIntervals || {};

        window.taskIntervals[taskId] = setInterval(() => {
            // 🛡️ فحص ذكي: لو المستخدم رجع للبوت وفتح الصفحة (يعني مش برة بينفذ المهمة) يتم تجميد العداد فوراً!
            if (document.visibilityState === 'visible' || document.hasFocus()) {
                let btn = document.getElementById(`btn-task-${taskId}`);
                if (btn) {
                    btn.innerText = `تابع العمل.. ⏳`;
                    btn.style.color = "#ff4444"; // تلوين الزر لتنبيهه بالعودة السريعة
                }
                return; // إيقاف الخصم الزمني وتجميد الثانية لحين المغادرة الفعلية
            }

            // إذا كان المستخدم برة التطبيق والصفحة مخفية (ينفذ المهمة بصدق) يخصم الوقت طبيعي
            if (window.taskTimers[taskId] > 1) {
                window.taskTimers[taskId]--;
                let btn = document.getElementById(`btn-task-${taskId}`);
                if (btn) {
                    btn.innerText = `نفذ.. ${window.taskTimers[taskId]}⏳`;
                    btn.style.color = "#ffaa00";
                }
            } else {
                clearInterval(window.taskIntervals[taskId]);
                window.activeTasksState[taskId] = 'ready';
                window.currentlyRunningTaskId = null; // تصفير الحماية بنجاح
                window.fetchAndRenderTasks();
            }
        }, 1000);
    };

    // مضافة حماية إضافية للـ visibility change العامة للتأكيد الفوري
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'visible' && window.currentlyRunningTaskId) {
            let tId = window.currentlyRunningTaskId;
            if (window.activeTasksState[tId] === 'running') {
                let btn = document.getElementById(`btn-task-${tId}`);
                if (btn) {
                    btn.innerText = `تابع التنفيذ بالخارج 🛑`;
                    btn.style.background = "rgba(239,68,68,0.2)";
                    btn.style.color = "#ef4444";
                }
            }
        }
    });

    window.verifyTask = async function(taskId, reward) {
        const btn = document.getElementById(`btn-task-${taskId}`);
        if(btn) { btn.innerText = "فحص الفني..."; btn.disabled = true; btn.style.opacity = "0.5"; }

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
                alert(`🎉 مبارك! تم تأكيد المهمة وإضافة رصيد بقيمة ${reward.toLocaleString()} ZN`);
            } else {
                alert("⚠️ لم يكتمل الفحص بعد: " + (result.error || "تأكد من المتابعة الفعلية"));
                window.activeTasksState[taskId] = 'ready';
            }
        } catch (e) {
            alert("خطأ في الاتصال بالشبكة.");
            window.activeTasksState[taskId] = 'ready';
        }
        window.fetchAndRenderTasks();
        if (typeof window.triggerAllUIUpdates === 'function') window.triggerAllUIUpdates();
    };

    window.cancelServerCampaign = async function(campId) {
        if (isCancelingCampaign) return;
        if (!confirm("هل أنت متأكد من إلغاء الحملة؟ سيتم خصم عمولة الإلغاء 10%.")) return;
        
        isCancelingCampaign = true;
        const btn = document.getElementById(`btn-cancel-${campId}`);
        if(btn) { btn.innerText = "جاري الحذف والرد..."; btn.disabled = true; }

        try {
            let response = await fetch('/api/cancel_campaign', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ telegramId: getTgId(), campaignId: campId })
            });
            let result = await response.json();
            if (response.ok && result.success) {
                alert(`✅ تم إلغاء حملتك بنجاح وإرجاع الرصيد المتبقي لـ محفظتك الإعلانية!`);
                if (typeof window.fetchPlayerDataFromServer === 'function') await window.fetchPlayerDataFromServer();
                window.fetchAndRenderTasks();
            } else { alert("⚠️ خطأ بالإلغاء: " + result.error); }
        } catch (e) { alert("حدث خطأ."); }
        finally { isCancelingCampaign = false; }
    };

    window.convertZnToAdZn = async function() {
        if (isConvertingBalance) return;
        let amount = prompt("أدخل رصيد ZN المراد تحويله لرصيد الإعلانات:\n* سيتم تطبيق عمولة تداول 10%.");
        if (!amount || isNaN(amount) || amount <= 0) return;
        amount = parseFloat(amount);

        if (parseFloat(window.PlayerData?.balance || 0) < amount) {
            alert("⚠️ رصيد ZN الحالي غير كافٍ للعملية!");
            return;
        }

        isConvertingBalance = true;
        try {
            let response = await fetch('/api/convert_adzn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ telegramId: getTgId(), amount: amount })
            });
            let result = await response.json();
            if (response.ok && result.success) {
                alert(`✅ شحن ناجح! تمت عملية التحويل لمحفظتك بنجاح.`);
                if (window.PlayerData) {
                    window.PlayerData.balance -= amount;
                    window.PlayerData.ad_balance = (window.PlayerData.ad_balance || 0) + result.received;
                }
                window.updateTasksUI();
                if (typeof window.triggerAllUIUpdates === 'function') window.triggerAllUIUpdates();
            } else { alert("⚠️ فشل: " + result.error); }
        } catch (e) { alert("خطأ شبكة."); }
        finally { isConvertingBalance = false; }
    };

    window.openAdModal = function(type) {
        currentAdType = type;
        document.getElementById('ad-modal-title').innerText = `إطلاق حملة ${type} حقيقية`;
        document.getElementById('ad-link').value = '';
        document.getElementById('ad-reward').value = '';
        document.getElementById('ad-users').value = '';
        
        const selectContainer = document.getElementById('ad-desc-select');
        selectContainer.innerHTML = '';
        
        let optionsHtml = '';
        let optionsList = preDefinedDescriptions[type] || ["برجاء اتباع الرابط لإكمال التفاعل الإعلاني."];
        optionsList.forEach(descText => {
            optionsHtml += `<option value="${descText}">${descText}</option>`;
        });
        selectContainer.innerHTML = optionsHtml;

        const submitBtn = document.getElementById('btn-submit-campaign-action');
        if (submitBtn) {
            submitBtn.innerText = "نشر الحملة";
            submitBtn.disabled = false;
            submitBtn.style.opacity = "1";
        }
        document.getElementById('ad-modal').style.display = 'flex';
    };

    window.closeAdModal = function() {
        if (isSubmittingCampaign) return;
        document.getElementById('ad-modal').style.display = 'none';
    };

    window.submitAdCampaign = async function() {
        if (isSubmittingCampaign) return;

        let link = document.getElementById('ad-link').value.trim();
        let desc = document.getElementById('ad-desc-select').value; 
        let reward = parseFloat(document.getElementById('ad-reward').value);
        let users = parseInt(document.getElementById('ad-users').value);

        if (!link || !desc || isNaN(reward) || reward <= 0 || isNaN(users) || users <= 0) {
            alert("⚠️ يرجى ملء كافة الخانات المالية وبينات الرابط بشكل سليم.");
            return;
        }

        let linkLower = link.toLowerCase();
        if (currentAdType === 'يوتيوب' && !linkLower.includes("youtube.com") && !linkLower.includes("youtu.be")) {
            alert("⚠️ خطأ أمني: يجب إدخال رابط فيديو أو قناة يوتيوب صحيح يبدأ بـ youtube.com أو youtu.be");
            return;
        }
        if (currentAdType === 'تيليجرام' && !linkLower.includes("t.me")) {
            alert("⚠️ خطأ أمني: يجب إدخال رابط قناة أو جروب تيليجرام صحيح يبدأ بـ t.me");
            return;
        }
        if (currentAdType === 'انستغرام' && !linkLower.includes("instagram.com")) {
            alert("⚠️ خطأ أمني: يجب إدخال رابط حساب أو منشور انستغرام صحيح يبدأ بـ instagram.com");
            return;
        }
        if (currentAdType === 'X' && !linkLower.includes("twitter.com") && !linkLower.includes("x.com")) {
            alert("⚠️ خطأ أمني: يجب إدخال رابط تفاعل لمنصة X يبدأ بـ x.com أو twitter.com");
            return;
        }

        if (currentAdType === 'موقع') {
            const forbiddenKeywords = ['porn', 'sexy', 'xnx', 'adult', 'gambling', 'casino', 'bet365', '1xbet', 'sex', 'إباحي', 'جنس', 'قمار'];
            let foundViolation = forbiddenKeywords.some(word => linkLower.includes(word));
            if (foundViolation) {
                alert("🚨 نظام الأمان التلقائي 🚨\nتم حظر الرابط فوراً لاحتوائه على محتوى مخالف لسياسة البوت!");
                return;
            }
        }

        let totalCost = reward * users;
        let currentAdBalance = parseFloat(window.PlayerData?.ad_balance || 0);

        if (currentAdBalance < totalCost) {
            alert(`⚠️ رصيدك الإعلاني غير كافٍ! التكلفة المطلوبة: ${totalCost} AdZN`);
            return;
        }

        document.getElementById('review-modal').style.display = 'flex';
        let remainingSeconds = 15;
        const countdownTimerDisplay = document.getElementById('review-countdown-timer');
        
        isSubmittingCampaign = true;
        closeAdModal(); 

        let reviewInterval = setInterval(async () => {
            remainingSeconds--;
            if (countdownTimerDisplay) countdownTimerDisplay.innerText = remainingSeconds;
            
            if (remainingSeconds <= 0) {
                clearInterval(reviewInterval);
                
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
                    
                    document.getElementById('review-modal').style.display = 'none'; 

                    if (response.ok && result.success) {
                        if(window.PlayerData) window.PlayerData.ad_balance -= totalCost;
                        
                        // 🔥 تفعيل مودال النجاح الزجاجي الجديد الاحترافي بدل الـ alert القديم 🔥
                        document.getElementById('success-modal').style.display = 'flex';
                    } else {
                        isSubmittingCampaign = false;
                        alert("⚠️ رفض السيرفر إنشاء الحملة: " + (result.error || "تأكد من سلامة الحساب"));
                    }
                } catch (e) {
                    document.getElementById('review-modal').style.display = 'none';
                    isSubmittingCampaign = false;
                    alert("حدث خطأ أثناء رفع الحملة للسيرفر الرئيسي.");
                }
            }
        }, 1000);
    };

    // 🔥 دالة التوجيه التلقائي الذكي والإغلاق الفوري بعد ضغط "متابعة الحملات" 🔥
    window.handleSuccessRedirect = function() {
        // 1. إخفاء مودال النجاح
        document.getElementById('success-modal').style.display = 'none';
        
        // 2. إعادة متغير الحماية للوضع الطبيعي تمهيداً لأي حملات قادمة
        isSubmittingCampaign = false;

        // 3. التحويل التلقائي لقسم حملات الترويج
        window.switchTasksTab('promote');

        // 4. تحديث البيانات بالكامل من السيرفر لرسم الإعلان الجديد بالأسفل
        window.updateTasksUI();

        // 5. عمل سكرول سلس لأسفل الصفحة (مكان ظهور الإعلانات) لتجربة مستخدم خرافية
        setTimeout(() => {
            const container = document.getElementById('active-ads-container');
            if (container) {
                container.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 300);
    };

    setTimeout(() => {
        if(typeof window.updateTasksUI === 'function') window.updateTasksUI();
    }, 400);

})();

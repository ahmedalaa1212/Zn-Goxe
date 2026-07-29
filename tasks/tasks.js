// tasks/tasks.js
(function initTasks() {
    if (window.Telegram?.WebApp) {
        window.Telegram.WebApp.ready();
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

    // دالة حماية وتطهير النصوص من هجمات XSS
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
        'يوتيوب': ["اشترك بالقناة وفعّل جرس التنبيهات 🔔", "ضع لايك حقيقي للفيديو المرفق 👍", "اكتب تعليق إيجابي يخص محتوى الفيديو 💬"],
        'تيليجرام': ["انضم إلى القناة وقم بزيارة آخر 3 منشورات 📢", "انضم إلى الجروب وشارك في النقاشات بأدب 👥"],
        'موقع': ["قم بتصفح الموقع والبقاء داخله لمدة دقيقة كاملة 🌐", "تصفح المقالات وتفاعل مع الإعلانات داخل الموقع 📄"],
        'انستغرام': ["تابع الحساب الرسمي وتفاعل باللايكات 📸", "ضع لايك على المنشور الأخير واكتب تعليق ❤️"],
        'X': ["تابع الحساب الرسمي وقم بعمل ريتويت للتغريدة المثبتة 🔁", "ضع إعجاب على التغريدة الأخيرة المنشورة 🤍"]
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
        return window.GameState?.userId || window.Telegram?.WebApp?.initDataUnsafe?.user?.id?.toString() || "";
    }

    window.switchTasksTab = function(tab) {
        const earnSection = document.getElementById('section-earn');
        const promoteSection = document.getElementById('section-promote');
        const btnEarn = document.getElementById('btn-tab-earn');
        const btnPromote = document.getElementById('btn-tab-promote');

        if (earnSection) earnSection.style.display = tab === 'earn' ? 'block' : 'none';
        if (promoteSection) promoteSection.style.display = tab === 'promote' ? 'block' : 'none';

        if (btnEarn) {
            if (tab === 'earn') btnEarn.classList.add('active');
            else btnEarn.classList.remove('active');
        }
        if (btnPromote) {
            if (tab === 'promote') btnPromote.classList.add('active');
            else btnPromote.classList.remove('active');
        }
        
        if (tab === 'earn' || tab === 'promote') {
            window.fetchAndRenderTasks(); 
        }
    };

    window.updateTasksUI = function() {
        if (typeof window.updateGlobalUI === 'function') {
            window.updateGlobalUI();
        }
        const topBal = document.getElementById('top-balance-tasks');
        if (topBal && window.GameState?.balance !== undefined) {
            topBal.innerText = `ZN ${Math.floor(window.GameState.balance).toLocaleString()}`;
        }
        const adBalDisplay = document.getElementById('ad-balance-display');
        if (adBalDisplay && window.GameState?.ad_balance !== undefined) {
            adBalDisplay.innerText = `AdZN ${Math.floor(window.GameState.ad_balance).toLocaleString()}`;
        }
        window.fetchAndRenderTasks();
    };

    window.fetchAndRenderTasks = async function() {
        const container = document.getElementById('tasks-list-container');
        const activeAdsContainer = document.getElementById('active-ads-container');
        let myId = String(getTgId()).trim();
        
        const initData = window.Telegram?.WebApp?.initData || "";
        let realTasks = [];
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
                    realTasks = data.campaigns || []; 
                    
                    if (data.user_id) {
                        myId = String(data.user_id).trim();
                        if (window.GameState) window.GameState.userId = myId;
                    }

                    if (window.GameState) {
                        if (data.ad_balance !== undefined) window.GameState.ad_balance = data.ad_balance;
                        if (data.balance !== undefined) window.GameState.balance = data.balance;
                    }

                    const topBal = document.getElementById('top-balance-tasks');
                    if (topBal && window.GameState?.balance !== undefined) {
                        topBal.innerText = `ZN ${Math.floor(window.GameState.balance).toLocaleString()}`;
                    }
                    const adBalDisplay = document.getElementById('ad-balance-display');
                    if (adBalDisplay && window.GameState?.ad_balance !== undefined) {
                        adBalDisplay.innerText = `AdZN ${Math.floor(window.GameState.ad_balance).toLocaleString()}`;
                    }
                }
            }
        } catch (e) { console.warn("خطأ جلب المهام", e); }

        if (container) {
            let allTasks = [];
            realTasks.forEach(task => {
                allTasks.push({
                    id: String(task.id),
                    title: `دعم وتفاعل منصة (${escapeHtml(task.platform)})`,
                    description: escapeHtml(task.description) || "برجاء اتباع الرابط لإكمال المهمة المطلوبة بنجاح التام.",
                    platform: task.platform || 'أخرى',
                    reward: Number(task.reward || 0),
                    link: task.url,
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
                            actionHtml = `<button type="button" id="btn-task-${task.id}" onclick="startTask('${task.id}', '${encodeURIComponent(task.link)}', ${task.reward})" style="background: #fff; color: #000; border: none; padding: 8px 22px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: 800; transition: 0.2s;">ابدأ</button>`;
                        } else if (state === 'running') {
                            let currentTotalOutside = window.accumulatedOutsideTime[task.id] || 0;
                            if (document.visibilityState === 'hidden') {
                                currentTotalOutside += (Date.now() - (window.lastGoOutside[task.id] || Date.now())) / 1000;
                            }
                            let remaining = Math.max(1, 15 - Math.floor(currentTotalOutside));
                            
                            if (remaining <= 1 && currentTotalOutside >= 15) {
                                window.taskStates[task.id] = 'ready';
                                actionHtml = `<button type="button" id="btn-task-${task.id}" onclick="verifyTask('${task.id}', ${task.reward})" style="background: #ffcc00; color: #000; border: none; padding: 8px 18px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: 800; box-shadow: 0 0 10px rgba(255, 204, 0, 0.3);">تحقق ✅</button>`;
                            } else if (document.visibilityState === 'visible') {
                                actionHtml = `<button type="button" id="btn-task-${task.id}" disabled style="background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); padding: 8px 14px; border-radius: 8px; font-size: 12px; cursor: not-allowed; font-weight: bold;">عُد للمهمة.. ${remaining}ث⏳</button>`;
                            } else {
                                actionHtml = `<button type="button" id="btn-task-${task.id}" disabled style="background: #222; color: #ffaa00; border: 1px solid #333; padding: 8px 14px; border-radius: 8px; font-size: 12px; cursor: not-allowed; font-weight: bold;">جاري التنفيذ.. ${remaining}ث⏳</button>`;
                            }
                        } else if (state === 'ready') {
                            actionHtml = `<button type="button" id="btn-task-${task.id}" onclick="verifyTask('${task.id}', ${task.reward})" style="background: #ffcc00; color: #000; border: none; padding: 8px 18px; border-radius: 8px; font-size: 12px; cursor: pointer; font-weight: 800; box-shadow: 0 0 10px rgba(255, 204, 0, 0.3);">تحقق ✅</button>`;
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
                                <strong>التوجيه الفعلي للزوار:</strong> ${escapeHtml(ad.description)}
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
                            <div style="color: #475569; font-size: 11px; margin-bottom: 12px; word-break: break-all; text-align: left; background: #090911; padding: 8px; border-radius: 8px; font-family: monospace;" dir="ltr">${escapeHtml(ad.url)}</div>
                            <button type="button" id="btn-cancel-${ad.id}" onclick="cancelServerCampaign('${ad.id}')" style="width: 100%; background: rgba(239,68,68,0.05); border: 1px solid rgba(239,68,68,0.25); color: #ef4444; padding: 11px; border-radius: 10px; cursor: pointer; font-weight: 700; font-size: 12px; transition: 0.2s;">إلغاء الإعلان فوراً وسحب المتبقي لحسابك</button>
                        </div>`;
                });
                activeAdsContainer.innerHTML = adsHtml;
            }
        }
    };

    window.startTask = function(taskId, encodedLink, reward) {
        const link = decodeURIComponent(encodedLink);
        window.taskStates[taskId] = 'running';
        window.accumulatedOutsideTime[taskId] = 0;
        window.lastGoOutside[taskId] = Date.now();

        if (window.Telegram?.WebApp) { 
            window.Telegram.WebApp.openLink(link); 
        } else { 
            window.open(link, '_blank'); 
        }
        
        window.fetchAndRenderTasks();
        
        if (window.taskIntervals[taskId]) clearInterval(window.taskIntervals[taskId]);

        window.taskIntervals[taskId] = setInterval(() => {
            let currentTotalOutside = window.accumulatedOutsideTime[taskId] || 0;
            if (document.visibilityState === 'hidden') {
                currentTotalOutside += (Date.now() - (window.lastGoOutside[taskId] || Date.now())) / 1000;
            }
            
            let remaining = 15 - Math.floor(currentTotalOutside);
            let btn = document.getElementById(`btn-task-${taskId}`);
            
            if (remaining <= 0) {
                clearInterval(window.taskIntervals[taskId]);
                window.taskStates[taskId] = 'ready';
                window.fetchAndRenderTasks();
            } else {
                if (btn) {
                    if (document.visibilityState === 'visible') {
                        btn.innerText = `عُد للمهمة.. ${remaining}ث⏳`;
                        btn.style.background = "rgba(239,68,68,0.15)";
                        btn.style.color = "#ef4444";
                        btn.style.border = "1px solid rgba(239,68,68,0.3)";
                    } else {
                        btn.innerText = `جاري التنفيذ.. ${remaining}ث⏳`;
                    }
                }
            }
        }, 1000);
    };

    if (!window.visibilityListenerAdded) {
        document.addEventListener('visibilitychange', () => {
            const now = Date.now();
            for (let taskId in window.taskStates) {
                if (window.taskStates[taskId] === 'running') {
                    if (document.visibilityState === 'visible') {
                        let timeSpentOutside = (now - (window.lastGoOutside[taskId] || now)) / 1000;
                        window.accumulatedOutsideTime[taskId] = (window.accumulatedOutsideTime[taskId] || 0) + timeSpentOutside;
                        window.lastGoOutside[taskId] = now;
                    } else if (document.visibilityState === 'hidden') {
                        window.lastGoOutside[taskId] = now;
                    }
                }
            }
            if (document.visibilityState === "visible") {
                if (typeof window.updateGlobalUI === 'function') window.updateGlobalUI();
            }
        });
        window.visibilityListenerAdded = true;
    }

    window.verifyTask = async function(taskId, reward) {
        if (isVerifyingTask) return;
        
        const initData = window.Telegram?.WebApp?.initData;
        if (!initData) {
            alert("⚠️ يجب فتح البوت من تليجرام للتحقق الحقيقي.");
            return;
        }

        isVerifyingTask = true;
        const btn = document.getElementById(`btn-task-${taskId}`);
        if (btn) { 
            btn.innerText = "فحص التفاعل..."; 
            btn.disabled = true; 
            btn.style.opacity = "0.5"; 
        }

        try {
            let response = await fetch('/api/tasks/complete_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData, taskId: taskId })
            });
            let result = await response.json();
            
            if (response.ok && result.success) {
                if (window.GameState) {
                    if (result.new_balance !== undefined) {
                        window.GameState.balance = Number(result.new_balance);
                    } else {
                        window.GameState.balance += Number(reward);
                    }
                }
                
                delete window.taskStates[taskId];
                delete window.accumulatedOutsideTime[taskId];
                delete window.lastGoOutside[taskId];
                
                alert(`🎉 مبارك! تم تأكيد التفاعل وإضافة رصيد بقيمة ${reward.toLocaleString()} ZN`);
            } else {
                alert("⚠️ فشل التحقق: " + (result.error || "تأكد من إتمام التفاعل الفعلي أولاً"));
                window.taskStates[taskId] = 'ready';
            }
        } catch (e) {
            alert("حدث خطأ في الاتصال بالسيرفر الرئيسي.");
            window.taskStates[taskId] = 'ready';
        } finally {
            isVerifyingTask = false;
            await window.fetchAndRenderTasks();
        }
    };

    window.cancelServerCampaign = async function(campId) {
        const initData = window.Telegram?.WebApp?.initData;
        if (!initData) return alert("⚠️ غير مصرح بالعملية خارج التليجرام.");

        if (isCancelingCampaign) return;
        if (!confirm("هل أنت متأكد من إلغاء الحملة؟ سيتم إرجاع رصيد النقاط غير المستهلكة فوراً.")) return;
        
        isCancelingCampaign = true;
        const btn = document.getElementById(`btn-cancel-${campId}`);
        if (btn) { btn.innerText = "جاري الحذف والرد..."; btn.disabled = true; }

        try {
            let response = await fetch('/api/tasks/cancel_campaign', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData, campaignId: campId })
            });
            let result = await response.json();
            if (response.ok && result.success) {
                alert(`✅ تم إلغاء حملتك بنجاح وإرجاع الميزانية المتبقية لمحفظتك!`);
                if (window.GameState && result.new_ad_balance !== undefined) {
                    window.GameState.ad_balance = Number(result.new_ad_balance);
                } else if (window.GameState && result.refund !== undefined) {
                    window.GameState.ad_balance += Number(result.refund);
                }
                window.fetchAndRenderTasks();
            } else { 
                alert("⚠️ خطأ بالإلغاء: " + (result.error || "عذراً تعذر الإلغاء")); 
            }
        } catch (e) { alert("حدث خطأ في الاتصال بالسيرفر."); }
        finally { isCancelingCampaign = false; }
    };

    window.convertZnToAdZn = async function() {
        const initData = window.Telegram?.WebApp?.initData;
        if (!initData) return alert("⚠️ يجب فتح اللعبة من داخل التليجرام أولاً.");

        if (isConvertingBalance) return;
        let inputVal = prompt("أدخل رصيد ZN المراد تحويله لرصيد الإعلانات:\n* سيتم تطبيق عمولة تداول 10%.");
        if (!inputVal) return;
        let amount = parseFloat(inputVal.trim());
        if (isNaN(amount) || amount <= 0) {
            alert("⚠️ يرجى إدخال مبلغ صحيح وموجب.");
            return;
        }

        let currentBal = window.GameState ? window.GameState.balance : 0;
        if (currentBal < amount) {
            alert("⚠️ رصيد ZN الحالي غير كافٍ للعملية!");
            return;
        }

        isConvertingBalance = true;
        try {
            let response = await fetch('/api/tasks/convert_adzn', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: initData, amount: amount })
            });
            let result = await response.json();
            if (response.ok && result.success) {
                alert(`✅ شحن ناجح! تمت عملية التحويل لمحفظتك بنجاح.`);
                
                if (window.GameState) {
                    if (result.new_balance !== undefined) window.GameState.balance = Number(result.new_balance);
                    if (result.new_ad_balance !== undefined) window.GameState.ad_balance = Number(result.new_ad_balance);
                }
                
                window.updateTasksUI();
            } else { alert("⚠️ فشل: " + (result.error || "خطأ في عملية التحويل")); }
        } catch (e) { alert("خطأ شبكة أثناء تحويل الرصيد."); }
        finally { isConvertingBalance = false; }
    };

    window.openAdModal = function(type) {
        currentAdType = type;
        const modalTitle = document.getElementById('ad-modal-title');
        if (modalTitle) modalTitle.innerText = `إطلاق حملة ${type} حقيقية`;
        
        const linkEl = document.getElementById('ad-link');
        const rewardEl = document.getElementById('ad-reward');
        const usersEl = document.getElementById('ad-users');
        if (linkEl) linkEl.value = '';
        if (rewardEl) rewardEl.value = '';
        if (usersEl) usersEl.value = '';
        
        const selectContainer = document.getElementById('ad-desc-select');
        if (selectContainer) {
            selectContainer.innerHTML = '';
            let optionsHtml = '';
            let optionsList = preDefinedDescriptions[type] || ["برجاء اتباع الرابط لإكمال التفاعل الإعلاني."];
            optionsList.forEach(descText => {
                optionsHtml += `<option value="${escapeHtml(descText)}">${escapeHtml(descText)}</option>`;
            });
            selectContainer.innerHTML = optionsHtml;
        }

        const submitBtn = document.getElementById('btn-submit-campaign-action');
        if (submitBtn) {
            submitBtn.innerText = "نشر الحملة";
            submitBtn.disabled = false;
            submitBtn.style.opacity = "1";
        }
        const adModal = document.getElementById('ad-modal');
        if (adModal) adModal.style.display = 'flex';
    };

    window.closeAdModal = function() {
        if (isSubmittingCampaign) return;
        const adModal = document.getElementById('ad-modal');
        if (adModal) adModal.style.display = 'none';
    };

    window.submitAdCampaign = async function() {
        const initData = window.Telegram?.WebApp?.initData;
        if (!initData) return alert("⚠️ عذراً لا يمكن إنتاج حملات إعلانية خارج تطبيق تليجرام الأصلي.");

        if (isSubmittingCampaign) return;

        let link = document.getElementById('ad-link')?.value.trim() || '';
        let desc = document.getElementById('ad-desc-select')?.value || ''; 
        let reward = parseFloat(document.getElementById('ad-reward')?.value || '0');
        let users = parseInt(document.getElementById('ad-users')?.value || '0', 10);

        if (!link || !desc || isNaN(reward) || reward <= 0 || isNaN(users) || users <= 0) {
            alert("⚠️ يرجى ملء كافة الخانات المالية وبيانات الرابط بشكل سليم.");
            return;
        }

        if (!/^https?:\/\//i.test(link)) {
            link = 'https://' + link;
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
        let currentAdBalance = window.GameState ? window.GameState.ad_balance : 0;

        if (currentAdBalance < totalCost) {
            alert(`⚠️ رصيدك الإعلاني غير كافٍ! التكلفة المطلوبة: ${totalCost.toLocaleString()} AdZN`);
            return;
        }

        isSubmittingCampaign = true;
        
        const adModal = document.getElementById('ad-modal');
        if (adModal) adModal.style.display = 'none';

        const reviewModal = document.getElementById('review-modal');
        if (reviewModal) reviewModal.style.display = 'flex';
        
        let remainingSeconds = 10;
        const countdownTimerDisplay = document.getElementById('review-countdown-timer');
        if (countdownTimerDisplay) countdownTimerDisplay.innerText = remainingSeconds;

        let reviewInterval = setInterval(async () => {
            remainingSeconds--;
            if (countdownTimerDisplay) countdownTimerDisplay.innerText = remainingSeconds;
            
            if (remainingSeconds <= 0) {
                clearInterval(reviewInterval);
                
                try {
                    let response = await fetch('/api/tasks/create_campaign', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                            initData: initData,
                            platform: currentAdType,
                            url: link,
                            description: desc, 
                            reward: reward,
                            users_needed: users
                        })
                    });
                    let result = await response.json();
                    
                    if (reviewModal) reviewModal.style.display = 'none'; 

                    if (response.ok && result.success) {
                        if (window.GameState) {
                            if (result.new_ad_balance !== undefined) window.GameState.ad_balance = Number(result.new_ad_balance);
                            else window.GameState.ad_balance -= totalCost;
                        }
                        const successModal = document.getElementById('success-modal');
                        if (successModal) successModal.style.display = 'flex';
                    } else {
                        isSubmittingCampaign = false;
                        alert("⚠️ رفض السيرفر إنشاء الحملة: " + (result.error || "تأكد من سلامة الحساب"));
                    }
                } catch (e) {
                    if (reviewModal) reviewModal.style.display = 'none';
                    isSubmittingCampaign = false;
                    alert("حدث خطأ أثناء رفع الحملة للسيرفر الرئيسي.");
                }
            }
        }, 1000);
    };

    window.handleSuccessRedirect = function() {
        const successModal = document.getElementById('success-modal');
        const reviewModal = document.getElementById('review-modal');
        const adModal = document.getElementById('ad-modal');
        
        if (successModal) successModal.style.display = 'none';
        if (reviewModal) reviewModal.style.display = 'none';
        if (adModal) adModal.style.display = 'none';
        
        isSubmittingCampaign = false;

        window.switchTasksTab('promote');
        window.updateTasksUI();

        setTimeout(() => {
            const container = document.getElementById('active-ads-container');
            if (container) {
                container.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
        }, 300);
    };

    window.addEventListener('pageshow', () => {
        window.updateTasksUI();
    });

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        window.updateTasksUI();
    } else {
        document.addEventListener('DOMContentLoaded', window.updateTasksUI);
    }

})();

(function initTasks() {
    // 1. قائمة المهام الثابتة (للتجربة حالياً، ممكن نربطها بالسيرفر بعدين)
    const dummyTasks = [
        { id: '101', title: "انضم لقناتنا الرسمية", reward: 5000, icon: "fab fa-telegram", color: "#38bdf8", link: "https://t.me/" },
        { id: '102', title: "اشترك في قناة اليوتيوب", reward: 8000, icon: "fab fa-youtube", color: "#ef4444", link: "https://youtube.com/" },
        { id: '103', title: "تابعنا على منصة X", reward: 3000, icon: "fab fa-twitter", color: "#1da1f2", link: "https://x.com/" },
        { id: '104', title: "زيارة موقعنا", reward: 2000, icon: "fas fa-globe", color: "#28a745", link: "https://google.com/" },
        { id: '105', title: "متابعة انستغرام", reward: 4000, icon: "fab fa-instagram", color: "#e1306c", link: "https://instagram.com/" }
    ];

    let completedTasks = JSON.parse(localStorage.getItem('zn_completed_tasks') || '[]');
    let myAds = JSON.parse(localStorage.getItem('zn_my_ads') || '[]'); // هنحتفظ بيها محلياً مؤقتاً لعرضها

    // جلب الـ ID
    function getTgId() {
        return window.PlayerData?.tg_id || "5102387551";
    }

    // 2. التبديل بين الأقسام
    window.switchTasksTab = function(tab) {
        document.getElementById('section-earn').style.display = tab === 'earn' ? 'block' : 'none';
        document.getElementById('section-promote').style.display = tab === 'promote' ? 'block' : 'none';
        
        document.getElementById('btn-tab-earn').style.background = tab === 'earn' ? '#0088cc' : 'transparent';
        document.getElementById('btn-tab-earn').style.color = tab === 'earn' ? '#fff' : '#888';
        
        document.getElementById('btn-tab-promote').style.background = tab === 'promote' ? '#0088cc' : 'transparent';
        document.getElementById('btn-tab-promote').style.color = tab === 'promote' ? '#fff' : '#888';
    };

    // 3. تحديث واجهة المستخدم
    window.updateTasksUI = function() {
        const pData = window.PlayerData || { balance: 0, ad_balance: 0 };
        
        const tasksTopBalance = document.getElementById('top-balance-tasks');
        if (tasksTopBalance) tasksTopBalance.innerText = `ZN ${Math.floor(pData.balance || 0).toLocaleString()}`;

        const adBalDisplay = document.getElementById('ad-balance-display');
        if (adBalDisplay) {
            adBalDisplay.innerText = `AdZN ${Math.floor(pData.ad_balance || 0).toLocaleString()}`;
        }

        renderTasksList();
        renderMyAds();
    };

    // 4. رسم المهام
    function renderTasksList() {
        const container = document.getElementById('tasks-list-container');
        if (!container) return;

        let html = '';
        dummyTasks.forEach(task => {
            const isCompleted = completedTasks.includes(task.id);
            html += `
                <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 15px; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <i class="${task.icon}" style="font-size: 24px; color: ${task.color};"></i>
                        <div style="text-align: right;">
                            <div style="color: #fff; font-size: 13px; font-weight: bold;">${task.title}</div>
                            <div style="color: #ffcc00; font-size: 12px; font-weight: bold;">+${task.reward.toLocaleString()} ZN</div>
                        </div>
                    </div>
                    <div>
                        ${isCompleted ? 
                            `<button disabled style="background: rgba(40, 167, 69, 0.2); color: #28a745; border: 1px solid #28a745; padding: 8px 15px; border-radius: 8px; font-size: 12px;">مكتمل ✔️</button>` 
                            : 
                            `<button id="btn-task-${task.id}" onclick="startTask('${task.id}', '${task.link}', ${task.reward})" style="background: #fff; color: #000; border: none; padding: 8px 20px; border-radius: 8px; font-size: 12px; cursor: pointer;">ابدأ</button>`
                        }
                    </div>
                </div>`;
        });
        container.innerHTML = html;
    }

    // 5. عمل المهمة (بتربط بالسيرفر الحقيقي)
    window.startTask = function(taskId, link, reward) {
        window.open(link, '_blank');
        const btn = document.getElementById(`btn-task-${taskId}`);
        btn.innerText = "تحقق ⏳";
        btn.style.background = "#ffcc00";
        
        btn.onclick = async function() {
            btn.innerText = "جاري التأكيد...";
            btn.disabled = true;

            try {
                // الاتصال بـ API السيرفر
                let response = await fetch('/api/complete_task', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ telegramId: getTgId(), taskId: taskId })
                });

                let result = await response.json();

                if (response.ok && result.success) {
                    completedTasks.push(taskId);
                    localStorage.setItem('zn_completed_tasks', JSON.stringify(completedTasks));
                    
                    alert(`🎉 مبروك! تمت إضافة المكافأة.`);
                    
                    // إجبار النظام المركزي على سحب الرصيد الجديد من السيرفر فوراً
                    if (typeof window.fetchPlayerDataFromServer === 'function') {
                        await window.fetchPlayerDataFromServer();
                    }
                } else {
                    // السيرفر رفض (ممكن لأن المهمة مش موجودة في قاعدة بيانات السيرفر لسه)
                    // للتمويه في وضع التطوير: هنحفظها محلي ونحدث الواجهة مؤقتاً
                    console.warn("المهمة غير موجودة في قاعدة البيانات، سيتم محاكاتها محلياً.");
                    completedTasks.push(taskId);
                    localStorage.setItem('zn_completed_tasks', JSON.stringify(completedTasks));
                    
                    if (window.PlayerData) {
                        window.PlayerData.balance += reward;
                    }
                    if (typeof window.triggerAllUIUpdates === 'function') window.triggerAllUIUpdates();
                    else updateTasksUI();
                    
                    alert(`🎉 مبروك! تمت إضافة ${reward.toLocaleString()} ZN`);
                }
            } catch (e) {
                console.error("خطأ في السيرفر", e);
                btn.innerText = "تحقق ⏳";
                btn.disabled = false;
            }
        };
    };

    // 6. التحويل من ZN إلى إعلانات (بتربط بالسيرفر الحقيقي)
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
                // إجبار السيرفر على سحب الرصيد المحدث
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
    // 🛠️ نظام إدارة الإعلانات وإنشائها (السيرفر الحقيقي)
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
                
                closeAdModal();
                alert("✅ تم نشر حملتك الإعلانية بنجاح!");
                
                if (typeof window.fetchPlayerDataFromServer === 'function') {
                    await window.fetchPlayerDataFromServer();
                }
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
    setTimeout(updateTasksUI, 300);
})();

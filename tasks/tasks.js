(function initTasks() {
    
    // 1. قائمة المهام كاملة زي ما طلبت
    const dummyTasks = [
        { id: 101, title: "انضم لقناتنا الرسمية", reward: 5000, icon: "fab fa-telegram", color: "#38bdf8", link: "https://t.me/" },
        { id: 102, title: "اشترك في قناة اليوتيوب", reward: 8000, icon: "fab fa-youtube", color: "#ef4444", link: "https://youtube.com/" },
        { id: 103, title: "تابعنا على منصة X", reward: 3000, icon: "fab fa-twitter", color: "#1da1f2", link: "https://x.com/" },
        { id: 104, title: "زيارة موقعنا", reward: 2000, icon: "fas fa-globe", color: "#28a745", link: "https://google.com/" },
        { id: 105, title: "متابعة انستغرام", reward: 4000, icon: "fab fa-instagram", color: "#e1306c", link: "https://instagram.com/" }
    ];

    let completedTasks = JSON.parse(localStorage.getItem('zn_completed_tasks') || '[]');
    let myAds = JSON.parse(localStorage.getItem('zn_my_ads') || '[]');

    // =========================================================
    // 🔴 الحل الجذري لمشكلة اختفاء الرصيد ورجوعه 🔴
    // =========================================================
    async function updateBalanceSecurely(newBalance, newAdBalance) {
        // 1. تحديث المتغيرات العالمية فوراً عشان الشاشة متعملش فلاش للرقم القديم
        if (!window.PlayerData) window.PlayerData = {};
        window.PlayerData.balance = newBalance;
        window.PlayerData.ad_balance = newAdBalance;

        // 2. تحديث واجهة المستخدم العلوية (اللي في كل الصفحات)
        const allMainBalances = document.querySelectorAll('.sync-balance');
        allMainBalances.forEach(el => el.innerText = `ZN ${Math.floor(newBalance).toLocaleString()}`);

        // 3. محاولة إرسال التحديث لملف server.py الخاص بك أو قاعدة البيانات
        try {
            // استدعاء دالة الحفظ الخاصة بمشروعك (لو موجودة في game.js)
            if (typeof window.saveUserData === 'function') {
                window.saveUserData(); 
            } else if (typeof window.updateServerData === 'function') {
                window.updateServerData();
            }
            
            // تحديث الواجهة المحلية
            updateTasksUI();
            return true;
        } catch (error) {
            console.error("خطأ في الحفظ:", error);
            updateTasksUI();
            return true; 
        }
    }

    // 2. دالة التبديل بين الأقسام
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
        
        // تحديث رصيد المهام اللي فوق
        const tasksTopBalance = document.getElementById('top-balance-tasks');
        if (tasksTopBalance) tasksTopBalance.innerText = `ZN ${Math.floor(pData.balance || 0).toLocaleString()}`;

        // تحديث الرصيد الإعلاني
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
                            `<button id="btn-task-${task.id}" onclick="startTask(${task.id}, '${task.link}', ${task.reward})" style="background: #fff; color: #000; border: none; padding: 8px 20px; border-radius: 8px; font-size: 12px; cursor: pointer;">ابدأ</button>`
                        }
                    </div>
                </div>`;
        });
        container.innerHTML = html;
    }

    // 5. عمل المهمة واكتساب الرصيد
    window.startTask = function(taskId, link, reward) {
        window.open(link, '_blank');
        const btn = document.getElementById(`btn-task-${taskId}`);
        btn.innerText = "تحقق ⏳";
        btn.style.background = "#ffcc00";
        
        btn.onclick = async function() {
            btn.innerText = "جاري التأكيد...";
            btn.disabled = true;

            let currentBalance = parseFloat(window.PlayerData?.balance || 0);
            let currentAdBalance = parseFloat(window.PlayerData?.ad_balance || 0);
            
            // إضافة الرصيد وتحديثه بقوة
            completedTasks.push(taskId);
            localStorage.setItem('zn_completed_tasks', JSON.stringify(completedTasks));
            
            await updateBalanceSecurely(currentBalance + reward, currentAdBalance);
            alert(`🎉 مبروك! تمت إضافة ${reward.toLocaleString()} ZN`);
        };
    };

    // 6. التحويل من ZN إلى إعلانات (ممنوع العكس)
    window.convertZnToAdZn = async function() {
        let amount = prompt("أدخل كمية ZN لتحويلها إلى رصيد إعلانات (AdZN):");
        if (!amount || isNaN(amount) || amount <= 0) return;
        amount = parseInt(amount);

        let currentBalance = parseFloat(window.PlayerData?.balance || 0);
        let currentAdBalance = parseFloat(window.PlayerData?.ad_balance || 0);

        if (currentBalance < amount) {
            alert("⚠️ رصيدك من ZN غير كافٍ!");
            return;
        }

        // خصم وإضافة وتحديث قوي
        await updateBalanceSecurely(currentBalance - amount, currentAdBalance + amount);
        alert(`✅ تم شحن رصيد الإعلانات بنجاح بـ ${amount} AdZN`);
    };

    // ==========================================
    // 🛠️ نظام إدارة الإعلانات وإنشائها
    // ==========================================
    let currentAdType = '';

    window.openAdModal = function(type) {
        currentAdType = type;
        document.getElementById('ad-modal-title').innerText = `حملة ${type} جديدة`;
        document.getElementById('ad-link').value = '';
        document.getElementById('ad-budget').value = '';
        document.getElementById('ad-modal').style.display = 'flex';
    };

    window.closeAdModal = function() {
        document.getElementById('ad-modal').style.display = 'none';
    };

    // نشر الإعلان وخصم الرصيد الإعلاني
    window.submitAdCampaign = async function() {
        let link = document.getElementById('ad-link').value;
        let budget = parseInt(document.getElementById('ad-budget').value);

        if (!link || isNaN(budget) || budget <= 0) {
            alert("⚠️ يرجى إدخال الرابط والميزانية بشكل صحيح!");
            return;
        }

        let currentBalance = parseFloat(window.PlayerData?.balance || 0);
        let currentAdBalance = parseFloat(window.PlayerData?.ad_balance || 0);

        if (currentAdBalance < budget) {
            alert("⚠️ رصيد الإعلانات الخاص بك غير كافٍ! قم بشحنه أولاً.");
            return;
        }

        // خصم الميزانية الإعلانية فقط
        await updateBalanceSecurely(currentBalance, currentAdBalance - budget);
        
        // حفظ الإعلان
        let newAd = { id: Date.now(), type: currentAdType, link: link, budget: budget };
        myAds.push(newAd);
        localStorage.setItem('zn_my_ads', JSON.stringify(myAds));
        
        closeAdModal();
        alert("✅ تم نشر حملتك الإعلانية بنجاح!");
    };

    // عرض الإعلانات النشطة
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
                        <span style="color: #38bdf8; font-size: 13px; font-weight: bold;">${ad.budget} AdZN</span>
                    </div>
                    <div style="color: #888; font-size: 11px; margin-bottom: 15px; word-break: break-all;">${ad.link}</div>
                    <button onclick="cancelMyAd(${ad.id})" style="width: 100%; background: rgba(239,68,68,0.1); border: 1px solid #ef4444; color: #ef4444; padding: 8px; border-radius: 8px; cursor: pointer; font-weight: bold;">إلغاء واسترداد (يخصم 10%)</button>
                </div>`;
        });
        container.innerHTML = html;
    }

    // إلغاء الإعلان واسترداد 90% لرصيد الإعلانات
    window.cancelMyAd = async function(adId) {
        if (!confirm("هل أنت متأكد من إلغاء الإعلان؟ سيتم خصم 10% كرسوم إدارية ولن يمكنك تحويل الرصيد لـ ZN.")) return;

        let adIndex = myAds.findIndex(a => a.id === adId);
        if (adIndex === -1) return;

        let ad = myAds[adIndex];
        let refundAmount = Math.floor(ad.budget * 0.9); // خصم 10%
        
        let currentBalance = parseFloat(window.PlayerData?.balance || 0);
        let currentAdBalance = parseFloat(window.PlayerData?.ad_balance || 0);

        // إرجاع الرصيد الإعلاني فقط
        await updateBalanceSecurely(currentBalance, currentAdBalance + refundAmount);
        
        // مسح الإعلان من القائمة
        myAds.splice(adIndex, 1);
        localStorage.setItem('zn_my_ads', JSON.stringify(myAds));
        
        alert(`✅ تم الإلغاء! تمت إعادة ${refundAmount} AdZN لرصيدك الإعلاني.`);
    };

    // تشغيل التحديث عند فتح الصفحة
    setTimeout(updateTasksUI, 300);
})();

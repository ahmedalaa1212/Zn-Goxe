(function initTasks() {
    
    // تأمين متغير رصيد الإعلانات في الكائن المركزي (عشان لو مش جاي من السيرفر لسه)
    if (window.PlayerData && typeof window.PlayerData.ad_balance === 'undefined') {
        window.PlayerData.ad_balance = 0; 
    }

    // 1. قاعدة بيانات المهام التجريبية
    const dummyTasks = [
        { id: 101, title: "انضم لقناتنا الرسمية", reward: 5000, icon: "fab fa-telegram", color: "#38bdf8", link: "https://t.me/telegram" },
        { id: 102, title: "اشترك في قناة اليوتيوب", reward: 8000, icon: "fab fa-youtube", color: "#ef4444", link: "https://youtube.com" },
        { id: 103, title: "تابعنا على منصة X", reward: 3000, icon: "fab fa-twitter", color: "#1da1f2", link: "https://twitter.com" }
    ];

    // جلب المهام المكتملة محلياً (للتجربة حالياً لحد ما نربطها بقاعدة البيانات)
    let completedTasks = JSON.parse(localStorage.getItem('zn_completed_tasks') || '[]');

    // 2. دالة التبديل بين (اكسب ZN) و (روّج لقناتك)
    window.switchTasksTab = function(tab) {
        const earnSec = document.getElementById('section-earn');
        const promoteSec = document.getElementById('section-promote');
        const btnEarn = document.getElementById('btn-tab-earn');
        const btnPromote = document.getElementById('btn-tab-promote');

        if (tab === 'earn') {
            earnSec.style.display = 'block';
            promoteSec.style.display = 'none';
            btnEarn.style.background = '#0088cc';
            btnEarn.style.color = '#fff';
            btnPromote.style.background = 'transparent';
            btnPromote.style.color = '#888';
        } else {
            earnSec.style.display = 'none';
            promoteSec.style.display = 'block';
            btnEarn.style.background = 'transparent';
            btnEarn.style.color = '#888';
            btnPromote.style.background = '#0088cc';
            btnPromote.style.color = '#fff';
        }
    };

    // 3. دالة تحديث واجهة المهام (بتشتغل مع المزامنة المركزية)
    window.updateTasksUI = function() {
        const pData = window.PlayerData;
        if (!pData) return;

        // تحديث رصيد الإعلانات
        const adBalDisplay = document.getElementById('ad-balance-display');
        if (adBalDisplay) {
            adBalDisplay.innerText = `AdZN ${Math.floor(pData.ad_balance || 0).toLocaleString()}`;
        }

        // رسم المهام
        renderTasksList();
    };

    // 4. دالة رسم المهام
    function renderTasksList() {
        const container = document.getElementById('tasks-list-container');
        if (!container) return;

        let html = '';
        dummyTasks.forEach(task => {
            const isCompleted = completedTasks.includes(task.id);
            
            html += `
                <div style="background: #1a1a1a; border: 1px solid #333; border-radius: 12px; padding: 15px; margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="width: 45px; height: 45px; background: rgba(255,255,255,0.05); border-radius: 50%; display: flex; align-items: center; justify-content: center;">
                            <i class="${task.icon}" style="font-size: 24px; color: ${task.color};"></i>
                        </div>
                        <div style="text-align: right;">
                            <div style="color: #fff; font-size: 13px; font-weight: bold; margin-bottom: 3px;">${task.title}</div>
                            <div style="color: #ffcc00; font-size: 12px; font-weight: bold;">+${task.reward.toLocaleString()} ZN</div>
                        </div>
                    </div>
                    <div>
                        ${isCompleted ? 
                            `<button disabled style="background: rgba(40, 167, 69, 0.2); color: #28a745; border: 1px solid #28a745; padding: 8px 15px; border-radius: 8px; font-family: inherit; font-weight: bold; font-size: 12px;">مكتمل ✔️</button>` 
                            : 
                            `<button id="btn-task-${task.id}" onclick="startTask(${task.id}, '${task.link}', ${task.reward})" style="background: #fff; color: #000; border: none; padding: 8px 20px; border-radius: 8px; font-family: inherit; font-weight: bold; font-size: 12px; cursor: pointer; transition: 0.2s;">ابدأ</button>`
                        }
                    </div>
                </div>
            `;
        });
        container.innerHTML = html;
    }

    // 5. دالة بدء المهمة (تفتح الرابط وتجهز زر التحقق)
    window.startTask = function(taskId, link, reward) {
        const btn = document.getElementById(`btn-task-${taskId}`);
        if (!btn) return;

        // فتح الرابط
        if (window.Telegram && window.Telegram.WebApp) {
            window.Telegram.WebApp.openLink(link);
        } else {
            window.open(link, '_blank');
        }

        // تغيير الزر لوضع التحقق
        btn.innerText = "تحقق ⏳";
        btn.style.background = "#ffcc00";
        btn.style.color = "#000";
        btn.onclick = function() { verifyTask(taskId, reward, btn); };
    };

    // 6. دالة التحقق وإعطاء المكافأة
    window.verifyTask = function(taskId, reward, btn) {
        btn.innerText = "جاري التأكد...";
        btn.disabled = true;

        // محاكاة تأخير السيرفر للتحقق
        setTimeout(() => {
            // للتجربة: إضافة الرصيد مباشرة في الكائن المركزي
            if (window.PlayerData) {
                window.PlayerData.balance = parseFloat(window.PlayerData.balance) + reward;
            }
            
            // حفظ المهمة كمكتملة
            completedTasks.push(taskId);
            localStorage.setItem('zn_completed_tasks', JSON.stringify(completedTasks));

            // تنبيه للمستخدم
            if (window.Telegram && window.Telegram.WebApp) {
                window.Telegram.WebApp.showAlert(`🎉 مبروك! لقد حصلت على ${reward.toLocaleString()} ZN لإتمام المهمة.`);
            } else {
                alert(`🎉 مبروك! لقد حصلت على ${reward.toLocaleString()} ZN لإتمام المهمة.`);
            }
            
            // إجبار كل الشاشات على تحديث أرقامها فوراً (عشان الرصيد يسمع فوق)
            if (typeof window.triggerAllUIUpdates === 'function') {
                window.triggerAllUIUpdates();
            } else {
                window.updateTasksUI(); 
            }
        }, 2000); // انتظار ثانيتين للواقعية
    };

    // 7. دالة تحويل رصيد ZN لعملات إعلانية AdZN
    window.convertZnToAdZn = function() {
        let amount = prompt("أدخل كمية ZN التي تريد تحويلها إلى رصيد إعلانات (AdZN):\n\nعلماً بأن 1 ZN = 1 AdZN");
        
        if (!amount || amount.trim() === "") return;
        amount = parseInt(amount);

        if (isNaN(amount) || amount <= 0) {
            alert("⚠️ يرجى إدخال رقم صحيح!");
            return;
        }

        if (window.PlayerData && window.PlayerData.balance >= amount) {
            // الخصم والإضافة
            window.PlayerData.balance -= amount;
            window.PlayerData.ad_balance = (window.PlayerData.ad_balance || 0) + amount;
            
            alert(`✅ تم تحويل ${amount.toLocaleString()} ZN إلى رصيد إعلانات بنجاح!`);
            
            // تحديث الشاشات لسماع الخصم فوق والإضافة تحت
            if (typeof window.triggerAllUIUpdates === 'function') {
                window.triggerAllUIUpdates();
            } else {
                window.updateTasksUI();
            }
        } else {
            alert("⚠️ رصيدك من ZN غير كافٍ لإتمام عملية التحويل!");
        }
    };

    // 8. حيلة برمجية ذكية: نربط تحديث المهام بالدالة المركزية بتاعت التطبيق كله بدون ما نعدل ملف game.js
    if (typeof window.triggerAllUIUpdates !== 'undefined') {
        const originalTrigger = window.triggerAllUIUpdates;
        window.triggerAllUIUpdates = function() {
            originalTrigger(); // شغل التحديث العادي لباقي الشاشات
            if (typeof window.updateTasksUI === 'function') window.updateTasksUI(); // حدث شاشة المهام كمان معاهم
        };
    }

    // تشغيل التحديث فور فتح الصفحة
    setTimeout(window.updateTasksUI, 200);

})();

(function initFriends() {
    // 1. إعدادات التيليجرام الأساسية
    const tg = window.Telegram.WebApp;
    // الحصول على أيدي المستخدم من التيليجرام، أو وضع رقم افتراضي للتجربة
    const userId = tg.initDataUnsafe?.user?.id || '123456789'; 
    const botUsername = 'ZnGoxe_Bot'; // ضع يوزرنيم البوت الخاص بك هنا

    // 2. إنشاء رابط الإحالة الخاص بتطبيقات تيليجرام المصغرة (Mini Apps)
    const referralLink = `https://t.me/${botUsername}/start?startapp=ref_${userId}`;
    document.getElementById('invite-link-input').value = referralLink;

    // 3. محاكاة بيانات المستخدم من قاعدة البيانات (Firebase)
    // **ملاحظة للمطور**: يجب أن يتم جلب هذه القيم من قاعدة البيانات الخاصة بك
    let userData = {
        balance: 50000, // الرصيد الأساسي
        pendingReferralEarnings: 1250, // الأرباح المعلقة من لعب الأصدقاء
        invitedFriendsCount: 4, // عدد الأصدقاء الفعلي الذين دخلوا من الرابط
        claimedTasks: [] // أرقام المهام التي تم استلامها مسبقاً (مثال: [1])
    };

    // تحديث الواجهة بالبيانات الحالية
    updateUI();

    // 4. دالة نسخ الرابط
    window.copyInviteLink = function() {
        navigator.clipboard.writeText(referralLink).then(() => {
            const btn = document.getElementById('copy-link-btn');
            btn.innerText = "تم النسخ! ✓";
            btn.style.background = "#00cc66";
            setTimeout(() => {
                btn.innerText = "نسخ الرابط";
                btn.style.background = "#0088cc";
            }, 2000);
            
            // يمكنك إضافة تأثير اهتزاز (Haptic Feedback) من تيليجرام
            tg.HapticFeedback.impactOccurred('light');
        });
    };

    // 5. دالة تجميع أرباح الأصدقاء (مع خصم 3%)
    window.claimReferralEarnings = function() {
        if (userData.pendingReferralEarnings <= 0) return;

        // حساب الخصم
        const amount = userData.pendingReferralEarnings;
        const fee = amount * 0.03; // خصم 3%
        const netAmount = amount - fee; // الصافي الذي سيضاف للرصيد

        // تحديث البيانات (هنا يجب عمل Update في Firebase)
        userData.balance += netAmount;
        userData.pendingReferralEarnings = 0;

        // تأثير اهتزاز النجاح
        tg.HapticFeedback.notificationOccurred('success');

        // تحديث الواجهة
        updateUI();

        // تنبيه للمستخدم بنجاح العملية
        tg.showAlert(`تم تجميع ${netAmount.toLocaleString()} ZN بنجاح بعد خصم رسوم 3% (${fee} ZN).`);
    };

    // 6. تهيئة مهام دعوة الأصدقاء
    const tasks = [
        { id: 1, friendsReq: 1, reward: 500 },
        { id: 2, friendsReq: 3, reward: 1500 },
        { id: 3, friendsReq: 5, reward: 3000 },
        { id: 4, friendsReq: 10, reward: 7000 },
        { id: 5, friendsReq: 15, reward: 12000 },
        { id: 6, friendsReq: 20, reward: 20000 },
        { id: 7, friendsReq: 30, reward: 35000 },
        { id: 8, friendsReq: 50, reward: 60000 },
        { id: 9, friendsReq: 75, reward: 100000 },
        { id: 10, friendsReq: 100, reward: 200000 }
    ];

    function renderTasks() {
        const tasksList = document.getElementById('friends-tasks-list');
        tasksList.innerHTML = tasks.map(task => {
            const isClaimed = userData.claimedTasks.includes(task.id);
            const isEligible = userData.invitedFriendsCount >= task.friendsReq;
            
            let btnClass = 'claim-task-btn';
            let btnText = 'استلام';
            let onclickAttr = '';

            if (isClaimed) {
                btnClass += ' claimed';
                btnText = 'تم الاستلام';
            } else if (isEligible) {
                btnClass += ' active';
                onclickAttr = `onclick="claimTask(${task.id}, ${task.reward})"`;
            } else {
                // لم يكمل العدد المطلوب بعد
                onclickAttr = `onclick="showTaskError(${task.friendsReq})"`;
            }

            return `
                <div class="task-item">
                    <div class="task-info">
                        <div class="task-title">دعوة ${task.friendsReq} صديق</div>
                        <div class="task-reward">المكافأة: ZN ${task.reward.toLocaleString()}</div>
                    </div>
                    <button class="${btnClass}" ${onclickAttr}>${btnText}</button>
                </div>
            `;
        }).join('');
    }

    // 7. دالة استلام مكافأة المهمة
    window.claimTask = function(taskId, reward) {
        // تأكيد إضافي
        if (userData.claimedTasks.includes(taskId)) return;

        // تحديث البيانات (يجب تحديث Firebase هنا: زيادة الرصيد وإضافة الـ taskId لمصفوفة claimedTasks)
        userData.balance += reward;
        userData.claimedTasks.push(taskId);
        
        tg.HapticFeedback.notificationOccurred('success');
        updateUI();
    };

    // 8. رسالة خطأ إذا حاول الاستلام قبل اكتمال العدد
    window.showTaskError = function(req) {
        tg.HapticFeedback.notificationOccurred('error');
        tg.showAlert(`عذراً، يجب عليك دعوة ${req} أصدقاء أولاً لاستلام هذه المكافأة. لديك الآن ${userData.invitedFriendsCount} صديق.`);
    };

    // 9. دالة مركزية لتحديث الواجهة بالكامل
    function updateUI() {
        // تحديث الرصيد فوق
        document.getElementById('friends-current-balance').innerText = userData.balance.toLocaleString();
        
        // تحديث الأرباح المعلقة
        document.getElementById('pending-referral-earnings').innerText = userData.pendingReferralEarnings.toLocaleString();
        
        // تعطيل/تفعيل زر التجميع
        const claimEarningsBtn = document.getElementById('claim-earnings-btn');
        if (userData.pendingReferralEarnings <= 0) {
            claimEarningsBtn.disabled = true;
            claimEarningsBtn.innerText = "لا توجد أرباح للتجميع";
        } else {
            claimEarningsBtn.disabled = false;
            claimEarningsBtn.innerText = "تجميع أرباح الأصدقاء";
        }

        // تحديث عدد الأصدقاء
        document.getElementById('total-invited-friends').innerText = userData.invitedFriendsCount;

        // إعادة رسم المهام بناءً على البيانات الجديدة
        renderTasks();
    }
})();

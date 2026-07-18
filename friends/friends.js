(function initFriends() {
    const tg = window.Telegram.WebApp;
    // الحصول على أيدي المستخدم
    const userId = tg.initDataUnsafe?.user?.id || '123456789'; 
    const botUsername = 'ZnGoxe_Bot'; // تأكد من تغيير هذا ليوزرنيم البوت الخاص بك
    
    // رابط الإحالة
    const referralLink = `https://t.me/${botUsername}/start?startapp=ref_${userId}`;
    
    // مهلة بسيطة لضمان تحميل الـ HTML قبل وضع الرابط
    setTimeout(() => {
        const linkInput = document.getElementById('invite-link-input');
        if(linkInput) linkInput.value = referralLink;
    }, 100);

    // بيانات وهمية مؤقتة للتجربة (سيتم استبدالها لاحقاً ببيانات السيرفر)
    let userData = {
        balance: 50000, 
        pendingReferralEarnings: 1250, 
        invitedFriendsCount: 4, 
        claimedTasks: [] 
    };

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

    // رسم قائمة المهام
    function renderTasks() {
        const tasksList = document.getElementById('friends-tasks-list');
        if(!tasksList) return;
        
        tasksList.innerHTML = tasks.map(task => {
            const isClaimed = userData.claimedTasks.includes(task.id);
            const isEligible = userData.invitedFriendsCount >= task.friendsReq;
            
            // تنسيق الزر الافتراضي
            let btnStyle = `border: none; padding: 10px 15px; border-radius: 8px; font-size: 13px; font-weight: bold; cursor: pointer;`;
            let btnText = 'استلام';
            let onclickAttr = '';

            if (isClaimed) {
                btnStyle += ` background: #2a2a2a; color: #555; cursor: not-allowed;`;
                btnText = 'تم الاستلام';
            } else if (isEligible) {
                btnStyle += ` background: #0088cc; color: #fff;`; // أزرق عند القابلية للاستلام
                onclickAttr = `onclick="claimTask(${task.id}, ${task.reward})"`;
            } else {
                btnStyle += ` background: #444; color: #fff;`; // رمادي إذا لم يكمل العدد
                onclickAttr = `onclick="showTaskError(${task.friendsReq})"`;
            }

            return `
                <div style="background: #1c1c1c; padding: 15px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #333; text-align: right;">
                    <div>
                        <div style="font-weight: bold; font-size: 16px; margin-bottom: 5px; color: #fff;">دعوة ${task.friendsReq} صديق</div>
                        <div style="font-size: 13px; color: #ffcc00;">المكافأة: ZN ${task.reward.toLocaleString()}</div>
                    </div>
                    <button style="${btnStyle}" ${onclickAttr}>${btnText}</button>
                </div>
            `;
        }).join('');
    }

    // تحديث الأرقام في الواجهة
    function updateUI() {
        const balEl = document.getElementById('friends-current-balance');
        if(balEl) balEl.innerText = userData.balance.toLocaleString();
        
        const earnEl = document.getElementById('pending-referral-earnings');
        if(earnEl) earnEl.innerText = userData.pendingReferralEarnings.toLocaleString();
        
        const claimBtn = document.getElementById('claim-earnings-btn');
        if(claimBtn) {
            if (userData.pendingReferralEarnings <= 0) {
                claimBtn.disabled = true;
                claimBtn.innerText = "لا توجد أرباح للتجميع";
                claimBtn.style.background = "#333";
                claimBtn.style.color = "#777";
                claimBtn.style.cursor = "not-allowed";
            } else {
                claimBtn.disabled = false;
                claimBtn.innerText = "تجميع أرباح الأصدقاء";
                claimBtn.style.background = "#00cc66";
                claimBtn.style.color = "white";
                claimBtn.style.cursor = "pointer";
            }
        }

        const invEl = document.getElementById('total-invited-friends');
        if(invEl) invEl.innerText = userData.invitedFriendsCount;

        renderTasks();
    }

    // نسخ الرابط
    window.copyInviteLink = function() {
        navigator.clipboard.writeText(referralLink).then(() => {
            const btn = document.getElementById('copy-link-btn');
            btn.innerText = "تم النسخ! ✓";
            btn.style.background = "#00cc66";
            setTimeout(() => {
                btn.innerText = "نسخ الرابط";
                btn.style.background = "#0088cc";
            }, 2000);
            if(tg.HapticFeedback) tg.HapticFeedback.impactOccurred('light');
        });
    };

    // تجميع أرباح الأصدقاء (بخصم 3%)
    window.claimReferralEarnings = function() {
        if (userData.pendingReferralEarnings <= 0) return;
        
        const amount = userData.pendingReferralEarnings;
        const fee = amount * 0.03; // خصم 3%
        const netAmount = amount - fee; // الصافي

        userData.balance += netAmount;
        userData.pendingReferralEarnings = 0;

        if(tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        updateUI();
        tg.showAlert(`تم تجميع ${netAmount.toLocaleString()} ZN بنجاح بعد خصم رسوم التحويل 3% (${fee} ZN).`);
    };

    // استلام المهام
    window.claimTask = function(taskId, reward) {
        if (userData.claimedTasks.includes(taskId)) return;
        
        userData.balance += reward;
        userData.claimedTasks.push(taskId);
        
        if(tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('success');
        updateUI();
    };

    // تنبيه الخطأ
    window.showTaskError = function(req) {
        if(tg.HapticFeedback) tg.HapticFeedback.notificationOccurred('error');
        tg.showAlert(`عذراً، يجب عليك دعوة ${req} أصدقاء أولاً لاستلام هذه المكافأة. لديك الآن ${userData.invitedFriendsCount} صديق.`);
    };

    // تشغيل التحديث الأولي بعد 100 ملي ثانية لضمان ظهور العناصر
    setTimeout(updateUI, 100);
})();

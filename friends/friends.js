// ==========================================
// إعدادات مهام الأصدقاء والمكافآت
// ==========================================
const REF_TASKS = [
    { id: 1, reqFriends: 1, reward: 5000 },
    { id: 2, reqFriends: 5, reward: 30000 },
    { id: 3, reqFriends: 10, reward: 75000 },
    { id: 4, reqFriends: 25, reward: 200000 },
    { id: 5, reqFriends: 50, reward: 500000 },
    { id: 6, reqFriends: 100, reward: 1500000 },
    { id: 7, reqFriends: 500, reward: 10000000 }
];

const BOT_USERNAME = "zngoxe_bot"; 
const APP_SHORT_NAME = "app"; 

// ==========================================
// تحديث الواجهة (الرئيسية)
// ==========================================
window.updateFriendsUI = function() {
    const pData = window.PlayerData;
    if (!pData) return;

    // 1. تحديث الأرصدة والعدادات في المربعات العلوية
    const pendingEl = document.getElementById('pending-ref-earnings');
    if (pendingEl) pendingEl.innerText = Math.floor(pData.pending_ref_earnings || 0).toLocaleString();

    const countEl = document.getElementById('invited-friends-count');
    if (countEl) countEl.innerText = parseInt(pData.invited_friends_count || 0).toLocaleString();

    const topBalance = document.getElementById('top-balance-friends');
    if (topBalance) topBalance.innerText = `ZN: ${Math.floor(pData.balance || 0).toLocaleString()}`;

    // تفعيل/تعطيل زر السحب
    const btnClaim = document.getElementById('btn-claim-ref');
    if (btnClaim) {
        if (pData.pending_ref_earnings <= 0) {
            btnClaim.disabled = true;
            btnClaim.innerText = "لا توجد أرباح للسحب";
        } else {
            btnClaim.disabled = false;
            btnClaim.innerText = "سحب الأرباح الآن";
        }
    }

    // 2. تحديث رابط الدعوة
    const linkInput = document.getElementById('ref-link-input');
    if (linkInput && pData.tg_id) {
        linkInput.value = `https://t.me/${BOT_USERNAME}/${APP_SHORT_NAME}?startapp=ref_${pData.tg_id}`;
    }

    // 3. استدعاء دوال الرسم
    renderRefTasks();
    renderFriendsHistory(); 
};

// ==========================================
// رسم سجل الأصدقاء (بشكل احترافي مع Avatar)
// ==========================================
function renderFriendsHistory() {
    const container = document.getElementById('friends-list-container');
    if (!container) return;

    const pData = window.PlayerData;
    const friendsList = pData.referred_users_list || [];

    if (friendsList.length === 0) {
        container.innerHTML = `
            <div class="empty-state">
                <span style="font-size: 3rem; display: block; margin-bottom: 10px;">📭</span>
                لم تقم بدعوة أي صديق حتى الآن.<br>شارك رابطك لتبدأ في كسب الأرباح!
            </div>`;
        return;
    }

    let html = '<ul class="friends-list">';
    friendsList.forEach(friend => {
        const friendName = friend.name || "مستخدم";
        const friendId = friend.id || "---";
        const earnedFromHim = friend.earned || 0;
        
        // أخذ أول حرف من اسم الصديق للصورة الرمزية
        const firstLetter = friendName.charAt(0).toUpperCase();

        html += `
            <li class="friend-item">
                <div class="friend-avatar">${firstLetter}</div>
                <div class="friend-info">
                    <span class="friend-name">${friendName}</span>
                    <span class="friend-id">ID: ${friendId}</span>
                </div>
                <div class="friend-earn">
                    +${Math.floor(earnedFromHim).toLocaleString()} ZN
                </div>
            </li>
        `;
    });
    html += '</ul>';
    
    container.innerHTML = html;
}

// ==========================================
// رسم قائمة المهام (مع شريط التقدم Progress Bar)
// ==========================================
function renderRefTasks() {
    const listEl = document.getElementById('ref-tasks-list');
    if (!listEl) return;

    const pData = window.PlayerData;
    const currentFriends = parseInt(pData.invited_friends_count || 0);
    const claimedTasks = pData.claimed_ref_tasks || [];
    
    let html = '';

    REF_TASKS.forEach(task => {
        const isClaimed = claimedTasks.includes(task.id);
        const isReady = currentFriends >= task.reqFriends;
        
        // حساب نسبة شريط التقدم المئوية
        let progressPercent = (currentFriends / task.reqFriends) * 100;
        if (progressPercent > 100) progressPercent = 100; // الحد الأقصى 100%

        let btnHtml = '';
        if (isClaimed) {
            btnHtml = `<button disabled class="claimed-btn">✅ مستلمة</button>`;
        } else if (isReady) {
            btnHtml = `<button onclick="claimRefTask(${task.id}, ${task.reward}, ${task.reqFriends})" class="claim-btn">🎁 استلام</button>`;
        } else {
            let remaining = task.reqFriends - currentFriends;
            btnHtml = `<button disabled class="locked-btn">🔒 باقي ${remaining}</button>`;
        }

        html += `
            <li class="task-item">
                <div class="task-header">
                    <div class="task-info">
                        <h4>دعوة ${task.reqFriends} أصدقاء</h4>
                        <p>مكافأة: ${task.reward.toLocaleString()} ZN</p>
                    </div>
                    <div class="task-action">
                        ${btnHtml}
                    </div>
                </div>
                
                <!-- شريط التقدم -->
                <div class="progress-container">
                    <div class="progress-bar" style="width: ${progressPercent}%;"></div>
                </div>
                
                <div class="task-footer">
                    <span>تقدمك: ${currentFriends} / ${task.reqFriends}</span>
                    <span>${Math.floor(progressPercent)}%</span>
                </div>
            </li>
        `;
    });

    listEl.innerHTML = html;
}

// ==========================================
// دالة النسخ
// ==========================================
window.copyRefLink = function() {
    const linkInput = document.getElementById('ref-link-input');
    if (!linkInput || !linkInput.value || linkInput.value === "جاري التحميل...") return;
    
    navigator.clipboard.writeText(linkInput.value).then(() => {
        const tele = window.Telegram?.WebApp;
        if (tele && tele.showAlert) {
            tele.showAlert("تم نسخ الرابط بنجاح! 🚀 شاركه الآن.");
        } else {
            alert("تم نسخ الرابط بنجاح! 🚀");
        }
    }).catch(err => console.error('Error:', err));
};

// ==========================================
// دوال السحب والاستلام (تتصل بالخادم)
// ==========================================
window.claimRefEarnings = async function() {
    const pData = window.PlayerData;
    if (!pData || !pData.tg_id || pData.pending_ref_earnings <= 0) return;

    const btn = document.getElementById('btn-claim-ref');
    try {
        if(btn) { btn.disabled = true; btn.innerText = "⏳ جاري السحب..."; }

        const res = await fetch('/api/claim_ref_earnings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ telegramId: pData.tg_id })
        });
        
        const data = await res.json();
        
        if (data.success) {
            const tele = window.Telegram?.WebApp;
            const msg = `🎉 تم السحب بنجاح!\nأضيف ${Math.floor(data.net_amount).toLocaleString()} ZN إلى رصيدك.`;
            if (tele && tele.showAlert) tele.showAlert(msg);
            else alert(msg);
            
            // تحديث البيانات من الخادم
            if(window.fetchPlayerDataFromServer) window.fetchPlayerDataFromServer();
        } else {
            alert(data.error || 'حدث خطأ أثناء السحب.');
            if(btn) { btn.disabled = false; btn.innerText = "سحب الأرباح الآن"; }
        }
    } catch (e) {
        alert('خطأ في الاتصال بالخادم. يرجى المحاولة لاحقاً.');
        if(btn) { btn.disabled = false; btn.innerText = "سحب الأرباح الآن"; }
    }
};

window.claimRefTask = async function(taskId, reward, reqFriends) {
    const pData = window.PlayerData;
    if (!pData || !pData.tg_id) return;

    try {
        const res = await fetch('/api/claim_ref_task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ telegramId: pData.tg_id, taskId: taskId, reward: reward, reqFriends: reqFriends })
        });
        
        const data = await res.json();
        
        if (data.success) {
            const tele = window.Telegram?.WebApp;
            const msg = `🎊 مبروك! لقد أتممت المهمة واستلمت ${reward.toLocaleString()} ZN.`;
            if (tele && tele.showAlert) tele.showAlert(msg);
            else alert(msg);
            
            // تحديث البيانات من الخادم
            if(window.fetchPlayerDataFromServer) window.fetchPlayerDataFromServer();
        } else {
            alert(data.error || 'عذراً، لم تتمكن من استلام المكافأة.');
        }
    } catch (e) {
        alert('خطأ في الاتصال بالخادم.');
    }
};

// تهيئة الصفحة عند التحميل
if (window.PlayerData && window.PlayerData.tg_id) {
    window.updateFriendsUI();
}

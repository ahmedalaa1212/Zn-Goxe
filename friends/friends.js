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

    // 1. تحديث الأرصدة والعدادات
    const pendingEl = document.getElementById('pending-ref-earnings');
    if (pendingEl) pendingEl.innerText = Math.floor(pData.pending_ref_earnings || 0).toLocaleString();

    const countEl = document.getElementById('invited-friends-count');
    if (countEl) countEl.innerText = parseInt(pData.invited_friends_count || 0).toLocaleString();

    const topBalance = document.getElementById('top-balance-friends');
    if (topBalance) topBalance.innerText = `ZN: ${Math.floor(pData.balance || 0).toLocaleString()}`;

    const btnClaim = document.getElementById('btn-claim-ref');
    if (btnClaim) btnClaim.disabled = (pData.pending_ref_earnings <= 0);

    // 2. تحديث الرابط
    const linkInput = document.getElementById('ref-link-input');
    if (linkInput && pData.tg_id) {
        linkInput.value = `https://t.me/${BOT_USERNAME}/${APP_SHORT_NAME}?startapp=ref_${pData.tg_id}`;
    }

    // 3. استدعاء دوال الرسم
    renderRefTasks();
    renderFriendsHistory(); // الدالة الجديدة
};

// ==========================================
// القسم الجديد: رسم سجل الأصدقاء
// ==========================================
function renderFriendsHistory() {
    const container = document.getElementById('friends-list-container');
    if (!container) return;

    const pData = window.PlayerData;
    
    // الداتا بيز بتاعتك لازم تبعت مصفوفة اسمها referred_users_list
    // لو مش موجودة أو فاضية، هنعرض رسالة فارغة
    const friendsList = pData.referred_users_list || [];

    if (friendsList.length === 0) {
        container.innerHTML = '<div class="empty-state">لم تقم بدعوة أي صديق حتى الآن. شارك رابطك لتبدأ!</div>';
        return;
    }

    let html = '<ul class="friends-list">';
    friendsList.forEach(friend => {
        // friend المفروض يكون كائن فيه: name, id, earned
        const friendName = friend.name || "مستخدم مخفي";
        const friendId = friend.id || "بدون ID";
        const earnedFromHim = friend.earned || 0;

        html += `
            <li class="friend-item">
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
// رسم قائمة المهام
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
        
        let btnHtml = '';
        if (isClaimed) {
            btnHtml = `<button disabled class="claimed-btn">تم الاستلام</button>`;
        } else if (isReady) {
            btnHtml = `<button onclick="claimRefTask(${task.id}, ${task.reward}, ${task.reqFriends})" class="claim-btn">استلام</button>`;
        } else {
            let remaining = task.reqFriends - currentFriends;
            btnHtml = `<button disabled class="locked-btn">باقي ${remaining}</button>`;
        }

        html += `
            <li class="task-item">
                <div class="task-info">
                    <h4>دعوة ${task.reqFriends} أصدقاء</h4>
                    <p>مكافأة: ${task.reward.toLocaleString()} ZN</p>
                </div>
                <div class="task-action">
                    ${btnHtml}
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
    if (!linkInput || !linkInput.value) return;
    
    navigator.clipboard.writeText(linkInput.value).then(() => {
        const tele = window.Telegram?.WebApp;
        if (tele && tele.showAlert) {
            tele.showAlert("تم نسخ الرابط! شاركه الآن.");
        } else {
            alert("تم نسخ الرابط بنجاح!");
        }
    }).catch(err => console.error('Error:', err));
};

// ==========================================
// دوال السحب والاستلام (تتصل بالخادم)
// ==========================================
window.claimRefEarnings = async function() {
    const pData = window.PlayerData;
    if (!pData || !pData.tg_id || pData.pending_ref_earnings <= 0) return;

    try {
        const btn = document.getElementById('btn-claim-ref');
        if(btn) { btn.disabled = true; btn.innerText = "جاري السحب..."; }

        const res = await fetch('/api/claim_ref_earnings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ telegramId: pData.tg_id })
        });
        
        const data = await res.json();
        
        if (data.success) {
            const tele = window.Telegram?.WebApp;
            const msg = `تم السحب! حصلت على ${Math.floor(data.net_amount).toLocaleString()} ZN (خصم 3% رسوم).`;
            if (tele && tele.showAlert) tele.showAlert(msg);
            else alert(msg);
            
            if(window.fetchPlayerDataFromServer) window.fetchPlayerDataFromServer();
        } else {
            alert(data.error || 'حدث خطأ');
            if(btn) { btn.disabled = false; btn.innerText = "سحب الأرباح الآن"; }
        }
    } catch (e) {
        alert('خطأ في الاتصال بالخادم');
        const btn = document.getElementById('btn-claim-ref');
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
            const msg = `مبروك! استلمت ${reward.toLocaleString()} ZN.`;
            if (tele && tele.showAlert) tele.showAlert(msg);
            else alert(msg);
            
            if(window.fetchPlayerDataFromServer) window.fetchPlayerDataFromServer();
        } else {
            alert(data.error || 'خطأ في الاستلام');
        }
    } catch (e) {
        alert('خطأ في الاتصال');
    }
};

if (window.PlayerData && window.PlayerData.tg_id) {
    window.updateFriendsUI();
}

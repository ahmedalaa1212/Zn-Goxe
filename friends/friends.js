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

// 🔥 تم إضافة يوزرنيم البوت الخاص بك بنجاح
const BOT_USERNAME = "zngoxe_bot"; 
const APP_SHORT_NAME = "app"; // غيره لو الميني آب بتاعك اسمه حاجة تانية في البوت فازر (BotFather)

// ==========================================
// تحديث الواجهة (مربوط بالـ game.js)
// ==========================================
window.updateFriendsUI = function() {
    const pData = window.PlayerData;
    if (!pData) return;

    // 1. تحديث أرباح التعدين المعلقة
    const pendingEl = document.getElementById('pending-ref-earnings');
    if (pendingEl) pendingEl.innerText = Math.floor(pData.pending_ref_earnings || 0).toLocaleString();

    // 2. تحديث عدد الأصدقاء
    const countEl = document.getElementById('invited-friends-count');
    if (countEl) countEl.innerText = parseInt(pData.invited_friends_count || 0).toLocaleString();

    // 3. تحديث حالة زر سحب الأرباح (تعطيله لو الرصيد 0)
    const btnClaim = document.getElementById('btn-claim-ref');
    if (btnClaim) {
        btnClaim.disabled = (pData.pending_ref_earnings <= 0);
    }

    // 4. إنشاء وتحديث رابط الإحالة
    const linkInput = document.getElementById('ref-link-input');
    if (linkInput && pData.tg_id) {
        linkInput.value = `https://t.me/${BOT_USERNAME}/${APP_SHORT_NAME}?startapp=ref_${pData.tg_id}`;
    }

    // 5. رسم قائمة مهام الأصدقاء
    renderRefTasks();
};

// ==========================================
// رسم قائمة المهام بناءً على حالة المستخدم
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
// دالة نسخ رابط الإحالة
// ==========================================
window.copyRefLink = function() {
    const linkInput = document.getElementById('ref-link-input');
    if (!linkInput || !linkInput.value) return;
    
    navigator.clipboard.writeText(linkInput.value).then(() => {
        const tele = window.Telegram?.WebApp;
        if (tele && tele.showAlert) {
            tele.showAlert("تم نسخ رابط الدعوة بنجاح! شاركه مع أصدقائك لزيادة أرباحك.");
        } else {
            alert("تم نسخ رابط الدعوة بنجاح!");
        }
    }).catch(err => {
        console.error('Failed to copy: ', err);
    });
};

// ==========================================
// دالة سحب أرباح تعدين الأصدقاء (الـ 10%)
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
            const msg = `تم سحب ${Math.floor(data.net_amount).toLocaleString()} ZN بنجاح إلى رصيدك! (تم خصم 3% رسوم).`;
            if (tele && tele.showAlert) {
                tele.showAlert(msg);
            } else {
                alert(msg);
            }
            // إجبار التحديث اللحظي للبيانات المركزية لتسميع الرصيد الجديد
            if(window.fetchPlayerDataFromServer) window.fetchPlayerDataFromServer();
        } else {
            alert(data.error || 'حدث خطأ أثناء السحب');
            if(btn) { btn.disabled = false; btn.innerText = "سحب الأرباح الآن"; }
        }
    } catch (e) {
        console.error(e);
        alert('خطأ في الاتصال بالخادم');
        const btn = document.getElementById('btn-claim-ref');
        if(btn) { btn.disabled = false; btn.innerText = "سحب الأرباح الآن"; }
    }
};

// ==========================================
// دالة استلام مكافأة مهمة الإحالة
// ==========================================
window.claimRefTask = async function(taskId, reward, reqFriends) {
    const pData = window.PlayerData;
    if (!pData || !pData.tg_id) return;

    try {
        const res = await fetch('/api/claim_ref_task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                telegramId: pData.tg_id,
                taskId: taskId,
                reward: reward,
                reqFriends: reqFriends
            })
        });
        
        const data = await res.json();
        
        if (data.success) {
            const tele = window.Telegram?.WebApp;
            const msg = `مبروك! تم استلام مكافأة ${reward.toLocaleString()} ZN بنجاح.`;
            if (tele && tele.showAlert) {
                tele.showAlert(msg);
            } else {
                alert(msg);
            }
            // إجبار التحديث اللحظي للبيانات المركزية لتسميع الرصيد والمهمة المغلقة
            if(window.fetchPlayerDataFromServer) window.fetchPlayerDataFromServer();
        } else {
            alert(data.error || 'حدث خطأ أثناء الاستلام');
        }
    } catch (e) {
        console.error(e);
        alert('خطأ في الاتصال بالخادم');
    }
};

// تشغيل التحديث المبدئي إذا كانت البيانات محملة مسبقاً
if (window.PlayerData && window.PlayerData.tg_id) {
    window.updateFriendsUI();
}

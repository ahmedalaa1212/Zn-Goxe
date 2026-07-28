const REF_TASKS = [
    { id: 1, reqFriends: 1, reward: 5000 },
    { id: 2, reqFriends: 5, reward: 30000 },
    { id: 3, reqFriends: 10, reward: 75000 },
    { id: 4, reqFriends: 25, reward: 200000 },
    { id: 5, reqFriends: 50, reward: 500000 },
    { id: 6, reqFriends: 100, reward: 1500000 },
    { id: 7, reqFriends: 500, reward: 10000000 }
];

// ⚠️ تأكد أن هذا هو يوزر البوت الخاص بك بالضبط
const BOT_USERNAME = "zngoxe_bot"; 

// ==========================================
// 1. جلب البيانات تلقائياً عند فتح الصفحة
// ==========================================
document.addEventListener("DOMContentLoaded", async () => {
    const tele = window.Telegram?.WebApp;
    if (tele) {
        tele.ready();
        tele.expand();
    }
    
    const initData = tele?.initData;
    
    if (!initData) {
        document.getElementById('ref-link-input').value = "يرجى فتح التطبيق من تليجرام";
        document.getElementById('friends-list-container').innerHTML = '<div class="empty-state">يرجى فتح التطبيق من تليجرام لعرض الأصدقاء.</div>';
        return;
    }

    try {
        // جلب بيانات اللاعب الأساسية لعرض الرابط والمحفظة
        const response = await fetch('/api/farm/player_data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData })
        });
        
        const data = await response.json();
        
        if (data.success) {
            window.PlayerData = data.player; // حفظ البيانات
            updateFriendsUI(); // تحديث الواجهة
        } else {
            document.getElementById('ref-link-input').value = "حدث خطأ في جلب البيانات";
        }
        
        // جلب قائمة الأصدقاء (السجل)
        await fetchAndRenderFriendsList();

    } catch (error) {
        console.error("Error fetching data:", error);
        document.getElementById('ref-link-input').value = "خطأ في الاتصال بالسيرفر";
    }
});


// ==========================================
// 2. تحديث واجهة الأصدقاء (الرابط، المهام، الأرصدة)
// ==========================================
window.updateFriendsUI = function() {
    const pData = window.PlayerData;
    if (!pData) return;

    const pendingEl = document.getElementById('pending-ref-earnings');
    if (pendingEl) pendingEl.innerText = Math.floor(pData.pending_ref_earnings || 0).toLocaleString();

    const countEl = document.getElementById('invited-friends-count');
    if (countEl) countEl.innerText = parseInt(pData.invited_friends_count || 0).toLocaleString();

    const topBalance = document.getElementById('top-balance-friends');
    if (topBalance) topBalance.innerText = `ZN: ${Math.floor(pData.balance || 0).toLocaleString()}`;

    const btnClaim = document.getElementById('btn-claim-ref');
    if (btnClaim) {
        if ((pData.pending_ref_earnings || 0) <= 0) {
            btnClaim.disabled = true;
            btnClaim.innerText = "لا توجد أرباح للسحب";
        } else {
            btnClaim.disabled = false;
            btnClaim.innerText = "سحب الأرباح الآن";
        }
    }

    const linkInput = document.getElementById('ref-link-input');
    if (linkInput) {
        if (pData.telegram_id || pData.tg_id) {
            const uid = pData.telegram_id || pData.tg_id;
            linkInput.value = `https://t.me/${BOT_USERNAME}?start=ref_${uid}`;
        } else {
            linkInput.value = "فشل توليد الرابط";
        }
    }

    renderRefTasks();
};

// ==========================================
// 3. عرض مهام الأصدقاء (الإنجازات)
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
        
        let progressPercent = (currentFriends / task.reqFriends) * 100;
        if (progressPercent > 100) progressPercent = 100; 

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
// 4. نسخ الرابط
// ==========================================
window.copyRefLink = function() {
    const linkInput = document.getElementById('ref-link-input');
    if (!linkInput || !linkInput.value || linkInput.value.includes("جاري") || linkInput.value.includes("يرجى")) {
        const tele = window.Telegram?.WebApp;
        if (tele && tele.showAlert) tele.showAlert("يرجى الانتظار حتى يتم تحميل الرابط الخاص بك.");
        else alert("يرجى الانتظار حتى يتم تحميل الرابط الخاص بك.");
        return;
    }
    
    const finalLink = linkInput.value;
    
    navigator.clipboard.writeText(finalLink).then(() => {
        const tele = window.Telegram?.WebApp;
        if (tele && tele.showAlert) {
            tele.showAlert("✅ تم نسخ الرابط بنجاح! شاركه الآن.");
        } else {
            alert("تم نسخ الرابط بنجاح!");
        }
    }).catch(err => console.error('Error copying:', err));
};

// ==========================================
// 5. سحب أرباح الإحالة
// ==========================================
window.claimRefEarnings = async function() {
    const pData = window.PlayerData;
    const tele = window.Telegram?.WebApp;
    const initData = tele?.initData;

    if (!initData) return;
    if (!pData || (pData.pending_ref_earnings || 0) <= 0) return;

    const btn = document.getElementById('btn-claim-ref');
    try {
        if(btn) { btn.disabled = true; btn.innerText = "⏳ جاري السحب..."; }

        const res = await fetch('/api/friends/claim_ref_earnings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData })
        });
        
        const data = await res.json();
        
        if (data.success) {
            if (tele && tele.showAlert) tele.showAlert(`🎉 تم السحب بنجاح!\nأضيف ${Math.floor(data.net_amount).toLocaleString()} ZN إلى رصيدك.`);
            
            // تحديث البيانات محلياً
            window.PlayerData.balance = data.new_balance;
            window.PlayerData.pending_ref_earnings = 0;
            updateFriendsUI();
        } else {
            if (tele && tele.showAlert) tele.showAlert(data.error || 'حدث خطأ أثناء السحب.');
            if(btn) { btn.disabled = false; btn.innerText = "سحب الأرباح الآن"; }
        }
    } catch (e) {
        if (tele && tele.showAlert) tele.showAlert('خطأ في الاتصال بالخادم. يرجى المحاولة لاحقاً.');
        if(btn) { btn.disabled = false; btn.innerText = "سحب الأرباح الآن"; }
    }
};

// ==========================================
// 6. استلام مكافأة مهام الدعوة
// ==========================================
window.claimRefTask = async function(taskId, reward, reqFriends) {
    const tele = window.Telegram?.WebApp;
    const initData = tele?.initData;

    if (!initData) return;

    try {
        const res = await fetch('/api/friends/claim_ref_task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                initData: initData,
                taskId: taskId, 
                reward: reward, 
                reqFriends: reqFriends 
            })
        });
        
        const data = await res.json();
        
        if (data.success) {
            if (tele && tele.showAlert) tele.showAlert(`🎊 مبروك! لقد أتممت المهمة واستلمت ${reward.toLocaleString()} ZN.`);
            
            // تحديث البيانات محلياً
            window.PlayerData.balance = data.new_balance;
            if(!window.PlayerData.claimed_ref_tasks) window.PlayerData.claimed_ref_tasks = [];
            window.PlayerData.claimed_ref_tasks.push(taskId);
            updateFriendsUI();
        } else {
            if (tele && tele.showAlert) tele.showAlert(data.error || 'عذراً، لم تتمكن من استلام المكافأة.');
        }
    } catch (e) {
        if (tele && tele.showAlert) tele.showAlert('خطأ في الاتصال بالخادم.');
    }
};

// ==========================================
// 7. جلب وعرض سجل الأصدقاء
// ==========================================
window.fetchAndRenderFriendsList = async function() {
    const tele = window.Telegram?.WebApp;
    const initData = tele?.initData;
    
    if (!initData) return;

    const container = document.getElementById('friends-list-container');
    try {
        const res = await fetch('/api/friends/list', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData })
        });
        const data = await res.json();
        
        if (data.success) {
            if (data.friends.length === 0) {
                container.innerHTML = '<div class="empty-state">لم تقم بدعوة أي أصدقاء حتى الآن.</div>';
                return;
            }
            
            let html = '<ul class="friends-list">';
            data.friends.forEach(f => {
                let statusHtml = '';
                if (f.upgrades_count >= 3) {
                    statusHtml = `<span style="color: #2ecc71; font-size: 0.8rem;">نشط ✅</span>`;
                } else {
                    let req = 3 - f.upgrades_count;
                    statusHtml = `<span style="color: #f39c12; font-size: 0.8rem;">ينقصه ${req} ترقية ⏳</span>`;
                }
                
                html += `
                    <li class="friend-item">
                        <div class="friend-avatar">${f.name.charAt(0).toUpperCase()}</div>
                        <div class="friend-info">
                            <span class="friend-name">${f.name}</span>
                            <span class="friend-id">${statusHtml}</span>
                        </div>
                        <div class="friend-earn">+${Math.floor(f.generated).toLocaleString()} ZN</div>
                    </li>
                `;
            });
            html += '</ul>';
            container.innerHTML = html;
        } else {
            container.innerHTML = '<div class="empty-state">فشل في تحميل الأصدقاء.</div>';
        }
    } catch (e) {
        container.innerHTML = '<div class="empty-state">خطأ في الاتصال بالخادم.</div>';
    }
};

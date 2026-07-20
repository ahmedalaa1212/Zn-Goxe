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
        if (pData.pending_ref_earnings <= 0) {
            btnClaim.disabled = true;
            btnClaim.innerText = "لا توجد أرباح للسحب";
        } else {
            btnClaim.disabled = false;
            btnClaim.innerText = "سحب الأرباح الآن";
        }
    }

    // تأمين إنشاء الرابط 
    const linkInput = document.getElementById('ref-link-input');
    if (linkInput) {
        if (pData.tg_id) {
            linkInput.value = `https://t.me/${BOT_USERNAME}?start=ref_${pData.tg_id}`;
        } else {
            linkInput.value = "جاري التحميل...";
        }
    }

    renderRefTasks();
    if(typeof window.fetchAndRenderFriendsList === 'function') {
        window.fetchAndRenderFriendsList();
    }
};

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

window.copyRefLink = function() {
    const pData = window.PlayerData;
    let finalLink = "";
    
    // تأمين النسخ حتى لو مربع النص فيه مشكلة
    if (pData && pData.tg_id) {
        finalLink = `https://t.me/${BOT_USERNAME}?start=ref_${pData.tg_id}`;
    } else {
        const linkInput = document.getElementById('ref-link-input');
        if (!linkInput || !linkInput.value || linkInput.value.includes("جاري")) {
            alert("يرجى الانتظار حتى يتم تحميل الرابط الخاص بك.");
            return;
        }
        finalLink = linkInput.value;
    }
    
    navigator.clipboard.writeText(finalLink).then(() => {
        const tele = window.Telegram?.WebApp;
        if (tele && tele.showAlert) {
            tele.showAlert("تم نسخ الرابط بنجاح! 🚀 شاركه الآن.");
        } else {
            alert("تم نسخ الرابط بنجاح! 🚀");
        }
    }).catch(err => console.error('Error:', err));
};

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
            
            if(window.fetchPlayerDataFromServer) window.fetchPlayerDataFromServer();
        } else {
            alert(data.error || 'عذراً، لم تتمكن من استلام المكافأة.');
        }
    } catch (e) {
        alert('خطأ في الاتصال بالخادم.');
    }
};

if (window.PlayerData && window.PlayerData.tg_id) {
    window.updateFriendsUI();
}

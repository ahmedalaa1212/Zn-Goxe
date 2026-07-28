const REF_TASKS = [
    { id: 1, reqFriends: 1, reward: 5000 },
    { id: 2, reqFriends: 5, reward: 30000 },
    { id: 3, reqFriends: 10, reward: 75000 },
    { id: 4, reqFriends: 25, reward: 200000 },
    { id: 5, reqFriends: 50, reward: 500000 },
    { id: 6, reqFriends: 100, reward: 1500000 },
    { id: 7, reqFriends: 500, reward: 10000000 }
];

const BOT_USERNAME = "zngoxe_bot"; // يوزر البوت

document.addEventListener("DOMContentLoaded", async () => {
    const tele = window.Telegram?.WebApp;
    if (tele) {
        tele.ready();
        tele.expand();
    }
    
    const initData = tele?.initData;
    
    if (!initData) {
        document.getElementById('ref-link-input').value = "يرجى فتح التطبيق من داخل تليجرام";
        document.getElementById('friends-list-container').innerHTML = '<div class="empty-state">يرجى فتح التطبيق من تليجرام لعرض الأصدقاء.</div>';
        return;
    }

    // توليد الرابط فوراً لضمان عدم بقاء "جاري التحميل"
    let userId = "";
    try {
        if (tele?.initDataUnsafe?.user?.id) {
            userId = tele.initDataUnsafe.user.id;
        }
    } catch(e) { console.error("Error getting user ID:", e); }

    const refInput = document.getElementById('ref-link-input');
    if (userId) {
        refInput.value = `https://t.me/${BOT_USERNAME}?start=ref_${userId}`;
    } else {
        refInput.value = "حدث خطأ في توليد الرابط";
    }

    // جلب بيانات الرصيد والمهام من مسار الأصدقاء المستقل
    try {
        const response = await fetch('/api/friends/data', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData })
        });
        const data = await response.json();
        window.PlayerData = data.success ? data.player : {};
    } catch (error) {
        console.warn("Failed to fetch player data.");
        window.PlayerData = {}; 
    }

    updateFriendsUI();
    await fetchAndRenderFriendsList(initData);
});

function updateFriendsUI() {
    const pData = window.PlayerData || {};
    
    const pending = parseFloat(pData.pending_ref_earnings) || 0;
    const invited = parseInt(pData.invited_friends_count) || 0;
    const balance = parseFloat(pData.balance) || 0;

    document.getElementById('pending-ref-earnings').innerText = Math.floor(pending).toLocaleString();
    document.getElementById('invited-friends-count').innerText = invited.toLocaleString();
    document.getElementById('top-balance-friends').innerText = `ZN: ${Math.floor(balance).toLocaleString()}`;

    const btnClaim = document.getElementById('btn-claim-ref');
    if (pending <= 0) {
        btnClaim.disabled = true;
        btnClaim.innerText = "لا توجد أرباح للسحب";
    } else {
        btnClaim.disabled = false;
        btnClaim.innerText = "سحب الأرباح الآن";
    }

    renderRefTasks(invited, pData.claimed_ref_tasks || []);
}

function renderRefTasks(currentFriends, claimedTasks) {
    const listEl = document.getElementById('ref-tasks-list');
    if (!listEl) return;

    let html = '';
    REF_TASKS.forEach(task => {
        const isClaimed = claimedTasks.includes(task.id);
        const isReady = currentFriends >= task.reqFriends;
        let progressPercent = Math.min((currentFriends / task.reqFriends) * 100, 100);

        let btnHtml = '';
        if (isClaimed) {
            btnHtml = `<button disabled class="claimed-btn">✅ مستلمة</button>`;
        } else if (isReady) {
            btnHtml = `<button onclick="claimRefTask(${task.id}, ${task.reward}, ${task.reqFriends})" class="claim-btn" style="background: linear-gradient(45deg, #2ecc71, #27ae60); color: white;">🎁 استلام</button>`;
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
                    <div class="task-action">${btnHtml}</div>
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
    const link = document.getElementById('ref-link-input').value;
    if (link.includes("جاري") || link.includes("يرجى") || link.includes("خطأ")) return;
    
    navigator.clipboard.writeText(link).then(() => {
        window.Telegram?.WebApp?.showAlert("✅ تم نسخ الرابط بنجاح!");
    });
};

window.claimRefEarnings = async function() {
    const tele = window.Telegram?.WebApp;
    const initData = tele?.initData;
    if (!initData) return;

    const btn = document.getElementById('btn-claim-ref');
    btn.disabled = true;
    btn.innerText = "⏳ جاري السحب...";

    try {
        const res = await fetch('/api/friends/claim_ref_earnings', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData })
        });
        const data = await res.json();
        
        if (data.success) {
            tele.showAlert(`🎉 تم السحب بنجاح!\nأضيف ${Math.floor(data.net_amount).toLocaleString()} ZN إلى رصيدك.`);
            window.PlayerData.balance = data.new_balance;
            window.PlayerData.pending_ref_earnings = 0;
            updateFriendsUI();
        } else {
            tele.showAlert(data.error || "فشل السحب");
            btn.disabled = false;
            btn.innerText = "سحب الأرباح الآن";
        }
    } catch (e) {
        tele.showAlert('خطأ في الاتصال بالخادم.');
        btn.disabled = false;
        btn.innerText = "سحب الأرباح الآن";
    }
};

window.claimRefTask = async function(taskId, reward, reqFriends) {
    const tele = window.Telegram?.WebApp;
    const initData = tele?.initData;
    if (!initData) return;

    try {
        const res = await fetch('/api/friends/claim_ref_task', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData, taskId, reward, reqFriends })
        });
        const data = await res.json();
        
        if (data.success) {
            tele.showAlert(`🎊 مبروك! استلمت ${reward.toLocaleString()} ZN.`);
            window.PlayerData.balance = data.new_balance;
            if(!window.PlayerData.claimed_ref_tasks) window.PlayerData.claimed_ref_tasks = [];
            window.PlayerData.claimed_ref_tasks.push(taskId);
            updateFriendsUI();
        } else {
            tele.showAlert(data.error || "خطأ في الاستلام");
        }
    } catch (e) {
        tele.showAlert('خطأ في الاتصال بالخادم.');
    }
};

async function fetchAndRenderFriendsList(initData) {
    const container = document.getElementById('friends-list-container');
    try {
        const res = await fetch('/api/friends/list', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initData: initData })
        });
        const data = await res.json();
        
        if (data.success) {
            if (!data.friends || data.friends.length === 0) {
                container.innerHTML = '<div class="empty-state">لم تقم بدعوة أي أصدقاء حتى الآن.</div>';
                return;
            }
            
            let html = '<ul class="friends-list">';
            data.friends.forEach(f => {
                let statusHtml = f.upgrades_count >= 3 
                    ? `<span style="color: #2ecc71; font-size: 0.8rem;">نشط ✅</span>`
                    : `<span style="color: #f39c12; font-size: 0.8rem;">ينقصه ${3 - (f.upgrades_count || 0)} ترقية ⏳</span>`;
                
                html += `
                    <li class="friend-item">
                        <div class="friend-avatar">${(f.name || 'U').charAt(0).toUpperCase()}</div>
                        <div class="friend-info">
                            <span class="friend-name">${f.name || 'مستخدم مجهول'}</span>
                            <span class="friend-id">${statusHtml}</span>
                        </div>
                        <div class="friend-earn">+${Math.floor(f.generated || 0).toLocaleString()} ZN</div>
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
}

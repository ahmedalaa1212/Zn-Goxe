const REF_TASKS = [
    { id: 1, reqFriends: 1, reward: 5000 },
    { id: 2, reqFriends: 5, reward: 30000 },
    { id: 3, reqFriends: 10, reward: 75000 },
    { id: 4, reqFriends: 25, reward: 200000 },
    { id: 5, reqFriends: 50, reward: 500000 },
    { id: 6, reqFriends: 100, reward: 1500000 },
    { id: 7, reqFriends: 500, reward: 10000000 }
];

const BOT_USERNAME = "zngoxe_bot"; // يوزر البوت بدون @

// --- أدوات المزامنة الموحدة مع باقي الصفحات (localStorage) ---
function getStoredBalance() {
    const bal = localStorage.getItem('user_balance') || localStorage.getItem('zn_balance');
    return bal !== null ? parseFloat(bal) : null;
}

function setStoredBalance(newBalance) {
    if (newBalance !== undefined && newBalance !== null) {
        const strVal = newBalance.toString();
        localStorage.setItem('user_balance', strVal);
        localStorage.setItem('zn_balance', strVal);
    }
}

function initFriendsPage() {
    const tele = window.Telegram?.WebApp;
    if (tele) {
        tele.ready();
        tele.expand();
    }
    
    const initData = tele?.initData;
    const refInput = document.getElementById('ref-link-input');
    
    let userId = "0000";
    if (tele?.initDataUnsafe?.user?.id) {
        userId = tele.initDataUnsafe.user.id;
    }

    if (refInput) {
        if (!initData && userId === "0000") {
            refInput.value = "يرجى فتح التطبيق من داخل تليجرام";
        } else {
            refInput.value = `https://t.me/${BOT_USERNAME}?start=ref_${userId}`;
        }
    }

    // 1. عرض الرصيد المحفوظ محلياً فوراً (إن وجد) لعدم حدوث أي تأخير أو اختلاف
    const cachedBalance = getStoredBalance();
    if (cachedBalance !== null) {
        if (!window.PlayerData) window.PlayerData = {};
        window.PlayerData.balance = cachedBalance;
        updateFriendsUI();
    }

    const container = document.getElementById('friends-list-container');
    if (!initData) {
        if(container) container.innerHTML = '<div class="empty-state">يرجى فتح التطبيق من تليجرام لعرض الأصدقاء.</div>';
        return;
    }

    // 2. طلب أحدث البيانات من السيرفر ومزامنتها
    loadFriendsData(initData);
}

async function loadFriendsData(initData) {
    try {
        const response = await fetch('/api/friends/data', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${initData}`
            },
            body: JSON.stringify({ initData: initData })
        });
        const data = await response.json();
        if (data.success && data.player) {
            window.PlayerData = data.player;
            // حفظ الرصيد الجاي من السيرفر في المخزن المحلي الموحد
            setStoredBalance(data.player.balance);
        }
    } catch (error) {
        console.warn("Failed to fetch player data.");
    }

    updateFriendsUI();
    await fetchAndRenderFriendsList(initData);
}

function updateFriendsUI() {
    const pData = window.PlayerData || {};
    
    // إذا كان هناك رصيد في المخزن المحلي أحدث، نعتمد عليه
    const localBal = getStoredBalance();
    const balance = localBal !== null ? localBal : (parseFloat(pData.balance) || 0);
    
    const pending = parseFloat(pData.pending_ref_earnings) || 0;
    const totalInvited = parseInt(pData.invited_friends_count) || 0;
    const eligibleForTasks = parseInt(pData.eligible_task_friends_count) || 0;

    const elPending = document.getElementById('pending-ref-earnings');
    const elInvited = document.getElementById('invited-friends-count');
    const elBalance = document.getElementById('top-balance-friends');
    const btnClaim = document.getElementById('btn-claim-ref');

    if(elPending) elPending.innerText = Math.floor(pending).toLocaleString();
    if(elInvited) elInvited.innerText = totalInvited.toLocaleString();
    if(elBalance) elBalance.innerText = `ZN: ${Math.floor(balance).toLocaleString()}`;

    if(btnClaim) {
        if (pending <= 0) {
            btnClaim.disabled = true;
            btnClaim.innerText = "لا توجد أرباح للسحب";
        } else {
            btnClaim.disabled = false;
            btnClaim.innerText = "سحب الأرباح الآن";
        }
    }

    renderRefTasks(eligibleForTasks, pData.claimed_ref_tasks || []);
}

function renderRefTasks(eligibleFriendsCount, claimedTasks) {
    const listEl = document.getElementById('ref-tasks-list');
    if (!listEl) return;

    let html = '';
    REF_TASKS.forEach(task => {
        const isClaimed = claimedTasks.includes(task.id);
        const isReady = eligibleFriendsCount >= task.reqFriends;
        let progressPercent = Math.min((eligibleFriendsCount / task.reqFriends) * 100, 100);

        let btnHtml = '';
        if (isClaimed) {
            btnHtml = `<button disabled class="claimed-btn">✅ مستلمة</button>`;
        } else if (isReady) {
            btnHtml = `<button onclick="claimRefTask(${task.id}, ${task.reward}, ${task.reqFriends})" class="claim-btn" style="background: linear-gradient(45deg, #2ecc71, #27ae60); color: white;">🎁 استلام</button>`;
        } else {
            let remaining = task.reqFriends - eligibleFriendsCount;
            btnHtml = `<button disabled class="locked-btn">🔒 باقي ${remaining}</button>`;
        }

        html += `
            <li class="task-item">
                <div class="task-header">
                    <div class="task-info">
                        <h4>دعوة ${task.reqFriends} أصدقاء (3+ ترقيات)</h4>
                        <p>مكافأة: ${task.reward.toLocaleString()} ZN</p>
                    </div>
                    <div class="task-action">${btnHtml}</div>
                </div>
                <div class="progress-container">
                    <div class="progress-bar" style="width: ${progressPercent}%;"></div>
                </div>
                <div class="task-footer">
                    <span>مؤهلين: ${eligibleFriendsCount} / ${task.reqFriends}</span>
                    <span>${Math.floor(progressPercent)}%</span>
                </div>
            </li>
        `;
    });
    listEl.innerHTML = html;
}

window.copyRefLink = function() {
    const refInput = document.getElementById('ref-link-input');
    if(!refInput) return;
    
    const link = refInput.value;
    if (!link || link.includes("جاري") || link.includes("يرجى")) return;
    
    navigator.clipboard.writeText(link).then(() => {
        window.Telegram?.WebApp?.showAlert("✅ تم نسخ الرابط بنجاح!");
    });
};

window.claimRefEarnings = async function() {
    const tele = window.Telegram?.WebApp;
    const initData = tele?.initData;
    if (!initData) return;

    const btn = document.getElementById('btn-claim-ref');
    if(btn) {
        btn.disabled = true;
        btn.innerText = "⏳ جاري السحب...";
    }

    try {
        const res = await fetch('/api/friends/claim_ref_earnings', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${initData}`
            },
            body: JSON.stringify({ initData: initData })
        });
        const data = await res.json();
        
        if (data.success) {
            tele.showAlert(`🎉 تم السحب بنجاح!\nأضيف ${Math.floor(data.net_amount).toLocaleString()} ZN إلى رصيدك.`);
            
            // تحديث الـ LocalStorage والذاكرة بالرصيد الجديد لترُى في باقي الصفحات فوراً
            setStoredBalance(data.new_balance);
            if (!window.PlayerData) window.PlayerData = {};
            window.PlayerData.balance = data.new_balance;
            window.PlayerData.pending_ref_earnings = 0;
            
            updateFriendsUI();
        } else {
            tele.showAlert(data.error || "فشل السحب");
            if(btn) {
                btn.disabled = false;
                btn.innerText = "سحب الأرباح الآن";
            }
        }
    } catch (e) {
        tele.showAlert('خطأ في الاتصال بالخادم.');
        if(btn) {
            btn.disabled = false;
            btn.innerText = "سحب الأرباح الآن";
        }
    }
};

window.claimRefTask = async function(taskId, reward, reqFriends) {
    const tele = window.Telegram?.WebApp;
    const initData = tele?.initData;
    if (!initData) return;

    try {
        const res = await fetch('/api/friends/claim_ref_task', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${initData}`
            },
            body: JSON.stringify({ initData, taskId, reward, reqFriends })
        });
        const data = await res.json();
        
        if (data.success) {
            tele.showAlert(`🎊 مبروك! استلمت ${reward.toLocaleString()} ZN.`);
            
            // تحديث الـ LocalStorage والذاكرة بالرصيد الجديد لترُى في المزرعة وباقي الصفحات
            setStoredBalance(data.new_balance);
            if (!window.PlayerData) window.PlayerData = {};
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
    if(!container) return;

    try {
        const res = await fetch('/api/friends/list', {
            method: 'POST',
            headers: { 
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${initData}`
            },
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
                const cnt = f.upgrades_count || 0;
                let statusHtml = cnt >= 3 
                    ? `<span style="color: #2ecc71; font-size: 0.8rem;">مؤهل للمهام (${cnt}/3 ترقيات) ✅</span>`
                    : `<span style="color: #f39c12; font-size: 0.8rem;">ينقصه ${3 - cnt} ترقية (${cnt}/3 ترقيات) ⏳</span>`;
                
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

// إعادة تحديث الواجهة فوراً عند العودة للصفحة من أي صفحة أخرى
window.addEventListener('pageshow', function() {
    const stored = getStoredBalance();
    if (stored !== null) {
        if (!window.PlayerData) window.PlayerData = {};
        window.PlayerData.balance = stored;
        updateFriendsUI();
    }
});

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initFriendsPage);
} else {
    initFriendsPage();
}

(function initFriendsModule() {
    const REF_TASKS = [
        { id: 1, reqFriends: 1, reward: 5000 },
        { id: 2, reqFriends: 5, reward: 30000 },
        { id: 3, reqFriends: 10, reward: 75000 },
        { id: 4, reqFriends: 25, reward: 200000 },
        { id: 5, reqFriends: 50, reward: 500000 },
        { id: 6, reqFriends: 100, reward: 1500000 },
        { id: 7, reqFriends: 500, reward: 10000000 }
    ];

    const BOT_USERNAME = "zngoxe_bot"; // اسم يوزر البوت بدون @

    // جلب الرصيد مباشرة من الـ Proxy المركزي الموحد مع التخلص التام من الكسور
    function getStoredBalance() {
        let bal = 0;
        if (window.userState && window.userState.balance !== undefined) {
            bal = parseFloat(window.userState.balance);
        } else if (window.PlayerData && window.PlayerData.balance !== undefined) {
            bal = parseFloat(window.PlayerData.balance);
        }
        return Math.floor(bal || 0);
    }

    // تحديث الرصيد عبر الـ Proxy المركزي لتحديث كافة القوائم فوراً وبدون كسور
    function setStoredBalance(newBalance) {
        if (newBalance !== undefined && newBalance !== null) {
            const numVal = Math.floor(parseFloat(newBalance) || 0);
            if (window.userState) {
                window.userState.balance = numVal;
            }
            if (window.PlayerData) {
                window.PlayerData.balance = numVal;
            }
        }
    }

    function showToast(message) {
        const tele = window.Telegram?.WebApp;
        if (tele && tele.showAlert) {
            tele.showAlert(message);
        } else {
            alert(message);
        }
    }

    function initFriendsPage() {
        const tele = window.Telegram?.WebApp;
        if (tele) {
            tele.ready();
            tele.expand();
        }
        
        const refInput = document.getElementById('ref-link-input');
        
        let userId = "0000";
        if (tele?.initDataUnsafe?.user?.id) {
            userId = tele.initDataUnsafe.user.id;
        }

        if (refInput) {
            if (!tele?.initData && userId === "0000") {
                refInput.value = "يرجى فتح التطبيق من داخل تليجرام";
            } else {
                refInput.value = `https://t.me/${BOT_USERNAME}?start=ref_${userId}`;
            }
        }

        // تهيئة الكائن المحلي
        if (!window.PlayerData) window.PlayerData = {};
        window.PlayerData.balance = getStoredBalance();
        
        window.updateFriendsUI();

        if (!tele?.initData) {
            const container = document.getElementById('friends-list-container');
            if (container) container.innerHTML = '<div class="empty-state">يرجى فتح التطبيق من تليجرام لعرض الأصدقاء.</div>';
            return;
        }

        // جلب أحدث البيانات من الخادم عبر fetchAPI الآمن من game.js
        loadFriendsData();
    }

    async function loadFriendsData() {
        try {
            const data = await window.fetchAPI('/api/friends/data', 'POST', {});
            if (data && data.success && data.player) {
                window.PlayerData = { ...window.PlayerData, ...data.player };
                if (data.player.balance !== undefined) {
                    setStoredBalance(data.player.balance);
                }
            }
        } catch (error) {
            console.warn("فشل في جلب بيانات الأصدقاء من الخادم:", error);
        }

        window.updateFriendsUI();
        await fetchAndRenderFriendsList();
    }

    // الخطاف المطلوب لتحديث واجهة الأصدقاء وتوافقه مع الـ Proxy
    window.updateFriendsUI = function() {
        const pData = window.PlayerData || {};
        
        const balance = getStoredBalance();
        if (window.PlayerData) window.PlayerData.balance = balance;
        
        const pending = parseFloat(pData.pending_ref_earnings) || 0;
        const totalInvited = parseInt(pData.invited_friends_count) || 0;
        const eligibleForTasks = parseInt(pData.eligible_task_friends_count) || 0;

        // 🔥 الحل الجذري: ربط وتحديث عنصر الرصيد في أعلى صفحة الأصدقاء لحظياً وبدون كسور
        const elBalance = document.getElementById('top-balance-friends') || document.querySelector('.zn-balance-display');
        if (elBalance) {
            elBalance.innerText = balance.toLocaleString();
        }

        const elPending = document.getElementById('pending-ref-earnings');
        const elInvited = document.getElementById('invited-friends-count');
        const btnClaim = document.getElementById('btn-claim-ref');

        if (elPending) elPending.innerText = Math.floor(pending).toLocaleString();
        if (elInvited) elInvited.innerText = totalInvited.toLocaleString();

        if (btnClaim) {
            if (pending <= 0) {
                btnClaim.disabled = true;
                btnClaim.style.opacity = "0.6";
                btnClaim.innerText = "لا توجد أرباح للسحب";
            } else {
                btnClaim.disabled = false;
                btnClaim.style.opacity = "1";
                btnClaim.innerText = "سحب الأرباح الآن 💰";
            }
        }

        renderRefTasks(eligibleForTasks, pData.claimed_ref_tasks || []);
    };

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
                btnHtml = `<button onclick="claimRefTask(${task.id}, ${task.reward}, ${task.reqFriends})" class="claim-btn" style="background: linear-gradient(45deg, #2ecc71, #27ae60); color: white; cursor: pointer;">🎁 استلام</button>`;
            } else {
                let remaining = task.reqFriends - eligibleFriendsCount;
                btnHtml = `<button disabled class="locked-btn">🔒 باقي ${remaining}</button>`;
            }

            html += `
                <li class="task-item">
                    <div class="task-header">
                        <div class="task-info">
                            <h4>دعوة ${task.reqFriends} أصدقاء (3+ ترقيات)</h4>
                            <p>مكافأة: ${Math.floor(task.reward).toLocaleString()} ZN</p>
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
        if (!refInput) return;
        
        const link = refInput.value;
        if (!link || link.includes("جاري") || link.includes("يرجى")) return;
        
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(link).then(() => {
                showToast("✅ تم نسخ رابط الدعوة بنجاح!");
            }).catch(() => fallbackCopy(refInput));
        } else {
            fallbackCopy(refInput);
        }
    };

    window.shareRefLink = function() {
        const refInput = document.getElementById('ref-link-input');
        if (!refInput) return;
        
        const link = refInput.value;
        if (!link || link.includes("جاري") || link.includes("يرجى")) return;

        const shareText = "انضم إلي في لعبة Zn Goxe واحصل على مكافآت تعدين مجانية! 🪙🚀";
        const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(shareText)}`;

        const tele = window.Telegram?.WebApp;
        if (tele && typeof tele.openTelegramLink === 'function') {
            tele.openTelegramLink(shareUrl);
        } else {
            window.open(shareUrl, '_blank');
        }
    };

    function fallbackCopy(inputEl) {
        inputEl.select();
        inputEl.setSelectionRange(0, 99999);
        document.execCommand("copy");
        showToast("✅ تم نسخ رابط الدعوة بنجاح!");
    }

    window.claimRefEarnings = async function() {
        const btn = document.getElementById('btn-claim-ref');
        if (btn) {
            btn.disabled = true;
            btn.innerText = "⏳ جاري السحب...";
        }

        try {
            const data = await window.fetchAPI('/api/friends/claim_ref_earnings', 'POST', {});
            if (data && data.success) {
                showToast(`🎉 تم السحب بنجاح!\nأُضيف ${Math.floor(data.net_amount).toLocaleString()} ZN إلى رصيدك.`);
                
                // التحديث هنا سيُفعّل الـ Proxy في game.js لتحديث الرصيد لحظياً في كل التطبيق
                setStoredBalance(data.new_balance);
                if (!window.PlayerData) window.PlayerData = {};
                window.PlayerData.balance = Math.floor(data.new_balance);
                window.PlayerData.pending_ref_earnings = 0;
                
                window.updateFriendsUI();
            } else {
                showToast(data.error || "فشل السحب");
                if (btn) {
                    btn.disabled = false;
                    btn.innerText = "سحب الأرباح الآن 💰";
                }
            }
        } catch (e) {
            showToast(e.message || 'خطأ في الاتصال بالخادم.');
            if (btn) {
                btn.disabled = false;
                btn.innerText = "سحب الأرباح الآن 💰";
            }
        }
    };

    window.claimRefTask = async function(taskId, reward, reqFriends) {
        try {
            const data = await window.fetchAPI('/api/friends/claim_ref_task', 'POST', { taskId, reward, reqFriends });
            if (data && data.success) {
                showToast(`🎊 مبروك! استلمت مكافأة ${Math.floor(reward).toLocaleString()} ZN.`);
                
                // التحديث اللحظي للواجهات
                setStoredBalance(data.new_balance);
                if (!window.PlayerData) window.PlayerData = {};
                window.PlayerData.balance = Math.floor(data.new_balance);
                if (!window.PlayerData.claimed_ref_tasks) window.PlayerData.claimed_ref_tasks = [];
                window.PlayerData.claimed_ref_tasks.push(taskId);
                
                window.updateFriendsUI();
            } else {
                showToast(data.error || "خطأ في استلام المكافأة");
            }
        } catch (e) {
            showToast(e.message || 'خطأ في الاتصال بالخادم.');
        }
    };

    async function fetchAndRenderFriendsList() {
        const container = document.getElementById('friends-list-container');
        if (!container) return;

        try {
            const data = await window.fetchAPI('/api/friends/list', 'POST', {});
            if (data && data.success) {
                if (!data.friends || data.friends.length === 0) {
                    container.innerHTML = '<div class="empty-state">لم تقم بدعوة أي أصدقاء حتى الآن.</div>';
                    return;
                }
                
                let html = '<ul class="friends-list">';
                data.friends.forEach(f => {
                    const cnt = f.upgrades_count || 0;
                    let statusHtml = cnt >= 3 
                        ? `<span style="color: #2ecc71;">مؤهل للمهام (${cnt}/3 ترقيات) ✅</span>`
                        : `<span style="color: #f39c12;">ينقصه ${3 - cnt} ترقية (${cnt}/3) ⏳</span>`;
                    
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

    // الاستماع لتغيرات الحالة العامة من أي قائمة أخرى عبر الـ Proxy
    window.addEventListener('userStateUpdated', (e) => {
        if (e.detail && e.detail.prop === 'balance') {
            window.updateFriendsUI();
        }
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initFriendsPage);
    } else {
        initFriendsPage();
    }
})();


// friends/friends.js
(function initFriendsModule() {
    const tele = window.Telegram?.WebApp;
    const INIT_DATA = tele?.initData || "";

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

    // --- أدوات المزامنة الموحدة والمطابقة تماماً لكود المزرعة ---
    function getStoredBalance() {
        if (window.GameState && window.GameState.balance !== undefined && window.GameState.balance !== null) {
            return parseFloat(window.GameState.balance);
        }
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        return bal !== null ? parseFloat(bal) : 0;
    }

    function setStoredBalance(newBalance) {
        if (newBalance !== undefined && newBalance !== null) {
            const numVal = parseFloat(newBalance);
            if (typeof window.setBalance === 'function') {
                window.setBalance(numVal);
            } else {
                if (!window.GameState) window.GameState = {};
                window.GameState.balance = numVal;
                localStorage.setItem('zn_balance', numVal.toString());
                localStorage.setItem('user_balance', numVal.toString());
            }
        }
    }

    function showToast(message) {
        if (tele && tele.showAlert) {
            tele.showAlert(message);
        } else {
            alert(message);
        }
    }

    function initFriendsPage() {
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
            if (!INIT_DATA && userId === "0000") {
                refInput.value = "يرجى فتح التطبيق من داخل تليجرام";
            } else {
                refInput.value = `https://t.me/${BOT_USERNAME}?start=ref_${userId}`;
            }
        }

        // تهيئة البيانات المحلية فوراً من الكاش لمنع التصفير لقيمة 8000
        const cachedBal = getStoredBalance();
        window.PlayerData = { balance: cachedBal, pending_ref_earnings: 0, invited_friends_count: 0 };
        
        window.updateFriendsUI();

        if (!INIT_DATA) {
            const container = document.getElementById('friends-list-container');
            if (container) container.innerHTML = '<div class="empty-state">يرجى فتح التطبيق من تليجرام لعرض الأصدقاء.</div>';
            return;
        }

        loadFriendsData();
    }

    // جلب بيانات الأصدقاء مع إرسال التوثيق الآمن في البودي
    async function loadFriendsData() {
        if (!INIT_DATA) return;
        try {
            let response = await fetch('/api/friends/data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: INIT_DATA })
            });
            let data = await response.json();
            
            if (response.ok && data.success && data.player) {
                window.PlayerData = { ...window.PlayerData, ...data.player };
                if (data.player.balance !== undefined) {
                    setStoredBalance(data.player.balance);
                }
            }
        } catch (error) {
            console.error("فشل في جلب بيانات الأصدقاء:", error);
        }

        window.updateFriendsUI();
        await fetchAndRenderFriendsList();
    }

    // تحديث الواجهة وتوحيد عناصر الرصيد مع المزرعة والأصدقاء
    window.updateFriendsUI = function() {
        const pData = window.PlayerData || {};
        let balance = getStoredBalance();
        
        if (window.PlayerData) window.PlayerData.balance = balance;
        
        let pending = parseFloat(pData.pending_ref_earnings || 0);
        let totalInvited = parseInt(pData.invited_friends_count || 0);
        let eligibleForTasks = parseInt(pData.eligible_task_friends_count || 0);

        // تحديث كل عناصر الرصيد اللي تحمل كلاس المزرعة أو الأصدقاء
        const elBalances = document.querySelectorAll('.zn-balance-display, #top-balance-friends, #farm-balance');
        elBalances.forEach(el => {
            if (el.id === 'farm-balance' || el.innerText.includes('ZN')) {
                el.innerText = `ZN: ${Math.floor(balance).toLocaleString()}`;
            } else {
                el.innerText = Math.floor(balance).toLocaleString();
            }
        });

        const elPending = document.getElementById('pending-ref-earnings');
        const elInvited = document.getElementById('invited-friends-count');
        const btnClaim = document.getElementById('btn-claim-ref');

        if (elPending) elPending.innerText = Math.floor(pending).toLocaleString();
        if (elInvited) elInvited.innerText = totalInvited.toLocaleString();

        if (btnClaim) {
            if (pending <= 0) {
                btnClaim.disabled = true;
                btnClaim.className = "btn-cooldown";
                btnClaim.style.background = "#333";
                btnClaim.innerText = "لا توجد أرباح للسحب";
            } else {
                btnClaim.disabled = false;
                btnClaim.className = "btn-ready";
                btnClaim.style.background = "linear-gradient(45deg, #2ecc71, #27ae60)";
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
                btnHtml = `<button disabled style="background:#333; color:#777; border:none; padding:6px 10px; border-radius:6px; font-size:11px;">✅ مستلمة</button>`;
            } else if (isReady) {
                btnHtml = `<button onclick="claimRefTask(${task.id}, ${task.reward}, ${task.reqFriends})" style="background: linear-gradient(45deg, #2ecc71, #27ae60); color: white; border:none; padding:6px 10px; border-radius:6px; font-size:11px; cursor: pointer; font-weight:bold;">🎁 استلام</button>`;
            } else {
                let remaining = task.reqFriends - eligibleFriendsCount;
                btnHtml = `<button disabled style="background:#222; color:#555; border:1px solid #333; padding:6px 10px; border-radius:6px; font-size:11px;">🔒 باقي ${remaining}</button>`;
            }

            html += `
                <li style="background:#1a1a1a; border:1px solid #333; border-radius:12px; padding:12px; margin-bottom:10px; list-style:none; direction:rtl;">
                    <div style="display:flex; justify-content:between; align-items:center; display:-webkit-box; display:-webkit-flex; justify-content:space-between;">
                        <div>
                            <h4 style="margin:0; color:#fff; font-size:13px;">دعوة ${task.reqFriends} أصدقاء (3+ ترقيات)</h4>
                            <p style="margin:4px 0 0 0; color:#f39c12; font-size:11px; font-weight:bold;">مكافأة: ${Math.floor(task.reward).toLocaleString()} ZN</p>
                        </div>
                        <div>${btnHtml}</div>
                    </div>
                    <div style="width:100%; background:#222; height:6px; border-radius:4px; overflow:hidden; margin-top:8px;">
                        <div style="width:${progressPercent}%; height:100%; background:#f39c12;"></div>
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
        if (!link || link.includes("يرجى")) return;
        
        navigator.clipboard.writeText(link).then(() => {
            showToast("✅ تم نسخ رابط الدعوة بنجاح!");
        }).catch(() => {
            refInput.select();
            document.execCommand("copy");
            showToast("✅ تم نسخ رابط الدعوة بنجاح!");
        });
    };

    window.shareRefLink = function() {
        const refInput = document.getElementById('ref-link-input');
        if (!refInput) return;
        const link = refInput.value;
        if (!link || link.includes("يرجى")) return;

        const shareText = "انضم إلي في لعبة Zn Goxe واحصل على مكافآت تعدين مجانية! 🪙🚀";
        const shareUrl = `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(shareText)}`;

        if (tele && typeof tele.openTelegramLink === 'function') {
            tele.openTelegramLink(shareUrl);
        } else {
            window.open(shareUrl, '_blank');
        }
    };

    // عملية سحب الأرباح مع إرسال توثيق initData لحل مشكلة فشل السحب
    window.claimRefEarnings = async function() {
        if (!INIT_DATA) return;
        const btn = document.getElementById('btn-claim-ref');
        if (btn) {
            btn.disabled = true;
            btn.innerText = "⏳ جاري السحب...";
        }

        try {
            let response = await fetch('/api/friends/claim_ref_earnings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: INIT_DATA })
            });
            let data = await response.json();
            
            if (response.ok && data.success) {
                showToast(`🎉 تم السحب بنجاح!\nأُضيف ${Math.floor(data.net_amount).toLocaleString()} ZN إلى رصيدك.`);
                
                setStoredBalance(data.new_balance);
                if (!window.PlayerData) window.PlayerData = {};
                window.PlayerData.balance = Math.floor(data.new_balance);
                window.PlayerData.pending_ref_earnings = 0;
                
                window.updateFriendsUI();
            } else {
                showToast(data.error || "فشل السحب من السيرفر");
                window.updateFriendsUI();
            }
        } catch (e) {
            showToast("حدث خطأ أثناء الاتصال بالسيرفر.");
            window.updateFriendsUI();
        }
    };

    // استلام مهمة الأصدقاء مع إرسال توثيق initData
    window.claimRefTask = async function(taskId, reward, reqFriends) {
        if (!INIT_DATA) return;
        try {
            let response = await fetch('/api/friends/claim_ref_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: INIT_DATA, taskId, reward, reqFriends })
            });
            let data = await response.json();

            if (response.ok && data.success) {
                showToast(`🎊 مبروك! استلمت مكافأة ${Math.floor(reward).toLocaleString()} ZN.`);
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
            showToast("خطأ في الاتصال بالخادم.");
        }
    };

    async function fetchAndRenderFriendsList() {
        const container = document.getElementById('friends-list-container');
        if (!container || !INIT_DATA) return;

        try {
            let response = await fetch('/api/friends/list', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: INIT_DATA })
            });
            let data = await response.json();

            if (response.ok && data.success) {
                if (!data.friends || data.friends.length === 0) {
                    container.innerHTML = '<div class="empty-state" style="text-align:center; color:#777; padding:20px;">لم تقم بدعوة أي أصدقاء حتى الآن.</div>';
                    return;
                }
                
                let html = '<ul style="padding:0; margin:0;">';
                data.friends.forEach(f => {
                    const cnt = f.upgrades_count || 0;
                    let statusHtml = cnt >= 3 
                        ? `<span style="color: #2ecc71; font-size:11px;">مؤهل للمهام (${cnt}/3 ترقيات) ✅</span>`
                        : `<span style="color: #f39c12; font-size:11px;">ينقصه ${3 - cnt} ترقية (${cnt}/3) ⏳</span>`;
                    
                    html += `
                        <li style="display:flex; justify-content:space-between; align-items:center; background:#1a1a1a; padding:10px; border-radius:10px; margin-bottom:8px; border:1px solid #333;">
                            <div style="display:flex; align-items:center; gap:10px;">
                                <div style="width:35px; height:35px; background:#f39c12; border-radius:50%; display:flex; align-items:center; justify-content:center; color:#000; font-weight:bold;">${(f.name || 'U').charAt(0).toUpperCase()}</div>
                                <div style="display:flex; flex-direction:column;">
                                    <span style="color:#fff; font-size:13px; font-weight:bold;">${f.name || 'مستخدم مجهول'}</span>
                                    ${statusHtml}
                                </div>
                            </div>
                            <div style="color:#2ecc71; font-weight:bold; font-size:13px;">+${Math.floor(f.generated || 0).toLocaleString()} ZN</div>
                        </li>
                    `;
                });
                html += '</ul>';
                container.innerHTML = html;
            } else {
                container.innerHTML = '<div class="empty-state" style="text-align:center; color:#777;">فشل في تحميل قائمة الأصدقاء.</div>';
            }
        } catch (e) {
            container.innerHTML = '<div class="empty-state" style="text-align:center; color:#777;">خطأ في الاتصال بالخادم.</div>';
        }
    }

    // --- التايمر السحري للمزامنة اللحظية الفائقة والربط بين القوائم بدون ريفريش ---
    setInterval(() => {
        const cachedBal = getStoredBalance();
        // إذا اختلف الرصيد في الكاش المحلي عن الرصيد الحالي المسجل بالواجهة، يتم التحديث فوراً
        if (window.PlayerData && Math.floor(window.PlayerData.balance) !== Math.floor(cachedBal)) {
            window.PlayerData.balance = cachedBal;
            if (typeof window.updateFriendsUI === 'function') {
                window.updateFriendsUI();
            }
        }
    }, 1000); // يفحص كل 1 ثانية لمزامنة فائقة السرعة

    // المزامنة عند التبديل التقليدي بين النوافذ
    window.addEventListener('pageshow', () => {
        const stored = getStoredBalance();
        if (window.PlayerData) window.PlayerData.balance = stored;
        window.updateFriendsUI();
        loadFriendsData();
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            const stored = getStoredBalance();
            if (window.PlayerData) window.PlayerData.balance = stored;
            window.updateFriendsUI();
            loadFriendsData();
        }
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initFriendsPage);
    } else {
        initFriendsPage();
    }
})();

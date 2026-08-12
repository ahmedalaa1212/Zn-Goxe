// friends/friends.js
(function initFriendsModule() {
    const tele = window.Telegram?.WebApp;
    const INIT_DATA = tele?.initData || "";
    const BOT_USERNAME = "zngoxe_bot";

    let lastFetchTimestamp = 0;
    const FETCH_COOLDOWN_MS = 3000;
    let isTaskClaiming = false;

    window.FriendsConfig = {
        min_upgrades_for_task: 3,
        commission_percent: 10,
        claim_fee_percent: 1.5,
        ref_tasks: {}
    };

    function getUserId() {
        if (tele?.initDataUnsafe?.user?.id) {
            return String(tele.initDataUnsafe.user.id);
        }
        return "0000";
    }

    function formatNumber(num, maxDecimals = 2) {
        const val = parseFloat(num) || 0;
        if (Number.isInteger(val)) {
            return val.toLocaleString();
        }
        return val.toLocaleString(undefined, {
            minimumFractionDigits: 0,
            maximumFractionDigits: maxDecimals
        });
    }

    function getStoredBalance() {
        if (window.userState && window.userState.balance !== undefined && window.userState.balance !== null && !isNaN(window.userState.balance)) {
            return parseFloat(window.userState.balance);
        }
        if (window.PlayerData && window.PlayerData.balance !== undefined && window.PlayerData.balance !== null && !isNaN(window.PlayerData.balance)) {
            return parseFloat(window.PlayerData.balance);
        }
        if (window.GameState && window.GameState.balance !== undefined && window.GameState.balance !== null && !isNaN(window.GameState.balance)) {
            return parseFloat(window.GameState.balance);
        }
        const bal = localStorage.getItem('zn_balance') || localStorage.getItem('user_balance');
        return bal !== null ? parseFloat(bal) : 0;
    }

    function setStoredBalance(newBalance) {
        if (newBalance === undefined || newBalance === null || isNaN(newBalance)) return;
        const numVal = parseFloat(newBalance);
        const currentVal = getStoredBalance();

        if (window.userState) {
            window.userState.balance = numVal;
        }

        if (!window.PlayerData) window.PlayerData = {};
        window.PlayerData.balance = numVal;

        if (!window.GameState) window.GameState = {};
        window.GameState.balance = numVal;

        localStorage.setItem('zn_balance', numVal.toString());
        localStorage.setItem('user_balance', numVal.toString());

        if (typeof window.animateBalance === 'function' && currentVal !== numVal) {
            window.animateBalance(currentVal, numVal);
        } else if (typeof window.setBalance === 'function') {
            window.setBalance(numVal);
        }

        if (typeof window.updateUI === 'function') {
            window.updateUI();
        }
    }

    function showToast(message) {
        if (tele && tele.showAlert) {
            tele.showAlert(message);
        } else {
            alert(message);
        }
    }

    function updateDynamicTextsFromConfig() {
        const cfg = window.FriendsConfig || {};
        
        const elComm = document.getElementById('info-comm-percent');
        if (elComm && cfg.commission_percent !== undefined) {
            elComm.innerText = `${cfg.commission_percent}%`;
        }

        const elUpgrades = document.getElementById('info-min-upgrades');
        if (elUpgrades && cfg.min_upgrades_for_task !== undefined) {
            elUpgrades.innerText = `${cfg.min_upgrades_for_task} ترقيات`;
        }

        const elFee = document.getElementById('info-claim-fee');
        if (elFee && cfg.claim_fee_percent !== undefined) {
            elFee.innerText = `${cfg.claim_fee_percent}%`;
        }
    }

    function initFriendsPage() {
        if (tele) {
            tele.ready();
            tele.expand();
        }
        
        const refInput = document.getElementById('ref-link-input');
        const userId = getUserId();

        if (refInput) {
            if (!INIT_DATA && userId === "0000") {
                refInput.value = "يرجى فتح التطبيق من داخل تليجرام";
            } else {
                refInput.value = `https://t.me/${BOT_USERNAME}?start=ref_${userId}`;
            }
        }

        const cachedBal = getStoredBalance();
        window.PlayerData = { balance: cachedBal, pending_ref_earnings: 0, total_ref_earnings: 0, invited_friends_count: 0, ...window.PlayerData };
        
        window.updateFriendsUI();

        if (!INIT_DATA && userId === "0000") {
            const container = document.getElementById('friends-list-container');
            if (container) container.innerHTML = '<div class="empty-state">يرجى فتح التطبيق من تليجرام لعرض الأصدقاء.</div>';
            return;
        }

        loadFriendsData();
    }

    async function loadFriendsData(force = false) {
        const userId = getUserId();
        if (!INIT_DATA && userId === "0000") return;

        const now = Date.now();
        if (!force && (now - lastFetchTimestamp < FETCH_COOLDOWN_MS)) {
            window.updateFriendsUI();
            return;
        }

        lastFetchTimestamp = now;

        try {
            let response = await fetch('/api/friends/data', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: INIT_DATA, user_id: userId })
            });
            let data = await response.json();
            
            if (response.ok && data.success && data.player) {
                window.PlayerData = { ...window.PlayerData, ...data.player };
                if (data.friends_config) {
                    window.FriendsConfig = data.friends_config;
                }
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

    window.updateFriendsUI = function() {
        const pData = window.PlayerData || {};
        let balance = getStoredBalance();
        
        if (window.PlayerData) window.PlayerData.balance = balance;
        if (window.userState) window.userState.balance = balance;
        
        let pending = parseFloat(pData.pending_ref_earnings || 0);
        let totalEarnings = parseFloat(pData.total_ref_earnings || 0);
        let totalInvited = parseInt(pData.invited_friends_count || 0);
        let eligibleForTasks = parseInt(pData.eligible_task_friends_count || 0);

        const elBalances = document.querySelectorAll('.zn-balance-display, #top-balance-friends, #farm-balance');
        elBalances.forEach(el => {
            if (el.id === 'farm-balance' || el.innerText.includes('ZN')) {
                el.innerText = `ZN: ${formatNumber(balance, 2)}`;
            } else {
                el.innerText = formatNumber(balance, 2);
            }
        });

        const elPending = document.getElementById('pending-ref-earnings');
        const elTotal = document.getElementById('total-ref-earnings');
        const elInvited = document.getElementById('invited-friends-count');
        const btnClaim = document.getElementById('btn-claim-ref');

        if (elPending) elPending.innerText = formatNumber(pending, 2);
        if (elTotal) elTotal.innerText = formatNumber(totalEarnings, 2);
        if (elInvited) elInvited.innerText = totalInvited.toLocaleString();

        if (btnClaim) {
            if (pending <= 0) {
                btnClaim.disabled = true;
                btnClaim.style.background = "#222226";
                btnClaim.style.color = "#666666";
                btnClaim.innerText = "لا توجد أرباح للسحب";
            } else {
                btnClaim.disabled = false;
                btnClaim.style.background = "#2ecc71";
                btnClaim.style.color = "#000000";
                btnClaim.innerText = "سحب الأرباح الآن 💰";
            }
        }

        updateDynamicTextsFromConfig();
        renderRefTasks(eligibleForTasks, pData.claimed_ref_tasks || []);
    };

    function renderRefTasks(eligibleFriendsCount, claimedTasks) {
        const listEl = document.getElementById('ref-tasks-list');
        if (!listEl) return;

        const rawTasks = window.FriendsConfig?.ref_tasks || {};
        const minUpgrades = window.FriendsConfig?.min_upgrades_for_task || 3;

        let taskKeys = Object.keys(rawTasks).sort((a, b) => {
            return (parseInt(rawTasks[a].reqFriends) || 0) - (parseInt(rawTasks[b].reqFriends) || 0);
        });

        if (taskKeys.length === 0) {
            listEl.innerHTML = '<li class="empty-state">لا توجد مهام إحالة متوفرة حالياً.</li>';
            return;
        }

        let html = '';
        taskKeys.forEach(key => {
            const task = rawTasks[key];
            const taskId = parseInt(key) || key;
            const reqFriends = parseInt(task.reqFriends) || 1;
            const reward = parseFloat(task.reward) || 0;

            const isClaimed = claimedTasks.includes(taskId) || claimedTasks.includes(key) || claimedTasks.includes(String(taskId));
            const isReady = eligibleFriendsCount >= reqFriends;
            let progressPercent = Math.min((eligibleFriendsCount / reqFriends) * 100, 100);

            let btnHtml = '';
            if (isClaimed) {
                btnHtml = `<button disabled style="background:#222226; color:#777; border:none; padding:6px 10px; border-radius:6px; font-size:11px;">✅ مستلمة</button>`;
            } else if (isReady) {
                btnHtml = `<button onclick="window.claimRefTask('${key}', ${reward}, ${reqFriends})" style="background:#2ecc71; color:#000; border:none; padding:6px 10px; border-radius:6px; font-size:11px; cursor:pointer; font-weight:bold;">🎁 استلام</button>`;
            } else {
                let remaining = reqFriends - eligibleFriendsCount;
                btnHtml = `<button disabled style="background:#18181c; color:#555; border:1px solid #2a2a2e; padding:6px 10px; border-radius:6px; font-size:11px;">🔒 باقي ${remaining}</button>`;
            }

            html += `
                <li style="background:#121215; border:1px solid #26262b; border-radius:12px; padding:12px; margin-bottom:10px; list-style:none; direction:rtl;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <h4 style="margin:0; color:#fff; font-size:13px;">دعوة ${reqFriends} أصدقاء (${minUpgrades}+ ترقيات)</h4>
                            <p style="margin:4px 0 0 0; color:#f39c12; font-size:11px; font-weight:bold;">مكافأة: ${formatNumber(reward, 2)} ZN</p>
                        </div>
                        <div>${btnHtml}</div>
                    </div>
                    <div style="width:100%; background:#1c1c20; height:6px; border-radius:4px; overflow:hidden; margin-top:8px;">
                        <div style="width:${progressPercent}%; height:100%; background:#f39c12; border-radius:4px;"></div>
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

    window.claimRefEarnings = async function() {
        const userId = getUserId();
        const btn = document.getElementById('btn-claim-ref');
        if (btn) {
            btn.disabled = true;
            btn.innerText = "⏳ جاري السحب...";
        }

        try {
            let response = await fetch('/api/friends/claim_ref_earnings', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: INIT_DATA, user_id: userId })
            });
            let data = await response.json();
            
            if (response.ok && data.success) {
                const formattedNet = formatNumber(data.net_amount, 2);
                const feePercent = window.FriendsConfig?.claim_fee_percent || 1.5;
                showToast(`🎉 تم السحب بنجاح!\nأُضيف ${formattedNet} ZN إلى رصيدك (بعد خصم ${feePercent}% رسوم).`);
                
                if (!window.PlayerData) window.PlayerData = {};
                window.PlayerData.pending_ref_earnings = 0;

                setStoredBalance(data.new_balance);
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

    window.claimRefTask = async function(taskId, reward, reqFriends) {
        if (isTaskClaiming) return;
        isTaskClaiming = true;
        
        const userId = getUserId();
        try {
            let response = await fetch('/api/friends/claim_ref_task', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: INIT_DATA, user_id: userId, taskId, reward, reqFriends })
            });
            let data = await response.json();

            if (response.ok && data.success) {
                showToast(`🎊 مبروك! استلمت مكافأة ${formatNumber(reward, 2)} ZN.`);
                
                if (!window.PlayerData) window.PlayerData = {};
                if (data.claimed_ref_tasks) {
                    window.PlayerData.claimed_ref_tasks = data.claimed_ref_tasks;
                } else {
                    if (!window.PlayerData.claimed_ref_tasks) window.PlayerData.claimed_ref_tasks = [];
                    window.PlayerData.claimed_ref_tasks.push(taskId);
                }

                setStoredBalance(data.new_balance);
                window.updateFriendsUI();
            } else {
                showToast(data.error || "خطأ في استلام المكافأة");
            }
        } catch (e) {
            showToast("خطأ في الاتصال بالخادم.");
        } finally {
            isTaskClaiming = false;
        }
    };

    async function fetchAndRenderFriendsList() {
        const container = document.getElementById('friends-list-container');
        if (!container) return;

        const userId = getUserId();
        const minUpgrades = window.FriendsConfig?.min_upgrades_for_task || 3;

        try {
            let response = await fetch('/api/friends/list', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ initData: INIT_DATA, user_id: userId })
            });
            let data = await response.json();

            if (response.ok && data.success) {
                if (!data.friends || data.friends.length === 0) {
                    container.innerHTML = '<div class="empty-state">لم تقم بدعوة أي أصدقاء حتى الآن.</div>';
                    return;
                }
                
                let html = '<ul style="padding:0; margin:0;">';
                data.friends.forEach(f => {
                    const cnt = f.upgrades_count || 0;
                    let statusHtml = cnt >= minUpgrades 
                        ? `<span style="color: #2ecc71; font-size:11px;">مؤهل للمهام (${cnt}/${minUpgrades} ترقيات) ✅</span>`
                        : `<span style="color: #f39c12; font-size:11px;">ينقصه ${minUpgrades - cnt} ترقية (${cnt}/${minUpgrades}) ⏳</span>`;
                    
                    const genVal = parseFloat(f.generated || f.earned_from_him || 0);
                    const formattedGen = formatNumber(genVal, 2);

                    html += `
                        <li style="display:flex; justify-content:space-between; align-items:center; background:#121215; padding:10px 12px; border-radius:10px; margin-bottom:8px; border:1px solid #26262b;">
                            <div style="display:flex; align-items:center; gap:10px;">
                                <div style="width:34px; height:34px; background:#f39c12; border-radius:50%; display:flex; align-items:center; justify-content:center; color:#000; font-weight:bold; font-size:13px;">${(f.name || 'U').charAt(0).toUpperCase()}</div>
                                <div style="display:flex; flex-direction:column;">
                                    <span style="color:#fff; font-size:13px; font-weight:600;">${f.name || 'مستخدم مجهول'}</span>
                                    ${statusHtml}
                                </div>
                            </div>
                            <div style="text-align: left;">
                                <span style="display:block; color:#2ecc71; font-weight:bold; font-size:13px;">+${formattedGen} ZN</span>
                                <span style="font-size:10px; color:#888;">المجمع منه</span>
                            </div>
                        </li>
                    `;
                });
                html += '</ul>';
                container.innerHTML = html;
            } else {
                container.innerHTML = '<div class="empty-state">فشل في تحميل قائمة الأصدقاء.</div>';
            }
        } catch (e) {
            container.innerHTML = '<div class="empty-state">خطأ في الاتصال بالخادم.</div>';
        }
    }

    setInterval(() => {
        const cachedBal = getStoredBalance();
        if (window.PlayerData && Math.floor(window.PlayerData.balance) !== Math.floor(cachedBal)) {
            window.PlayerData.balance = cachedBal;
            if (typeof window.updateFriendsUI === 'function') {
                window.updateFriendsUI();
            }
        }
    }, 1000);

    window.addEventListener('pageshow', () => {
        const stored = getStoredBalance();
        if (window.PlayerData) window.PlayerData.balance = stored;
        window.updateFriendsUI();
        loadFriendsData(true);
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            const stored = getStoredBalance();
            if (window.PlayerData) window.PlayerData.balance = stored;
            window.updateFriendsUI();
            loadFriendsData(true);
        }
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initFriendsPage);
    } else {
        initFriendsPage();
    }
})();

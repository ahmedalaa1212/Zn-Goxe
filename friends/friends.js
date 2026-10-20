// friends/friends.js
(function initFriendsModule() {
    const tele = window.Telegram?.WebApp;
    const INIT_DATA = tele?.initData || "";
    const BOT_USERNAME = "zngoxe_bot";

    function escapeHTML(str) {
        return String(str || "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    async function secureRequest(url, method = "GET", body = null) {
        const initData = tele?.initData || "";

        if (!initData) {
            throw new Error("يجب فتح التطبيق من داخل Telegram.");
        }

        const headers = {
            Accept: "application/json",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            Pragma: "no-cache",
            "X-Telegram-Init-Data": initData,
            Authorization: `Bearer ${initData}`
        };

        const options = {
            method,
            headers,
            cache: "no-store",
            credentials: "same-origin"
        };

        if (body !== null && method !== "GET" && method !== "HEAD") {
            headers["Content-Type"] = "application/json";
            options.body = JSON.stringify(body);
        }

        // إضافة طابع زمني للرابط لمنع أي كاش على مستوى WebView
        const sep = url.includes("?") ? "&" : "?";
        const liveUrl = `${url}${sep}_t=${Date.now()}`;

        const response = await fetch(liveUrl, options);
        let data = {};

        try {
            data = await response.json();
        } catch {
            data = {};
        }

        if (!response.ok) {
            throw new Error(data.error || `HTTP ${response.status}`);
        }

        return data;
    }

    let lastFetchTimestamp = 0;
    const FETCH_COOLDOWN_MS = 1000;
    const LIVE_POLL_INTERVAL_MS = 2500; // مزامنة حية مع Supabase كل 2.5 ثانية
    let isFetchingLive = false;
    let isTaskClaiming = false;
    let isClaimingRefEarnings = false;

    // الإعدادات الافتراضية (5 ترقيات، ويتم تحديثها لحظياً من Supabase)
    window.FriendsConfig = {
        min_upgrades_for_task: 5,
        vip_min_upgrades_for_task: 3,
        commission_percent: 10,
        vip_commission_percent: 12,
        claim_fee_percent: 1.5,
        vip_claim_fee_percent: 0.0,
        ref_tasks: {
            "1": { reqFriends: 1, reward: 50 },
            "2": { reqFriends: 3, reward: 200 },
            "3": { reqFriends: 5, reward: 500 },
            "4": { reqFriends: 10, reward: 1200 },
            "5": { reqFriends: 20, reward: 2800 },
            "6": { reqFriends: 35, reward: 5500 },
            "7": { reqFriends: 50, reward: 9000 },
            "8": { reqFriends: 75, reward: 15000 },
            "9": { reqFriends: 100, reward: 22000 },
            "10": { reqFriends: 150, reward: 35000 }
        }
    };

    function getMinUpgrades() {
        // فحص الشرط الفعّال الخاص باللاعب أولاً (يتأثر بحالة VIP)
        if (window.PlayerData && window.PlayerData.effective_min_upgrades !== undefined) {
            const val = parseInt(window.PlayerData.effective_min_upgrades);
            if (!isNaN(val) && val > 0) return val;
        }
        // الرجوع للشرط الافتراضي العام في حال لم يتوفر
        const cfgVal = parseInt(window.FriendsConfig?.min_upgrades_for_task);
        return (!isNaN(cfgVal) && cfgVal > 0) ? cfgVal : 5;
    }

    function getUserId() {
        if (tele?.initDataUnsafe?.user?.id) {
            return String(tele.initDataUnsafe.user.id);
        }
        return "";
    }

    function getStartParam() {
        return tele?.initDataUnsafe?.start_param || "";
    }

    function getCacheKey() {
        const userId = getUserId();
        return userId ? `zn_friends_cache_v3_${userId}` : 'zn_friends_cache_v3_global';
    }

    function saveCachedData(data) {
        try {
            if (!data) return;
            const payloadToSave = {
                PlayerData: data,
                FriendsConfig: window.FriendsConfig
            };
            localStorage.setItem(getCacheKey(), JSON.stringify(payloadToSave));
        } catch (e) {
            console.error("خطأ حفظ كاش الأصدقاء:", e);
        }
    }

    function loadCachedData() {
        try {
            // مسح نسخ الكاش القديمة لضمان عدم بقاء شرط الـ 3 ترقيات القديم
            const uid = getUserId();
            if (uid) {
                localStorage.removeItem(`zn_friends_cache_${uid}`);
                localStorage.removeItem(`zn_friends_cache_v2_${uid}`);
            }
            localStorage.removeItem('zn_friends_cache_global');
            localStorage.removeItem('zn_friends_cache_v2_global');

            const cached = localStorage.getItem(getCacheKey());
            if (cached) {
                const parsed = JSON.parse(cached);
                if (parsed && typeof parsed === 'object') {
                    if (parsed.PlayerData) {
                        window.PlayerData = { ...window.PlayerData, ...parsed.PlayerData };
                    } else {
                        window.PlayerData = { ...window.PlayerData, ...parsed };
                    }
                    if (parsed.FriendsConfig) {
                        window.FriendsConfig = { ...window.FriendsConfig, ...parsed.FriendsConfig };
                    }
                    return true;
                }
            }
        } catch (e) {
            console.error("خطأ قراءة كاش الأصدقاء:", e);
        }
        return false;
    }

    function cloneCurrentState() {
        try {
            return {
                PlayerData: JSON.parse(JSON.stringify(window.PlayerData || {})),
                FriendsConfig: JSON.parse(JSON.stringify(window.FriendsConfig || {})),
                balance: getStoredBalance()
            };
        } catch (e) {
            return null;
        }
    }

    function restoreState(backup) {
        if (!backup) return;
        if (backup.PlayerData) window.PlayerData = backup.PlayerData;
        if (backup.FriendsConfig) window.FriendsConfig = backup.FriendsConfig;
        if (backup.balance !== undefined) setStoredBalance(backup.balance);
        saveCachedData(window.PlayerData);
    }

    function formatNumber(num, maxDecimals = 6) {
        const val = parseFloat(num) || 0;
        if (isNaN(val) || val === 0) return "0.00";
        
        let str = val.toFixed(maxDecimals).replace(/\.?0+$/, '');
        let parts = str.split('.');
        let integerPart = parseFloat(parts[0]).toLocaleString('en-US');
        let decimalPart = parts[1] || '00';
        if (decimalPart.length === 1) decimalPart += '0';
        
        return `${integerPart}.${decimalPart}`;
    }

    function formatNumberHTML(num, maxDecimals = 6) {
        const val = parseFloat(num) || 0;
        let integerPart = "0";
        let decimalPart = "00";

        if (!isNaN(val) && val !== 0) {
            let str = val.toFixed(maxDecimals).replace(/\.?0+$/, '');
            let parts = str.split('.');
            integerPart = parseFloat(parts[0]).toLocaleString('en-US');
            decimalPart = parts[1] || '00';
            if (decimalPart.length === 1) decimalPart += '0';
        }

        const totalLen = integerPart.length + decimalPart.length;
        let fontSizeStyle = "";
        if (totalLen > 14) {
            fontSizeStyle = "font-size: 0.65em;";
        } else if (totalLen > 11) {
            fontSizeStyle = "font-size: 0.75em;";
        } else if (totalLen > 8) {
            fontSizeStyle = "font-size: 0.85em;";
        }

        return `<span dir="ltr" style="direction: ltr; unicode-bidi: isolate; white-space: nowrap; display: inline-flex; align-items: baseline; justify-content: center; vertical-align: baseline; max-width: 100%; ${fontSizeStyle}">${integerPart}<span style="font-size: 0.75em; opacity: 0.7; margin-left: 1px;">.${decimalPart}</span></span>`;
    }

    function formatInteger(num) {
        const val = Math.floor(parseFloat(num) || 0);
        return val.toLocaleString('en-US');
    }

    function getStoredBalance() {
        if (window.PlayerData && window.PlayerData.balance !== undefined && window.PlayerData.balance !== null && !isNaN(window.PlayerData.balance)) {
            return parseFloat(window.PlayerData.balance);
        }

        const sources = [
            window.userState?.balance,
            window.GameState?.balance
        ];

        for (const src of sources) {
            if (src !== undefined && src !== null && !isNaN(src)) {
                return parseFloat(src);
            }
        }

        const localBal = localStorage.getItem('zn_balance') ?? localStorage.getItem('user_balance');
        if (localBal !== null && !isNaN(parseFloat(localBal))) {
            return parseFloat(localBal);
        }

        return 0;
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
        const pData = window.PlayerData || {};
        const isVip = pData.is_vip || false;

        const commPercent = pData.effective_commission ?? (isVip ? (cfg.vip_commission_percent ?? 12) : (cfg.commission_percent ?? 10));
        const feePercent = pData.effective_claim_fee ?? (isVip ? (cfg.vip_claim_fee_percent ?? 0) : (cfg.claim_fee_percent ?? 1.5));
        
        // جلب الشرط الديناميكي الذي يتغير بناءً على حالة الـ VIP
        const minUpgrades = getMinUpgrades();

        const elComm = document.getElementById('info-comm-percent');
        if (elComm) {
            elComm.innerText = isVip ? `${commPercent}% 👑 VIP` : `${commPercent}%`;
        }

        const elUpgrades = document.getElementById('info-min-upgrades');
        if (elUpgrades) {
            elUpgrades.innerText = `${minUpgrades} ترقيات`;
        }

        const elFee = document.getElementById('info-claim-fee');
        if (elFee) {
            elFee.innerText = isVip ? "0% (👑 VIP معفي)" : `${feePercent}%`;
        }

        // تحديث أي نصوص ثابتة في الصفحة وتغييرها للرقم الصحيح
        document.querySelectorAll('p, li, span, div, small').forEach(el => {
            if (el.children.length === 0 && el.textContent) {
                if (/شراء\s+\d+\s+ترقيات/.test(el.textContent)) {
                    el.textContent = el.textContent.replace(/شراء\s+\d+\s+ترقيات/g, `شراء ${minUpgrades} ترقيات`);
                } else if (/^\s*\d+\s+ترقيات\s*$/.test(el.textContent) && el.id !== 'info-min-upgrades') {
                    el.textContent = `${minUpgrades} ترقيات`;
                }
                if (/يتم خصم\s+[\d.]+\s*%\s*رسوم/.test(el.textContent)) {
                    el.textContent = el.textContent.replace(/يتم خصم\s+[\d.]+\s*%\s*رسوم/g, `يتم خصم ${feePercent}% رسوم`);
                }
            }
        });
    }

    function renderFriendsListHTML(friendsArr) {
        const container = document.getElementById('friends-list-container');
        if (!container) return;

        const minUpgrades = getMinUpgrades();
        const list = Array.isArray(friendsArr) ? friendsArr : [];

        // تحديث عدد الأصدقاء والمؤهلين في الواجهة مباشرة بناءً على القائمة الحية والشرط الفعال
        const eligibleLive = list.filter(f => (parseInt(f.upgrades_count) || 0) >= minUpgrades).length;
        if (window.PlayerData) {
            window.PlayerData.invited_friends_count = list.length;
            window.PlayerData.eligible_task_friends_count = eligibleLive;
        }

        if (list.length === 0) {
            container.innerHTML = '<div class="empty-state">لم تقم بدعوة أي أصدقاء حتى الآن.</div>';
            return;
        }

        let html = '<ul style="padding:0; margin:0;">';
        list.forEach(f => {
            const cnt = parseInt(f.upgrades_count) || 0;
            const isEligible = cnt >= minUpgrades;
            let statusHtml = isEligible 
                ? `<span style="color: #2ecc71; font-size:11px;">مؤهل للمهام (${cnt}/${minUpgrades} ترقيات) ✅</span>`
                : `<span style="color: #f39c12; font-size:11px;">ينقصه ترقيات (${cnt}/${minUpgrades}) ⏳</span>`;
            
            const genVal = parseFloat(f.generated ?? f.earned_from_him ?? 0);
            const formattedGen = formatNumberHTML(genVal);
            const safeName = escapeHTML(f.name || f.first_name || 'مستخدم مجهول');
            const initial = escapeHTML((f.name || f.first_name || 'U').trim().charAt(0).toUpperCase() || 'U');

            html += `
                <li style="display:flex; justify-content:space-between; align-items:center; background:#121215; padding:10px 12px; border-radius:10px; margin-bottom:8px; border:1px solid #26262b;">
                    <div style="display:flex; align-items:center; gap:10px;">
                        <div style="width:34px; height:34px; background:#f39c12; border-radius:50%; display:flex; align-items:center; justify-content:center; color:#000; font-weight:bold; font-size:13px;">${initial}</div>
                        <div style="display:flex; flex-direction:column;">
                            <span style="color:#fff; font-size:13px; font-weight:600;">${safeName}</span>
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
    }

    function initFriendsPage() {
        if (tele) {
            tele.ready();
            tele.expand();
        }
        
        const refInput = document.getElementById('ref-link-input');
        const userId = getUserId();

        if (refInput) {
            if (!INIT_DATA && (!userId || userId === "0000")) {
                refInput.value = "يرجى فتح التطبيق من داخل تليجرام";
            } else {
                refInput.value = `https://t.me/${BOT_USERNAME}?start=ref_${userId}`;
            }
        }

        loadCachedData();
        const cachedBal = getStoredBalance();
        window.PlayerData = {
            balance: cachedBal,
            pending_ref_earnings: 0,
            total_ref_earnings: 0,
            invited_friends_count: 0,
            ...window.PlayerData
        };
        
        window.updateFriendsUI();

        if (!INIT_DATA && (!userId || userId === "0000")) {
            const container = document.getElementById('friends-list-container');
            if (container) container.innerHTML = '<div class="empty-state">يرجى فتح التطبيق من تليجرام لعرض الأصدقاء.</div>';
            return;
        }

        loadFriendsData(true);
    }

    async function loadFriendsData(force = false) {
        const userId = getUserId();
        if (!INIT_DATA && (!userId || userId === "0000")) return;
        if (isFetchingLive || isTaskClaiming || isClaimingRefEarnings) return;

        const now = Date.now();
        if (!force && (now - lastFetchTimestamp < FETCH_COOLDOWN_MS)) {
            window.updateFriendsUI();
            return;
        }

        isFetchingLive = true;
        lastFetchTimestamp = now;

        try {
            let data = await secureRequest('/api/friends/data', 'POST', {
                user_id: userId,
                start_param: getStartParam()
            });
            
            if (data && data.success && data.player) {
                if (data.friends_config) {
                    window.FriendsConfig = { ...window.FriendsConfig, ...data.friends_config };
                } else if (data.player.friends_config) {
                    window.FriendsConfig = { ...window.FriendsConfig, ...data.player.friends_config };
                }

                window.PlayerData = { ...window.PlayerData, ...data.player };
                
                // استقبال وتحديث بيانات وميزات הـ VIP والترقيات من السيرفر
                if (data.is_vip !== undefined) window.PlayerData.is_vip = data.is_vip;
                if (data.effective_commission !== undefined) window.PlayerData.effective_commission = data.effective_commission;
                if (data.effective_claim_fee !== undefined) window.PlayerData.effective_claim_fee = data.effective_claim_fee;
                if (data.effective_min_upgrades !== undefined) window.PlayerData.effective_min_upgrades = data.effective_min_upgrades;
                else if (data.player && data.player.effective_min_upgrades !== undefined) window.PlayerData.effective_min_upgrades = data.player.effective_min_upgrades;

                if (data.player.balance !== undefined && data.player.balance !== null) {
                    setStoredBalance(data.player.balance);
                }

                const liveFriends = data.friends || data.player.friends;
                if (Array.isArray(liveFriends)) {
                    renderFriendsListHTML(liveFriends);
                } else {
                    await fetchAndRenderFriendsList();
                }

                saveCachedData(window.PlayerData);
                window.updateFriendsUI();
            }
        } catch (error) {
            console.error("فشل في جلب بيانات الأصدقاء:", error);
        } finally {
            isFetchingLive = false;
        }
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

        const elBalances = document.querySelectorAll('.zn-balance-display, #top-balance-friends, #farm-balance, #top-balance, #header-zn-balance, .user-balance');
        elBalances.forEach(el => {
            el.style.whiteSpace = 'nowrap';
            if (el.id === 'farm-balance' || el.innerText.includes('ZN') || el.innerHTML.includes('ZN')) {
                el.innerHTML = `${formatNumberHTML(balance)} ZN`;
            } else {
                el.innerHTML = formatNumberHTML(balance);
            }
        });

        const elPending = document.getElementById('pending-ref-earnings');
        const elTotal = document.getElementById('total-ref-earnings');
        const elInvited = document.getElementById('invited-friends-count');
        const btnClaim = document.getElementById('btn-claim-ref');

        if (elPending) {
            elPending.style.whiteSpace = 'nowrap';
            elPending.style.display = 'inline-block';
            elPending.innerHTML = formatNumberHTML(pending);
        }
        if (elTotal) {
            elTotal.style.whiteSpace = 'nowrap';
            elTotal.style.display = 'inline-block';
            elTotal.innerHTML = formatNumberHTML(totalEarnings);
        }
        if (elInvited) elInvited.innerText = totalInvited.toLocaleString();

        if (btnClaim) {
            if (isClaimingRefEarnings) {
                btnClaim.disabled = true;
                btnClaim.style.background = "#222226";
                btnClaim.style.color = "#888888";
                btnClaim.innerText = "⏳ جاري السحب...";
            } else if (pending <= 0) {
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
        const minUpgrades = getMinUpgrades();

        let taskKeys = Object.keys(rawTasks).sort((a, b) => {
            return (parseInt(rawTasks[a].reqFriends) || 0) - (parseInt(rawTasks[b].reqFriends) || 0);
        });

        if (taskKeys.length === 0) {
            listEl.innerHTML = '<li class="empty-state">لا توجد مهام إحالة متوفرة حالياً.</li>';
            return;
        }

        let html = '';
        const claimedList = (claimedTasks || []).map(String);
        const upgradeText = `+${minUpgrades} ترقيات`;

        taskKeys.forEach(key => {
            const task = rawTasks[key];
            const taskId = parseInt(key) || key;
            const reqFriends = parseInt(task.reqFriends) || 1;
            const reward = parseFloat(task.reward) || 0;

            const isClaimed = claimedList.includes(String(taskId)) || claimedList.includes(String(key));
            const isReady = eligibleFriendsCount >= reqFriends;
            let progressPercent = Math.min((eligibleFriendsCount / reqFriends) * 100, 100);

            let btnHtml = '';
            if (isClaimed) {
                btnHtml = `<button disabled style="background:#222226; color:#777; border:none; padding:6px 10px; border-radius:6px; font-size:11px;">✅ مستلمة</button>`;
            } else if (isReady) {
                btnHtml = `<button onclick="window.claimRefTask('${escapeHTML(key)}', ${reward}, ${reqFriends})" ${isTaskClaiming ? 'disabled' : ''} style="background:#2ecc71; color:#000; border:none; padding:6px 10px; border-radius:6px; font-size:11px; cursor:pointer; font-weight:bold;">${isTaskClaiming ? '⏳...' : '🎁 استلام'}</button>`;
            } else {
                let remaining = reqFriends - eligibleFriendsCount;
                btnHtml = `<button disabled style="background:#18181c; color:#555; border:1px solid #2a2a2e; padding:6px 10px; border-radius:6px; font-size:11px;">🔒 باقي ${remaining}</button>`;
            }

            html += `
                <li style="background:#121215; border:1px solid #26262b; border-radius:12px; padding:12px; margin-bottom:10px; list-style:none; direction:rtl;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <h4 style="margin:0; color:#fff; font-size:13px;">دعوة ${reqFriends} أصدقاء (${upgradeText})</h4>
                            <p style="margin:4px 0 0 0; color:#f39c12; font-size:11px; font-weight:bold;">مكافأة: ${formatInteger(reward)} ZN</p>
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
        if (isClaimingRefEarnings) return;

        const pData = window.PlayerData || {};
        const pending = parseFloat(pData.pending_ref_earnings || 0);

        if (pending <= 0) {
            showToast("لا توجد أرباح للسحب حالياً");
            return;
        }

        isClaimingRefEarnings = true;
        const backup = cloneCurrentState();

        const isVip = pData.is_vip || false;
        const feePercent = pData.effective_claim_fee !== undefined 
            ? parseFloat(pData.effective_claim_fee) 
            : (isVip ? 0.0 : parseFloat(window.FriendsConfig?.claim_fee_percent ?? 1.5));

        const estimatedNet = pending * (1 - (feePercent / 100));
        const currentBal = getStoredBalance();

        setStoredBalance(currentBal + estimatedNet);
        window.PlayerData.pending_ref_earnings = 0;
        saveCachedData(window.PlayerData);
        window.updateFriendsUI();

        const userId = getUserId();
        try {
            let data = await secureRequest('/api/friends/claim_ref_earnings', 'POST', {
                user_id: userId
            });
            
            if (data && data.success) {
                const formattedNet = formatNumber(data.net_amount || estimatedNet);
                const feeText = isVip ? "(👑 بدون رسوم VIP)" : `(بعد خصم ${feePercent}% رسوم)`;
                showToast(`🎉 تم السحب بنجاح!\nأُضيف ${formattedNet} ZN إلى رصيدك ${feeText}.`);
                
                if (data.new_balance !== undefined) {
                    setStoredBalance(data.new_balance);
                }
                saveCachedData(window.PlayerData);
                window.updateFriendsUI();
            } else {
                restoreState(backup);
                window.updateFriendsUI();
                showToast(data?.error || "فشل السحب من السيرفر");
            }
        } catch (e) {
            console.error("خطأ سحب الأرباح:", e);
            restoreState(backup);
            window.updateFriendsUI();
            showToast(e.message || "حدث خطأ أثناء الاتصال بالسيرفر.");
        } finally {
            isClaimingRefEarnings = false;
            window.updateFriendsUI();
        }
    };

    window.claimRefTask = async function(taskId, reward, reqFriends) {
        if (isTaskClaiming) return;
        isTaskClaiming = true;
        
        const backup = cloneCurrentState();
        const currentBal = getStoredBalance();
        const numReward = parseFloat(reward) || 0;

        if (!window.PlayerData) window.PlayerData = {};
        if (!window.PlayerData.claimed_ref_tasks) window.PlayerData.claimed_ref_tasks = [];
        
        const taskStr = String(taskId);
        if (!window.PlayerData.claimed_ref_tasks.map(String).includes(taskStr)) {
            window.PlayerData.claimed_ref_tasks.push(taskId);
        }

        setStoredBalance(currentBal + numReward);
        saveCachedData(window.PlayerData);
        window.updateFriendsUI();

        const userId = getUserId();
        try {
            let data = await secureRequest('/api/friends/claim_ref_task', 'POST', {
                user_id: userId,
                taskId,
                reward,
                reqFriends
            });

            if (data && data.success) {
                showToast(`🎊 مبروك! استلمت مكافأة ${formatInteger(reward)} ZN.`);
                
                if (data.claimed_ref_tasks) {
                    window.PlayerData.claimed_ref_tasks = data.claimed_ref_tasks;
                }
                if (data.new_balance !== undefined) {
                    setStoredBalance(data.new_balance);
                }
                saveCachedData(window.PlayerData);
                window.updateFriendsUI();
            } else {
                restoreState(backup);
                window.updateFriendsUI();
                showToast(data?.error || "خطأ في استلام المكافأة");
            }
        } catch (e) {
            console.error("خطأ استلام المهمة:", e);
            restoreState(backup);
            window.updateFriendsUI();
            showToast(e.message || "خطأ في الاتصال بالخادم.");
        } finally {
            isTaskClaiming = false;
            window.updateFriendsUI();
        }
    };

    async function fetchAndRenderFriendsList() {
        const container = document.getElementById('friends-list-container');
        if (!container) return;

        const userId = getUserId();

        try {
            let data = await secureRequest('/api/friends/list', 'POST', {
                user_id: userId
            });

            if (data && data.success) {
                renderFriendsListHTML(data.friends || []);
                saveCachedData(window.PlayerData);
                window.updateFriendsUI();
            } else if (!container.innerHTML || container.innerHTML.trim() === '') {
                container.innerHTML = '<div class="empty-state">فشل في تحميل قائمة الأصدقاء.</div>';
            }
        } catch (e) {
            if (!container.innerHTML || container.innerHTML.trim() === '') {
                container.innerHTML = '<div class="empty-state">خطأ في الاتصال بالخادم.</div>';
            }
        }
    }

    // مزامنة حية ومستمرة من Supabase أثناء وقوف المستخدم داخل التطبيق
    setInterval(() => {
        if (document.visibilityState === "visible") {
            loadFriendsData(true);
        }
    }, LIVE_POLL_INTERVAL_MS);

    window.addEventListener('pageshow', () => {
        loadFriendsData(true);
    });

    document.addEventListener("visibilitychange", () => {
        if (document.visibilityState === "visible") {
            loadFriendsData(true);
        }
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initFriendsPage);
    } else {
        initFriendsPage();
    }
})();

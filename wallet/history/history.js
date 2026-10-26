window.historyModule = (function () {
    let allTransactions = [];
    let currentFilter = 'all';
    let activeAbortController = null;
    let isFetching = false;
    let lastFetchTime = 0;

    // مسح أي كاش قديم فارغ كان مخزناً من المحاولات السابقة
    try {
        Object.keys(localStorage).forEach(k => {
            if (
                k.startsWith('zn_tx_history_cache_v2_') ||
                k.startsWith('zn_tx_history_cache_v3_') ||
                k.startsWith('zn_tx_history_cache_v4_')
            ) {
                localStorage.removeItem(k);
            }
        });
    } catch (e) {}

    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    // جلب معرف المستخدم الحقيقي بكل الطرق الممكنة دون تداخل بين الحسابات
    function getUserId() {
        if (window.Telegram?.WebApp?.initDataUnsafe?.user?.id) {
            return String(window.Telegram.WebApp.initDataUnsafe.user.id).trim();
        }

        if (window.Telegram?.WebApp?.initData) {
            try {
                const params = new URLSearchParams(window.Telegram.WebApp.initData);
                const userParam = params.get('user');
                if (userParam) {
                    const userObj = JSON.parse(decodeURIComponent(userParam));
                    if (userObj && userObj.id) return String(userObj.id).trim();
                }
            } catch (e) {}
        }

        if (window.userState?.tg_id) return String(window.userState.tg_id).trim();
        if (window.userState?.user_id) return String(window.userState.user_id).trim();
        if (window.userState?.userId) return String(window.userState.userId).trim();
        if (window.userState?.id) return String(window.userState.id).trim();

        if (window.PlayerData?.tg_id) return String(window.PlayerData.tg_id).trim();
        if (window.PlayerData?.user_id) return String(window.PlayerData.user_id).trim();
        if (window.PlayerData?.userId) return String(window.PlayerData.userId).trim();
        if (window.PlayerData?.id) return String(window.PlayerData.id).trim();

        const urlParams = new URLSearchParams(window.location.search);
        const urlId = urlParams.get('user_id') || urlParams.get('tg_id') || urlParams.get('uid');
        if (urlId && urlId !== 'null' && urlId !== 'undefined') return String(urlId).trim();

        const localId = (
            localStorage.getItem('tg_user_id') ||
            localStorage.getItem('user_id') ||
            localStorage.getItem('tg_id') ||
            sessionStorage.getItem('user_id')
        );
        if (localId && localId !== 'null' && localId !== 'undefined') return String(localId).trim();

        if (window.currentUser && window.currentUser.id) return String(window.currentUser.id).trim();
        if (window.userId) return String(window.userId).trim();

        return "";
    }

    function getCacheKey(userId) {
        return `zn_tx_history_cache_v5_${userId}`;
    }

    function loadCachedTransactions(userId) {
        if (!userId) return null;
        try {
            const raw = localStorage.getItem(getCacheKey(userId));
            if (!raw) return null;
            const parsed = JSON.parse(raw);
            if (Array.isArray(parsed) && parsed.length > 0) return parsed;
        } catch (e) {}
        return null;
    }

    function saveCachedTransactions(userId, txs) {
        if (!userId || !Array.isArray(txs)) return;
        try {
            if (txs.length > 0) {
                localStorage.setItem(getCacheKey(userId), JSON.stringify(txs.slice(0, 80)));
            } else {
                localStorage.removeItem(getCacheKey(userId));
            }
        } catch (e) {}
    }

    // تنسيق التاريخ والوقت بالسنة والشهر واليوم والساعة والدقيقة والثانية
    function formatArabicDate(timestamp, fallbackStr) {
        if (!timestamp) return fallbackStr || 'غير محدد';
        try {
            const tsNum = Number(timestamp);
            const date = new Date(tsNum > 1e11 ? tsNum : tsNum * 1000);
            if (isNaN(date.getTime())) return fallbackStr || 'غير محدد';

            const optionsDate = { year: 'numeric', month: 'short', day: 'numeric' };
            const optionsTime = { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: true };

            const dateStr = date.toLocaleDateString('ar-EG', optionsDate);
            const timeStr = date.toLocaleTimeString('ar-EG', optionsTime);

            return `${dateStr} • ${timeStr}`;
        } catch (e) {
            return fallbackStr || 'غير محدد';
        }
    }

    async function fetchTransactions(forceRefresh = false, retryCount = 0) {
        const container = document.getElementById('history-list-container');
        const userId = getUserId();

        if (!userId || userId === '0') {
            if (retryCount < 5) {
                setTimeout(() => fetchTransactions(forceRefresh, retryCount + 1), 350);
                return;
            }
            if (container) {
                container.innerHTML = `
                    <div class="history-empty">
                        <div>⚠️ تعذر تحديد معرف المستخدم، يرجى إعادة فتح المحفظة.</div>
                        <button onclick="historyModule.refresh(true)" style="margin-top:10px; padding:6px 14px; border-radius:8px; background:#0ea5e9; color:#fff; border:none; cursor:pointer; font-weight:bold;">🔄 إعادة المحاولة</button>
                    </div>`;
            }
            return;
        }

        // منع إجهاض الطلبات المتتالية إذا كان هناك طلب يعمل بالفعل خلال أقل من ثانيتين
        const now = Date.now();
        if (isFetching && !forceRefresh && (now - lastFetchTime < 2500)) {
            return;
        }

        // عرض السجلات المحفوظة مؤقتاً ريثما يرد السيرفر
        if (allTransactions.length === 0) {
            const cached = loadCachedTransactions(userId);
            if (cached && cached.length > 0) {
                allTransactions = cached;
                updateCounts();
                renderList();
            }
        }

        if (container && allTransactions.length === 0) {
            container.innerHTML = `
                <div class="history-loading">
                    <div class="spinner"></div>
                    <span>جاري تحميل سجل المعاملات...</span>
                </div>`;
        }

        if (activeAbortController) {
            try { activeAbortController.abort(); } catch (e) {}
        }
        activeAbortController = new AbortController();
        isFetching = true;
        lastFetchTime = now;

        const timeoutId = setTimeout(() => {
            if (activeAbortController) {
                try { activeAbortController.abort(); } catch (e) {}
            }
        }, 10000);

        try {
            const initData = window.Telegram?.WebApp?.initData || '';
            const reqHeaders = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'X-Telegram-User-Id': userId.toString(),
                'X-Telegram-Init-Data': initData
            };

            let response = await fetch(`/api/wallet/history/transactions?user_id=${encodeURIComponent(userId)}&force=1&_t=${Date.now()}`, {
                method: 'GET',
                cache: 'no-store',
                signal: activeAbortController.signal,
                headers: reqHeaders
            });

            if (response.status === 404) {
                response = await fetch(`/api/history/transactions?user_id=${encodeURIComponent(userId)}&force=1&_t=${Date.now()}`, {
                    method: 'GET',
                    cache: 'no-store',
                    signal: activeAbortController.signal,
                    headers: reqHeaders
                });
            }

            clearTimeout(timeoutId);

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.success && Array.isArray(data.transactions)) {
                allTransactions = data.transactions;
                saveCachedTransactions(userId, allTransactions);
                updateCounts();
                renderList();
            } else if (container && allTransactions.length === 0) {
                container.innerHTML = `
                    <div class="history-empty">
                        <div>⚠️ ${escapeHtml(data.message || 'لا توجد معاملات متاحة حالياً')}</div>
                        <button onclick="historyModule.refresh(true)" style="margin-top:10px; padding:6px 14px; border-radius:8px; background:#0ea5e9; color:#fff; border:none; cursor:pointer; font-weight:bold;">🔄 تحديث</button>
                    </div>`;
            }
        } catch (error) {
            clearTimeout(timeoutId);
            if (error && error.name === 'AbortError') {
                return;
            }

            if (retryCount < 1) {
                setTimeout(() => fetchTransactions(true, retryCount + 1), 500);
                return;
            }

            console.error('⚠️ [history.js] Error fetching history:', error);
            if (container && allTransactions.length === 0) {
                container.innerHTML = `
                    <div class="history-empty">
                        <div>⚠️ حدث خطأ أثناء الاتصال بالسيرفر.</div>
                        <button onclick="historyModule.refresh(true)" style="margin-top:10px; padding:6px 14px; border-radius:8px; background:#0ea5e9; color:#fff; border:none; cursor:pointer; font-weight:bold;">🔄 إعادة تحميل السجلات</button>
                    </div>`;
            }
        } finally {
            isFetching = false;
        }
    }

    function updateCounts() {
        const depositCount = allTransactions.filter(t => t.type === 'deposit').length;
        const withdrawCount = allTransactions.filter(t => t.type === 'withdraw').length;

        const countAll = document.getElementById('count-all');
        const countDeposit = document.getElementById('count-deposit');
        const countWithdraw = document.getElementById('count-withdraw');

        if (countAll) countAll.innerText = allTransactions.length;
        if (countDeposit) countDeposit.innerText = depositCount;
        if (countWithdraw) countWithdraw.innerText = withdrawCount;
    }

    function filterHistory(type) {
        currentFilter = type;
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-filter') === type);
        });
        renderList();
    }

    function getStatusInfo(tx) {
        const st = String(tx.status || '').toLowerCase();
        if (st === 'completed' || st === 'success' || st === 'paid' || st === 'approved') {
            return {
                statusClass: 'status-completed',
                statusText: 'تم التنفيذ ✅'
            };
        } else if (st === 'failed' || st === 'rejected' || st === 'cancelled' || st === 'expired') {
            return {
                statusClass: 'status-failed',
                statusText: 'مرفوض / فاشل ❌'
            };
        } else {
            return {
                statusClass: 'status-pending',
                statusText: 'قيد المراجعة ⏳'
            };
        }
    }

    function renderList() {
        const container = document.getElementById('history-list-container');
        if (!container) return;

        let filtered = allTransactions;
        if (currentFilter !== 'all') {
            filtered = allTransactions.filter(t => t.type === currentFilter);
        }

        if (filtered.length === 0) {
            const filterLabel = currentFilter === 'deposit' ? 'إيداع' : (currentFilter === 'withdraw' ? 'سحب' : '');
            container.innerHTML = `
                <div class="history-empty">
                    <div style="font-size: 32px; margin-bottom: 8px;">📭</div>
                    <div>لا توجد معاملات ${filterLabel} في هذه القائمة حتى الآن</div>
                </div>`;
            return;
        }

        let html = '';
        filtered.forEach((tx, idx) => {
            const isDeposit = tx.type === 'deposit';
            const icon = isDeposit ? '📥' : '📤';
            const sign = isDeposit ? '+' : '-';
            const amountClass = isDeposit ? 'deposit' : 'withdraw';
            const iconClass = isDeposit ? 'deposit' : 'withdraw';

            const { statusClass, statusText } = getStatusInfo(tx);
            const formattedDate = formatArabicDate(tx.timestamp, tx.formatted_date);
            const rawId = escapeHtml(String(tx.id || ''));
            const shortTxId = rawId.length > 16 ? rawId.substring(0, 8) + '...' + rawId.substring(rawId.length - 4) : rawId;
            const currency = escapeHtml(tx.currency || 'ZNX');
            const typeTitle = escapeHtml(tx.type_ar || (isDeposit ? 'إيداع' : 'سحب'));
            const detailsText = escapeHtml(tx.details || 'معاملة شبكة TON');

            html += `
            <div class="tx-card" onclick="historyModule.showDetails(${idx})" style="cursor: pointer;">
                <div class="tx-card-main">
                    <div class="tx-type-group">
                        <div class="tx-type-icon ${iconClass}">${icon}</div>
                        <div>
                            <h4 class="tx-title">${typeTitle} ${currency}</h4>
                            <div class="tx-date" dir="rtl">${escapeHtml(formattedDate)}</div>
                        </div>
                    </div>
                    <div class="tx-amount-group">
                        <div class="tx-amount ${amountClass}">${sign}${parseFloat(tx.amount || 0).toFixed(4)} ${currency}</div>
                        <span class="tx-status-badge ${statusClass}">${statusText}</span>
                    </div>
                </div>

                <div class="tx-card-footer">
                    <div>التفاصيل: <span style="color: #cbd5e1;">${detailsText}</span></div>
                    <div class="tx-id-box" onclick="event.stopPropagation();">
                        <span>#${shortTxId}</span>
                        <span class="copy-btn" onclick="historyModule.copyText('${rawId}')" title="نسخ رقم المعاملة">📋</span>
                    </div>
                </div>

                ${tx.failure_reason ? `
                <div class="failure-reason-box">
                    <span>⚠️ <b>ملاحظة / سبب الرفض:</b> ${escapeHtml(tx.failure_reason)}</span>
                </div>
                ` : ''}
            </div>
            `;
        });

        container.innerHTML = html;
    }

    function showDetails(index) {
        let filtered = allTransactions;
        if (currentFilter !== 'all') {
            filtered = allTransactions.filter(t => t.type === currentFilter);
        }
        const tx = filtered[index];
        if (!tx) return;

        const modal = document.getElementById('tx-details-modal');
        const body = document.getElementById('tx-modal-body');
        if (!modal || !body) return;

        const { statusText } = getStatusInfo(tx);
        const formattedDate = formatArabicDate(tx.timestamp, tx.formatted_date);

        body.innerHTML = `
            <div style="display:flex; flex-direction:column; gap:10px; font-size:14px; text-align:right;" dir="rtl">
                <div><b>نوع العملية:</b> ${escapeHtml(tx.type_ar || (tx.type === 'deposit' ? 'إيداع' : 'سحب'))}</div>
                <div><b>المبلغ:</b> ${parseFloat(tx.amount || 0).toFixed(4)} ${escapeHtml(tx.currency || 'ZNX')}</div>
                ${tx.type === 'withdraw' && tx.fee_usd ? `<div><b>رسوم الشبكة:</b> $${parseFloat(tx.fee_usd).toFixed(2)} USD</div>` : ''}
                ${tx.tier_name ? `<div><b>الشريحة:</b> ${escapeHtml(tx.tier_name)}</div>` : ''}
                <div><b>الحالة:</b> ${statusText}</div>
                <div><b>التاريخ والوقت:</b> ${escapeHtml(formattedDate)}</div>
                <div><b>التفاصيل:</b> ${escapeHtml(tx.details || 'معاملة شبكة TON')}</div>
                ${tx.wallet_address ? `<div><b>عنوان المحفظة:</b> <span style="word-break:break-all; font-family:monospace;">${escapeHtml(tx.wallet_address)}</span></div>` : ''}
                ${tx.failure_reason ? `<div style="color:#f87171;"><b>سبب الرفض/الملاحظة:</b> ${escapeHtml(tx.failure_reason)}</div>` : ''}
                <div style="word-break:break-all;"><b>رقم المعاملة:</b> #${escapeHtml(tx.id)}</div>
            </div>
        `;
        modal.style.display = 'flex';
    }

    function copyText(text) {
        if (!text) return;
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(text).then(() => {
                showNotice('تم نسخ رقم المعاملة للحافظة!');
            }).catch(() => fallbackCopy(text));
        } else {
            fallbackCopy(text);
        }
    }

    function fallbackCopy(text) {
        const input = document.createElement('input');
        input.value = text;
        document.body.appendChild(input);
        input.select();
        document.execCommand('copy');
        document.body.removeChild(input);
        showNotice('تم نسخ رقم المعاملة!');
    }

    function showNotice(msg) {
        if (window.Telegram?.WebApp?.showAlert) {
            window.Telegram.WebApp.showAlert(msg);
        } else {
            alert(msg);
        }
    }

    function closeModal() {
        const modal = document.getElementById('tx-details-modal');
        if (modal) modal.style.display = 'none';
    }

    // تحديث فوري للسجل عند تقديم طلب سحب جديد
    window.addEventListener('withdrawSubmitted', () => {
        fetchTransactions(true);
    });

    // تحديث هادئ غير متكرر عند تحديث حالة المستخدم (بحد أقصى مرة كل 15 ثانية لمنع قطع الاتصال)
    window.addEventListener('userStateUpdated', () => {
        if (Date.now() - lastFetchTime > 15000 && document.getElementById('history-list-container')) {
            fetchTransactions(false);
        }
    });

    return {
        init: () => fetchTransactions(true),
        refresh: (force = true) => fetchTransactions(force),
        filterHistory: filterHistory,
        showDetails: showDetails,
        copyText: copyText,
        closeModal: closeModal
    };
})();

window.init_history_module = function () {
    if (window.historyModule) {
        window.historyModule.init();
    }
};

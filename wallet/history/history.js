window.historyModule = (function () {
    let allTransactions = [];
    let currentFilter = 'all';

    // Get Telegram User ID securely from all sources
    function getUserId() {
        if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe?.user?.id) {
            return window.Telegram.WebApp.initDataUnsafe.user.id;
        }
        
        const urlParams = new URLSearchParams(window.location.search);
        const urlId = urlParams.get('user_id') || urlParams.get('tg_id') || urlParams.get('uid');
        if (urlId) return urlId;

        const localId = localStorage.getItem('tg_user_id') || localStorage.getItem('user_id') || localStorage.getItem('tg_id');
        if (localId) return localId;

        if (window.currentUser && window.currentUser.id) return window.currentUser.id;

        return null;
    }

    // Format Arabic Date & Time
    function formatArabicDate(timestamp) {
        if (!timestamp) return 'غير محدد';
        try {
            const date = new Date(timestamp * 1000);
            if (isNaN(date.getTime())) return 'غير محدد';
            
            const optionsDate = { year: 'numeric', month: 'short', day: 'numeric' };
            const optionsTime = { hour: '2-digit', minute: '2-digit', hour12: true };

            const dateStr = date.toLocaleDateString('ar-EG', optionsDate);
            const timeStr = date.toLocaleTimeString('ar-EG', optionsTime);

            return `${dateStr} - ${timeStr}`;
        } catch (e) {
            return 'غير محدد';
        }
    }

    // Load Data from Backend API
    async function fetchTransactions() {
        const container = document.getElementById('history-list-container');
        if (!container) return;

        container.innerHTML = `
            <div class="history-loading">
                <div class="spinner"></div>
                <span>جاري تحميل سجل المعاملات...</span>
            </div>`;

        const userId = getUserId();
        if (!userId) {
            container.innerHTML = `<div class="history-empty">⚠️ تعذر تحديد معرف المستخدم. حاول إعادة فتح التطبيق.</div>`;
            return;
        }
        
        try {
            const response = await fetch(`/api/wallet/history/transactions?user_id=${encodeURIComponent(userId)}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-User-Id': userId.toString()
                }
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }

            const data = await response.json();

            if (data.success && Array.isArray(data.transactions)) {
                allTransactions = data.transactions;
                updateCounts();
                renderList();
            } else {
                container.innerHTML = `<div class="history-empty">⚠️ ${data.message || 'لا توجد معاملات متاحة حالياً'}</div>`;
            }
        } catch (error) {
            console.error('⚠️ [history.js] Error fetching history:', error);
            container.innerHTML = `<div class="history-empty">⚠️ حدث خطأ أثناء الاتصال بالسيرفر.</div>`;
        }
    }

    // Update Filter Badges
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

    // Filter Logic
    function filterHistory(type) {
        currentFilter = type;
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-filter') === type);
        });
        renderList();
    }

    // Render Cards List
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
        filtered.forEach(tx => {
            const isDeposit = tx.type === 'deposit';
            const icon = isDeposit ? '📥' : '📤';
            const sign = isDeposit ? '+' : '-';
            const amountClass = isDeposit ? 'deposit' : 'withdraw';
            const iconClass = isDeposit ? 'deposit' : 'withdraw';

            let statusClass = 'status-completed';
            let statusText = tx.status_ar || 'مكتمل';
            
            if (tx.status === 'pending') {
                statusClass = 'status-pending';
                statusText = 'قيد الانتظار ⏳';
            } else if (tx.status === 'failed' || tx.status === 'rejected') {
                statusClass = 'status-failed';
                statusText = 'مرفوض/فاشل ❌';
            }

            const formattedDate = formatArabicDate(tx.timestamp);
            const rawId = String(tx.id || '');
            const shortTxId = rawId.length > 16 ? rawId.substring(0, 8) + '...' + rawId.substring(rawId.length - 4) : rawId;

            html += `
            <div class="tx-card">
                <div class="tx-card-main">
                    <div class="tx-type-group">
                        <div class="tx-type-icon ${iconClass}">${icon}</div>
                        <div>
                            <h4 class="tx-title">${tx.type_ar || (isDeposit ? 'إيداع' : 'سحب')} ${tx.currency || 'USDT'}</h4>
                            <div class="tx-date">${formattedDate}</div>
                        </div>
                    </div>
                    <div class="tx-amount-group">
                        <div class="tx-amount ${amountClass}">${sign}${parseFloat(tx.amount || 0).toFixed(4)} ${tx.currency || 'USDT'}</div>
                        <span class="tx-status-badge ${statusClass}">${statusText}</span>
                    </div>
                </div>

                <div class="tx-card-footer">
                    <div>تفاصيل: <span style="color: #cbd5e1;">${tx.details || 'معاملة شبكة TON'}</span></div>
                    <div class="tx-id-box">
                        <span>#${shortTxId}</span>
                        <span class="copy-btn" onclick="historyModule.copyText('${rawId}')" title="نسخ المعاملة">📋</span>
                    </div>
                </div>

                ${tx.failure_reason ? `
                <div class="failure-reason-box">
                    <span>⚠️ <b>سبب عدم الاكتفاء/الفشل:</b> ${tx.failure_reason}</span>
                </div>
                ` : ''}
            </div>
            `;
        });

        container.innerHTML = html;
    }

    // Helper to Copy Hash or Memo
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
        if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.showAlert) {
            window.Telegram.WebApp.showAlert(msg);
        } else {
            alert(msg);
        }
    }

    function closeModal() {
        const modal = document.getElementById('tx-details-modal');
        if (modal) modal.style.display = 'none';
    }

    // Auto Init
    setTimeout(fetchTransactions, 50);

    return {
        init: fetchTransactions,
        filterHistory: filterHistory,
        copyText: copyText,
        closeModal: closeModal
    };
})();

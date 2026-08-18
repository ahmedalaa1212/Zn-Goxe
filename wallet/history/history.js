window.historyModule = (function () {
    let allTransactions = [];
    let currentFilter = 'all';

    // Get Telegram User ID securely
    function getUserId() {
        if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe?.user) {
            return window.Telegram.WebApp.initDataUnsafe.user.id;
        }
        // Fallback for debugging/testing
        const urlParams = new URLSearchParams(window.location.search);
        return urlParams.get('user_id') || localStorage.getItem('tg_user_id') || '123456789';
    }

    // Format Arabic Date & Time
    function formatArabicDate(timestamp) {
        if (!timestamp) return 'غير محدد';
        const date = new Date(timestamp * 1000);
        
        const optionsDate = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
        const optionsTime = { hour: '2-digit', minute: '2-digit', hour12: true };

        const dateStr = date.toLocaleDateString('ar-EG', optionsDate);
        const timeStr = date.toLocaleTimeString('ar-EG', optionsTime);

        return `${dateStr} - ${timeStr}`;
    }

    // Load Data from Backend API
    async function fetchTransactions() {
        const container = document.getElementById('history-list-container');
        if (!container) return;

        const userId = getUserId();
        
        try {
            const response = await fetch(`/api/wallet/history/transactions?user_id=${userId}`, {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-User-Id': userId.toString()
                }
            });

            const data = await response.json();

            if (data.success && Array.isArray(data.transactions)) {
                allTransactions = data.transactions;
                updateCounts();
                renderList();
            } else {
                container.innerHTML = `<div class="history-empty">⚠️ فشل جلب البيانات: ${data.message || 'خطأ غير معروف'}</div>`;
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

        document.getElementById('count-all').innerText = allTransactions.length;
        document.getElementById('count-deposit').innerText = depositCount;
        document.getElementById('count-withdraw').innerText = withdrawCount;
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
            container.innerHTML = `
                <div class="history-empty">
                    <div style="font-size: 32px; margin-bottom: 8px;">📭</div>
                    <div>لا توجد معاملات في هذه القائمة حتى الآن</div>
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
            const shortTxId = tx.id && tx.id.length > 16 ? tx.id.substring(0, 10) + '...' + tx.id.substring(tx.id.length - 4) : tx.id;

            html += `
            <div class="tx-card">
                <div class="tx-card-main">
                    <div class="tx-type-group">
                        <div class="tx-type-icon ${iconClass}">${icon}</div>
                        <div>
                            <h4 class="tx-title">${tx.type_ar} ${tx.currency || 'USDT'}</h4>
                            <div class="tx-date">${formattedDate}</div>
                        </div>
                    </div>
                    <div class="tx-amount-group">
                        <div class="tx-amount ${amountClass}">${sign}${parseFloat(tx.amount).toFixed(2)} ${tx.currency || 'USDT'}</div>
                        <span class="tx-status-badge ${statusClass}">${statusText}</span>
                    </div>
                </div>

                <div class="tx-card-footer">
                    <div>تفاصيل: <span style="color: #cbd5e1;">${tx.details || 'معاملة شبكة TON'}</span></div>
                    <div class="tx-id-box">
                        <span>#${shortTxId}</span>
                        <span class="copy-btn" onclick="historyModule.copyText('${tx.id}')" title="نسخ المعاملة">📋</span>
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
        navigator.clipboard.writeText(text).then(() => {
            if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.showAlert) {
                window.Telegram.WebApp.showAlert('تم نسخ رقم المعاملة للحافظة!');
            } else {
                alert('تم نسخ رقم المعاملة: ' + text);
            }
        });
    }

    function closeModal() {
        const modal = document.getElementById('tx-details-modal');
        if (modal) modal.style.display = 'none';
    }

    // Auto Init on script load
    setTimeout(fetchTransactions, 100);

    return {
        init: fetchTransactions,
        filterHistory: filterHistory,
        copyText: copyText,
        closeModal: closeModal
    };
})();

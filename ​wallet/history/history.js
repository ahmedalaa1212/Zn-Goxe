// wallet/history/history.js
(function () {
    'use strict';

    let historyCache = null;
    let historyCacheTime = 0;
    const HISTORY_CACHE_TTL = 120000; // 2 دقيقة

    window.clearHistoryCache = function() {
        historyCache = null;
        historyCacheTime = 0;
    };

    window.renderHistoryListUI = function(rawList) {
        if (window.currentWalletTab !== 'history') return;
        const container = document.getElementById('history-items-container');
        const content = document.getElementById('wallet-content');

        if (Array.isArray(rawList) && rawList.length > 0) {
            let html = '';
            rawList.forEach(item => {
                let typeText = '⚙️ عملية';
                let amountColor = '#10b981';
                
                const itemType = String(item.type || '').toLowerCase();

                if (itemType === 'deposit') {
                    typeText = '🟢 إيداع TON';
                    amountColor = '#10b981';
                } else if (itemType === 'withdraw' || itemType === 'withdrawal') {
                    typeText = '🔴 سحب أرباح';
                    amountColor = '#ef4444';
                } else if (itemType === 'convert' || itemType === 'conversion') {
                    typeText = '🔄 تحويل نقاط ZN';
                    amountColor = '#0098ea';
                }

                let statusText = 'مكتمل ✅';
                let statusColor = '#10b981';
                const status = String(item.status || '').toLowerCase();

                if (status === 'pending' || status === 'processing') {
                    statusText = 'قيد المراجعة ⏳';
                    statusColor = '#f59e0b';
                } else if (status === 'rejected' || status === 'cancelled' || status === 'failed') {
                    statusText = 'مرفوض ❌';
                    statusColor = '#ef4444';
                }

                const dateVal = item.created_at || item.date || item.timestamp;
                const dateStr = dateVal ? new Date(dateVal).toLocaleString('en-US', {
                    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit'
                }) : '';

                const rawAmount = parseFloat(item.amount_usd || item.amount || (item.amount_zn ? item.amount_zn / 1000000 : 0));
                const displayAmount = rawAmount.toFixed(2);
                
                html += `
                    <div style="background: rgba(10, 13, 20, 0.5); padding: 12px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; border: 1px solid rgba(255,255,255,0.05);">
                        <div>
                            <div style="font-weight: bold; color: #fff; font-size: 14px;">${typeText}</div>
                            <div style="font-size: 11px; color: #94a3b8; margin-top: 3px;" class="num-en">${dateStr}</div>
                        </div>
                        <div style="text-align: left;">
                            <div style="color: ${amountColor}; font-weight: 800; font-size: 15px;" class="num-en">$${displayAmount}</div>
                            <div style="font-size: 11px; color: ${statusColor}; font-weight:600; margin-top: 3px;">${statusText}</div>
                        </div>
                    </div>`;
            });

            if (container) {
                container.innerHTML = html;
            } else if (content) {
                content.innerHTML = `<div class="card" style="padding: 16px;">
                    <h3 style="margin-top:0; color:#fff; text-align:center; font-size:16px; margin-bottom:15px;">📋 سجل المعاملات</h3>
                    <div id="history-items-container" style="display: flex; flex-direction: column; gap: 10px; max-height: 380px; overflow-y: auto;">
                        ${html}
                    </div></div>`;
            }
        } else {
            if (content) {
                content.innerHTML = `
                    <div class="card" style="text-align:center; color:#94a3b8; padding:40px 20px;">
                        <div style="font-size:40px; margin-bottom:10px;">📥</div>
                        لا توجد عمليات سابقة مسجلة
                    </div>`;
            }
        }
    };

    window.loadHistoryData = function() {
        const now = Date.now();
        if (historyCache && (now - historyCacheTime < HISTORY_CACHE_TTL)) {
            window.renderHistoryListUI(historyCache);
        } else {
            const content = document.getElementById('wallet-content');
            if (content) {
                content.innerHTML = `
                    <div class="card" style="text-align:center; color:#94a3b8; padding:30px;">
                        <div style="font-size:32px; margin-bottom:10px;">⏳</div>
                        جاري جلب سجل المعاملات...
                    </div>`;
            }

            const payload = window.getAuthPayload?.();
            window.apiCall('/api/wallet/history/get', 'POST', payload).then((data) => {
                const rawList = data?.history || data?.transactions || data?.data || [];
                historyCache = rawList;
                historyCacheTime = Date.now();
                window.renderHistoryListUI(rawList);
            }).catch(() => {
                window.renderHistoryListUI([]);
            });
        }
    };
})();


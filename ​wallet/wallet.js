// ==========================================
// إدارة المحفظة الرئيسية والتحويل بين التبويبات
// ==========================================
(function() {
    window.currentWalletTab = window.currentWalletTab || 'deposit';

    window.initWalletView = function() {
        if (typeof window.updateUI === 'function') window.updateUI();
        window.switchWalletTab(window.currentWalletTab);
    };

    window.switchWalletTab = function(tabName) {
        window.currentWalletTab = tabName;

        const tabs = ['deposit', 'history', 'withdraw'];
        tabs.forEach(t => {
            const btn = document.getElementById(`btn-tab-${t}`);
            if (btn) {
                if (t === tabName) {
                    btn.style.background = '#0088cc';
                    btn.style.color = '#ffffff';
                    btn.style.border = 'none';
                } else {
                    btn.style.background = 'rgba(255,255,255,0.08)';
                    btn.style.color = '#cccccc';
                    btn.style.border = '1px solid rgba(255,255,255,0.1)';
                }
            }
        });

        const container = document.getElementById('wallet-sub-content');
        if (!container) return;

        if (tabName === 'deposit') {
            if (typeof window.renderDepositView === 'function') window.renderDepositView(container);
        } else if (tabName === 'history') {
            if (typeof window.renderHistoryView === 'function') window.renderHistoryView(container);
        } else if (tabName === 'withdraw') {
            if (typeof window.renderWithdrawView === 'function') window.renderWithdrawView(container);
        }
    };

    window.onWalletTabOpen = window.initWalletView;

    if (document.getElementById('view-wallet')?.classList.contains('active')) {
        window.initWalletView();
    }
})();

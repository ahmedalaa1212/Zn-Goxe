// ==========================================
// 💳 جافاسكريبت إدارة تبويبات المحفظة
// ==========================================

window.currentWalletTab = 'deposit';

window.initWalletView = function() {
    if (typeof window.updateUI === 'function') window.updateUI();
    window.switchWalletTab(window.currentWalletTab || 'deposit');
};

window.onWalletTabOpen = function() {
    if (typeof window.updateUI === 'function') window.updateUI();
};

window.switchWalletTab = async function(tabName) {
    window.currentWalletTab = tabName;

    // 1. تحديث شكل الأزرار
    const tabs = ['deposit', 'withdraw', 'history'];
    tabs.forEach(t => {
        const btn = document.getElementById(`tab-btn-${t}`);
        if (btn) {
            if (t === tabName) {
                btn.style.background = '#3b82f6';
                btn.style.color = '#ffffff';
            } else {
                btn.style.background = 'transparent';
                btn.style.color = '#94a3b8';
            }
        }
    });

    // 2. تحميل واجهة القائمة المطلوبة ديناميكياً
    const folderPath = `wallet/${tabName}`;
    const containerId = 'sub-wallet-content';
    
    if (typeof window.loadSubModule === 'function') {
        await window.loadSubModule(folderPath, containerId);
    }

    // 3. استدعاء دالة التهيئة الخاصة بكل قائمة فرعية إذا كانت موجودة
    const initSubFuncName = `init${tabName.charAt(0).toUpperCase() + tabName.slice(1)}View`;
    if (typeof window[initSubFuncName] === 'function') {
        window[initSubFuncName]();
    }
};

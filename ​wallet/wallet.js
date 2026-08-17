window.walletModule = (function () {
    let currentTab = 'deposit';

    // جلب تحديث الأرصدة من السيرفر
    async function fetchWalletBalances() {
        try {
            const userId = window.Telegram?.WebApp?.initDataUnsafe?.user?.id || '';
            const res = await fetch(`/api/wallet/data?user_id=${userId}`);
            if (!res.ok) return;
            const data = await res.json();
            
            if (data.success) {
                const znElem = document.getElementById('zn-balance-display');
                const usdtElem = document.getElementById('usdt-balance-display');
                
                if (znElem) znElem.innerText = Number(data.zn_balance || 0).toFixed(2);
                if (usdtElem) usdtElem.innerText = Number(data.usdt_balance || 0).toFixed(2);
            }
        } catch (err) {
            console.error("خطأ في تحديث أرصدة المحفظة:", err);
        }
    }

    // التنقل بين القوائم الثلاثة وتحميل ملفاتها الفرعية
    async function switchTab(tabName) {
        currentTab = tabName;

        // تحديث حالة الأزرار
        ['deposit', 'history', 'withdraw'].forEach(t => {
            const btn = document.getElementById(`tab-btn-${t}`);
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

        const container = document.getElementById('wallet-subview-container');
        if (!container) return;

        try {
            // المحاولة بمسارات متعددة لضمان التحميل بغض النظر عن المسار الحالي
            let response = await fetch(`/wallet/${tabName}/${tabName}.html`);
            if (!response.ok) {
                response = await fetch(`wallet/${tabName}/${tabName}.html`);
            }

            if (response.ok) {
                container.innerHTML = await response.text();
                
                // تشغيل دالة التهيئة المخصصة للقائمة الفرعية إن وجدت
                const initFuncName = `init_${tabName}_module`;
                if (typeof window[initFuncName] === 'function') {
                    window[initFuncName]();
                }
            } else {
                container.innerHTML = `<div style="text-align:center; padding:20px; color:#aaa;">تعذر تحميل واجهة ${tabName}</div>`;
            }
        } catch (e) {
            console.error(`فشل تحميل واجهة ${tabName}:`, e);
        }
    }

    function init() {
        fetchWalletBalances();
        switchTab('deposit');
    }

    return {
        init,
        switchTab,
        fetchWalletBalances
    };
})();

// تشغيل عند الجاهزية المباشرة أو عند تحميل DOM
if (document.getElementById('wallet-subview-container')) {
    window.walletModule.init();
}
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('wallet-subview-container')) {
        window.walletModule.init();
    }
});

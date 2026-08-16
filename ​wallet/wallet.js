// ==========================================
// موديول المحفظة الرئيسي (Wallet Controller)
// ==========================================

window.activeWalletTab = 'deposit';
const loadedWalletSubmodules = new Set();

window.onWalletTabOpen = function() {
    window.updateWalletHeaderUI();
    
    // فتح آخر تبويب نشط أو الافتراضي (الإيداع)
    if (!document.getElementById('wallet-subview-container')?.firstElementChild || 
        document.getElementById('wallet-subview-container')?.querySelector('.wallet-loading-spinner')) {
        window.switchWalletTab(window.activeWalletTab || 'deposit');
    }
};

window.updateWalletHeaderUI = function() {
    const znBal = parseFloat(window.userState?.balance || 0);
    const usdBal = parseFloat(window.userState?.usd_balance || 0);

    const znEl = document.getElementById('wallet-zn-balance');
    const usdEl = document.getElementById('wallet-usd-balance');

    if (znEl) znEl.innerText = `${window.formatBalance(znBal)} ZN`;
    if (usdEl) usdEl.innerText = `$${window.formatBalance(usdBal)} USD`;

    if (typeof window.updateTonPriceUI === 'function') {
        window.updateTonPriceUI();
    }
};

window.switchWalletTab = async function(tabName) {
    window.activeWalletTab = tabName;

    // تحديث شكل الأزرار النشطة
    document.querySelectorAll('.wallet-tab-btn').forEach(btn => btn.classList.remove('active'));
    const activeBtn = document.getElementById(`tab-btn-${tabName}`);
    if (activeBtn) activeBtn.classList.add('active');

    const container = document.getElementById('wallet-subview-container');
    if (!container) return;

    // إظهار مؤشر التحميل
    container.innerHTML = `
        <div class="wallet-loading-spinner">
            <i class="fas fa-circle-notch fa-spin"></i>
            <p>جاري تحميل قسم ${getTabTitle(tabName)}...</p>
        </div>
    `;

    try {
        const cacheBuster = `?v=${Date.now()}`;
        const htmlPath = `wallet/${tabName}/${tabName}.html${cacheBuster}`;
        const jsPath = `wallet/${tabName}/${tabName}.js${cacheBuster}`;

        const res = await fetch(htmlPath);
        if (res.ok) {
            const html = await res.text();
            container.innerHTML = html;

            // تحميل سكربت القسم الفرعي
            await loadWalletSubScript(jsPath);

            // تشغيل دالة التهيئة المخصصة للقسم
            const initFuncName = `init${tabName.charAt(0).toUpperCase() + tabName.slice(1)}View`;
            if (typeof window[initFuncName] === 'function') {
                window[initFuncName]();
            }
        } else {
            container.innerHTML = `
                <div style="text-align: center; padding: 30px; color: #ef4444;">
                    <i class="fas fa-exclamation-triangle" style="font-size: 2.5rem; margin-bottom: 10px;"></i>
                    <p>عفواً، تعذر تحميل واجهة ${getTabTitle(tabName)}.</p>
                </div>
            `;
        }
    } catch (err) {
        console.error(`[Wallet] Error loading subtab ${tabName}:`, err);
        container.innerHTML = `
            <div style="text-align: center; padding: 30px; color: #ef4444;">
                <i class="fas fa-wifi" style="font-size: 2.5rem; margin-bottom: 10px;"></i>
                <p>حدث خطأ أثناء الاتصال بالشبكة.</p>
            </div>
        `;
    }
};

function loadWalletSubScript(scriptUrl) {
    return new Promise((resolve) => {
        const cleanUrl = scriptUrl.split('?')[0];
        const existing = document.querySelector(`script[src*="${cleanUrl}"]`);
        if (existing) existing.remove();

        const script = document.createElement('script');
        script.src = scriptUrl;
        script.onload = () => resolve();
        script.onerror = () => resolve();
        document.body.appendChild(script);
    });
}

function getTabTitle(tabName) {
    switch (tabName) {
        case 'deposit': return 'الإيداع';
        case 'withdraw': return 'السحب';
        case 'history': return 'السجلات';
        default: return tabName;
    }
}

// استماع لحدث تحديث الرصيد لإعادة التحديث تلقائياً
window.addEventListener('userStateUpdated', () => {
    if (document.getElementById('view-wallet')?.classList.contains('active')) {
        window.updateWalletHeaderUI();
    }
});

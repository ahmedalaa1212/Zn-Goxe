window.offersModule = (function() {

    function updateRealBalanceDisplay() {
        const realBal = parseFloat(window.userState?.balance || 0);
        const balEl = document.getElementById('offers-real-balance');
        if (balEl) {
            balEl.innerHTML = `${window.formatBalance(realBal)} ZN`;
        }
    }

    async function openSubModule(moduleFolder) {
        const modal = document.getElementById('sub-module-modal');
        const contentEl = document.getElementById('sub-module-content');
        if (!modal || !contentEl) return;

        contentEl.innerHTML = `<div style="text-align: center; padding: 30px; color: #aaa;">جاري الفتح...</div>`;
        modal.style.display = 'flex';

        try {
            // جلب ملف الـ HTML الخاص بالمجلد الفرعي ديناميكياً
            const response = await fetch(`/offers/${moduleFolder}/${moduleFolder}.html`);
            if (response.ok) {
                const htmlText = await response.text();
                contentEl.innerHTML = htmlText;
            } else {
                contentEl.innerHTML = `<div style="text-align: center; color: #ff4d4d; padding: 20px;">تعذر تحميل القائمة الفرعية.</div>`;
            }
        } catch (err) {
            console.error("Failed to load submodule view:", err);
            contentEl.innerHTML = `<div style="text-align: center; color: #ff4d4d; padding: 20px;">حدث خطأ في تحميل القائمة.</div>`;
        }
    }

    function closeSubModule() {
        const modal = document.getElementById('sub-module-modal');
        if (modal) modal.style.display = 'none';
    }

    function init() {
        updateRealBalanceDisplay();
    }

    return {
        init: init,
        openSubModule: openSubModule,
        closeSubModule: closeSubModule
    };
})();

window.onOffersTabOpen = function() {
    if (window.offersModule) window.offersModule.init();
};

window.addEventListener('userStateUpdated', () => {
    if (document.getElementById('view-offers')?.classList.contains('active')) {
        const balEl = document.getElementById('offers-real-balance');
        if (balEl && window.userState?.balance !== undefined) {
            balEl.innerHTML = `${window.formatBalance(window.userState.balance)} ZN`;
        }
    }
});

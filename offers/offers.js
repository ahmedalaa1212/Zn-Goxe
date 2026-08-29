window.offersModule = (function() {

    // تحديث عرض الرصيد الفعلي فقط
    function updateRealBalanceDisplay() {
        const realBal = parseFloat(window.userState?.balance || 0);
        const balEl = document.getElementById('offers-real-balance');
        if (balEl) {
            balEl.innerHTML = `${window.formatBalance(realBal)} ZN`;
        }
    }

    // فتح المجلد الفرعي الخاص بكل قائمة من الـ 8
    async function openSubModule(moduleKey) {
        const modal = document.getElementById('sub-module-modal');
        const titleEl = document.getElementById('sub-module-title');
        const contentEl = document.getElementById('sub-module-content');

        if (!modal || !titleEl || !contentEl) return;

        const moduleTitles = {
            'goxe': 'عرض Goxe',
            'fogo': 'عرض fuego',
            'hitob': 'عرض hitob',
            'wex': 'عرض wex',
            'vover': 'عرض vover',
            'znzn': 'عرض znzn',
            'blxe': 'عرض Blxe',
            'extra': 'عرض Extra'
        };

        titleEl.innerText = moduleTitles[moduleKey] || 'القائمة الفرعية';
        contentEl.innerHTML = `<div style="text-align: center; padding: 20px; color: #aaa;">جاري الاتصال بـ ${moduleTitles[moduleKey]}...</div>`;
        modal.style.display = 'flex';

        try {
            // طلب بيانات أو واجهة المجلد الفرعي من الـ API
            const res = await window.fetchAPI(`/api/offers/${moduleKey}/data`);
            
            if (res && res.success) {
                // إذا كان للمجلد الفرعي واجهة أو مهام خاصة يتم عرضها هنا
                if (res.html) {
                    contentEl.innerHTML = res.html;
                } else if (res.items && res.items.length > 0) {
                    contentEl.innerHTML = res.items.map(item => `
                        <div style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 12px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <div style="font-weight: bold; font-size: 13px; color: #fff;">${item.title}</div>
                                <div style="font-size: 11px; color: #2ec4b6;">+${item.reward} ZN (رصيد فعلي)</div>
                            </div>
                            <button onclick="window.offersModule.claimSubTask('${moduleKey}', '${item.id}')" style="background: #2ec4b6; color: #000; border: none; padding: 6px 14px; border-radius: 8px; font-weight: bold; font-size: 12px; cursor: pointer;">
                                تنفيذ
                            </button>
                        </div>
                    `).join('');
                } else {
                    contentEl.innerHTML = `<p style="color: #aaa; text-align: center; font-size: 13px;">لا توجد مهام متاحة في هذه القائمة حالياً.</p>`;
                }
            } else {
                contentEl.innerHTML = `<p style="color: #ff4d4d; text-align: center; font-size: 13px;">${res.error || 'فشل تحميل القائمة'}</p>`;
            }
        } catch (err) {
            contentEl.innerHTML = `<p style="color: #ff4d4d; text-align: center; font-size: 13px;">حدث خطأ أثناء تحميل القائمة الفرعية.</p>`;
        }
    }

    // إغلاق نافذة القائمة الفرعية
    function closeSubModule() {
        const modal = document.getElementById('sub-module-modal');
        if (modal) modal.style.display = 'none';
    }

    // تنفيذ مهمة داخل مجلد فرعي
    async function claimSubTask(moduleKey, taskId) {
        try {
            const res = await window.fetchAPI(`/api/offers/${moduleKey}/claim`, 'POST', { task_id: taskId });
            if (res && res.success) {
                if (res.new_balance !== undefined) {
                    window.userState.balance = parseFloat(res.new_balance);
                }
                updateRealBalanceDisplay();
                alert(`🎉 تم إضافة ${res.reward || 0} ZN إلى رصيدك الفعلي.`);
                closeSubModule();
            } else {
                alert(res.error || 'فشل استلام المكافأة.');
            }
        } catch (err) {
            alert(err.message || 'حدث خطأ أثناء التنفيذ.');
        }
    }

    function init() {
        updateRealBalanceDisplay();
    }

    return {
        init: init,
        openSubModule: openSubModule,
        closeSubModule: closeSubModule,
        claimSubTask: claimSubTask
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

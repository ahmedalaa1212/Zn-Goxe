window.offersModule = (function() {
    function updateRealBalanceDisplay() {
        const realBal = parseFloat(window.userState?.balance || 0);
        const balEl = document.getElementById('offers-real-balance');
        if (balEl) {
            balEl.innerHTML = `${window.formatBalance(realBal)} ZN`;
        }
    }

    async function initOffersView() {
        updateRealBalanceDisplay();
    }

    async function openCategory(categoryKey) {
        const modal = document.getElementById('offer-modal');
        const titleEl = document.getElementById('modal-offer-title');
        const tasksEl = document.getElementById('modal-offer-tasks');

        if (!modal || !titleEl || !tasksEl) return;

        const categoryNames = {
            'offer_goxe': 'عرض Goxe',
            'offer_fogo': 'عرض fuego',
            'offer_hitob': 'عرض hitob',
            'offer_wex': 'عرض wex',
            'offer_vover': 'عرض vover',
            'offer_znzn': 'عرض znzn',
            'offer_blxe': 'عرض Blxe',
            'offer_extra': 'عرض Extra'
        };

        titleEl.innerText = categoryNames[categoryKey] || 'عرض خاص';
        tasksEl.innerHTML = `<p style="color: #aaa; text-align: center; font-size: 13px;">جاري تحميل المهام المتاحة...</p>`;
        modal.style.display = 'flex';

        try {
            const res = await window.fetchAPI(`/api/offers/tasks?category=${categoryKey}`);
            if (res && res.success && res.tasks && res.tasks.length > 0) {
                tasksEl.innerHTML = res.tasks.map(task => `
                    <div style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 12px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <div style="font-weight: bold; font-size: 13px; color: #fff;">${task.title}</div>
                            <div style="font-size: 11px; color: #2ec4b6;">+${task.reward} ZN (رصيد فعلي)</div>
                        </div>
                        <button onclick="window.offersModule.claimOfferTask('${task.id}')" style="background: #2ec4b6; color: #000; border: none; padding: 6px 14px; border-radius: 8px; font-weight: bold; font-size: 12px; cursor: pointer;">
                            استلام
                        </button>
                    </div>
                `).join('');
            } else {
                tasksEl.innerHTML = `<p style="color: #aaa; text-align: center; font-size: 13px;">لا توجد مهام متاحة في هذا العرض حالياً.</p>`;
            }
        } catch (err) {
            tasksEl.innerHTML = `<p style="color: #ff4d4d; text-align: center; font-size: 13px;">حدث خطأ أثناء تحميل المهام.</p>`;
        }
    }

    async function claimOfferTask(taskId) {
        try {
            const res = await window.fetchAPI('/api/offers/claim', 'POST', { task_id: taskId });
            if (res && res.success) {
                if (res.new_balance !== undefined) {
                    window.userState.balance = parseFloat(res.new_balance);
                }
                updateRealBalanceDisplay();
                alert(`🎉 مبروك! تم إضافة ${res.reward || 0} ZN إلى رصيدك الفعلي.`);
                closeOfferModal();
            } else {
                alert(res.error || 'عذراً، فشل استلام العرض.');
            }
        } catch (err) {
            alert(err.message || 'حدث خطأ غير متوقع.');
        }
    }

    window.closeOfferModal = function() {
        const modal = document.getElementById('offer-modal');
        if (modal) modal.style.display = 'none';
    };

    window.openOfferCategory = openCategory;

    return {
        init: initOffersView,
        openCategory: openCategory,
        claimOfferTask: claimOfferTask
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

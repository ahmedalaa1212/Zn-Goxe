window.initOffersView = function() {
    console.log("⚡ تم تهيئة قائمة أرباح العروض بنجاح");

    const cards = document.querySelectorAll('.offer-card');
    cards.forEach(card => {
        card.addEventListener('click', function() {
            const offerId = this.getAttribute('data-offer-id');
            window.openOfferFolder(offerId);
        });
    });

    if (typeof window.updateUI === 'function') {
        window.updateUI();
    }
};

window.onOffersTabOpen = window.initOffersView;

// دالة التوجيه والدخول للمجلدات الفرعية الـ 8
window.openOfferFolder = function(offerId) {
    console.log(`فتح مجلد العرض رقم: ${offerId}`);
    // سيتم التوجيه وتحميل الـ 4 ملفات التابعة لمجلد العرض المحدد
    alert(`جاري فتح مجلد العرض رقم [${offerId}]...`);
};

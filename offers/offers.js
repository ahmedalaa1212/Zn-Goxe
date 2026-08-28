window.onOffersTabOpen = async function() {
    await window.loadOffersList();
};

window.loadOffersList = async function() {
    const container = document.getElementById('offers-list');
    if (!container) return;

    try {
        const res = await window.fetchAPI('/api/offers/list', 'GET');
        if (res && res.success && Array.isArray(res.offers)) {
            window.renderOffers(res.offers);
        } else {
            container.innerHTML = `<div style="text-align: center; padding: 20px; color: #ff5252;">${res?.error || 'فشل جلب قائمة العروض'}</div>`;
        }
    } catch (err) {
        console.error("خطأ تحميل العروض:", err);
        container.innerHTML = `<div style="text-align: center; padding: 20px; color: #ff5252;">حدث خطأ أثناء الاتصال بالسيرفر.</div>`;
    }
};

window.renderOffers = function(offers) {
    const container = document.getElementById('offers-list');
    if (!container) return;

    if (offers.length === 0) {
        container.innerHTML = `<div style="text-align: center; padding: 30px; color: #888;">لا توجد عروض متاحة حالياً.</div>`;
        return;
    }

    let html = '';
    offers.forEach(offer => {
        const isCompleted = offer.completed;
        let rewardText = `+${window.formatBalance(offer.reward_amount)} ZN`;
        
        if (offer.reward_type === 'usd_balance') {
            rewardText = `+$${window.formatBalance(offer.reward_amount)}`;
        } else if (offer.reward_type === 'ad_balance') {
            rewardText = `+${window.formatBalance(offer.reward_amount)} AdZN`;
        } else if (offer.reward_type === 'hybrid') {
            rewardText = `+${window.formatBalance(offer.reward_amount)} ZN +${window.formatBalance(offer.secondary_reward_amount)} AdZN`;
        }

        html += `
            <div class="offer-card" id="offer-card-${offer.id}">
                <div class="offer-info">
                    <div class="offer-icon">${offer.icon || '🎁'}</div>
                    <div class="offer-details">
                        <h4>${offer.title}</h4>
                        <p>${offer.description}</p>
                        <div class="offer-reward">${rewardText}</div>
                    </div>
                </div>
                <div>
                    ${isCompleted 
                        ? `<button class="offer-btn completed" disabled>مكتمل ✅</button>` 
                        : `<button class="offer-btn" onclick="window.handleOfferClick('${offer.id}', '${offer.action_url || ''}')">تنفيذ العرض 🚀</button>`
                    }
                </div>
            </div>
        `;
    });

    container.innerHTML = html;
};

window.handleOfferClick = async function(offerId, actionUrl) {
    if (actionUrl && actionUrl.trim() !== '') {
        if (window.Telegram?.WebApp?.openTelegramLink && actionUrl.includes('t.me')) {
            window.Telegram.WebApp.openTelegramLink(actionUrl);
        } else {
            window.open(actionUrl, '_blank');
        }
    }

    setTimeout(async () => {
        await window.claimOfferReward(offerId);
    }, 1500);
};

window.claimOfferReward = async function(offerId) {
    try {
        const res = await window.fetchAPI('/api/offers/claim', 'POST', { offer_id: offerId });
        if (res && res.success) {
            alert(res.message || 'تم استلام المكافأة بنجاح!');
            if (res.player) {
                Object.assign(window.userState, res.player);
            }
            await window.loadOffersList();
        } else {
            alert(res?.error || 'تعذر استلام المكافأة.');
        }
    } catch (e) {
        alert(e.message || 'حدث خطأ أثناء الاتصال بالسيرفر.');
    }
};

if (document.getElementById('view-offers')?.classList.contains('active')) {
    window.onOffersTabOpen();
}


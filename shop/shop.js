(function initShop() {
    const miningPackages = [
        { level: 1, price: 1000, boost: 500 }, { level: 2, price: 3000, boost: 1200 },
        { level: 3, price: 7000, boost: 2500 }, { level: 4, price: 15000, boost: 5000 },
        { level: 5, price: 30000, boost: 10000 }, { level: 6, price: 60000, boost: 22000 },
        { level: 7, price: 120000, boost: 45000 }, { level: 8, price: 250000, boost: 100000 },
        { level: 9, price: 500000, boost: 250000 }, { level: 10, price: 1000000, boost: 600000 }
    ];

    const storagePackages = [
        { level: 1, price: 2000, cap: "20,000" }, { level: 2, price: 5000, cap: "30,000" },
        { level: 3, price: 10000, cap: "50,000" }, { level: 4, price: 25000, cap: "100,000" },
        { level: 5, price: 50000, cap: "250,000" }, { level: 6, price: 100000, cap: "500,000" },
        { level: 7, price: 250000, cap: "1,000,000" }, { level: 8, price: 500000, cap: "2,500,000" }
    ];

    let currentActiveTab = 'mining';

    window.updateShopUI = function() {
        const pData = window.PlayerData;
        const balanceEl = document.getElementById('shop-zn-balance');
        if (balanceEl) balanceEl.innerText = pData.balance.toLocaleString();
        
        renderShopTab(currentActiveTab);
    };

    window.renderShopTab = function(tab) {
        currentActiveTab = tab;
        const pData = window.PlayerData;
        const content = document.getElementById('shop-content');
        if (!content) return;
        
        content.innerHTML = '';
        
        const btnMining = document.getElementById('btn-mining');
        const btnStorage = document.getElementById('btn-storage');
        if (btnMining) btnMining.style.background = (tab === 'mining') ? '#0088cc' : '#222';
        if (btnStorage) btnStorage.style.background = (tab === 'storage') ? '#0088cc' : '#222';

        if (tab === 'mining') {
            miningPackages.forEach(item => {
                let count = pData.upgrades[`lvl${item.level}`] || 0;
                let isMaxed = count >= 20;
                content.innerHTML += `
                    <div style="background:#1c1c1c; margin-bottom:10px; padding:15px; border-radius:10px; border:1px solid ${isMaxed ? '#333' : '#00cc66'};">
                        <div style="display:flex; justify-content:space-between; margin-bottom:5px;">
                            <b>مستوى ${item.level}</b>
                            <span>الترقيات: ${count}/20</span>
                        </div>
                        <button onclick="checkAndBuy('mining', ${item.level}, ${item.price})" style="width:100%; padding:10px; background:${isMaxed ? '#333' : '#00cc66'}; border:none; color:white; border-radius:5px; font-weight:bold; cursor:pointer;">
                            ${isMaxed ? 'تم الانتهاء' : 'شراء بـ ' + item.price.toLocaleString()}
                        </button>
                    </div>`;
            });
        } else {
            storagePackages.forEach(item => {
                let isBought = item.level <= pData.storage_level;
                let isNext = item.level === pData.storage_level + 1;
                
                content.innerHTML += `
                    <div style="background:#1c1c1c; margin-bottom:10px; padding:15px; border-radius:10px; border:1px solid ${isBought ? '#333' : (isNext ? '#00cc66' : '#222')}; display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <b>مستوى ${item.level}</b>
                            <div style="font-size:12px; color:#aaa;">السعة: ${item.cap} ZN</div>
                        </div>
                        <button onclick="${isNext ? `checkAndBuy('storage', ${item.level}, ${item.price})` : ''}" style="padding:10px; background:${isBought ? '#333' : (isNext ? '#00cc66' : '#222')}; border:none; color:white; border-radius:5px; font-weight:bold; cursor:${isNext ? 'pointer' : 'default'};">
                            ${isBought ? 'تم الشراء' : (isNext ? 'شراء بـ ' + item.price.toLocaleString() : 'مغلق')}
                        </button>
                    </div>`;
            });
        }
    };

    window.checkAndBuy = function(type, level, price) {
        const pData = window.PlayerData;
        const modal = document.getElementById('msg-modal');
        if (!modal) return;
        
        const msgEl = document.getElementById('modal-msg');
        const actionsEl = document.getElementById('modal-actions');
        
        if (pData.balance < price) {
            msgEl.innerText = "عذراً، رصيدك غير كافٍ!";
            actionsEl.innerHTML = `<button onclick="closeModal()" style="padding:10px 20px; background:#cc0000; border:none; color:white; border-radius:5px; font-weight:bold; cursor:pointer;">إغلاق</button>`;
        } else {
            msgEl.innerText = `هل تريد شراء الترقية مقابل ${price.toLocaleString()} ZN؟`;
            actionsEl.innerHTML = `
                <button onclick="closeModal()" style="padding:10px 20px; background:#444; border:none; color:white; border-radius:5px; margin-left:10px; font-weight:bold; cursor:pointer;">إلغاء</button>
                <button onclick="executePurchase('${type}', ${level})" style="padding:10px 20px; background:#00cc66; border:none; color:white; border-radius:5px; font-weight:bold; cursor:pointer;">تأكيد</button>
            `;
        }
        modal.style.display = 'flex';
    };

    window.executePurchase = async function(type, level) {
        const pData = window.PlayerData;
        closeModal();
        try {
            let response = await fetch('/api/upgrade', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    tg_id: pData.tg_id,
                    type: type,
                    level_num: level
                })
            });
            if (response.ok) {
                await pData.fetchUpdates();
            }
        } catch (e) {
            console.error("Upgrade error:", e);
        }
    };

    window.closeModal = function() { 
        const modal = document.getElementById('msg-modal');
        if (modal) modal.style.display = 'none'; 
    };

    // فحص دوري لتعبئة المتجر أوتوماتيكياً لو كان معروضاً وفارغاً
    setInterval(() => {
        const shopSection = document.getElementById('main-shop-section');
        const shopContent = document.getElementById('shop-content');
        if (shopSection && shopContent) {
            if (shopSection.style.display !== 'none' && window.getComputedStyle(shopSection).display !== 'none' && shopContent.innerHTML === '') {
                window.updateShopUI();
            }
        }
    }, 300);
})();

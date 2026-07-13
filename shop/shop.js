let playerZnBalance = 15400;
let miningUpgrades = {1:0, 2:0, 3:0, 4:0, 5:0, 6:0, 7:0, 8:0, 9:0, 10:0};
let currentStorageLevel = 0;

const miningPackages = [
    { level: 1, price: 1000, boost: 500 }, { level: 2, price: 3000, boost: 1200 },
    { level: 3, price: 7000, boost: 2500 }, { level: 4, price: 15000, boost: 5000 },
    { level: 5, price: 30000, boost: 10000 }, { level: 6, price: 60000, boost: 22000 },
    { level: 7, price: 120000, boost: 45000 }, { level: 8, price: 250000, boost: 100000 },
    { level: 9, price: 500000, boost: 250000 }, { level: 10, price: 1000000, boost: 600000 }
];

// التأكد من تحميل العناصر أول ما الصفحة تفتح
document.addEventListener('DOMContentLoaded', () => {
    renderShopTab('mining');
});

function renderShopTab(tab) {
    const content = document.getElementById('shop-content');
    content.innerHTML = '';
    document.getElementById('btn-mining').style.background = (tab === 'mining') ? '#0088cc' : '#222';
    document.getElementById('btn-storage').style.background = (tab === 'storage') ? '#0088cc' : '#222';

    if (tab === 'mining') {
        miningPackages.forEach(item => {
            let count = miningUpgrades[item.level];
            let isMaxed = count >= 20;
            content.innerHTML += `<div style="background:#1c1c1c; margin-bottom:10px; padding:15px; border-radius:10px; border:1px solid ${isMaxed ? '#333' : '#00cc66'};">
                <div style="display:flex; justify-content:space-between; margin-bottom:5px;"><b>مستوى ${item.level}</b><span>الترقيات: ${count}/20</span></div>
                <button onclick="checkAndBuy('mining', ${item.level}, ${item.price})" style="width:100%; padding:10px; background:${isMaxed ? '#333' : '#00cc66'}; border:none; color:white; border-radius:5px;">
                    ${isMaxed ? 'تم الانتهاء' : 'شراء بـ ' + item.price.toLocaleString()}
                </button>
            </div>`;
        });
    }
}

function checkAndBuy(type, level, price) {
    const modal = document.getElementById('msg-modal');
    const msg = document.getElementById('modal-msg');
    const actions = document.getElementById('modal-actions');
    
    modal.style.display = 'flex';
    
    if (playerZnBalance < price) {
        msg.innerText = "عذراً، رصيدك غير كافٍ!";
        actions.innerHTML = `<button onclick="closeModal()" style="padding:10px 20px; background:#cc0000; border:none; color:white; border-radius:5px;">إغلاق</button>`;
    } else {
        msg.innerText = `هل تريد شراء ترقية مقابل ${price.toLocaleString()} ZN؟`;
        actions.innerHTML = `
            <button onclick="closeModal()" style="padding:10px 20px; background:#444; border:none; color:white; border-radius:5px; margin-left:10px;">إلغاء</button>
            <button onclick="executePurchase('${type}', ${level}, ${price})" style="padding:10px 20px; background:#00cc66; border:none; color:white; border-radius:5px;">تأكيد</button>`;
    }
}

function executePurchase(type, level, price) {
    playerZnBalance -= price;
    document.getElementById('shop-zn-balance').innerText = playerZnBalance.toLocaleString();
    if (type === 'mining') miningUpgrades[level]++;
    closeModal();
    renderShopTab(type);
}

function closeModal() { document.getElementById('msg-modal').style.display = 'none'; }

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

const storagePackages = [
    { level: 1, price: 2000, cap: "20,000" }, { level: 2, price: 5000, cap: "30,000" },
    { level: 3, price: 10000, cap: "50,000" }, { level: 4, price: 25000, cap: "100,000" },
    { level: 5, price: 50000, cap: "250,000" }, { level: 6, price: 100000, cap: "500,000" },
    { level: 7, price: 250000, cap: "1,000,000" }, { level: 8, price: 500000, cap: "2,500,000" }
];

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
    } else {
        storagePackages.forEach(item => {
            let isBought = item.level <= currentStorageLevel;
            content.innerHTML += `<div style="background:#1c1c1c; margin-bottom:10px; padding:15px; border-radius:10px; border:1px solid ${isBought ? '#333' : '#00cc66'}; display:flex; justify-content:space-between; align-items:center;">
                <div><b>مستوى ${item.level}</b><div style="font-size:12px; color:#aaa;">السعة: ${item.cap} ZN</div></div>
                <button onclick="checkAndBuy('storage', ${item.level}, ${item.price})" style="padding:10px; background:${isBought ? '#333' : '#00cc66'}; border:none; color:white; border-radius:5px;">
                    ${isBought ? 'تم الشراء' : 'شراء بـ ' + item.price.toLocaleString()}
                </button>
            </div>`;
        });
    }
}

function checkAndBuy(type, level, price) {
    const modal = document.getElementById('msg-modal');
    document.getElementById('modal-msg').innerText = playerZnBalance < price ? "عذراً، رصيدك غير كافٍ!" : `هل تريد شراء الترقية مقابل ${price.toLocaleString()} ZN؟`;
    document.getElementById('modal-actions').innerHTML = playerZnBalance < price ? 
        `<button onclick="closeModal()" style="padding:10px 20px; background:#cc0000; border:none; color:white; border-radius:5px;">إغلاق</button>` :
        `<button onclick="closeModal()" style="padding:10px 20px; background:#444; border:none; color:white; border-radius:5px; margin-left:10px;">إلغاء</button>
         <button onclick="executePurchase('${type}', ${level}, ${price})" style="padding:10px 20px; background:#00cc66; border:none; color:white; border-radius:5px;">تأكيد</button>`;
    modal.style.display = 'flex';
}

function executePurchase(type, level, price) {
    playerZnBalance -= price;
    document.getElementById('shop-zn-balance').innerText = playerZnBalance.toLocaleString();
    if (type === 'mining') miningUpgrades[level]++;
    else currentStorageLevel = level;
    closeModal();
    renderShopTab(type);
}
function closeModal() { document.getElementById('msg-modal').style.display = 'none'; }

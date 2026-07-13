let playerZnBalance = 15400;
let miningUpgrades = {1:0, 2:0, 3:0, 4:0, 5:0, 6:0, 7:0, 8:0, 9:0, 10:0};
let currentStorageLevel = 0;
let pendingPurchase = null;

const miningPackages = [
    { level: 1, price: 1000, boost: 500 }, { level: 2, price: 3000, boost: 1200 },
    { level: 3, price: 7000, boost: 2500 }, { level: 4, price: 15000, boost: 5000 },
    { level: 5, price: 30000, boost: 10000 }, { level: 6, price: 60000, boost: 22000 },
    { level: 7, price: 120000, boost: 45000 }, { level: 8, price: 250000, boost: 100000 },
    { level: 9, price: 500000, boost: 250000 }, { level: 10, price: 1000000, boost: 600000 }
];

const storagePackages = [
    { level: 1, price: 2000, capacity: "20,000" }, { level: 2, price: 5000, capacity: "30,000" },
    { level: 3, price: 10000, capacity: "50,000" }, { level: 4, price: 25000, capacity: "100,000" },
    { level: 5, price: 50000, capacity: "250,000" }, { level: 6, price: 100000, capacity: "500,000" },
    { level: 7, price: 250000, capacity: "1,000,000" }, { level: 8, price: 500000, capacity: "2,500,000" }
];

function renderShopTab(tab) {
    const content = document.getElementById('shop-content');
    content.innerHTML = '';
    
    document.getElementById('btn-mining').style.background = (tab === 'mining') ? '#0088cc' : '#222';
    document.getElementById('btn-storage').style.background = (tab === 'storage') ? '#0088cc' : '#222';

    if (tab === 'mining') {
        miningPackages.forEach(item => {
            let boughtCount = miningUpgrades[item.level];
            let isMaxed = boughtCount >= 20;
            content.innerHTML += `<div style="background:#1c1c1c; margin-bottom:10px; padding:15px; border-radius:10px; border:1px solid ${isMaxed ? '#333' : '#00cc66'};">
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                    <div><b>مستوى ${item.level}</b><div style="font-size:12px; color:#aaa;">السرعة: +${item.boost.toLocaleString()}</div></div>
                    <div style="font-size:12px; color:#00cc66; font-weight:bold;">الترقيات: ${boughtCount} / 20</div>
                </div>
                <button onclick="showConfirmModal('mining', ${item.level}, ${item.price})" style="width:100%; padding:10px; background:${isMaxed ? '#333' : '#00cc66'}; border:none; color:white; border-radius:8px;" ${isMaxed ? 'disabled' : ''}>
                    ${isMaxed ? 'تم الانتهاء' : 'شراء بـ ' + item.price.toLocaleString()}
                </button>
            </div>`;
        });
    } else {
        storagePackages.forEach(item => {
            let isBought = item.level <= currentStorageLevel;
            content.innerHTML += `<div style="background:#1c1c1c; margin-bottom:10px; padding:15px; border-radius:10px; border:1px solid ${isBought ? '#333' : '#00cc66'}; display:flex; justify-content:space-between; align-items:center;">
                <div><b>مستوى ${item.level}</b><div style="font-size:12px; color:#aaa;">السعة: ${item.capacity} ZN</div></div>
                <button onclick="showConfirmModal('storage', ${item.level}, ${item.price})" style="padding:10px; background:${isBought ? '#333' : '#00cc66'}; border:none; color:white; border-radius:8px;" ${isBought ? 'disabled' : ''}>
                    ${isBought ? 'تم الشراء' : 'شراء بـ ' + item.price.toLocaleString()}
                </button>
            </div>`;
        });
    }
}

function showConfirmModal(type, level, price) {
    pendingPurchase = { type, level, price };
    document.getElementById('modal-text').innerText = `تأكيد شراء ترقية مستوى ${level}؟`;
    document.getElementById('confirm-modal').style.display = 'flex';
    document.getElementById('modal-confirm-btn').onclick = () => {
        if (playerZnBalance >= price) {
            playerZnBalance -= price;
            if (type === 'mining') miningUpgrades[level]++;
            else currentStorageLevel = level;
            document.getElementById('shop-zn-balance').innerText = playerZnBalance.toLocaleString();
            renderShopTab(type);
        }
        document.getElementById('confirm-modal').style.display = 'none';
    };
}

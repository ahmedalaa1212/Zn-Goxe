// رصيد اللاعب
let playerZnBalance = 15400;

// سجل ترقيات التعدين (كل مستوى بيبدأ من 0 ترقيات، والحد الأقصى 20)
let miningUpgrades = {
    1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0, 7: 0, 8: 0, 9: 0, 10: 0
};

// مستوى سعة التخزين (8 مستويات كترقية عادية)
let currentStorageLevel = 0; 

// بيانات باقات التعدين (10 مستويات أساسية)
const miningPackages = [
    { level: 1, price: 1000, boost: 500 },
    { level: 2, price: 3000, boost: 1200 },
    { level: 3, price: 7000, boost: 2500 },
    { level: 4, price: 15000, boost: 5000 },
    { level: 5, price: 30000, boost: 10000 },
    { level: 6, price: 60000, boost: 22000 },
    { level: 7, price: 120000, boost: 45000 },
    { level: 8, price: 250000, boost: 100000 },
    { level: 9, price: 500000, boost: 250000 },
    { level: 10, price: 1000000, boost: 600000 }
];

// بيانات باقات التخزين (8 مستويات)
const storagePackages = [
    { level: 1, price: 2000, capacity: "20,000 ZN" },
    { level: 2, price: 5000, capacity: "30,000 ZN" },
    { level: 3, price: 10000, capacity: "50,000 ZN" },
    { level: 4, price: 25000, capacity: "100,000 ZN" },
    { level: 5, price: 50000, capacity: "250,000 ZN" },
    { level: 6, price: 100000, capacity: "500,000 ZN" },
    { level: 7, price: 250000, capacity: "1,000,000 ZN" },
    { level: 8, price: 500000, capacity: "2,500,000 ZN" }
];

// الدالة المسؤولة عن عرض القسم المختار
function renderShopTab(tab) {
    const content = document.getElementById('shop-content');
    if (!content) return;

    // حفظ التبويب الأخير 
    localStorage.setItem('lastShopTab', tab);

    // تظبيط ألوان الأزرار
    document.getElementById('btn-mining').style.background = (tab === 'mining') ? '#0088cc' : '#222';
    document.getElementById('btn-storage').style.background = (tab === 'storage') ? '#0088cc' : '#222';

    // تفريغ المحتوى
    content.innerHTML = '';

    if (tab === 'mining') {
        // عرض باقات التعدين (10 باقات، لكل باقة 20 ترقية)
        miningPackages.forEach(item => {
            let boughtCount = miningUpgrades[item.level];
            let isMaxed = boughtCount >= 20; // هل وصل للحد الأقصى (20 ترقية)؟
            
            let btnColor = isMaxed ? '#333' : '#00cc66'; 
            let btnText = isMaxed ? 'تم الانتهاء من هذا المستوى ✅' : `شراء بـ ${item.price.toLocaleString()} ZN`;
            let btnDisabled = isMaxed ? 'disabled' : '';

            let card = `
                <div style="background:#1c1c1c; padding:15px; border-radius:10px; border:1px solid ${isMaxed ? '#333' : '#00cc66'}; display:flex; flex-direction:column; gap:10px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <div>
                            <div style="font-weight:bold; font-size:16px; margin-bottom:5px;">مستوى ${item.level}</div>
                            <div style="color:#aaa; font-size:12px;">السرعة: <span style="color:#fff;">+${item.boost.toLocaleString()} ZN / ساعة</span></div>
                        </div>
                        <div style="color:${isMaxed ? '#888' : '#00cc66'}; font-size:12px; font-weight:bold; background:#222; padding:5px 10px; border-radius:5px;">
                            الترقيات: ${boughtCount} / 20
                        </div>
                    </div>
                    <button onclick="buyPackage('mining', ${item.level}, ${item.price})" style="width:100%; padding:10px; background:${btnColor}; border:none; color:${isMaxed ? '#888' : 'white'}; border-radius:8px; font-weight:bold;" ${btnDisabled}>
                        ${btnText}
                    </button>
                </div>
            `;
            content.innerHTML += card;
        });

    } else if (tab === 'storage') {
        // عرض باقات التخزين (مفتوحة وتقدر تشتري أي مستوى)
        storagePackages.forEach(item => {
            let isBought = item.level <= currentStorageLevel;
            let btnColor = isBought ? '#333' : '#00cc66';
            let btnText = isBought ? 'تم الشراء ✅' : `شراء بـ ${item.price.toLocaleString()} ZN`;
            let btnDisabled = isBought ? 'disabled' : '';

            let card = `
                <div style="background:#1c1c1c; padding:15px; border-radius:10px; border:1px solid ${isBought ? '#333' : '#00cc66'}; display:flex; justify-content:space-between; align-items:center;">
                    <div>
                        <div style="font-weight:bold; font-size:16px; margin-bottom:5px;">مستوى ${item.level}</div>
                        <div style="color:#aaa; font-size:12px;">الحد الأقصى: <span style="color:#fff;">${item.capacity}</span></div>
                    </div>
                    <button onclick="buyPackage('storage', ${item.level}, ${item.price})" style="padding:10px 15px; background:${btnColor}; border:none; color:${isBought ? '#888' : 'white'}; border-radius:8px; font-weight:bold;" ${btnDisabled}>
                        ${btnText}
                    </button>
                </div>
            `;
            content.innerHTML += card;
        });
    }

    // تحديث الرصيد في الواجهة
    document.getElementById('shop-zn-balance').innerText = playerZnBalance.toLocaleString();
}

// دالة الشراء
function buyPackage(type, level, price) {
    if (playerZnBalance < price) {
        alert("رصيدك من الـ ZN غير كافٍ!");
        return;
    }
    
    if (type === 'mining') {
        if (miningUpgrades[level] >= 20) return; // حماية إضافية
        playerZnBalance -= price;
        miningUpgrades[level] += 1; // زيادة عدد الترقيات بمقدار 1
    } else if (type === 'storage') {
        playerZnBalance -= price;
        currentStorageLevel = level;
    }

    // إعادة رسم الواجهة فوراً
    renderShopTab(type);
}

// تشغيل الواجهة لأول مرة 
setTimeout(() => {
    let lastTab = localStorage.getItem('lastShopTab') || 'mining';
    renderShopTab(lastTab);
}, 100);

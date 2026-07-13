// رصيد افتراضي للتجربة
let playerZnBalance = 15400;

// المستويات الحالية للاعب (لنفترض إنه في المستوى 0 في الاتنين)
let currentMiningLevel = 0; 
let currentStorageLevel = 0; 

// بيانات باقات التعدين (10 مستويات)
const miningPackages = [
    { level: 1, price: 1000, boost: "+500 ZN / ساعة" },
    { level: 2, price: 3000, boost: "+1,200 ZN / ساعة" },
    { level: 3, price: 7000, boost: "+2,500 ZN / ساعة" },
    { level: 4, price: 15000, boost: "+5,000 ZN / ساعة" },
    { level: 5, price: 30000, boost: "+10,000 ZN / ساعة" },
    { level: 6, price: 60000, boost: "+22,000 ZN / ساعة" },
    { level: 7, price: 120000, boost: "+45,000 ZN / ساعة" },
    { level: 8, price: 250000, boost: "+100,000 ZN / ساعة" },
    { level: 9, price: 500000, boost: "+250,000 ZN / ساعة" },
    { level: 10, price: 1000000, boost: "+600,000 ZN / ساعة" }
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

    // تظبيط ألوان الأزرار
    document.getElementById('btn-mining').style.background = (tab === 'mining') ? '#0088cc' : '#222';
    document.getElementById('btn-storage').style.background = (tab === 'storage') ? '#0088cc' : '#222';

    // تفريغ المحتوى القديم
    content.innerHTML = '';

    let activeData = (tab === 'mining') ? miningPackages : storagePackages;
    let playerCurrentLevel = (tab === 'mining') ? currentMiningLevel : currentStorageLevel;

    // رسم الكروت
    activeData.forEach(item => {
        let isBought = item.level <= playerCurrentLevel;
        let isNext = item.level === playerCurrentLevel + 1;
        let isLocked = item.level > playerCurrentLevel + 1;

        let btnColor = isBought ? '#333' : (isNext ? '#00cc66' : '#222');
        let btnText = isBought ? 'تم الشراء ✅' : `شراء بـ ${item.price.toLocaleString()} ZN`;
        let btnDisabled = isBought || isLocked ? 'disabled' : '';

        // تصميم الكارت
        let card = `
            <div style="background:#1c1c1c; padding:15px; border-radius:10px; border:1px solid ${isNext ? '#00cc66' : '#333'}; display:flex; justify-content:space-between; align-items:center; opacity: ${isLocked ? '0.6' : '1'};">
                <div>
                    <div style="font-weight:bold; font-size:16px; margin-bottom:5px;">مستوى ${item.level}</div>
                    <div style="color:#aaa; font-size:12px;">${tab === 'mining' ? 'السرعة:' : 'الحد الأقصى:'} <span style="color:#fff;">${tab === 'mining' ? item.boost : item.capacity}</span></div>
                </div>
                <button onclick="buyPackage('${tab}', ${item.level}, ${item.price})" style="padding:10px 15px; background:${btnColor}; border:none; color:${isBought ? '#888' : 'white'}; border-radius:8px; font-weight:bold;" ${btnDisabled}>
                    ${btnText}
                </button>
            </div>
        `;
        content.innerHTML += card;
    });
}

// دالة الشراء
function buyPackage(type, level, price) {
    if (playerZnBalance < price) {
        alert("رصيدك غير كافٍ لشراء هذا المستوى!");
        return;
    }
    
    // خصم الرصيد (وهمي للتجربة في الواجهة)
    playerZnBalance -= price;
    document.getElementById('shop-zn-balance').innerText = playerZnBalance.toLocaleString();

    // تحديث مستوى اللاعب
    if (type === 'mining') currentMiningLevel = level;
    if (type === 'storage') currentStorageLevel = level;

    // إعادة رسم الواجهة عشان الأزرار تتحدث
    renderShopTab(type);
    
    alert(`تم الترقية للمستوى ${level} بنجاح!`);
}

// تشغيل الواجهة فوراً على أول تاب
setTimeout(() => {
    renderShopTab('mining');
}, 100);

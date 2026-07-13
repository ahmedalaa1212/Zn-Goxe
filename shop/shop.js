// رصيد اللاعب
let playerZnBalance = 15400;

// مستويات اللاعب الحالية (صفر يعني لسه مبدأش)
let currentMiningLevel = 0; 
let currentStorageLevel = 0; 

// بيانات باقات التعدين (20 مستوى)
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
    { level: 10, price: 1000000, boost: "+600,000 ZN / ساعة" },
    { level: 11, price: 2000000, boost: "+1,200,000 ZN / ساعة" },
    { level: 12, price: 4000000, boost: "+2,500,000 ZN / ساعة" },
    { level: 13, price: 8000000, boost: "+5,000,000 ZN / ساعة" },
    { level: 14, price: 15000000, boost: "+10,000,000 ZN / ساعة" },
    { level: 15, price: 30000000, boost: "+22,000,000 ZN / ساعة" },
    { level: 16, price: 60000000, boost: "+45,000,000 ZN / ساعة" },
    { level: 17, price: 120000000, boost: "+100,000,000 ZN / ساعة" },
    { level: 18, price: 250000000, boost: "+250,000,000 ZN / ساعة" },
    { level: 19, price: 500000000, boost: "+600,000,000 ZN / ساعة" },
    { level: 20, price: 1000000000, boost: "+1,500,000,000 ZN / ساعة" }
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

    // حفظ التبويب الأخير عشان يفضل فاتحه
    localStorage.setItem('lastShopTab', tab);

    // تظبيط ألوان الأزرار
    document.getElementById('btn-mining').style.background = (tab === 'mining') ? '#0088cc' : '#222';
    document.getElementById('btn-storage').style.background = (tab === 'storage') ? '#0088cc' : '#222';

    // تفريغ المحتوى
    content.innerHTML = '';

    let activeData = (tab === 'mining') ? miningPackages : storagePackages;
    let playerCurrentLevel = (tab === 'mining') ? currentMiningLevel : currentStorageLevel;

    // رسم الكروت (الكل مفتوح يقدر يشتريه)
    activeData.forEach(item => {
        let isBought = item.level <= playerCurrentLevel; // لو اشترى مستوى 5، مستويات 1 لـ 5 هتبقى متعلمة صح
        
        let btnColor = isBought ? '#333' : '#00cc66'; // أخضر لو لسه مشتراهوش
        let btnText = isBought ? 'تم الشراء ✅' : `شراء بـ ${item.price.toLocaleString()} ZN`;
        let btnDisabled = isBought ? 'disabled' : '';

        // تصميم الكارت (مفيش شفافية، كله منور وواضح)
        let card = `
            <div style="background:#1c1c1c; padding:15px; border-radius:10px; border:1px solid ${isBought ? '#333' : '#00cc66'}; display:flex; justify-content:space-between; align-items:center;">
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

    // تحديث الرصيد في الواجهة
    document.getElementById('shop-zn-balance').innerText = playerZnBalance.toLocaleString();
}

// دالة الشراء
function buyPackage(type, level, price) {
    if (playerZnBalance < price) {
        alert("رصيدك من الـ ZN غير كافٍ لشراء هذا المستوى!");
        return;
    }
    
    // خصم الرصيد 
    playerZnBalance -= price;
    
    // تحديث مستوى اللاعب للمستوى الجديد اللي اشتراه
    if (type === 'mining') currentMiningLevel = level;
    if (type === 'storage') currentStorageLevel = level;

    // إعادة رسم الواجهة فوراً
    renderShopTab(type);
    
    alert(`مبروك! تم الترقية للمستوى ${level} بنجاح.`);
}

// تشغيل الواجهة لأول مرة عشان نضمن إنها متحملة
setTimeout(() => {
    let lastTab = localStorage.getItem('lastShopTab') || 'mining';
    renderShopTab(lastTab);
}, 100);

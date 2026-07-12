// دالة التنقل بين القوائم (Switch Views)
function switchView(viewName) {
    // 1. إخفاء كل الصفحات
    const views = document.querySelectorAll('.game-view');
    views.forEach(view => view.classList.remove('active'));

    // 2. إزالة حالة "النشط" من كل الأزرار
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => item.classList.remove('active'));

    // 3. إظهار الصفحة المطلوبة
    const targetView = document.getElementById('view-' + viewName);
    if (targetView) targetView.classList.add('active');

    // 4. تفعيل الزرار اللي ضغطت عليه
    const targetNav = document.getElementById('nav-' + viewName);
    if (targetNav) targetNav.classList.add('active');

    // 5. تحميل محتوى القائمة المطلوبة
    if (viewName === 'farm') {
        loadFarmContent();
    } else {
        // يمكنك إضافة دوال لباقي القوائم هنا لاحقاً
        console.log("جاري تحميل قائمة: " + viewName);
    }
}

// دالة تحميل بيانات المزرعة
function loadFarmContent() {
    const farmView = document.getElementById('view-farm');
    
    // محاكاة لبيانات المخزن (هتتربط لاحقاً بالـ Backend)
    const currentStorage = 12450; 
    const maxStorage = 20000;      
    const percentage = (currentStorage / maxStorage) * 100;

    farmView.innerHTML = `
        <div class="farm-container" style="text-align: center; padding: 20px;">
            <!-- 1. منطقة المزرعة -->
            <div class="farm-visual" style="font-size: 60px; margin: 30px 0;">🏗️</div>
            <h2 style="margin-bottom: 20px;">مزرعة التعدين</h2>
            
            <!-- 2. عداد العملات الفعلي -->
            <div id="balance-display" style="font-size: 32px; font-weight: bold; color: #fff; margin-bottom: 30px;">
                الرصيد: ${currentStorage.toLocaleString()}
            </div>
            
            <!-- 3. شريط التقدم -->
            <div class="progress-bar-container" style="width: 90%; background: #333; height: 25px; margin: 0 auto; border-radius: 15px; overflow: hidden; border: 1px solid #444;">
                <div id="storage-bar" style="width: ${percentage}%; background: linear-gradient(90deg, #0088cc, #00aaff); height: 100%; transition: width 0.5s;"></div>
            </div>
            
            <!-- 4. بيانات المخزن -->
            <p style="font-size: 14px; color: #aaa; margin-top: 10px;">
                ${currentStorage.toLocaleString()} / ${maxStorage.toLocaleString()} عملة
            </p>
            
            <!-- 5. زر التجميع -->
            <button onclick="claimCoins()" style="margin-top: 25px; width: 80%; padding: 15px; background: #0088cc; border: none; color: white; font-size: 16px; border-radius: 12px; font-weight: bold; cursor: pointer;">
                تجميع (Claim)
            </button>

            <!-- 6. بطاقة المكافأة اليومية (مكانها داخل المزرعة) -->
            <div class="daily-reward" style="margin-top: 30px; padding: 15px; background: #1c1c1c; border-radius: 12px; border: 1px solid #333;">
                <p>🎁 استلم مكافأتك اليومية!</p>
                <button onclick="claimDaily()" style="margin-top: 10px; background: #444; border: none; color: white; padding: 8px 20px; border-radius: 8px;">استلام</button>
            </div>
        </div>
    `;
}

// دالة التجميع
function claimCoins() {
    alert("تم تجميع العملات بنجاح!");
}

// دالة المكافأة اليومية
function claimDaily() {
    alert("تم استلام مكافأة اليوم!");
}

// تحميل المزرعة عند فتح اللعبة لأول مرة
window.onload = () => {
    loadFarmContent();
};

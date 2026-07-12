// دالة التنقل بين القوائم (Switch Views)
function switchView(viewName) {
    // 1. إخفاء كل الصفحات (Views)
    const views = document.querySelectorAll('.game-view');
    views.forEach(view => view.classList.remove('active'));

    // 2. إزالة حالة "النشط" من كل الأزرار
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => item.classList.remove('active'));

    // 3. إظهار الصفحة المطلوبة
    document.getElementById('view-' + viewName).classList.add('active');

    // 4. تفعيل الزرار اللي ضغطت عليه
    document.getElementById('nav-' + viewName).classList.add('active');

    // 5. إذا كانت القائمة هي "المزرعة"، هنحمل بياناتها (جزء للمستقبل)
    if (viewName === 'farm') {
        loadFarmContent();
    }
}

// دالة تحميل بيانات المزرعة (مبدئياً كشكل)
function loadFarmContent() {
    const farmView = document.getElementById('view-farm');
    farmView.innerHTML = `
        <div class="farm-container" style="text-align: center; padding-top: 20px;">
            <h3>مزرعة التعدين</h3>
            <div id="balance-display" style="font-size: 24px; margin: 20px 0;">الرصيد: 0</div>
            
            <!-- شريط التقدم اللي طلبته -->
            <div class="progress-bar-container" style="width: 80%; background: #333; height: 20px; margin: 0 auto; border-radius: 10px;">
                <div id="storage-bar" style="width: 30%; background: #0088cc; height: 100%; border-radius: 10px;"></div>
            </div>
            <p style="font-size: 12px; color: #888; margin-top: 5px;">المخزون: 30% | الحد الأقصى: 20,000</p>
            
            <button onclick="claimCoins()" style="margin-top: 20px; padding: 10px 30px; background: #0088cc; border: none; color: white; border-radius: 8px;">تجميع (Claim)</button>
        </div>
    `;
}

// دالة مبدئية للتجميع
function claimCoins() {
    alert("جاري الاتصال بقاعدة البيانات...");
}

// تحميل المزرعة عند فتح اللعبة لأول مرة
window.onload = () => {
    loadFarmContent();
};

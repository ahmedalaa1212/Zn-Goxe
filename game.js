// تعريف الكائن العالمي لإدارة بيانات اللاعب في كل القوائم
window.PlayerData = {
    tg_id: null,
    balance: 0,
    hourly_rate: 20,
    max_cap: 10000,
    unclaimed: 0,
    storage_level: 0,
    upgrades: {},
    
    // دالة لجلب البيانات من السيرفر وتحديث الواجهة
    async fetchUpdates() {
        if (!this.tg_id) return;
        try {
            let response = await fetch(`/api/user_data?tg_id=${this.tg_id}`);
            if (response.ok) {
                let data = await response.json();
                this.balance = data.balance;
                this.hourly_rate = data.hourly_rate;
                this.max_cap = data.max_cap;
                this.unclaimed = data.unclaimed;
                this.storage_level = data.storage_level;
                this.upgrades = data.upgrades;
                
                // تحديث الشاشات الظاهرة تلقائياً
                if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
                if (typeof window.updateShopUI === 'function') window.updateShopUI();
            }
        } catch (e) {
            console.error("Error fetching player data:", e);
        }
    }
};

// استخراج الـ Telegram ID بأمان عند تحميل اللعبة
document.addEventListener('DOMContentLoaded', () => {
    const tele = window.Telegram?.WebApp;
    if (tele) tele.ready();
    
    const urlParams = new URLSearchParams(window.location.search);
    // جلب الآي دي من بيانات تليجرام الرسمية أو من الرابط كخيار احتياطي، أو آي دي تجريبي للمتصفح
    window.PlayerData.tg_id = tele?.initDataUnsafe?.user?.id || urlParams.get('tg_id') || "5102387551";
    
    // جلب البيانات فوراً من السيرفر
    window.PlayerData.fetchUpdates();
    
    // عداد داخلي لتحديث الأرقام من السيرفر بانتظام كل 10 ثوانٍ
    setInterval(() => {
        window.PlayerData.fetchUpdates();
    }, 10000);
});

// تعريف الكائن العالمي لإدارة بيانات اللاعب
window.PlayerData = {
    tg_id: null,
    balance: 0,
    hourly_rate: 0, // هتبدأ بـ 0 لحد ما السيرفر يرد بالبيانات الحقيقية
    max_cap: 10000,
    unclaimed: 0,
    storage_level: 0,
    upgrades: {},
    
    // دالة جلب البيانات من السيرفر وتحديث الواجهة
    async fetchUpdates() {
        if (!this.tg_id) return;
        try {
            // نداء للسيرفر لجلب الداتا
            let response = await fetch(`/api/user_data?tg_id=${this.tg_id}`);
            if (response.ok) {
                let data = await response.json();
                
                // تحديث القيم بناءً على ما يرسله السيرفر
                this.balance = data.balance || 0;
                this.hourly_rate = data.hourly_rate || 0;
                this.max_cap = data.max_cap || 10000;
                this.unclaimed = data.unclaimed || 0;
                this.storage_level = data.storage_level || 0;
                this.upgrades = data.upgrades || {};
                
                // تحديث الواجهات فوراً لو كانت موجودة في الصفحة
                if (typeof window.updateFarmUI === 'function') window.updateFarmUI();
                if (typeof window.updateShopUI === 'function') window.updateShopUI();
                
                console.log("Data updated successfully from server");
            }
        } catch (e) {
            console.error("Error fetching player data:", e);
        }
    }
};

// استخراج الـ Telegram ID وتفعيل اللعبة
document.addEventListener('DOMContentLoaded', () => {
    const tele = window.Telegram?.WebApp;
    if (tele) tele.ready();
    
    const urlParams = new URLSearchParams(window.location.search);
    
    // تحديد الآي دي (أولوية لتليجرام ثم الرابط ثم الآي دي التجريبي)
    window.PlayerData.tg_id = tele?.initDataUnsafe?.user?.id || urlParams.get('tg_id') || "5102387551";
    
    // جلب البيانات فوراً عند فتح اللعبة
    window.PlayerData.fetchUpdates();
    
    // تحديث البيانات من السيرفر كل 10 ثواني لضمان الدقة
    setInterval(() => {
        window.PlayerData.fetchUpdates();
    }, 10000);
});

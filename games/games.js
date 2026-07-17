window.playGame = async function(gameType) {
    if (gameType === 'box') {
        const btn = document.getElementById('btn-play-box');
        btn.disabled = true;
        btn.innerText = "جاري تحميل الإعلان... ⏳";

        // استدعاء دالة الإعلان الخاصة بـ Monetag (نفس اللي عملناها في المزرعة)
        let adWatched = false;
        
        if (typeof window.show_11322720 === 'function') {
            try {
                await window.show_11322720(); // المستخدم بيشوف الإعلان
                adWatched = true;
            } catch(e) {
                console.error("تم إغلاق الإعلان قبل الاكتمال", e);
            }
        } else {
            alert("⚠️ يرجى إيقاف مانع الإعلانات بالجهاز للعب!");
            btn.disabled = false;
            btn.innerText = "افتح الصندوق الآن (إعلان 📺)";
            return;
        }

        // لو كمل الإعلان
        if (adWatched) {
            btn.innerText = "جاري سحب الجائزة... 🎲";
            // هنا في المرحلة الجاية هنكلم السيرفر عشان يضيفله رقم عشوائي
            setTimeout(() => {
                let randomReward = Math.floor(Math.random() * (15000 - 1000 + 1)) + 1000;
                
                if (window.Telegram && window.Telegram.WebApp) {
                    window.Telegram.WebApp.showAlert(`🎉 مبروك! كسبت ${randomReward.toLocaleString()} ZN من صندوق الحظ!`);
                } else {
                    alert(`🎉 مبروك! كسبت ${randomReward.toLocaleString()} ZN من صندوق الحظ!`);
                }

                btn.disabled = false;
                btn.innerText = "افتح الصندوق مرة أخرى (إعلان 📺)";
            }, 1500);
        } else {
            alert("⚠️ يجب عليك مشاهدة الإعلان كاملاً للحصول على المكافأة!");
            btn.disabled = false;
            btn.innerText = "افتح الصندوق الآن (إعلان 📺)";
        }
    }
};


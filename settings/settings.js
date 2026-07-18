(function initSettingsSystem() {
    
    // دالة آمنة لجلب المعرف الحقيقي من تليجرام WebApp
    function getTgId() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) return String(webAppUser.id);
        }
        // معرف افتراضي للاختبار محلياً فقط في حال عدم وجود التليجرام
        return "5102387551"; 
    }

    // دالة لجلب اسم اللاعب الحقيقي من تليجرام
    function getPlayerName() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) {
                return webAppUser.first_name + (webAppUser.last_name ? " " + webAppUser.last_name : "");
            }
        }
        return "اللاعب المحترف";
    }

    // الدالة السحرية: تذهب للسيرفر مباشرة وتجيب بيانات الـ Firebase بناءً على الـ ID
    async function fetchAndRenderData() {
        const telegramId = getTgId();
        
        // تعبئة البيانات الأساسية المتاحة من التليجرام فوراً قبل انتظار السيرفر
        const usernameEl = document.getElementById('player-username');
        const telegramIdEl = document.getElementById('player-telegram-id');
        const avatarEl = document.getElementById('player-avatar');

        if (usernameEl) usernameEl.innerText = getPlayerName();
        if (telegramIdEl) telegramIdEl.innerText = telegramId;

        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser && webAppUser.photo_url && avatarEl) {
                avatarEl.innerHTML = `<img src="${webAppUser.photo_url}" style="width:100%; height:100%; object-fit:cover;">`;
            }
        }

        try {
            // نطلب البيانات من الـ Endpoint اللي في السيرفر بتاعك
            let response = await fetch(`/api/user_data?telegramId=${telegramId}`);
            let result = await response.json();

            if (result.success && result.data) {
                const userData = result.data;

                // تحديث كائن اللعبة العام للاحتياط
                window.PlayerData = userData;

                // حساب إجمالي مستويات كروت التعدين المشترية من لفل 1 لـ لفل 10
                let totalUpgradesCount = 0;
                for (let i = 1; i <= 10; i++) {
                    totalUpgradesCount += parseInt(userData[`lvl${i}_count`] || 0);
                }

                // جلب مستوى المخزن الحالي
                let currentStorage = parseInt(userData.storage_level || 0);

                // حقن البيانات الحقيقية القادمة من الـ Firebase داخل الواجهة
                const totalMiningEl = document.getElementById('stat-total-mining');
                const storageLevelEl = document.getElementById('stat-storage-level');

                if (totalMiningEl) totalMiningEl.innerText = `${totalUpgradesCount} / 150`;
                if (storageLevelEl) storageLevelEl.innerText = `مستوى ${currentStorage}`;
                
                console.log("✅ Settings data loaded successfully from Firebase!");
            } else {
                console.error("⚠️ Server returned success:false or missing data");
            }
        } catch (error) {
            console.error("❌ Error fetching settings from backend:", error);
        }
    }

    // دالة نسخ الـ ID الشيك وإظهار رسالة توست تأكيدية
    window.copyPlayerId = function() {
        const idText = document.getElementById('player-telegram-id').innerText;
        navigator.clipboard.writeText(idText).then(() => {
            showToast("تم نسخ الـ ID بنجاح! 📋");
        }).catch(err => {
            console.error('فشل في نسخ النص: ', err);
        });
    };

    // دوال النوافذ المنبثقة لشروط الاستخدام
    window.showPrivacyModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'flex';
    };

    window.closeSettingsModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'none';
    };

    // دالة إظهار رسائل التوست المنبثقة
    function showToast(text) {
        const toast = document.getElementById('toast-msg');
        if (toast) {
            toast.innerText = text;
            toast.style.display = 'block';
            setTimeout(() => {
                toast.style.display = 'none';
            }, 2000);
        }
    }

    // زر تحديث اللعبة: يقوم بعمل ريفرش كامل وإعادة تحميل لحل مشاكل ضعف النت والتهنيج
    window.refreshGameData = function() {
        showToast("🔄 جاري إعادة تحميل وتحديث اللعبة بالكامل...");
        setTimeout(() => {
            window.location.reload(); 
        }, 800);
    };

    // التشغيل التلقائي والمباشر فور تحميل الصفحة لضمان سحب البيانات فوراً
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        fetchAndRenderData();
    } else {
        document.addEventListener('DOMContentLoaded', fetchAndRenderData);
    }

    // حارس صامت للتأكد من المحاولة مجدداً لو الصفحة فتحت وكان السيرفر لسه بيحمل
    setInterval(() => {
        const totalMiningEl = document.getElementById('stat-total-mining');
        if (totalMiningEl && totalMiningEl.innerText === "0 / 150") {
            fetchAndRenderData();
        }
    }, 2000);

})();

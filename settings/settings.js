(function initSettingsSystem() {
    
    function getTgId() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) return String(webAppUser.id);
        }
        return "5102387551"; // Fallback for testing
    }

    function getPlayerName() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser) {
                return webAppUser.first_name + (webAppUser.last_name ? " " + webAppUser.last_name : "");
            }
        }
        return "اللاعب المحترف";
    }

    // 🔒 تحديث الدالة لترسل البيانات في الـ Headers لضمان أقصى درجات الأمان
    async function fetchAndRenderData() {
        const telegramId = getTgId();
        const initData = window.Telegram?.WebApp?.initData; 
        
        const usernameEl = document.getElementById('player-username');
        const telegramIdEl = document.getElementById('player-telegram-id');
        const avatarEl = document.getElementById('player-avatar');

        // طباعة البيانات الشخصية مباشرة بدون سيرفر
        if (usernameEl) usernameEl.innerText = getPlayerName();
        if (telegramIdEl) telegramIdEl.innerText = telegramId;

        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            const webAppUser = window.Telegram.WebApp.initDataUnsafe.user;
            if (webAppUser && webAppUser.photo_url && avatarEl) {
                avatarEl.innerHTML = `<img src="${webAppUser.photo_url}" style="width:100%; height:100%; object-fit:cover;">`;
            }
        }

        // جلب الإحصائيات (المزرعة والمخزن) من السيرفر حصراً لمنع التلاعب
        if (!initData) {
            console.error("⚠️ فشل: لا يوجد initData، تأكد من فتح اللعبة داخل تليجرام.");
            return;
        }

        try {
            let response = await fetch('/api/settings/stats', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': initData // 🔒 إرسال التوقيع في الهيدر
                }
            });

            let result = await response.json();

            if (result.success) {
                const totalMiningEl = document.getElementById('stat-total-mining');
                const totalStorageEl = document.getElementById('stat-total-storage');
                
                if (totalMiningEl) {
                    totalMiningEl.innerText = `${result.farm_levels_count} مستويات`;
                }
                if (totalStorageEl) {
                    totalStorageEl.innerText = `${result.storage_levels_count} مستويات`;
                }
                
                console.log("✅ تمت مزامنة الإحصائيات بأمان من السيرفر!");
            } else {
                console.error("⚠️ السيرفر رفض الطلب أو البيانات غير متاحة:", result.message);
            }
        } catch (error) {
            console.error("❌ خطأ أثناء جلب البيانات من السيرفر:", error);
        }
    }

    window.copyPlayerId = function() {
        const idText = document.getElementById('player-telegram-id').innerText;
        navigator.clipboard.writeText(idText).then(() => {
            showToast("تم نسخ الـ ID بنجاح! 📋");
        }).catch(err => {
            console.error('فشل في نسخ النص: ', err);
        });
    };

    window.showPrivacyModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'flex';
    };

    window.closeSettingsModal = function() {
        const modal = document.getElementById('settings-modal');
        if (modal) modal.style.display = 'none';
    };

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

    // تم حذف دالة refreshGameData لأننا أزلنا الزر

    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        fetchAndRenderData();
    } else {
        document.addEventListener('DOMContentLoaded', fetchAndRenderData);
    }

    // تحديث البيانات كل 5 ثواني كحد أقصى لتخفيف الضغط على الفايربيس
    setInterval(() => {
        const totalMiningEl = document.getElementById('stat-total-mining');
        if (totalMiningEl && totalMiningEl.innerText === "0 مستويات") {
            fetchAndRenderData();
        }
    }, 5000);

})();

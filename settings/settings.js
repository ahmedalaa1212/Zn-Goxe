(function initSettingsSystem() {
    
    function getTgUser() {
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            if (window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.user) {
                return window.Telegram.WebApp.initDataUnsafe.user;
            }
        }
        return null;
    }

    function getTgId() {
        const user = getTgUser();
        return user ? String(user.id) : "5102387551"; // Fallback for testing
    }

    function getPlayerName() {
        const user = getTgUser();
        if (user) {
            return user.first_name + (user.last_name ? " " + user.last_name : "");
        }
        return "اللاعب المحترف";
    }

    // 🔄 دالة التحديث في الوقت الفعلي (بدون الضغط على السيرفر)
    function updateStatsFromLocalData() {
        // نتحقق إذا كانت بيانات اللاعب موجودة في المتغير العام الذي يحدثه المتجر
        if (window.PlayerData) {
            const totalMiningEl = document.getElementById('stat-total-mining');
            const totalStorageEl = document.getElementById('stat-total-storage');
            
            let farmLevelsCount = 0;
            // حساب مستويات المزرعة المفتوحة (التي تحتوي على ترقية واحدة على الأقل)
            if (window.PlayerData.upgrades) {
                for (let i = 1; i <= 9; i++) {
                    if (window.PlayerData.upgrades[`lvl${i}`] > 0) {
                        farmLevelsCount++;
                    }
                }
            }

            // حساب مستوى المخزن الحالي (رقم المستوى يعبر عن عدد المستويات المفتوحة)
            let storageLevelsCount = parseInt(window.PlayerData.storage_level || 0);

            if (totalMiningEl) {
                totalMiningEl.innerText = `${farmLevelsCount} مستويات`;
                totalMiningEl.style.color = "#00cc66"; 
            }
            if (totalStorageEl) {
                totalStorageEl.innerText = `${storageLevelsCount} مستويات`;
                totalStorageEl.style.color = "#0088cc"; 
            }
        }
    }

    // 🔒 تحميل البيانات الأساسية للمستخدم (الاسم والصورة) وجلب أولي من السيرفر كإجراء احتياطي
    async function fetchAndRenderData() {
        const telegramId = getTgId();
        let initData = "";
        
        if (typeof window.Telegram !== 'undefined' && window.Telegram.WebApp) {
            initData = window.Telegram.WebApp.initData;
        }
        
        const usernameEl = document.getElementById('player-username');
        const telegramIdEl = document.getElementById('player-telegram-id');
        const avatarEl = document.getElementById('player-avatar');
        const totalMiningEl = document.getElementById('stat-total-mining');
        const totalStorageEl = document.getElementById('stat-total-storage');

        // طباعة البيانات الشخصية مباشرة للسرعة
        if (usernameEl) usernameEl.innerText = getPlayerName();
        if (telegramIdEl) telegramIdEl.innerText = telegramId;

        const user = getTgUser();
        if (user && user.photo_url && avatarEl) {
            avatarEl.innerHTML = `<img src="${user.photo_url}" style="width:100%; height:100%; object-fit:cover; border-radius:50%;">`;
        }

        if (!initData) {
            console.error("⚠️ فشل: لا يوجد initData، تأكد من فتح اللعبة داخل تليجرام.");
            if (totalMiningEl && !window.PlayerData) totalMiningEl.innerText = "0 مستويات (تجريبي)";
            if (totalStorageEl && !window.PlayerData) totalStorageEl.innerText = "0 مستويات (تجريبي)";
            return;
        }

        // إذا لم تكن البيانات المحلية جاهزة بعد، جلبها من السيرفر كاحتياطي
        if (!window.PlayerData) {
            try {
                let response = await fetch('/api/settings/stats', {
                    method: 'GET',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Telegram-Init-Data': initData
                    }
                });

                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }

                let result = await response.json();

                if (result.success) {
                    if (totalMiningEl) {
                        totalMiningEl.innerText = `${result.farm_levels_count} مستويات`;
                        totalMiningEl.style.color = "#00cc66";
                    }
                    if (totalStorageEl) {
                        totalStorageEl.innerText = `${result.storage_levels_count} مستويات`;
                        totalStorageEl.style.color = "#0088cc";
                    }
                }
            } catch (error) {
                console.error("❌ خطأ أثناء جلب البيانات من السيرفر:", error);
                if (totalMiningEl) {
                    totalMiningEl.innerText = "خطأ في الاتصال";
                    totalMiningEl.style.color = "#ff4444";
                }
                if (totalStorageEl) {
                    totalStorageEl.innerText = "خطأ في الاتصال";
                    totalStorageEl.style.color = "#ff4444";
                }
            }
        }
    }

    // دعم قوي لعملية النسخ داخل متصفح تيليجرام
    window.copyPlayerId = function() {
        const idText = document.getElementById('player-telegram-id').innerText;
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(idText).then(() => {
                showToast("تم نسخ الـ ID بنجاح! 📋");
            }).catch(err => {
                console.error('فشل في نسخ النص: ', err);
                fallbackCopyTextToClipboard(idText);
            });
        } else {
            fallbackCopyTextToClipboard(idText);
        }
    };

    function fallbackCopyTextToClipboard(text) {
        const textArea = document.createElement("textarea");
        textArea.value = text;
        textArea.style.position = "fixed"; 
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        try {
            document.execCommand('copy');
            showToast("تم نسخ الـ ID بنجاح! 📋");
        } catch (err) {
            console.error('Fallback: فشل النسخ', err);
        }
        document.body.removeChild(textArea);
    }

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

    // استدعاء التحميل الأولي
    if (document.readyState === 'complete' || document.readyState === 'interactive') {
        setTimeout(fetchAndRenderData, 100);
    } else {
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(fetchAndRenderData, 100);
        });
    }

    // 🚀 الحلقة السحرية: فحص محلي كل ثانية لتحديث واجهة الإعدادات فور الشراء 
    // من المتجر دون أي تحميل أو استهلاك للسيرفر
    setInterval(updateStatsFromLocalData, 1000);

})();

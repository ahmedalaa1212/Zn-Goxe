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

    // 🔄 دالة التحديث في الوقت الفعلي (تحسب إجمالي الترقيات الفعلية)
    function updateStatsFromLocalData() {
        if (window.PlayerData) {
            const totalMiningEl = document.getElementById('stat-total-mining');
            const totalStorageEl = document.getElementById('stat-total-storage');
            
            let totalUpgradesCount = 0;
            
            // حساب إجمالي جميع الترقيات المشتراة داخل الـ 9 مستويات
            if (window.PlayerData.upgrades) {
                for (let i = 1; i <= 9; i++) {
                    totalUpgradesCount += parseInt(window.PlayerData.upgrades[`lvl${i}`] || 0);
                }
            }

            // حساب مستوى المخزن الحالي
            let storageLevelsCount = parseInt(window.PlayerData.storage_level || 0);

            if (totalMiningEl) {
                totalMiningEl.innerText = `${totalUpgradesCount} مستويات`;
                totalMiningEl.style.color = "#00cc66"; 
            }
            if (totalStorageEl) {
                totalStorageEl.innerText = `${storageLevelsCount} مستويات`;
                totalStorageEl.style.color = "#0088cc"; 
            }
        }
    }

    // 🔒 تحميل البيانات الأساسية وجلب الإحصائيات من السيرفر كإجراء احتياطي
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

        if (usernameEl) usernameEl.innerText = getPlayerName();
        if (telegramIdEl) telegramIdEl.innerText = telegramId;

        const user = getTgUser();
        if (user && user.photo_url && avatarEl) {
            avatarEl.innerHTML = `<img src="${user.photo_url}" style="width:100%; height:100%; object-fit:cover; border-radius:50%;">`;
        }

        if (!initData) {
            if (totalMiningEl && !window.PlayerData) totalMiningEl.innerText = "0 مستويات";
            if (totalStorageEl && !window.PlayerData) totalStorageEl.innerText = "0 مستويات";
            return;
        }

        // لو الداتا المحلية موجودة، استخدمها مباشرة ووفر طلب السيرفر
        if (window.PlayerData) {
            updateStatsFromLocalData();
            return;
        }

        // جلب احتياطي من السيرفر في حالة التحميل لأول مرة
        try {
            let response = await fetch('/api/settings/stats', {
                method: 'GET',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Telegram-Init-Data': initData
                }
            });

            if (response.ok) {
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
            }
        } catch (error) {
            console.error("❌ خطأ أثناء جلب البيانات:", error);
            if (totalMiningEl) {
                totalMiningEl.innerText = "خطأ في الاتصال";
                totalMiningEl.style.color = "#ff4444";
            }
        }
    }

    window.copyPlayerId = function() {
        const idText = document.getElementById('player-telegram-id').innerText;
        if (navigator.clipboard && window.isSecureContext) {
            navigator.clipboard.writeText(idText).then(() => {
                showToast("تم نسخ الـ ID بنجاح! 📋");
            }).catch(err => {
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
        } catch (err) {}
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

    // فحص دوري كل ثانية لتحديث واجهة الإعدادات فور الشراء 
    setInterval(updateStatsFromLocalData, 1000);

})();

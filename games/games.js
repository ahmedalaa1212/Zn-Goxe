// بيانات الـ 12 جائزة في العجلة
const wheelPrizes = [500, 1000, 2000, 3000, 5000, 10000, 15000, 20000, 25000, 50000, 75000, 100000];
// ألوان الـ 12 قسم
const wheelColors = ['#ff4d4d', '#ff9933', '#ffcc00', '#33cc33', '#3399ff', '#cc33ff', '#ff3399', '#669999', '#ff6600', '#99cc00', '#00cccc', '#9966ff'];

let pendingReward = 0; 
let cooldownMinutes = 3; 

// جلب ID المستخدم من تليجرام بشكل سليم
function getTelegramId() {
    if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.user) {
        return window.Telegram.WebApp.initDataUnsafe.user.id.toString();
    }
    return window.PlayerData?.tg_id || "5102387551"; 
}

// دالة تحديث الواجهة الخاصة بالألعاب (يتم استدعاؤها من الكود المركزي في game.js)
window.updateGamesUI = function() {
    const pData = window.PlayerData;
    if (!pData) return;
    
    // تحديث الرصيد في أعلى شاشة الألعاب
    const gameBalEl = document.getElementById('top-balance-games');
    if (gameBalEl) {
        const formattedBalance = Math.floor(pData.balance).toLocaleString();
        gameBalEl.innerText = gameBalEl.innerText.includes('ZN:') ? `ZN: ${formattedBalance}` : `ZN ${formattedBalance}`;
    }
};

// إرسال المكافأة للسيرفر وتحديث الرصيد الفعلي في البوت بالكامل
async function sendRewardToServer(tgId, amount) {
    try {
        const response = await fetch('/api/game_reward', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ telegramId: tgId, reward: amount })
        });
        const result = await response.json();
        if (result.success) {
            // استدعاء جلب البيانات الموحد لتحديث كل الصفحات بنفس اللحظة
            if (typeof window.fetchPlayerDataFromServer === 'function') {
                await window.fetchPlayerDataFromServer();
            }
            return true;
        }
        return false;
    } catch (error) {
        console.error("خطأ في الاتصال بالسيرفر وإرسال المكافأة:", error);
        return false;
    }
}

// دالة تهيئة العجلة ورسم الأقسام
function initWheel() {
    const wheel = document.getElementById('spin-wheel');
    if (!wheel) return;
    
    // تصفير المحتوى للتأكد من عدم التكرار عند إعادة الفتح
    wheel.innerHTML = '';
    
    let gradientParts = [];
    for (let i = 0; i < 12; i++) {
        let startDeg = i * 30;
        let endDeg = (i + 1) * 30;
        gradientParts.push(`${wheelColors[i]} ${startDeg}deg ${endDeg}deg`);
    }
    wheel.style.background = `conic-gradient(${gradientParts.join(', ')})`;

    for (let i = 0; i < 12; i++) {
        let angle = (i * 30) + 15; 
        let text = document.createElement('div');
        
        let displayPrize = wheelPrizes[i] >= 1000 ? (wheelPrizes[i]/1000) + 'K' : wheelPrizes[i];
        
        text.innerText = displayPrize;
        text.style.position = 'absolute';
        text.style.width = '40px';
        text.style.left = '50%';
        text.style.top = '10px'; 
        text.style.marginLeft = '-20px';
        text.style.textAlign = 'center';
        text.style.fontWeight = 'bold';
        text.style.fontSize = '14px';
        text.style.color = '#fff';
        text.style.textShadow = '1px 1px 2px rgba(0,0,0,0.8)';
        text.style.transformOrigin = '50% 100px'; 
        text.style.transform = `rotate(${angle}deg)`;
        
        wheel.appendChild(text);
    }
}

setTimeout(initWheel, 300);

// التحقق من العدادات
function checkCooldowns() {
    startTimerIfActive('box', 'btn-play-box', 'افتح الصندوق الآن (إعلان 📺)');
    startTimerIfActive('spin', 'btn-play-spin', 'لف العجلة الآن (إعلان 📺)');
}
setTimeout(checkCooldowns, 500);

// دالة اللعب والتأكد من إعلان Monetag
window.playGame = async function(gameType) {
    let btnId = gameType === 'box' ? 'btn-play-box' : 'btn-play-spin';
    const btn = document.getElementById(btnId);
    let originalText = gameType === 'box' ? 'افتح الصندوق الآن (إعلان 📺)' : 'لف العجلة الآن (إعلان 📺)';

    if (!btn) return;
    btn.disabled = true;
    btn.innerText = "جاري تحميل الإعلان... ⏳";

    let adWatched = false;
    
    // استدعاء Monetag
    if (typeof window.show_11322720 === 'function') {
        try {
            await window.show_11322720();
            adWatched = true;
        } catch(e) {
            console.error("لم يكتمل الإعلان", e);
        }
    } else {
        alert("⚠️ يرجى إيقاف مانع الإعلانات لتتمكن من اللعب!");
        btn.disabled = false;
        btn.innerText = originalText;
        return;
    }

    if (adWatched) {
        if(gameType === 'box') {
            btn.innerText = "جاري سحب الجائزة... 🎲";
            setTimeout(() => {
                let reward = Math.floor(Math.random() * (25000 - 1000 + 1)) + 1000;
                showWinModal(reward);
                setCooldown(gameType, btnId, originalText);
            }, 1000);
        } 
        else if (gameType === 'spin') {
            btn.innerText = "جاري لف العجلة... 🎡";
            const wheel = document.getElementById('spin-wheel');
            if (!wheel) return;
            
            let prizeIndex = Math.floor(Math.random() * 12);
            let prize = wheelPrizes[prizeIndex];
            
            let stopAngle = 360 - ((prizeIndex * 30) + 15); 
            let totalRotation = stopAngle + 1800; 

            wheel.style.transform = `rotate(${totalRotation}deg)`;
            
            setTimeout(() => {
                showWinModal(prize);
                setCooldown(gameType, btnId, originalText);
                
                setTimeout(() => {
                    wheel.style.transition = 'none';
                    wheel.style.transform = `rotate(${stopAngle}deg)`;
                    setTimeout(() => wheel.style.transition = 'transform 4s cubic-bezier(0.25, 0.1, 0.25, 1)', 50);
                }, 1000);

            }, 4200); 
        }
    } else {
        alert("⚠️ يجب عليك مشاهدة الإعلان كاملاً للحصول على المكافأة!");
        btn.disabled = false;
        btn.innerText = originalText;
    }
};

// نافذة الفوز
function showWinModal(reward) {
    pendingReward = reward;
    document.getElementById('win-amount').innerText = reward.toLocaleString() + " ZN";
    
    document.getElementById('btn-claim-x2').innerText = "ضاعفها x2 (إعلان 📺)";
    document.getElementById('btn-claim-x2').disabled = false;
    document.getElementById('btn-claim-normal').style.display = "block";
    
    document.getElementById('win-modal').style.display = "flex";
}

// الاستلام العادي والمضاعف
window.claimReward = async function(type) {
    const modal = document.getElementById('win-modal');
    const tgId = getTelegramId();
    
    if (type === 'normal') {
        const success = await sendRewardToServer(tgId, pendingReward);
        if (success) {
            alert(`✅ تم استلام ${pendingReward.toLocaleString()} ZN بنجاح!`);
            modal.style.display = "none";
        } else {
            alert("⚠️ حدث خطأ أثناء الاتصال بالسيرفر، يرجى المحاولة لاحقاً.");
        }
    } 
    else if (type === 'double') {
        const btnX2 = document.getElementById('btn-claim-x2');
        if (!btnX2) return;
        btnX2.disabled = true;
        btnX2.innerText = "جاري تحميل الإعلان... ⏳";
        
        let adWatched = false;
        if (typeof window.show_11322720 === 'function') {
            try {
                await window.show_11322720();
                adWatched = true;
            } catch(e) {}
        }
        
        if (adWatched) {
            let doubledReward = pendingReward * 2;
            const success = await sendRewardToServer(tgId, doubledReward);
            
            if (success) {
                document.getElementById('win-amount').innerText = doubledReward.toLocaleString() + " ZN";
                document.getElementById('win-amount').style.color = "#00ff00"; 
                
                btnX2.innerText = "✅ تمت المضاعفة بنجاح!";
                document.getElementById('btn-claim-normal').style.display = "none";
                
                setTimeout(() => {
                    alert(`🎉 مبروك! تم إضافة ${doubledReward.toLocaleString()} ZN لرصيدك!`);
                    modal.style.display = "none";
                }, 1000);
            } else {
                alert("⚠️ حدث خطأ أثناء إضافة المكافأة.");
                btnX2.disabled = false;
                btnX2.innerText = "ضاعفها x2 (إعلان 📺)";
            }
        } else {
            alert("⚠️ لم يكتمل الإعلان، لم يتم مضاعفة المكافأة.");
            btnX2.disabled = false;
            btnX2.innerText = "ضاعفها x2 (إعلان 📺)";
        }
    }
};

// نظام العداد
function setCooldown(gameType, btnId, originalText) {
    let now = new Date().getTime();
    localStorage.setItem(gameType + '_cooldown', now);
    startTimerIfActive(gameType, btnId, originalText);
}

function startTimerIfActive(gameType, btnId, originalText) {
    let lastTime = localStorage.getItem(gameType + '_cooldown');
    if (!lastTime) return;

    let now = new Date().getTime();
    let diffSeconds = Math.floor((now - parseInt(lastTime)) / 1000);
    let totalCooldownSeconds = cooldownMinutes * 60;

    if (diffSeconds < totalCooldownSeconds) {
        let remaining = totalCooldownSeconds - diffSeconds;
        let btn = document.getElementById(btnId);
        
        if(btn) {
            btn.disabled = true;
            btn.classList.add('btn-disabled');
            
            let interval = setInterval(() => {
                remaining--;
                let m = Math.floor(remaining / 60);
                let s = remaining % 60;
                btn.innerText = `انتظر ${m}:${s < 10 ? '0'+s : s} ⏳`;
                
                if (remaining <= 0) {
                    clearInterval(interval);
                    btn.disabled = false;
                    btn.classList.remove('btn-disabled');
                    btn.innerText = originalText;
                    localStorage.removeItem(gameType + '_cooldown');
                }
            }, 1000);
        }
    } else {
        localStorage.removeItem(gameType + '_cooldown');
    }
}

// تشغيل المزامنة الفورية عند التحميل
window.updateGamesUI();

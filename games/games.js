// بيانات الـ 12 جائزة في العجلة
const wheelPrizes = [500, 1000, 2000, 3000, 5000, 10000, 15000, 20000, 25000, 50000, 75000, 100000];
// ألوان الـ 12 قسم
const wheelColors = ['#ff4d4d', '#ff9933', '#ffcc00', '#33cc33', '#3399ff', '#cc33ff', '#ff3399', '#669999', '#ff6600', '#99cc00', '#00cccc', '#9966ff'];

let pendingReward = 0; // متغير لحفظ الجائزة قبل الاستلام
let cooldownMinutes = 3; // مدة الانتظار بالدقائق

// دالة تهيئة العجلة ورسم الـ 12 قسم بالأرقام
function initWheel() {
    const wheel = document.getElementById('spin-wheel');
    if (!wheel) return;
    
    // إنشاء التدرج اللوني (Conic Gradient)
    let gradientParts = [];
    for (let i = 0; i < 12; i++) {
        let startDeg = i * 30;
        let endDeg = (i + 1) * 30;
        gradientParts.push(`${wheelColors[i]} ${startDeg}deg ${endDeg}deg`);
    }
    wheel.style.background = `conic-gradient(${gradientParts.join(', ')})`;

    // إضافة الأرقام داخل العجلة
    for (let i = 0; i < 12; i++) {
        let angle = (i * 30) + 15; // وضع الرقم في منتصف القسم
        let text = document.createElement('div');
        
        // تحويل الرقم لشكل مختصر (مثال: 10K)
        let displayPrize = wheelPrizes[i] >= 1000 ? (wheelPrizes[i]/1000) + 'K' : wheelPrizes[i];
        
        text.innerText = displayPrize;
        text.style.position = 'absolute';
        text.style.width = '40px';
        text.style.left = '50%';
        text.style.top = '10px'; // المسافة من الحافة
        text.style.marginLeft = '-20px';
        text.style.textAlign = 'center';
        text.style.fontWeight = 'bold';
        text.style.fontSize = '14px';
        text.style.color = '#fff';
        text.style.textShadow = '1px 1px 2px rgba(0,0,0,0.8)';
        // دوران النص ليكون مضبوط مع العجلة
        text.style.transformOrigin = '50% 100px'; // 100px هي نصف قطر العجلة
        text.style.transform = `rotate(${angle}deg)`;
        
        wheel.appendChild(text);
    }
}

// تشغيل التهيئة
setTimeout(initWheel, 300);

// التحقق من العدادات عند فتح الصفحة
function checkCooldowns() {
    startTimerIfActive('box', 'btn-play-box', 'افتح الصندوق الآن (إعلان 📺)');
    startTimerIfActive('spin', 'btn-play-spin', 'لف العجلة الآن (إعلان 📺)');
}
setTimeout(checkCooldowns, 500);

// دالة اللعب (الصندوق والعجلة)
window.playGame = async function(gameType) {
    let btnId = gameType === 'box' ? 'btn-play-box' : 'btn-play-spin';
    const btn = document.getElementById(btnId);
    let originalText = gameType === 'box' ? 'افتح الصندوق الآن (إعلان 📺)' : 'لف العجلة الآن (إعلان 📺)';

    btn.disabled = true;
    btn.innerText = "جاري تحميل الإعلان... ⏳";

    let adWatched = false;
    
    // استدعاء إعلان Monetag
    if (typeof window.show_11322720 === 'function') {
        try {
            await window.show_11322720();
            adWatched = true;
        } catch(e) {
            console.error("لم يكتمل الإعلان", e);
        }
    } else {
        alert("⚠️ يرجى إيقاف مانع الإعلانات للعب!");
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
            
            // اختيار جائزة عشوائية من الـ 12
            let prizeIndex = Math.floor(Math.random() * 12);
            let prize = wheelPrizes[prizeIndex];
            
            // حساب درجة الدوران لتقف العجلة عند القسم الفائز
            // المعادلة: 360 درجة - الزاوية المركزية للقسم المختار + لفات عشوائية كثيرة (مثلا 5 لفات = 1800 درجة)
            let stopAngle = 360 - ((prizeIndex * 30) + 15); 
            let totalRotation = stopAngle + 1800; // 5 لفات كاملة + زاوية الوقوف

            wheel.style.transform = `rotate(${totalRotation}deg)`;
            
            setTimeout(() => {
                showWinModal(prize);
                setCooldown(gameType, btnId, originalText);
                
                // إعادة ضبط العجلة للمرة القادمة بدون أنيميشن عشان متبانش
                setTimeout(() => {
                    wheel.style.transition = 'none';
                    wheel.style.transform = `rotate(${stopAngle}deg)`;
                    setTimeout(() => wheel.style.transition = 'transform 4s cubic-bezier(0.25, 0.1, 0.25, 1)', 50);
                }, 1000);

            }, 4200); // وقت الأنيميشن بتاع العجلة
        }
    } else {
        alert("⚠️ يجب عليك مشاهدة الإعلان كاملاً للحصول على المكافأة!");
        btn.disabled = false;
        btn.innerText = originalText;
    }
};

// دالة عرض نافذة الفوز (Modal)
function showWinModal(reward) {
    pendingReward = reward;
    document.getElementById('win-amount').innerText = reward.toLocaleString() + " ZN";
    
    // إرجاع الأزرار لحالتها الأصلية
    document.getElementById('btn-claim-x2').innerText = "ضاعفها x2 (إعلان 📺)";
    document.getElementById('btn-claim-x2').disabled = false;
    document.getElementById('btn-claim-normal').style.display = "block";
    
    document.getElementById('win-modal').style.display = "flex";
}

// دالة استلام الجائزة (عادي أو مضاعفة)
window.claimReward = async function(type) {
    const modal = document.getElementById('win-modal');
    
    if (type === 'normal') {
        // في المرحلة القادمة سيتم إرسال (pendingReward) للسيرفر
        alert(`✅ تم استلام ${pendingReward.toLocaleString()} ZN بنجاح!`);
        modal.style.display = "none";
    } 
    else if (type === 'double') {
        const btnX2 = document.getElementById('btn-claim-x2');
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
            document.getElementById('win-amount').innerText = doubledReward.toLocaleString() + " ZN";
            document.getElementById('win-amount').style.color = "#00ff00"; // تغيير اللون للأخضر كدليل ع المضاعفة
            
            btnX2.innerText = "✅ تمت المضاعفة بنجاح!";
            document.getElementById('btn-claim-normal').style.display = "none";
            
            setTimeout(() => {
                alert(`🎉 مبروك! تم إضافة ${doubledReward.toLocaleString()} ZN لرصيدك!`);
                modal.style.display = "none";
            }, 1000);
        } else {
            alert("⚠️ لم يكتمل الإعلان، لم يتم مضاعفة المكافأة.");
            btnX2.disabled = false;
            btnX2.innerText = "ضاعفها x2 (إعلان 📺)";
        }
    }
};

// --- نظام العداد (Cooldown) المتطور ---

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

// تحديث الرصيد العلوي
setInterval(() => {
    const balanceElem = document.getElementById('top-balance-games');
    if(balanceElem && window.userBalance) {
        balanceElem.innerText = Math.floor(window.userBalance).toLocaleString() + " ZN";
    }
}, 2000);

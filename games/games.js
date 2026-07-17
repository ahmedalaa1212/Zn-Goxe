window.playGame = async function(gameType) {
    let btnId = gameType === 'box' ? 'btn-play-box' : 'btn-play-spin';
    const btn = document.getElementById(btnId);
    let originalText = btn.innerText;
    
    btn.disabled = true;
    btn.innerText = "جاري تحميل الإعلان... ⏳";

    let adWatched = false;
    
    // استدعاء إعلان Monetag
    if (typeof window.show_11322720 === 'function') {
        try {
            await window.show_11322720();
            adWatched = true;
        } catch(e) {
            console.error("لم يتم الإعلان", e);
        }
    } else {
        alert("⚠️ يرجى إيقاف مانع الإعلانات بالجهاز للعب!");
        btn.disabled = false;
        btn.innerText = originalText;
        return;
    }

    if (adWatched) {
        if(gameType === 'box') {
            btn.innerText = "جاري سحب الجائزة... 🎲";
            setTimeout(() => {
                let reward = Math.floor(Math.random() * (15000 - 1000 + 1)) + 1000;
                showAlert(`🎁 مبروك! كسبت ${reward.toLocaleString()} ZN من الصندوق!`);
                btn.disabled = false;
                btn.innerText = originalText;
            }, 1000);
        } 
        else if (gameType === 'spin') {
            btn.innerText = "جاري لف العجلة... 🎡";
            const wheel = document.getElementById('spin-wheel');
            // عمل أنيميشن لف العجلة برقم عشوائي للدرجات
            let randomDegree = Math.floor(Math.random() * 360) + 1440; // تلف 4 مرات على الأقل
            wheel.style.transform = `rotate(${randomDegree}deg)`;
            
            setTimeout(() => {
                let rewardsList = [500, 1000, 2500, 5000, 10000];
                let reward = rewardsList[Math.floor(Math.random() * rewardsList.length)];
                showAlert(`🎡 وقفت العجلة! مبروك كسبت ${reward.toLocaleString()} ZN!`);
                
                // إعادة ضبط العجلة بعد ثانية لتكون جاهزة للمرة القادمة
                setTimeout(() => {
                    wheel.style.transition = 'none';
                    wheel.style.transform = `rotate(${randomDegree % 360}deg)`;
                    setTimeout(() => wheel.style.transition = 'transform 3s cubic-bezier(0.25, 0.1, 0.25, 1)', 50);
                }, 1000);

                btn.disabled = false;
                btn.innerText = originalText;
            }, 3000); // الانتظار 3 ثواني حتى تكتمل لفة العجلة
        }
    } else {
        alert("⚠️ يجب عليك مشاهدة الإعلان كاملاً للحصول على المكافأة!");
        btn.disabled = false;
        btn.innerText = originalText;
    }
};

function showAlert(msg) {
    if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.showAlert) {
        window.Telegram.WebApp.showAlert(msg);
    } else {
        alert(msg);
    }
}

// تحديث الرصيد العلوي في صفحة الألعاب
setInterval(() => {
    const balanceElem = document.getElementById('top-balance-games');
    if(balanceElem && window.userBalance) {
        balanceElem.innerText = Math.floor(window.userBalance).toLocaleString() + " ZN";
    }
}, 2000);

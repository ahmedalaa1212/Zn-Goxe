window.switchTaskTab = function(tab) {
    const earnBtn = document.getElementById('btn-tab-earn');
    const promoteBtn = document.getElementById('btn-tab-promote');
    const earnSec = document.getElementById('section-earn');
    const promoteSec = document.getElementById('section-promote');

    if(tab === 'earn') {
        earnBtn.style.background = '#0088cc'; earnBtn.style.color = 'white';
        promoteBtn.style.background = 'transparent'; promoteBtn.style.color = '#888';
        earnSec.style.display = 'block';
        promoteSec.style.display = 'none';
        loadTasksList(); 
    } else {
        promoteBtn.style.background = '#0f3460'; promoteBtn.style.color = 'white';
        earnBtn.style.background = 'transparent'; earnBtn.style.color = '#888';
        promoteSec.style.display = 'block';
        earnSec.style.display = 'none';
    }
};

window.selectPlatform = function(type, name, iconClass, color) {
    // إزالة التحديد من كل الأزرار
    document.querySelectorAll('.platform-btn').forEach(btn => {
        btn.style.borderColor = '#333';
        btn.style.boxShadow = 'none';
    });
    
    // تمييز الزر المختار
    const activeBtn = document.getElementById(`plat-${type}`);
    activeBtn.style.borderColor = color;
    activeBtn.style.boxShadow = `0 0 10px ${color}40`;

    // إظهار وتجهيز الفورم
    const form = document.getElementById('campaign-form');
    form.style.display = 'block';
    
    document.getElementById('form-icon').className = `fab ${iconClass} fas`; // fas للموقع
    document.getElementById('form-icon').style.color = color;
    document.getElementById('form-title').innerText = `إعداد حملة ${name}`;
    
    const urlInput = document.getElementById('task-url');
    if(type === 'telegram') { urlInput.placeholder = "https://t.me/yourchannel"; document.getElementById('url-label').innerText = "رابط القناة أو الجروب:"; }
    else if(type === 'youtube') { urlInput.placeholder = "https://youtube.com/watch?v=..."; document.getElementById('url-label').innerText = "رابط الفيديو أو القناة:"; }
    else if(type === 'instagram') { urlInput.placeholder = "https://instagram.com/yourprofile"; document.getElementById('url-label').innerText = "رابط حسابك أو البوست:"; }
    else { urlInput.placeholder = "https://yourwebsite.com"; document.getElementById('url-label').innerText = "رابط الموقع المطلوب زيارته:"; }
};

window.calculateTaskCost = function() {
    let reward = parseFloat(document.getElementById('task-reward').value) || 0;
    let users = parseInt(document.getElementById('task-users').value) || 0;
    let total = reward * users;
    document.getElementById('task-total-cost').innerText = total.toLocaleString() + " AdZN";
};

window.loadTasksList = function() {
    const tasksList = document.getElementById('tasks-list');
    let dummyHTML = `
        <div style="background: #1c1c1c; border: 1px solid #333; border-radius: 10px; padding: 15px; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <div style="font-size: 24px; color: #0088cc;"><i class="fab fa-telegram"></i></div>
                <div>
                    <div style="color: #fff; font-size: 14px; font-weight: bold;">اشترك في قناة ZN الرسمية</div>
                    <div style="color: #ffcc00; font-size: 12px; margin-top: 3px;">+5,000 ZN</div>
                </div>
            </div>
            <button style="background: #333; color: white; border: none; border-radius: 5px; padding: 6px 12px; font-size: 12px; font-weight: bold; cursor: pointer;">تنفيذ</button>
        </div>
    `;
    tasksList.innerHTML = dummyHTML;
};

// دالة وهمية لتحديث الرصيد العلوي برمجياً (سيتم ربطها لاحقاً بالسيرفر)
setInterval(() => {
    const balanceElem = document.getElementById('top-balance-tasks');
    if(balanceElem && window.userBalance) {
        balanceElem.innerText = Math.floor(window.userBalance).toLocaleString() + " ZN";
    }
}, 2000);

setTimeout(loadTasksList, 500);

// دالة التبديل بين التبويبات
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
        loadTasksList(); // تحميل المهام
    } else {
        promoteBtn.style.background = '#0088cc'; promoteBtn.style.color = 'white';
        earnBtn.style.background = 'transparent'; earnBtn.style.color = '#888';
        promoteSec.style.display = 'block';
        earnSec.style.display = 'none';
    }
};

// دالة حساب تكلفة الإعلان
window.calculateTaskCost = function() {
    let reward = parseFloat(document.getElementById('task-reward').value) || 0;
    let users = parseInt(document.getElementById('task-users').value) || 0;
    let total = reward * users;
    document.getElementById('task-total-cost').innerText = total.toLocaleString() + " ZN";
};

// دالة تجريبية لتحميل المهام (شكل فقط للمرحلة الأولى)
window.loadTasksList = function() {
    const tasksList = document.getElementById('tasks-list');
    // مهام تجريبية لضبط الشكل
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
        
        <div style="background: #1c1c1c; border: 1px solid #333; border-radius: 10px; padding: 15px; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between;">
            <div style="display: flex; align-items: center; gap: 10px;">
                <div style="font-size: 24px; color: #ff0000;"><i class="fab fa-youtube"></i></div>
                <div>
                    <div style="color: #fff; font-size: 14px; font-weight: bold;">شاهد فيديو الشرح</div>
                    <div style="color: #ffcc00; font-size: 12px; margin-top: 3px;">+3,000 ZN</div>
                </div>
            </div>
            <button style="background: #333; color: white; border: none; border-radius: 5px; padding: 6px 12px; font-size: 12px; font-weight: bold; cursor: pointer;">تنفيذ</button>
        </div>
    `;
    tasksList.innerHTML = dummyHTML;
};

// سيتم ربط هذه الدوال بقاعدة البيانات في المرحلة الثانية
window.openConvertModal = function() { alert("قريباً: سيتم فتح نافذة تحويل الرصيد!"); };
window.createNewTask = function() { alert("قريباً: سيتم خصم الرصيد ونشر مهمتك!"); };

// تشغيل تحميل المهام مبدئياً
setTimeout(loadTasksList, 500);


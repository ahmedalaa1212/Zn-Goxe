// دالة التنقل بين القوائم
function switchView(viewName) {
    document.querySelectorAll('.game-view').forEach(v => v.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.getElementById('view-' + viewName).classList.add('active');
    document.getElementById('nav-' + viewName).classList.add('active');
    if (viewName === 'farm') loadFarmContent();
}

function loadFarmContent() {
    const farmView = document.getElementById('view-farm');
    
    // بيانات تجريبية (العدد اللي اشتراه من كل مستوى)
    // لاحظ: هنا بنخزن عدد القطع اللي اشتراها من كل مستوى
    const userUpgrades = [5, 2, 0, 0, 0, 0, 0, 0, 0, 0]; 

    farmView.innerHTML = `
        <div class="header-stats" style="display: flex; justify-content: space-between; padding: 10px; background: #1c1c1c; border-radius: 10px; margin-bottom: 20px;">
            <div class="stat">⚡ 120/س</div>
            <div class="stat" style="color: #ffcc00;">ZN: 15,400</div>
        </div>

        <div class="farm-container" style="text-align: center;">
            <div style="font-size: 50px; margin: 10px 0;">🏗️</div>
            
            <div style="width: 100%; background: #333; height: 20px; border-radius: 10px; overflow: hidden;">
                <div style="width: 60%; background: #0088cc; height: 100%;"></div>
            </div>
            <p style="font-size: 12px; margin: 5px 0;">12,450 / 20,000</p>
            
            <button style="width: 100%; padding: 12px; background: #0088cc; border: none; color: white; border-radius: 8px; font-weight: bold;">تجميع (Claim)</button>

            <!-- حقول التعدين الـ 10 -->
            <div class="mining-fields" style="margin-top: 20px; display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px;">
                ${userUpgrades.map((count, i) => {
                    const isUnlocked = i === 0 || userUpgrades[i-1] > 0; // يفتح لو هو الأول أو اللي قبله مفتوح
                    return `
                        <div style="background: ${isUnlocked ? '#1c1c1c' : '#111'}; padding: 15px; border-radius: 10px; border: 1px solid ${isUnlocked ? '#444' : '#222'}; color: ${isUnlocked ? '#fff' : '#555'};">
                            ${isUnlocked ? `
                                <div style="font-size: 20px; color: #ffcc00; margin-bottom: 5px;">🪙 ZN</div>
                                <div style="font-size: 14px; font-weight: bold;">LV ${i+1}</div>
                                <div style="font-size: 12px; color: #0088cc;">x${count}</div>
                            ` : `
                                <div style="font-size: 20px;">🔒</div>
                                <div style="font-size: 12px;">مغلق</div>
                            `}
                        </div>
                    `;
                }).join('')}
            </div>
        </div>
    `;
}

window.onload = () => loadFarmContent();

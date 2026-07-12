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
    
    // بيانات تجريبية (هنربطها بالـ Database لاحقاً)
    const znBalance = 15400; // الرصيد الكلي
    const miningSpeed = 120; // سرعة التعدين في الساعة
    const currentStorage = 12450;
    const maxStorage = 20000;
    const percentage = (currentStorage / maxStorage) * 100;

    farmView.innerHTML = `
        <!-- شريط البيانات العلوي -->
        <div class="header-stats" style="display: flex; justify-content: space-between; padding: 10px; background: #1c1c1c; border-radius: 10px; margin-bottom: 20px;">
            <div class="stat">⚡ سرعة: ${miningSpeed}/س</div>
            <div class="stat" style="color: #00ffcc;">ZN: ${znBalance.toLocaleString()}</div>
        </div>

        <div class="farm-container" style="text-align: center;">
            <div class="farm-visual" style="font-size: 50px; margin: 10px 0;">🏗️</div>
            
            <!-- شريط التقدم -->
            <div class="progress-bar-container" style="width: 100%; background: #333; height: 20px; border-radius: 10px; overflow: hidden;">
                <div style="width: ${percentage}%; background: #0088cc; height: 100%;"></div>
            </div>
            <p style="font-size: 12px; margin: 5px 0;">${currentStorage.toLocaleString()} / ${maxStorage.toLocaleString()}</p>
            
            <button onclick="claimCoins()" style="width: 100%; padding: 12px; background: #0088cc; border: none; color: white; border-radius: 8px; font-weight: bold;">تجميع (Claim)</button>

            <!-- المكافأة اليومية (شريط صغير) -->
            <div class="daily-reward" style="margin-top: 15px; padding: 8px; background: #222; border-radius: 5px; font-size: 12px; border: 1px solid #444;">
                🎁 مكافأة اليوم: 500 ZN | <span onclick="claimDaily()" style="color: #0088cc; cursor: pointer;">استلام</span>
            </div>

            <!-- حقول التعدين الـ 10 (المستويات) -->
            <div class="mining-fields" style="margin-top: 20px; display: grid; grid-template-columns: repeat(5, 1fr); gap: 10px;">
                ${Array.from({length: 10}, (_, i) => `
                    <div style="background: #1c1c1c; padding: 10px 0; border-radius: 5px; font-size: 10px; border: 1px solid #333;">
                        LV ${i+1}
                    </div>
                `).join('')}
            </div>
        </div>
    `;
}

function claimCoins() { alert("تم تجميع العملات!"); }
function claimDaily() { alert("تم استلام المكافأة!"); }

window.onload = () => loadFarmContent();

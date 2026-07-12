function initFarm() {
    const fieldsContainer = document.getElementById('mining-fields');
    const userUpgrades = [5, 2, 0, 0, 0, 0, 0, 0, 0, 0]; 

    fieldsContainer.innerHTML = userUpgrades.map((count, i) => {
        const isUnlocked = i === 0 || userUpgrades[i-1] > 0;
        return `
            <div style="background: ${isUnlocked ? '#1c1c1c' : '#111'}; padding: 15px; border-radius: 10px; border: 1px solid ${isUnlocked ? '#444' : '#222'};">
                ${isUnlocked ? `
                    <div style="font-size: 20px; color: #ffcc00;">🪙 ZN</div>
                    <div style="font-size: 14px; font-weight: bold;">LV ${i+1}</div>
                    <div style="font-size: 12px; color: #0088cc;">x${count}</div>
                ` : `
                    <div style="font-size: 20px;">🔒</div>
                    <div style="font-size: 12px; color: #555;">مغلق</div>
                `}
            </div>
        `;
    }).join('');
}
initFarm();


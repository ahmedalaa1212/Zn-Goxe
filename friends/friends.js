(function initFriends() {
    const tasksList = document.getElementById('tasks-list');
    
    // تعريف الـ 10 مهام
    const tasks = [
        { friends: 1, reward: 500 },
        { friends: 3, reward: 1500 },
        { friends: 5, reward: 3000 },
        { friends: 10, reward: 7000 },
        { friends: 15, reward: 12000 },
        { friends: 20, reward: 20000 },
        { friends: 30, reward: 35000 },
        { friends: 50, reward: 60000 },
        { friends: 75, reward: 100000 },
        { friends: 100, reward: 200000 }
    ];

    tasksList.innerHTML = tasks.map((task, i) => `
        <div style="background: #1c1c1c; padding: 15px; border-radius: 10px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center; border: 1px solid #333;">
            <div>
                <div style="font-weight: bold;">دعوة ${task.friends} صديق</div>
                <div style="font-size: 12px; color: #ffcc00;">المكافأة: ${task.reward.toLocaleString()} ZN</div>
            </div>
            <button style="background: #444; border: none; color: #fff; padding: 5px 10px; border-radius: 5px; font-size: 12px;">استلام</button>
        </div>
    `).join('');
})();

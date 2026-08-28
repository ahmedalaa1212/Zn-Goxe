window.onLeaderboardTabOpen = async function() {
    await window.loadLeaderboardData();
};

window.loadLeaderboardData = async function() {
    const listContainer = document.getElementById('lb-list-container');
    if (!listContainer) return;

    try {
        const res = await window.fetchAPI('/api/leaderboard/top', 'GET');
        if (res && res.success && Array.isArray(res.leaderboard)) {
            window.renderLeaderboard(res.leaderboard, res.user_rank, res.user_balance);
        } else {
            listContainer.innerHTML = `<div style="text-align: center; padding: 20px; color: #ff5252;">${res?.error || 'فشل جلب لوحة الصدارة'}</div>`;
        }
    } catch (err) {
        console.error("خطأ جلب لوحة الصدارة:", err);
        listContainer.innerHTML = `<div style="text-align: center; padding: 20px; color: #ff5252;">حدث خطأ في الاتصال بالسيرفر.</div>`;
    }
};

window.renderLeaderboard = function(list, myRank, myBalance) {
    // 1. تحديث منصة التتويج Top 3
    const top1 = list[0] || { first_name: '---', balance: 0 };
    const top2 = list[1] || { first_name: '---', balance: 0 };
    const top3 = list[2] || { first_name: '---', balance: 0 };

    const p1Name = document.getElementById('pod1-name');
    const p1Score = document.getElementById('pod1-score');
    if (p1Name) p1Name.innerText = top1.first_name;
    if (p1Score) p1Score.innerText = `${window.formatBalance(top1.balance)} ZN`;

    const p2Name = document.getElementById('pod2-name');
    const p2Score = document.getElementById('pod2-score');
    if (p2Name) p2Name.innerText = top2.first_name;
    if (p2Score) p2Score.innerText = `${window.formatBalance(top2.balance)} ZN`;

    const p3Name = document.getElementById('pod3-name');
    const p3Score = document.getElementById('pod3-score');
    if (p3Name) p3Name.innerText = top3.first_name;
    if (p3Score) p3Score.innerText = `${window.formatBalance(top3.balance)} ZN`;

    // 2. تحديث القائمة للمراكز من 4 فما فوق
    const listContainer = document.getElementById('lb-list-container');
    if (!listContainer) return;

    const restList = list.slice(3);
    if (restList.length === 0) {
        listContainer.innerHTML = `<div style="text-align: center; padding: 20px; color: #888;">لا يوجد لاعبين إضافيين بعد.</div>`;
    } else {
        let html = '';
        restList.forEach(item => {
            const isMe = String(item.telegram_id) === String(window.userState?.tg_id);
            html += `
                <div class="lb-item" style="${isMe ? 'background: rgba(0, 136, 204, 0.2); font-weight: bold;' : ''}">
                    <div class="lb-rank">#${item.rank}</div>
                    <div class="lb-user">${item.first_name} ${isMe ? ' (أنت)' : ''}</div>
                    <div class="lb-score">${window.formatBalance(item.balance)} ZN</div>
                </div>
            `;
        });
        listContainer.innerHTML = html;
    }

    // 3. تحديث شريط الترتيب الشفاف السفلي للمستخدم
    const rankValEl = document.getElementById('my-rank-val');
    const rankBalEl = document.getElementById('my-rank-balance');
    
    if (rankValEl) rankValEl.innerText = `#${myRank || '--'}`;
    if (rankBalEl) rankBalEl.innerText = `${window.formatBalance(myBalance !== undefined ? myBalance : window.userState?.balance)} ZN`;
};

if (document.getElementById('view-leaderboard')?.classList.contains('active')) {
    window.onLeaderboardTabOpen();
}


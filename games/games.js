/**
 * نظام إدارة قسم الألعاب وتنقلات الألعاب الفرعية والشارات الديناميكية
 */

// جلب وتطبيق الشارات الديناميكية للألعاب من الفايربيس
async function fetchAndRenderGameBadges() {
    try {
        const response = await fetch('/api/games/list?t=' + new Date().getTime());
        const data = await response.json();
        
        if (data && data.success && data.badges) {
            Object.keys(data.badges).forEach(gameId => {
                const badgeEl = document.getElementById(`badge-${gameId}`);
                if (badgeEl) {
                    const badgeText = data.badges[gameId];
                    if (badgeText && String(badgeText).trim() !== '') {
                        badgeEl.innerText = badgeText;
                        badgeEl.style.display = 'inline-block';
                    } else {
                        badgeEl.style.display = 'none';
                    }
                }
            });
        }
    } catch (err) {
        console.error("خطأ في جلب شارات الألعاب من السيرفر:", err);
    }
}

// تحميل لعبة فرعية ديناميكياً داخل الكادي
function loadSubGame(folderName, gameName) {
    const mainMenu = document.getElementById('games-main-menu');
    const subgameScreen = document.getElementById('subgame-screen');
    const subgameHolder = document.getElementById('subgame-holder');

    if (!mainMenu || !subgameScreen || !subgameHolder) {
        console.error("عناصر الواجهة غير مكتملة!");
        return;
    }

    // إخفاء القائمة الرئيسية وإظهار واجهة اللعبة الفرعية
    mainMenu.style.display = 'none';
    subgameScreen.style.display = 'block';

    // تفريغ المحتوى القديم وعرض مؤشر تحميل
    subgameHolder.innerHTML = '<div style="text-align:center; padding: 40px; color:#8b949e;"><i class="fas fa-spinner fa-spin fa-2x"></i><br><br>جاري تحميل اللعبة...</div>';

    // جلب ملف HTML الخاص باللعبة المطلوبة
    fetch(`games/${folderName}/${gameName}.html?v=${new Date().getTime()}`)
        .then(response => {
            if (!response.ok) throw new Error("تعذر جلب واجهة اللعبة");
            return response.text();
        })
        .then(html => {
            subgameHolder.innerHTML = html;

            // استدعاء وتنفيذ ملف JS الخاص باللعبة الفرعية
            const scriptPath = `games/${folderName}/${gameName}.js?v=${new Date().getTime()}`;
            
            // حذف أي سكريبت قديم لنفس اللعبة لتفادي التكرار
            const existingScript = document.getElementById(`script-${gameName}`);
            if (existingScript) existingScript.remove();

            const script = document.createElement('script');
            script.id = `script-${gameName}`;
            script.src = scriptPath;
            document.body.appendChild(script);
        })
        .catch(err => {
            console.error("خطأ في تحميل اللعبة:", err);
            subgameHolder.innerHTML = '<div style="text-align:center; padding: 30px; color:#f85149;">حدث خطأ أثناء تحميل اللعبة. يرجي المحاولة لاحقاً.</div>';
        });
}

// العودة من أي لعبة فرعية للقائمة الرئيسية للألعاب
function closeSubGame() {
    const mainMenu = document.getElementById('games-main-menu');
    const subgameScreen = document.getElementById('subgame-screen');
    const subgameHolder = document.getElementById('subgame-holder');

    if (subgameScreen) subgameScreen.style.display = 'none';
    if (mainMenu) mainMenu.style.display = 'flex';
    if (subgameHolder) subgameHolder.innerHTML = '';
}

// التأكد من تحديث عناصر الرصيد وجلب الشارات بانتظام
(function syncGamesData() {
    if (typeof window.updateGlobalBalanceDisplay === 'function') {
        window.updateGlobalBalanceDisplay();
    }
    fetchAndRenderGameBadges();
})();

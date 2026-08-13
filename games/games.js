let currentGameScript = null;

/**
 * تحميل واجهة وسكربت اللعبة الفرعية ديناميكياً
 * @param {string} folderName اسم مجلد اللعبة (مثال: goxe)
 * @param {string} fileName اسم الملف (مثال: goxe)
 */
function loadSubGame(folderName, fileName) {
    const mainMenu = document.getElementById('games-main-menu');
    const subgameScreen = document.getElementById('subgame-screen');
    const holder = document.getElementById('subgame-holder');

    if (!mainMenu || !subgameScreen || !holder) return;

    mainMenu.style.display = 'none';
    subgameScreen.style.display = 'block';
    holder.innerHTML = '<div style="color:#ffffff; text-align:center; padding:30px; font-weight:bold;">جاري فتح اللعبة... 🚀</div>';

    // 1. جلب واجهة اللعبة الـ HTML
    fetch(`games/${folderName}/${fileName}.html?v=${Date.now()}`)
        .then(res => {
            if (!res.ok) throw new Error('تعذر تحميل واجهة اللعبة');
            return res.text();
        })
        .then(html => {
            holder.innerHTML = html;

            // 2. تحميل سكربت الجافا سكربت الخاص باللعبة
            if (currentGameScript) currentGameScript.remove();
            currentGameScript = document.createElement('script');
            currentGameScript.src = `games/${folderName}/${fileName}.js?v=${Date.now()}`;
            document.body.appendChild(currentGameScript);
        })
        .catch(err => {
            holder.innerHTML = `<div style="color:#ff4d4d; text-align:center; padding:20px;">حدث خطأ أثناء تحميل اللعبة: ${err.message}</div>`;
        });
}

/**
 * العودة للقائمة الرئيسية للألعاب
 */
function closeSubGame() {
    const mainMenu = document.getElementById('games-main-menu');
    const subgameScreen = document.getElementById('subgame-screen');
    const holder = document.getElementById('subgame-holder');

    if (mainMenu && subgameScreen && holder) {
        holder.innerHTML = '';
        subgameScreen.style.display = 'none';
        mainMenu.style.display = 'block';
    }

    if (currentGameScript) {
        currentGameScript.remove();
        currentGameScript = null;
    }
}

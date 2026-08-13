let currentGameScript = null;

function loadSubGame(folderName, fileName) {
    const mainMenu = document.getElementById('games-main-menu');
    const subgameScreen = document.getElementById('subgame-screen');
    const holder = document.getElementById('subgame-holder');

    if (!mainMenu || !subgameScreen || !holder) return;

    mainMenu.style.display = 'none';
    subgameScreen.style.display = 'block';
    holder.innerHTML = '<div style="color:#fff; text-align:center; padding:30px;">جاري فتح اللعبة... 🚀</div>';

    // 1. جلب واجهة اللعبة الـ HTML
    fetch(`games/${folderName}/${fileName}.html?v=${Date.now()}`)
        .then(res => res.text())
        .then(html => {
            holder.innerHTML = html;

            // 2. تحميل سكربت اللعبة
            if (currentGameScript) currentGameScript.remove();
            currentGameScript = document.createElement('script');
            currentGameScript.src = `games/${folderName}/${fileName}.js?v=${Date.now()}`;
            document.body.appendChild(currentGameScript);
        })
        .catch(err => {
            holder.innerHTML = '<div style="color:#ff4d4d; text-align:center;">فشل تحميل اللعبة!</div>';
        });
}

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

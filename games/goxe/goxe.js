(function initGoxeGame() {
    console.log("تم تحميل ملفات لعبة Goxe بنجاح!");

    const actionBtn = document.getElementById('goxe-action-btn');
    const scoreDisplay = document.getElementById('goxe-score-display');
    let currentScore = 0;

    if (actionBtn) {
        actionBtn.addEventListener('click', function() {
            currentScore += 10;
            if (scoreDisplay) {
                scoreDisplay.textContent = currentScore;
            }

            if (typeof window.showGlobalToast === 'function') {
                window.showGlobalToast("أحسنت! أضفت 10 نقاط في لعبة Goxe!");
            } else {
                alert("أحسنت! أضفت 10 نقاط في لعبة Goxe!");
            }
        });
    }
})();

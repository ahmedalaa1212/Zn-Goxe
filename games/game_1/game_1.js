(function initGame1() {
    console.log("تم تحميل اللعبة الأولى");
    const btn = document.getElementById('btn-play-g1');
    if(btn) {
        btn.onclick = () => alert("شغالة تمام!");
    }
})();

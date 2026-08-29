// JavaScript Logic for مهام الألعاب (games_tasks)
window.games_tasksModule = (function() {
    function init() {
        console.log("مهام الألعاب module initialized.");
    }
    
    async function loadData() {
        try {
            const res = await window.fetchAPI('/api/offers/games_tasks/data');
            return res;
        } catch(err) {
            console.error("Error loading games_tasks:", err);
            return { success: false, message: "خطأ في الاتصال" };
        }
    }

    return {
        init: init,
        loadData: loadData
    };
})();

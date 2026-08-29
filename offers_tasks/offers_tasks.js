// JavaScript Logic for مهام العروض (offers_tasks)
window.offers_tasksModule = (function() {
    function init() {
        console.log("مهام العروض module initialized.");
    }
    
    async function loadData() {
        try {
            const res = await window.fetchAPI('/api/offers/offers_tasks/data');
            return res;
        } catch(err) {
            console.error("Error loading offers_tasks:", err);
            return { success: false, message: "خطأ في الاتصال" };
        }
    }

    return {
        init: init,
        loadData: loadData
    };
})();

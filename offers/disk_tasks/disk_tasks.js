// JavaScript Logic for مهام اسطوانة (disk_tasks)
window.disk_tasksModule = (function() {
    function init() {
        console.log("مهام اسطوانة module initialized.");
    }
    
    async function loadData() {
        try {
            const res = await window.fetchAPI('/api/offers/disk_tasks/data');
            return res;
        } catch(err) {
            console.error("Error loading disk_tasks:", err);
            return { success: false, message: "خطأ في الاتصال" };
        }
    }

    return {
        init: init,
        loadData: loadData
    };
})();

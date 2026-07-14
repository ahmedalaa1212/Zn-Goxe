const express = require('express');
const app = express();
const path = require('path');

// تشغيل الملفات الثابتة في المجلد الرئيسي
app.use(express.static(__dirname));

app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// هام جداً لـ Railway
const PORT = process.env.PORT || 3000;
app.listen(PORT, "0.0.0.0", () => {
  console.log(`Server is running on port ${PORT}`);
});

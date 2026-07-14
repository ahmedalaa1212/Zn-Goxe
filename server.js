const express = require('express');
const app = express();
const path = require('path');

// ده اللي بيخلي السيرفر يقرأ كل ملفاتك في المجلد الرئيسي
app.use(express.static(__dirname));

// ده اللي بيخلي السيرفر يفتح ملف index.html بتاعك أول ما يدخلوا على اللعبة
app.get('/', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// تشغيل السيرفر
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
  console.log(`Server is running on port ${PORT}`);
});

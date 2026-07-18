.friends-page {
    padding: 20px;
    color: #ffffff;
    text-align: center;
    font-family: 'Tajawal', sans-serif; /* يفضل استخدام خط عربي جيد */
    padding-bottom: 80px; /* مساحة للقائمة السفلية */
}

.header-balance {
    display: flex;
    justify-content: center;
    align-items: center;
    gap: 10px;
    font-size: 28px;
    font-weight: bold;
    color: #ffffff;
    margin-bottom: 20px;
}

.page-title {
    margin-bottom: 20px;
    font-size: 22px;
}

.card-label {
    font-size: 14px;
    color: #aaaaaa;
    margin-bottom: 15px;
}

/* كروت الأقسام */
.referral-card, .earnings-card, .stats-card {
    background: #1c1c1c;
    padding: 20px;
    border-radius: 15px;
    margin-bottom: 20px;
    border: 1px solid #2a2a2a;
}

/* تنسيق حقل الرابط والزر */
.invite-link-container {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

#invite-link-input {
    background: #000000;
    color: #ffffff;
    border: 1px solid #333;
    padding: 12px;
    border-radius: 8px;
    text-align: center;
    font-family: monospace;
    font-size: 14px;
    width: 100%;
    outline: none;
}

#copy-link-btn {
    background: #0088cc;
    color: white;
    border: none;
    padding: 12px;
    border-radius: 8px;
    font-weight: bold;
    cursor: pointer;
    transition: background 0.2s;
}

#copy-link-btn:active { background: #006699; }

/* قسم الأرباح */
.earnings-amount {
    font-size: 32px;
    font-weight: bold;
    color: #ffcc00;
    margin-bottom: 5px;
}

.earnings-amount .currency {
    font-size: 20px;
}

.fee-note {
    font-size: 11px;
    color: #ff6b6b;
    margin-bottom: 15px;
}

#claim-earnings-btn {
    width: 100%;
    background: #00cc66;
    color: white;
    border: none;
    padding: 15px;
    border-radius: 10px;
    font-weight: bold;
    font-size: 16px;
    cursor: pointer;
}
#claim-earnings-btn:disabled {
    background: #333;
    color: #777;
    cursor: not-allowed;
}

/* تنسيق المهام */
.task-item {
    background: #1c1c1c;
    padding: 15px;
    border-radius: 12px;
    margin-bottom: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border: 1px solid #2a2a2a;
    text-align: right;
}

.task-info .task-title {
    font-weight: bold;
    font-size: 16px;
    margin-bottom: 5px;
}

.task-info .task-reward {
    font-size: 13px;
    color: #ffcc00;
}

.claim-task-btn {
    background: #444;
    color: #fff;
    border: none;
    padding: 8px 15px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: bold;
    cursor: pointer;
}

.claim-task-btn.active {
    background: #0088cc;
}

.claim-task-btn.claimed {
    background: #2a2a2a;
    color: #555;
    cursor: not-allowed;
}

from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class CheckPills(db.Model):
    __tablename__ = 'CheckPills'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    dt = db.Column(db.DateTime, nullable=False)

    lid0 = db.Column(db.String(10), default="Unknown")
    lid1 = db.Column(db.String(10), default="Unknown")
    lid2 = db.Column(db.String(10), default="Unknown")
    lid3 = db.Column(db.String(10), default="Unknown")

    has_pill0 = db.Column(db.String(10), default="Unknown")
    has_pill1 = db.Column(db.String(10), default="Unknown")
    has_pill2 = db.Column(db.String(10), default="Unknown")
    has_pill3 = db.Column(db.String(10), default="Unknown")

    # 新增欄位：用於網頁上早、午、晚餐檢查框的狀態紀錄
    # 狀態值：'Pending' (等待/未到), 'Checked' (已服藥打勾), 'Missed' (未服藥打叉)
    breakfast_status = db.Column(db.String(10), default="Pending")
    breakfast_time = db.Column(db.String(20), default="") # 紀錄實際服藥時間，例如 "07:32:15"

    lunch_status = db.Column(db.String(10), default="Pending")
    lunch_time = db.Column(db.String(20), default="")

    dinner_status = db.Column(db.String(10), default="Pending")
    dinner_time = db.Column(db.String(20), default="")
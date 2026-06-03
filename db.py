from flask_sqlalchemy import SQLAlchemy
from datetime import date

db = SQLAlchemy()

class CheckPills(db.Model):
    __tablename__ = 'CheckPills'

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    dt = db.Column(db.Date, nullable=False, unique=True, default=date.today())
    updated_at = db.Column(db.String(30), default="")

    lid0 = db.Column(db.String(10), default="Unknown")
    lid1 = db.Column(db.String(10), default="Unknown")
    lid2 = db.Column(db.String(10), default="Unknown")
    lid3 = db.Column(db.String(10), default="Unknown")

    has_pill0 = db.Column(db.String(10), default="Unknown")
    has_pill1 = db.Column(db.String(10), default="Unknown")
    has_pill2 = db.Column(db.String(10), default="Unknown")
    has_pill3 = db.Column(db.String(10), default="Unknown")

    breakfast_status = db.Column(db.String(10), default="Pending")
    breakfast_time = db.Column(db.String(20), default="")

    lunch_status = db.Column(db.String(10), default="Pending")
    lunch_time = db.Column(db.String(20), default="")

    dinner_status = db.Column(db.String(10), default="Pending")
    dinner_time = db.Column(db.String(20), default="")
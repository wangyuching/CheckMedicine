from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Pill(db.Model):
    __tablename__ = 'CheckPill'

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
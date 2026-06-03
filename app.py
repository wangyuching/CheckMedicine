from ultralytics import YOLO
import cv2
import time as t
from datetime import datetime, timedelta, date
import numpy as np
from flask import Flask, render_template, Response, jsonify

from alotdef import (
    get_target_obb, 
    split_obb, 
    lid_connect_split_box, 
    pillbox_head_tail, 
    check_pill_in_split_box,
    draw_slot_states,
    single_grid_status
    )
from db import db, CheckPills

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://root:DataBase@127.0.0.1:3306/project"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
with app.app_context():
    db.create_all()

TIME_SLOTS = {
    'breakfast': {'start': (7, 0), 'end': (8, 0), 'name': '早餐'},
    'lunch': {'start': (12, 0), 'end': (13, 0), 'name': '午餐'},
    'dinner': {'start': (17, 0), 'end': (18, 0), 'name': '晚餐'}
}
MEAL_TO_GRID_INDEX = {
    'breakfast': 0,
    'lunch': 1,
    'dinner': 2
}

class SystemState:
    def __init__(self):
        self.is_absent = False
        self.absent_start_time = None
sys_state = SystemState()

def get_current_time_status():
    now = datetime.now()
    for key, slot in TIME_SLOTS.items():
        start_time = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=slot['start'][0], minutes=slot['start'][1])
        end_time = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=slot['end'][0], minutes=slot['end'][1])
        
        before_30 = start_time - timedelta(minutes=30)
        after_30 = end_time + timedelta(minutes=30)
        
        if before_30 <= now < start_time:
            return key, 'before_30', slot['name']
        elif start_time <= now <= end_time:
            return key, 'in_slot', slot['name']
        elif end_time < now <= after_30:
            return key, 'after_30', slot['name']
            
    return None, 'outside', ''

def get_db_record(today_str):
    return CheckPills.query.filter(dt=today_str).first()

def create_default_daily_record(today_str):
    new_data = CheckPills(
        dt=today_str,
        updated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        lid0="Close", lid1="Close", lid2="Close", lid3="Close",
        has_pill0="Unknown", has_pill1="Unknown", has_pill2="Unknown", has_pill3="Unknown",
        breakfast_status="Pending", lunch_status="Pending", dinner_status="Pending"
    )
    try:
        db.session.add(new_data)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"建立預設資料失敗: {e}")
    return CheckPills.query.filter(dt=today_str).first()

def insert_status_to_db(current_slots_data):
    with app.app_context():
        now = datetime.now()
        today_date = now.date()
        dt_str = now.strftime("%Y-%m-%d")
        
        record = get_db_record(today_date)
        if not record:
            record = create_default_daily_record(today_date)

        if not record:
            print("無法取得或建立資料庫記錄。")
            return
            
        slot_key, period_type, meal_name = get_current_time_status()
        if slot_key and (period_type in ['in_slot', 'after_30']):
            status_attr = f"{slot_key}_status"
            time_attr = f"{slot_key}_time"

            if hasattr(record, status_attr) and getattr(record, status_attr) != 'Checked':
                target_grid_idx = MEAL_TO_GRID_INDEX.get(slot_key)
                
                if target_grid_idx is not None and target_grid_idx in current_slots_data:
                    grid_data = current_slots_data[target_grid_idx]
                    
                    if grid_data['lid'] == 'Open' and not grid_data['Has_pill']:
                        setattr(record, status_attr, 'Checked')
                        setattr(record, time_attr, now.strftime("%H:%M:%S"))
        lids = [current_slots_data[i]['lid'] for i in range(4)]
        has_pills = [
            "Unknown" if current_slots_data[i]['lid'] == "Close" else
            ("Full" if current_slots_data[i]['Has_pill'] else "Empty")
            for i in range(4)
        ]
        
        try:
            for i in range(4):
                setattr(record, f"lid{i}", lids[i])
                setattr(record, f"has_pill{i}", has_pills[i])
            
            record.updated_at = dt_str
            db.session.commit()

        except Exception as e:
            db.session.rollback()
            print(f"資料庫寫入失敗: {e}")

model = YOLO("best.pt", task="obb")
cap = cv2.VideoCapture(1)

def cap_real_time():
    HSV_LOWER = np.array([0, 0, 255])
    HSV_UPPER = np.array([179, 255, 255])
    reverse_state = False

    same_time_tracker = {
        "active_opens": [], "open_start_time": None, "missing_start_time": None, "triggered": False,
    }

    while cap.isOpened():
        ok, frame = cap.read()
        if (not ok) | (frame is None): break
        
        frame = cv2.resize(frame, (640, 480))
        results = model(frame, verbose=False)
        pill_detect_frame = frame.copy()

        bedtime_word = get_target_obb(results, target_cls=0)
        pill_boxes = get_target_obb(results, target_cls=4)
        
        if pill_boxes:
            sys_state.is_absent = False
            sys_state.absent_start_time = None

            lid_close = get_target_obb(results, target_cls=1)
            lid_open = get_target_obb(results, target_cls=3)
            all_lids = []
            for ls in lid_close: all_lids.append({'box': ls, 'state': 'Close'})
            for lo in lid_open: all_lids.append({'box': lo, 'state': 'Open'})

            for pb in pill_boxes:
                if bedtime_word:
                    reverse_state = pillbox_head_tail(bedtime_word, pb)

                w, h = pb[2], pb[3]
                split_axis = "w" if w > h else "h"
                sub_boxes = split_obb(pb, split_axis, num_splits=4, reverse=reverse_state)

                slots_data = {i: {"lid" : "Missing", "Has_pill": False} for i in range(4)}
                for lid in all_lids:
                    idx = lid_connect_split_box(lid['box'], sub_boxes)
                    if idx != -1: slots_data[idx]['lid'] = lid['state']

                for i, sub_box in enumerate(sub_boxes):
                    current_lid_state = slots_data[i]['lid']
                    if current_lid_state == "Open":
                        has_pill, mask = check_pill_in_split_box(pill_detect_frame, i, sub_box, HSV_LOWER, HSV_UPPER)
                        slots_data[i]['Has_pill'] = has_pill
                    else:
                        slots_data[i]['Has_pill'] = False
                    
                    if i == 3:
                        cv2.putText(pill_detect_frame, "TAIL", (int(sub_box[0]), int(sub_box[1]-20)), 
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
                    # draw_slot_states(pill_detect_frame, sub_box, i, slots_data[i])

            single_grid_status(
                    frame=pill_detect_frame, 
                    current_slots_data=slots_data, 
                    tracker=same_time_tracker, 
                    duration=5.0, 
                    missing=5.0, 
                    db_insert=insert_status_to_db
                )        
        else:
            if sys_state.absent_start_time is None:
                sys_state.absent_start_time = t.time()
            
            if t.time() - sys_state.absent_start_time > 0.1:
                sys_state.is_absent = True

        ret, jpeg = cv2.imencode('.jpg', frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
        yield(b'--pill_detect_frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')

    cap.release()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    now = datetime.now()        
    today_str = now.date()

    record = get_db_record(today_str)
    if not record:
        record = create_default_daily_record(today_str)
    
    status_data = {
        'alert_message': '',
        'breakfast': {'status': 'Pending', 'time': ''},
        'lunch': {'status': 'Pending', 'time': ''},
        'dinner': {'status': 'Pending', 'time': ''}
    }
    
    is_current_meal_checked = False
    slot_key, period_type, meal_name = get_current_time_status()
    
    for meal_key, slot in TIME_SLOTS.items():
        db_status = getattr(record, f"{meal_key}_status", 'Pending')
        db_time = getattr(record, f"{meal_key}_time", '')
        
        if db_status == 'Checked':
            status_data[meal_key]['status'] = 'Checked'
            status_data[meal_key]['time'] = db_time
            if meal_key == slot_key:
                is_current_meal_checked = True
        else:
            end_time = datetime.combine(now.date(), datetime.min.time()) + timedelta(hours=slot['end'][0], minutes=slot['end'][1])
            if now > (end_time + timedelta(minutes=30)):
                status_data[meal_key]['status'] = 'Missed'
            else:
                status_data[meal_key]['status'] = 'Pending'
        
    if sys_state.is_absent:
        if period_type == 'before_30':
            alert_msg = "還沒到服用藥的時段，請放下藥盒，並放置於畫面中。"
        elif period_type in ['in_slot', 'after_30']:
            if is_current_meal_checked:
                alert_msg = f"已服用完{meal_name}時段的藥。請將蓋子打開、藥盒放置在畫面中。"
            else:
                alert_msg = f"請服用{meal_name}時段的藥。完成後請將蓋子打開、藥盒放置在畫面中。"
        else:
            alert_msg = "還沒到服用藥的時段，請放下藥盒，並放置於畫面中。"

    else:
        if period_type == 'before_30':
            alert_msg = f"準備服用{meal_name}時段的藥。"
        elif period_type in ['in_slot', 'after_30']:
            if is_current_meal_checked:
                alert_msg = f"已服用完{meal_name}時段的藥。請將蓋子打開、藥盒放置在畫面中。"
            else:
                alert_msg = f"請服用{meal_name}時段的藥。完成後請將蓋子打開、藥盒放置在畫面中。"
        else:
            alert_msg = "目前非服用藥的時段。"

    status_data['alert_message'] = alert_msg
    return jsonify(status_data)

@app.route('/cap_in_html')
def cap_in_html():
    return Response(cap_real_time(), mimetype='multipart/x-mixed-replace; boundary=pill_detect_frame')

if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=1010)
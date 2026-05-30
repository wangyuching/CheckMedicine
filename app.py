from ultralytics import YOLO
import cv2
import time as t
import numpy as np
from flask import Flask, render_template, Response, jsonify
import base64

from alotdef import (
    get_target_obb, 
    split_obb, 
    lid_connect_split_box, 
    pillbox_head_tail, 
    check_pill_in_split_box,
    draw_slot_states
    )
from db import db, CheckPills

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://root:DataBase@127.0.0.1:3306/project"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()

def insert_pill_data(current_slots_data, frame):
    with app.app_context():
        dt_str = t.strftime("%Y-%m-%d %H:%M:%S", t.localtime())

        lids = [current_slots_data[i]['lid'] for i in range(4)]
        has_pills = [
            "Unknown" if current_slots_data[i]['lid'] == "Close" else
            ("Full" if current_slots_data[i]['Has_pill'] else "Empty")
            for i in range(4)
        ]

        try:
            new_data = CheckPills(
                dt=dt_str,
                lid0=lids[0],
                lid1=lids[1],
                lid2=lids[2],
                lid3=lids[3],
                has_pill0=has_pills[0],
                has_pill1=has_pills[1],
                has_pill2=has_pills[2],
                has_pill3=has_pills[3],
            )
            db.session.add(new_data)
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Error inserting data: {e}")

model = YOLO("best.pt", task="obb") #best.float32.tflite, best.onnx
cap = cv2.VideoCapture(1)

def cap_real_time():
    HSV_LOWER = np.array([0, 0, 255])
    HSV_UPPER = np.array([179, 255, 255])

    reverse_state = False
    has_once_detect_bedtime_word = False

    same_time_tracker = {
        "active_opens":[],
        "open_start_time": None,
        "missing_start_time": None,
        "triggered": False,
    }

    while cap.isOpened():
        ok, frame = cap.read()
        if (not ok) | (frame is None):    
            print("usb pull out and in again...")
            break
        else:
            frame = cv2.resize(frame, (640, 480))

            results = model(frame, verbose=False)

            pill_detect_frame = frame.copy()
            pill_detect_frame = cv2.resize(pill_detect_frame, (640, 480))

            bedtime_word = get_target_obb(results, target_cls=0)
            pill_boxes = get_target_obb(results, target_cls=4)
            if pill_boxes:
                lid_close = get_target_obb(results, target_cls=1)
                lid_open = get_target_obb(results, target_cls=3)
                all_lids = []
                for ls in lid_close: all_lids.append({'box': ls, 'state': 'Close'})
                for lo in lid_open: all_lids.append({'box': lo, 'state': 'Open'})

                for pb in pill_boxes:
                    if bedtime_word:
                        current_res = pillbox_head_tail(bedtime_word, pb)
                        reverse_state = current_res
                        has_once_detect_bedtime_word = True
                        print("Direction updated by bedtime_word.")
                    elif has_once_detect_bedtime_word:
                        pass
                        print("Direction kept from last detection.")

                    w, h = pb[2], pb[3]
                    split_axis = "w" if w > h else "h"
                    sub_boxes = split_obb(pb, split_axis, num_splits=4, reverse=reverse_state)

                    slots_data = {i: {"lid" : "Missing", "Has_pill": False} for i in range(4)}
                    for lid in all_lids:
                        idx = lid_connect_split_box(lid['box'], sub_boxes)
                        if idx != -1:
                            slots_data[idx]['lid'] = lid['state']

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
                        
                        draw_slot_states(pill_detect_frame, sub_box, i, slots_data[i])

            else:
                print("Cant find object pill_box.")
                cv2.putText(pill_detect_frame, "WHERE IS THE PILL BOX?", (20, 250), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 0, 255), 3)

            ret, jpeg = cv2.imencode('.jpg', pill_detect_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
            pill_detect_frame = jpeg.tobytes()
            yield(
                b'--pill_detect_frame\r\n'
                b'Content-Type: image/jpeg\r\n\r\n' + pill_detect_frame + b'\r\n'
            )

            # t.sleep(0.2)
    cap.release()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/history')
def api_history():
    history = CheckPills.query.all()
    history_list = []
    for record in history:
        def to_base64(img_blob):
            if img_blob:
                return base64.b64encode(img_blob).decode('utf-8')
            return None

        history_list.append({
            'dt': record.dt.strftime("%Y-%m-%d %H:%M:%S"),
            'lid0': record.lid0,
            'lid1': record.lid1,
            'lid2': record.lid2,
            'lid3': record.lid3,
            'has_pill0': record.has_pill0,
            'has_pill1': record.has_pill1,
            'has_pill2': record.has_pill2,
            'has_pill3': record.has_pill3,
        })
    return jsonify(history_list)

@app.route('/cap_in_html')
def cap_in_html():
    return Response(cap_real_time(), mimetype='multipart/x-mixed-replace; boundary=pill_detect_frame')

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=1010)
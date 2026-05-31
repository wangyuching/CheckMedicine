from ultralytics import YOLO
import cv2
import time as t
from datetime import datetime, timedelta
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

# 定義吃藥時間段 (時, 分)
TIME_SLOTS = {
    'breakfast': {'start': (7, 0), 'end': (8, 0), 'name': '早餐'},
    'lunch': {'start': (12, 0), 'end': (13, 0), 'name': '午餐'},
    'dinner': {'start': (17, 0), 'end': (18, 0), 'name': '晚餐'}
}

MEAL_TO_GRID_INDEX = {
    'breakfast': 0,  # 0 號格放早餐藥
    'lunch': 1,      # 1 號格放午餐藥
    'dinner': 2      # 2 號格放晚餐藥
}

# 狀態管理類別
class SystemState:
    def __init__(self):
        self.is_absent = False          # 藥盒是否被拿走
        self.absent_start_time = None   # 藥盒開始消失的時間點（防抖動）

sys_state = SystemState()

# ==================== 輔助功能函式 ====================
def get_current_time_status():
    """計算當前時間處於哪一個服藥區間"""
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
    """取得當天最新的一筆資料庫紀錄"""
    return CheckPills.query.filter(CheckPills.dt.like(f"{today_str}%")).order_by(CheckPills.id.desc()).first()

def create_default_daily_record(today_str):
    """為新的一天初始化首筆預設紀錄，防止查詢斷層"""
    dt_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    new_data = CheckPills(
        dt=dt_str,
        lid0="Close", lid1="Close", lid2="Close", lid3="Close",
        has_pill0="Unknown", has_pill1="Unknown", has_pill2="Unknown", has_pill3="Unknown",
        breakfast_status="Pending", lunch_status="Pending", dinner_status="Pending"
    )
    db.session.add(new_data)
    db.session.commit()
    return new_data

def insert_status_to_db(current_slots_data):
    """
    此函式統一由 singel_grid_status 在開盒滿足秒數(5秒)後調用。
    集中處理：1. 判斷時段服藥狀態更新 2. 儲存四格最新狀態
    """
    with app.app_context():
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        dt_str = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # 1. 取得或初始化今日主要紀錄
        record = get_db_record(today_str)
        if not record:
            record = create_default_daily_record(today_str)
            
        # 2. 統整判斷：當前時段與對應格子的吃藥邏輯
        slot_key, period_type, meal_name = get_current_time_status()
        
        # 僅在服藥時段內 (in_slot) 或服藥後半小時內 (after_30) 進行服藥結算
        if slot_key and (period_type in ['in_slot', 'after_30']):
            status_attr = f"{slot_key}_status"
            time_attr = f"{slot_key}_time"
            
            # 如果該時段還沒被標記為 Checked，才進行檢查
            if hasattr(record, status_attr) and getattr(record, status_attr) != 'Checked':
                target_grid_idx = MEAL_TO_GRID_INDEX.get(slot_key)
                
                if target_grid_idx is not None and target_grid_idx in current_slots_data:
                    grid_data = current_slots_data[target_grid_idx]
                    
                    # 條件：對應格子為開啟狀態 (Open) 且經影像確認裡面「已經沒有藥物」 (Has_pill == False)
                    if grid_data['lid'] == 'Open' and not grid_data['Has_pill']:
                        setattr(record, status_attr, 'Checked')
                        setattr(record, time_attr, now.strftime("%H:%M:%S"))
                        print(f"[{dt_str}] 🎉 成功觸發：{meal_name}時段服藥成功，更新主狀態！")

        # 3. 統整紀錄：更新目前最新四個格子的蓋子與藥物詳細 Log 到當前紀錄中
        lids = [current_slots_data[i]['lid'] for i in range(4)]
        has_pills = [
            "Unknown" if current_slots_data[i]['lid'] == "Close" else
            ("Full" if current_slots_data[i]['Has_pill'] else "Empty")
            for i in range(4)
        ]
        
        try:
            # 同步更新主表的當前即時四格特徵
            for i in range(4):
                setattr(record, f"lid{i}", lids[i])
                setattr(record, f"has_pill{i}", has_pills[i])
            
            # 若您的 CheckPills 為唯一的資料表，此處 commit 會同時將「服藥打勾」與「四格狀態」寫入
            # 如果需要每次開盒都「新增一筆獨立的 Log Row」，可以將此處改為新增另一個 Log Model 的實例並 add
            record.dt = dt_str  # 更新最後更新時間
            db.session.commit()
            print(f"[{dt_str}] 💾 資料庫已同步保存當前藥盒四格詳細狀態。")
            
        except Exception as e:
            db.session.rollback()
            print(f"資料庫寫入失敗: {e}")

# ==================== 核心物件初始化 ====================
model = YOLO("best.pt", task="obb")
cap = cv2.VideoCapture(1)

# ==================== 主要影像與邏輯串流 ====================
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
            # 藥盒在畫面上：重置所有消失計時
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
                    draw_slot_states(pill_detect_frame, sub_box, i, slots_data[i])

            single_grid_status(
                    frame=pill_detect_frame, 
                    current_slots_data=slots_data, 
                    tracker=same_time_tracker, 
                    duration=5.0, 
                    missing=5.0, 
                    db_insert=insert_status_to_db
                )        
        else:
            # 防辨識抖動：若藥盒不見，先記錄開始消失的時間點
            if sys_state.absent_start_time is None:
                sys_state.absent_start_time = t.time()
            
            # 連續消失超過 0.5 秒，才真正判定為「被拿走 (is_absent = True)」
            if t.time() - sys_state.absent_start_time > 0.5:
                sys_state.is_absent = True

        ret, jpeg = cv2.imencode('.jpg', pill_detect_frame, [int(cv2.IMWRITE_JPEG_QUALITY), 50])
        yield(b'--pill_detect_frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + jpeg.tobytes() + b'\r\n')
        
    cap.release()

# ==================== Flask 路由實作 ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def api_status():
    now = datetime.now()        
    today_str = now.strftime("%Y-%m-%d") # 00:00 自動換日

    record = get_db_record(today_str)
    if not record:
        # 如果新的一天還沒有任何紀錄，自動建立初始狀態
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
        
    alert_msg = "目前非吃藥時段"
    if slot_key:
        if period_type == 'before_30':
            if sys_state.is_absent:
                alert_msg = "還沒到吃藥時間段"
            else:
                alert_msg = f"{meal_name}時間段開始吃藥"
                
        elif period_type in ['in_slot', 'after_30']:
            if is_current_meal_checked:
                alert_msg = f"已吃過{meal_name}的藥了"
            else:
                alert_msg = f"要吃{meal_name}的藥"
    
    status_data['alert_message'] = alert_msg
    return jsonify(status_data)

@app.route('/cap_in_html')
def cap_in_html():
    return Response(cap_real_time(), mimetype='multipart/x-mixed-replace; boundary=pill_detect_frame')

if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=1010)
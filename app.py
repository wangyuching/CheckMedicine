from ultralytics import YOLO
import cv2
import time as t
from datetime import datetime, timedelta
import numpy as np
from flask import Flask, render_template, Response, jsonify
import base64

from alotdef import (
    get_target_obb, 
    split_obb, 
    lid_connect_split_box, 
    pillbox_head_tail, 
    check_pill_in_split_box,
    draw_slot_states,
    singel_grid_status
    )
from db import db, CheckPills

app = Flask(__name__)

app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://root:DataBase@127.0.0.1:3306/project"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()

# ==================== 全域變數與配置 ====================
web_alert_message = ""
alert_clear_time = None  # 用於控制 30 秒後清除提示
last_remind_time = {}    # 紀錄每 5 分鐘提醒的時間戳


# 定義吃藥時段 (時, 分)
TIME_SLOTS = {
    'breakfast': {'start': (7, 0), 'end': (8, 0), 'name': '早餐'},
    'lunch': {'start': (12, 0), 'end': (13, 0), 'name': '午餐'},
    'dinner': {'start': (17, 0), 'end': (18, 0), 'name': '晚餐'}
}

# ==================== 輔助功能函式 ====================
def get_current_time_status():
    """
    根據目前時間，判斷處於哪個時端與前後範圍
    回傳: slot_key, period_type ('before_30', 'in_slot', 'after_30', 'outside'), slot_name
    """
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

def insert_status_to_db(current_slots_data):
    """
    你原本的單格狀態變更觸發的資料庫寫入機制（維持保留）
    """
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
                lid0=lids[0], lid1=lids[1], lid2=lids[2], lid3=lids[3],
                has_pill0=has_pills[0], has_pill1=has_pills[1], has_pill2=has_pills[2], has_pill3=has_pills[3],
            )
            db.session.add(new_data)
            db.session.commit()
            print("Successfully inserted slot trigger data to DB.")
        except Exception as e:
            db.session.rollback()
            print(f"Error inserting data: {e}")

def update_db_on_pill_check(slots_data):
    """
    檢查當前是否在服藥時段或後30分鐘內，
    如果是，且藥盒內所有格子都空了（藥吃完了），就自動更新當日該時段的服藥狀態與時間。
    """
    with app.app_context():
        now = datetime.now()
        today_str = now.strftime("%Y-%m-%d")
        slot_key, period_type, _ = get_current_time_status()
        
        if slot_key and (period_type in ['in_slot', 'after_30']):
            # 取得或創建今天的紀錄（以當天日期為主要查詢依據）
            # 注意：若你的資料庫主鍵仍是遞增 id，此處會尋找當天最新的一筆
            record = CheckPills.query.filter(CheckPills.dt.like(f"{today_str}%")).order_by(CheckPills.id.desc()).first()
            if not record:
                # 如果完全沒有，可選擇不動作或建立一筆新底稿
                return False
            
            # 判斷是否所有格子內的藥丸都清空了
            all_empty = all(not data['Has_pill'] for data in slots_data.values())
            
            status_attr = f"{slot_key}_status"
            time_attr = f"{slot_key}_time"
            
            # 如果偵測到吃完藥，且資料庫尚未被標記為 Checked
            if hasattr(record, status_attr) and getattr(record, status_attr) != 'Checked':
                if all_empty:
                    setattr(record, status_attr, 'Checked')
                    # 假設你在 db.py 有擴充對應的時間欄位，若沒有則只會跳過這行
                    if hasattr(record, time_attr):
                        setattr(record, time_attr, now.strftime("%H:%M:%S"))
                    db.session.commit()
                    return True
        return False

# ==================== 核心物件初始化 ====================
model = YOLO("best.pt", task="obb")
cap = cv2.VideoCapture(1)

# ==================== 主要影像與邏輯串流 ====================
def cap_real_time():
    global web_alert_message, alert_clear_time, last_remind_time

    HSV_LOWER = np.array([0, 0, 255])
    HSV_UPPER = np.array([179, 255, 255])

    reverse_state = False
    has_once_detect_bedtime_word = False

    same_time_tracker = {
        "active_opens": [],
        "open_start_time": None,
        "missing_start_time": None,
        "triggered": False,
    }

    while cap.isOpened():
        ok, frame = cap.read()
        if (not ok) | (frame is None):    
            print("usb pull out and in again...")
            break
        
        frame = cv2.resize(frame, (640, 480))
        results = model(frame, verbose=False)

        pill_detect_frame = frame.copy()
        pill_detect_frame = cv2.resize(pill_detect_frame, (640, 480))

        bedtime_word = get_target_obb(results, target_cls=0)
        pill_boxes = get_target_obb(results, target_cls=4)
        
        # ------------------ 時段提醒文字狀態機 ------------------
        slot_key, period_type, slot_name = get_current_time_status()
        now_ts = t.time()
        
        # 自動清除「非吃藥時間動藥盒」持續 30 秒的提醒
        if alert_clear_time and now_ts > alert_clear_time:
            web_alert_message = ""
            alert_clear_time = None

        # 情況 1：時段前的 30 分鐘 -> 持續顯示提醒
        if period_type == 'before_30':
            web_alert_message = f"{slot_name}時段開始吃藥"
            
        # 情況 2：時段內 或 時段後的 30 分鐘
        elif period_type in ['in_slot', 'after_30']:
            # 檢查當前時段是否已經吃過藥（這裡從即時 tracker 判斷，或者可在 API 中結合 DB 判斷）
            # 如果還沒吃藥，則每 5 分鐘（300秒）更新一次提醒字樣
            if slot_key not in last_remind_time or (now_ts - last_remind_time[slot_key] > 300):
                web_alert_message = f"要吃{slot_name}的藥"
                last_remind_time[slot_key] = now_ts
                
        # 超過時段+30分，自動將 Pending 的時段標記為未服藥（Missed），這部分交由後續歷史或 API 處理更佳
        
        # ------------------ 藥盒偵測與放回事件 ------------------
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

                # 檢查是否觸發時段內吃完藥的資料庫更新
                is_just_eaten = update_db_on_pill_check(slots_data)
                if is_just_eaten:
                    # 如果判定剛剛吃完藥了，則當前時段的提示字樣可以提早結束
                    web_alert_message = ""

                # 執行你原本的格子時間追蹤與資料庫寫入機制
                singel_grid_status(
                    frame=pill_detect_frame,
                    current_slots_data=slots_data,
                    tracker=same_time_tracker,
                    duration=5.0,
                    missing=5.0,
                    db_insert=insert_status_to_db
                )

        else:
            
            # 依據目前時間區段，更新網頁提醒字樣
            if period_type in ['outside', 'before_30']:
                web_alert_message = "還沒到吃藥時段"
                alert_clear_time = now_ts + 30  # 設定 30 秒後自動清除
            elif period_type in ['in_slot', 'after_30']:
                web_alert_message = f"要吃{slot_name}的藥"

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
    """
    保留你原本完整的歷史紀錄 API 邏輯（包含 Blob 轉換檢查）
    """
    history = CheckPills.query.all()
    history_list = []
    for record in history:
        # 確保相容舊有的 dt 物件格式與字串格式
        dt_display = record.dt.strftime("%Y-%m-%d %H:%M:%S") if hasattr(record.dt, 'strftime') else str(record.dt)

        history_list.append({
            'dt': dt_display,
            'lid0': record.lid0, 'lid1': record.lid1, 'lid2': record.lid2, 'lid3': record.lid3,
            'has_pill0': record.has_pill0, 'has_pill1': record.has_pill1, 'has_pill2': record.has_pill2, 'has_pill3': record.has_pill3,
            # 若你在 db.py 擴充了各時段狀態，也可以在這邊一併補上傳給前端
        })
    return jsonify(history_list)

@app.route('/api/status')
def api_status():
    """
    提供給前端 index.html 進行即時文字提醒更新的 API
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    # 撈取今天最後一筆紀錄來獲取吃藥狀態
    record = CheckPills.query.filter(CheckPills.dt.like(f"{today_str}%")).order_by(CheckPills.id.desc()).first()
    
    # 如果你在 db.py 裡還沒有加上 breakfast_status 欄位，
    # 預設會先回傳 'Pending'，你可以根據需求在 db.py 增加欄位或調整此處的映射
    return jsonify({
        'alert_message': web_alert_message,
        'breakfast': {
            'status': getattr(record, 'breakfast_status', 'Pending') if record else 'Pending', 
            'time': getattr(record, 'breakfast_time', '') if record else ''
        },
        'lunch': {
            'status': getattr(record, 'lunch_status', 'Pending') if record else 'Pending', 
            'time': getattr(record, 'lunch_time', '') if record else ''
        },
        'dinner': {
            'status': getattr(record, 'dinner_status', 'Pending') if record else 'Pending', 
            'time': getattr(record, 'dinner_time', '') if record else ''
        }
    })

@app.route('/cap_in_html')
def cap_in_html():
    return Response(cap_real_time(), mimetype='multipart/x-mixed-replace; boundary=pill_detect_frame')

if __name__ == '__main__':
    app.run(debug=False, host='127.0.0.1', port=1010)
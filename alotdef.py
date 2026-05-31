import cv2
import numpy as np
import time as t

def get_target_obb(results, target_cls):
    filtered_boxes = []
    # name = ["bedtime_Word", "lid_close", "lid_hinge", "lid_open", "pill_box"]

    for r in results:
        classes = r.obb.cls
        boxes = r.obb.xywhr #[center_x, center_y, width, height, rotation_radians]

        mask = (classes == target_cls)
        target_boxes = boxes[mask]
        target_boxes_np = target_boxes.cpu().numpy()
        
        for box in target_boxes_np:
            filtered_boxes.append(box)
            
    return filtered_boxes

def draw_target_obb(image, boxes, color, thickness=2):
    output_img = image.copy()
    for box in boxes:
        x, y, w, h, r = box

        angle = np.degrees(r)
        rect = ((x, y), (w, h), angle)

        points = cv2.boxPoints(rect)
        points = np.int32(points)
    
        cv2.polylines(output_img, [points], isClosed=True, color=color, thickness=thickness)

    return output_img

def split_obb(obb_xywhr, axis='w', num_splits=4, reverse=False):
    xc, yc, w, h, r = obb_xywhr
    
    new_w = w / num_splits if axis == 'w' else w
    new_h = h / num_splits if axis == 'h' else h
    
    sub_obbs = []
    
    steps = np.linspace(-0.5 + 1/(2*num_splits), 0.5 - 1/(2*num_splits), num_splits)

    if reverse:
        steps = steps[::-1]

    for step in steps:
        if axis == 'w':
            dx, dy = step * w, 0
        else:
            dx, dy = 0, step * h
            
        new_x = xc + dx * np.cos(r) - dy * np.sin(r)
        new_y = yc + dx * np.sin(r) + dy * np.cos(r)
        
        sub_obbs.append([new_x, new_y, new_w, new_h, r])
        
    return sub_obbs

def lid_connect_split_box(lid_box, sub_boxes):
    lx, ly = lid_box[0], lid_box[1]
    min_dist = float('inf')
    best_idx = -1

    for idx, s_box in enumerate(sub_boxes):
        sx, sy = s_box[0], s_box[1]
        dist = np.sqrt((lx - sx)**2 + (ly - sy)**2)
        if dist < min_dist:
            min_dist = dist
            best_idx = idx

    return best_idx

def pillbox_head_tail(bedtime_word, pill_box):
    if not bedtime_word:
        return False
    
    px, py, pw, ph, pr = pill_box
    bx, by, bw, bh, br = bedtime_word[0]

    if pw > ph: #horizontal
        axis_vec = np.array([np.cos(pr), np.sin(pr)])
    else: #vertical
        axis_vec = np.array([-np.sin(pr), np.cos(pr)])

    target_vec = np.array([bx - px, by - py])

    projection = np.dot(target_vec, axis_vec)

    return True if projection < 0 else False


def check_pill_in_split_box(frame, i, box, hsv_lower, hsv_upper, threshold=0.1):
    xc, yc, w, h, r = box
    M = cv2.getRotationMatrix2D((xc, yc), np.degrees(r), 1)
    rotated = cv2.warpAffine(frame, M, (frame.shape[1], frame.shape[0]))
    base_crop = cv2.getRectSubPix(rotated, (int(w), int(h)), (xc, yc))
    h_crop, w_crop = base_crop.shape[:2]
    pad_w = int(w_crop * 0.05)
    pad_h = int(h_crop * 0.05)
    crop = base_crop[pad_h:-pad_h, pad_w:-pad_w] # 去除邊緣 5% 的區域

    if (crop is None) or (crop.size == 0):
        return False, np.zeros((10, 10), dtype=np.uint8)
    

    hsv_img = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    base_mask = cv2.inRange(hsv_img, hsv_lower, hsv_upper)

    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.morphologyEx(base_mask, cv2.MORPH_CLOSE, kernel)

    white_pixels = cv2.countNonZero(mask)
    total_pixels = w * h
    ratio = white_pixels / total_pixels

    has_pill = ratio> threshold
    print(f"Box {i}: Pill Ratio = {ratio:.2%}")

    return has_pill, mask

def draw_slot_states(image, box, slot_idx, slot_data):
    x, y,w, h, r = box
    lid_state = slot_data['lid']
    pill_state = "Full" if slot_data['Has_pill'] else "Empty"

    if lid_state == "Open" and not slot_data["Has_pill"]:
        color = (0, 255, 0)  # Green for open & empty
    elif lid_state == "Open" and slot_data["Has_pill"]:
        color = (0, 0, 255)  # Red for open & full
    elif lid_state == "Close":
        color = (255, 0, 0)  # Blue for closed lid
    else:
        color = (100, 100, 100)  # Gray for missing lid

    rect = ((x, y), (w, h), np.degrees(r))
    points = cv2.boxPoints(rect)
    points = np.int32(points)
        
    cv2.polylines(image, [points], isClosed=True, color=color, thickness=2)

    label = f"#{slot_idx} {lid_state}"
    cv2.putText(image, label, (int(x) - 30, int(y)), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

    if lid_state == "Open":
        pill_label = f"{pill_state}"
        cv2.putText(image, pill_label, (int(x) - 30, int(y) + 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)    

def single_grid_status(frame, current_slots_data, tracker, duration, missing, db_insert):
    current_opens = [
        idx for idx, 
        data in current_slots_data.items() 
        if data['lid'] == "Open"
    ]

    if len(current_opens) > 0:
        tracker['missing_start_time'] = None

        if current_opens != tracker['active_opens']:
            tracker['active_opens'] = current_opens
            tracker['open_start_time'] = t.time()
            tracker['triggered'] = False

        else:
            if tracker['open_start_time'] is not None and not tracker['triggered']:
                elapsed_time = t.time() - tracker['open_start_time']

                if elapsed_time > duration:
                    db_insert(current_slots_data)
                    tracker['triggered'] = True
    
    else:
        if tracker['open_start_time'] is not None:
            if tracker['missing_start_time'] is None:
                tracker['missing_start_time'] = t.time()

            lost_duration = t.time() - tracker['missing_start_time']

            if lost_duration > missing:
                tracker['active_opens'] = []
                tracker['open_start_time'] = None
                tracker['missing_start_time'] = None
                tracker['triggered'] = False

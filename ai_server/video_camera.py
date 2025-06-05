from flask import Flask, render_template, Response, request, abort, jsonify
from flask_cors import CORS
from .camera import VideoCamera
import threading
import time
import cv2
import json
import os
import base64
from datetime import datetime

# Import RFID MQTT components
try:
    from rfid_mqtt_server_v2 import RFIDMQTTServer  # Sử dụng version 2 với hỗ trợ vào/ra
except ImportError:    from rfid_mqtt_server import RFIDMQTTServer  # Fallback to original version
from .whitelist_db import WhitelistDB

app = Flask(__name__)
CORS(app)  # Enable CORS for ThingsBoard integration

# Global instances
global_camera = None
rfid_server = None
camera_lock = threading.Lock()
rfid_lock = threading.Lock()

def get_global_camera():
    """Get or create global camera instance"""
    global global_camera
    with camera_lock:
        if global_camera is None:
            # Tạo camera instance với auto_save_enabled=False để tắt lưu tự động
            global_camera = VideoCamera(auto_save_enabled=False)
            # Initialize the camera connection
            global_camera.open_camera()
        return global_camera

@app.route("/")
def index():
    return render_template("index.html")

def gen(camera: VideoCamera):
    while True:
        with camera_lock:
            # Đặt save_plate=False để không lưu biển số khi chỉ hiển thị video
            frame = camera.get_frame(save_plate=False)
        if frame is None:
            time.sleep(0.1)  # Ngủ ngắn để tránh tốn CPU
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n\r\n"
        )

@app.route("/video_feed")
def video_feed():
    camera = get_global_camera()
    return Response(
        gen(camera),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )

# --- Enhanced snapshot endpoint ---
@app.route("/snapshot")
def snapshot():
    flag = request.args.get("flag", default=0, type=int)
    crop = request.args.get("crop", default=1, type=int)  # Mặc định là cắt hình ảnh
    extract_plate = request.args.get("extract_plate", default=0, type=int)  # Tính năng mới
    
    if flag != 1:
        abort(400, "Snapshot flag must be 1")
    
    # Sử dụng camera global thay vì tạo mới
    camera = get_global_camera()
    
    # Chụp ảnh với tính năng lưu biển số
    with camera_lock:
        frame = camera.get_frame(save_plate=True, crop_vehicle=(crop == 1))
    
    if not frame:
        abort(500, "Failed to capture image")
    
    print("📸 Snapshot captured successfully! Camera continues running...")
      # Nếu yêu cầu trích xuất biển số
    if extract_plate == 1:
        try:
            # Lấy frame thô trực tiếp từ camera (không qua file I/O)
            with camera_lock:
                ret, raw_frame = camera.cap.read()
            
            if not ret or raw_frame is None:
                return jsonify({
                    "success": False,
                    "error": "Không thể lấy frame từ camera",
                    "timestamp": datetime.now().isoformat()                }), 500            # Trích xuất biển số trực tiếp từ frame thô (lossless)
            from .camera import extract_plate_text_advanced, model
            
            # Tạo thư mục lưu ảnh nếu chưa có
            save_dir = "captured_plates"
            os.makedirs(save_dir, exist_ok=True)
            
            extraction_result = extract_plate_text_advanced(
                image_source=raw_frame,  # Sử dụng frame thô thay vì file
                model=model,
                confidence_threshold=0.5,
                save_cropped=True,
                save_dir=save_dir
            )
            
            # Trả về JSON với thông tin biển số
            result = {
                "success": True,
                "license_plate": extraction_result['texts'][0] if extraction_result['texts'] else "",
                "all_plates": extraction_result['texts'],
                "confidences": extraction_result['confidences'],
                "detection_count": len(extraction_result['texts']),
                "image_path": extraction_result['save_paths'][0] if extraction_result['save_paths'] else None,
                "timestamp": datetime.now().isoformat()
            }
            
            if extraction_result['texts']:
                print(f"🚗 Đã trích xuất biển số (chế độ lossless): {extraction_result['texts'][0]}")
                print(f"📊 Confidence: {extraction_result['confidences'][0]:.3f}")
                print(f"📁 Tổng số biển số phát hiện: {len(extraction_result['texts'])}")
            else:
                print("⚠️ Không trích xuất được biển số")
                result["success"] = False
                result["error"] = "Không trích xuất được biển số từ ảnh"
            
            return jsonify(result)
            
        except Exception as e:
            print(f"❌ Lỗi trích xuất biển số: {e}")
            return jsonify({
                "success": False,
                "error": f"Lỗi xử lý ảnh: {str(e)}",
                "timestamp": datetime.now().isoformat()
            }), 500
    else:
        # Trả về ảnh như cũ
        return Response(frame, mimetype="image/jpeg")

# --- Status endpoint ---
@app.route("/status")
def status():
    camera = get_global_camera()
    status_info = {
        "camera_open": camera.is_open,
        "camera_index": camera.camera_index,
        "message": "Camera is running and ready for snapshots!"
    }
    return status_info

# Add RFID management routes
@app.route("/rfid/status")
def rfid_status():
    """Trạng thái RFID MQTT Server"""
    global rfid_server
    if rfid_server:
        return jsonify({
            "rfid_running": rfid_server.is_running,
            "mqtt_broker": "test.mosquitto.org",
            "mqtt_port": 1883,
            "subscribe_topic": "yolouno/rfid/scan",
            "publish_topic": "yolouno/rfid/response"
        })
    else:
        return jsonify({"rfid_running": False, "message": "RFID server not initialized"})

@app.route("/rfid/whitelist")
def get_whitelist():
    """Lấy danh sách thẻ cho phép"""
    try:
        db = WhitelistDB()
        cards = db.get_all_cards()
        return jsonify({
            "success": True,
            "total": len(cards),
            "cards": [
                {
                    "uid": card["uid"],
                    "name": card["name"],
                    "department": card["department"],
                    "created_at": card["created_at"].isoformat() if card.get("created_at") else None
                }
                for card in cards
            ]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/rfid/add_card", methods=["POST"])
def add_card():
    """Thêm thẻ mới vào whitelist"""
    try:
        data = request.get_json()
        uid = data.get("uid", "").strip()
        name = data.get("name", "").strip()
        department = data.get("department", "Unknown").strip()
        
        if not uid or not name:
            return jsonify({"success": False, "error": "UID và tên không được để trống"}), 400
        
        db = WhitelistDB()
        success = db.add_card(uid, name, department)
        
        if success:
            return jsonify({"success": True, "message": f"Đã thêm thẻ {uid} - {name}"})
        else:
            return jsonify({"success": False, "error": "UID đã tồn tại"}), 400
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/rfid/remove_card", methods=["POST"])
def remove_card():
    """Xóa thẻ khỏi whitelist"""
    try:
        data = request.get_json()
        uid = data.get("uid", "").strip()
        
        if not uid:
            return jsonify({"success": False, "error": "UID không được để trống"}), 400
        
        db = WhitelistDB()
        success = db.remove_card(uid)
        
        if success:
            return jsonify({"success": True, "message": f"Đã xóa thẻ {uid}"})
        else:
            return jsonify({"success": False, "error": "Không tìm thấy thẻ"}), 400
            
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/rfid/test_uid", methods=["POST"])
def test_uid():
    """Test UID để kiểm tra quyền truy cập"""
    try:
        data = request.get_json()
        uid = data.get("uid", "").strip()
        
        if not uid:
            return jsonify({"success": False, "error": "UID không được để trống"}), 400
        db = WhitelistDB()
        result = db.check_uid_allowed(uid)
        
        return jsonify({
            "success": True,
            "uid": uid,
            "allowed": result["allowed"],
            "name": result.get("name"),
            "department": result.get("department"),
            "message": result["message"]
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# =============================================================================
# VEHICLE TRACKING API ENDPOINTS - Mới cho hệ thống vào/ra
# =============================================================================

@app.route("/vehicle/parking_status")
def get_parking_status():
    """Lấy trạng thái bãi xe hiện tại"""
    try:
        db = WhitelistDB()
        vehicles_inside = db.get_vehicles_in_parking()
        recent_history = db.get_vehicle_history(limit=10)
        mismatches = db.get_mismatch_reports(limit=5)
        
        return jsonify({
            "success": True,
            "vehicles_inside": len(vehicles_inside),
            "vehicles_list": [
                {
                    "uid": v["uid"],
                    "license_plate": v["license_plate"],
                    "entry_time": v["entry_time"].isoformat(),
                    "duration_minutes": int((datetime.now() - v["entry_time"]).total_seconds() / 60)
                }
                for v in vehicles_inside
            ],
            "recent_history": [
                {
                    "uid": h["uid"],
                    "license_plate": h["license_plate"],
                    "entry_time": h["entry_time"].isoformat(),
                    "exit_time": h["exit_time"].isoformat() if h.get("exit_time") else None,
                    "status": h["status"],
                    "match_status": h.get("match_status"),
                    "exit_license_plate": h.get("exit_license_plate")
                }
                for h in recent_history
            ],
            "mismatch_count": len(mismatches),
            "mismatches": [
                {
                    "uid": m["uid"],
                    "entry_plate": m["license_plate"],
                    "exit_plate": m["exit_license_plate"],
                    "exit_time": m["exit_time"].isoformat()
                }
                for m in mismatches
            ]
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/vehicle/history/<uid>")
def get_vehicle_history(uid):
    """Lấy lịch sử xe của một UID cụ thể"""
    try:
        db = WhitelistDB()
        history = db.get_vehicle_history(uid=uid, limit=20)
        
        return jsonify({
            "success": True,
            "uid": uid,
            "total_records": len(history),
            "history": [
                {
                    "entry_time": h["entry_time"].isoformat(),
                    "exit_time": h["exit_time"].isoformat() if h.get("exit_time") else None,
                    "license_plate": h["license_plate"],
                    "exit_license_plate": h.get("exit_license_plate"),
                    "status": h["status"],
                    "match_status": h.get("match_status"),
                    "duration_minutes": int((h["exit_time"] - h["entry_time"]).total_seconds() / 60) if h.get("exit_time") else None
                }
                for h in history
            ]
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/vehicle/force_exit", methods=["POST"])
def force_vehicle_exit():
    """Buộc xe ra khỏi bãi (dành cho admin)"""
    try:
        data = request.get_json()
        uid = data.get("uid", "").strip()
        reason = data.get("reason", "Admin force exit").strip()
        
        if not uid:
            return jsonify({"success": False, "error": "UID không được để trống"}), 400
        
        db = WhitelistDB()
        
        # Tìm xe trong bãi
        entry_record = db.vehicle_tracking_collection.find_one({
            "uid": uid,
            "status": "inside",
            "exit_time": None
        })
        
        if not entry_record:
            return jsonify({"success": False, "error": f"Xe với UID {uid} không có trong bãi"}), 400
        
        # Cập nhật trạng thái ra
        update_data = {
            "exit_time": datetime.now(),
            "exit_license_plate": "FORCE_EXIT",
            "status": "force_exit",
            "match_status": "admin_override",
            "admin_reason": reason,
            "updated_at": datetime.now()
        }
        
        db.vehicle_tracking_collection.update_one(
            {"_id": entry_record["_id"]},
            {"$set": update_data}
        )
        
        return jsonify({
            "success": True,
            "message": f"Đã buộc xe {uid} ra khỏi bãi",
            "reason": reason
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/vehicle/save_plate_info", methods=["POST"])
def save_plate_info():
    """Lưu thông tin biển số đã được chỉnh sửa vào MongoDB collection vehicle_tracking"""
    try:
        data = request.get_json()
        license_plate = data.get("license_plate", "").strip().upper()
        uid = data.get("uid", "").strip()
        timestamp = data.get("timestamp")
        source = data.get("source", "manual_edit")
        
        if not license_plate:
            return jsonify({"success": False, "error": "Biển số không được để trống"}), 400
        
        # Lưu vào MongoDB database
        from datetime import datetime
        import json
        
        # Khởi tạo database connection
        db = WhitelistDB()
        
        # Tạo thư mục lưu trữ JSON logs nếu chưa có (backup)
        log_dir = "Data/plate_logs"
        os.makedirs(log_dir, exist_ok=True)
        
        # Tạo log entry cho JSON backup
        log_entry = {
            "license_plate": license_plate,
            "uid": uid if uid else None,
            "timestamp": timestamp if timestamp else datetime.now().isoformat(),
            "source": source,
            "processed_at": datetime.now().isoformat()
        }
        
        # Lưu vào MongoDB collection vehicle_tracking
        mongodb_result = None
        entry_result = None
        
        # Kiểm tra xem đây là chỉnh sửa biển số hay tạo mới
        if uid:
            # Kiểm tra xem UID đã có trong bãi chưa
            existing_vehicle = db.vehicle_tracking_collection.find_one({
                "uid": uid,
                "status": "inside",
                "exit_time": None
            })
            
            if existing_vehicle:
                # Cập nhật biển số cho xe đang trong bãi
                update_result = db.vehicle_tracking_collection.update_one(
                    {"_id": existing_vehicle["_id"]},
                    {"$set": {
                        "license_plate": license_plate,
                        "updated_at": datetime.now(),
                        "source": source
                    }}
                )
                mongodb_result = update_result
                print(f"✅ Đã cập nhật biển số trong vehicle_tracking: {license_plate} (UID: {uid})")
                entry_result = {
                    "success": True,
                    "message": f"Đã cập nhật biển số cho xe trong bãi",
                    "updated": True
                }
            else:
                # Thêm mới xe vào bãi
                entry_result = db.vehicle_entry(uid, license_plate, None)
                print(f"✅ Đã thêm xe vào bãi qua widget: {license_plate} (UID: {uid})")
                mongodb_result = {"inserted_id": entry_result.get("entry_id", "unknown")}
        else:
            # Nếu không có UID, tạo bản ghi xe vào không có UID
            entry_data = {
                "uid": None,
                "license_plate": license_plate,
                "entry_time": datetime.now(),
                "entry_image": None,
                "status": "manual_entry",
                "exit_time": None,
                "exit_image": None,
                "exit_license_plate": None,
                "match_status": None,
                "source": source,
                "created_at": datetime.now()
            }
            
            insert_result = db.vehicle_tracking_collection.insert_one(entry_data)
            mongodb_result = insert_result
            print(f"✅ Đã lưu biển số vào vehicle_tracking (manual): {license_plate}")
            entry_result = {
                "success": True,
                "message": f"Đã lưu biển số (thủ công)",
                "entry_id": str(insert_result.inserted_id)
            }
        
        # Backup vào JSON file
        log_file = f"{log_dir}/plate_log_{datetime.now().strftime('%Y%m%d')}.json"
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []
        
        logs.append(log_entry)
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Đã lưu thông tin biển số: {license_plate} (UID: {uid}) vào vehicle_tracking và JSON backup")
        
        return jsonify({
            "success": True,
            "message": f"Đã lưu thông tin biển số {license_plate} vào database",
            "license_plate": license_plate,
            "uid": uid,
            "mongodb_id": str(mongodb_result.inserted_id) if hasattr(mongodb_result, 'inserted_id') else entry_result.get("entry_id", "unknown"),
            "timestamp": log_entry["processed_at"],
            "details": entry_result
        })
        
    except Exception as e:
        print(f"❌ Lỗi lưu thông tin biển số: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/vehicle/recent_plates")
def get_recent_plates():
    """Lấy danh sách biển số đã lưu gần đây từ vehicle_tracking collection"""
    try:
        from datetime import datetime, timedelta
        import json
        import glob
        
        recent_plates = []
        
        # Thử đọc từ MongoDB trước
        try:
            db = WhitelistDB()
            # Lấy 20 bản ghi gần nhất từ vehicle_tracking collection
            mongodb_plates = list(db.vehicle_tracking_collection.find().sort("entry_time", -1).limit(20))
            
            for plate in mongodb_plates:
                # Sử dụng biển số ra nếu có, không thì dùng biển số vào
                license_plate = plate.get("exit_license_plate") or plate.get("license_plate", "")
                
                # Sử dụng thời gian ra nếu có, không thì dùng thời gian vào
                timestamp = plate.get("exit_time") or plate.get("entry_time", datetime.now())
                
                # Xác định trạng thái xe
                status = plate.get("status", "inside")
                
                # Thêm vào danh sách kết quả
                recent_plates.append({
                    "license_plate": license_plate,
                    "uid": plate.get("uid"),
                    "entry_time": plate.get("entry_time", datetime.now()).isoformat(),
                    "exit_time": plate.get("exit_time").isoformat() if plate.get("exit_time") else None,
                    "processed_at": timestamp.isoformat(),
                    "source": plate.get("source", "vehicle_tracking"),
                    "status": status,
                    "match_status": plate.get("match_status")
                })
            
            print(f"✅ Đã tải {len(recent_plates)} biển số từ vehicle_tracking collection")
            
        except Exception as mongo_error:
            print(f"⚠️ Lỗi đọc từ MongoDB: {mongo_error}, fallback về JSON files")
            
            # Fallback về JSON files nếu MongoDB lỗi
            log_dir = "Data/plate_logs"
            if os.path.exists(log_dir):
                # Lấy log files từ 7 ngày gần đây
                for i in range(7):
                    date_str = (datetime.now() - timedelta(days=i)).strftime('%Y%m%d')
                    log_file = f"{log_dir}/plate_log_{date_str}.json"
                    
                    if os.path.exists(log_file):
                        with open(log_file, 'r', encoding='utf-8') as f:
                            daily_logs = json.load(f)
                            recent_plates.extend(daily_logs)
                
                # Sắp xếp theo thời gian mới nhất
                recent_plates.sort(key=lambda x: x.get('processed_at', ''), reverse=True)
                
                # Lấy 20 bản ghi gần nhất
                recent_plates = recent_plates[:20]
                
                print(f"✅ Đã tải {len(recent_plates)} biển số từ JSON files")
        
        return jsonify({
            "success": True,
            "total": len(recent_plates),
            "plates": recent_plates,
            "source": "vehicle_tracking" if recent_plates and len(mongodb_plates) > 0 else "json_files"
        })
        
    except Exception as e:
        print(f"❌ Lỗi tổng quát: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/plate_edit")
def plate_edit():
    """Hiển thị trang chỉnh sửa biển số sau khi chụp"""
    # Lấy tham số từ query string
    auto_capture = request.args.get("auto_capture", default=0, type=int)
    
    extraction_result = None
    image_data = None
    
    if auto_capture == 1:
        # Tự động chụp và trích xuất
        try:
            camera = get_global_camera()
            
            # Chụp ảnh
            with camera_lock:
                frame = camera.get_frame(save_plate=True, crop_vehicle=True)
            
            if frame:
                # Convert frame to base64 for display
                import base64
                image_data = base64.b64encode(frame).decode('utf-8')
                  # Trích xuất biển số
                temp_path = f"temp_snapshot_{int(time.time())}.jpg"
                with open(temp_path, 'wb') as f:
                    f.write(frame)
                try:
                    from camera import extract_plate_text, model
                    plate_texts = extract_plate_text(temp_path, model)
                    
                    extraction_result = {
                        "success": True,
                        "license_plate": plate_texts[0] if plate_texts else "",
                        "all_plates": plate_texts,
                        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    }
                    
                    if not plate_texts:
                        extraction_result["success"] = False
                        extraction_result["error"] = "Không trích xuất được biển số từ ảnh"
                        
                except Exception as e:
                    extraction_result = {
                        "success": False,
                        "error": f"Lỗi xử lý ảnh: {str(e)}",
                        "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                    }
                finally:
                    # Xóa file tạm
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            else:
                extraction_result = {
                    "success": False,
                    "error": "Không thể chụp ảnh",
                    "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                }
                
        except Exception as e:
            extraction_result = {
                "success": False,
                "error": f"Lỗi hệ thống: {str(e)}",
                "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            }
    
    return render_template('plate_edit.html', 
                         extraction_result=extraction_result,
                         image_data=image_data)

@app.route("/save_plate_edit", methods=["POST"])
def save_plate_edit():
    """Lưu thông tin biển số đã chỉnh sửa từ form"""
    try:
        license_plate = request.form.get("license_plate", "").strip().upper()
        uid = request.form.get("uid", "").strip()
        notes = request.form.get("notes", "").strip()
        action = request.form.get("action", "save")  # save hoặc save_and_new
        
        if not license_plate:
            return jsonify({"success": False, "error": "Biển số không được để trống"}), 400
        
        # Validate license plate format (basic Vietnamese format)
        import re
        plate_pattern = r'^[0-9]{2}[A-Z]-[0-9]{3,5}$|^[0-9]{2}[A-Z][0-9]-[0-9]{3,5}$'
        if not re.match(plate_pattern, license_plate):
            print(f"⚠️ Biển số {license_plate} không đúng định dạng chuẩn, nhưng vẫn cho phép lưu")
        
        # Tạo thư mục lưu trữ
        log_dir = "Data/plate_logs"
        os.makedirs(log_dir, exist_ok=True)
        
        # Tạo log entry
        log_entry = {
            "license_plate": license_plate,
            "uid": uid if uid else None,
            "notes": notes if notes else None,
            "source": "manual_edit",
            "timestamp": datetime.now().isoformat(),
            "processed_at": datetime.now().isoformat(),
            "action": action
        }
        
        # Lưu vào file log hàng ngày
        log_file = f"{log_dir}/plate_log_{datetime.now().strftime('%Y%m%d')}.json"
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                logs = json.load(f)
        else:
            logs = []
        
        logs.append(log_entry)
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(logs, f, ensure_ascii=False, indent=2)
        
        # Cập nhật database nếu có UID
        if uid:
            try:
                db = WhitelistDB()
                # Kiểm tra UID có tồn tại không
                card_info = db.check_uid_allowed(uid)
                if card_info["allowed"]:
                    print(f"✅ UID {uid} hợp lệ cho {card_info.get('name', 'Unknown')}")
                else:
                    print(f"⚠️ UID {uid} không có trong whitelist")
            except Exception as e:
                print(f"⚠️ Không thể kiểm tra UID: {e}")
        
        print(f"✅ Đã lưu biển số: {license_plate}" + (f" (UID: {uid})" if uid else ""))
        
        return jsonify({
            "success": True,
            "message": f"Đã lưu thông tin biển số {license_plate}",
            "license_plate": license_plate,
            "uid": uid,
            "timestamp": log_entry["processed_at"],
            "action": action
        })
        
    except Exception as e:
        print(f"❌ Lỗi lưu thông tin: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/vehicle/auto_save", methods=["POST"])
def toggle_auto_save():
    """Bật/tắt tính năng lưu tự động biển số"""
    try:
        data = request.get_json()
        enabled = data.get("enabled", False)
        
        camera = get_global_camera()
        
        if enabled:
            camera.enable_auto_save()
            message = "Đã bật tính năng lưu tự động biển số"
        else:
            camera.disable_auto_save()
            message = "Đã tắt tính năng lưu tự động biển số"
        
        return jsonify({
            "success": True,
            "message": message,
            "auto_save_enabled": camera.is_auto_save_enabled()
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/vehicle/auto_save_status")
def get_auto_save_status():
    """Lấy trạng thái tính năng lưu tự động"""
    try:
        camera = get_global_camera()
        return jsonify({
            "success": True,
            "auto_save_enabled": camera.is_auto_save_enabled()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

def start_rfid_server():
    """Khởi động RFID MQTT Server trong thread riêng"""
    global rfid_server
    try:
        with rfid_lock:
            if rfid_server is None:
                rfid_server = RFIDMQTTServer()
                print("🚀 Đang khởi động RFID MQTT Server...")
                
                # Khởi động RFID server trong thread riêng để không block Flask
                def run_rfid_server():
                    try:
                        rfid_server.start()
                    except Exception as e:
                        print(f"❌ Lỗi RFID Server thread: {e}")
                
                rfid_thread = threading.Thread(target=run_rfid_server, daemon=True)
                rfid_thread.start()
                
                # Chờ một chút để RFID server khởi động
                time.sleep(2)
                print("✅ RFID Server thread đã khởi động")
                
    except Exception as e:
        print(f"❌ Lỗi khởi động RFID Server: {e}")

def main():
    """Main function to start the integrated system"""
    print("Starting License Plate Detection Server...")
    
    # Start RFID server
    start_rfid_server()
    
    # Start Flask app
    app.run(host="0.0.0.0", port=5000, debug=True)


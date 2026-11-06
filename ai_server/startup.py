
import os
import sys
import time
import threading
import subprocess
import signal
from datetime import datetime

# Add src directory to Python path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = current_dir
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

def print_banner():
    """In banner hệ thống"""
    print("="*80)
    print("HỆ THỐNG KIỂM SOÁT TRUY CẬP TÍCH HỢP")
    print("RFID MQTT Access Control + 📸 License Plate Detection")
    print("="*80)
    print(f"Khởi động lúc: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

def check_dependencies():
    """Kiểm tra các dependencies cần thiết"""
    print("Đang kiểm tra dependencies...")
    
    required_modules = [
        "paho.mqtt",
        "pymongo", 
        "flask",
        "cv2",
        "ultralytics"
    ]
    
    missing_modules = []
    
    for module in required_modules:
        try:
            if module == "cv2":
                __import__("cv2")
            elif module == "paho.mqtt":
                __import__("paho.mqtt.client")
            else:
                __import__(module)
            print(f"{module}")
        except ImportError:
            print(f"{module}")
            missing_modules.append(module)
    
    if missing_modules:
        print(f"\nThiếu {len(missing_modules)} module(s). Cài đặt với:")
        print("pip install -r requirements.txt")
        return False
    
    print("Tất cả dependencies đã sẵn sàng!")
    return True

def check_mongodb():
    """Kiểm tra kết nối MongoDB"""
    print("\nĐang kiểm tra MongoDB...")
    
    try:
        import pymongo
        client = pymongo.MongoClient("mongodb://localhost:27017/", serverSelectionTimeoutMS=3000)
        client.admin.command('ping')
        print("MongoDB đã kết nối thành công!")
        client.close()
        return True
    except Exception as e:
        print(f" MongoDB không khả dụng: {e}")
        print("Hệ thống vẫn có thể chạy nhưng không có database persistence")
        return False

def check_camera():
    """Kiểm tra camera"""
    print("\nĐang kiểm tra camera...")
    
    try:
        import cv2
        cap = cv2.VideoCapture(0)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret:
                print("Camera hoạt động bình thường!")
                cap.release()
                return True
            else:
                print("Camera không thể capture frame")
        else:
            print("Không thể mở camera")
        cap.release()
        return False
    except Exception as e:
        print(f"Lỗi kiểm tra camera: {e}")
        return False

def check_files():
    """Kiểm tra các file cần thiết"""
    print("\nĐang kiểm tra files...")
    
    required_files = [
        'camera/video_camera.py',
        'camera/camera.py',
        'rfid/rfid_mqtt_server.py',
        'rfid/rfid_mqtt_server_v2.py',
        'database/whitelist_db.py',
        'config/settings.py'
    ]
    
    missing_files = []
    
    for file in required_files:
        file_path = os.path.join(src_dir, file)
        if os.path.exists(file_path):
            print(f" Có : {file}")
        else:
            print(f" Không có: {file}")
            missing_files.append(file)
    
    if missing_files:
        print(f"\nThiếu {len(missing_files)} file(s)")
        return False
    
    print("ất cả files đã sẵn sàng!")
    return True

def setup_environment():
    """Thiết lập môi trường"""
    print("Đang thiết lập môi trường...")
    
    # Tạo thư mục cần thiết
    from config.paths import IMAGE_DIR, PLATE_LOG_DIR, CAPTURED_PLATES_DIR, SNAPSHOT_DIR
    directories = [IMAGE_DIR, PLATE_LOG_DIR, CAPTURED_PLATES_DIR, SNAPSHOT_DIR]
    
    for full_path in directories:
        os.makedirs(full_path, exist_ok=True)
        print(f"  📁 {os.path.relpath(full_path, src_dir)}")
    
    print("Môi trường đã sẵn sàng!")

def start_integrated_system():
    """Khởi động hệ thống tích hợp"""
    print("\n Đang khởi động hệ thống tích hợp...")
    try:
        # Khởi động video_camera.py (đã tích hợp RFID) as a module
        process = subprocess.Popen([
            sys.executable, '-m', 'camera.video_camera'
        ], cwd=src_dir)
        
        print("Hệ thống tích hợp đã khởi động!")

        
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\nĐang dừng hệ thống...")
            process.terminate()
            
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Force killing process...")
                process.kill()
            
            print("Hệ thống đã dừng thành công")
        
    except Exception as e:
        print(f"Lỗi khởi động hệ thống: {e}")

def start_standalone_rfid():
    """Khởi động RFID server riêng biệt"""
    print("\nĐang khởi động RFID MQTT Server (standalone)...")
    
    try:
        process = subprocess.Popen([
            sys.executable, '-m', 'rfid.rfid_mqtt_server'
        ], cwd=src_dir)
        
        print("RFID MQTT Server đã khởi động!")
        
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\nĐang dừng RFID server...")
            process.terminate()
            
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Force killing process...")
                process.kill()
            
            print("RFID server đã dừng thành công")
        
    except Exception as e:
        print(f"Lỗi khởi động RFID server: {e}")

def start_camera_only():
    """Khởi động chỉ camera system"""
    print("\nĐang khởi động Camera System...")
    
    try:
        process = subprocess.Popen([
            sys.executable, '-m', 'camera.video_camera'
        ], cwd=src_dir)
        
        print("Camera System đã khởi động!")
        
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\nĐang dừng camera system...")
            process.terminate()
            
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print("Force killing process...")
                process.kill()
            
            print("Camera system đã dừng thành công")
        
    except Exception as e:
        print(f" Lỗi khởi động camera system: {e}")

def start_rfid_v2():
    """Khởi động RFID server version 2 (hỗ trợ vào/ra)"""
    print("\n Đang khởi động RFID MQTT Server v2 (Vào/Ra)...")
    
    try:
        process = subprocess.Popen([
            sys.executable, '-m', 'rfid.rfid_mqtt_server_v2'
        ], cwd=src_dir)
        
        print(" RFID MQTT Server v2 đã khởi động!")
        print("\n Press Ctrl+C to stop...")
        
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\n Đang dừng RFID server v2...")
            process.terminate()
            
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(" Force killing process...")
                process.kill()
            
            print(" RFID server v2 đã dừng thành công")
        
    except Exception as e:
        print(f" Lỗi khởi động RFID server v2: {e}")

def test_system():
    """Test các thành phần của hệ thống"""
    print("\nKIỂM TRA HỆ THỐNG")
    print("-" * 40)
    
    try:
        # Test database
        print("1. Kiểm tra Database...")
        from database.whitelist_db import WhitelistDB
        db = WhitelistDB()
        cards = db.get_all_cards()
        print(f"    Database: {len(cards)} thẻ trong whitelist")
        
        # Test UID mẫu
        test_uid = "A1B2C3D4"
        result = db.check_uid_allowed(test_uid)
        print(f"    Test UID {test_uid}: {'Cho phép' if result['allowed'] else 'Từ chối'}")
        
        # Test MQTT config
        print("2. Kiểm tra MQTT Config...")
        from config.settings import MQTT_BROKER, MQTT_PORT, TOPIC_SUB, TOPIC_PUB
        print(f"    MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
        print(f"    Subscribe: {TOPIC_SUB}")
        print(f"    Publish: {TOPIC_PUB}")
        
        print("\n Tất cả test đều PASS!")
        
    except Exception as e:
        print(f"❌ Lỗi test: {e}")

def show_config():
    """Hiển thị cấu hình hệ thống"""
    print("\n CẤU HÌNH HỆ THỐNG")
    print("-" * 40)
    
    try:
        import config.settings as mqtt_config
        
        print("🔐 RFID MQTT Configuration:")
        print(f"  - MQTT Broker: {mqtt_config.MQTT_BROKER}:{mqtt_config.MQTT_PORT}")
        print(f"  - Subscribe Topic: {mqtt_config.TOPIC_SUB}")
        print(f"  - Publish Topic: {mqtt_config.TOPIC_PUB}")
        print(f"  - MongoDB URI: {mqtt_config.MONGODB_URI}")
        print(f"  - Database: {mqtt_config.DATABASE_NAME}")
        print(f"  - Collection: {mqtt_config.COLLECTION_NAME}")
        
        print(f"\n📸 Camera Configuration:")
        print(f"  - Flask Host: {mqtt_config.FLASK_HOST}:{mqtt_config.FLASK_PORT}")
        print(f"  - Web Interface: http://{mqtt_config.FLASK_HOST}:{mqtt_config.FLASK_PORT}")
        print(f"  - Video Feed: http://{mqtt_config.FLASK_HOST}:{mqtt_config.FLASK_PORT}/video_feed")
        print(f"  - Snapshot API: http://{mqtt_config.FLASK_HOST}:{mqtt_config.FLASK_PORT}/snapshot?flag=1")
        
        print(f"\n🔗 Integrated APIs:")
        print(f"  - RFID Status: http://{mqtt_config.FLASK_HOST}:{mqtt_config.FLASK_PORT}/rfid/status")
        print(f"  - Whitelist: http://{mqtt_config.FLASK_HOST}:{mqtt_config.FLASK_PORT}/rfid/whitelist")
        print(f"  - Add Card: POST http://{mqtt_config.FLASK_HOST}:{mqtt_config.FLASK_PORT}/rfid/add_card")
        
    except Exception as e:
        print(f"❌ Lỗi đọc config: {e}")

def show_system_info():
    """Hiển thị thông tin hệ thống"""
    print("\nTHÔNG TIN HỆ THỐNG")
    print("="*50)
    print(f"Working Directory: {os.getcwd()}")
    print(f"Python: {sys.version}")
    print(f"Platform: {os.name}")
    print(f"Source Directory: {src_dir}")
    
    # Kiểm tra file quan trọng
    important_files = [
        "camera/video_camera.py",
        "camera/camera.py", 
        "rfid/rfid_mqtt_server.py",
        "rfid/rfid_mqtt_server_v2.py",
        "database/whitelist_db.py",
        "config/settings.py"
    ]
    
    print("\nCác file quan trọng:")
    for file_path in important_files:
        full_path = os.path.join(src_dir, file_path)
        if os.path.exists(full_path):
            print(f"   {file_path}")
        else:
            print(f"  ❌ {file_path}")

def main_menu():
    """Menu chính của ứng dụng"""
    print_banner()
    
    # Kiểm tra hệ thống
    deps_ok = check_dependencies()
    files_ok = check_files()
    
    if not deps_ok or not files_ok:
        print("\nVui lòng cài đặt dependencies và đảm bảo tất cả files tồn tại!")
        print("Chạy: pip install -r requirements.txt")
        return
    
    # Thiết lập môi trường
    setup_environment()
    
    # Kiểm tra các thành phần tùy chọn
    mongo_ok = check_mongodb()
    camera_ok = check_camera()
    
    print("\n" + "="*50)
    print("CHỌN CHẾ ĐỘ KHỞI ĐỘNG")
    print("="*50)
    print("1.Hệ thống tích hợp (RFID + Camera)")
    print("2.Chỉ RFID MQTT Server")
    print("3.Chỉ Camera System")
    print("4.RFID v2 (Hỗ trợ xe vào/ra)")
    print("5.Test hệ thống")
    print("6.Xem cấu hình")
    print("7.Thông tin hệ thống")
    print("8.Thoát")
    
    while True:
        try:
            choice = input("\nChọn chế độ (1-8): ").strip()
            
            if choice == "1":
                start_integrated_system()
                break
                
            elif choice == "2":
                start_standalone_rfid()
                break
                
            elif choice == "3":
                start_camera_only()
                break
                
            elif choice == "4":
                start_rfid_v2()
                break
                
            elif choice == "5":
                test_system()
                
            elif choice == "6":
                show_config()
                
            elif choice == "7":
                show_system_info()
                
            elif choice == "8":
                print("Tạm biệt!")
                break
                
            else:
                print("Lựa chọn không hợp lệ!")
                
        except KeyboardInterrupt:
            print("\nĐã dừng chương trình")
            break

def signal_handler(sig, frame):
    """Xử lý tín hiệu dừng"""
    print("\n\nĐang dừng hệ thống...")
    sys.exit(0)

if __name__ == "__main__":
    # Đăng ký signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        main_menu()
    except Exception as e:
        print(f"Lỗi khởi động: {e}")
        print("Vui lòng kiểm tra lại cài đặt và thử lại")

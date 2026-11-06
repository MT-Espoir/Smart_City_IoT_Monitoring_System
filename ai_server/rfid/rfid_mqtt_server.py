import paho.mqtt.client as mqtt
import json
import logging
import threading
import time
import requests
from datetime import datetime
from database.whitelist_db import WhitelistDB
from config.settings import *

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RFIDMQTTServer:
    def __init__(self):
        """Khởi tạo RFID MQTT Server"""
        self.client = mqtt.Client()
        self.db = WhitelistDB()
        self.is_running = False
        
        # Setup MQTT callbacks
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        self.client.on_disconnect = self.on_disconnect
        
        logger.info("🚀 RFID MQTT Server đã được khởi tạo")
    
    def on_connect(self, client, userdata, flags, rc):
        """Callback khi kết nối MQTT thành công"""
        if rc == 0:
            logger.info(f"✅ Đã kết nối MQTT Broker: {MQTT_BROKER}:{MQTT_PORT}")
            
            # Subscribe topic nhận UID từ thiết bị RFID
            client.subscribe(TOPIC_SUB)
            logger.info(f"📡 Đã subscribe topic: {TOPIC_SUB}")
            
            self.is_running = True
        else:
            logger.error(f"❌ Lỗi kết nối MQTT Broker. Code: {rc}")
    
    def on_disconnect(self, client, userdata, rc):
        """Callback khi mất kết nối MQTT"""
        logger.warning(f"⚠️ Mất kết nối MQTT Broker. Code: {rc}")
        self.is_running = False
    
    def on_message(self, client, userdata, msg):
        """
        Callback xử lý message nhận được từ MQTT
        
        Expected message format:
        {
            "uid": "A1B2C3D4",
            "device_id": "RFID_READER_001",
            "timestamp": "2025-05-25T10:30:00"
        }
        """
        try:
            # Decode message
            message = msg.payload.decode('utf-8')
            logger.info(f"📨 Nhận message từ {msg.topic}: {message}")
            
            # Parse JSON
            try:
                data = json.loads(message)
            except json.JSONDecodeError:
                # Nếu không phải JSON, coi như UID trực tiếp
                data = {"uid": message.strip()}
            
            uid = data.get("uid", "").strip()
            device_id = data.get("device_id", "UNKNOWN_DEVICE")
            
            if not uid:
                logger.warning("⚠️ Message không chứa UID hợp lệ")
                return
            
            # Kiểm tra UID trong whitelist
            auth_result = self.db.check_uid_allowed(uid)
            
            # Log access attempt
            self.db.log_access_attempt(
                uid=uid,
                allowed=auth_result["allowed"],
                additional_info={
                    "device_id": device_id,
                    "topic": msg.topic,
                    "timestamp": datetime.now().isoformat()
                }
            )
            
            # Tạo response message
            response = {
                "uid": uid,
                "allowed": auth_result["allowed"],
                "name": auth_result.get("name"),
                "department": auth_result.get("department"),
                "message": auth_result["message"],
                "timestamp": datetime.now().isoformat(),
                "device_id": device_id
            }
            
            # Gửi response về thiết bị
            self.send_response(response)
            
            # Nếu được phép truy cập, chụp ảnh từ camera
            if auth_result["allowed"]:
                self.trigger_camera_snapshot(uid, auth_result["name"])
            
        except Exception as e:
            logger.error(f"❌ Lỗi xử lý message: {e}")
            
            # Gửi error response
            error_response = {
                "uid": "UNKNOWN",
                "allowed": False,
                "message": f"Lỗi hệ thống: {str(e)}",
                "timestamp": datetime.now().isoformat(),
                "error": True
            }
            self.send_response(error_response)
    
    def send_response(self, response_data):
        """Gửi phản hồi về thiết bị qua MQTT"""
        try:
            response_json = json.dumps(response_data, ensure_ascii=False, indent=2)
            
            result = self.client.publish(TOPIC_PUB, response_json)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                status = "✅ Cho phép" if response_data["allowed"] else "❌ Từ chối"
                logger.info(f"📤 Đã gửi response: {status} - UID: {response_data['uid']}")
            else:
                logger.error(f"❌ Lỗi gửi response. Code: {result.rc}")
                
        except Exception as e:
            logger.error(f"❌ Lỗi gửi response: {e}")
    
    def trigger_camera_snapshot(self, uid, name):
        """Kích hoạt chụp ảnh từ camera khi truy cập thành công"""
        try:
            snapshot_url = f"http://{FLASK_HOST}:{FLASK_PORT}/snapshot?flag=1&crop=1"
            
            logger.info(f"📸 Đang chụp ảnh cho UID: {uid} - {name}")
            
            # Gửi request chụp ảnh (non-blocking)
            def capture_async():
                try:
                    response = requests.get(snapshot_url, timeout=10)
                    if response.status_code == 200:
                        logger.info(f"✅ Đã chụp ảnh thành công cho {name}")
                    else:
                        logger.warning(f"⚠️ Lỗi chụp ảnh: HTTP {response.status_code}")
                except requests.exceptions.RequestException as e:
                    logger.warning(f"⚠️ Không thể kết nối camera: {e}")
            
            # Chạy trong thread riêng để không block MQTT
            threading.Thread(target=capture_async, daemon=True).start()
            
        except Exception as e:
            logger.error(f"❌ Lỗi trigger camera: {e}")
    
    def start(self):
        """Khởi động MQTT Server"""
        try:
            logger.info(f"🔄 Đang kết nối tới MQTT Broker...")
            
            # Kết nối MQTT Broker
            self.client.connect(MQTT_BROKER, MQTT_PORT, 60)
            
            # Bắt đầu loop
            self.client.loop_start()
            
            logger.info("🚀 RFID MQTT Server đã khởi động!")
            logger.info(f"📡 Subscribe topic: {TOPIC_SUB}")
            logger.info(f"📤 Publish topic: {TOPIC_PUB}")
            logger.info(f"📸 Camera URL: http://{FLASK_HOST}:{FLASK_PORT}")
            
            # Keep running
            while True:
                if not self.is_running:
                    logger.warning("⚠️ MQTT connection lost. Attempting to reconnect...")
                    time.sleep(5)
                    try:
                        self.client.reconnect()
                    except Exception as e:
                        logger.error(f"❌ Reconnect failed: {e}")
                
                time.sleep(1)
                
        except KeyboardInterrupt:
            logger.info("🛑 Đang dừng server...")
            self.stop()
        except Exception as e:
            logger.error(f"❌ Lỗi khởi động server: {e}")
    
    def stop(self):
        """Dừng MQTT Server"""
        try:
            self.client.loop_stop()
            self.client.disconnect()
            logger.info("✅ RFID MQTT Server đã dừng")
        except Exception as e:
            logger.error(f"❌ Lỗi dừng server: {e}")
    
    def test_uid(self, uid):
        """Test function để kiểm tra UID"""
        logger.info(f"🧪 Testing UID: {uid}")
        
        # Tạo test message
        test_message = {
            "uid": uid,
            "device_id": "TEST_DEVICE",
            "timestamp": datetime.now().isoformat()
        }
        
        # Simulate incoming message
        class TestMessage:
            def __init__(self, payload, topic):
                self.payload = payload.encode('utf-8')
                self.topic = topic
        
        test_msg = TestMessage(json.dumps(test_message), TOPIC_SUB)
        self.on_message(self.client, None, test_msg)

# CLI Interface cho testing
def main():
    server = RFIDMQTTServer()
    
    print("\n🎯 RFID MQTT Access Control System")
    print("="*50)
    print("1. Khởi động server")
    print("2. Test UID")
    print("3. Xem danh sách thẻ")
    print("4. Thêm thẻ mới")
    print("5. Thoát")
    
    while True:
        try:
            choice = input("\n👉 Chọn chức năng (1-5): ").strip()
            
            if choice == "1":
                print("\n🚀 Đang khởi động RFID MQTT Server...")
                server.start()
                break
                
            elif choice == "2":
                uid = input("Nhập UID để test: ").strip()
                if uid:
                    server.test_uid(uid)
                
            elif choice == "3":
                cards = server.db.get_all_cards()
                print(f"\n📋 Danh sách thẻ ({len(cards)} thẻ):")
                for card in cards:
                    print(f"  - UID: {card['uid']} | {card['name']} | {card['department']}")
                
            elif choice == "4":
                uid = input("Nhập UID: ").strip()
                name = input("Nhập tên: ").strip()
                dept = input("Nhập phòng ban: ").strip() or "Unknown"
                
                if uid and name:
                    success = server.db.add_card(uid, name, dept)
                    if success:
                        print(f"✅ Đã thêm thẻ {uid} - {name}")
                    else:
                        print(f"❌ Lỗi thêm thẻ (có thể đã tồn tại)")
                
            elif choice == "5":
                print("👋 Tạm biệt!")
                break
                
            else:
                print("❌ Lựa chọn không hợp lệ!")
                
        except KeyboardInterrupt:
            print("\n🛑 Đã dừng chương trình")
            break

if __name__ == "__main__":
    main()

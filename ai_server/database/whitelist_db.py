import pymongo
from datetime import datetime
import logging
from config.settings import MONGODB_URI, DATABASE_NAME, COLLECTION_NAME

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WhitelistDB:
    def __init__(self):
        """Khởi tạo kết nối MongoDB"""
        try:
            self.client = pymongo.MongoClient(MONGODB_URI)
            self.db = self.client[DATABASE_NAME]
            self.collection = self.db[COLLECTION_NAME]
            # Thêm collection cho license plates
            self.license_plates_collection = self.db["license_plates"]
            # Thêm collection cho theo dõi xe vào/ra
            self.vehicle_tracking_collection = self.db["vehicle_tracking"]
            logger.info("✅ Đã kết nối MongoDB thành công")
            
            # Tạo sample data nếu collection trống
            self._init_sample_data()
            
        except Exception as e:
            logger.error(f"❌ Lỗi kết nối MongoDB: {e}")
            raise
    
    def _init_sample_data(self):
        """Khởi tạo dữ liệu mẫu cho whitelist"""
        if self.collection.count_documents({}) == 0:
            sample_cards = [
                {
                    "uid": "3D 6D CD 05",
                    "name": "Nguyễn Văn A",
                    "department": "IT",
                    "status": "active",
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                },
                {
                    "uid": "77 72 8F 04",
                    "name": "Trần Thị B", 
                    "department": "HR",
                    "status": "active",
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                },
                {
                    "uid": "I9J0K1L2",
                    "name": "Lê Văn C",
                    "department": "Security",
                    "status": "active", 
                    "created_at": datetime.now(),
                    "updated_at": datetime.now()
                }
            ]
            
            self.collection.insert_many(sample_cards)
            logger.info(f"✅ Đã thêm {len(sample_cards)} thẻ mẫu vào whitelist")
    
    def check_uid_allowed(self, uid):
        """
        Kiểm tra UID có trong danh sách cho phép không
        
        Args:
            uid (str): UID của thẻ RFID
            
        Returns:
            dict: Thông tin kết quả kiểm tra
        """
        try:
            card = self.collection.find_one({
                "uid": uid,
                "status": "active"
            })
            
            if card:
                logger.info(f"✅ UID {uid} được phép truy cập - {card['name']}")
                return {
                    "allowed": True,
                    "uid": uid,
                    "name": card["name"],
                    "department": card["department"],
                    "message": "Truy cập được phép"
                }
            else:
                logger.warning(f"❌ UID {uid} không được phép truy cập")
                return {
                    "allowed": False,
                    "uid": uid,
                    "name": None,
                    "department": None,
                    "message": "Truy cập bị từ chối"
                }
                
        except Exception as e:
            logger.error(f"❌ Lỗi kiểm tra UID {uid}: {e}")
            return {
                "allowed": False,
                "uid": uid,
                "name": None,
                "department": None,
                "message": f"Lỗi hệ thống: {str(e)}"
            }
    
    def add_card(self, uid, name, department="Unknown"):
        """Thêm thẻ mới vào whitelist"""
        try:
            card_data = {
                "uid": uid,
                "name": name,
                "department": department,
                "status": "active",
                "created_at": datetime.now(),
                "updated_at": datetime.now()
            }
            
            # Kiểm tra UID đã tồn tại chưa
            existing = self.collection.find_one({"uid": uid})
            if existing:
                logger.warning(f"⚠️ UID {uid} đã tồn tại")
                return False
            
            self.collection.insert_one(card_data)
            logger.info(f"✅ Đã thêm thẻ {uid} - {name}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Lỗi thêm thẻ {uid}: {e}")
            return False
    
    def remove_card(self, uid):
        """Xóa thẻ khỏi whitelist (soft delete)"""
        try:
            result = self.collection.update_one(
                {"uid": uid},
                {
                    "$set": {
                        "status": "inactive",
                        "updated_at": datetime.now()
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ Đã vô hiệu hóa thẻ {uid}")
                return True
            else:
                logger.warning(f"⚠️ Không tìm thấy thẻ {uid}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Lỗi xóa thẻ {uid}: {e}")
            return False
    
    def get_all_cards(self):
        """Lấy danh sách tất cả thẻ active"""
        try:
            cards = list(self.collection.find({"status": "active"}))
            return cards
        except Exception as e:
            logger.error(f"❌ Lỗi lấy danh sách thẻ: {e}")
            return []
    
    def log_access_attempt(self, uid, allowed, additional_info=None):
        """Ghi log lại việc truy cập"""
        try:
            log_collection = self.db["access_logs"]
            log_data = {
                "uid": uid,
                "allowed": allowed,
                "timestamp": datetime.now(),
                "additional_info": additional_info or {}
            }
            
            log_collection.insert_one(log_data)
            logger.info(f"📝 Đã ghi log truy cập: {uid} - {'Cho phép' if allowed else 'Từ chối'}")
            
        except Exception as e:
            logger.error(f"❌ Lỗi ghi log: {e}")
    
    def save_license_plate(self, plate_text, image_path=None):
        """
        Lưu thông tin biển số xe vào database
        
        Args:
            plate_text (str): Text của biển số xe
            image_path (str): Đường dẫn đến file ảnh (tùy chọn)
            
        Returns:
            str: ID của record được tạo, hoặc None nếu lỗi
        """
        try:
            if not plate_text or not plate_text.strip():
                logger.warning("⚠️ Plate text trống, không lưu vào database")
                return None
                
            plate_data = {
                "plate": plate_text.strip(),
                "time_in": datetime.now(),
                "image_path": image_path,
                "created_at": datetime.now()
            }
            
            result = self.license_plates_collection.insert_one(plate_data)
            plate_id = str(result.inserted_id)
            
            logger.info(f"💾 Đã lưu biển số: {plate_text} với ID: {plate_id}")
            return plate_id
            
        except Exception as e:
            logger.error(f"❌ Lỗi lưu biển số {plate_text}: {e}")
            return None
    
    def get_license_plates(self, limit=50):
        """
        Lấy danh sách biển số xe đã lưu
        
        Args:
            limit (int): Số lượng record tối đa trả về
            
        Returns:
            list: Danh sách các record biển số xe
        """
        try:
            plates = list(self.license_plates_collection.find()
                         .sort("time_in", -1)  # Sắp xếp theo thời gian mới nhất
                         .limit(limit))
            return plates
        except Exception as e:
            logger.error(f"❌ Lỗi lấy danh sách biển số: {e}")
            return []
    
    def search_license_plate(self, plate_text):
        """
        Tìm kiếm biển số xe trong database
        
        Args:
            plate_text (str): Text biển số cần tìm
            
        Returns:
            list: Danh sách các record matching
        """
        try:
            plates = list(self.license_plates_collection.find({
                "plate": {"$regex": plate_text, "$options": "i"}  # Tìm kiếm không phân biệt hoa thường
            }).sort("time_in", -1))
            return plates
        except Exception as e:
            logger.error(f"❌ Lỗi tìm kiếm biển số {plate_text}: {e}")
            return []

    # =============================================================================
    # VEHICLE TRACKING METHODS - Theo dõi xe vào/ra
    # =============================================================================
    
    def vehicle_entry(self, uid, license_plate, image_path=None):
        """
        Ghi nhận xe vào bãi
        
        Args:
            uid (str): UID của thẻ RFID
            license_plate (str): Biển số xe đã trích xuất
            image_path (str): Đường dẫn ảnh chụp
            
        Returns:
            dict: Kết quả ghi nhận
        """
        try:
            # Kiểm tra xe đã có trong bãi chưa
            existing_entry = self.vehicle_tracking_collection.find_one({
                "uid": uid,
                "status": "inside",
                "exit_time": None
            })
            
            if existing_entry:
                logger.warning(f"⚠️ Xe với UID {uid} đã có trong bãi")
                return {
                    "success": False,
                    "message": f"Xe đã có trong bãi từ {existing_entry['entry_time']}",
                    "existing_plate": existing_entry.get("license_plate")
                }
            
            # Tạo record mới cho xe vào
            entry_data = {
                "uid": uid,
                "license_plate": license_plate,
                "entry_time": datetime.now(),
                "entry_image": image_path,
                "status": "inside",
                "exit_time": None,
                "exit_image": None,
                "exit_license_plate": None,
                "match_status": None,
                "created_at": datetime.now()
            }
            
            result = self.vehicle_tracking_collection.insert_one(entry_data)
            entry_id = str(result.inserted_id)
            
            logger.info(f"🚗➡️ Xe vào: UID {uid}, Biển số {license_plate}")
            
            return {
                "success": True,
                "message": f"Xe vào thành công - Biển số: {license_plate}",
                "entry_id": entry_id,
                "license_plate": license_plate
            }
            
        except Exception as e:
            logger.error(f"❌ Lỗi ghi nhận xe vào {uid}: {e}")
            return {
                "success": False,
                "message": f"Lỗi hệ thống: {str(e)}"
            }
    
    def vehicle_exit(self, uid, license_plate, image_path=None):
        """
        Ghi nhận xe ra khỏi bãi và kiểm tra khớp biển số
        
        Args:
            uid (str): UID của thẻ RFID
            license_plate (str): Biển số xe đã trích xuất khi ra
            image_path (str): Đường dẫn ảnh chụp khi ra
            
        Returns:
            dict: Kết quả ghi nhận và kiểm tra
        """
        try:
            # Tìm record xe vào tương ứng
            entry_record = self.vehicle_tracking_collection.find_one({
                "uid": uid,
                "status": "inside",
                "exit_time": None
            })
            
            if not entry_record:
                logger.warning(f"⚠️ Không tìm thấy xe với UID {uid} trong bãi")
                return {
                    "success": False,
                    "message": f"Xe với UID {uid} không có trong bãi",
                    "match_status": "no_entry_record"
                }
            
            entry_plate = entry_record.get("license_plate", "")
            
            # So sánh biển số vào và ra
            plates_match = self._compare_license_plates(entry_plate, license_plate)
            
            # Cập nhật record với thông tin xe ra
            update_data = {
                "exit_time": datetime.now(),
                "exit_image": image_path,
                "exit_license_plate": license_plate,
                "status": "completed",
                "match_status": "match" if plates_match else "mismatch",
                "updated_at": datetime.now()
            }
            
            self.vehicle_tracking_collection.update_one(
                {"_id": entry_record["_id"]},
                {"$set": update_data}
            )
            
            result_message = f"Xe ra thành công - UID: {uid}"
            if plates_match:
                result_message += f"\n✅ Biển số khớp: {entry_plate}"
                logger.info(f"🚗⬅️✅ Xe ra khớp biển số: UID {uid}, {entry_plate} = {license_plate}")
            else:
                result_message += f"\n❌ Biển số KHÔNG khớp!\nVào: {entry_plate}\nRa: {license_plate}"
                logger.warning(f"🚗⬅️❌ Xe ra KHÔNG khớp biển số: UID {uid}, {entry_plate} ≠ {license_plate}")
            
            return {
                "success": True,
                "message": result_message,
                "match_status": "match" if plates_match else "mismatch",
                "entry_plate": entry_plate,
                "exit_plate": license_plate,
                "entry_time": entry_record["entry_time"],
                "exit_time": update_data["exit_time"]
            }
            
        except Exception as e:
            logger.error(f"❌ Lỗi ghi nhận xe ra {uid}: {e}")
            return {
                "success": False,
                "message": f"Lỗi hệ thống: {str(e)}"
            }
    
    def _compare_license_plates(self, plate1, plate2):
        """
        So sánh 2 biển số xe (cho phép sai khác nhỏ do OCR)
        
        Args:
            plate1 (str): Biển số thứ nhất
            plate2 (str): Biển số thứ hai
            
        Returns:
            bool: True nếu biển số khớp (hoặc gần khớp)
        """
        if not plate1 or not plate2:
            return False
        
        # Chuẩn hóa biển số (bỏ khoảng trắng, chuyển về chữ hoa)
        clean_plate1 = ''.join(plate1.upper().split())
        clean_plate2 = ''.join(plate2.upper().split())
        
        # Kiểm tra khớp hoàn toàn
        if clean_plate1 == clean_plate2:
            return True
        
        # Kiểm tra độ tương tự (cho phép 1-2 ký tự sai khác do OCR)
        if len(clean_plate1) == len(clean_plate2):
            diff_count = sum(c1 != c2 for c1, c2 in zip(clean_plate1, clean_plate2))
            # Cho phép tối đa 2 ký tự khác nhau (có thể do lỗi OCR)
            return diff_count <= 2
        
        return False
    
    def get_vehicles_in_parking(self):
        """
        Lấy danh sách xe hiện đang trong bãi
        
        Returns:
            list: Danh sách xe trong bãi
        """
        try:
            vehicles = list(self.vehicle_tracking_collection.find({
                "status": "inside",
                "exit_time": None
            }).sort("entry_time", -1))
            
            return vehicles
        except Exception as e:
            logger.error(f"❌ Lỗi lấy danh sách xe trong bãi: {e}")
            return []
    
    def get_vehicle_history(self, uid=None, limit=50):
        """
        Lấy lịch sử ra vào của xe
        
        Args:
            uid (str): UID cụ thể (None để lấy tất cả)
            limit (int): Số lượng record tối đa
            
        Returns:
            list: Lịch sử ra vào
        """
        try:
            query = {}
            if uid:
                query["uid"] = uid
            
            history = list(self.vehicle_tracking_collection.find(query)
                          .sort("entry_time", -1)
                          .limit(limit))
            
            return history
        except Exception as e:
            logger.error(f"❌ Lỗi lấy lịch sử xe: {e}")
            return []
    
    def get_mismatch_reports(self, limit=20):
        """
        Lấy danh sách các trường hợp biển số không khớp
        
        Args:
            limit (int): Số lượng record tối đa
            
        Returns:
            list: Danh sách các trường hợp không khớp
        """
        try:
            mismatches = list(self.vehicle_tracking_collection.find({
                "match_status": "mismatch"
            }).sort("exit_time", -1).limit(limit))
            
            return mismatches
        except Exception as e:
            logger.error(f"❌ Lỗi lấy báo cáo không khớp: {e}")
            return []

# Test functions
if __name__ == "__main__":
    print("🧪 Testing WhitelistDB...")
    
    try:
        db = WhitelistDB()
        
        # Test check existing UID
        result = db.check_uid_allowed("A1B2C3D4")
        print(f"Test UID A1B2C3D4: {result}")
        
        # Test check non-existing UID
        result = db.check_uid_allowed("XXXXXXXX")
        print(f"Test UID XXXXXXXX: {result}")
        
        # Test get all cards
        cards = db.get_all_cards()
        print(f"Tổng số thẻ active: {len(cards)}")
        
    except Exception as e:
        print(f"❌ Lỗi test: {e}")

import warnings
warnings.filterwarnings('ignore')

# Import necessary libraries
import os
import shutil
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import random
import cv2
import yaml
import torch
import pytesseract
from PIL import Image
from ultralytics import YOLO
from collections import deque
import subprocess  # For executing ffmpeg
# from IPython.display import display  # Import display for showing images
import glob  # Import glob for file pattern matching
from datetime import datetime  # For timestamp generation
from whitelist_db import WhitelistDB  # Import database functionality
# from run.detect.train7.weights import best  # Import the trained YOLOv8 model
# Define dataset paths relative to script directory to create absolute paths
script_dir = os.path.dirname(os.path.abspath(__file__))
train_dir = os.path.join(script_dir, "Data", "license-plate-dataset", "images", "train")
val_dir = os.path.join(script_dir, "Data", "license-plate-dataset", "images", "val")

# Define class names
classes = ["license_plate"]  # Add more classes if needed

pytesseract.pytesseract.tesseract_cmd = r'C:/Program Files/Tesseract-OCR/tesseract.exe'

# Load the trained YOLOv8 model (assuming you have already trained it)
model_path = os.path.join(script_dir, "..", "..", "yolov8n.pt")  # Path to YOLOv8 model in project root
model = YOLO(model_path)

def extract_plate_text_advanced(image_source, model, confidence_threshold=0.5, save_cropped=False, save_dir=None):
    """
    Hàm trích xuất biển số xe chất lượng cao với tiền xử lý nâng cao.
    
    Args:
        image_source: Có thể là đường dẫn file ảnh (str) hoặc frame ảnh (numpy array)
        model: Trained YOLO model
        confidence_threshold (float): Ngưỡng confidence cho detection (default: 0.5)
        save_cropped (bool): Có lưu ảnh biển số đã crop không
        save_dir (str): Thư mục lưu ảnh (nếu save_cropped=True)
        
    Returns:
        dict: {
            'texts': [list of extracted texts],
            'confidences': [list of detection confidences],
            'boxes': [list of bounding boxes],
            'cropped_images': [list of cropped plate images],
            'save_paths': [list of saved file paths if saved]
        }
    """
    result = {
        'texts': [],
        'confidences': [],
        'boxes': [],
        'cropped_images': [],
        'save_paths': []
    }
    
    # Xử lý input (file path hoặc frame)
    if isinstance(image_source, str):
        # Đọc từ file
        frame = cv2.imread(image_source)
        if frame is None:
            print(f"❌ Không thể đọc ảnh từ: {image_source}")
            return result
    else:
        # Sử dụng frame trực tiếp
        frame = image_source.copy()
    
    # Detect license plates
    results = model(frame)
    
    for result_item in results:
        if result_item.boxes is not None:
            for box in result_item.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                conf = box.conf[0].item()
                
                # Chỉ xử lý detection có confidence cao
                if conf > confidence_threshold:
                    # Crop license plate region
                    cropped_plate = frame[y1:y2, x1:x2]
                    
                    # Kiểm tra kích thước crop hợp lệ
                    if cropped_plate.size == 0:
                        continue
                    
                    try:
                        # === TIỀN XỬ LÝ ỢẢH NÂNG CAO ===
                        # Chuyển sang grayscale
                        gray_plate = cv2.cvtColor(cropped_plate, cv2.COLOR_BGR2GRAY)
                        
                        # Resize để cải thiện OCR (nếu ảnh quá nhỏ)
                        height, width = gray_plate.shape
                        if height < 50 or width < 100:
                            # Tính scale factor dựa trên kích thước tối ưu
                            scale_h = max(2, 50 // height)
                            scale_w = max(2, 100 // width)
                            scale_factor = min(scale_h, scale_w, 4)  # Giới hạn tối đa 4x
                            
                            new_width = int(width * scale_factor)
                            new_height = int(height * scale_factor)
                            gray_plate = cv2.resize(gray_plate, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
                        
                        # Áp dụng Gaussian blur để giảm noise
                        gray_plate = cv2.GaussianBlur(gray_plate, (3, 3), 0)
                        
                        # Áp dụng CLAHE (Contrast Limited Adaptive Histogram Equalization)
                        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                        gray_plate = clahe.apply(gray_plate)
                        
                        # Áp dụng adaptive threshold để cải thiện contrast
                        binary_plate = cv2.adaptiveThreshold(
                            gray_plate, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
                        )
                        
                        # Morphological operations để làm sạch ảnh
                        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
                        binary_plate = cv2.morphologyEx(binary_plate, cv2.MORPH_CLOSE, kernel)
                        
                        # === TRÍCH XUẤT TEXT VỚI NHIỀU CẤU HÌNH ===
                        # Cấu hình OCR cho biển số Việt Nam
                        ocr_configs = [
                            # Config 1: Tối ưu cho biển số có định dạng chuẩn
                            '--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.',
                            # Config 2: Single text line với whitelist
                            '--psm 7 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.',
                            # Config 3: Uniform block
                            '--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-.',
                            # Config 4: Single word
                            '--psm 8',
                            # Config 5: Default với preprocessing
                            '--psm 7'
                        ]
                        
                        best_text = ""
                        best_confidence = 0
                        
                        # Thử các cấu hình OCR khác nhau
                        for config in ocr_configs:
                            try:
                                # Thử với binary image
                                text = pytesseract.image_to_string(binary_plate, config=config).strip()
                                
                                # Nếu không có kết quả, thử với grayscale
                                if not text:
                                    text = pytesseract.image_to_string(gray_plate, config=config).strip()
                                
                                # Làm sạch text
                                cleaned_text = ''.join(char.upper() for char in text if char.isalnum() or char == '-')
                                
                                # Validate biển số Việt Nam
                                if _validate_vietnamese_license_plate(cleaned_text):
                                    best_text = cleaned_text
                                    break
                                elif len(cleaned_text) >= 4 and not best_text:
                                    best_text = cleaned_text
                                    
                            except Exception as e:
                                continue
                        
                        # Lưu kết quả
                        if best_text:
                            result['texts'].append(best_text)
                            result['confidences'].append(conf)
                            result['boxes'].append([x1, y1, x2, y2])
                            result['cropped_images'].append(cropped_plate)
                            
                            # Lưu ảnh cropped nếu được yêu cầu
                            if save_cropped and save_dir:
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                                filename = f"license_plate_{best_text}_{timestamp}.jpg"
                                save_path = os.path.join(save_dir, filename)
                                cv2.imwrite(save_path, cropped_plate)
                                result['save_paths'].append(save_path)
                                print(f"✅ Đã lưu biển số '{best_text}' tại: {save_path}")
                        
                    except Exception as e:
                        print(f"❌ Lỗi xử lý OCR: {e}")
                        continue
    
    return result

def _validate_vietnamese_license_plate(text):
    """
    Validate định dạng biển số Việt Nam
    
    Args:
        text (str): Text cần validate
        
    Returns:
        bool: True nếu hợp lệ
    """
    import re
    
    if not text or len(text) < 6:
        return False
    
    # Patterns cho biển số Việt Nam
    patterns = [
        r'^[0-9]{2}[A-Z]-[0-9]{3,5}$',      # 12A-12345
        r'^[0-9]{2}[A-Z][0-9]-[0-9]{3,5}$', # 12A1-12345  
        r'^[0-9]{2}[A-Z]{2}-[0-9]{3,5}$',   # 12AB-12345
        r'^[A-Z]{2}-[0-9]{3,5}$',           # HA-12345 (xe công)
        r'^[0-9]{2}[A-Z]{2}[0-9]{3,5}$',    # 12AB12345 (không có dấu gạch)
        r'^[0-9]{2}[A-Z][0-9]{3,5}$'        # 12A12345 (không có dấu gạch)
    ]
    
    for pattern in patterns:
        if re.match(pattern, text):
            return True
    
    return False

# Wrapper functions để tương thích ngược
def extract_plate_text(image_path, model, confidence_threshold=0.5, save_cropped=False, save_dir=None):
    """
    Detects license plates in an image using a YOLO model and extracts text using OCR.
    
    Args:
        image_path (str): The path to the input image.
        model: The trained YOLO model.
        confidence_threshold (float): Minimum confidence for detection
        save_cropped (bool): Whether to save cropped license plate images
        save_dir (str): Directory to save cropped images
        
    Returns:
        list: A list of extracted license plate texts.
    """
    # Use the advanced function for better results
    result = extract_plate_text_advanced(
        image_source=image_path,
        model=model,
        confidence_threshold=confidence_threshold,
        save_cropped=save_cropped,
        save_dir=save_dir
    )
    
    # Return only the texts for backward compatibility
    return result['texts']

# VideoCamera class for Flask streaming
class VideoCamera:
    def __init__(self, camera_index=0, auto_save_enabled=False):
        """
        Initialize the VideoCamera with camera index.
        
        Args:
            camera_index (int): Index of the camera to use (0 for default camera)
            auto_save_enabled (bool): Whether to enable automatic saving to database (default: False)
        """
        self.camera_index = camera_index
        self.cap = None
        self.model = model  # Use the globally loaded model
        self.save_dir = os.path.join(script_dir, "Data", "image")
        self.is_open = False
        self.auto_save_enabled = auto_save_enabled  # New flag to control auto-saving
        
        # Initialize database connection
        try:
            self.db = WhitelistDB()
            print("Database connection established for license plate storage")
        except Exception as e:
            print(f"Warning: Could not connect to database: {e}")
            self.db = None
          # Create save directory if it doesn't exist
        os.makedirs(self.save_dir, exist_ok=True)
        
    def open_camera(self):
        """Open camera connection"""
        if not self.is_open:
            self.cap = cv2.VideoCapture(self.camera_index)
            if self.cap.isOpened():
                self.is_open = True
                return True
            else:
                return False
            return True
        
    def close_camera(self):
        """Close camera connection"""
        if self.cap and self.is_open:
            self.cap.release()
            self.is_open = False
            
    def __enter__(self):
        """Context manager entry"""
        self.open_camera()
        if not self.is_open:
            raise RuntimeError(f"Could not open camera {self.camera_index}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close_camera()
            
    def get_frame(self, save_plate=False, crop_vehicle=False):
        """
        Capture a frame from the camera and optionally detect license plates.
        
        Args:
            save_plate (bool): Whether to save detected license plate images
            crop_vehicle (bool): Whether to return cropped vehicle image
            
        Returns:
            bytes: JPEG encoded frame
        """
        if not self.cap:
            self.cap = cv2.VideoCapture(self.camera_index)
            
        if not self.cap.isOpened():
            return None
            
        ret, frame = self.cap.read()
        if not ret:
            return None
        
        # If save_plate is True, use the advanced extraction function
        if save_plate:
            result = extract_plate_text_advanced(
                image_source=frame,
                model=self.model,
                confidence_threshold=0.5,
                save_cropped=True,
                save_dir=self.save_dir
            )
            
            # Draw bounding boxes and add text to frame
            for i, (text, conf, box) in enumerate(zip(result['texts'], result['confidences'], result['boxes'])):
                x1, y1, x2, y2 = box
                
                # Draw bounding box
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(frame, f'License Plate: {conf:.2f}', 
                          (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                
                if text:
                    print(f"Detected license plate text: {text}")
                    # Add text to the frame
                    cv2.putText(frame, f'Text: {text}', 
                              (x1, y2+20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 0), 2)
                      # Save to database if connected AND auto_save is enabled
                    if self.db and self.auto_save_enabled:
                        try:
                            save_path = result['save_paths'][i] if i < len(result['save_paths']) else None
                            self.db.save_license_plate(
                                plate_text=text,
                                image_path=save_path
                            )
                            print(f"License plate '{text}' saved to database (auto-save enabled)")
                        except Exception as db_error:
                            print(f"Error saving to database: {db_error}")
                    elif not self.auto_save_enabled:
                        print(f"License plate '{text}' detected but auto-save is disabled")
                    else:
                        print("Database not connected - skipping save")
        else:
            # Just detect and draw bounding boxes without saving
            results = self.model(frame)
            
            for result in results:
                if result.boxes is not None:
                    for box in result.boxes:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        conf = box.conf[0].item()
                        
                        if conf > 0.5:
                            # Draw bounding box
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                            cv2.putText(frame, f'License Plate: {conf:.2f}', 
                                      (x1, y1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        # If crop_vehicle is True and we're saving, return the cropped vehicle region
        if crop_vehicle and save_plate:
            # For now, we'll return the detected license plate region
            # You can modify this to crop the entire vehicle if needed
            results = self.model(frame)
            for result in results:
                if result.boxes is not None and len(result.boxes) > 0:
                    box = result.boxes[0]  # Take the first detection
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = box.conf[0].item()
                    
                    if conf > 0.5:
                        # Expand the crop area to include more of the vehicle
                        h, w = frame.shape[:2]
                        margin = 50
                        x1 = max(0, x1 - margin)
                        y1 = max(0, y1 - margin)
                        x2 = min(w, x2 + margin)
                        y2 = min(h, y2 + margin)
                        
                        cropped_frame = frame[y1:y2, x1:x2]
                        ret, jpeg = cv2.imencode('.jpg', cropped_frame)
                        return jpeg.tobytes()
        
        # Encode frame as JPEG
        ret, jpeg = cv2.imencode('.jpg', frame)
        if ret:
            return jpeg.tobytes()
        else:
            return None
    
    def get_recent_license_plates(self, limit=10):
        """
        Get recently detected license plates from database.
        
        Args:
            limit (int): Maximum number of records to return
            
        Returns:
            list: List of license plate records or empty list if no database connection
        """
        if self.db:
            try:
                return self.db.get_license_plates(limit=limit)
            except Exception as e:
                print(f"Error retrieving license plates: {e}")
                return []
        else:
            print("Database not connected")
            return []
    
    def search_license_plate(self, plate_text):
        """
        Search for a specific license plate in the database.
        
        Args:
            plate_text (str): License plate text to search for
            
        Returns:
            list: List of matching records or empty list if no database connection
        """
        if self.db:
            try:
                return self.db.search_license_plate(plate_text)
            except Exception as e:
                print(f"Error searching license plate: {e}")
                return []
        else:
            print("Database not connected")
            return []
    
    def enable_auto_save(self):
        """Enable automatic saving of detected license plates to database"""
        self.auto_save_enabled = True
        print("📝 Auto-save enabled for license plate detection")
    
    def disable_auto_save(self):
        """Disable automatic saving of detected license plates to database"""
        self.auto_save_enabled = False
        print("🚫 Auto-save disabled for license plate detection")
    
    def is_auto_save_enabled(self):
        """Check if auto-save is currently enabled"""
        return self.auto_save_enabled

    def __del__(self):
        """Destructor to release camera"""
        if self.cap:
            self.cap.release()

# Function to extract text from image frame (for direct use)
def extract_plate_text_from_frame(frame, model, confidence_threshold=0.5, save_cropped=False, save_dir=None):
    """
    Detects license plates in a frame and extracts text using OCR.
    
    Args:
        frame: OpenCV image frame
        model: The trained YOLO model
        confidence_threshold (float): Minimum confidence for detection
        save_cropped (bool): Whether to save cropped license plate images
        save_dir (str): Directory to save cropped images
        
    Returns:
        list: A list of extracted license plate texts
    """
    # Use the advanced function for better results
    result = extract_plate_text_advanced(
        image_source=frame,
        model=model,
        confidence_threshold=confidence_threshold,
        save_cropped=save_cropped,
        save_dir=save_dir
    )
    
    # Return only the texts for backward compatibility
    return result['texts']

# --- Example Usage ---
if __name__ == "__main__":
    # Test with static images
    all_images = glob.glob("Test/*.jpg")
    
    if all_images:
        # Select a few images for testing
        test_images = random.sample(all_images, min(3, len(all_images)))
        
        for img_path in test_images:
            print(f"Processing image: {os.path.basename(img_path)}")
            plate_texts = extract_plate_text(img_path, model)
            
            if plate_texts:
                print(f"Detected plate text(s): {', '.join(plate_texts)}")
            else:
                print("No license plates detected or text extracted.")
            print("-" * 30)
    
    # Test with camera (uncomment to test)
    # print("Testing camera...")
    # try:
    #     with VideoCamera() as cam:
    #         for i in range(10):  # Capture 10 frames
    #             frame = cam.get_frame(save_plate=True)
    #             if frame:
    #                 print(f"Captured frame {i+1}")
    #             else:
    #                 print(f"Failed to capture frame {i+1}")
    # except Exception as e:
    #     print(f"Camera test failed: {e}")
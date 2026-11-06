import os

# Thư mục gốc của source (src/), dùng làm mốc cho mọi đường dẫn
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DATA_DIR = os.path.join(SRC_DIR, "Data")
IMAGE_DIR = os.path.join(DATA_DIR, "image")
PLATE_LOG_DIR = os.path.join(DATA_DIR, "plate_logs")
DATASET_DIR = os.path.join(DATA_DIR, "license-plate-dataset")
CAPTURED_PLATES_DIR = os.path.join(SRC_DIR, "captured_plates")
SNAPSHOT_DIR = os.path.join(SRC_DIR, "mqtt_snapshots")

# YOLOv8 model nằm ở thư mục Study/ (giữ nguyên vị trí cũ)
MODEL_PATH = os.path.join(SRC_DIR, "..", "..", "yolov8n.pt")

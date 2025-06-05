# MQTT Configuration
MQTT_BROKER = "test.mosquitto.org"
MQTT_PORT = 1883

# Topics cho RFID vào/ra
TOPIC_SUB_IN = "yolouno/rfid/scan/in"     # Quét thẻ xe vào
TOPIC_SUB_OUT = "yolouno/rfid/scan/out"   # Quét thẻ xe ra
TOPIC_PUB_IN = "yolouno/rfid/response/in" # Phản hồi xe vào
TOPIC_PUB_OUT = "yolouno/rfid/response/out" # Phản hồi xe ra

# Backward compatibility
TOPIC_SUB = TOPIC_SUB_IN  # Giữ topic cũ cho tương thích
TOPIC_PUB = TOPIC_PUB_IN

# MongoDB Configuration
MONGODB_URI = "mongodb://localhost:27017/"
DATABASE_NAME = "rfid_system"
COLLECTION_NAME = "whitelist"

# Flask Configuration for integration
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000

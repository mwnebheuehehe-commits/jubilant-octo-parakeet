# config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # API Server
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    API_VERSION = "v1"
    
    # MongoDB
    MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    DATABASE_NAME = os.getenv("DATABASE_NAME", "neutron_botnet")
    
    # Security
    JWT_SECRET = os.getenv("JWT_SECRET", "neutron_super_secret_key_2024_159357")
    JWT_ALGORITHM = "HS256"
    
    # Attack Settings (Game Server Takedown)
    MIN_BANDWIDTH_GBPS = 3.0
    MAX_BANDWIDTH_GBPS = 7.0
    OPTIMAL_BANDWIDTH_GBPS = 5.0
    MIN_PPS = 1_000_000
    MAX_PPS = 2_000_000
    OPTIMAL_PPS = 1_500_000
    
    # Attack Limits
    MAX_ATTACK_DURATION = 3600
    MIN_ATTACK_DURATION = 10
    DEFAULT_DURATION = 45
    DEFAULT_THREADS = 12
    DEFAULT_METHOD = 0
    
    # Rate Limiting
    RATE_LIMIT_CALLS = 100
    RATE_LIMIT_PERIOD = 60
    
    # Binary Path
    BINARY_PATH = "./neutron"
    
    # API Key Plans
    PLANS = {
        "BASIC": {"concurrent": 1, "duration_limit": 300, "bandwidth_limit": 3.0, "price": 0},
        "PRO": {"concurrent": 5, "duration_limit": 1800, "bandwidth_limit": 5.0, "price": 500},
        "ENTERPRISE": {"concurrent": 20, "duration_limit": 7200, "bandwidth_limit": 10.0, "price": 2000}
    }

config = Config()

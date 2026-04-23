# database.py
from pymongo import MongoClient
from datetime import datetime, timedelta
import secrets
from typing import Optional, Dict, List
from config import config

class Database:
    def __init__(self):
        self.client = MongoClient(config.MONGODB_URL)
        self.db = self.client[config.DATABASE_NAME]
        
        # Collections
        self.api_keys = self.db.api_keys
        self.attacks = self.db.attacks
        self.users = self.db.users
        self.stats = self.db.stats
        
        # Create indexes
        self.api_keys.create_index("key", unique=True)
        self.api_keys.create_index("user_id")
        self.attacks.create_index("attack_id", unique=True)
        self.attacks.create_index("api_key")
        self.attacks.create_index("started_at")
        
    def generate_api_key(self, user_id: str, plan: str, concurrent: int, expiry_days: int) -> Dict:
        """Generate new API key"""
        key_value = f"neutron_{secrets.token_hex(24)}"
        expiry_date = datetime.utcnow() + timedelta(days=expiry_days)
        
        key_doc = {
            "key": key_value,
            "user_id": user_id,
            "plan": plan,
            "max_concurrent": concurrent,
            "created_at": datetime.utcnow(),
            "expiry_date": expiry_date,
            "status": "active",
            "total_attacks": 0,
            "total_bandwidth": 0.0,
            "last_used": None
        }
        self.api_keys.insert_one(key_doc)
        return key_doc
    
    def validate_api_key(self, key_value: str) -> Optional[Dict]:
        """Validate API key"""
        key_doc = self.api_keys.find_one({"key": key_value, "status": "active"})
        if not key_doc:
            return None
        if key_doc["expiry_date"] < datetime.utcnow():
            self.api_keys.update_one({"key": key_value}, {"$set": {"status": "expired"}})
            return None
        self.api_keys.update_one({"key": key_value}, {"$set": {"last_used": datetime.utcnow()}})
        return key_doc
    
    def revoke_key(self, key_value: str) -> bool:
        """Revoke API key"""
        result = self.api_keys.update_one({"key": key_value}, {"$set": {"status": "revoked"}})
        return result.modified_count > 0
    
    def renew_key(self, key_value: str, days: int = 30) -> bool:
        """Renew API key"""
        new_expiry = datetime.utcnow() + timedelta(days=days)
        result = self.api_keys.update_one({"key": key_value}, {"$set": {"expiry_date": new_expiry, "status": "active"}})
        return result.modified_count > 0
    
    def update_concurrent_limit(self, key_value: str, concurrent: int) -> bool:
        """Update concurrent attack limit"""
        result = self.api_keys.update_one({"key": key_value}, {"$set": {"max_concurrent": concurrent}})
        return result.modified_count > 0
    
    def list_keys(self, user_id: str) -> List[Dict]:
        """List all keys for user"""
        keys = list(self.api_keys.find({"user_id": user_id}))
        for k in keys:
            k["_id"] = str(k["_id"])
        return keys
    
    def get_key_stats(self, key_value: str) -> Optional[Dict]:
        """Get key usage statistics"""
        key_doc = self.api_keys.find_one({"key": key_value})
        if not key_doc:
            return None
        
        attacks = list(self.attacks.find({"api_key": key_value}).sort("started_at", -1).limit(50))
        for a in attacks:
            a["_id"] = str(a["_id"])
        
        return {
            "key_info": {
                "key": key_doc["key"][:16] + "...",
                "plan": key_doc["plan"],
                "max_concurrent": key_doc["max_concurrent"],
                "created_at": key_doc["created_at"].isoformat(),
                "expiry_date": key_doc["expiry_date"].isoformat(),
                "status": key_doc["status"],
                "total_attacks": key_doc["total_attacks"],
                "total_bandwidth": key_doc["total_bandwidth"]
            },
            "recent_attacks": attacks[:20]
        }
    
    def log_attack(self, attack_id: str, api_key: str, target_ip: str, target_port: int,
                   method: str, duration: int, bandwidth_gbps: float, pps: int, status: str = "running") -> Dict:
        """Log attack to database"""
        attack_doc = {
            "attack_id": attack_id,
            "api_key": api_key,
            "target_ip": target_ip,
            "target_port": target_port,
            "method": method,
            "duration": duration,
            "bandwidth_gbps": bandwidth_gbps,
            "pps": pps,
            "status": status,
            "started_at": datetime.utcnow(),
            "ended_at": None
        }
        self.attacks.insert_one(attack_doc)
        
        # Update key stats
        self.api_keys.update_one({"key": api_key}, {"$inc": {"total_attacks": 1, "total_bandwidth": bandwidth_gbps}})
        return attack_doc
    
    def update_attack_status(self, attack_id: str, status: str):
        """Update attack status"""
        self.attacks.update_one({"attack_id": attack_id}, {"$set": {"status": status, "ended_at": datetime.utcnow()}})
    
    def get_active_attacks(self, api_key: str = None) -> List[Dict]:
        """Get active attacks"""
        query = {"status": "running"}
        if api_key:
            query["api_key"] = api_key
        attacks = list(self.attacks.find(query))
        for a in attacks:
            a["_id"] = str(a["_id"])
        return attacks
    
    def get_attack_history(self, api_key: str = None, limit: int = 100, offset: int = 0) -> List[Dict]:
        """Get attack history"""
        query = {}
        if api_key:
            query["api_key"] = api_key
        attacks = list(self.attacks.find(query).sort("started_at", -1).skip(offset).limit(limit))
        for a in attacks:
            a["_id"] = str(a["_id"])
        return attacks
    
    def get_attack_stats(self, api_key: str = None) -> Dict:
        """Get attack statistics"""
        query = {}
        if api_key:
            query["api_key"] = api_key
        
        pipeline = [
            {"$match": query},
            {"$group": {
                "_id": None,
                "total_attacks": {"$sum": 1},
                "total_bandwidth": {"$sum": "$bandwidth_gbps"},
                "avg_duration": {"$avg": "$duration"},
                "avg_bandwidth": {"$avg": "$bandwidth_gbps"},
                "avg_pps": {"$avg": "$pps"}
            }}
        ]
        result = list(self.attacks.aggregate(pipeline))
        
        if result:
            return result[0]
        return {
            "total_attacks": 0,
            "total_bandwidth": 0,
            "avg_duration": 0,
            "avg_bandwidth": 0,
            "avg_pps": 0
        }

db = Database()

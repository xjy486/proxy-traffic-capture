from flask import Flask, request, jsonify
import subprocess
import threading
import time
import os
import signal
import shutil
from pathlib import Path

app = Flask(__name__)

# --- 配置区域 ---
# 基础路径
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Xray路径
XRAY_EXEC = "./xray_custom"
XRAY_CONFIG = "/home/mijiu/Desktop/config/local_config.json"
# sudo密码
SUDO_PASSWORD = "1234"
# 网卡名称
DEFAULT_INTERFACE = "ens33"

# --- 网络初始化功能 ---
def run_sudo_command(cmd_list):
    """辅助函数：使用密码执行sudo命令"""
    try:
        # 使用 -S 参数从标准输入读取密码
        full_cmd = ['sudo', '-S'] + cmd_list
        proc = subprocess.Popen(
            full_cmd, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.PIPE
        )
        # 传入密码
        stdout, stderr = proc.communicate(input=f"{SUDO_PASSWORD}\n".encode())
        
        if proc.returncode != 0:
            # 虽然要求静默，但如果出错最好记录一下，方便调试
            # print(f"Command failed: {' '.join(cmd_list)} | Error: {stderr.decode().strip()}")
            pass
        return True
    except Exception as e:
        # print(f"Execution error: {e}")
        return False

def init_network_config(interface):
    """在启动时静默初始化网卡配置"""
    print(f"[*] Initializing network interface {interface} (disabling offloading)...")
    
    commands = [
        # 1. 查看配置 (虽然只是查看，但也按要求执行)
        ['ethtool', '-k', interface],
        # 2. 关闭 TSO, GSO, UFO
        ['ethtool', '-K', interface, 'tso', 'off', 'gso', 'off', 'ufo', 'off'],
        # 3. 关闭 GRO, LRO
        ['ethtool', '-K', interface, 'gro', 'off', 'lro', 'off'],
        # 4. 关闭 TX, RX checksum
        ['ethtool', '-K', interface, 'tx', 'off', 'rx', 'off']
    ]
    
    for cmd in commands:
        run_sudo_command(cmd)
        
    print("[*] Network initialization completed.")

# --- 任务管理器类 ---
class TaskManager:
    def __init__(self):
        # 结构: { "domain_idx": { "processes": [], "timer": timer_obj, "files": [] } }
        self.active_tasks = {}
        self.lock = threading.Lock()

    def _get_task_key(self, domain, idx):
        return f"{domain}_{idx}"

    def _ensure_dirs(self, domain):
        """确保日志和抓包目录存在"""
        dirs = [
            os.path.join(BASE_DIR, "logs", domain),
            os.path.join(BASE_DIR, "pcapng", "tls", domain),
            os.path.join(BASE_DIR, "pcapng", "proxy", domain)
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)
        return dirs

    def start_combined_task(self, domain, idx, tls_port, proxy_port, interface=DEFAULT_INTERFACE, timeout=60):
        key = self._get_task_key(domain, idx)
        
        with self.lock:
            if key in self.active_tasks:
                return False, f"Task {key} is already running."

        # 1. 准备目录和文件路径
        log_dir, tls_dir, proxy_dir = self._ensure_dirs(domain)
        
        log_file = os.path.join(log_dir, f"{idx}.log")
        tls_pcap = os.path.join(tls_dir, f"{idx}.pcapng")
        proxy_pcap = os.path.join(proxy_dir, f"{idx}.pcapng")

        processes = []
        process_files = [log_file, tls_pcap, proxy_pcap]

        try:
            # --- 命令 1: 启动 Xray 代理 ---
            log_fp = open(log_file, 'w')
            xray_cmd = [
                XRAY_EXEC,
                '--config', XRAY_CONFIG
            ]
            proc_xray = subprocess.Popen(xray_cmd, stdout=log_fp, stderr=subprocess.STDOUT)
            processes.append({'proc': proc_xray, 'type': 'xray', 'file_obj': log_fp})
            
            time.sleep(0.5)

            # --- 命令 2: 启动 TLS 流量捕获 ---
            # 注意：dumpcap通常也需要root权限，如果脚本以普通用户运行，这里可能需要调整
            # 但既然提供了sudo密码，我们可以尝试用sudo启动dumpcap，或者假设脚本本身就是sudo运行的
            dumpcap_tls_cmd = [
                'dumpcap', '-i', interface, '-f', f'port {tls_port}',
                '-w', tls_pcap, '-q'
            ]
            # 为了确保有权限，这里也可以加上sudo逻辑，但通常建议直接用sudo python server.py运行整个脚本
            # 这里保持原样，假设环境已配置好 capabilities 或以 root 运行
            proc_tls = subprocess.Popen(dumpcap_tls_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            processes.append({'proc': proc_tls, 'type': 'dumpcap_tls'})

            # --- 命令 3: 启动 Proxy 流量捕获 ---
            dumpcap_proxy_cmd = [
                'dumpcap', '-i', interface, '-f', f'port {proxy_port}',
                '-w', proxy_pcap, '-q'
            ]
            proc_proxy = subprocess.Popen(dumpcap_proxy_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            processes.append({'proc': proc_proxy, 'type': 'dumpcap_proxy'})

            # --- 设置超时自动停止 ---
            timer = threading.Timer(timeout, self.stop_task, [domain, idx])
            timer.start()

            # 注册任务
            with self.lock:
                self.active_tasks[key] = {
                    'processes': processes,
                    'timer': timer,
                    'start_time': time.time(),
                    'files': process_files
                }

            return True, f"Started task {key}. Output files: {process_files}"

        except Exception as e:
            self._kill_processes(processes)
            return False, str(e)

    def stop_task(self, domain, idx):
        key = self._get_task_key(domain, idx)
        
        with self.lock:
            if key not in self.active_tasks:
                return False, "Task not found"
            
            task_info = self.active_tasks[key]
            
            if task_info['timer'].is_alive():
                task_info['timer'].cancel()
            
            self._kill_processes(task_info['processes'])
            del self.active_tasks[key]
            
        return True, "Task stopped successfully"

    def _kill_processes(self, processes_list):
        for p_info in processes_list:
            proc = p_info.get('proc')
            try:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
            except Exception as e:
                pass # 静默处理错误
            
            if 'file_obj' in p_info and p_info['file_obj']:
                try:
                    p_info['file_obj'].close()
                except:
                    pass

    def delete_files(self, domain, idx):
        key = self._get_task_key(domain, idx)
        if key in self.active_tasks:
            return False, "Task is currently running. Stop it first."

        files_to_remove = [
            os.path.join(BASE_DIR, "logs", domain, f"{idx}.log"),
            os.path.join(BASE_DIR, "pcapng", "tls", domain, f"{idx}.pcapng"),
            os.path.join(BASE_DIR, "pcapng", "proxy", domain, f"{idx}.pcapng")
        ]

        deleted = []
        errors = []

        for f_path in files_to_remove:
            try:
                if os.path.exists(f_path):
                    os.remove(f_path)
                    deleted.append(f_path)
            except Exception as e:
                errors.append(f"{f_path}: {str(e)}")

        msg = f"Deleted: {len(deleted)} files."
        if errors:
            msg += f" Errors: {'; '.join(errors)}"
        
        return True, msg

# 全局管理器实例
manager = TaskManager()

# --- API 路由 ---

@app.route('/api/start_task', methods=['POST'])
def start_task_endpoint():
    data = request.json
    domain = data.get('domain')
    idx = data.get('idx')
    tls_port = data.get('tls_port')
    proxy_port = data.get('proxy_port')
    interface = data.get('interface', DEFAULT_INTERFACE)
    timeout = data.get('timeout', 60)

    if not all([domain, idx, tls_port, proxy_port]):
        return jsonify({'success': False, 'message': 'Missing required params'}), 400

    success, msg = manager.start_combined_task(str(domain), str(idx), tls_port, proxy_port, interface, int(timeout))
    return jsonify({'success': success, 'message': msg}), 200 if success else 500

@app.route('/api/stop_task', methods=['POST'])
def stop_task_endpoint():
    data = request.json
    domain = data.get('domain')
    idx = data.get('idx')

    if not domain or idx is None:
        return jsonify({'success': False, 'message': 'Missing domain or idx'}), 400

    success, msg = manager.stop_task(str(domain), str(idx))
    return jsonify({'success': success, 'message': msg}), 200 if success else 404

@app.route('/api/delete_files', methods=['POST'])
def delete_files_endpoint():
    data = request.json
    domain = data.get('domain')
    idx = data.get('idx')

    if not domain or idx is None:
        return jsonify({'success': False, 'message': 'Missing domain or idx'}), 400

    success, msg = manager.delete_files(str(domain), str(idx))
    return jsonify({'success': success, 'message': msg}), 200 if success else 500

# --- 主程序入口 ---

if __name__ == '__main__':
    # 1. 启动时先执行 ethtool 配置
    init_network_config(DEFAULT_INTERFACE)
    
    # 2. 启动 Flask 服务
    print("[*] Starting Flask server...")
    app.run(host='0.0.0.0', port=5000, debug=False)

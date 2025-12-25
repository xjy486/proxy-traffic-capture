import os
import yaml
from typing import Dict, Any

def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    """
    从 yaml 文件加载配置。
    
    Args:
        config_path: 配置文件路径，默认为 "config.yaml"
        
    Returns:
        配置字典。如果文件不存在，返回空字典。
    """
    if not os.path.exists(config_path):
        return {}
    try:
        with open(config_path, 'r', encoding='utf-8') as config_file:
            return yaml.safe_load(config_file) or {}
    except Exception as e:
        print(f"加载配置文件失败: {e}")
        return {}

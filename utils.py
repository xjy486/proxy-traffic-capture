import os
from pathlib import Path
import re
from typing import Dict, Optional

import yaml
from urllib.parse import urlparse
from config_manager import load_config

def parse_domain(url: str) -> str:
    """提取 URL 的域名部分"""
    return urlparse(url).netloc
    
def load_websites(filename: str, count: int) -> tuple[dict, int]:
    """
    返回的数据格式
    websites = {
        "domain":{"url":[url1, url2], "count":count},
    }
    total 总访问次数
    """
    with open(filename, 'r') as f:
        lines = f.readlines()
    websites = {}
    total = 0
    for line in lines:
        url = line.strip()
        if not url:
            continue
        domain = parse_domain(url)
        if domain not in websites:
            websites[domain] = {"url": [], "count": count}
            total += count
        websites[domain]["url"].append(url)
    return websites, total

def load_websites_simple(filename: str) -> tuple[dict, int]:
    """
    返回的数据格式
    websites = {
        "domain":{"url":[url], "count":count},
    }
    total 总访问次数
    """
    with open(filename, 'r') as f:
        lines = f.readlines()
    websites = {}
    total = 0
    for line in lines:
        url = line.strip()
        if not url:
            continue
        domain = parse_domain(url)
        if domain not in websites:
            websites[domain] = {"url": [], "count": 0}
        websites[domain]["url"].append(url)
        websites[domain]["count"] += 1
        total += 1
    return websites, total

def get_tasks_mode_1(filename="websites.txt", count=1):
    """
    模式一：给定一个websites.txt 和 访问次数
    实现每次从websites中取出来自不同的domain下的一个url进行访问，如果访问成功则count-1，如果domain遍历完毕，再从头开始，直到所有的domain的count都为0
    """
    websites, total = load_websites(filename, count)
    domains = list(websites.keys())
    tasks = []
    
    while total > 0:
        for domain in domains:
            if websites[domain]['count'] > 0:
                urls = websites[domain]['url']
                # 轮询获取URL，如果count大于URL数量，则循环使用
                idx = (count - websites[domain]['count']) % len(urls)
                url = urls[idx]
                tasks.append(url)
                websites[domain]['count'] -= 1
                total -= 1
    return tasks

def get_tasks_mode_2(filename="websites.txt"):
    """
    模式二：给定一个websites.txt，文件中可能有重复的url，实现每次从websites中取出来自不同的domain下的一个url进行访问，访问成功后该domain下的url从列表中删除，直到所有的domain的url列表都为空
    """
    websites, total = load_websites_simple(filename)
    domains = list(websites.keys())
    tasks = []
    
    while total > 0:
        for domain in domains:
            if websites[domain]['count'] > 0 and websites[domain]['url']:
                url = websites[domain]['url'].pop(0)
                tasks.append(url)
                websites[domain]['count'] -= 1
                total -= 1
    return tasks




def _sanitize_domain(domain: str) -> str:
    """替换域名中的非法文件名字符"""
    if not domain:
        return "unknown"
    return re.sub(r"[^A-Za-z0-9._-]", "_", domain)


def _next_screenshot_index(directory: Path) -> int:
    """基于现有截图文件推断下一个索引"""
    max_index = -1
    for image_path in directory.glob("*.png"):
        try:
            max_index = max(max_index, int(image_path.stem))
        except ValueError:
            continue
    return max_index + 1


def gen_screenshot(url: str, config: Optional[dict] = None) -> str:
    """生成截图文件路径，并确保目录存在"""
    return prepare_capture_context(url, config)["screenshot_path"]


def prepare_capture_context(url: str, config: Optional[dict] = None) -> Dict[str, object]:
    """预留截图路径并返回抓包相关上下文信息"""
    if config is None:
        config = load_config()

    file_cfg = config.get("file", {})
    root_dir = file_cfg.get("screenshots_dir", "screenshots")
    domain = _sanitize_domain(parse_domain(url))
    domain_dir = Path(root_dir) / domain
    domain_dir.mkdir(parents=True, exist_ok=True)

    index = _next_screenshot_index(domain_dir)
    screenshot_path = domain_dir / f"{index}.png"

    return {
        "domain": domain,
        "index": index,
        "index_str": str(index),
        "screenshot_path": str(screenshot_path),
        "directory": str(domain_dir),
    }
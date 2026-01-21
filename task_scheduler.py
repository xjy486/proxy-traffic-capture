import logging
from collections import deque
from typing import Iterable, List, Optional, Union

from driver import get_firefox_driver
from config_manager import load_config
from utils import get_tasks_mode_1
from process_handler import process_single_url

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def _normalize_urls(urls: Optional[Union[str, Iterable[str]]]) -> List[str]:
    """将输入标准化为 URL 列表"""
    if urls is None:
        return []
    if isinstance(urls, str):
        stripped = urls.strip()
        return [stripped] if stripped else []

    normalized: List[str] = []
    for item in urls:
        if not isinstance(item, str):
            continue
        stripped = item.strip()
        if stripped:
            normalized.append(stripped)
    return normalized

def run_tasks(urls: Optional[Union[str, Iterable[str]]] = None):
    """
    启动任务队列，处理所有 URL。
    
    Args:
        urls: 可选的 URL 列表。如果未提供，将从配置文件指定的网站列表中读取。
    """
    config = load_config()
    
    # 1. 获取 URL 列表
    normalized_urls = _normalize_urls(urls)
    if not normalized_urls:
        websites_cfg = config.get("websites", {})
        websites_file = websites_cfg.get("file", "websites.txt")
        visit_count = int(websites_cfg.get("count", 1))
        
        try:
            logger.info(f"从文件加载 URL: {websites_file}, 每个访问 {visit_count} 次")
            normalized_urls = get_tasks_mode_1(websites_file, visit_count)
        except FileNotFoundError:
            logger.error(f"网站列表文件不存在: {websites_file}")
            return
            
    if not normalized_urls:
        logger.info("没有需要访问的 URL")
        return

    # 2. 初始化配置参数
    visit_cfg = config.get("visit", {})
    max_retries = max(1, int(visit_cfg.get("max_retries", 2)))
    
    # 3. 初始化任务队列
    # 队列元素: {"url": url, "attempts": 0}
    task_queue = deque({"url": url, "attempts": 0} for url in normalized_urls)
    logger.info(f"总任务数: {len(task_queue)}")

    # 4. 初始化浏览器
    driver = None
    try:
        
        
        while task_queue:
            driver = get_firefox_driver()
            task = task_queue.popleft()
            url = task["url"]
            attempts = task["attempts"]
            
            logger.info(f"开始处理任务 ({attempts + 1}/{max_retries + 1}): {url}, 剩余任务数: {len(task_queue)}")
            
            # 调用单次处理逻辑
            result = process_single_url(driver, url, config)
            status = result["status"]
            
            if status == "success":
                logger.info(f"任务完成: {url}")
            else:
                logger.warning(f"任务失败 ({status}): {url}")
                # 重试逻辑
                if attempts < max_retries:
                    logger.info(f"重新加入队列进行重试: {url}")
                    task["attempts"] += 1
                    task_queue.append(task)
                else:
                    logger.error(f"达到最大重试次数，放弃任务: {url}")
            driver.quit()
    except Exception as e:
        logger.critical(f"任务执行过程中发生严重错误: {e}", exc_info=True)
    finally:
        if driver:
            logger.info("关闭浏览器")
            driver.quit()

if __name__ == "__main__":
    run_tasks()

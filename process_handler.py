import logging
from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor

from selenium.webdriver.remote.webdriver import WebDriver

from visit import visit_page
from pcap_service import start_capture_task, stop_capture_task, delete_capture_files
from service_client import classify_screenshot, is_blank_prediction
from utils import prepare_capture_context

logger = logging.getLogger(__name__)

# 创建全局线程池，用于异步处理分类任务
# max_workers 可以根据需要调整，避免过多并发请求压垮分类服务
classification_executor = ThreadPoolExecutor(max_workers=4)

def _async_classify_task(service_cfg: dict, pcap_cfg: dict, screenshot_path: str, url: str, capture_domain: str, capture_index: str) -> Dict[str, Any]:
    """
    异步执行的分类任务：分类 -> 判断空白页 -> (可选)清理抓包文件
    
    Returns:
        Dict: 包含 prediction 和 is_blank 的结果字典
    """
    result = {"prediction": None, "is_blank": False, "error": None}
    try:
        prediction = classify_screenshot(service_cfg, screenshot_path)
        result["prediction"] = prediction
        
        if is_blank_prediction(prediction, service_cfg):
            logger.warning(f"检测到空白页 ({url}), 预测结果: {prediction}")
            result["is_blank"] = True
            
            pcap_enabled = bool(pcap_cfg.get("service"))
            cleanup_on_failure = bool(pcap_cfg.get("delete_on_failure", True))
            
            if pcap_enabled and cleanup_on_failure:
                logger.info(f"空白页清理抓包文件: {url}")
                delete_capture_files(pcap_cfg, capture_domain, capture_index)
        else:
            logger.info(f"后台分类完成: {url}, 结果: {prediction}")
            
    except Exception as e:
        logger.error(f"后台分类任务发生错误 ({url}): {e}")
        result["error"] = str(e)
        
    return result

def process_single_url(driver: WebDriver, url: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理单个 URL 的完整流程：抓包 -> 访问 -> 截图 -> 停止抓包 -> (异步)分类。
    
    Args:
        driver: WebDriver 实例
        url: 目标 URL
        config: 全局配置
        
    Returns:
        Dict: 处理结果，包含 status, screenshot_path, future 等信息。
    """
    service_cfg = config.get("service", {}) or {}
    pcap_cfg = config.get("pcapng", {}) or {}
    pcap_enabled = bool(pcap_cfg.get("service"))
    cleanup_on_failure = bool(pcap_cfg.get("delete_on_failure", True))
    
    # 1. 准备上下文（路径、ID等）
    try:
        capture_ctx = prepare_capture_context(url, config)
    except Exception as e:
        logger.error(f"准备上下文失败 ({url}): {e}")
        return {"status": "error", "error": str(e)}

    capture_domain = capture_ctx["domain"]
    capture_index = capture_ctx["index_str"]
    screenshot_path = str(capture_ctx["screenshot_path"])
    
    result = {
        "url": url,
        "domain": capture_domain,
        "index": capture_index,
        "screenshot_path": screenshot_path,
        "status": "unknown",
        "prediction": "pending", # 标记为处理中
        "is_blank": False,
        "future": None
    }

    # 2. 启动抓包
    if pcap_enabled:
        if not start_capture_task(pcap_cfg, capture_domain, capture_index):
            logger.error(f"启动抓包失败: {url}")
            result["status"] = "capture_start_failed"
            return result

    # 3. 执行访问
    visit_success = visit_page(driver, url, screenshot_path, config)
    
    # 4. 停止抓包
    if pcap_enabled:
        if not stop_capture_task(pcap_cfg, capture_domain, capture_index):
            logger.error(f"停止抓包失败: {url}")
            # 即使停止失败，如果访问成功了，也可能算部分成功
            pass

    if not visit_success:
        result["status"] = "visit_failed"
        if pcap_enabled and cleanup_on_failure:
            logger.info(f"访问失败，清理抓包文件: {url}")
            delete_capture_files(pcap_cfg, capture_domain, capture_index)
        return result

    # 5. 提交异步分类任务
    # 只要访问成功，就认为本轮任务成功，分类结果在后台处理
    result["status"] = "success"
    
    future = classification_executor.submit(
        _async_classify_task,
        service_cfg,
        pcap_cfg,
        screenshot_path,
        url,
        capture_domain,
        capture_index
    )
    result["future"] = future
    
    logger.info(f"访问成功，已提交后台分类: {url}")

    return result

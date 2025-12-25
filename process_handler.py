import logging
import time
from typing import Dict, Any, Optional

from selenium.webdriver.remote.webdriver import WebDriver

from visit import visit_page
from pcap_service import start_capture_task, stop_capture_task, delete_capture_files
from service_client import classify_screenshot, is_blank_prediction
from utils import prepare_capture_context

logger = logging.getLogger(__name__)

def process_single_url(driver: WebDriver, url: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理单个 URL 的完整流程：抓包 -> 访问 -> 截图 -> 停止抓包 -> 分类。
    
    Args:
        driver: WebDriver 实例
        url: 目标 URL
        config: 全局配置
        
    Returns:
        Dict: 处理结果，包含 status, screenshot_path, prediction 等信息
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
        "prediction": None,
        "is_blank": False
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
            # 即使停止失败，如果访问成功了，也可能算部分成功，但这里为了严谨标记为错误
            # 或者仅记录日志
            pass

    if not visit_success:
        result["status"] = "visit_failed"
        if pcap_enabled and cleanup_on_failure:
            logger.info(f"访问失败，清理抓包文件: {url}")
            delete_capture_files(pcap_cfg, capture_domain, capture_index)
        return result

    # 5. 截图分类
    prediction = classify_screenshot(service_cfg, screenshot_path)
    result["prediction"] = prediction
    
    if is_blank_prediction(prediction, service_cfg):
        logger.warning(f"检测到空白页 ({url}), 预测结果: {prediction}")
        result["is_blank"] = True
        result["status"] = "blank_page"
        # 如果是空白页，是否需要清理抓包？根据需求，这里假设保留以便分析，或者也可以清理
        if pcap_enabled and cleanup_on_failure:
            delete_capture_files(pcap_cfg, capture_domain, capture_index)
    else:
        result["status"] = "success"
        logger.info(f"处理成功: {url}, 分类结果: {prediction}")
    result["status"] = "success"
    return result

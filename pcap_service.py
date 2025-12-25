import logging
from typing import Any, Dict
from urllib.parse import urljoin

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

logger = logging.getLogger(__name__)


def _post_json(base_url: str, endpoint: str, payload: Dict[str, Any], request_timeout: float) -> bool:
    if requests is None:
        logger.warning("requests 库未安装，无法调用抓包服务接口")
        return False

    url = urljoin(_normalize_base_url(base_url), endpoint)

    try:
        response = requests.post(url, json=payload, timeout=request_timeout)
        response.raise_for_status()
        logger.debug("抓包服务响应: %s -> %s", endpoint, response.text)
        return True
    except requests.RequestException as exc:  # type: ignore[attr-defined]
        logger.warning("调用抓包服务失败 %s: %s", endpoint, exc)
        return False


def _normalize_base_url(value: str) -> str:
    if not value.endswith('/'):
        return value + '/'
    return value


def start_capture_task(pcap_config: dict, domain: str, idx: str) -> bool:
    """启动抓包任务"""
    base_url = pcap_config.get("service")
    if not base_url:
        logger.debug("未配置抓包服务地址，跳过 start_task 调用")
        return False

    interface = pcap_config.get("interface")
    ports = pcap_config.get("port", {})
    tls_port = ports.get("tls")
    proxy_port = ports.get("proxy")

    if not interface or tls_port is None or proxy_port is None:
        logger.warning("抓包服务配置不完整，缺少 interface/tls/proxy 配置")
        return False

    capture_timeout = int(pcap_config.get("timeout", 60))
    request_timeout = float(pcap_config.get("request_timeout", 10))

    payload = {
        "domain": domain,
        "idx": idx,
        "tls_port": tls_port,
        "proxy_port": proxy_port,
        "interface": interface,
        "timeout": capture_timeout,
    }

    logger.info("启动抓包任务: %s #%s", domain, idx)
    return _post_json(base_url, "api/start_task", payload, request_timeout)


def stop_capture_task(pcap_config: dict, domain: str, idx: str) -> bool:
    """停止抓包任务"""
    base_url = pcap_config.get("service")
    if not base_url:
        return False

    request_timeout = float(pcap_config.get("request_timeout", 10))
    payload = {
        "domain": domain,
        "idx": idx,
    }
    logger.info("停止抓包任务: %s #%s", domain, idx)
    return _post_json(base_url, "api/stop_task", payload, request_timeout)


def delete_capture_files(pcap_config: dict, domain: str, idx: str) -> bool:
    """删除抓包任务生成的文件"""
    base_url = pcap_config.get("service")
    if not base_url:
        return False

    request_timeout = float(pcap_config.get("request_timeout", 10))
    payload = {
        "domain": domain,
        "idx": idx,
    }
    logger.info("删除抓包文件: %s #%s", domain, idx)
    return _post_json(base_url, "api/delete_files", payload, request_timeout)

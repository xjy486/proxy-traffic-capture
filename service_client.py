import logging
from typing import Any, Optional

try:
    import requests  # type: ignore
except ImportError:  # pragma: no cover
    requests = None  # type: ignore

logger = logging.getLogger(__name__)


def classify_screenshot(service_config: dict, screenshot_path: str) -> Optional[int]:
    """调用识别服务对截图进行分类"""
    service_url = service_config.get("resnet18_url")
    if not service_url:
        return None

    if requests is None:
        logger.warning("requests 库未安装，无法调用识别服务")
        return None

    timeout = service_config.get("timeout", 5)
    payload = {"image_path": screenshot_path}

    try:
        response = requests.post(service_url, json=payload, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as exc:  # type: ignore[attr-defined]
        logger.warning("调用识别服务失败: %s", exc)
        return None

    try:
        data = response.json()
    except ValueError as exc:
        logger.warning("识别服务返回非 JSON 数据: %s", exc)
        return None

    return _extract_prediction(data)


def is_blank_prediction(prediction: Optional[int], service_config: dict) -> bool:
    """根据配置判断预测结果是否为空白页"""
    if prediction is None:
        return False
    blank_label = service_config.get("blank_label", 0)
    return prediction == blank_label


def _extract_prediction(data: Any) -> Optional[int]:
    """从响应数据中提取分类结果"""
    if isinstance(data, (int, float)):
        return int(data)

    if isinstance(data, dict):
        for key in ("prediction", "result", "label", "value"):
            value = data.get(key)
            if isinstance(value, (int, float)):
                return int(value)

    if isinstance(data, list) and data:
        first_item = data[0]
        if isinstance(first_item, (int, float)):
            return int(first_item)

    logger.warning("识别服务返回未知格式: %s", data)
    return None

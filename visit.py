import time
import logging
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, WebDriverException

# 配置日志
logger = logging.getLogger(__name__)

def _wait_for_ready_state(driver: WebDriver, timeout: int) -> None:
    """
    等待页面进入 complete 状态。
    
    Args:
        driver: WebDriver 实例
        timeout: 超时时间（秒）
    """
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except TimeoutException:
        logger.warning("等待页面 readyState complete 超时")

def _simulate_user_scroll(driver: WebDriver, steps: int, distance: int, pause: float) -> None:
    """
    通过滚动模拟用户行为，改善页面渲染效果。
    
    Args:
        driver: WebDriver 实例
        steps: 滚动次数
        distance: 每次滚动距离（像素）
        pause: 每次滚动后的暂停时间（秒）
    """
    for _ in range(max(1, steps)):
        driver.execute_script("window.scrollBy(0, arguments[0]);", distance)
        time.sleep(max(0.1, pause))
    # 滚回顶部
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(0.5) # 等待滚回顶部完成

def visit_page(driver: WebDriver, url: str, screenshot_path: str, config: dict) -> bool:
    """
    访问单个 URL，执行滚动操作并截图。
    
    Args:
        driver: WebDriver 实例
        url: 目标 URL
        screenshot_path: 截图保存路径
        config: 配置字典
        
    Returns:
        bool: 访问并截图成功返回 True，否则返回 False
    """
    browser_cfg = config.get("browser", {})
    visit_cfg = config.get("visit", {})
    
    timeout = int(browser_cfg.get("timeout", 15))
    scroll_steps = int(visit_cfg.get("scroll_steps", 4))
    scroll_pixels = int(visit_cfg.get("scroll_pixels", 400))
    scroll_pause = float(visit_cfg.get("scroll_pause", 0.8))
    settle_pause = float(visit_cfg.get("post_wait", 1.0))

    try:
        logger.info(f"正在访问: {url}")
        driver.set_page_load_timeout(timeout)
        driver.get(url)
        
        # _wait_for_ready_state(driver, timeout)
        
        # 模拟滚动以触发懒加载
        _simulate_user_scroll(driver, scroll_steps, scroll_pixels, scroll_pause)
        
        # 等待页面稳定
        time.sleep(settle_pause)
        
        # 截图
        logger.info(f"保存截图到: {screenshot_path}")
        driver.save_screenshot(screenshot_path)
        return True
        
    except TimeoutException:
        # 访问超时
        logger.warning(f"访问超时: {url}, 截图保存到: {screenshot_path}")
        driver.save_screenshot(screenshot_path)
        return True
    except WebDriverException as e:
        logger.error(f"浏览器错误 ({url}): {e}")
        return False
    except Exception as e:
        logger.error(f"访问发生未知错误 ({url}): {e}")
        return False
    finally:
        driver.quit()

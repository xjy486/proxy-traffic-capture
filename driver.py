import yaml
import os
import logging
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from webdriver_manager.firefox import GeckoDriverManager

from config_manager import load_config
# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_firefox_driver():
    """
    根据 config.yaml 返回配置好的 Firefox WebDriver
    """
    config = load_config()
    
    browser_cfg = config.get('browser', {})
    proxy_cfg = config.get('proxy', {})
    driver_cfg = config.get('driver', {})

    options = FirefoxOptions()
    # 读取Firefox Profile
    profile_path = browser_cfg.get('profile')  
    if profile_path and os.path.exists(profile_path):
        options.add_argument("-profile")
        options.add_argument(profile_path)
        logger.info(f"使用 Firefox Profile: {profile_path}")  
    # 无头模式
    if browser_cfg.get('headless', False):
        options.add_argument('--headless')

    # UA 与语言
    user_agent = browser_cfg.get('user_agent')
    if user_agent:
        options.set_preference("general.useragent.override", user_agent)
    
    accept_language = browser_cfg.get('accept_language')
    if accept_language:
        options.set_preference("intl.accept_languages", accept_language)

    # 页面加载策略
    options.set_capability("pageLoadStrategy", browser_cfg.get('page_load_strategy', 'normal'))
    options.set_capability("acceptInsecureCerts", True)

    # --- 关键：阻止离站拦截与后台请求 (优化流量捕获) ---
    options.set_preference("dom.disable_beforeunload", True)
    options.set_preference("dom.serviceWorkers.enabled", False)

    # 禁用缓存
    options.set_preference("browser.cache.disk.enable", False)
    options.set_preference("browser.cache.memory.enable", False)
    options.set_preference("browser.cache.offline.enable", False)
    options.set_preference("network.http.use-cache", False)

    # 启动页/主页
    options.set_preference("browser.startup.page", 1)
    options.set_preference("browser.startup.homepage", "about:blank")
    options.set_preference("startup.homepage_welcome_url", "about:blank")

    # 禁用遥测与数据上报
    options.set_preference("toolkit.telemetry.enabled", False)
    options.set_preference("toolkit.telemetry.unified", False)
    options.set_preference("datareporting.healthreport.uploadEnabled", False)
    options.set_preference("datareporting.policy.dataSubmissionEnabled", False)

    # 禁用更新
    options.set_preference("app.update.auto", False)
    options.set_preference("app.update.enabled", False)
    options.set_preference("extensions.update.enabled", False)

    # 禁用 SafeBrowsing (减少背景请求)
    options.set_preference("browser.safebrowsing.enabled", False)
    options.set_preference("browser.safebrowsing.phishing.enabled", False)
    options.set_preference("browser.safebrowsing.malware.enabled", False)

    # 禁用网络预测与预取
    options.set_preference("network.prefetch-next", False)
    options.set_preference("network.dns.disablePrefetch", True)
    options.set_preference("network.predictor.enabled", False)
    options.set_preference("network.captive-portal-service.enabled", False)

    # 代理设置
    # 仅当 proxy.enabled 为 True 时才配置代理，且仅有socks5代理
    if proxy_cfg.get('enabled', True):
        proxy_host = proxy_cfg.get('host')
        proxy_port = proxy_cfg.get('port')
        if proxy_host and proxy_port:
            proxy_address = f"{proxy_host}:{proxy_port}"
            options.set_preference("network.proxy.type", 1)  # 手动配置代理
            options.set_preference("network.proxy.socks", proxy_host)
            options.set_preference("network.proxy.socks_port", int(proxy_port))
            options.set_preference("network.proxy.socks_version", 5)
            options.set_preference("network.proxy.socks_remote_dns", True)
            logger.info(f"已配置 SOCKS5 代理: {proxy_address}")
        else:
            raise ValueError("代理配置错误：请提供有效的 host 和 port")


    # 驱动路径处理
    executable_path = driver_cfg.get('path')
    if not executable_path or not os.path.exists(executable_path):
        # 使用 webdriver-manager 自动下载/管理
        executable_path = GeckoDriverManager().install()

    service = Service(executable_path=executable_path)
    driver = webdriver.Firefox(service=service, options=options)
    
    return driver

if __name__ == "__main__":
    # 测试代码
    try:
        logger.info("正在启动浏览器...")
        driver = get_firefox_driver()
        driver.get("about:blank")
        logger.info(f"浏览器启动成功，当前页面: {driver.current_url}")
        driver.quit()
    except Exception as e:
        logger.error(f"启动失败: {e}")




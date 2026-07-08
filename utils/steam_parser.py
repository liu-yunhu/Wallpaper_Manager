"""
Steam Parser
处理 Steam 创意工坊订阅数据的解析

负责读取 Steam 客户端 userdata 目录下的 VDF 订阅文件，
以及 Workshop 内容目录的壁纸文件夹。
"""

import vdf
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class SteamParser:
    """Steam 创意工坊数据解析器"""

    # Wallpaper Engine 的 Steam App ID
    APP_ID = "431960"

    def __init__(self, config: dict):
        self.config = config
        # VDF 订阅数据缓存（30 秒 TTL，避免频繁读取磁盘）
        self._all_subscription_data: Optional[dict] = None
        self._subscription_cache_time: float = 0
        self._cache_duration: float = 30

        # Steam 用户列表缓存
        self._user_cache: Optional[list] = None
        self._user_cache_time: float = 0

    # ------------------------------------------------------------------
    # 路径解析
    # ------------------------------------------------------------------

    def get_steam_library_path(self) -> str:
        """获取 Steam 创意工坊内容库路径"""
        return self.config.get('steam_library_path', '')

    def get_workshop_file_path(self) -> str:
        """获取 appworkshop ACF 文件路径"""
        if self.config.get('workshop_file'):
            return self.config['workshop_file']
        # steam_library_path 已直接指向 431960 目录，
        # 需上溯两级到 workshop 目录查找 acf 文件
        content_path = self.get_steam_library_path()
        workshop_path = Path(content_path).parent.parent
        return str(workshop_path / f"appworkshop_{self.APP_ID}.acf")

    def get_content_path(self) -> Path:
        """获取壁纸内容目录（即 431960 目录）"""
        if self.config.get('content_path'):
            return Path(self.config['content_path'])
        # steam_library_path 直接指向 431960 目录
        return Path(self.get_steam_library_path())

    def get_steam_user_data_path(self) -> Optional[Path]:
        """
        获取 Steam userdata 目录路径

        优先级：配置项 > Windows 注册表 > 常见安装路径
        """
        try:
            # 1. 优先使用用户配置的路径（config 是 dict，必须用 .get 而非 hasattr）
            configured = self.config.get('steam_userdata_path')
            if configured and configured.strip():
                configured_path = Path(configured.strip())
                if configured_path.exists():
                    logger.debug("使用配置的 Steam userdata 路径: %s", configured_path)
                    return configured_path
                logger.warning("配置的 Steam userdata 路径不存在: %s，回退到自动检测", configured_path)

            # 2. 从 Windows 注册表读取 Steam 安装路径
            if os.name == 'nt':
                try:
                    import winreg
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                        r"SOFTWARE\WOW6432Node\Valve\Steam") as key:
                        steam_path = winreg.QueryValueEx(key, "InstallPath")[0]
                        registry_path = Path(steam_path) / "userdata"
                        if registry_path.exists():
                            logger.debug("使用注册表中的 Steam userdata 路径: %s", registry_path)
                            return registry_path
                except OSError as e:
                    logger.debug("无法从注册表读取 Steam 路径: %s", e)

            # 3. 回退到常见安装路径
            common_paths = [
                Path.home() / ".steam" / "steam" / "userdata",
                Path("C:") / "Program Files (x86)" / "Steam" / "userdata",
                Path("C:") / "Steam" / "userdata"
            ]
            for path in common_paths:
                if path.exists():
                    logger.debug("使用常见路径中的 Steam userdata: %s", path)
                    return path

        except Exception as e:
            logger.error("获取 Steam userdata 路径时出错: %s", e)

        logger.error("未找到有效的 Steam userdata 路径")
        return None

    # ------------------------------------------------------------------
    # 用户与订阅数据
    # ------------------------------------------------------------------

    def get_all_steam_user_ids(self) -> list:
        """获取本机所有 Steam 用户 ID（数字命名的目录）"""
        current_time = time.time()

        if (self._user_cache is not None and
                current_time - self._user_cache_time < self._cache_duration):
            return self._user_cache

        try:
            steam_userdata_path = self.get_steam_user_data_path()
            if not steam_userdata_path:
                return []

            user_dirs = [d for d in steam_userdata_path.iterdir()
                         if d.is_dir() and d.name.isdigit()]
            user_ids = [d.name for d in user_dirs]

            self._user_cache = user_ids
            self._user_cache_time = current_time

            logger.debug("发现 %d 个 Steam 用户: %s", len(user_ids), user_ids)
            return user_ids

        except Exception as e:
            logger.error("获取 Steam 用户 ID 时出错: %s", e)
            return []

    def get_steam_user_id(self) -> Optional[str]:
        """获取最近活跃的 Steam 用户 ID（按目录修改时间）"""
        try:
            steam_userdata_path = self.get_steam_user_data_path()
            if not steam_userdata_path:
                return None

            user_dirs = [d for d in steam_userdata_path.iterdir()
                         if d.is_dir() and d.name.isdigit()]
            if not user_dirs:
                return None

            most_recent = max(user_dirs, key=lambda d: d.stat().st_mtime)
            return most_recent.name

        except Exception as e:
            logger.error("获取 Steam 用户 ID 时出错: %s", e)
            return None

    def get_all_subscription_data(self) -> dict:
        """
        获取所有用户的订阅数据（带缓存）

        返回: {user_id: {workshop_id: {user_id, time_subscribed, disabled_locally, is_active}}}
        """
        current_time = time.time()

        # 命中缓存直接返回
        if (self._all_subscription_data is not None and
                current_time - self._subscription_cache_time < self._cache_duration):
            return self._all_subscription_data

        try:
            steam_userdata_path = self.get_steam_user_data_path()
            if not steam_userdata_path:
                return {}

            all_user_ids = self.get_all_steam_user_ids()
            all_data: dict = {}

            for user_id in all_user_ids:
                subscription_file = (steam_userdata_path / user_id /
                                     "ugc" / f"{self.APP_ID}_subscriptions.vdf")

                if not subscription_file.exists():
                    continue

                try:
                    with open(subscription_file, 'r', encoding='utf-8') as f:
                        data = vdf.load(f)

                    user_subscriptions: dict = {}

                    files_data = data.get('subscribedfiles', {})
                    for value in files_data.values():
                        if isinstance(value, dict) and 'publishedfileid' in value:
                            file_id = value['publishedfileid']
                            disabled = value.get('disabled_locally', '0') == '1'
                            user_subscriptions[file_id] = {
                                'user_id': user_id,
                                'time_subscribed': value.get('time_subscribed', 'Unknown'),
                                'disabled_locally': disabled,
                                'is_active': not disabled
                            }

                    all_data[user_id] = user_subscriptions

                except Exception as e:
                    logger.error("读取用户 %s 的订阅数据失败: %s", user_id, e)
                    continue

            self._all_subscription_data = all_data
            self._subscription_cache_time = current_time
            return all_data

        except Exception as e:
            logger.error("获取全部订阅数据时出错: %s", e)
            return {}

    def get_realtime_subscribed_items(self) -> Optional[set]:
        """
        获取所有用户当前活跃订阅的并集（实时读取，合并多用户）

        返回: set of workshop_id，无数据时返回 None（用于触发上层回退逻辑）
        """
        try:
            all_data = self.get_all_subscription_data()
            if not all_data:
                return None

            all_subscribed_items: set = set()
            users_with_subscriptions = 0

            for user_id, user_subscriptions in all_data.items():
                active = [item_id for item_id, details in user_subscriptions.items()
                          if details['is_active']]
                if active:
                    logger.debug("用户 %s 有 %d 个活跃订阅", user_id, len(active))
                    all_subscribed_items.update(active)
                    users_with_subscriptions += 1

            logger.debug("合计: 来自 %d 个用户的 %d 个去重订阅项",
                         users_with_subscriptions, len(all_subscribed_items))
            return all_subscribed_items

        except Exception as e:
            logger.error("读取实时订阅数据时出错: %s", e)
            return None

    def load_workshop_data(self) -> Optional[set]:
        """加载 Workshop 安装数据，优先用实时订阅，失败则回退到 ACF 文件"""
        realtime_data = self.get_realtime_subscribed_items()
        if realtime_data is not None:
            return realtime_data

        logger.info("回退到 ACF 文件解析...")

        try:
            workshop_file = self.get_workshop_file_path()

            if not Path(workshop_file).exists():
                logger.warning("Workshop 文件不存在: %s", workshop_file)
                return None

            with open(workshop_file, 'r', encoding='utf-8') as f:
                data = vdf.load(f)

            workshop_items = data.get('AppWorkshop', {}).get('WorkshopItemsInstalled', {})
            result = set(workshop_items.keys()) if isinstance(workshop_items, dict) else set()
            return result

        except Exception as e:
            logger.error("加载 Workshop 数据失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 单项查询
    # ------------------------------------------------------------------

    def get_subscription_details_by_user(self, workshop_id: str) -> list:
        """获取某个创意工坊项目的订阅详情（哪些用户订阅、何时订阅）"""
        try:
            all_data = self.get_all_subscription_data()
            if not all_data:
                return []

            details = []
            for user_subscriptions in all_data.values():
                if workshop_id in user_subscriptions:
                    details.append(user_subscriptions[workshop_id])
            return details

        except Exception as e:
            logger.error("获取订阅详情时出错: %s", e)
            return []

    def get_realtime_subscription_status(self, workshop_id: str) -> Optional[bool]:
        """
        获取某个项目的实时订阅状态（任一用户订阅即为 True）

        返回: True/False，数据不可用时返回 None（触发上层回退）
        """
        try:
            subscribed_items = self.get_realtime_subscribed_items()
            if subscribed_items is not None:
                return workshop_id in subscribed_items
            # 实时数据不可用时回退到 ACF
            logger.debug("项目 %s 回退到 ACF 判定", workshop_id)
            return self._check_vdf_subscription(workshop_id)
        except Exception as e:
            logger.error("获取实时订阅状态时出错: %s", e)
            return None

    def _check_vdf_subscription(self, workshop_id: str) -> bool:
        """从 ACF 文件判定订阅状态"""
        workshop_items = self.load_workshop_data()
        return bool(workshop_items and workshop_id in workshop_items)

    def is_valid_workshop_id(self, workshop_id: str) -> bool:
        """检查是否为合法的创意工坊 ID（纯数字）"""
        try:
            int(workshop_id)
            return True
        except (ValueError, TypeError):
            return False

    # ------------------------------------------------------------------
    # 缓存管理
    # ------------------------------------------------------------------

    def invalidate_cache(self) -> None:
        """清除所有缓存（配置变更或壁纸删除后调用）"""
        self._all_subscription_data = None
        self._subscription_cache_time = 0
        self._user_cache = None
        self._user_cache_time = 0
        logger.debug("SteamParser 缓存已清除")

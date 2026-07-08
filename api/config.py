"""
Configuration API
应用配置管理：读写 config.json
"""

import json
import logging
import shutil
import traceback
from pathlib import Path
from typing import Optional

from utils.paths import get_config_path

logger = logging.getLogger(__name__)

# 仅这些键会被持久化与回写（避免污染 Flask 内置配置）
_CUSTOM_CONFIG_KEYS = [
    'steam_library_path',
    'steam_userdata_path',
    'workshop_file',
    'content_path',
    'server',
    'preview'
]


class ConfigAPI:
    """配置管理 API"""

    def __init__(self, config: dict):
        self.config = config
        # 配置文件位于数据目录（打包后为 %APPDATA%\WallpaperManager\config.json）
        self.config_file = get_config_path()

    def get_config(self) -> dict:
        """获取当前配置（仅返回自定义键）"""
        return {
            'steam_library_path': self.config.get('steam_library_path', ''),
            'steam_userdata_path': self.config.get('steam_userdata_path', ''),
            'workshop_file': self.config.get('workshop_file', ''),
            'content_path': self.config.get('content_path', ''),
            'server': self.config.get('server', {}),
            'preview': self.config.get('preview', {})
        }

    def update_config(self, new_config: Optional[dict]) -> bool:
        """更新配置（仅自定义键），先备份再写入"""
        if not new_config:
            logger.warning("收到空的配置数据")
            return False

        if not isinstance(new_config, dict):
            logger.error("配置必须是字典类型")
            return False

        logger.debug("更新配置: %s", new_config)

        # 读取现有配置文件
        file_config: dict = {}
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    file_config = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("读取现有配置失败，将覆盖: %s", e)
                file_config = {}

        # 仅更新提供的自定义键
        for key, value in new_config.items():
            if key in _CUSTOM_CONFIG_KEYS:
                file_config[key] = value
                # 同步更新内存中的配置
                self.config[key] = value

        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        try:
            # 写入前备份
            if self.config_file.exists():
                backup_file = self.config_file.with_suffix('.json.bak')
                shutil.copy2(self.config_file, backup_file)

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(file_config, f, ensure_ascii=False, indent=2)

            logger.info("配置已保存到 %s", self.config_file)
            return True

        except PermissionError:
            logger.error("写入配置文件被拒绝（权限不足）: %s", self.config_file)
            return False
        except OSError as e:
            logger.error("写入配置文件失败: %s", e)
            return False
        except Exception as e:
            logger.error("更新配置时发生未预期错误: %s", e)
            traceback.print_exc()
            return False

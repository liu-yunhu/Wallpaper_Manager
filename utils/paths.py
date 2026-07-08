# -*- coding: utf-8 -*-
"""
应用路径工具
定位应用数据目录：打包后使用 %APPDATA%\\WallpaperManager，确保任何启动方式下均可写入。
"""

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def get_data_dir() -> Path:
    """
    获取应用数据目录
    打包后使用 %APPDATA%\\WallpaperManager，确保任何启动方式下均可写入；
    开发环境使用项目根目录。
    """
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包环境：优先使用用户 APPDATA 目录（不受启动目录影响）
        appdata = os.environ.get('APPDATA')
        if appdata:
            data_dir = Path(appdata) / 'WallpaperManager'
            try:
                data_dir.mkdir(parents=True, exist_ok=True)
                return data_dir
            except OSError:
                logger.warning("无法创建数据目录 %s，退化到 exe 所在目录", data_dir)
        # 退化方案：exe 所在目录
        return Path(sys.executable).parent
    # 开发环境：项目根目录
    return Path('.')


def get_config_path() -> Path:
    """
    获取 config.json 路径
    打包后首次运行时，从 exe 内置模板（sys._MEIPASS/config.json）初始化一份到数据目录，
    避免首次运行丢失默认 Steam 路径等配置。
    """
    config_path = get_data_dir() / 'config.json'
    if not config_path.exists():
        meipass = getattr(sys, '_MEIPASS', None)
        if meipass:
            template = Path(meipass) / 'config.json'
            if template.exists():
                try:
                    config_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(template, config_path)
                    logger.info("已从内置模板初始化配置文件: %s", config_path)
                except OSError as e:
                    logger.warning("初始化配置文件失败: %s", e)
    return config_path

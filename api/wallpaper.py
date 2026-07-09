"""
Wallpaper API
壁纸数据管理与操作

核心设计：
- 分页查询时先取廉价的 ID 列表（仅 iterdir），搜索/分页后再按本页 ID
  并行计算完整信息，避免对全部壁纸做 rglob/project.json 读取。
- 三级缓存（大小 / project.json 解析 / 完整信息），按文件 mtime 失效，删除壁纸时主动清除。
"""

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from utils.image_processor import ImageProcessor
from utils.steam_parser import SteamParser

logger = logging.getLogger(__name__)

# 模块级线程池：壁纸信息计算为 I/O 密集型，多线程可显著加速本页计算
_INFO_THREAD_POOL = ThreadPoolExecutor(max_workers=8)

# contentrating 原始值 -> 中文标签（None/未知值由调用方兜底为“未分级”）
_CONTENT_RATING_LABELS = {
    'Everyone': '大众级',
    'Questionable': '家长指导级',
    'Mature': '成人级(R-18)',
}
# type 归一化值（小写）-> 中文标签
_TYPE_LABELS = {
    'scene': '场景',
    'video': '视频',
    'web': '网页',
}


class WallpaperAPI:
    """壁纸管理 API"""

    # 完整信息缓存 TTL（秒），含预览图路径与订阅详情
    _INFO_CACHE_TTL: float = 60

    def __init__(self, config: dict):
        self.config = config
        self.steam_parser = SteamParser(config)
        self.image_processor = ImageProcessor(config)

        # 大小缓存: {wallpaper_id: (size_bytes, folder_mtime)}，按 mtime 失效
        self._size_cache: dict = {}
        # project.json 解析缓存: {wallpaper_id: (data_dict, project_json_mtime)}，按 mtime 失效
        # 一次读取同时提供 title / content_rating / type，避免多字段各读一次磁盘
        self._project_cache: dict = {}
        # 完整信息缓存: {wallpaper_id: (info_dict, timestamp)}，按 TTL 失效
        self._info_cache: dict = {}
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------
    # 列表（廉价，仅返回 ID，按大小降序）
    # ------------------------------------------------------------------

    def list_wallpaper_ids(self, subscribed: bool) -> list:
        """
        列出已订阅或未订阅的壁纸 ID（按文件夹大小降序）

        仅遍历目录 + 读取（缓存的）大小，不读取 project.json / 预览图，
        供分页流程使用。
        """
        realtime_subscribed = self.steam_parser.get_realtime_subscribed_items()
        subscribed_set = set(realtime_subscribed) if realtime_subscribed else set()

        content_path = self.steam_parser.get_content_path()
        if not content_path.exists():
            return []

        # 收集符合条件的 ID
        matching_ids = []
        for folder in content_path.iterdir():
            if not (folder.is_dir() and self.steam_parser.is_valid_workshop_id(folder.name)):
                continue
            is_subscribed = folder.name in subscribed_set
            if is_subscribed == subscribed:
                matching_ids.append(folder.name)

        return self._sort_ids_by_size_desc(matching_ids, content_path)

    def list_wallpaper_ids_by_user(self, user_id: str, subscribed_only: bool) -> list:
        """按指定用户过滤的壁纸 ID 列表（按大小降序）"""
        all_data = self.steam_parser.get_all_subscription_data()
        if not all_data or user_id not in all_data:
            return []

        user_subs = all_data[user_id]
        content_path = self.steam_parser.get_content_path()
        if not content_path.exists():
            return []

        if subscribed_only:
            matching_ids = [
                wid for wid, details in user_subs.items()
                if details['is_active'] and (content_path / wid).exists()
            ]
        else:
            # 未被该用户活跃订阅的（含禁用项与磁盘残留），与全局未订阅语义一致
            active_ids = {wid for wid, details in user_subs.items() if details['is_active']}
            matching_ids = [
                folder.name for folder in content_path.iterdir()
                if folder.is_dir()
                and self.steam_parser.is_valid_workshop_id(folder.name)
                and folder.name not in active_ids
            ]

        return self._sort_ids_by_size_desc(matching_ids, content_path)

    def filter_ids(self, wallpaper_ids: list, search_query: Optional[str] = None,
                   content_rating: Optional[str] = None,
                   wallpaper_type: Optional[str] = None) -> list:
        """
        按标题搜索 + 年龄分级 + 类型过滤 ID 列表（字段均来自 project.json 解析缓存）

        所有条件为空时原样返回。content_rating / wallpaper_type 取值约定：
        具体值匹配该原始值（type 已归一化为小写）；'none' 匹配字段缺失；None/'' 不筛。
        """
        has_search = bool(search_query and search_query.strip())
        has_rating = bool(content_rating and content_rating.strip())
        has_type = bool(wallpaper_type and wallpaper_type.strip())
        if not (has_search or has_rating or has_type):
            return wallpaper_ids

        term = search_query.strip().lower() if has_search else None
        rating = content_rating.strip() if has_rating else None
        wp_type = wallpaper_type.strip() if has_type else None
        content_path = self.steam_parser.get_content_path()

        def matches(wallpaper_id: str) -> bool:
            data = self._get_project_data(wallpaper_id, content_path / wallpaper_id)
            if term and term not in data['title'].lower():
                return False
            if rating:
                cr = data['content_rating']
                if rating == 'none':
                    if cr is not None:
                        return False
                elif cr != rating:
                    return False
            if wp_type:
                t = data['type']
                if wp_type == 'none':
                    if t is not None:
                        return False
                elif t != wp_type:
                    return False
            return True

        return [wid for wid in wallpaper_ids if matches(wid)]

    def _sort_ids_by_size_desc(self, wallpaper_ids: list, content_path: Path) -> list:
        """按文件夹大小降序排列 ID（大小来自缓存，并行计算冷数据）"""
        if not wallpaper_ids:
            return []

        # 并行获取大小（缓存命中时几乎无开销，冷数据时多线程加速）
        sizes = list(_INFO_THREAD_POOL.map(
            lambda wid: self._get_folder_size_cached(wid, content_path / wid),
            wallpaper_ids
        ))
        paired = sorted(zip(wallpaper_ids, sizes), key=lambda x: x[1], reverse=True)
        return [wid for wid, _ in paired]

    # ------------------------------------------------------------------
    # 批量信息（仅为本页计算，并行 + 缓存）
    # ------------------------------------------------------------------

    def get_wallpaper_info_batch(self, wallpaper_ids: list, subscribed: bool) -> list:
        """并行计算一批壁纸的完整信息（用于分页后的本页数据）"""
        content_path = self.steam_parser.get_content_path()

        def compute(wallpaper_id: str) -> Optional[dict]:
            folder_path = content_path / wallpaper_id
            if not folder_path.exists():
                return None
            info = self._get_wallpaper_info(wallpaper_id, folder_path)
            info['subscribed'] = subscribed
            return info

        results = list(_INFO_THREAD_POOL.map(compute, wallpaper_ids))
        return [r for r in results if r is not None]

    # ------------------------------------------------------------------
    # 单项查询
    # ------------------------------------------------------------------

    def get_wallpaper_details(self, wallpaper_id: str) -> Optional[dict]:
        """获取单个壁纸的详情（含订阅状态与置信度）"""
        try:
            content_path = self.steam_parser.get_content_path()
            folder_path = content_path / wallpaper_id

            if not folder_path.exists():
                return None

            # 增强订阅检测，实时数据不可用时回退到 VDF
            subscription_status = self.steam_parser.get_realtime_subscription_status(wallpaper_id)
            if subscription_status is None:
                workshop_items = self.steam_parser.load_workshop_data()
                is_subscribed = bool(workshop_items and wallpaper_id in workshop_items)
                confidence = 'medium'
            else:
                is_subscribed = subscription_status
                confidence = 'high'

            wallpaper_info = self._get_wallpaper_info(wallpaper_id, folder_path)
            wallpaper_info['subscribed'] = is_subscribed
            wallpaper_info['confidence'] = confidence
            return wallpaper_info

        except Exception as e:
            logger.error("获取壁纸详情失败: %s", e)
            return None

    def get_preview_image(self, wallpaper_id: str) -> Optional[str]:
        """获取壁纸预览图路径"""
        try:
            content_path = self.steam_parser.get_content_path()
            folder_path = content_path / wallpaper_id

            if not folder_path.exists():
                return None

            return self.image_processor.get_preview_path(folder_path)

        except Exception as e:
            logger.error("获取预览图失败: %s", e)
            return None

    # ------------------------------------------------------------------
    # 操作
    # ------------------------------------------------------------------

    def delete_wallpaper(self, wallpaper_id: str) -> bool:
        """删除壁纸文件夹并清除其缓存"""
        try:
            content_path = self.steam_parser.get_content_path()
            folder_path = content_path / wallpaper_id

            if not folder_path.exists():
                return False

            shutil.rmtree(folder_path)
            self._invalidate_wallpaper_cache(wallpaper_id)
            logger.info("已删除壁纸 %s", wallpaper_id)
            return True

        except Exception as e:
            logger.error("删除壁纸失败: %s", e)
            return False

    def open_wallpaper_folder(self, wallpaper_id: str) -> bool:
        """在文件资源管理器中打开壁纸文件夹"""
        try:
            content_path = self.steam_parser.get_content_path()
            folder_path = content_path / wallpaper_id

            if not folder_path.exists():
                logger.warning("壁纸文件夹不存在: %s", folder_path)
                return False

            if os.name == 'nt':
                # Windows explorer 即使成功也常返回非零，故不使用 check=True
                subprocess.Popen(['explorer', str(folder_path)],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
                return True
            elif os.name == 'posix':
                if subprocess.run(['which', 'open'], capture_output=True).returncode == 0:
                    subprocess.run(['open', str(folder_path)], check=True)
                else:
                    subprocess.run(['xdg-open', str(folder_path)], check=True)
                return True

            logger.warning("不支持的操作系统: %s", os.name)
            return False

        except Exception as e:
            logger.error("打开文件夹失败: %s", e)
            return False

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------

    def get_statistics(self, user_id: Optional[str] = None) -> dict:
        """获取存储与订阅统计（可按用户过滤），复用大小缓存避免重复扫描"""
        try:
            if user_id and user_id != 'all':
                sub_ids = self.list_wallpaper_ids_by_user(user_id, subscribed_only=True)
                unsub_ids = self.list_wallpaper_ids_by_user(user_id, subscribed_only=False)
            else:
                sub_ids = self.list_wallpaper_ids(subscribed=True)
                unsub_ids = self.list_wallpaper_ids(subscribed=False)

            content_path = self.steam_parser.get_content_path()

            def total_size(ids: list) -> int:
                return sum(self._get_folder_size_cached(wid, content_path / wid)
                           for wid in ids)

            subscribed_size = total_size(sub_ids)
            unsubscribed_size = total_size(unsub_ids)
            total_size_bytes = subscribed_size + unsubscribed_size

            return {
                'total': {
                    'count': len(sub_ids) + len(unsub_ids),
                    'size': total_size_bytes,
                    'size_formatted': self._format_size(total_size_bytes)
                },
                'subscribed': {
                    'count': len(sub_ids),
                    'size': subscribed_size,
                    'size_formatted': self._format_size(subscribed_size)
                },
                'unsubscribed': {
                    'count': len(unsub_ids),
                    'size': unsubscribed_size,
                    'size_formatted': self._format_size(unsubscribed_size)
                }
            }

        except Exception as e:
            logger.error("获取统计信息失败: %s", e)
            return {
                'total': {'count': 0, 'size': 0, 'size_formatted': '0 B'},
                'subscribed': {'count': 0, 'size': 0, 'size_formatted': '0 B'},
                'unsubscribed': {'count': 0, 'size': 0, 'size_formatted': '0 B'}
            }

    # ------------------------------------------------------------------
    # 内部：信息 / 大小 / 标题（均带缓存）
    # ------------------------------------------------------------------

    def _get_wallpaper_info(self, wallpaper_id: str, folder_path: Path) -> dict:
        """获取壁纸完整信息（TTL 缓存）"""
        # 命中 TTL 缓存直接返回（深拷贝避免调用方污染缓存）
        cached = self._info_cache.get(wallpaper_id)
        if cached and (time.time() - cached[1] < self._INFO_CACHE_TTL):
            return dict(cached[0])

        project = self._get_project_data(wallpaper_id, folder_path)
        title = project['title']
        content_rating = project['content_rating']
        wp_type = project['type']
        size = self._get_folder_size_cached(wallpaper_id, folder_path)
        preview_path, preview_type = self.image_processor.find_preview_file(folder_path)
        subscription_details = self.steam_parser.get_subscription_details_by_user(wallpaper_id)

        wallpaper_info = {
            'id': wallpaper_id,
            'title': title,
            'content_rating': content_rating,
            'content_rating_label': _CONTENT_RATING_LABELS.get(content_rating, '未分级'),
            'type': wp_type,
            'type_label': _TYPE_LABELS.get(wp_type, '未知'),
            'size': size,
            'size_formatted': self._format_size(size),
            'path': str(folder_path),
            'preview_available': preview_path is not None,
            'preview_type': preview_type,
            'subscription_details': subscription_details or []
        }

        # 用户友好的订阅汇总
        if subscription_details:
            active_users = [d for d in subscription_details if d['is_active']]
            wallpaper_info['subscribed_by_users'] = len(active_users)
            wallpaper_info['total_users'] = len(subscription_details)
        else:
            wallpaper_info['subscribed_by_users'] = 0
            wallpaper_info['total_users'] = 0

        with self._cache_lock:
            self._info_cache[wallpaper_id] = (wallpaper_info, time.time())
        return dict(wallpaper_info)

    def _get_wallpaper_title(self, wallpaper_id: str, folder_path: Path) -> str:
        """从 project.json 读取标题（委托给 _get_project_data，共享解析缓存）"""
        return self._get_project_data(wallpaper_id, folder_path)['title']

    def _get_project_data(self, wallpaper_id: str, folder_path: Path) -> dict:
        """
        解析 project.json，返回 {title, content_rating, type}（按文件 mtime 缓存）

        一次读取同时提供标题、年龄分级、类型三字段，避免多字段各自读盘。
        content_rating 保留原始字符串；type 归一化为小写；缺失字段为 None。
        """
        project_file = folder_path / "project.json"
        fallback_title = f'ID: {folder_path.name}'
        if not project_file.exists():
            return {'title': fallback_title, 'content_rating': None, 'type': None}

        try:
            mtime = project_file.stat().st_mtime
        except OSError:
            mtime = 0

        cached = self._project_cache.get(wallpaper_id)
        if cached and cached[1] == mtime:
            return cached[0]

        result = {'title': fallback_title, 'content_rating': None, 'type': None}
        try:
            with open(project_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            result['title'] = data.get('title', fallback_title)
            cr = data.get('contentrating')
            if isinstance(cr, str):
                result['content_rating'] = cr
            t = data.get('type')
            if isinstance(t, str):
                result['type'] = t.lower()
        except (OSError, json.JSONDecodeError, ValueError) as e:
            logger.debug("读取 project.json 失败 (%s): %s", folder_path, e)

        with self._cache_lock:
            self._project_cache[wallpaper_id] = (result, mtime)
        return result

    def _get_folder_size_cached(self, wallpaper_id: str, folder_path: Path) -> int:
        """获取文件夹大小（按文件夹 mtime 缓存，os.scandir 递归求和）"""
        try:
            folder_mtime = folder_path.stat().st_mtime
        except OSError:
            return 0

        cached = self._size_cache.get(wallpaper_id)
        if cached and cached[1] == folder_mtime:
            return cached[0]

        size = self._compute_folder_size(folder_path)
        with self._cache_lock:
            self._size_cache[wallpaper_id] = (size, folder_mtime)
        return size

    @staticmethod
    def _compute_folder_size(folder_path: Path) -> int:
        """递归计算文件夹总大小（os.scandir 比 rglob 更快）"""
        total = 0
        stack = [folder_path]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            if entry.is_dir(follow_symlinks=False):
                                stack.append(entry.path)
                            elif entry.is_file(follow_symlinks=False):
                                total += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            continue
            except OSError:
                continue
        return total

    def _invalidate_wallpaper_cache(self, wallpaper_id: str) -> None:
        """清除单个壁纸的所有缓存"""
        with self._cache_lock:
            self._size_cache.pop(wallpaper_id, None)
            self._project_cache.pop(wallpaper_id, None)
            self._info_cache.pop(wallpaper_id, None)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """将字节数格式化为易读字符串"""
        size = float(size_bytes)
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} PB"

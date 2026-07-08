# -*- coding: utf-8 -*-
"""
Wallpaper Engine Web Manager
管理 Wallpaper Engine 订阅的 Flask Web 应用
"""

import json
import logging
from pathlib import Path
from typing import Optional

from flask import Flask, render_template, jsonify, request, send_file

from api.config import ConfigAPI
from api.wallpaper import WallpaperAPI
from utils.paths import get_config_path, get_data_dir

logger = logging.getLogger(__name__)


# 搜索历史记录文件路径（打包后位于 %APPDATA%\WallpaperManager\）
SEARCH_HISTORY_FILE = get_data_dir() / 'search_history.json'
MAX_HISTORY_SIZE = 20


def _load_search_history() -> list:
    """从文件加载搜索历史记录"""
    try:
        if SEARCH_HISTORY_FILE.exists():
            with open(SEARCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
    except (OSError, json.JSONDecodeError) as e:
        logger.warning("读取搜索历史失败: %s", e)
    return []


def _save_search_history(history: list) -> None:
    """保存搜索历史记录到文件"""
    try:
        with open(SEARCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.error("保存搜索历史失败: %s", e)


# 允许的每页条数预设值
_ALLOWED_PAGE_SIZES = {10, 20, 50}
_DEFAULT_PAGE_SIZE = 20


def _paginate(items: list, page: int, page_size: int) -> list:
    """对列表进行分页切片，自动处理页码越界；page_size=0 表示返回全部"""
    if page_size == 0:
        return items, 1, 1
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    # 边界裁剪：页码超出范围时自动修正
    page = max(1, min(page, total_pages))
    start = (page - 1) * page_size
    end = start + page_size
    return items[start:end], page, total_pages


def _wallpaper_section(wallpaper_api: WallpaperAPI, ids: list, page: int,
                       page_size: int, subscribed: bool) -> dict:
    """
    构建单个分区（已订阅/未订阅）的响应数据

    流程：分页切片 ID -> 仅为本页并行计算完整信息
    """
    page_ids, clamped_page, total_pages = _paginate(ids, page, page_size)
    wallpapers = wallpaper_api.get_wallpaper_info_batch(page_ids, subscribed=subscribed)
    return {
        'total': len(ids),
        'page': clamped_page,
        'page_size': page_size,
        'total_pages': total_pages,
        'wallpapers': wallpapers
    }


def create_app(config: Optional[dict] = None):
    """
    Flask 应用工厂

    :param config: 可选的配置字典，未提供时从 config.json 加载（便于测试注入）
    """
    app = Flask(__name__)

    # 加载配置：优先使用传入的，否则从 config.json 读取
    if config is not None:
        app.config.update(config)
    else:
        config_path = get_config_path()
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    app.config.update(json.load(f))
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("读取 config.json 失败，使用默认配置: %s", e)
                app.config.update(_default_config())
        else:
            app.config.update(_default_config())

    # 初始化 API
    wallpaper_api = WallpaperAPI(app.config)
    config_api = ConfigAPI(app.config)

    @app.route('/')
    def index():
        """主页"""
        return render_template('index.html')

    @app.route('/config-test')
    def config_test():
        """配置测试页"""
        return render_template('config_test.html')

    @app.route('/api/wallpapers')
    def get_wallpapers():
        """分页获取壁纸列表（已订阅/未订阅分区）"""
        try:
            user_filter = request.args.get('user', None)
            search_query = request.args.get('search', None)
            # 支持独立的页码参数，兼容旧的 page 参数
            subscribed_page = int(request.args.get('subscribed_page',
                                                   request.args.get('page', 1)))
            unsubscribed_page = int(request.args.get('unsubscribed_page',
                                                     request.args.get('page', 1)))
            page_size = int(request.args.get('page_size', _DEFAULT_PAGE_SIZE))
            # 仅允许预设的每页条数，page_size=0 表示返回全部（导出用）
            if page_size not in _ALLOWED_PAGE_SIZES and page_size != 0:
                page_size = _DEFAULT_PAGE_SIZE

            # 1. 取廉价的 ID 列表（按大小降序）
            if user_filter and user_filter != 'all':
                sub_ids = wallpaper_api.list_wallpaper_ids_by_user(user_filter, subscribed_only=True)
                unsub_ids = wallpaper_api.list_wallpaper_ids_by_user(user_filter, subscribed_only=False)
            else:
                sub_ids = wallpaper_api.list_wallpaper_ids(subscribed=True)
                unsub_ids = wallpaper_api.list_wallpaper_ids(subscribed=False)

            # 2. 按标题搜索过滤（标题来自缓存）
            sub_ids = wallpaper_api.filter_ids_by_search(sub_ids, search_query)
            unsub_ids = wallpaper_api.filter_ids_by_search(unsub_ids, search_query)

            # 3. 分页后仅为本页计算完整信息
            return jsonify({
                'success': True,
                'data': {
                    'subscribed': _wallpaper_section(
                        wallpaper_api, sub_ids, subscribed_page, page_size, subscribed=True),
                    'unsubscribed': _wallpaper_section(
                        wallpaper_api, unsub_ids, unsubscribed_page, page_size, subscribed=False)
                }
            })
        except Exception as e:
            logger.error("获取壁纸列表失败: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/wallpapers/<wallpaper_id>')
    def get_wallpaper(wallpaper_id):
        """获取单个壁纸详情"""
        try:
            wallpaper = wallpaper_api.get_wallpaper_details(wallpaper_id)
            if wallpaper:
                return jsonify({'success': True, 'data': wallpaper})
            return jsonify({'success': False, 'error': 'Wallpaper not found'}), 404
        except Exception as e:
            logger.error("获取壁纸详情失败: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/wallpapers/<wallpaper_id>/preview')
    def get_wallpaper_preview(wallpaper_id):
        """获取壁纸预览图"""
        try:
            preview_path = wallpaper_api.get_preview_image(wallpaper_id)
            if preview_path and Path(preview_path).exists():
                return send_file(preview_path)
            # 返回占位图
            placeholder_path = Path('static/images/no-preview.png')
            if placeholder_path.exists():
                return send_file(placeholder_path)
            return jsonify({'success': False, 'error': 'Preview not available'}), 404
        except Exception as e:
            logger.error("获取预览图失败: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/wallpapers/<wallpaper_id>', methods=['DELETE'])
    def delete_wallpaper(wallpaper_id):
        """删除壁纸"""
        try:
            success = wallpaper_api.delete_wallpaper(wallpaper_id)
            return jsonify({
                'success': success,
                'message': 'Wallpaper deleted successfully' if success else 'Failed to delete wallpaper'
            })
        except Exception as e:
            logger.error("删除壁纸失败: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/wallpapers/<wallpaper_id>/open-folder', methods=['POST'])
    def open_wallpaper_folder(wallpaper_id):
        """在文件资源管理器中打开壁纸文件夹"""
        try:
            success = wallpaper_api.open_wallpaper_folder(wallpaper_id)
            return jsonify({
                'success': success,
                'message': 'Folder opened successfully' if success else 'Failed to open folder'
            })
        except Exception as e:
            logger.error("打开文件夹失败: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/config')
    def get_config():
        """获取当前配置"""
        try:
            return jsonify({'success': True, 'data': config_api.get_config()})
        except Exception as e:
            logger.error("获取配置失败: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/config', methods=['POST'])
    def update_config():
        """更新配置"""
        try:
            new_config = request.get_json()
            if not new_config:
                return jsonify({'success': False, 'error': '请求数据为空'}), 400

            success = config_api.update_config(new_config)
            if success:
                # 配置变更后清除 SteamParser 缓存，使新路径立即生效
                wallpaper_api.steam_parser.invalidate_cache()
                return jsonify({'success': True, 'message': '配置保存成功'})
            return jsonify({'success': False, 'error': '配置保存失败'}), 500
        except Exception as e:
            logger.error("更新配置失败: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/stats')
    def get_stats():
        """获取存储与订阅统计"""
        try:
            user_id = request.args.get('user', None)
            stats = wallpaper_api.get_statistics(user_id)
            return jsonify({'success': True, 'data': stats})
        except Exception as e:
            logger.error("获取统计失败: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/search-history', methods=['GET', 'POST', 'DELETE'])
    def search_history():
        """搜索历史记录管理"""
        try:
            if request.method == 'GET':
                history = _load_search_history()
                return jsonify({'success': True, 'data': history})

            elif request.method == 'POST':
                data = request.get_json(silent=True) or {}
                keyword = (data.get('keyword', '') or '').strip()
                if not keyword:
                    return jsonify({'success': False, 'error': '搜索关键词不能为空'}), 400

                history = _load_search_history()
                # 去重：移除已存在的相同关键词
                history = [h for h in history if h != keyword]
                # 插入到列表最前面
                history.insert(0, keyword)
                # 限制最大条数
                history = history[:MAX_HISTORY_SIZE]
                _save_search_history(history)
                return jsonify({'success': True, 'data': history})

            elif request.method == 'DELETE':
                _save_search_history([])
                return jsonify({'success': True, 'data': []})
        except Exception as e:
            logger.error("搜索历史操作失败: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/users')
    def get_users():
        """获取所有 Steam 用户及其订阅信息"""
        try:
            from utils.steam_parser import SteamParser
            parser = SteamParser(app.config)

            all_data = parser.get_all_subscription_data()
            users = []
            for user_id, user_subscriptions in all_data.items():
                active_subscriptions = [item_id for item_id, details in user_subscriptions.items()
                                        if details['is_active']]
                users.append({
                    'id': user_id,
                    'display_name': f"用户 {user_id}",
                    'subscription_count': len(active_subscriptions)
                })

            return jsonify({'success': True, 'data': users})
        except Exception as e:
            logger.error("获取用户列表失败: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/api/steam-paths')
    def get_steam_paths():
        """获取系统当前使用的 Steam 路径"""
        try:
            from utils.steam_parser import SteamParser

            config_data = config_api.get_config()
            configured_userdata = config_data.get('steam_userdata_path', '') if config_data else ''

            parser = SteamParser(app.config)
            userdata_path = parser.get_steam_user_data_path()
            content_path = parser.get_content_path()

            # 检测是否回退到了非配置路径
            using_fallback = False
            if configured_userdata and configured_userdata.strip():
                actual_path_str = str(userdata_path) if userdata_path else ''
                using_fallback = configured_userdata.strip() != actual_path_str

            return jsonify({
                'success': True,
                'data': {
                    'configured_userdata_path': configured_userdata if configured_userdata else None,
                    'actual_userdata_path': str(userdata_path) if userdata_path else None,
                    'content_path': str(content_path),
                    'using_fallback': using_fallback
                }
            })
        except Exception as e:
            logger.error("获取 Steam 路径失败: %s", e)
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'success': False, 'error': 'Endpoint not found'}), 404

    @app.errorhandler(500)
    def internal_error(error):
        logger.error("内部错误: %s", error)
        return jsonify({'success': False, 'error': 'Internal server error'}), 500

    return app


def _default_config() -> dict:
    """默认配置（路径直接指向 431960 目录）"""
    return {
        'steam_library_path': 'F:\\SteamLibrary\\steamapps\\workshop\\content\\431960',
        'server': {
            'host': '127.0.0.1',
            'port': 5000,
            'debug': True
        }
    }


def main():
    """主函数"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )

    app = create_app()

    server_config = app.config.get('server', {})
    host = server_config.get('host', '127.0.0.1')
    port = server_config.get('port', 5000)
    debug = server_config.get('debug', True)

    logger.info("启动 Wallpaper Engine Web Manager")
    logger.info("服务地址: http://%s:%s", host, port)
    logger.info("调试模式: %s", '开启' if debug else '关闭')

    try:
        app.run(host=host, port=port, debug=debug)
    except KeyboardInterrupt:
        logger.info("用户已停止服务")
    except Exception as e:
        logger.error("服务出错: %s", e)


if __name__ == '__main__':
    main()

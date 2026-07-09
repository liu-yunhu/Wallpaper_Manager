# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概览

Wallpaper Engine Web Manager —— 基于 Flask 的本地壁纸管理工具,通过浏览器浏览/搜索/清理 Steam Wallpaper Engine(App ID `431960`)的创意工坊订阅内容。**所有壁纸信息都来自本地文件解析,不联网、不调用 Steam Web API**。

## 常用命令

```bash
# 安装依赖(仅 Flask / vdf / Pillow)
pip install -r requirements.txt

# 开发运行(debug=True,开启 Flask reloader)→ http://127.0.0.1:5000
python app.py

# 启动器入口(自动开浏览器,debug=False,无 reloader,打包时用此入口)
python launcher.py

# 打包为单文件 exe(输出 dist/WallpaperManager.exe)
build.bat            # 等价于: python -m PyInstaller launcher.spec
```

**测试**:项目曾用 pytest 组织测试(`.pytest_cache/v/cache/nodeids` 记录了 `test_app` / `test_wallpaper_api` / `test_steam_parser` / `test_image_processor` 的用例),但**测试源文件未纳入版本控制**,当前 `tests/` 仅剩 `__pycache__`。新增测试时用 pytest,跑单个用例:`pytest tests/test_wallpaper_api.py::test_get_statistics`。仓库无 lint 配置。

## 架构

### 双入口,共用应用工厂

`create_app()`(在 `app.py`)是唯一的 Flask 应用工厂,接收可选 `config` dict(便于测试注入)。两个入口都走它:
- `app.py` 的 `main()`:开发用,读 `config.json` 的 `server.debug`(默认 `True`),保留 reloader。
- `launcher.py`:打包/启动用,强制 `debug=False`、`use_reloader=False`、`threaded=True`,延迟 2 秒自动开浏览器。`launcher.spec` 以它为入口打包。

### 三层结构,共享同一个 `config` dict

路由层(`app.py`)→ 业务 API 层(`api/`)→ 数据访问层(`utils/`)。`WallpaperAPI`、`ConfigAPI`、`SteamParser`、`ImageProcessor` 在构造时都接收同一个 `app.config` dict 引用;**修改配置后必须调用 `steam_parser.invalidate_cache()`**(见 `POST /api/config`),否则旧路径的缓存(订阅数据 30s TTL)不会失效。

### 数据来源(纯本地解析,无网络)

壁纸内容在 `<Steam>/steamapps/workshop/content/431960/<workshop_id>/` 下,每个壁纸是一个以 workshop ID 命名的文件夹:
- **标题 / 年龄分级 / 类型**:读文件夹内 `project.json` 的 `title` / `contentrating` / `type` 字段(统一经 `_get_project_data` 解析);title 缺失回退 `ID: <文件夹名>`,type 归一化为小写。中文标签映射见模块级 `_CONTENT_RATING_LABELS` / `_TYPE_LABELS`。
- **大小**:递归 `os.scandir` 累加文件大小(`_compute_folder_size`,用栈而非 rglob,更快)。
- **预览图**:`ImageProcessor.find_preview_file` 先按标准名(`preview.jpg/png/gif/...`)找,再回退到 `rglob` 按扩展名优先级挑(<50MB 的候选)。
- **订阅状态**:见下「订阅检测」。

### 关键路径约定与陷阱(改路径相关代码必读)

- 配置项 `steam_library_path` **直接指向 `431960` 内容目录**(即 `.../workshop/content/431960`),不是 workshop 根目录。`get_workshop_file_path()` 据此**上溯两级**到 workshop 目录找 `appworkshop_431960.acf`。改这层路径逻辑时务必同步两处。
- `steam_userdata_path` 可选:留空时按「用户配置 → Windows 注册表 `HKLM\SOFTWARE\WOW6432Node\Valve\Steam\InstallPath` → 常见安装路径」三级回退(`get_steam_user_data_path`)。
- App ID `431960` 硬编码在 `SteamParser.APP_ID`。

### 性能架构(核心设计,见 `api/wallpaper.py` 顶部注释)

分页查询刻意分两阶段,避免对全量壁纸读 `project.json`/找预览图:
1. **列表阶段**(`list_wallpaper_ids`):只 `iterdir` 取 ID,按(缓存的)文件夹大小降序排序,**不碰 project.json / 预览图**。筛选过滤(`filter_ids`,支持标题搜索 + contentrating + type)只读(缓存的)project.json 解析结果。
2. **本页阶段**(`get_wallpaper_info_batch`):仅对当前页的 ID,用**模块级 `ThreadPoolExecutor`(8 workers)**并行算完整信息。

三级缓存,均带失效条件(均在 `WallpaperAPI`,受 `_cache_lock` 保护):
- `_size_cache`:按文件夹 mtime 失效。
- `_project_cache`:一次解析 `project.json` 同时提供 title / content_rating / type,按 `project.json` mtime 失效。
- `_info_cache`:60s TTL。
- 删除壁纸(`delete_wallpaper`)→ `_invalidate_wallpaper_cache` 清该项三层缓存;改配置 → 清 SteamParser 缓存。

### 订阅检测与置信度

订阅数据两级优先级(`SteamParser`):
1. **首选**:读每个用户的 `userdata/<uid>/ugc/431960_subscriptions.vdf`(实时、按用户、区分 `disabled_locally`),多用户取活跃订阅**并集**。
2. **回退**:上面读不到时读 `appworkshop_431960.acf` 的 `WorkshopItemsInstalled`(只反映已安装,不区分用户)。

`get_wallpaper_details` 返回 `confidence`:实时 VDF 命中为 `'high'`,回退 ACF 为 `'medium'`。详情接口里 `subscribed` 字段任一用户活跃订阅即为 `True`。

### 打包后的数据目录模式(`utils/paths.py`)

PyInstaller 打包后(`sys.frozen` 为真),数据目录切到 `%APPDATA%\WallpaperManager`(开发环境则是项目根 `.`),`config.json` 与 `search_history.json` 都写在这里,不污染 exe 目录。**首次运行**时 `get_config_path()` 会从内置模板(`sys._MEIPASS/config.json`,由 `launcher.spec` 的 `datas` 打入)复制一份 `config.json` 到数据目录,避免首跑丢默认 Steam 路径。任何"读写配置/历史"的代码都必须走 `get_data_dir()` / `get_config_path()`,不要硬编码相对路径。

### 配置持久化白名单

`ConfigAPI` 只持久化 `_CUSTOM_CONFIG_KEYS`(`steam_library_path` / `steam_userdata_path` / `workshop_file` / `content_path` / `server` / `preview`)里的键,避免把 Flask 内置配置写回 `config.json`。写入前先备份为 `.json.bak`。

## 约定

- **平台**:以 Windows 为主(注册表检测 Steam 路径、`explorer` 打开文件夹),`utils` 里保留 posix 兼容分支。开发实测跨 Python 3.11/3.13/3.14(`__pycache__` 多版本共存)。
- **错误处理**:API 层方法普遍 `try/except` 后记日志并返回空值/`None`/`False`,路由层再统一包成 `{success, error}` JSON。延续此风格,勿让异常直接冒泡到 Flask。
- **图片处理**:`ImageProcessor` 曾有缩放/GIF 取帧逻辑,因泄漏临时文件已被移除(见 git 历史);重新引入图片处理时务必管理好临时文件清理。
- **前端**:原生 JS(Bootstrap 5 + Font Awesome)通过 Fetch 调用 `app.py` 中的 `/api/*`,无构建步骤、无前端框架。API 端点表见 README。

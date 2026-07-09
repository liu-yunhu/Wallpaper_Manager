# Wallpaper Engine Web Manager

基于 Flask 的本地壁纸管理工具，通过浏览器浏览、搜索、清理 Steam Wallpaper Engine（App ID `431960`）的创意工坊订阅内容。所有壁纸信息来自本地文件解析，不联网、不调用 Steam Web API。

![demo](static/img/demo.png)

---

## 版本说明

| 版本 | 适用场景 | 说明 |
|------|----------|------|
| **Release** | 普通用户 | 打包为独立可执行文件，解压即用，无需安装 Python 环境。下载地址见 [Releases](https://github.com/liu-yunhu/Wallpaper_Manager/releases) |
| **本地开发版**（当前仓库） | 开发者 / 进阶用户 | 需要 Python 3.8+ 环境，通过源码运行，适合二次开发与调试 |

---

## 功能特性

- **订阅管理** — 分页浏览已订阅/未订阅壁纸，按文件夹大小降序排列
- **多用户支持** — 自动识别本机所有 Steam 用户，可切换用户查看各自的订阅数据
- **多维筛选** — 按标题搜索、类型（场景/视频/网页）、年龄分级（大众级/家长指导级/成人级）组合过滤
- **预览图** — 内嵌预览图展示，支持 project.json 内嵌预览及常见图片格式
- **一键操作** — 删除壁纸释放磁盘空间、在资源管理器中打开壁纸文件夹、批量导出列表
- **存储统计** — 实时展示已订阅/未订阅壁纸的数量与占用空间，可视化存储占比
- **Web 配置界面** — 通过网页即可修改 Steam 路径等配置项，无需手动编辑文件
- **路径自动检测** — 优先使用配置路径，支持从 Windows 注册表自动读取 Steam 安装位置，回退到常见安装路径
- **搜索历史** — 自动保存最近 20 条搜索关键词
- **响应式 UI** — Bootstrap 5 + Font Awesome 6，适配桌面与移动端

---

## 技术栈

- **后端**：Flask（应用工厂模式），vdf（VDF 解析），Pillow（图像处理）
- **前端**：Bootstrap 5，Font Awesome 6，原生 JavaScript（Fetch API，无构建步骤）
- **数据源**：Steam userdata 目录下的 VDF 订阅文件 + Workshop 内容目录
- **打包**：PyInstaller（单文件 exe）

---

## 快速开始

### 环境要求

- Python 3.8+
- Steam 客户端（需安装 Wallpaper Engine）

### 1. 克隆项目

```bash
git clone https://github.com/liu-yunhu/Wallpaper_Manager.git
cd Wallpaper_Manager
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置路径

首次启动前，编辑 `config.json`：

```json
{
  "steam_library_path": "F:\\SteamLibrary\\steamapps\\workshop\\content\\431960",
  "steam_userdata_path": "E:\\Software\\Steam\\userdata"
}
```

- `steam_library_path`：Wallpaper Engine 的 Workshop 内容目录（指向 `.../workshop/content/431960`）
- `steam_userdata_path`：Steam 安装目录下的 `userdata` 文件夹（可选，留空则自动检测）

也可在启动后通过网页「配置」按钮在线修改。

### 4. 启动服务

```bash
python app.py
```

浏览器访问 `http://localhost:5000`。

### 5. 打包为 exe

```bash
build.bat
# 等价于: python -m PyInstaller launcher.spec
```

输出在 `dist/WallpaperManager.exe`。

---

## 项目结构

```
wallpaper-engine-web-manager/
├── app.py                    # Flask 应用入口（工厂模式 + 路由）
├── launcher.py               # 启动器入口（打包用，自动开浏览器）
├── launcher.spec             # PyInstaller 打包配置
├── build.bat                 # 打包脚本
├── config.json               # 配置文件
├── requirements.txt          # Python 依赖
├── static/
│   ├── css/
│   │   ├── bootstrap.min.css # Bootstrap 5
│   │   ├── all.min.css       # Font Awesome 6
│   │   └── style.css         # 自定义样式
│   ├── js/
│   │   ├── bootstrap.bundle.min.js
│   │   └── app.js            # 前端逻辑
│   ├── webfonts/             # Font Awesome 字体
│   └── img/                  # 图片资源
├── templates/
│   ├── base.html             # 基础布局
│   └── index.html            # 主页
├── api/
│   ├── wallpaper.py          # 壁纸数据管理（分页、缓存、删除）
│   └── config.py             # 配置读写（带备份）
└── utils/
    ├── steam_parser.py       # Steam VDF 解析、路径检测
    ├── image_processor.py    # 预览图提取与处理
    └── paths.py              # 数据目录路径管理（打包前后自适应）
```

---

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 主页 |
| `/api/wallpapers` | GET | 分页获取壁纸列表，支持 `user`、`search`、`content_rating`、`wallpaper_type`、`subscribed_page`、`unsubscribed_page`、`page_size` |
| `/api/wallpapers/<id>` | GET | 获取壁纸详情 |
| `/api/wallpapers/<id>/preview` | GET | 获取壁纸预览图 |
| `/api/wallpapers/<id>` | DELETE | 删除壁纸 |
| `/api/wallpapers/<id>/open-folder` | POST | 在资源管理器中打开壁纸文件夹 |
| `/api/stats` | GET | 获取存储统计，支持 `user` 参数 |
| `/api/users` | GET | 获取 Steam 用户列表及订阅数 |
| `/api/config` | GET / POST | 读取或更新配置 |
| `/api/steam-paths` | GET | 获取当前 Steam 路径信息 |
| `/api/search-history` | GET / POST / DELETE | 搜索历史管理 |
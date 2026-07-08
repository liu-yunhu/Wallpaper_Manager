# Wallpaper Engine Web Manager

基于 Flask 后端与响应式前端的 Wallpaper Engine 创意工坊订阅管理工具，通过浏览器即可浏览、搜索、清理本地壁纸内容。

![demo](static/img/demo.png)

---

## 版本说明

| 版本 | 适用场景 | 说明 |
|------|----------|------|
| **Release** | 普通用户 | 打包为独立可执行文件，解压即用，无需安装 Python 环境。下载地址见 [Releases](https://github.com/your-repo/releases) |
| **本地开发版**（当前仓库） | 开发者 / 进阶用户 | 需要 Python 3.8+ 环境，通过源码运行，适合二次开发与调试 |

---

## 功能特性

- **订阅管理** — 分页浏览已订阅/未订阅壁纸，按文件夹大小降序排列，轻松定位占用空间最多的内容
- **多用户支持** — 自动识别本机所有 Steam 用户，可切换用户查看各自的订阅数据
- **标题搜索** — 支持按壁纸标题实时过滤
- **预览图** — 内嵌预览图展示，支持 project.json 内嵌预览及常见图片格式
- **一键操作** — 删除壁纸释放磁盘空间、在资源管理器中打开壁纸文件夹
- **存储统计** — 实时展示已订阅/未订阅壁纸的数量与占用空间
- **Web 配置界面** — 无需手动编辑文件，通过网页即可修改 Steam 路径等配置项
- **路径自动检测** — 优先使用配置路径，支持从 Windows 注册表自动读取 Steam 安装位置，并回退到常见安装路径
- **响应式 UI** — 基于 Bootstrap 5 + Font Awesome，适配桌面与移动端

---

## 技术栈

- **后端**：Flask（应用工厂模式），vdf（VDF 解析），Pillow（图像处理）
- **前端**：Bootstrap 5，Font Awesome 6，原生 JavaScript（Fetch API）
- **数据源**：Steam userdata 目录下的 VDF 订阅文件 + Workshop 内容目录

---

## Quick Start

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

首次启动前，编辑 `config.json` 中的关键路径：

```json
{
  "steam_library_path": "F:\\SteamLibrary\\steamapps\\workshop\\content\\431960",
  "steam_userdata_path": "E:\\Software\\Steam\\userdata"
}
```

- `steam_library_path`：Wallpaper Engine 的 Workshop 内容目录（指向 `.../workshop/content/431960`）
- `steam_userdata_path`：Steam 安装目录下的 `userdata` 文件夹（可选，程序会自动检测）

也可在启动后通过网页「配置」按钮在线修改。

### 4. 启动服务

```bash
python app.py
```

### 5. 打开界面

浏览器访问 `http://localhost:5000`，点击「配置」按钮确认路径正确后即可使用。

---

## 配置说明

启动后请点击页面中的「配置」按钮检查路径是否正确。订阅数据从 Steam 客户端下的 `userdata` 文件夹读取，内容文件从 Workshop 的 `431960` 目录读取。

`config.json` 可配置项：

| 字段 | 说明 |
|------|------|
| `steam_library_path` | Wallpaper Engine Workshop 内容目录（`431960`） |
| `steam_userdata_path` | Steam userdata 目录（可选，留空则自动检测） |
| `server.host` | 监听地址，默认 `127.0.0.1` |
| `server.port` | 监听端口，默认 `5000` |
| `server.debug` | 调试模式，开发版默认 `true`，Release 版为 `false` |

---

## 项目结构

```
wallpaper-engine-web-manager/
├── app.py                    # Flask 应用入口（工厂模式）
├── config.json               # 配置文件
├── requirements.txt          # Python 依赖
├── static/                   # 静态资源
│   ├── css/                  # 样式表（Bootstrap + 自定义）
│   ├── js/                   # 前端逻辑
│   └── img/                  # 图片资源
├── templates/                # Jinja2 模板
│   ├── base.html             # 基础布局
│   └── index.html            # 主页
├── api/                      # 后端 API 模块
│   ├── wallpaper.py          # 壁纸数据管理（分页、缓存、删除）
│   └── config.py             # 配置读写（带备份）
└── utils/                    # 工具模块
    ├── steam_parser.py       # Steam VDF 解析、路径检测
    └── image_processor.py    # 预览图提取与处理
```

---

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 主页 |
| `/api/wallpapers` | GET | 分页获取壁纸列表（支持 `user`、`search`、`page_size` 参数） |
| `/api/wallpapers/<id>` | GET | 获取壁纸详情 |
| `/api/wallpapers/<id>/preview` | GET | 获取壁纸预览图 |
| `/api/wallpapers/<id>` | DELETE | 删除壁纸 |
| `/api/wallpapers/<id>/open-folder` | POST | 在资源管理器中打开壁纸文件夹 |
| `/api/stats` | GET | 获取存储统计 |
| `/api/users` | GET | 获取 Steam 用户列表 |
| `/api/config` | GET | 获取当前配置 |
| `/api/config` | POST | 更新配置 |
| `/api/steam-paths` | GET | 获取当前 Steam 路径信息 |
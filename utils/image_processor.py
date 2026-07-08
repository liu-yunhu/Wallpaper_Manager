"""
Image Processor
预览图查找与处理

仅保留预览图查找逻辑；图片处理（缩放/GIF 取帧）原为死代码且会泄漏
临时文件，已移除，需要时可在 git 历史中找回。
"""

import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# 预览图标准文件名（按优先级）
_PREVIEW_FILES = [
    ('preview.jpg', 'image'),
    ('preview.jpeg', 'image'),
    ('preview.png', 'image'),
    ('preview.gif', 'gif'),
    ('preview.webp', 'image'),
    ('preview.bmp', 'image'),
]

# 回退时识别的图片扩展名（按优先级）
_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tga']
_EXT_PRIORITY = {ext: i for i, ext in enumerate(_IMAGE_EXTENSIONS)}
# 跳过大于此大小的文件（很可能是主壁纸文件而非预览图）
_MAX_PREVIEW_SIZE = 50 * 1024 * 1024  # 50MB


class ImageProcessor:
    """图片处理工具"""

    def __init__(self, config: dict):
        self.config = config

    def find_preview_file(self, folder_path: Path) -> Tuple[Optional[str], Optional[str]]:
        """
        查找壁纸文件夹中的预览图

        返回: (preview_path, file_type) 或 (None, None)
              file_type 为 'image' 或 'gif'
        """
        # 1. 优先查找标准命名的预览图
        for filename, file_type in _PREVIEW_FILES:
            preview_path = folder_path / filename
            if preview_path.exists():
                return str(preview_path), file_type

        # 2. 回退：单次遍历收集所有候选图片，按扩展名优先级挑选
        candidates = []
        ext_set = set(_IMAGE_EXTENSIONS)
        for entry in folder_path.rglob('*'):
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in ext_set:
                continue
            try:
                if entry.stat().st_size > _MAX_PREVIEW_SIZE:
                    continue
            except OSError:
                continue
            candidates.append(entry)

        if not candidates:
            return None, None

        # 稳定排序：按扩展名优先级，同优先级保持 rglob 顺序
        candidates.sort(key=lambda c: _EXT_PRIORITY.get(c.suffix.lower(), 999))
        best = candidates[0]
        file_type = 'gif' if best.suffix.lower() == '.gif' else 'image'
        return str(best), file_type

    def get_preview_path(self, folder_path: Path) -> Optional[str]:
        """获取预览图路径（仅路径，不区分类型）"""
        preview_path, _ = self.find_preview_file(folder_path)
        return preview_path

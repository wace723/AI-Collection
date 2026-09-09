"""CSV 编码探测与文本解码。

示例文件原编码为 GBK，上传时也可能是 UTF-8（含 BOM）。
不引入 chardet 依赖，用试解码策略：按 UTF-8-SIG → GBK → GB18030 顺序尝试，
首个能完整解码且不含替换符的编码即采用。
"""

from __future__ import annotations

# 候选编码顺序：UTF-8-SIG 处理 BOM，GBK 覆盖示例文件，GB18030 是 GBK 超集兜底
_ENCODINGS: tuple[str, ...] = ("utf-8-sig", "gbk", "gb18030")


class EncodingError(ValueError):
    """所有候选编码都无法解码文件内容。"""


def detect_and_decode(raw: bytes) -> str:
    """探测字节流的编码并返回文本。

    Args:
        raw: 文件原始字节

    Returns:
        解码后的文本

    Raises:
        EncodingError: 所有候选编码都失败
    """
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise EncodingError("无法识别文件编码（已尝试 utf-8/gbk/gb18030）")

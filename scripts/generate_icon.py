"""アプリアイコンを生成するスクリプト"""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import subprocess
import tempfile


def create_icon_image(size: int) -> Image.Image:
    """アイコン画像を生成"""
    # 背景色（青系）
    bg_color = (46, 170, 220)  # #2eaadc

    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 角丸四角形の背景
    margin = int(size * 0.1)
    radius = int(size * 0.2)
    draw.rounded_rectangle(
        [margin, margin, size - margin, size - margin],
        radius=radius,
        fill=bg_color
    )

    # 「英」の文字を描画
    text = "英"

    # フォントサイズを計算
    font_size = int(size * 0.5)

    # macOSのヒラギノフォントを試す
    font_paths = [
        "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
        "/System/Library/Fonts/Hiragino Sans GB.ttc",
        "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]

    font = None
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue

    if font is None:
        # フォールバック
        font = ImageFont.load_default()

    # テキストのバウンディングボックスを取得
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # 中央に配置
    x = (size - text_width) // 2 - bbox[0]
    y = (size - text_height) // 2 - bbox[1]

    # 白い文字で描画
    draw.text((x, y), text, fill=(255, 255, 255), font=font)

    # 小さいペンマークを右下に
    pen_size = int(size * 0.15)
    pen_x = size - margin - pen_size - int(size * 0.05)
    pen_y = size - margin - pen_size - int(size * 0.05)

    # ペン（赤丸で表現）
    draw.ellipse(
        [pen_x, pen_y, pen_x + pen_size, pen_y + pen_size],
        fill=(235, 87, 87)  # 赤
    )

    return img


def create_iconset(output_dir: Path):
    """iconset フォルダを作成"""
    iconset_dir = output_dir / "AppIcon.iconset"
    iconset_dir.mkdir(parents=True, exist_ok=True)

    # 必要なサイズ
    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]

    for size, filename in sizes:
        img = create_icon_image(size)
        img.save(iconset_dir / filename, "PNG")
        print(f"  Created {filename} ({size}x{size})")

    return iconset_dir


def create_icns(output_dir: Path) -> Path:
    """macOS用 .icns ファイルを作成"""
    iconset_dir = create_iconset(output_dir)
    icns_path = output_dir / "AppIcon.icns"

    # iconutil コマンドで変換
    result = subprocess.run(
        ["iconutil", "-c", "icns", str(iconset_dir), "-o", str(icns_path)],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print(f"Created {icns_path}")
        # iconsetフォルダを削除
        import shutil
        shutil.rmtree(iconset_dir)
        return icns_path
    else:
        print(f"Error creating icns: {result.stderr}")
        return None


if __name__ == "__main__":
    output_dir = Path(__file__).parent.parent / "resources"
    output_dir.mkdir(exist_ok=True)

    print("Generating app icon...")
    icns_path = create_icns(output_dir)

    if icns_path and icns_path.exists():
        print(f"\nIcon created successfully: {icns_path}")
    else:
        print("\nFailed to create icon")

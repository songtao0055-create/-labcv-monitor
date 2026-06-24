"""
准备火灾+烟雾检测数据集

合并两个数据源:
  1. data/archive/  —— 主力数据集 (14k+ 训练图, 火焰+烟雾平衡)
     - 类别: ['smoke', 'fire']  (0=smoke, 1=fire)
  2. VOC2020/       —— 火焰补充 (2,059 图, 仅 fire 标注)

输出: data/fire_smoke_dataset/
  - 统一类别 ID: 0=smoke, 1=fire
  - train: archive train + VOC2020
  - val: archive val

用法: python prepare_dataset.py
"""

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
ARCHIVE_DIR = PROJECT_ROOT / "data" / "archive" / "data"
VOC_DIR = PROJECT_ROOT / "VOC2020"
OUT_DIR = PROJECT_ROOT / "data" / "fire_smoke_dataset"

# 统一后的类别映射: 0=smoke, 1=fire
# archive 已经是这个顺序，VOC2020 的 fire 映射为 1
CLASS_MAP = {"fire": 1, "smoke": 0}


def parse_voc_xml(xml_path: Path) -> list[tuple[int, float, float, float, float]]:
    """解析 VOC XML，返回 YOLO 格式标注列表 [(cls_id, cx, cy, w, h), ...]"""
    tree = ET.parse(xml_path)
    root = tree.getroot()
    size = root.find("size")
    img_w = int(size.find("width").text)
    img_h = int(size.find("height").text)

    labels = []
    for obj in root.findall("object"):
        name = obj.find("name").text
        if name not in CLASS_MAP:
            continue
        cls_id = CLASS_MAP[name]
        bbox = obj.find("bndbox")
        xmin = int(bbox.find("xmin").text)
        ymin = int(bbox.find("ymin").text)
        xmax = int(bbox.find("xmax").text)
        ymax = int(bbox.find("ymax").text)

        cx = ((xmin + xmax) / 2.0) / img_w
        cy = ((ymin + ymax) / 2.0) / img_h
        w = (xmax - xmin) / img_w
        h = (ymax - ymin) / img_h
        labels.append((cls_id, cx, cy, w, h))
    return labels


def merge_voc2020_into_train(train_img_dir: Path, train_lbl_dir: Path):
    """
    将 VOC2020 的火焰图片和标注合并到训练集中

    处理策略:
      - VOC2020 的图片 (JPEGImages/*.jpg) 直接复制
      - Annotation XML 转为 YOLO 格式
      - 图片命名统一加 voc_ 前缀防止与 archive 冲突
    """
    voc_img_dir = VOC_DIR / "JPEGImages"
    voc_ann_dir = VOC_DIR / "Annotations"
    if not voc_img_dir.exists() or not voc_ann_dir.exists():
        print("[SKIP] VOC2020 目录不存在，跳过火焰数据补充")
        return 0, 0

    converted_img = 0
    converted_box = 0

    for xml_file in sorted(voc_ann_dir.glob("*.xml")):
        fid = xml_file.stem
        img_src = voc_img_dir / f"{fid}.jpg"

        # 部分 VOC2020 图片可能是 PNG
        if not img_src.exists():
            # 尝试找匹配的图片
            for ext in (".jpg", ".jpeg", ".png", ".bmp"):
                candidate = voc_img_dir / f"{fid}{ext}"
                if candidate.exists():
                    img_src = candidate
                    break

        if not img_src.exists():
            continue

        labels = parse_voc_xml(xml_file)
        if not labels:
            # 只包含 fire 以外的类别（如已废弃的 smoke 标注），跳过
            continue

        # 用 voc_ 前缀避免与 archive 文件名冲突
        new_name = f"voc_{fid}.jpg"
        shutil.copy2(img_src, train_img_dir / new_name)

        lbl_path = train_lbl_dir / f"voc_{fid}.txt"
        with open(lbl_path, "w") as f:
            for cls_id, cx, cy, w, h in labels:
                f.write(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")

        converted_img += 1
        converted_box += len(labels)

    return converted_img, converted_box


def copy_archive_split(src_split: str, dst_split: str):
    """复制 archive 的一个 split (train/val) 到目标目录"""
    src_img = ARCHIVE_DIR / src_split / "images"
    src_lbl = ARCHIVE_DIR / src_split / "labels"
    dst_img = OUT_DIR / dst_split / "images"
    dst_lbl = OUT_DIR / dst_split / "labels"

    if not src_img.exists() or not src_lbl.exists():
        print(f"[SKIP] archive/{src_split} 不存在")
        return 0

    dst_img.mkdir(parents=True, exist_ok=True)
    dst_lbl.mkdir(parents=True, exist_ok=True)

    img_count = 0
    for img_file in src_img.iterdir():
        if img_file.suffix.lower() in (".jpg", ".jpeg", ".png", ".bmp", ".webp"):
            shutil.copy2(img_file, dst_img / img_file.name)
            img_count += 1

    lbl_count = 0
    for lbl_file in src_lbl.glob("*.txt"):
        shutil.copy2(lbl_file, dst_lbl / lbl_file.name)
        lbl_count += 1

    return img_count, lbl_count


def write_data_yaml():
    """生成 data.yaml"""
    content = f"""# fire_smoke_dataset —— fire + smoke detection
# 合并数据源: archive (主力) + VOC2020 (火焰补充)
# 类别: 0=smoke, 1=fire

path: {OUT_DIR.as_posix()}
train: train/images
val: val/images

nc: 2
names: ['smoke', 'fire']
"""
    yaml_path = OUT_DIR / "data.yaml"
    yaml_path.write_text(content, encoding="utf-8")
    print(f"[OK] data.yaml 已生成: {yaml_path}")


def main():
    print("=" * 60)
    print("  火灾烟雾数据集准备")
    print(f"  主力数据: archive/ ({ARCHIVE_DIR})")
    print(f"  火焰补充: VOC2020/ ({VOC_DIR})")
    print(f"  输出目录: {OUT_DIR}")
    print("  类别: 0=smoke, 1=fire")
    print("=" * 60)

    # 清理旧输出
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    # ---- 训练集: archive train + VOC2020 ----
    print("\n[1/3] 复制 archive train 数据...")
    train_imgs, train_lbls = copy_archive_split("train", "train")
    print(f"  → 图片: {train_imgs}, 标签: {train_lbls}")

    # ---- 验证集: archive val ----
    print("\n[2/3] 复制 archive val 数据...")
    val_imgs, val_lbls = copy_archive_split("val", "val")
    print(f"  → 图片: {val_imgs}, 标签: {val_lbls}")

    # ---- VOC2020 火焰补充到训练集 ----
    print("\n[3/3] 合并 VOC2020 火焰数据到训练集...")
    train_img_dir = OUT_DIR / "train" / "images"
    train_lbl_dir = OUT_DIR / "train" / "labels"
    voc_imgs, voc_boxes = merge_voc2020_into_train(train_img_dir, train_lbl_dir)
    print(f"  → 新增火焰图片: {voc_imgs}, 火焰标注框: {voc_boxes}")

    # ---- 生成 data.yaml ----
    write_data_yaml()

    # ---- 统计 ----
    print()
    print("=" * 60)
    print("  数据集摘要")
    print(f"  训练集: {train_imgs + voc_imgs} 张图片 ({train_imgs} archive + {voc_imgs} VOC2020)")
    print(f"  验证集: {val_imgs} 张图片")
    print(f"  类别: 0=smoke, 1=fire")
    print(f"  输出: {OUT_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()

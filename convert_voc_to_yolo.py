"""
VOC XML → YOLO 格式转换 (仅验证集)

用法: python convert_voc_to_yolo.py
输出: data/fire_dataset/val/ (YOLO 格式)
"""

import xml.etree.ElementTree as ET
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
VOC_DIR = PROJECT_ROOT / "voc2020"
OUT_DIR = PROJECT_ROOT / "data" / "fire_dataset"

CLASS_MAP = {"fire": 0, "smoke": 1}


def parse_voc_xml(xml_path: Path) -> list[tuple[int, float, float, float, float]]:
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


def main():
    train_txt = VOC_DIR / "ImageSets" / "Main" / "train.txt"
    with open(train_txt) as f:
        all_ids = [line.strip() for line in f if line.strip()]

    # 全部放 val 目录 (只做验证不做训练)
    img_dir = OUT_DIR / "val" / "images"
    lbl_dir = OUT_DIR / "val" / "labels"
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)

    converted = 0
    total_boxes = 0
    for fid in all_ids:
        img_src = VOC_DIR / "JPEGImages" / f"{fid}.jpg"
        xml_src = VOC_DIR / "Annotations" / f"{fid}.xml"
        if not img_src.exists() or not xml_src.exists():
            continue
        shutil.copy2(img_src, img_dir / f"{fid}.jpg")
        labels = parse_voc_xml(xml_src)
        total_boxes += len(labels)
        with open(lbl_dir / f"{fid}.txt", "w") as f:
            for cls_id, cx, cy, w, h in labels:
                f.write(f"{cls_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")
        converted += 1

    # data.yaml
    yaml_path = OUT_DIR / "data.yaml"
    yaml_path.write_text(f"path: {OUT_DIR}\ntrain: val/images\nval: val/images\nnc: 2\nnames: ['fire', 'smoke']\n")

    print(f"转换完成: {converted} 张图片, {total_boxes} 个标注框")
    print(f"输出目录: {OUT_DIR}")
    print(f"配置文件: {yaml_path}")


if __name__ == "__main__":
    main()

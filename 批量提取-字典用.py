#!/usr/bin/env python3
"""
Sky JSON 翻译清单扫描工具
扫描整个 JSON 目录，找出所有未翻译的类名和属性名
用法:
    python scan_all_names.py /path/to/json_dir
"""

import sys
import os
import json


def orig_name(name):
    """从带中文注释的名称中提取原始英文名"""
    if "（" in name and name.endswith("）"):
        return name.split("（")[0]
    if " (" in name and name.endswith(")"):
        return name.split(" (")[0]
    return name


def has_translation(name):
    """判断名称是否已有中文翻译"""
    if "（" in name and name.endswith("）"):
        return True
    if " (" in name and name.endswith(")"):
        return True
    return False


def scan_json_file(json_path: str) -> tuple:
    """扫描单个 JSON 文件"""
    with open(json_path, 'r', encoding='utf-8') as f:
        j = json.load(f)

    untranslated_classes = set()
    untranslated_props = set()
    all_classes = set()
    all_props = set()

    # 扫描 classes
    classes_data = j.get('classes', {})
    for cls_name, cls_meta in classes_data.items():
        real_cls = orig_name(cls_name)
        all_classes.add(real_cls)
        if not has_translation(cls_name):
            untranslated_classes.add(real_cls)

        if isinstance(cls_meta, dict):
            for prop_name in cls_meta.keys():
                real_prop = orig_name(prop_name)
                all_props.add(real_prop)
                if not has_translation(prop_name):
                    untranslated_props.add(real_prop)

    # 扫描 BSTNodes
    bst_nodes = j.get('BSTNodes', {})
    for bst_name, node_data in bst_nodes.items():
        if isinstance(node_data, dict):
            for cls_name in node_data.keys():
                real_cls = orig_name(cls_name)
                all_classes.add(real_cls)
                if not has_translation(cls_name):
                    untranslated_classes.add(real_cls)
            _scan_dict_keys(node_data, all_props, untranslated_props)

    return untranslated_classes, untranslated_props, all_classes, all_props


def _scan_dict_keys(obj, all_props, untranslated_props):
    if isinstance(obj, dict):
        for key in obj.keys():
            if not key.startswith('_') and not key.startswith('[') and key not in ('propertyType', 'objectByteSize', 'arrayIndex', 'version', 'MemorySize', 'classes', 'BSTNodes'):
                real_key = orig_name(key)
                all_props.add(real_key)
                if not has_translation(key):
                    untranslated_props.add(real_key)
            _scan_dict_keys(obj[key], all_props, untranslated_props)
    elif isinstance(obj, list):
        for item in obj:
            _scan_dict_keys(item, all_props, untranslated_props)


def find_json_files(root_dir: str) -> list:
    """递归查找所有 JSON 文件"""
    json_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith('.json'):
                full_path = os.path.join(dirpath, filename)
                json_files.append(full_path)
    return sorted(json_files)


def scan_all(root_dir: str):
    """扫描所有 JSON 文件"""
    json_files = find_json_files(root_dir)

    if not json_files:
        print(f"❌ 在 {root_dir} 中没有找到 JSON 文件")
        return

    print(f"找到 {len(json_files)} 个 JSON 文件\n")
    print("正在扫描...")

    all_untranslated_classes = set()
    all_untranslated_props = set()
    total_classes = set()
    total_props = set()

    for i, json_path in enumerate(json_files, 1):
        # 获取地图名
        rel_path = os.path.relpath(json_path, root_dir)
        parts = rel_path.replace('\\', '/').split('/')
        map_name = parts[0] if len(parts) > 1 else "unknown"

        try:
            unt_cls, unt_props, all_cls, all_props = scan_json_file(json_path)
            all_untranslated_classes.update(unt_cls)
            all_untranslated_props.update(unt_props)
            total_classes.update(all_cls)
            total_props.update(all_props)
        except Exception as e:
            print(f"  [{i}/{len(json_files)}] {map_name} ❌ {e}")

    # 输出结果
    print(f"\n{'='*60}")
    print(f"扫描结果:")
    print(f"  总类名数: {len(total_classes)}")
    print(f"  未翻译类名: {len(all_untranslated_classes)}")
    print(f"  总属性名数: {len(total_props)}")
    print(f"  未翻译属性名: {len(all_untranslated_props)}")

    # 生成输出文件
    base = os.path.basename(root_dir.rstrip('/\\')) or "output"
    out_path = os.path.join(os.path.dirname(root_dir) or '.', f"{base}_untranslated.txt")

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(f"扫描目录: {root_dir}\n")
        f.write(f"扫描文件数: {len(json_files)}\n")
        f.write(f"\n{'='*60}\n")
        f.write(f"未翻译类名 (共 {len(all_untranslated_classes)} 个):\n")
        f.write(f"{'='*60}\n")
        for name in sorted(all_untranslated_classes):
            f.write(f'    "{name}": "",\n')

        f.write(f"\n{'='*60}\n")
        f.write(f"未翻译属性名 (共 {len(all_untranslated_props)} 个):\n")
        f.write(f"{'='*60}\n")
        for name in sorted(all_untranslated_props):
            f.write(f'    "{name}": "",\n')

    print(f"\n📄 未翻译清单已保存到: {out_path}")
    print(f"\n翻译覆盖率:")
    if total_classes:
        cls_coverage = (1 - len(all_untranslated_classes) / len(total_classes)) * 100
        print(f"  类名: {cls_coverage:.1f}%")
    if total_props:
        prop_coverage = (1 - len(all_untranslated_props) / len(total_props)) * 100
        print(f"  属性名: {prop_coverage:.1f}%")

    return out_path


def main():
    if len(sys.argv) < 2:
        print("用法: python scan_all_names.py /path/to/json_dir")
        print("  扫描整个 JSON 目录，找出所有未翻译的名称")
        return

    root_dir = sys.argv[1]
    if not os.path.exists(root_dir):
        print(f"❌ 目录不存在: {root_dir}")
        return

    scan_all(root_dir)


if __name__ == '__main__':
    main()
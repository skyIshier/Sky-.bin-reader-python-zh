#!/usr/bin/env python3
"""
Sky .bin 批量转换工具
扫描整个 Levels 目录，将所有 .bin 文件转换为 JSON
保持原始目录结构，保留原始文件名

用法:
    python 批量转换.py                           # 交互式菜单
    python 批量转换.py /path/to/Levels            # 命令行模式
    python 批量转换.py /path/to/Levels /output    # 指定输出目录
"""

import sys
import os
import json
import struct
import shutil
from collections import OrderedDict
from io import BytesIO


# ============================================================
# 导入翻译表
# ============================================================

try:
    from zh字典 import CLASS_NAMES_ZH, PROPERTY_NAMES_ZH
except ImportError:
    CLASS_NAMES_ZH = {}
    PROPERTY_NAMES_ZH = {}


def translate_class_name(name):
    zh = CLASS_NAMES_ZH.get(name, "")
    if zh:
        return f"{name}（{zh}）"
    return name


def translate_property_name(name):
    zh = PROPERTY_NAMES_ZH.get(name, "")
    if zh:
        return f"{name}（{zh}）"
    return name


def orig_name(name):
    if "（" in name and name.endswith("）"):
        return name.split("（")[0]
    if " (" in name and name.endswith(")"):
        return name.split(" (")[0]
    return name


# ============================================================
# 浮点数精度保证
# ============================================================

def float_from_u32(u32: int) -> float:
    return struct.unpack('f', struct.pack('I', u32))[0]

def u32_from_float(f: float) -> int:
    return struct.unpack('I', struct.pack('f', f))[0]

def double_from_raw(raw_bytes: bytes) -> float:
    return struct.unpack('d', raw_bytes)[0]

NAN_SENTINEL = 0xFFFFFFF6

def should_read_uint32_as_integer(property_name: str) -> bool:
    real = orig_name(property_name)
    return real == "bstGuid" or "BstGuid" in real

def ends_with(value: str, suffix: str) -> bool:
    return value.endswith(suffix)

def is_nan_clump_string(value: str) -> bool:
    v = value.strip().lower()
    return v in ("", "-nan", "nan", "null")

def is_nan_numeric_text(value: str) -> bool:
    v = value.strip().lower()
    return v in ("-nan", "nan")

def _get_original_bin_candidates(json_file_path: str) -> list:
    base, ext = os.path.splitext(json_file_path)
    candidates = [base]
    for suffix in (".parsed", ".parser"):
        if ends_with(base, suffix):
            candidates.append(base[:-len(suffix)])
    return candidates


# ============================================================
# 数据结构
# ============================================================

class ClassDef:
    __slots__ = ('classPropertyNameOffset', 'classPropertyStartingIndex',
                 'classPropertyCount', 'className')
    def __init__(self):
        self.classPropertyNameOffset = 0
        self.classPropertyStartingIndex = 0
        self.classPropertyCount = 0
        self.className = ""
    @staticmethod
    def read(stream):
        c = ClassDef()
        data = stream.read(12)
        c.classPropertyNameOffset, c.classPropertyStartingIndex, c.classPropertyCount = struct.unpack('<III', data)
        return c


class PropertyDef:
    __slots__ = ('propertyType', 'propertyNameOffset', 'objectByteSize',
                 'arrayIndex', 'propertyName')
    def __init__(self):
        self.propertyType = 0
        self.propertyNameOffset = 0
        self.objectByteSize = 0
        self.arrayIndex = 0
        self.propertyName = ""
    @staticmethod
    def read(stream):
        p = PropertyDef()
        data = stream.read(16)
        p.propertyType, p.propertyNameOffset, p.objectByteSize, p.arrayIndex = struct.unpack('<IIII', data)
        return p


class BSTHeader:
    __slots__ = ('magic', 'version', 'classLength', 'propertyCount',
                 'BSTNodeCount', 'objectPtrCount', 'classOffset',
                 'propertyOffset', 'PropertyNameOffset', 'BSTNodeOffset', 'FileSize')
    def __init__(self, stream):
        data = stream.read(44)
        (self.magic, self.version, self.classLength, self.propertyCount,
         self.BSTNodeCount, self.objectPtrCount, self.classOffset,
         self.propertyOffset, self.PropertyNameOffset, self.BSTNodeOffset,
         self.FileSize) = struct.unpack('<4sIIIIIIIIII', data)
    @property
    def magic_str(self):
        return self.magic.decode('ascii', errors='replace')


# ============================================================
# 二进制读取
# ============================================================

def _read_cstring(stream) -> str:
    result = bytearray()
    while True:
        ch = stream.read(1)
        if not ch or ch == b'\x00':
            break
        result.extend(ch)
    return result.decode('utf-8', errors='replace')

def _read_classes(stream, header: BSTHeader) -> list:
    stream.seek(header.classOffset)
    return [ClassDef.read(stream) for _ in range(header.classLength)]

def _read_all_properties(stream, header: BSTHeader, classes: list) -> list:
    stream.seek(header.propertyOffset)
    all_props = []
    for cls in classes:
        props = []
        if cls.classPropertyCount > 0:
            stream.seek(header.propertyOffset + cls.classPropertyStartingIndex * 16)
            for _ in range(cls.classPropertyCount):
                props.append(PropertyDef.read(stream))
            for p in props:
                stream.seek(header.PropertyNameOffset + p.propertyNameOffset)
                p.propertyName = _read_cstring(stream)
        all_props.append(props)
        stream.seek(header.PropertyNameOffset + cls.classPropertyNameOffset)
        cls.className = _read_cstring(stream)
    return all_props


# ============================================================
# 读取原始值
# ============================================================

def _make_original_key(node, cls, prop):
    return f"{node}\x1F{cls}\x1F{prop}"

def load_original_string_pool_order(json_file_path: str) -> list:
    candidates = _get_original_bin_candidates(json_file_path)
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, 'rb') as f:
                header = BSTHeader(f)
                if header.magic_str != 'TGCL':
                    continue
                f.seek(header.PropertyNameOffset)
                names = []
                while f.tell() < header.BSTNodeOffset:
                    name = _read_cstring(f)
                    if name:
                        names.append(name)
                if names:
                    return names
        except:
            pass
    return []

def load_original_top_level_u32(json_file_path: str) -> dict:
    candidates = _get_original_bin_candidates(json_file_path)
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, 'rb') as f:
                header = BSTHeader(f)
                if header.magic_str != 'TGCL':
                    continue
                classes = _read_classes(f, header)
                all_props = _read_all_properties(f, header, classes)
                f.seek(header.BSTNodeOffset)
                out = {}
                for _ in range(header.BSTNodeCount):
                    index = struct.unpack('<I', f.read(4))[0]
                    bst_name = _read_cstring(f)
                    _capture_u32(f, bst_name, index, all_props, classes, out, True)
                if out:
                    return out
        except:
            pass
    return {}

def _capture_u32(stream, node_name, class_idx, all_props, classes, out, top):
    if class_idx >= len(all_props):
        return
    for prop in all_props[class_idx]:
        try:
            if prop.propertyType == 0 and prop.objectByteSize == 4:
                raw = struct.unpack('<I', stream.read(4))[0]
                if top:
                    key = _make_original_key(node_name, classes[class_idx].className, prop.propertyName)
                    out[key] = raw
            elif prop.propertyType == 0:
                skip = prop.objectByteSize if prop.objectByteSize > 0 else 4
                stream.seek(skip, 1)
            elif prop.propertyType == 1:
                _read_cstring(stream)
            elif prop.propertyType == 2:
                stream.seek(4, 1)
            elif prop.propertyType == 3:
                count = min(struct.unpack('<I', stream.read(4))[0], 100000)
                if prop.arrayIndex != 0xFFFFFFFF:
                    for _ in range(count):
                        _capture_u32(stream, node_name, prop.arrayIndex, all_props, classes, out, False)
                else:
                    stream.seek(count * 4, 1)
            else:
                stream.seek(max(prop.objectByteSize, 4), 1)
        except:
            break


# ============================================================
# .bin -> .json
# ============================================================

def bin_to_json(input_path: str, translate: bool = True) -> OrderedDict:
    with open(input_path, 'rb') as f:
        header = BSTHeader(f)
        if header.magic_str != 'TGCL':
            raise ValueError("不是有效的 TGCL 文件")

        classes = _read_classes(f, header)
        all_props = _read_all_properties(f, header, classes)

        j = OrderedDict()
        j['version'] = header.version
        j['MemorySize'] = str(header.objectPtrCount)
        j['classes'] = OrderedDict()
        j['BSTNodes'] = OrderedDict()

        for i, cls in enumerate(classes):
            cls_key = translate_class_name(cls.className) if translate else cls.className
            if not all_props[i]:
                j['classes'][cls_key] = None
            else:
                meta = OrderedDict()
                for prop in all_props[i]:
                    prop_key = translate_property_name(prop.propertyName) if translate else prop.propertyName
                    meta[prop_key] = OrderedDict([
                        ('propertyType', prop.propertyType),
                        ('objectByteSize', prop.objectByteSize),
                        ('arrayIndex', prop.arrayIndex)
                    ])
                j['classes'][cls_key] = meta

        f.seek(header.BSTNodeOffset)
        for _ in range(header.BSTNodeCount):
            index = struct.unpack('<I', f.read(4))[0]
            bst_name = _read_cstring(f)
            node = OrderedDict()
            _read_class_data(f, node, index, all_props, classes, translate)
            j['BSTNodes'][bst_name] = node

        bst_names = list(j['BSTNodes'].keys())
        for bst_name, node in j['BSTNodes'].items():
            if isinstance(node, dict):
                for cls_name, cls_data in node.items():
                    real_cls = orig_name(cls_name)
                    meta = j['classes'].get(real_cls, {})
                    if not meta:
                        for k in j['classes']:
                            if orig_name(k) == real_cls:
                                meta = j['classes'][k]
                                break
                    if isinstance(meta, dict) and isinstance(cls_data, dict):
                        _resolve_clump_refs(cls_data, j['classes'], meta, classes, bst_names)

        return j


def _read_class_data(stream, json_data, index, all_props, classes, translate=True):
    if index >= len(classes) or index >= len(all_props):
        return
    cls = classes[index]
    cls_key = translate_class_name(cls.className) if translate else cls.className
    if cls_key not in json_data:
        json_data[cls_key] = OrderedDict()
    target = json_data[cls_key]

    for prop in all_props[index]:
        try:
            ptype = prop.propertyType
            psize = prop.objectByteSize
            prop_key = translate_property_name(prop.propertyName) if translate else prop.propertyName

            if ptype == 0:
                if psize == 1:
                    v = struct.unpack('<B', stream.read(1))[0]
                    target[prop_key] = OrderedDict([('_raw_uint8', v), ('_value', bool(v) if v <= 1 else f"0x{v:02X}")])
                elif psize == 2:
                    v = struct.unpack('<H', stream.read(2))[0]
                    target[prop_key] = OrderedDict([('_raw_uint16', v), ('_value', v)])
                elif psize == 4:
                    raw = struct.unpack('<I', stream.read(4))[0]
                    if should_read_uint32_as_integer(prop.propertyName):
                        target[prop_key] = OrderedDict([('_raw_uint32', raw), ('_value', str(raw))])
                    else:
                        fval = float_from_u32(raw)
                        target[prop_key] = OrderedDict([('_raw_uint32', raw), ('_value', str(fval))])
                elif psize == 8:
                    raw_bytes = stream.read(8)
                    dval = double_from_raw(raw_bytes)
                    target[prop_key] = OrderedDict([('_raw_bytes_hex', raw_bytes.hex()), ('_value', str(dval))])
                elif psize == 10:
                    raw_bytes = stream.read(10)
                    dval = double_from_raw(raw_bytes[:8])
                    target[prop_key] = OrderedDict([('_raw_bytes_hex', raw_bytes.hex()), ('_value', str(dval))])
                elif psize == 16:
                    vals = struct.unpack('<ffff', stream.read(16))
                    target[prop_key] = OrderedDict([('_raw_floats', [str(v) for v in vals]), ('_value', [str(v) for v in vals])])
                elif psize == 64:
                    vals = struct.unpack('<16f', stream.read(64))
                    mat = [[str(vals[i*4+j]) for j in range(4)] for i in range(4)]
                    target[prop_key] = OrderedDict([('_raw_floats', [str(v) for v in vals]), ('_value', mat)])
                else:
                    raw_bytes = stream.read(psize)
                    target[prop_key] = OrderedDict([('_raw_bytes_hex', raw_bytes.hex()), ('_value', f"[大小 {psize} 字节]")])
            elif ptype == 1:
                target[prop_key] = _read_cstring(stream)
            elif ptype == 2:
                raw = struct.unpack('<I', stream.read(4))[0]
                target[prop_key] = OrderedDict([('_raw_uint32', raw), ('_is_clump', True)])
            elif ptype == 3:
                count = min(struct.unpack('<I', stream.read(4))[0], 100000)
                if prop.arrayIndex != 0xFFFFFFFF:
                    arr = []
                    for _ in range(count):
                        elem = OrderedDict()
                        _read_class_data(stream, elem, prop.arrayIndex, all_props, classes, translate)
                        arr.append(elem)
                    target[prop_key] = arr
                else:
                    clump_data = []
                    for _ in range(count):
                        raw = struct.unpack('<I', stream.read(4))[0]
                        clump_data.append(OrderedDict([('_raw_uint32', raw), ('_is_clump', True)]))
                    target[prop_key] = OrderedDict([('_array_count', count), ('_elements', clump_data)])
            else:
                raw_bytes = stream.read(max(psize, 4))
                target[prop_key] = OrderedDict([('_raw_bytes_hex', raw_bytes.hex()), ('_value', f"[未知类型 {psize} 字节]")])
        except Exception as e:
            print(f"    警告: 读取属性 '{prop.propertyName}' 失败: {e}")
            break


def _resolve_clump_refs(class_data, all_meta, class_meta, classes, bst_names):
    for prop_name, meta in class_meta.items():
        if not isinstance(meta, dict):
            continue
        ptype = meta.get('propertyType')
        array_idx = meta.get('arrayIndex')
        real_prop = orig_name(prop_name)

        if ptype == 2:
            val = class_data.get(prop_name)
            if isinstance(val, dict) and val.get('_is_clump'):
                raw = val['_raw_uint32']
                fv = float_from_u32(raw)
                if str(fv) == 'nan':
                    val['_clump_name'] = 'nan'
                elif raw < len(bst_names):
                    val['_clump_name'] = bst_names[raw]
                else:
                    val['_clump_name'] = str(raw)
        elif ptype == 3 and array_idx is not None and array_idx != 0xFFFFFFFF and array_idx < len(classes):
            arr = class_data.get(prop_name)
            if isinstance(arr, list):
                nested_cls = classes[array_idx].className
                nested_meta = all_meta.get(nested_cls, {})
                if not nested_meta:
                    for k in all_meta:
                        if orig_name(k) == nested_cls:
                            nested_meta = all_meta[k]
                            break
                for elem in arr:
                    if isinstance(elem, dict):
                        _resolve_clump_refs(elem, all_meta, nested_meta, classes, bst_names)
        elif ptype == 3:
            obj = class_data.get(prop_name)
            if isinstance(obj, dict) and '_elements' in obj:
                for elem in obj['_elements']:
                    if isinstance(elem, dict) and elem.get('_is_clump'):
                        raw = elem['_raw_uint32']
                        fv = float_from_u32(raw)
                        if str(fv) == 'nan':
                            elem['_clump_name'] = 'nan'
                        elif raw < len(bst_names):
                            elem['_clump_name'] = bst_names[raw]
                        else:
                            elem['_clump_name'] = str(raw)


# ============================================================
# .json -> .bin
# ============================================================

def json_to_bin(input_path: str, output_path: str):
    with open(input_path, 'r', encoding='utf-8') as f:
        j = json.load(f, object_pairs_hook=OrderedDict)

    classes = []
    cls_idx_map = {}
    prop_list = []
    prop_count = 0
    offset = 44
    cls_start = 0

    for cls_name, cls_meta in j.get('classes', {}).items():
        real_name = orig_name(cls_name)
        cd = ClassDef()
        cd.classPropertyCount = len(cls_meta) if isinstance(cls_meta, dict) else 0
        cd.classPropertyStartingIndex = cls_start
        cd.className = real_name
        cls_start += cd.classPropertyCount
        cls_idx_map[real_name] = len(classes)
        classes.append(cd)
        offset += 12

    prop_offset = offset
    for cls in classes:
        cls_key = cls.className
        meta = None
        for k, v in j.get('classes', {}).items():
            if orig_name(k) == cls_key:
                meta = v
                break
        if isinstance(meta, dict):
            for pname, pmeta in meta.items():
                real_pname = orig_name(pname)
                pd = PropertyDef()
                pd.propertyType = pmeta['propertyType']
                pd.objectByteSize = pmeta['objectByteSize']
                pd.arrayIndex = pmeta.get('arrayIndex', 0)
                pd.propertyName = real_pname
                prop_list.append(pd)
                offset += 16
                prop_count += 1

    orig_pool = load_original_string_pool_order(input_path)
    orig_u32 = load_original_top_level_u32(input_path)

    pooled = []
    pool_off = {}
    pool_pos = 0

    def reg(name):
        nonlocal pool_pos
        if name in pool_off:
            return pool_off[name]
        pool_off[name] = pool_pos
        pooled.append(name)
        pool_pos += len(name.encode('utf-8')) + 1
        return pool_off[name]

    for name in orig_pool:
        need = any(p.propertyName == name for p in prop_list) or any(c.className == name for c in classes)
        if need:
            reg(name)

    for p in prop_list:
        p.propertyNameOffset = reg(p.propertyName)
    for c in classes:
        c.classPropertyNameOffset = reg(c.className)

    name_offset = offset
    offset += pool_pos
    bst_offset = offset

    bst_nodes = j.get('BSTNodes', {})
    node_idx = {}
    obj_ptr = 0
    bst_buffer = BytesIO()

    for idx, bst_name in enumerate(bst_nodes.keys()):
        node_idx[bst_name] = idx
        nd = bst_nodes[bst_name]
        if isinstance(nd, dict) and nd:
            first_key = next(iter(nd))
            cls_name = orig_name(first_key)
            cls_data = nd[first_key]
            obj_ptr += _count_obj_ptrs(j, classes, cls_name, cls_data)

            class_idx = cls_idx_map.get(cls_name, 0)
            bst_buffer.write(struct.pack('<I', class_idx))
            bst_buffer.write(bst_name.encode('utf-8'))
            bst_buffer.write(b'\x00')
            _write_class(bst_buffer, j, classes, node_idx, orig_u32, bst_name, cls_name, cls_data)

    bst_data = bst_buffer.getvalue()
    bst_buffer.close()

    file_size = bst_offset + len(bst_data)
    version = j.get('version', 1)
    bst_count = len(bst_nodes)

    with open(output_path, 'wb') as f:
        f.write(struct.pack('<4sIIIIIIIIII',
            b'TGCL', version, len(classes), prop_count,
            bst_count, obj_ptr, 44, prop_offset,
            name_offset, bst_offset, file_size))

        for c in classes:
            f.write(struct.pack('<III', c.classPropertyNameOffset,
                                c.classPropertyStartingIndex, c.classPropertyCount))

        for p in prop_list:
            f.write(struct.pack('<IIII', p.propertyType, p.propertyNameOffset,
                                p.objectByteSize, p.arrayIndex))

        for name in pooled:
            f.write(name.encode('utf-8'))
            f.write(b'\x00')

        f.write(bst_data)

    return True


def _find_class_meta(j, cls_name):
    for k, v in j.get('classes', {}).items():
        if orig_name(k) == cls_name:
            return v
    return {}


def _find_key_in_dict(d, target):
    if isinstance(d, dict):
        for k in d:
            if orig_name(k) == target:
                return k
    return target


def _count_obj_ptrs(j, classes, cls_name, cls_data):
    meta = _find_class_meta(j, cls_name)
    if not isinstance(meta, dict) or not isinstance(cls_data, dict):
        return 0
    cnt = 0
    for pname, pmeta in meta.items():
        if not isinstance(pmeta, dict):
            continue
        ptype = pmeta['propertyType']
        aidx = pmeta.get('arrayIndex')
        val = cls_data.get(pname)

        if ptype == 2:
            cnt += 1
        elif ptype == 3 and aidx == 0xFFFFFFFF:
            if isinstance(val, dict) and '_elements' in val:
                cnt += len(val['_elements'])
            elif isinstance(val, list):
                cnt += len(val)
        elif ptype == 3 and isinstance(val, list) and aidx is not None and aidx < len(classes):
            ncls = classes[aidx].className
            for e in val:
                if isinstance(e, dict):
                    found_key = _find_key_in_dict(e, ncls)
                    if found_key in e:
                        cnt += _count_obj_ptrs(j, classes, ncls, e[found_key])
    return cnt


def _write_class(stream, j, classes, node_idx, orig_u32, node_name, cls_name, cls_data):
    meta = _find_class_meta(j, cls_name)
    if not isinstance(meta, dict) or not isinstance(cls_data, dict):
        return

    for pname, pmeta in meta.items():
        if not isinstance(pmeta, dict):
            continue
        ptype = pmeta['propertyType']
        psize = pmeta.get('objectByteSize', 0)
        aidx = pmeta.get('arrayIndex')
        val = cls_data.get(pname)
        real_pname = orig_name(pname)

        try:
            if ptype == 0:
                _write_general(stream, psize, val, orig_u32, node_name, cls_name, real_pname)
            elif ptype == 1:
                s = val if isinstance(val, str) else str(val)
                stream.write(s.encode('utf-8') + b'\x00')
            elif ptype == 2:
                _write_clump(stream, val, node_idx)
            elif ptype == 3:
                _write_array(stream, j, classes, node_idx, orig_u32, node_name, val, aidx)
            else:
                stream.write(_extract_raw_bytes(val, max(psize, 4)))
        except Exception as e:
            stream.write(b'\x00' * max(psize, 4))


def _write_general(stream, psize, val, orig_u32, node_name, cls_name, pname):
    if isinstance(val, dict):
        if psize == 1:
            raw = val.get('_raw_uint8', 0)
            stream.write(struct.pack('<B', raw & 0xFF))
        elif psize == 2:
            raw = val.get('_raw_uint16', 0)
            stream.write(struct.pack('<H', raw & 0xFFFF))
        elif psize == 4:
            raw = val.get('_raw_uint32')
            if raw is None:
                v_str = str(val.get('_value', '0'))
                try:
                    if '.' in v_str or 'e' in v_str.lower() or 'nan' in v_str.lower():
                        raw = u32_from_float(float(v_str))
                    else:
                        raw = int(v_str)
                except:
                    raw = orig_u32.get(_make_original_key(node_name, cls_name, pname), 0)
            stream.write(struct.pack('<I', raw))
        elif psize == 8:
            raw_hex = val.get('_raw_bytes_hex', '')
            if raw_hex and len(raw_hex) == 16:
                stream.write(bytes.fromhex(raw_hex))
            else:
                v = float(val.get('_value', '0'))
                stream.write(struct.pack('<d', v))
        elif psize == 10:
            raw_hex = val.get('_raw_bytes_hex', '')
            if raw_hex and len(raw_hex) == 20:
                stream.write(bytes.fromhex(raw_hex))
            else:
                v = float(val.get('_value', '0'))
                stream.write(struct.pack('<d', v) + b'\x00\x00')
        elif psize == 16:
            arr = val.get('_raw_floats', val.get('_value', []))
            if isinstance(arr, list):
                flat = [float(x) for x in arr[:4]]
                while len(flat) < 4:
                    flat.append(0.0)
                stream.write(struct.pack('<ffff', *flat))
            else:
                stream.write(b'\x00' * 16)
        elif psize == 64:
            arr = val.get('_raw_floats', [])
            if isinstance(arr, list) and len(arr) >= 16:
                flat = [float(x) for x in arr[:16]]
            else:
                flat = [0.0] * 16
            stream.write(struct.pack('<16f', *flat))
        else:
            raw = _extract_raw_bytes(val, psize)
            stream.write(raw)
    else:
        if psize == 1:
            stream.write(struct.pack('<B', int(bool(val)) if isinstance(val, (bool, int)) else 0))
        elif psize == 4:
            key = _make_original_key(node_name, cls_name, pname)
            stream.write(struct.pack('<I', orig_u32.get(key, 0)))
        elif psize == 8:
            stream.write(struct.pack('<d', float(val)))
        else:
            stream.write(b'\x00' * psize)


def _write_clump(stream, val, node_idx):
    if isinstance(val, dict) and val.get('_is_clump'):
        name = val.get('_clump_name', '')
        if name in node_idx:
            stream.write(struct.pack('<I', node_idx[name]))
        else:
            stream.write(struct.pack('<I', val['_raw_uint32']))
    else:
        stream.write(struct.pack('<I', 0xFFFFFFFF))


def _write_array(stream, j, classes, node_idx, orig_u32, node_name, val, aidx):
    if aidx == 0xFFFFFFFF:
        items = []
        if isinstance(val, dict) and '_elements' in val:
            items = val['_elements']
        elif isinstance(val, list):
            items = val
        stream.write(struct.pack('<I', len(items)))
        for item in items:
            if isinstance(item, dict) and item.get('_is_clump'):
                name = item.get('_clump_name', '')
                if name in node_idx:
                    stream.write(struct.pack('<I', node_idx[name]))
                else:
                    stream.write(struct.pack('<I', item.get('_raw_uint32', 0xFFFFFFFF)))
            elif isinstance(item, (int, float)):
                stream.write(struct.pack('<I', int(item)))
            else:
                stream.write(struct.pack('<I', 0xFFFFFFFF))
    else:
        arr = val if isinstance(val, list) else []
        stream.write(struct.pack('<I', len(arr)))
        if aidx is not None and aidx < len(classes):
            ncls = classes[aidx].className
            for e in arr:
                if isinstance(e, dict):
                    found_key = _find_key_in_dict(e, ncls)
                    if found_key in e:
                        _write_class(stream, j, classes, node_idx, orig_u32, node_name, ncls, e[found_key])
                else:
                    _write_class(stream, j, classes, node_idx, orig_u32, node_name, ncls, e)


def _extract_raw_bytes(val, size):
    if isinstance(val, dict):
        raw_hex = val.get('_raw_bytes_hex', '')
        if raw_hex:
            b = bytes.fromhex(raw_hex)
            return b.ljust(size, b'\x00')[:size]
    return b'\x00' * size


# ============================================================
# 批量转换逻辑
# ============================================================

def find_bin_files(root_dir: str) -> list:
    """递归查找所有 .bin 文件"""
    bin_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        for filename in filenames:
            if filename.endswith(".bin"):
                full_path = os.path.join(dirpath, filename)
                bin_files.append(full_path)
    return sorted(bin_files)


def batch_bin_to_json(levels_dir: str, output_dir: str) -> tuple:
    """
    批量转换所有 .bin 到 JSON
    保持目录结构，保留原始文件名
    """
    bin_files = find_bin_files(levels_dir)

    if not bin_files:
        print("❌ 没有找到任何 .bin 文件")
        return 0, 0

    success_count = 0
    fail_count = 0
    total = len(bin_files)

    for i, bin_path in enumerate(bin_files, 1):
        # 获取相对路径中的地图名
        rel_path = os.path.relpath(bin_path, levels_dir)
        parts = rel_path.replace('\\', '/').split('/')
        map_name = parts[0] if len(parts) > 1 else os.path.basename(os.path.dirname(bin_path))

        # 创建输出目录
        map_output_dir = os.path.join(output_dir, map_name)
        os.makedirs(map_output_dir, exist_ok=True)

        # 使用原始文件名
        original_filename = os.path.basename(bin_path)
        bin_output = os.path.join(map_output_dir, original_filename)
        json_output = os.path.join(map_output_dir, original_filename + ".json")

        # 复制原始 .bin 文件
        shutil.copy2(bin_path, bin_output)

        print(f"[{i}/{total}] {map_name}/{original_filename} ... ", end='', flush=True)

        try:
            result = bin_to_json(bin_path, translate=True)
            with open(json_output, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=1, ensure_ascii=False)
            print(f"✅")
            success_count += 1
        except Exception as e:
            print(f"❌ {e}")
            fail_count += 1
            # 删除失败的 bin 副本
            if os.path.exists(bin_output):
                os.remove(bin_output)

    return success_count, fail_count


def batch_json_to_bin(input_dir: str, output_dir: str) -> tuple:
    """批量将 JSON 转回 .bin，保留原始文件名"""
    json_files = []
    for dirpath, dirnames, filenames in os.walk(input_dir):
        for filename in filenames:
            if filename.endswith(".bin.json"):
                full_path = os.path.join(dirpath, filename)
                json_files.append(full_path)

    if not json_files:
        print("❌ 没有找到任何 .bin.json 文件")
        return 0, 0

    success_count = 0
    fail_count = 0
    total = len(json_files)

    for i, json_path in enumerate(json_files, 1):
        rel_path = os.path.relpath(json_path, input_dir)
        parts = rel_path.replace('\\', '/').split('/')
        map_name = parts[0] if len(parts) > 1 else "unknown"

        map_output_dir = os.path.join(output_dir, map_name)
        os.makedirs(map_output_dir, exist_ok=True)

        # 从 JSON 文件名还原 .bin 文件名
        json_filename = os.path.basename(json_path)
        # 去掉末尾的 .json 得到原始 .bin 文件名
        original_bin_name = json_filename[:-5]  # 去掉 ".json"
        bin_output = os.path.join(map_output_dir, original_bin_name)

        print(f"[{i}/{total}] {map_name}/{original_bin_name} ... ", end='', flush=True)

        try:
            json_to_bin(json_path, bin_output)
            print(f"✅")
            success_count += 1
        except Exception as e:
            print(f"❌ {e}")
            fail_count += 1

    return success_count, fail_count


# ============================================================
# 交互式菜单
# ============================================================

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')


def print_header():
    print("=" * 60)
    print("   Sky .bin 批量转换工具 作者:十二 原项目作者:Miau ")
    print("此项目网址:https://github.com/skyIshier/Sky-.bin-reader-python-zh")
    print("=" * 60)


def get_input_path(prompt, must_exist=True):
    while True:
        path = input(prompt).strip().strip('"').strip("'")
        if not path:
            print("❌ 路径不能为空\n")
            continue
        if must_exist and not os.path.exists(path):
            print(f"❌ 路径不存在: {path}\n")
            continue
        return path


def menu_batch_bin_to_json():
    clear_screen()
    print_header()
    print("\n📦 模式: 批量 .bin → .json\n")
    print("将 Levels 目录下所有 .bin 文件转换为 JSON")
    print("保持目录结构和原始文件名\n")

    levels_dir = get_input_path("请输入 Levels 目录路径: ")
    print(f"\n默认输出目录: {os.path.dirname(levels_dir)}/Levels_json")
    output_dir = input("自定义输出目录? (直接回车使用默认): ").strip().strip('"').strip("'")
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(levels_dir), "Levels_json")

    print(f"\n⏳ 开始扫描 {levels_dir} ...")
    bin_files = find_bin_files(levels_dir)
    print(f"找到 {len(bin_files)} 个 .bin 文件\n")

    if not bin_files:
        print("没有找到任何文件，请检查路径是否正确")
        input("\n按回车键返回主菜单...")
        return

    confirm = input(f"将转换 {len(bin_files)} 个文件并输出到 {output_dir}，确认? (y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        input("\n按回车键返回主菜单...")
        return

    print(f"\n⏳ 开始批量转换...\n")
    success, fail = batch_bin_to_json(levels_dir, output_dir)

    print(f"\n📊 转换完成:")
    print(f"  成功: {success} 个")
    print(f"  失败: {fail} 个")
    print(f"  输出目录: {output_dir}")

    input("\n按回车键返回主菜单...")


def menu_batch_json_to_bin():
    clear_screen()
    print_header()
    print("\n📦 模式: 批量 .json → .bin\n")
    print("将之前导出的 JSON 批量转回 .bin，保留原始文件名\n")

    input_dir = get_input_path("请输入 JSON 所在目录: ")
    print(f"\n默认输出目录: {os.path.dirname(input_dir)}/Levels_bin")
    output_dir = input("自定义输出目录? (直接回车使用默认): ").strip().strip('"').strip("'")
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(input_dir), "Levels_bin")

    print(f"\n⏳ 开始扫描 {input_dir} ...")

    json_files = []
    for dirpath, dirnames, filenames in os.walk(input_dir):
        for filename in filenames:
            if filename.endswith(".bin.json"):
                json_files.append(os.path.join(dirpath, filename))

    print(f"找到 {len(json_files)} 个 .bin.json 文件\n")

    if not json_files:
        print("没有找到任何文件")
        input("\n按回车键返回主菜单...")
        return

    confirm = input(f"将转换 {len(json_files)} 个文件并输出到 {output_dir}，确认? (y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消")
        input("\n按回车键返回主菜单...")
        return

    print(f"\n⏳ 开始批量转换...\n")
    success, fail = batch_json_to_bin(input_dir, output_dir)

    print(f"\n📊 转换完成:")
    print(f"  成功: {success} 个")
    print(f"  失败: {fail} 个")
    print(f"  输出目录: {output_dir}")

    input("\n按回车键返回主菜单...")


def main_menu():
    while True:
        clear_screen()
        print_header()
        print("\n请选择功能:")
        print("  1. 📥 批量 .bin → .json (整个 Levels 目录)")
        print("  2. 📤 批量 .json → .bin (整个 JSON 目录)")
        print("  0. 🚪 退出")
        print()
        c = input("请输入选项 [0-2]: ").strip()
        if c == '1':
            menu_batch_bin_to_json()
        elif c == '2':
            menu_batch_json_to_bin()
        elif c == '0':
            print("\n👋 再见!")
            sys.exit(0)
        else:
            print("❌ 无效选项，请重新输入")
            input("按回车键继续...")


def main():
    if len(sys.argv) > 1:
        levels_dir = sys.argv[1]
        output_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(levels_dir), "Levels_json")

        if not os.path.exists(levels_dir):
            print(f"❌ 目录不存在: {levels_dir}")
            return

        print(f"批量转换模式")
        print(f"源目录: {levels_dir}")
        print(f"输出目录: {output_dir}")
        print()
        success, fail = batch_bin_to_json(levels_dir, output_dir)
        print(f"\n完成: {success} 成功, {fail} 失败")
        return

    main_menu()


if __name__ == '__main__':
    main()
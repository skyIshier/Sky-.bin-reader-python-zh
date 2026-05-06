# Sky .bin 配置编辑器

> 基于 GitHub 开源项目 [Sky-.bin-reader](https://github.com/Miau0x1/Sky-.bin-reader) 的 C++ 源码完整移植为 Python 版本

---

## 项目简介

《光·遇》游戏配置文件（`.bin`）的读取、编辑、写入工具套件。支持将二进制 `.bin` 文件转换为可读可编辑的 JSON 格式，修改后再精确转换回 `.bin` 文件，保证字节级完全一致，游戏可正常读取。

---

## 核心特性

| 特性 | 说明 |
|------|------|
| **精确转换** | bin → json → bin 完整闭环，256,357 字节逐字节匹配验证通过 |
| **完整汉化** | 863 个类名 + 5059 个属性名 **100%** 中文翻译覆盖 |
| **批量处理** | 支持整个 Levels 目录下所有地图的一键批量转换 |
| **目录结构保持** | 输出自动按地图名分文件夹组织，保留原始文件名 |
| **文件对比** | 内置逐字节对比工具，验证转换正确性 |
| **跨平台** | 纯 Python 标准库实现，无需编译，Android/Linux/macOS/Windows 均可运行 |

---

## 文件结构



项目目录/

├── 单个转换.py          # 交互式单文件转换 (bin ↔ json)

├── 批量转换.py          # 批量转换整个 Levels 目录

├── 批量提取-字典用.py   # 扫描 JSON 目录，提取未翻译名称

├── zh字典.py            # 中文翻译表 (863 类名 + 5059 属性名)

└── 项目介绍.md          # 本文件

```

---

## 快速开始

### 1. 单个文件转换

```bash
python 单个转换.py
```

交互式菜单：

· 1 — .bin → .json（带完整中文翻译）
· 2 — .json → .bin
· 3 — 对比两个 .bin 文件

2. 批量转换整个 Levels 目录

```bash
python 批量转换.py
```

交互式菜单：

· 1 — 批量 .bin → .json（扫描整个目录，保持目录结构）
· 2 — 批量 .json → .bin（还原为原始格式）

3. 翻译覆盖率检查

```bash
python 批量提取-字典用.py <JSON目录路径>
```

---

JSON 结构说明

转换后的 JSON 包含两类数据：

classes（类定义元数据）

```json
"TransformObject（变换物体）": {
    "autoStart（自动开始）": {
        "propertyType": 0,       // 属性类型：0=数值 1=字符串 2=引用 3=数组
        "objectByteSize": 1,     // 数据大小（字节）
        "arrayIndex": 0          // 数组索引（0=非数组）
    }
}
```

BSTNodes（实际游戏数据）

```json
"BstNode_2093678655": {
    "TransformObject（变换物体）": {
        "autoStart（自动开始）": {
            "_raw_uint8": 0,        // 原始字节值（勿修改）
            "_value": false         // 可读值（修改这里）
        },
        "time（持续时间）": {
            "_raw_uint32": 1072064102,
            "_value": "1.7999999523162842"
        },
        "dragSound（拖拽音效）": ""   // 字符串直接修改
    }
}
```

---

修改指南

数据类型 修改方式 注意事项
布尔/数值 改 _value 字段 不要动 _raw_* 字段
字符串 直接改引号内文本 -
CLUMP引用 改 _clump_name 填目标节点名称
四维向量 改 _value 数组 格式 ["x","y","z","w"]

---

翻译覆盖

类型 已翻译 覆盖率
类名 863 100%
属性名 5059 100%
支持地图 104 全部主流地图

翻译表独立存放在 zh字典.py，可随时补充更新。

---

环境要求

· Python 3.6+
· 无需任何第三方库（仅使用标准库）

---

致谢

· 原作者：CodeAnalyzer53、TheSR、Miau0x1

· 2改作者:sky-shier-十二

· Python 移植及中文翻译：本项目

---

更新日期

2026年5月



此项目网址:https://github.com/skyIshier/Sky-.bin-reader-python-zh        "objectByteSize": 1,     // 数据大小（字节）
        "arrayIndex": 0          // 数组索引（0=非数组）
    }
}
```

BSTNodes（实际游戏数据）

```json
"BstNode_2093678655": {
    "TransformObject（变换物体）": {
        "autoStart（自动开始）": {
            "_raw_uint8": 0,        // 原始字节值（勿修改）
            "_value": false         // 可读值（修改这里）
        },
        "time（持续时间）": {
            "_raw_uint32": 1072064102,
            "_value": "1.7999999523162842"
        },
        "dragSound（拖拽音效）": ""   // 字符串直接修改
    }
}
```

---

修改指南

数据类型 修改方式 注意事项
布尔/数值 改 _value 字段 不要动 _raw_* 字段
字符串 直接改引号内文本 -
CLUMP引用 改 _clump_name 填目标节点名称
四维向量 改 _value 数组 格式 ["x","y","z","w"]

---

翻译覆盖

类型 已翻译 覆盖率
类名 863 100%
属性名 5059 100%
支持地图 104 全部主流地图

翻译表独立存放在 zh字典.py，可随时补充更新。

---

环境要求

· Python 3.6+
· 无需任何第三方库（仅使用标准库）

---

致谢

· 原作者：CodeAnalyzer53、TheSR、Miau0x1

· 2改作者:sky-shier-十二

· Python 移植及中文翻译：本项目

---

更新日期

2026年5月

此项目网址:https://github.com/skyIshier/Sky-.bin-reader-python-zh

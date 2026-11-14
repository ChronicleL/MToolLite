# MToolLite (RPG 游戏本地化与辅助增强工作台)

<div align="center">

![Python Version](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![PySide6](https://img.shields.io/badge/GUI-PySide6%20Qt6-41CD52?logo=qt&logoColor=white)
![Engines Supported](https://img.shields.io/badge/Engines-MV%20%7C%20MZ%20%7C%20XP%20%7C%20VX%20%7C%20VXAce%20%7C%202000%20%7C%20Wolf-blue)
![License](https://img.shields.io/badge/License-MIT-green)

**一个现代、轻量、高扩展的全功能独立 RPG 游戏本地化（文本提取、AI/机翻、无损挂载）与辅助工具**  
*零臃肿外部依赖 · 纯 Python 原生解析与注入 · 深色现代化 PySide6 界面 · 支持全系主流 RPG 引擎*

[特性亮点](#-核心特性) • [支持引擎](#-支持引擎矩阵) • [快速开始](#-快速开始) • [界面概览](#-界面预览) • [CLI 指南](#-命令行-cli-使用) • [架构说明](#-技术架构)

</div>

---

## ✨ 核心特性

- 🚀 **全格式无损挂载与还原**
  - **MV / MZ**：通过内存级插件链无损挂载翻译补丁，无需修改游戏原有 Data JSON，支持运行时捕获遗漏动态文本。
  - **XP / VX / VX Ace**：内置纯 Python 实现的 Ruby Marshal 4.8 序列化与 `.rgssad` / `.rgss3a` 解包，自动生成 `*.mtoollite.bak` 安全备份，一键无损还原。
  - **Wolf RPG Editor (ウディタ)**：完整支持 Wolf 2.x 与 Wolf 3.x / Pro 全系游戏，覆盖 `Evtext/*.txt` 剧本、`DataBase.project`、`.mps` 地图与 `.dat` 数据库，UTF-8 BOM 自动保真，秒级处理数万条对白。
  - **2000 / 2003**：支持经典 LDB 数据库与 LMU 地图事件文本解析。

- 🤖 **双模智能翻译流水线**
  - **AI 大模型模式**：深度适配 OpenAI 兼容 API（DeepSeek、OpenAI、本地 Ollama / LM Studio / NInfer 等），内置多线程并发、动态分批、失败自动降级重试与自定义角色/风格 Prompt。
  - **机器翻译模式**：内置 Google GTX（免费免 Key）、百度翻译等接口，支持一键测试通讯延迟。
  - **智能占位符防护盾 (Text Guard)**：自动加固并还原 `\C[x]`、`\V[x]`、`\N[x]`、`%s`、`\i[x]` 等游戏控制字符与转义标签，杜绝大模型破坏游戏脚本。
  - **专有名词术语表 (Glossary)**：支持导入专属 JSON 词库，翻译时强约束人物名、地名、招式统一。
  - **一键语言过滤与回退**：内置正则语言探测，一键标记并跳过汉字/既有译文，支持在词库表格中拖动多选、右键菜单退回未翻译或重新标记。

- ⚡ **内置快捷 F9 辅助修改器 (QoL Modifier)**
  - 针对 MV / MZ 游戏提供注入式修改悬浮窗（游戏中随时按 `F9` 呼出/隐藏）：
    - 角色锁血锁蓝（无敌模式）
    - 金币自定义（一键最大化）
    - 全物品/全武器/全防具获取
    - 任意全局开关 (Switches) 与变量 (Variables) 实时检索与修改
    - 自由穿墙 (No-Clip) 与移速倍增

- 🖥️ **现代深色双端体验**
  - **GUI 桌面端**：基于 PySide6 构建的流线型暗黑主题工作台，支持拖拽识别、实时双击加载历史、失效路径右键一键清理。
  - **CLI 命令行**：所有功能均具备对应 CLI 子命令，便于脚本自动化批处理。

---

## 🎮 支持引擎矩阵

| 游戏引擎 | 自动识别 | 文本提取 | 翻译挂载 | 一键还原 | F9 修改器 | 特别支持 |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **RPG Maker MZ** | ✅ | ✅ | ✅ (无损插件) | ✅ | ✅ | 运行时动态捕获 |
| **RPG Maker MV** | ✅ | ✅ | ✅ (无损插件) | ✅ | ✅ | 运行时动态捕获 |
| **RPG Maker VX Ace** | ✅ | ✅ | ✅ (自动备份) | ✅ | — | 原生 Marshal 4.8 / RGSS3A 解包 |
| **RPG Maker VX** | ✅ | ✅ | ✅ (自动备份) | ✅ | — | 原生 Marshal 4.8 / RGSS2A 解包 |
| **RPG Maker XP** | ✅ | ✅ | ✅ (自动备份) | ✅ | — | 原生 Marshal 4.8 / RGSSAD 解包 |
| **RPG Maker 2000/2003** | ✅ | ✅ | ✅ (自动备份) | ✅ | — | LDB / LMU 二进制解析 |
| **Wolf RPG Editor** | ✅ | ✅ | ✅ (自动备份) | ✅ | — | Wolf 2.x & 3.x/Pro、Evtext 剧本、Project 数据 |
| **Ren'Py / Tyrano** | ✅ | 规划中 | 规划中 | — | — | 基础引擎特征探测 |

---

## 📦 快速开始

### 1. 环境依赖
只需要 Python 3.9+ 以及 PySide6：
```bash
# 克隆仓库
git clone https://github.com/ChronicleL/MToolLite.git
cd MToolLite

# 安装唯一外部依赖
pip install PySide6
```

### 2. 启动图形化桌面端 (GUI)
```bash
# 启动 GUI 界面
python -m rpgm_tool gui

# 或者在 Windows 上双击运行:
start_mtoollite.bat
```

---

## 🖥️ 命令行 (CLI) 使用

工具提供统一的 CLI 入口，适用于批处理与无图形环境：

```bash
# 1. 识别游戏引擎类型
python -m rpgm_tool detect "D:\Games\MyGame"

# 2. 提取文本到 ManualTransFile.json
python -m rpgm_tool extract "D:\Games\MyGame"

# 3. 批量调用 AI/机翻接口翻译未译词条
python -m rpgm_tool translate "D:\Games\MyGame\ManualTransFile.json" \
  --base-url "https://api.deepseek.com/v1" \
  --api-key "sk-xxxx" \
  --model "deepseek-chat" \
  --batch-size 30 \
  --workers 4

# 4. 挂载翻译补丁 (支持开启遗漏文本捕获)
python -m rpgm_tool mount "D:\Games\MyGame" --capture

# 5. 一键卸载并完全还原游戏原版
python -m rpgm_tool unmount "D:\Games\MyGame"

# 6. 挂载 / 卸载 F9 游戏内修改器 (仅 MV/MZ)
python -m rpgm_tool cheat "D:\Games\MyGame"
python -m rpgm_tool uncheat "D:\Games\MyGame"
```

---

## 🏗️ 目录结构

```text
rpgm_tool/
├── __init__.py           # 包初始化入口
├── __main__.py           # python -m rpgm_tool 启动器
├── cli.py                # 命令行子命令路由与解析
├── gui.py                # PySide6 暗黑桌面工作台主逻辑
├── detector.py           # 全系 RPG 引擎精准识别模块
├── dictionary.py         # 字典加载、去重合并与状态维护
├── text_guard.py         # 转义符、控制字符防护盾
├── translator.py         # AI (OpenAI 协议) 与机器翻译多线程引擎
├── injector_mvmz.py      # MV/MZ 运行时翻译补丁注入与热重载
├── modifier_mvmz.py      # MV/MZ 游戏内 F9 QoL 悬浮修改器插件
├── extractor_mvmz.py     # MV/MZ 静态数据 JSON 提取与回写
├── extractor_rgss.py     # XP/VX/VXAce 文本提取与回写
├── extractor_wolf.py     # Wolf RPG 剧本与二进制文件全功能引擎
├── extractor_2k3.py      # 2000/2003 LDB/LMU 提取与回写
├── ruby_marshal.py       # 纯 Python 零依赖 Ruby Marshal 4.8 引擎
└── rgss_archive.py       # RGSSAD / RGSS2A / RGSS3A 解包提取器
tests/                    # 完整自动化单元测试用例集
```

---

## 🧪 自动化测试

项目内置完整的单元测试集，保障核心管道与二进制协议的稳定性：

```bash
python -m unittest discover -s tests -v
```

---

## 📄 开源协议

本项目采用 [MIT License](LICENSE) 授权开源。仅供学习交流、个人离线单机游戏本地化与无障碍辅助使用。

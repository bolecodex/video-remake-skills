# weibo-skills

基于 [changdu-skills](https://github.com/bolecodex/changdu-skills) 同类形态的 **weibo** CLI 与 Agent 技能包：对本地视频做 **分割 → 参考帧 + 提示词调用火山方舟 Seedance 2.0 重制分段 → 合并成片 → 效果验证**。

## 四大场景技能

| 技能 | 预设 | 说明 |
|------|------|------|
| [h2v-skill](skills/h2v-skill/SKILL.md) | `h2v` | 横屏素材转 9:16 竖屏构图 |
| [style-transfer-skill](skills/style-transfer-skill/SKILL.md) | `style_transfer` | AI 短剧转绘 / 换画风（水墨、赛博朋克、油画等） |
| [character-swap-skill](skills/character-swap-skill/SKILL.md) | `character_swap` | 换人向生成式重拍（非传统像素级换脸） |
| [viral-replica-skill](skills/viral-replica-skill/SKILL.md) | `viral_replica` | 爆款风格复刻（仅用于自有或已授权素材） |

## 安装

需要 **Python 3.10+**、**FFmpeg**（`ffmpeg`、`ffprobe` 在 PATH 中）。

```bash
cd /path/to/horizontal-to-vertical
bash scripts/setup.sh
source .venv/bin/activate
weibo version
```

或仅安装 CLI：

```bash
pip install -e "./weibo[dev]"
```

## 配置

```bash
# 必须
export WEIBO_ARK_API_KEY="你的火山方舟 API Key"

# 可选：使用控制台创建的 Seedance 推理接入点
export WEIBO_SEEDANCE_ENDPOINT="doubao-seedance-2-0-260128"

# TOS 上传（视频参考模式需要）
export VOLC_ACCESSKEY="火山引擎 Access Key"
export VOLC_SECRETKEY="火山引擎 Secret Key"
export WEIBO_TOS_BUCKET="TOS 桶名"
```

## 快速开始

```bash
# 一键横转竖
weibo run ./input.mp4 -o ./job_h2v --preset h2v \
  --prompt "竖屏安全区构图，主体居中偏上"

# 一键 AI 转绘
weibo run ./input.mp4 -o ./job_style --preset style_transfer \
  --prompt "水墨插画风格，保留表演与镜头节奏"

# 一键换人重拍
weibo run ./input.mp4 -o ./job_swap --preset character_swap \
  --prompt "将角色替换为银发精灵女战士，保持原片动作"

# 一键爆款复刻
weibo run ./input.mp4 -o ./job_viral --preset viral_replica \
  --prompt "复刻镜头语言和节奏，竖屏构图，画面饱满"
```

## 分步运行

```bash
weibo split ./input.mp4 -o ./job --preset h2v
weibo remake ./job/manifest.json --prompt "竖屏构图"
weibo merge ./job/manifest.json -o ./final.mp4
weibo verify ./job/manifest.json           # 生成 HTML 对比报告
weibo query --manifest ./job/manifest.json # 查看任务状态汇总
```

## Web 工作台

提供面向业务人员的可视化操作界面：

```bash
pip install fastapi uvicorn python-multipart
python server.py
# 浏览器打开 http://localhost:8899
```

功能：拖拽上传视频 → 选择预设模式 → 实时进度追踪 → 源视频与成片并排对比 → 下载成片 / 查看报告。自动处理真人审核拦截。

## CLI 命令

| 命令 | 说明 |
|------|------|
| `weibo run` | 一键全流程：分割 → 重制 → 合并 |
| `weibo split` | 分割视频 + 提取参考帧 + 上传 TOS + 生成 manifest |
| `weibo remake` | 逐段调用 Seedance 2.0 重制（支持恢复已有 task） |
| `weibo merge` | 合并重制片段为成片 |
| `weibo asset-register` | 将视频片段注册为 Assets（解决真人审核拦截） |
| `weibo query` | 查询任务状态（单任务或 manifest 汇总） |
| `weibo verify` | 生成 HTML 效果对比报告 |
| `weibo version` | 显示版本号 |

## 仓库结构

```
video-remake-skills/
├── weibo/                          # Python CLI 包
│   ├── pyproject.toml
│   └── src/weibo/
│       ├── cli/main.py             # Typer 入口
│       ├── commands/
│       │   ├── split.py            # weibo split
│       │   ├── remake.py           # weibo remake
│       │   ├── merge.py            # weibo merge
│       │   ├── run.py              # weibo run
│       │   ├── query.py            # weibo query
│       │   ├── verify.py           # weibo verify
│       │   └── asset.py            # weibo asset-register
│       ├── client/                 # Ark API 客户端
│       ├── models/                 # 请求/响应模型
│       ├── config.py               # 配置 + 预设
│       ├── manifest.py             # 任务清单
│       ├── assets.py               # Assets API 客户端（V4 签名鉴权）
│       ├── upload.py               # TOS 上传
│       └── utils.py                # FFmpeg 工具
├── skills/
│   ├── h2v-skill/                  # 横转竖
│   ├── style-transfer-skill/       # AI 转绘
│   ├── character-swap-skill/       # 换人重拍
│   └── viral-replica-skill/        # 爆款复刻
├── server.py                       # FastAPI Web 工作台
├── frontend.html                   # 前端页面
├── scripts/setup.sh
├── .env.example
└── README.md
```

## 音频说明

默认合并阶段以 FFmpeg concat 拼接各段视频。若需保留原片音轨，使用 `--keep-audio` 参数。

## License

MIT，见 [LICENSE](LICENSE)。

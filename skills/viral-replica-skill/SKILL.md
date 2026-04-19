---
name: viral-replica-skill
description: 使用 weibo CLI 复刻爆款视频的镜头语言和视觉风格，以 9:16 竖屏输出。仅用于自有或已授权素材。
homepage: https://www.volcengine.com/product/ark
metadata: {}
---

# 爆款风格复刻（Viral Replica）

复刻爆款视频的镜头语言、节奏和视觉风格，以 9:16 竖屏输出，适用于自有素材的风格化再创作。

**重要**：本技能仅用于自有或已获授权的素材，请勿用于未经授权的内容。

## 前置条件

```bash
test -n "$WEIBO_ARK_API_KEY" || test -n "$ARK_API_KEY"
test -n "$VOLC_ACCESSKEY" && test -n "$VOLC_SECRETKEY" && test -n "$WEIBO_TOS_BUCKET"
which ffmpeg && which ffprobe
weibo version
```

TOS 配置（`.env` 中）：
- `VOLC_ACCESSKEY` — 火山引擎 Access Key
- `VOLC_SECRETKEY` — 火山引擎 Secret Key
- `WEIBO_TOS_BUCKET` — TOS 桶名
- `WEIBO_TOS_ENDPOINT` — TOS 端点（默认 `tos-cn-beijing.volces.com`）

**重要**：视频参考模式**必须配置 TOS**，因为需要将分段视频上传获取公网 URL。含真人的视频可能触发安全审核，`weibo run --auto-asset`（默认开启）会自动注册 Asset 并重试。

## 一键运行

```bash
weibo run ./reference_video.mp4 -o ./job_viral \
  --preset viral_replica \
  --prompt "复刻此视频的镜头语言和节奏，竖屏构图，画面饱满有冲击力"
```

## 分步执行（含 Asset 注册）

```bash
# 1. 分割参考视频 + 上传 TOS
weibo split ./reference_video.mp4 -o ./job_viral --preset viral_replica

# 2. 注册 Asset（防真人审核拦截，推荐始终执行）
weibo asset-register ./job_viral/manifest.json -g viral-project

# 3. 风格复刻重制
weibo remake ./job_viral/manifest.json \
  --prompt "复刻原片的运镜节奏和视觉冲击力，9:16竖屏，主体居中偏上，色彩饱满"

# 4. 合并（--keep-audio 保留原声）
weibo merge ./job_viral/manifest.json -o ./final_viral.mp4 --keep-audio

# 5. 验证
weibo verify ./job_viral/manifest.json
```

## Prompt 编写指南

爆款复刻的核心是**节奏和视觉冲击力**：

1. **镜头语言**：描述要保留的运镜方式（推拉摇移跟、特写切换节奏）
2. **视觉风格**：色彩饱和度、光影对比、画面构图
3. **竖屏适配**：主体居中偏上，信息密度集中在安全区
4. **节奏感**：保留原片的剪辑节奏和情绪起伏

### 好的 prompt 示例

```
复刻原片的镜头语言、节奏与视觉风格，以 9:16 竖屏构图输出，
主体居中偏上，画面饱满有冲击力。色彩高饱和，光影对比强烈，
保留快速剪辑节奏和运镜张力。
```

### 分段差异化

不同段落可能需要不同的视觉侧重：

```bash
# 开场冲击段
echo "电影感开场，大特写，浅景深，色彩浓郁，竖屏居中构图" > ./job_viral/prompts/000.txt

# 节奏高潮段
echo "快速剪辑节奏，动态运镜，画面饱满，主体始终居中" > ./job_viral/prompts/005.txt

weibo remake ./job_viral/manifest.json
```

## 效果验证

```bash
weibo verify ./job_viral/manifest.json -o ./job_viral/report.html
```

重点检查：镜头节奏是否保留、竖屏构图是否合理、视觉冲击力是否达标。

## 约束

- Seedance 2.0 单段视频最长 15 秒
- 输出比例固定为 9:16
- 仅用于自有或已获授权的素材
- 复刻的是风格和节奏，而非逐帧复制

---
name: style-transfer-skill
description: 使用 weibo CLI 对视频进行 AI 风格转绘，将真人实拍转换为水墨、赛博朋克、油画等艺术风格。通过 Seedance 2.0 视频参考模式保持原片动作、镜头运动、节奏和音频不变，仅改变视觉风格。
homepage: https://www.volcengine.com/product/ark
metadata: {}
---

# AI 短剧转绘（Style Transfer）

将真人实拍视频转绘为指定艺术风格，**保留原片的全部动作、表演、镜头运动、叙事节奏和音频**，仅改变视觉风格。

核心原理：将源视频片段上传 TOS 获取 URL，以 `video_url` 视频参考模式调用 Seedance 2.0，模型基于原视频内容和动态重新生成目标风格的版本，最后 mux 回原始音轨。

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

**重要**：视频参考模式**必须配置 TOS**，因为需要将分段视频上传获取公网 URL。

## 一键运行

```bash
weibo run ./input.mp4 -o ./job_style \
  --preset style_transfer \
  --prompt "赛博朋克风格，霓虹灯光，暗色调，科幻感" \
  --keep-audio
```

默认行为：
1. 按 15s 分割视频
2. 每段自动上传 TOS
3. 以源视频 URL 为参考调用 Seedance 2.0（视频参考模式），用 prompt 指定目标风格
4. 合并成片并 mux 回原始音轨

## 分步执行

```bash
# 1. 分割 + 上传 TOS（默认 15s/段）
weibo split ./input.mp4 -o ./job_style --preset style_transfer

# 2. 逐段重制（自动使用视频参考，保留原片内容）
weibo remake ./job_style/manifest.json \
  --prompt "赛博朋克风格，霓虹灯光，暗色调，科幻感"

# 3. 合并成片 + mux 原音轨
weibo merge ./job_style/manifest.json -o ./final_style.mp4 --keep-audio

# 4. 效果验证
weibo verify ./job_style/manifest.json
```

### 保持原视频比例

`style_transfer` 预设默认输出 16:9，如果原视频是其他比例（如 9:16 竖屏），需要在 remake 时覆盖：

```bash
weibo remake ./job_style/manifest.json \
  --prompt "赛博朋克风格，霓虹灯光，暗色调，科幻感" \
  --ratio 9:16
```

### 逐段自定义 prompt

在任务目录 `prompts/` 下创建 `000.txt`、`001.txt` 等文件，可单独覆盖某段的 prompt：

```bash
echo "特写镜头，赛博朋克风格，面部霓虹光效" > ./job_style/prompts/003.txt
weibo remake ./job_style/manifest.json
```

## 支持的画风模板

以下 prompt 可直接使用或组合：

| 画风 | Prompt 关键词 |
|------|-------------|
| 水墨国风 | `水墨插画风格，写意笔触，留白意境，宣纸质感` |
| 赛博朋克 | `赛博朋克风格，霓虹灯光，暗色调，科幻感` |
| 油画 | `印象派油画风格，厚重笔触，色彩鲜艳` |
| 吉卜力 | `吉卜力动画风格，柔和色彩，手绘质感，温暖光线` |
| 漫画 | `日系赛璐璐动漫风格，线稿平涂，鲜明配色` |
| 像素风 | `像素艺术风格，复古游戏画面，8bit色彩` |
| 素描 | `铅笔素描风格，黑白灰调，细腻线条` |

## Prompt 编写指南

转绘 prompt 的核心是**描述目标风格而非内容**，内容由视频参考传达：

1. **风格描述**：明确画风名称 + 质感 + 色调
2. **保留声明**：明确要保留的原片元素（表演、镜头运动、场景布局）
3. **一致性**：同一项目所有段使用相同风格描述，避免段间风格跳变
4. **避免内容描述**：不要描述"一个人走在路上"之类的内容，这些由视频参考提供

### 好的 prompt 示例

```
保持原片镜头运动与表演节奏，将画风转换为水墨插画风格，
写意笔触，留白意境，宣纸质感。角色造型保持原片轮廓，
场景氛围与原片一致，色调偏青灰。
```

## 回退到图片参考模式

如果 TOS 未配置或需要强制使用首帧图片参考（会丢失动态信息）：

```bash
weibo split ./input.mp4 -o ./job_style --preset style_transfer --no-upload
weibo remake ./job_style/manifest.json --use-image \
  --prompt "赛博朋克风格，霓虹灯光，暗色调，科幻感"
```

**注意**：图片参考模式仅以首帧静态图为输入，无法保留原片的动作和镜头运动，效果会大打折扣。

## 效果验证

```bash
weibo verify ./job_style/manifest.json -o ./job_style/report.html
```

生成 HTML 对比报告，逐段并排展示源视频帧与重制帧。重点检查：
- 画风是否统一
- 角色动作是否与原片一致
- 镜头运动节奏是否保留
- 音频是否正常

## 约束

- Seedance 2.0 参考视频：2~15 秒，最大 50MB
- 默认分段 15 秒（Seedance 上限），可用 `-s` 调整
- 视频参考模式需要 TOS 配置，否则自动回退到图片参考
- 风格一致性取决于 prompt 的稳定性，建议所有段使用相同 prompt
- `--keep-audio` 合并时 mux 原始音轨，保留背景音乐和对白
- 转绘不应改变原片比例，如果原片非 16:9 需手动传入 `--ratio`

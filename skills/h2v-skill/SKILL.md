---
name: h2v-skill
description: 使用 weibo CLI 将横屏视频转换为 9:16 竖屏视频。分割源视频 → 上传 TOS → 以源视频为参考调用 Seedance 2.0 重制 → mux 原音频合并成片。
homepage: https://www.volcengine.com/product/ark
metadata: {}
---

# 横屏转竖屏（H2V）— 视频参考模式

将 16:9 横屏视频转换为 9:16 竖屏视频，**保留原片的全部动作、表演、镜头运动、节奏和音频**。

核心原理：将源视频片段上传 TOS 获取 URL，以 `video_url` 参考模式（而非首帧图片）调用 Seedance 2.0，模型基于原视频内容生成竖屏版本，最后 mux 回原始音轨。

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

## 一键运行

```bash
weibo run ./input.mp4 -o ./job_h2v --preset h2v
```

默认行为：
1. 按 15s 分割视频
2. 每段自动上传 TOS
3. 以源视频 URL 为参考 + 9:16 比例调用 Seedance 2.0
4. 合并成片并 mux 回原始音轨

## 分步执行

```bash
# 1. 分割 + 上传 TOS（默认 15s/段）
weibo split ./input.mp4 -o ./job_h2v --preset h2v

# 2. 逐段重制为 9:16 竖屏（自动使用视频参考）
weibo remake ./job_h2v/manifest.json

# 3. 合并成片（默认 mux 原音轨）
weibo merge ./job_h2v/manifest.json -o ./final_h2v.mp4 --keep-audio

# 4. 效果验证
weibo verify ./job_h2v/manifest.json
```

## Prompt 编写指南

视频参考模式下，prompt 应强调**保持原片内容不变，仅调整比例**：

### 好的 prompt 示例

```
以 9:16 竖屏比例重新构图，严格保持原视频的全部动作、表演、
镜头运动和节奏不变，仅调整画面构图比例，主体居中。
```

### 逐段自定义

在任务目录 `prompts/` 下创建 `000.txt`、`001.txt` 等文件，可单独覆盖某段的 prompt：

```bash
echo "特写镜头，人物面部居中，保持原片动作和节奏" > ./job_h2v/prompts/003.txt
weibo remake ./job_h2v/manifest.json
```

## 回退到图片参考模式

如果 TOS 未配置或需要强制使用首帧图片参考：

```bash
# split 时跳过上传
weibo split ./input.mp4 -o ./job_h2v --preset h2v --no-upload

# remake 时强制图片模式
weibo remake ./job_h2v/manifest.json --use-image
```

## 效果验证

```bash
weibo verify ./job_h2v/manifest.json -o ./job_h2v/report.html
```

生成 HTML 对比报告，逐段并排展示源视频帧与重制帧。

## 约束

- Seedance 2.0 参考视频：2~15 秒，最大 50MB
- 输出比例固定为 9:16
- 需要配置 TOS 才能使用视频参考模式
- 建议先用 1-2 段测试效果，满意后再全量运行

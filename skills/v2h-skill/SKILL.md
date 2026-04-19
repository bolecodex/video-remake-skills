---
name: v2h-skill
description: 使用 weibo CLI 将 9:16 竖屏视频转换为 16:9 横屏，保留原片全部动作、表演与镜头运动。
homepage: https://www.volcengine.com/product/ark
metadata: {}
---

# 竖屏转横屏（V2H）

将 9:16 竖屏视频智能重构为 16:9 横屏画面。Seedance 2.0 会利用横向空间扩展场景，保持主体在视觉中心，适用于将短视频素材转为横屏发布。

## 前置条件

```bash
test -n "$WEIBO_ARK_API_KEY" || test -n "$ARK_API_KEY"
test -n "$VOLC_ACCESSKEY" && test -n "$VOLC_SECRETKEY" && test -n "$WEIBO_TOS_BUCKET"
which ffmpeg && which ffprobe
weibo version
```

## 一键运行

```bash
weibo run ./vertical_video.mp4 -o ./job_v2h --preset v2h
```

## 分步执行

```bash
# 1. 分割 + 上传
weibo split ./vertical_video.mp4 -o ./job_v2h --preset v2h

# 2. 注册 Asset（含真人时推荐）
weibo asset-register ./job_v2h/manifest.json -g v2h-project

# 3. 逐段重制
weibo remake ./job_v2h/manifest.json

# 4. 合并（--keep-audio 保留原声）
weibo merge ./job_v2h/manifest.json -o ./final_v2h.mp4 --keep-audio

# 5. 验证
weibo verify ./job_v2h/manifest.json
```

## Prompt 编写指南

V2H 的核心是**画面扩展而非裁切**：

1. **空间利用**：利用横向空间展示更宽广的场景，而非简单拉伸
2. **主体居中**：主体保持在画面视觉中心
3. **动作保留**：所有动作、表情和交互关系与原片完全一致
4. **场景连贯**：扩展的横向区域应自然融入原有场景

### 好的 prompt 示例

```
以 16:9 横屏重新构图，利用两侧空间展现完整场景环境，
主体居中，严格保持原片的动作、表演、镜头运动和节奏不变。
```

## 约束

- Seedance 2.0 单段最长 15 秒
- 输出比例固定为 16:9（1280×720）
- 横向扩展的区域由 AI 生成，可能与真实场景有差异
- 人物密集镜头的扩展效果优于大场景

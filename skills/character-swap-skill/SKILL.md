---
name: character-swap-skill
description: 使用 weibo CLI 对视频进行换人向生成式重拍，将原片角色替换为指定形象，保留表演和镜头。
homepage: https://www.volcengine.com/product/ark
metadata: {}
---

# 换人向生成式重拍（Character Swap）

将原片中的角色替换为全新形象，保留原片的表演动作、镜头运动和场景布局。这不是传统像素级换脸，而是基于 Seedance 2.0 的生成式重拍。

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
weibo run ./input.mp4 -o ./job_swap \
  --preset character_swap \
  --prompt "将角色替换为：银发精灵女战士，尖耳，蓝色铠甲，保持原片动作和表情"
```

若含真人镜头被审核拦截，`--auto-asset` 会自动注册后重试。也可手动分步处理：

## 分步执行（含 Asset 注册）

```bash
# 1. 分割 + 上传 TOS
weibo split ./input.mp4 -o ./job_swap --preset character_swap

# 2. 注册 Asset（防真人审核拦截，推荐始终执行）
weibo asset-register ./job_swap/manifest.json -g swap-project

# 3. 逐段重拍
weibo remake ./job_swap/manifest.json \
  --prompt "将主角替换为金发骑士，全身板甲，红色披风，保持原片动作表情和镜头运动"

# 4. 合并（--keep-audio 保留原声）
weibo merge ./job_swap/manifest.json -o ./final_swap.mp4 --keep-audio

# 5. 验证
weibo verify ./job_swap/manifest.json
```

## Prompt 编写指南

换人重拍的核心是**角色锚定**，prompt 必须精确描述新角色外观：

1. **角色描述**：详细描述新角色的固定外貌特征（发型、发色、服装、配饰、体型）
2. **动作保留**：明确声明保持原片的动作、表情、交互关系
3. **场景保留**：明确声明保持原片的场景和镜头运动
4. **一致性锚定**：所有段使用完全相同的角色描述，避免段间角色外貌跳变

### 角色描述模板

```
【角色锚定】银发及腰，尖耳，琥珀色瞳孔，蓝色轻甲覆盖肩胸，
腰系银色腰带，深棕色长靴，左手持弓，身材修长挺拔。

【动作保留】保持原片所有角色的动作、表情和交互关系不变。

【场景保留】保持原片场景布局和镜头运动。
```

### 多角色替换

通过逐段 prompt 覆盖处理不同角色出场的段落：

```bash
# 主角出场段
echo "【角色A】银发精灵女战士... 保持原片动作" > ./job_swap/prompts/000.txt

# 配角出场段
echo "【角色A】银发精灵... 【角色B】矮人铁匠... 保持原片动作" > ./job_swap/prompts/003.txt

weibo remake ./job_swap/manifest.json
```

## 效果验证

```bash
weibo verify ./job_swap/manifest.json -o ./job_swap/report.html
```

重点检查：角色外貌是否段间一致、动作是否保留、场景是否完整。

## 约束

- Seedance 2.0 单段视频最长 15 秒
- 生成式重拍非像素级替换，角色动作可能有细微差异
- 角色一致性取决于 prompt 中角色描述的稳定性和精确度
- 建议先用 1 段测试角色形象是否满意，再全量运行

# Chinese TV ad/program segmentation — implementation task

## 状态 / Status

**任务规格与独立交付检查工具，尚无分割算法实现或外部代码交付。私有数据集与独立盲测：NOT EVALUATED。**

**Task specification and independent artifact checks. No segmentation implementation or external code delivery is included. Private-set and held-out evaluation: NOT EVALUATED.**

本仓库用于向 IMD Agent 或其他实现者交接一个独立的 Python 算法组件。完整要求见 [TASK.txt](TASK.txt)。仓库内的目标、接口与测试要求描述待完成工作，不代表功能已经实现。

This repository hands off an independent Python component to an IMD agent or another implementer. [TASK.txt](TASK.txt) is the implementation contract. Requirements describe work to be completed, not existing capabilities.

## 需要实现 / What to build

输入本地视频或预提取的帧、PTS、ASR 和粗分段，自动发现独立广告、节目、节目预告与频道宣传单元，判断身份和类别，并将边界定位到有证据支持的原生帧。保留同类相邻单元和短单元，合并同一单元内部镜头变化；证据不足输出 `unknown`。

Accept local video or pre-extracted frames, PTS, ASR and coarse segments. Discover independent advertising and program units, classify their content, and locate boundaries using supported native-frame evidence. Preserve short and adjacent same-class units; merge shot changes within one unit; emit `unknown` when evidence is insufficient.

交付可运行的 Python package/CLI、可注入的语义 provider、可配置的多模态 HTTP adapter、显式 replay provider、合成样例生成器、有效测试与使用说明。输出包括 `raw.jsonl`、`floor.jsonl`、`candidate_manifest.json`、证据决策账本及运行/费用/失败记录。详细字段、时间坐标和业务定义以 TASK.txt 为准。

Deliver a working Python package/CLI, injectable semantic provider, configurable multimodal HTTP adapter, explicit replay provider, synthetic fixture generator, meaningful tests and usage documentation. Produce `raw.jsonl`, `floor.jsonl`, `candidate_manifest.json`, an evidence/decision ledger, and runtime/cost/failure records. TASK.txt defines fields, time coordinates and business rules.

## Agent 接入 / Implementer handoff

1. 阅读 TASK.txt，在被分配的工作区完成独立实现；不要止于方案、空项目或报告。建议组织为 `adseg_auto/`、`tests/`、`examples/`。
2. 提供不依赖网络、GPU、私有数据或媒体工具的合成离线演示。下述命令仅是目标接口示例，当前仓库尚不能运行：`python -m adseg_auto --manifest INPUT --output NEW_DIR --provider replay`。
3. 默认不发生付费调用。Live provider 的 endpoint、model、credential 和 budget 由未来运行者在自己的环境配置；不要向任务发起者索取凭据。
4. 实际运行测试和一次全新离线演示，提交源码、执行过的命令、观察到的结果、接入步骤和局限。无法直接 push 时仍需完成代码包或可应用 patch，由平台或发起者发布；不要因缺少 GitHub 凭据停止实现或创建另一仓库。

1. Read TASK.txt and implement the component in the assigned workspace. A plan, empty scaffold or report alone is incomplete. Suggested layout: `adseg_auto/`, `tests/`, `examples/`.
2. Provide a synthetic offline demo requiring no network, GPU, private data or media binaries. The command above is a target interface example; it does not run in this seed repository yet.
3. Make no paid calls by default. Future operators configure their own live endpoint, model, credential and budget. Do not ask the requester for credentials.
4. Run meaningful tests and one fresh offline demo. Deliver source, commands actually run, observed results, integration steps and limitations. If push is unavailable, return a complete code bundle or applicable patch for publication by the platform/requester. Do not block implementation on GitHub credentials or create another repository.

## 数据和验收范围 / Data and evaluation scope

本仓库不提供或授权访问既有私有源码、视频、证据帧、转写、GT、预测结果或凭据。只允许使用实现者生成的合成样例进行随包演示。不要从本地环境发现、复制或上传其他材料。

Existing private source code, videos, evidence frames, transcripts, ground truth, predictions and credentials are neither supplied nor authorized for access. Use implementer-generated synthetic examples for the bundled demo. Do not discover, copy or upload other materials from the environment.

真实集目标为按频道及类别统计：类型正确率至少 95%、拆分正确率至少 80%、端点容差不超过 1 秒；raw 与 floor 分别报告。合成测试或平台结构验收不能证明这些准确率。真实素材集、冻结评分器和盲测由发起者在本地独立验收，本阶段统一标记 **NOT EVALUATED**。

Real-set targets are per channel and class: type correctness at least 95%, split correctness at least 80%, and endpoint tolerance at most one second, with raw and floor reported separately. Synthetic tests and platform structural acceptance do not demonstrate these accuracy targets. The requester performs private-data, frozen-scorer and held-out evaluation locally; all such metrics remain **NOT EVALUATED** at this stage.

## 文件与检查 / Contents and checks

- `README.md`: 当前状态、接入方法与交付边界 / status, handoff and delivery scope.
- `TASK.txt`: 完整实现规格 / full implementation specification.

- `acceptance/`: 独立、只读的结构验收工具与 16 项测试 / independent read-only artifact verifier and 16 tests.

```sh
python3 -B -m unittest discover -s acceptance -p 'test_*.py' -v
```

检查工具的输入、用法与局限见 [acceptance/README.md](acceptance/README.md)。它只检查文件合同，不证明分割算法或真实集准确率。

See [acceptance/README.md](acceptance/README.md) for usage and limits. Passing structural checks does not demonstrate segmentation or real-set accuracy.

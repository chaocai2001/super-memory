# Changelog

本项目的重要变更记录在此文件中。

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added

- `supermemory pending` 新增 `--idle-seconds N`：只提取至少 N 秒未更新的会话，并在 JSON 输出中通过 `deferred_sessions` 返回因活跃而推迟的会话数。
- macOS 定时消化改为每 5 分钟本地检查，默认仅在会话静默 10 分钟后启动后台蒸馏；常规后台任务每轮最多处理 5 个会话。
- macOS 使用 `RunAtLoad` 在登录或任务加载后补跑，使用 `StartCalendarInterval` 在睡眠唤醒后合并补跑，覆盖笔记本关机和合盖场景。
- 定时与手工 `digest.sh` 共用单实例锁，避免多个 worker 并发修改 wiki、会话游标和日志。
- Linux 文档增加周期 cron 与 `@reboot` 配置示例，支持定时检查和重启后补跑。

### Changed

- 普通任务开始时只自动召回记忆，不再在主会话中顺带消化积压；显式「消化积压 / 沉淀记忆」仍可按需执行。
- 显式「记住 / 纠正」继续立即写入 wiki；普通自动记忆改为静默后最终一致，通常延迟约 10–15 分钟。
- 四个 harness 的后台 worker 均使用统一的静默期参数，活跃会话不会被提前蒸馏。
- 手工执行 `digest.sh` 默认仍立即处理积压，并保留原有每轮最多 50 个会话的默认值。
- 安装或重新加载 launchd 时可能立即执行一次常规补跑，最多处理 5 个会话；大规模首次历史回灌仍需用户确认。

### Fixed

- 活跃会话因静默期过滤而推迟时，不再推进其增量游标。
- opencode SQLite 按每个 session 的 `time_updated` 独立判断静默状态，避免一个活跃会话阻塞其他会话。
- `apply` 遇到无效 ops 时不再确认对应会话或推进游标，失败批次可由后续任务重试。
- 空积压和锁竞争均直接退出，避免不必要的 worker 启动及模型 token 消耗。

### Documentation

- 更新中英文 README 的架构图、安装流程、CLI 参数、调度配置、延迟语义和故障排查说明。
- 更新 Codex、opencode、Kimi Code 和 Claude Code 的全局协议与 skill，明确后台自动消化和交互按需消化的边界。

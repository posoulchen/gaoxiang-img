# gaoxiang-img

高项 100 天学习计划的内容仓库，同时承担两件事：

1. **图片托管**：`img/` 下是每天的知识地图 / 记忆卡，钉钉消息通过 `ghproxy.net` 加速访问这些图片；
2. **云端定时发送**：`.github/workflows/daily.yml` 每天 23:20 UTC（北京时间 07:20）自动运行 `scripts/cloud_send.py`，把当天的学习资料推到钉钉。电脑关机也不影响。

## 目录

| 路径 | 内容 |
|---|---|
| `days/day-001.md … day-100.md` | 每日文字版资料 |
| `days/fig/*.json` | 知识地图/记忆卡的结构化数据 |
| `img/*.png` | 200 张配图 |
| `plan/plan.json` | 100 天的日期、章节、考点 |
| `scripts/cloud_send.py` | 云端发送器 |
| `state/sent-YYYY-MM-DD.txt` | 发送记录（电脑端与云端共用，避免重复） |

## 配置

仓库 Settings → Secrets and variables → Actions 里需要两个 secret：

- `DINGTALK_WEBHOOK`
- `DINGTALK_SECRET`

## 手动测试

Actions → `gaoxiang-daily` → Run workflow：

- `ping=true`：只发一条连通性测试；
- `day=3&dry_run=true`：只打印第 3 天的消息摘要，不发送。

> 仓库里的 `state/` 由工作流写入，不要手工改。

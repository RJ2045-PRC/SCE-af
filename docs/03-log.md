# 版本日志

## v0.1.0

脚手架：本机网页 + 源码 zip（复制本机 `.venv`）。第一条路径：气泡图切块识图，汇总 JSON。

| 变更 | 用户侧结果 | 实现要点 |
| --- | --- | --- |
| 本地网页 | 打开 `http://127.0.0.1:2054/` 可见版本号 | 标准库 HTTP；`/api/health` / `/api/version` |
| 切块识图 | 导入 PDF 后核对三块 JSON，可手改编号并下载 | 红框裁切；DeepSeek 只看小图；公差用 `limits.py` 解析 |
| 双系统 zip | Mac / Windows 各打带该机 `.venv` 的源码包 | `release/pack.py` |

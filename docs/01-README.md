# SCE-af v0.2.3

本仓库说明：结构、实现、开发用法。给同事的安装与发布包见仓库根 [`README.md`](../README.md)。

业务规则只认 [`04-rule.md`](04-rule.md)。需求进 [`02-update_backlog.md`](02-update_backlog.md)。已发布变更见 [`03-log.md`](03-log.md)。流程图见 [`05-flow.md`](05-flow.md)。

## 1. 定位与边界

**本机网页工具。** 绑定非 loopback 会把本机数据暴露在局域网，不要当生产服务。

| 做 | 不做 |
| --- | --- |
| 把气泡图拆开识图，汇总成 JSON，再导出 SIP / 控制计划 / 检查清单 / 特殊特性清单 / 全尺寸 FAI | 不当局域网服务；不把整份 PDF 一次送进模型；不读字典、不画工序 |
| `http://127.0.0.1:2054/` | 远程多用户服务 |

入口只有 `run.py`。

```bash
python3 setup_env.py
.venv/bin/python run.py
```

自定义端口：`.venv/bin/python run.py --port 8765`。必须用 `.venv` 里的 Python。

DeepSeek 密钥放项目根 `api-key.md`，已被 gitignore。

## 2. 仓库地图

```text
  run.py                 网页入口
  setup_env.py           首次装运行时依赖
  api-key.md             本机密钥（不进 git）
  sce_af/                领域包 + HTTP
    __init__.py          __version__ 唯一来源
    app.py               标准库 HTTP
    jobs.py              后台任务
    pipeline.py          切图 → 识图 → 汇总
    export_docs.py       JSON 填 SIP / QCP / 检查清单 / 特殊特性清单 / FAI
    slice.py / detect.py 页分类与红色气泡
    vision.py            DeepSeek 小图请求
    limits.py            公差解析
    ids.py               模号 / 料号
    paths.py
    open_page.py
  web/                   零构建前端
  data/template/         SIP、QCP、检查清单、特殊特性清单
  tests/
  release/               pack.py（复制本机 .venv）
  docs/                  01～05、GitHub Pages 静态 Demo
  output/jobs/           每次任务的 PDF、JSON 与导出 zip
```

当前怎么跑见 [`05-flow.md`](05-flow.md)。

打包不带 `docs/`、`tests/`、`AGENTS.md`。

## 3. 实现分层

`web/` 只打 API。领域逻辑在 `sce_af/`，不 import `http.server`。版本只出自 `__init__.__version__`，前端读 `/api/version`。

主流程不读 PDF。`plan_pdf` 切出 title / notes / bubble 任务，每块一张 PNG；`vision.complete_vision` 只看这一块；`merge_job` 解析公差并列出问题。核对后 `export_docs` 复制模板填格。

本地工作区新增实时流程图：`web/flow.js` 显示逐页缩略图、实际裁切区域和三路任务计数；数字跟随后端快照，页面切换与进度条在前端缓冲，不阻塞识图。`plan_pdf` 回调保存页面预览与归一化坐标，`run_pipeline` 上报各路排队、处理中、成功、失败数；`jobs` 的 `flow` 字段保留这些状态，最终 `result.json` 不包含动画数据。切片失败列入问题，其余切片继续。页面预览只在本机展示，不发送给模型。当前改动待随下一版本发布。

## 4. 测试与发布

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest tests -q
```

Mac：`release/打包.command` → `SCE-af v{版本}.zip`。  
Windows 虚拟机：`release/pack.bat` → `SCE-af v{版本}-win64.zip`。详见 skill `pp-scaffold` 的 release.md。

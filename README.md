# SCE-af v0.2.3

把气泡图拆开识图，汇总成 JSON，再导出 SIP、控制计划、检查清单、特殊特性清单和全尺寸 FAI。入口只有本地网页，不提供命令行。不做：不当局域网服务；不把整份 PDF 一次送进模型。规则见 [`docs/04-rule.md`](docs/04-rule.md)。

当前版本：**v0.2.3**。

静态核对 Demo（不必克隆或本机启动）：[https://rj2045-prc.github.io/SCE-af/](https://rj2045-prc.github.io/SCE-af/)

## 快速启动

第一次：

```bash
python3 setup_env.py
```

把 DeepSeek 密钥写成项目根的 `api-key.md`（不要提交）。以后双击 `打开SCE-af.command`，或：

```bash
.venv/bin/python run.py
```

浏览器打开 `http://127.0.0.1:2054/`。选择气泡图 PDF，等识图结束，核对基本信息、气泡表和技术要求，需要时手改模号/料号，再下载 JSON 或导出文档。

## 给同事用的发布包

1. **Mac**：发 `SCE-af v{版本}.zip`。解压后双击 `打开SCE-af.command`。包内带打包机上的运行时 `.venv`；系统不一致时启动器会改跑 `setup_env.py`。
2. **Windows**：发 `SCE-af v{版本}-win64.zip`（必须在 Windows 虚拟机里打包）。解压后双击 `打开SCE-af.bat`。

两种 zip 都是源码 + 该操作系统的 `.venv`，不是 exe。同事各自准备 `api-key.md`。

## 文档

- [项目说明（结构 / 实现 / 开发）](docs/01-README.md)
- [需求池](docs/02-update_backlog.md)
- [版本日志](docs/03-log.md)
- [业务规则](docs/04-rule.md)
- [流程图](docs/05-flow.md)

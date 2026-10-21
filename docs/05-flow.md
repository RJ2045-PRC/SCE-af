# 流程图

本文件描述当前项目怎么跑。业务规则仍只认 [`04-rule.md`](04-rule.md)。图按现在的代码画，不含尚未选定的提速做法。

## 同事路径

```mermaid
flowchart TD
  openPage[打开127.0.0.1] --> pickPdf[选择气泡图PDF]
  pickPdf --> upload["POST /api/jobs"]
  upload --> waitJob[页面轮询进度]
  waitJob --> bubblesFirst[气泡先出现]
  bubblesFirst --> review[核对基本信息气泡技术要求]
  review --> editRows[可手改编号与FAI]
  editRows --> download[下载JSON]
  editRows --> exportDocs["导出文档 zip"]
```

入口是本机网页。上传后页面轮询任务进度；气泡识图完成一条就出现一行 FAI，技术要求全部结束后再导出。需要时手改编号、描述和三个数值，确认后再下载 JSON 或导出五份 Excel。

## 程序路径

对应 `jobs.py` → `pipeline.run_pipeline`。导出走 `export_docs`。

```mermaid
flowchart TD
  savePdf[任务目录写入source.pdf] --> raster[逐页光栅]
  raster --> slice[切成标题栏红色气泡或技术要求条带]
  slice --> vision["DeepSeek识图，默认最多100路"]
  vision --> merge[汇总JSON并解析公差列出问题]
  merge --> resultFile[写入result.json]
  resultFile --> page[页面核对]
  page --> jsonDl[下载JSON]
  page --> exportPost["POST /api/jobs/id/export"]
  exportPost --> zipOut[写入docs.zip]
```

`plan_pdf` 先光栅再切块；每块一张 PNG，`complete_vision` 只看这一块。识图默认最多 100 路并发。`merge_job` 解析公差并列出问题，结果写入任务目录的 `result.json`。

## JSON 每块写到哪儿

导出按下面处理。不输出的分支也画出来。

```mermaid
flowchart TD
  jsonDoc[result.json]
  jsonDoc --> header[基础信息]
  jsonDoc --> bubbles[气泡公差]
  jsonDoc --> chars[特性表性能重量材料电气]
  jsonDoc --> notes[条文技术要求]
  jsonDoc --> issues[问题列表]
  header --> titles[五份表表头]
  header --> dropDrawingNo[图号不输出]
  bubbles --> fai[全尺寸FAI含NA]
  bubbles --> specials[仅SC和CC]
  bubbles --> dropPage[气泡页码不输出]
  specials --> sip[检查作业标准]
  specials --> qcp[控制计划尺寸检验]
  specials --> checklist[检查清单]
  specials --> scList[特殊特性清单]
  chars --> sip
  chars --> checklist
  chars --> markedChars[有SC或CC号]
  chars --> dropCharMeta[视图区域位置页码不输出]
  chars --> dropUnmarked[无标识不进清单]
  markedChars --> scList
  notes --> dropNotes[条文不输出]
  issues --> dropIssues[问题不输出]
```

## 边界

只绑 `127.0.0.1`。模型不见整份 PDF。DeepSeek 密钥只从本机 `api-key.md` 读。不读字典、不画工序。

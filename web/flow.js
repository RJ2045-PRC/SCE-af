const kinds = ["title", "bubble", "notes"];
const labels = ["基本信息", "气泡尺寸", "技术要求"];
const subtitles = ["文件名 + 标题栏", "红色气泡 · 并行识别", "条文 + 特殊特性表"];

export class FlowView {
  constructor() {
    this.root = document.getElementById("flow");
    this.lanes = kinds.map((kind, i) => {
      const lane = document.createElement("div");
      lane.className = "flow-lane";
      lane.innerHTML = `<div class="flow-label"><strong>${labels[i]}</strong><span class="count">等待切块</span></div>
        <p>${subtitles[i]}</p><div class="flow-meter"><div></div></div>
        <div class="flow-stats"><span>处理中 <b class="running">0</b></span><span>排队 <b class="queued">0</b></span><span class="failure">失败 <b>0</b> 块</span></div>
        <div class="flow-workers" aria-hidden="true">${Array.from({ length: 8 }, (_, j) => `<i style="--n:${j}"></i>`).join("")}</div>`;
      document.getElementById("flow_lanes").appendChild(lane);
      return lane;
    });
    this.reset("");
  }

  node(id) { return document.getElementById(`flow_${id}`); }

  reset(filename) {
    clearTimeout(this.pageTimer);
    this.jobId = null;
    this.lastJob = null;
    this.seenPages = new Set();
    this.pageQueue = [];
    this.pageTimer = null;
    this.exporting = false;
    this.root.classList.remove("slicing", "processing");
    this.node("filename").textContent = filename;
    this.node("phase").textContent = "上传 PDF…";
    this.node("page").textContent = "等待转图";
    this.node("overall").textContent = "";
    this.node("slice_count").textContent = "等待切块";
    this.node("regions").replaceChildren();
    this.node("preview").hidden = true;
    this.node("preview").removeAttribute("src");
    this.node("preview_wait").hidden = false;
    this.node("preview_wait").textContent = "等待页面转图";
    this.node("notice").hidden = true;
    this.node("json_state").textContent = "等待三路结果";
    this.node("json").classList.remove("ready");
    this.node("review").textContent = "等待识别完成";
    this.setExport("idle");
    this.renderChannels({});
  }

  show(filename) {
    this.reset(filename);
    this.root.classList.remove("hidden");
  }

  renderChannels(channels, stopped = false) {
    kinds.forEach((kind, i) => {
      const lane = this.lanes[i], c = channels[kind];
      lane.querySelector(".count").textContent = c ? `成功 ${c.succeeded} / ${c.total}` : "等待切块";
      lane.querySelector(".running").textContent = stopped ? 0 : (c?.running || 0);
      lane.querySelector(".queued").textContent = c?.queued || 0;
      lane.querySelector(".failure b").textContent = c?.failed || 0;
      lane.querySelector(".failure").classList.toggle("has-failure", !!c?.failed);
      lane.querySelector(".flow-meter div").style.width = c?.total ? `${(c.succeeded + c.failed) / c.total * 100}%` : "0%";
      lane.querySelectorAll(".flow-workers i").forEach((worker, j) => {
        worker.classList.toggle("active", !stopped && j < Math.min(8, c?.running || 0));
      });
    });
  }

  update(job) {
    if (this.jobId && this.jobId !== job.id) this.reset(job.filename);
    this.jobId = job.id;
    this.lastJob = job;
    this.root.classList.remove("hidden");
    this.node("filename").textContent = job.filename;
    const flow = job.flow || {}, p = job.progress || {}, channels = flow.channels || {};
    const terminal = ["done", "error"].includes(job.status);
    this.renderChannels(channels, terminal);
    const done = Object.values(channels).reduce((n, c) => n + c.succeeded + c.failed, 0);
    const total = Object.values(channels).reduce((n, c) => n + c.total, 0);
    const failed = Object.values(channels).reduce((n, c) => n + c.failed, 0);
    this.node("overall").textContent = total ? `${done} / ${total} 块已处理` : "正在统计切片";
    this.node("phase").textContent = job.status === "done" ? "处理结束 · 等待核对" : job.status === "error" ? "处理已停止" : p.message || "排队中";
    this.node("slice_count").textContent = total ? `共切出 ${total} 块 PNG` : p.stage === "slice" || p.stage === "raster" ? `已切出 ${p.done || 0} 块 PNG` : "等待切块";
    this.root.classList.toggle("slicing", !terminal && ["raster", "slice"].includes(p.stage));
    this.root.classList.toggle("processing", !terminal && p.stage === "vision");
    this.node("json_state").textContent = job.status === "done" ? "已汇总 · 待核对" : job.status === "error" ? "汇总未完成" : p.stage === "merge" ? "解析公差 · 合并校验" : "等待三路结果";
    this.node("json").classList.toggle("ready", job.status === "done");
    this.node("review").textContent = job.status === "done" ? "● 待用户核对" : job.status === "error" ? "处理失败" : "等待识别完成";
    this.node("notice").hidden = !(job.status === "error" || (job.status === "done" && failed));
    if (job.status === "error") this.node("notice").textContent = job.error || "任务失败，请检查后重新上传。";
    else if (job.status === "done" && failed) {
      const details = kinds.map((k, i) => channels[k]?.failed ? `${labels[i]} ${channels[k].failed} 块` : "").filter(Boolean);
      this.node("notice").textContent = `处理结束：${failed} 块识别失败（${details.join("、")}）。请结合下方问题列表核对缺失内容后再导出。`;
    }
    for (const page of flow.pages || []) {
      if (!this.seenPages.has(page.page)) {
        this.seenPages.add(page.page);
        this.pageQueue.push({ ...page, jobId: job.id, total: flow.page_count });
      }
    }
    if (job.status === "error") { clearTimeout(this.pageTimer); this.pageTimer = null; this.pageQueue = []; }
    else this.advancePage();
  }

  fail(message) {
    this.update({ ...this.lastJob, id: this.jobId, filename: this.node("filename").textContent,
      status: "error", error: message });
  }

  advancePage() {
    if (this.pageTimer || !this.pageQueue.length) return;
    const page = this.pageQueue.shift();
    this.node("page").textContent = `第 ${page.page} / ${page.total} 页`;
    const img = this.node("preview");
    img.onload = () => { img.hidden = false; this.node("preview_wait").hidden = true; };
    img.onerror = () => { img.hidden = true; this.node("preview_wait").hidden = false; this.node("preview_wait").textContent = "页面预览暂不可用，后台继续处理"; };
    img.src = `/api/jobs/${encodeURIComponent(page.jobId)}/crops/${encodeURIComponent(page.preview)}`;
    this.node("regions").replaceChildren();
    for (const region of page.regions) {
      const [x0, y0, x1, y1] = region.box;
      const box = document.createElement("div");
      box.className = `flow-region ${region.kind}`;
      Object.assign(box.style, { left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` });
      box.setAttribute("aria-label", labels[kinds.indexOf(region.kind)] || region.kind);
      this.node("regions").appendChild(box);
    }
    this.pageTimer = setTimeout(() => { this.pageTimer = null; this.advancePage(); }, 1100);
  }

  setExport(state) {
    this.exporting = state === "running";
    this.root.classList.toggle("exporting", this.exporting);
    this.node("export_state").textContent = {
      idle: "核对后填充 5 份 Excel 模板", running: "正在填充 SIP / 控制计划 / 检查清单 / 特殊特性清单 / FAI…",
      done: "✓ 5 份 Excel 已生成", error: "导出失败，可核对后重试",
    }[state];
  }
}

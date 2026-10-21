const fillVersion = (text) => {
  for (const node of document.querySelectorAll("#app_version, #app_version_foot")) {
    node.textContent = text;
  }
};

const $ = (id) => document.getElementById(id);

const cell = (value) => {
  const td = document.createElement("td");
  td.textContent = value == null || value === "" ? "" : String(value);
  return td;
};

const fillTable = (tbody, rows, keys) => {
  tbody.replaceChildren();
  for (const row of rows || []) {
    const tr = document.createElement("tr");
    for (const key of keys) tr.appendChild(cell(row[key]));
    tbody.appendChild(tr);
  }
};

const showResult = (job) => {
  const result = job.result;
  if (!result) return;
  $("result").classList.remove("hidden");
  const h = result.header || {};
  $("f_filename").value = h.filename || job.filename || "";
  $("f_customer").value = h.customer || "";
  $("f_part_name").value = h.part_name || "";
  $("f_mold_no").value = h.mold_no || "";
  $("f_part_no").value = h.part_no || "";
  $("f_drawing_no").value = h.drawing_no || "";
  $("f_revision").value = h.revision || "";
  const issues = $("issues");
  issues.replaceChildren();
  for (const item of result.issues || []) {
    const li = document.createElement("li");
    li.textContent = item.message || item.code || "";
    issues.appendChild(li);
  }
  if (!(result.issues || []).length) {
    const li = document.createElement("li");
    li.textContent = "没有问题。";
    issues.appendChild(li);
  }
  fillTable($("bubbles"), result.bubbles, [
    "num", "page", "special", "special_no", "type", "description", "nominal", "upper", "lower",
  ]);
  const req = result.requirements || {};
  fillTable($("notes"), req.notes, ["no", "page", "special", "special_no", "text"]);
  fillTable($("chars"), req.characteristics, [
    "cc_no", "sc_no", "name", "params", "view", "zone", "location", "page",
  ]);
  $("download").href = `/api/jobs/${job.id}/json`;
  $("export_btn").dataset.jobId = job.id;
};

const headerEdits = () => ({
  customer: $("f_customer").value,
  part_name: $("f_part_name").value,
  mold_no: $("f_mold_no").value,
  part_no: $("f_part_no").value,
  drawing_no: $("f_drawing_no").value,
  revision: $("f_revision").value,
});

const currentJobId = () => {
  const fromBtn = $("export_btn").dataset.jobId;
  if (fromBtn) return fromBtn;
  const href = $("download").getAttribute("href") || "";
  const match = href.match(/\/api\/jobs\/([^/]+)\//);
  return match ? match[1] : "";
};

const poll = async (id) => {
  const progress = $("progress");
  for (;;) {
    const resp = await fetch(`/api/jobs/${id}`);
    const job = await resp.json();
    const msg = (job.progress && job.progress.message) || job.status || "";
    progress.textContent = msg;
    if (job.status === "done") {
      $("status").textContent = "识图完成，请核对。";
      showResult(job);
      return;
    }
    if (job.status === "error") {
      $("status").textContent = job.error || "失败";
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
};

const boot = async () => {
  try {
    const resp = await fetch("/api/version");
    const data = await resp.json();
    const version = data && data.version ? String(data.version) : "";
    fillVersion(version ? `v${version}` : "");
  } catch (err) {
    fillVersion("");
    $("status").textContent = "无法读取版本。请用 run.py 打开本页，不要直接双击 HTML。";
    return;
  }
  try {
    const cfg = await (await fetch("/api/config")).json();
    $("key_state").textContent = cfg.has_key ? "已读取本机 DeepSeek 密钥" : "缺少 api-key.md";
  } catch (err) {
    $("key_state").textContent = "";
  }

  $("start_btn").addEventListener("click", async () => {
    const input = $("pdf_file");
    const file = input.files && input.files[0];
    if (!file) {
      $("status").textContent = "请先选择 PDF。";
      return;
    }
    $("result").classList.add("hidden");
    $("status").textContent = "上传中…";
    $("progress").textContent = "";
    const body = new FormData();
    body.append("file", file, file.name);
    const resp = await fetch("/api/jobs", { method: "POST", body });
    const job = await resp.json();
    if (!resp.ok) {
      $("status").textContent = job.error || "上传失败";
      return;
    }
    $("status").textContent = "正在切图识图…";
    await poll(job.id);
  });

  const pending = new URLSearchParams(location.search).get("job");
  if (pending) {
    $("status").textContent = "正在切图识图…";
    await poll(pending);
  }

  $("save_header").addEventListener("click", async () => {
    const id = currentJobId();
    if (!id) return;
    const resp = await fetch(`/api/jobs/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(headerEdits()),
    });
    const job = await resp.json();
    if (!resp.ok) {
      $("status").textContent = job.error || "保存失败";
      return;
    }
    $("status").textContent = "编号已保存。";
    showResult(job);
  });

  $("export_btn").addEventListener("click", async () => {
    const id = currentJobId();
    if (!id) return;
    $("status").textContent = "正在导出文档…";
    const resp = await fetch(`/api/jobs/${id}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(headerEdits()),
    });
    if (!resp.ok) {
      let message = "导出失败";
      try {
        const payload = await resp.json();
        message = payload.error || message;
      } catch (err) {
        message = "导出失败";
      }
      $("status").textContent = message;
      return;
    }
    const blob = await resp.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${id}-docs.zip`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    $("status").textContent = "文档已导出。";
  });
};

boot();

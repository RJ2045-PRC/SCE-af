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

const specialLabel = (value) => {
  const text = String(value || "NA").trim().toUpperCase();
  if (text === "SC" || text === "CC") return text;
  return "N/A";
};

const fmtBound = (value) => (value == null || value === "" ? "" : String(value));

const inputCell = (key, value, extra = {}) => {
  const td = document.createElement("td");
  const input = document.createElement("input");
  input.className = "fai-input";
  input.dataset.k = key;
  input.value = value == null ? "" : String(value);
  if (extra.title) input.title = extra.title;
  td.appendChild(input);
  return td;
};

let renderedCrops = new Set();

const cropKey = (row) => row.crop || `${row.page || ""}-${row.num || ""}`;

const makeFaiRow = (jobId, row) => {
  const tr = document.createElement("tr");
  tr.dataset.crop = row.crop || "";
  tr.appendChild(inputCell("num", row.num || ""));
  const shot = document.createElement("td");
  if (row.crop && jobId) {
    const img = document.createElement("img");
    img.className = "crop";
    img.alt = `气泡 ${row.num || ""}`;
    img.src = `/api/jobs/${jobId}/crops/${encodeURIComponent(row.crop)}`;
    shot.appendChild(img);
  }
  tr.appendChild(shot);
  tr.appendChild(inputCell("special", specialLabel(row.special)));
  tr.appendChild(inputCell("description", row.description || ""));
  tr.appendChild(inputCell("min_val", fmtBound(row.min_val)));
  tr.appendChild(inputCell("std_val", fmtBound(row.std_val)));
  tr.appendChild(inputCell("max_val", fmtBound(row.max_val)));
  return tr;
};

const fillFai = (job, { reset = false } = {}) => {
  const tbody = $("bubbles");
  const rows = (job.result && job.result.bubbles) || [];
  if (reset) {
    renderedCrops = new Set();
    tbody.replaceChildren();
  }
  for (const row of rows) {
    const key = cropKey(row);
    if (renderedCrops.has(key)) continue;
    renderedCrops.add(key);
    tbody.appendChild(makeFaiRow(job.id, row));
  }
};

const collectBubbles = () =>
  [...$("bubbles").querySelectorAll("tr")].map((tr) => ({
    num: tr.querySelector("[data-k=num]").value,
    special: tr.querySelector("[data-k=special]").value,
    description: tr.querySelector("[data-k=description]").value,
    min_val: tr.querySelector("[data-k=min_val]").value,
    std_val: tr.querySelector("[data-k=std_val]").value,
    max_val: tr.querySelector("[data-k=max_val]").value,
  }));

const setDoneUi = (done, job) => {
  $("export_btn").disabled = !done;
  $("save_bubbles").disabled = !done;
  $("save_header").disabled = !done;
  $("download").classList.toggle("disabled", !done);
  $("issues_card").classList.toggle("hidden", !done);
  $("notes_card").classList.toggle("hidden", !done);
  if (done && job) {
    $("download").href = `/api/jobs/${job.id}/json`;
    $("export_btn").dataset.jobId = job.id;
  }
};

const showHeader = (job) => {
  const result = job.result || {};
  const h = result.header || {};
  $("f_filename").value = h.filename || job.filename || "";
  $("f_customer").value = h.customer || "";
  $("f_part_name").value = h.part_name || "";
  $("f_mold_no").value = h.mold_no || "";
  $("f_part_no").value = h.part_no || "";
  $("f_drawing_no").value = h.drawing_no || "";
  $("f_revision").value = h.revision || "";
};

const showIssuesAndNotes = (job) => {
  const result = job.result || {};
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
  const req = result.requirements || {};
  fillTable($("notes"), req.notes, ["no", "page", "special", "special_no", "text"]);
  fillTable($("chars"), req.characteristics, [
    "cc_no", "sc_no", "name", "params", "view", "zone", "location", "page",
  ]);
};

const showResult = (job) => {
  if (!job || !job.result) return;
  $("result").classList.remove("hidden");
  showHeader(job);
  const done = job.status === "done";
  setDoneUi(done, job);
  if (done) {
    fillFai(job, { reset: true });
    showIssuesAndNotes(job);
  } else {
    fillFai(job);
  }
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
  $("export_btn").dataset.jobId = id;
  for (;;) {
    const resp = await fetch(`/api/jobs/${id}`);
    const job = await resp.json();
    const msg = (job.progress && job.progress.message) || job.status || "";
    progress.textContent = msg;
    if (job.result && (job.result.bubbles || []).length) {
      $("result").classList.remove("hidden");
      showHeader(job);
      fillFai(job);
      setDoneUi(false, job);
    }
    if (job.status === "done") {
      $("status").textContent = "识图完成，请核对。";
      showResult(job);
      return;
    }
    if (job.status === "error") {
      $("status").textContent = job.error || "失败";
      if (job.result && (job.result.bubbles || []).length) showResult(job);
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
    renderedCrops = new Set();
    $("bubbles").replaceChildren();
    $("export_btn").disabled = true;
    $("export_btn").dataset.jobId = "";
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

  $("save_bubbles").addEventListener("click", async () => {
    const id = currentJobId();
    if (!id) return;
    const resp = await fetch(`/api/jobs/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...headerEdits(), bubbles: collectBubbles() }),
    });
    const job = await resp.json();
    if (!resp.ok) {
      $("status").textContent = job.error || "保存失败";
      return;
    }
    $("status").textContent = "气泡已保存。";
    showResult(job);
  });

  $("export_btn").addEventListener("click", async () => {
    const id = currentJobId();
    if (!id) return;
    $("status").textContent = "正在导出文档…";
    const resp = await fetch(`/api/jobs/${id}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...headerEdits(), bubbles: collectBubbles() }),
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

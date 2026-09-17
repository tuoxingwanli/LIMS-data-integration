const $ = (selector) => document.querySelector(selector);

const state = {
  lastOrderNo: "WO-DEMO-001",
  lastBlindSampleNo: "BLIND-DEMO-001",
  lastResponse: null,
};

function now() {
  return new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function logEvent(title, detail, isError = false) {
  const list = $("#activity-list");
  const empty = list.querySelector(".empty");
  if (empty) empty.remove();
  const item = document.createElement("div");
  item.className = `activity${isError ? " error" : ""}`;
  item.innerHTML = `<span class="activity-mark"></span><div><strong>${title}</strong><small>${detail}</small></div><time>${now()}</time>`;
  list.prepend(item);
}

function showResponse(path, status, body, isError = false) {
  state.lastResponse = body;
  const viewer = $("#response-viewer");
  viewer.className = `response-viewer ${isError ? "error" : "success"}`;
  viewer.textContent = pretty(body);
  $("#response-code").textContent = status ? `HTTP ${status}` : "ERROR";
  $("#response-code").style.color = isError ? "#c56a48" : "var(--green)";
  $("#response-code").style.background = isError ? "#fff1eb" : "#ebf8f2";
  $("#response-path").textContent = path;
}

async function request(path, options = {}, label = path) {
  logEvent(`调用 ${label}`, `${options.method || "GET"} ${path}`);
  try {
    const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
    const text = await response.text();
    let body;
    try { body = text ? JSON.parse(text) : null; } catch { body = { raw: text }; }
    showResponse(path, response.status, body, !response.ok);
    logEvent(`${label} ${response.ok ? "完成" : "返回错误"}`, `HTTP ${response.status}`, !response.ok);
    if (!response.ok) throw new Error(body?.detail || body?.message || `HTTP ${response.status}`);
    return body;
  } catch (error) {
    const body = { error: error.message || "网络请求失败" };
    showResponse(path, 0, body, true);
    logEvent(`${label} 失败`, body.error, true);
    throw error;
  }
}

function setFlow(name) {
  const names = ["order", "detection", "result", "push"];
  const activeIndex = names.indexOf(name);
  document.querySelectorAll(".flow-node").forEach((node, index) => {
    node.classList.toggle("active", index === activeIndex);
    node.classList.toggle("done", index < activeIndex);
  });
  document.querySelectorAll(".flow-line").forEach((line, index) => line.classList.toggle("done", index < activeIndex));
}

function updateSession(text, mode = "") {
  const node = $("#session-state");
  node.className = `session-state ${mode}`;
  node.innerHTML = `<span class="state-dot"></span><span>${text}</span>`;
}

async function checkHealth() {
  const card = $("#health-card");
  const text = $("#health-text");
  const time = $("#health-time");
  card.classList.remove("online");
  text.textContent = "检查中";
  time.textContent = "正在连接 /health";
  try {
    const result = await request("/health", {}, "服务健康检查");
    text.textContent = result.status === "ok" ? "服务在线" : "服务响应异常";
    time.textContent = `最近检查 ${now()}`;
    $(".status-icon span").style.background = result.status === "ok" ? "var(--green)" : "var(--orange)";
  } catch {
    text.textContent = "服务不可用";
    time.textContent = "请确认 Uvicorn 已启动";
    $(".status-icon span").style.background = "#dc704e";
  }
}

function workOrderPayload() {
  return {
    order_no: $("#order-no").value.trim(),
    experimenter_id: $("#experimenter-id").value.trim(),
    project_name: $("#project-name").value.trim() || null,
    samples: [{ sample_no: $("#sample-no").value.trim(), sample_name: $("#sample-name").value.trim() || null }],
    test_items: $("#test-items").value.split(",").map((item) => item.trim()).filter(Boolean),
  };
}

$("#refresh-health").addEventListener("click", checkHealth);

$("#work-order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = workOrderPayload();
  try {
    const result = await request("/api/work-orders", { method: "POST", body: JSON.stringify(payload) }, "接收 LIMS 工单");
    state.lastOrderNo = payload.order_no;
    $("#result-order-no").value = payload.order_no;
    $("#result-sample-no").value = payload.samples[0].sample_no;
    setFlow("detection");
    logEvent(result.duplicate ? "工单已存在" : "工单保存成功", payload.order_no);
  } catch { /* request 已写入响应和日志 */ }
});

$("#scada-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const id = encodeURIComponent($("#query-experimenter").value.trim());
  try {
    const result = await request(`/api/scada/work-orders?experimenter_id=${id}`, {}, "查询 SCADA 工单");
    const list = $("#work-order-list");
    list.innerHTML = result.work_orders?.length
      ? result.work_orders.map((order) => `<strong>${order.order_no}</strong> · ${order.status} · ${order.samples.length} 个样品`).join("<br />")
      : `<span class="muted">暂无待处理工单（共 ${result.count || 0} 条）</span>`;
  } catch { $("#work-order-list").innerHTML = `<span class="muted">查询失败，请查看最近响应</span>`; }
});

async function detectionAction(action) {
  const blindSampleNo = $("#blind-sample-no").value.trim();
  state.lastBlindSampleNo = blindSampleNo;
  const endpoint = action === "start" ? "/startTest" : "/stopTest";
  try {
    const result = await request(endpoint, { method: "POST", body: JSON.stringify({ blindSampleNo }) }, action === "start" ? "开始检测" : "结束检测");
    if (result.code === "0010") {
      updateSession(action === "start" ? "检测中 · 已记录开始时间" : "检测已结束 · 已记录结束时间", action === "start" ? "recording" : "stopped");
      setFlow(action === "start" ? "detection" : "result");
    } else updateSession(result.message || "业务处理失败");
  } catch { updateSession("接口调用失败，请查看最近响应"); }
}

$("#start-test").addEventListener("click", () => detectionAction("start"));
$("#stop-test").addEventListener("click", () => detectionAction("stop"));

$("#result-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const rawValue = $("#result-value").value.trim();
  const numberValue = Number(rawValue);
  const payload = {
    order_no: $("#result-order-no").value.trim(),
    results: [{ sample_no: $("#result-sample-no").value.trim(), test_item: $("#result-item").value.trim(), value: rawValue !== "" && Number.isFinite(numberValue) ? numberValue : rawValue, unit: $("#result-unit").value.trim() || null }],
    finished: $("#result-finished").checked,
  };
  try { await request("/api/scada/results", { method: "POST", body: JSON.stringify(payload) }, "上传实验结果"); setFlow("push"); }
  catch { /* request 已写入响应和日志 */ }
});

$("#query-results").addEventListener("click", async () => {
  const orderNo = $("#result-order-no").value.trim() || state.lastOrderNo;
  try { await request(`/api/work-orders/${encodeURIComponent(orderNo)}/results`, {}, "查询实验结果"); }
  catch { /* request 已写入响应和日志 */ }
});

$("#push-results").addEventListener("click", async () => {
  const orderNo = $("#result-order-no").value.trim() || state.lastOrderNo;
  try { await request(`/api/work-orders/${encodeURIComponent(orderNo)}/push-to-lims`, { method: "POST" }, "回推 LIMS"); setFlow("push"); }
  catch { /* request 已写入响应和日志 */ }
});

$("#copy-response").addEventListener("click", async () => {
  if (!state.lastResponse) return;
  try { await navigator.clipboard.writeText(pretty(state.lastResponse)); logEvent("响应已复制", "JSON 已写入剪贴板"); }
  catch { logEvent("复制失败", "浏览器未允许访问剪贴板", true); }
});

$("#clear-log").addEventListener("click", () => {
  $("#activity-list").innerHTML = `<div class="activity empty"><span class="activity-mark"></span><div><strong>操作记录已清空</strong><small>等待下一次接口操作</small></div><time>${now()}</time></div>`;
});

checkHealth();

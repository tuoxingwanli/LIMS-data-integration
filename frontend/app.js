const $ = (selector) => document.querySelector(selector);

const state = { lastOrderNo: "WO-DEMO-001", lastResponse: null };

function now() {
  return new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function escapeHTML(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[char]);
}

function pretty(value) {
  return JSON.stringify(value, null, 2);
}

function errorMessage(body, status) {
  if (Array.isArray(body?.detail)) {
    return body.detail.map((item) => {
      const location = Array.isArray(item.loc) ? item.loc.filter(Boolean).join(".") : "请求";
      return `${location}: ${item.msg || "格式错误"}`;
    }).join("；");
  }
  if (typeof body?.detail === "string") return body.detail;
  if (typeof body?.message === "string") return body.message;
  return status ? `HTTP ${status}` : "网络请求失败";
}

function isBusinessError(body) {
  return body?.code === "500" || body?.success === false;
}

function logEvent(title, detail, isError = false) {
  const list = $("#activity-list");
  list.querySelector(".empty")?.remove();
  const item = document.createElement("div");
  item.className = `activity${isError ? " error" : ""}`;
  item.innerHTML = `<i></i><div><strong>${escapeHTML(title)}</strong><small>${escapeHTML(detail)}</small></div><time>${now()}</time>`;
  list.prepend(item);
}

function showResponse(path, status, body, isError = false) {
  state.lastResponse = body;
  const viewer = $("#response-viewer");
  viewer.className = `response-viewer${isError ? " error" : ""}`;
  viewer.textContent = pretty(body);
  $("#response-code").textContent = status ? `HTTP ${status}` : "ERROR";
  $("#response-code").style.color = isError ? "#cf654a" : "var(--green)";
  $("#response-path").textContent = path;
}

async function request(path, options = {}, label = path, silent = false) {
  if (!silent) logEvent(`调用 ${label}`, `${options.method || "GET"} ${path}`);
  try {
    const headers = { ...(options.headers || {}) };
    if (options.body && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
    const response = await fetch(path, { ...options, headers });
    const text = await response.text();
    let body;
    try { body = text ? JSON.parse(text) : null; } catch { body = { raw: text }; }
    const businessError = isBusinessError(body);
    const failed = !response.ok || businessError;
    if (!silent) showResponse(path, response.status, body, failed);
    if (!silent) logEvent(`${label}${failed ? "返回错误" : "完成"}`, `HTTP ${response.status}${businessError ? " · 业务失败" : ""}`, failed);
    if (!response.ok) throw new Error(errorMessage(body, response.status));
    return body;
  } catch (error) {
    if (!silent) { showResponse(path, 0, { error: error.message || "网络请求失败" }, true); logEvent(`${label}失败`, error.message || "网络请求失败", true); }
    throw error;
  }
}

function setFlow(current) {
  const names = ["order", "detection", "result", "push"];
  const activeIndex = names.indexOf(current);
  document.querySelectorAll("#flow-list li").forEach((node, index) => {
    node.classList.toggle("current", index === activeIndex);
    node.classList.toggle("complete", index < activeIndex);
  });
  document.querySelectorAll("[data-step-link]").forEach((node) => node.classList.toggle("active", node.dataset.stepLink === current));
  const labels = { order: "从工单开始", detection: "正在进行检测", result: "等待上传结果", push: "可以查询与回推" };
  $("#workflow-status").textContent = labels[current] || labels.order;
}

document.querySelectorAll("[data-step-link]").forEach((node) => {
  node.addEventListener("click", () => setFlow(node.dataset.stepLink));
});

function updateSession(text, mode = "") {
  const node = $("#session-state");
  node.className = `session-state ${mode}`;
  node.innerHTML = `<i></i><span>${escapeHTML(text)}</span>`;
}

async function checkHealth() {
  const stateNode = $("#server-state");
  const text = $("#health-text");
  stateNode.className = "server-state";
  text.textContent = "检查服务";
  try {
    const result = await request("/health", {}, "服务健康检查", true);
    stateNode.classList.add(result.status === "ok" ? "online" : "error");
    text.textContent = result.status === "ok" ? "服务在线" : "服务异常";
  } catch { stateNode.classList.add("error"); text.textContent = "服务不可用"; }
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

$("#work-order-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = workOrderPayload();
  try {
    const result = await request("/api/work-orders", { method: "POST", body: JSON.stringify(payload) }, "接收 LIMS 工单");
    state.lastOrderNo = payload.order_no;
    $("#result-order-no").value = payload.order_no;
    $("#result-sample-no").value = payload.samples[0].sample_no;
    setFlow("detection");
    logEvent(result.duplicate ? "工单已经存在" : "工单保存成功", payload.order_no);
  } catch { /* request 已记录响应 */ }
});

$("#query-scada").addEventListener("click", async () => {
  const experimenter = encodeURIComponent($("#experimenter-id").value.trim());
  try {
    const result = await request(`/api/scada/work-orders?experimenter_id=${experimenter}`, {}, "查询 SCADA 工单");
    $("#work-order-list").innerHTML = result.work_orders?.length
      ? result.work_orders.map((order) => `<strong>${escapeHTML(order.order_no)}</strong> · ${escapeHTML(order.status)} · ${order.samples.length} 个样品`).join("<br />")
      : `<span>暂无待处理工单（共 ${result.count || 0} 条）</span>`;
  } catch { $("#work-order-list").innerHTML = "<span>查询失败，请查看最近响应</span>"; }
});

async function detectionAction(action) {
  const blindSampleNo = $("#blind-sample-no").value.trim();
  const endpoint = action === "start" ? "/startTest" : "/stopTest";
  try {
    const result = await request(endpoint, { method: "POST", body: JSON.stringify({ blindSampleNo }) }, action === "start" ? "开始检测" : "结束检测");
    if (result.code === "0010") {
      updateSession(action === "start" ? "检测中，已记录开始时间" : "检测已结束，已记录结束时间", action === "start" ? "recording" : "stopped");
      setFlow(action === "start" ? "detection" : "result");
    } else updateSession(result.message || "业务处理失败", "error");
  } catch { updateSession("调用失败，请查看最近响应", "error"); }
}

$("#start-test").addEventListener("click", () => detectionAction("start"));
$("#stop-test").addEventListener("click", () => detectionAction("stop"));

$("#result-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const rawValue = $("#result-value").value.trim();
  const numericValue = Number(rawValue);
  const payload = {
    order_no: $("#result-order-no").value.trim(),
    results: [{ sample_no: $("#result-sample-no").value.trim(), test_item: $("#result-item").value.trim(), value: rawValue !== "" && Number.isFinite(numericValue) ? numericValue : rawValue, unit: $("#result-unit").value.trim() || null }],
    finished: $("#result-finished").checked,
  };
  try { await request("/api/scada/results", { method: "POST", body: JSON.stringify(payload) }, "上传实验结果"); setFlow("push"); }
  catch { /* request 已记录响应 */ }
});

$("#query-results").addEventListener("click", async () => {
  const orderNo = $("#result-order-no").value.trim() || state.lastOrderNo;
  try { await request(`/api/work-orders/${encodeURIComponent(orderNo)}/results`, {}, "查询实验结果"); }
  catch { /* request 已记录响应 */ }
});

$("#push-results").addEventListener("click", async () => {
  const orderNo = $("#result-order-no").value.trim() || state.lastOrderNo;
  try { await request(`/api/work-orders/${encodeURIComponent(orderNo)}/push-to-lims`, { method: "POST" }, "回推 LIMS"); setFlow("push"); }
  catch { /* request 已记录响应 */ }
});

$("#copy-response").addEventListener("click", async () => {
  if (!state.lastResponse) return;
  try { await navigator.clipboard.writeText(pretty(state.lastResponse)); logEvent("响应已复制", "JSON 已写入剪贴板"); }
  catch { logEvent("复制失败", "浏览器未允许访问剪贴板", true); }
});

$("#clear-log").addEventListener("click", () => {
  $("#activity-list").innerHTML = `<div class="activity empty"><i></i><div><strong>操作记录已清空</strong><small>等待下一次接口调用</small></div><time>${now()}</time></div>`;
});

checkHealth();

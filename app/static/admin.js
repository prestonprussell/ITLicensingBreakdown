const vendorSelect = document.getElementById("admin-vendor");
const searchInput = document.getElementById("admin-search");
const reloadBtn = document.getElementById("admin-reload-btn");
const syncEntraBtn = document.getElementById("admin-sync-entra-btn");
const importBtn = document.getElementById("admin-import-btn");
const importFileInput = document.getElementById("admin-import-file");
const addBtn = document.getElementById("admin-add-btn");
const saveBtn = document.getElementById("admin-save-btn");
const statusText = document.getElementById("admin-status");
const usersBody = document.getElementById("admin-users-body");
const addRuleBtn = document.getElementById("admin-add-rule-btn");
const usersSection = document.getElementById("admin-users-section");
const rulesSection = document.getElementById("admin-rules-section");
const rulesBody = document.getElementById("admin-rules-body");

let userRows = [];
let nextRowId = 1;

let ruleRows = [];
let availableBranches = [];
let availableRuleTypes = ["home_office", "single_branch", "unit_sequence", "split", "dynamic_user"];

const RULE_TYPE_LABELS = {
  home_office: "All to Home Office",
  single_branch: "All to one branch",
  unit_sequence: "One unit per branch (ordered)",
  split: "Fixed amount to a branch, remainder Home Office",
  dynamic_user: "Per matched user (by license)",
};

function isRulesMode() {
  return vendorSelect.value === "integricom-rules";
}

function setStatus(message, type = "info") {
  statusText.textContent = message;
  statusText.classList.remove("ok", "error");
  if (type === "ok") statusText.classList.add("ok");
  if (type === "error") statusText.classList.add("error");
}

function formatDate(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function escapeHtml(value) {
  return (value || "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function applyFilter(rows) {
  const query = searchInput.value.trim().toLowerCase();
  if (!query) return rows;

  return rows.filter((row) =>
    [row.first_name, row.last_name, row.email, row.branch].some((value) =>
      (value || "").toLowerCase().includes(query),
    ),
  );
}

function updateRowFromInput(rowId, field, value) {
  const row = userRows.find((item) => item._id === rowId);
  if (!row) return;
  row[field] = value;
}

function renderRows() {
  usersBody.innerHTML = "";
  const visibleRows = applyFilter(userRows);

  if (!visibleRows.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="7">No users match your current filter.</td>';
    usersBody.appendChild(tr);
    return;
  }

  visibleRows.forEach((row) => {
    const tr = document.createElement("tr");
    const emailReadOnly = row.is_new ? "" : "readonly";
    tr.innerHTML = `
      <td><input type="text" id="first-${row._id}" value="${escapeHtml(row.first_name)}" /></td>
      <td><input type="text" id="last-${row._id}" value="${escapeHtml(row.last_name)}" /></td>
      <td><input type="text" id="email-${row._id}" value="${escapeHtml(row.email)}" ${emailReadOnly} /></td>
      <td><input type="text" id="branch-${row._id}" value="${escapeHtml(row.branch)}" /></td>
      <td>${formatDate(row.last_seen_at)}</td>
      <td>${formatDate(row.updated_at)}</td>
      <td>
        <button id="action-${row._id}" type="button" class="${row.is_new ? "btn-secondary" : "btn-danger"}">
          ${row.is_new ? "Remove" : "Deactivate"}
        </button>
      </td>
    `;
    usersBody.appendChild(tr);

    document.getElementById(`first-${row._id}`).addEventListener("input", (event) => {
      updateRowFromInput(row._id, "first_name", event.target.value);
    });
    document.getElementById(`last-${row._id}`).addEventListener("input", (event) => {
      updateRowFromInput(row._id, "last_name", event.target.value);
    });
    document.getElementById(`email-${row._id}`).addEventListener("input", (event) => {
      updateRowFromInput(row._id, "email", event.target.value);
    });
    document.getElementById(`branch-${row._id}`).addEventListener("input", (event) => {
      updateRowFromInput(row._id, "branch", event.target.value);
    });

    document.getElementById(`action-${row._id}`).addEventListener("click", async () => {
      if (row.is_new) {
        userRows = userRows.filter((item) => item._id !== row._id);
        renderRows();
        return;
      }
      await deactivateRow(row);
    });
  });
}

function updateVendorActions() {
  const rulesMode = isRulesMode();
  const isIntegricom = vendorSelect.value === "integricom";
  const isAdobe = vendorSelect.value === "adobe";
  syncEntraBtn.hidden = rulesMode || !isIntegricom;
  importBtn.hidden = rulesMode || !isAdobe;
  addBtn.hidden = rulesMode;
  addRuleBtn.hidden = !rulesMode;
  if (usersSection) usersSection.hidden = rulesMode;
  if (rulesSection) rulesSection.hidden = !rulesMode;
}

// --- Rules mode -----------------------------------------------------------

function renderRuleParamsCell(row) {
  const type = row.rule_type;
  const branchOptions = (selected) =>
    availableBranches
      .map((b) => `<option value="${escapeHtml(b)}" ${b === selected ? "selected" : ""}>${escapeHtml(b)}</option>`)
      .join("");

  if (type === "home_office") {
    return '<span class="muted-line">All to Home Office</span>';
  }
  if (type === "single_branch") {
    return `<select id="rule-branch-${row._id}"><option value="">Choose branch…</option>${branchOptions(row.params.branch)}</select>`;
  }
  if (type === "split") {
    return `
      <select id="rule-branch-${row._id}"><option value="">Choose branch…</option>${branchOptions(row.params.branch)}</select>
      <input type="text" id="rule-amount-${row._id}" value="${escapeHtml(row.params.amount || "")}" placeholder="Amount (e.g. 97.00)" style="max-width:120px" />`;
  }
  if (type === "unit_sequence") {
    const branches = Array.isArray(row.params.branches) ? row.params.branches.join(", ") : "";
    return `<input type="text" id="rule-branches-${row._id}" value="${escapeHtml(branches)}" placeholder="Ordered branches, comma-separated" />`;
  }
  if (type === "dynamic_user") {
    const tokens = Array.isArray(row.params.match_tokens) ? row.params.match_tokens.join(", ") : "";
    return `<input type="text" id="rule-tokens-${row._id}" value="${escapeHtml(tokens)}" placeholder="License tokens, comma-separated" />`;
  }
  return "";
}

function wireRuleParamsInputs(row) {
  const branchSel = document.getElementById(`rule-branch-${row._id}`);
  if (branchSel) branchSel.addEventListener("change", (e) => { row.params.branch = e.target.value; });
  const amountInput = document.getElementById(`rule-amount-${row._id}`);
  if (amountInput) amountInput.addEventListener("input", (e) => { row.params.amount = e.target.value; });
  const branchesInput = document.getElementById(`rule-branches-${row._id}`);
  if (branchesInput) branchesInput.addEventListener("input", (e) => {
    row.params.branches = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
  });
  const tokensInput = document.getElementById(`rule-tokens-${row._id}`);
  if (tokensInput) tokensInput.addEventListener("input", (e) => {
    row.params.match_tokens = e.target.value.split(",").map((s) => s.trim()).filter(Boolean);
  });
}

function applyRuleFilter(rows) {
  const query = searchInput.value.trim().toLowerCase();
  if (!query) return rows;
  return rows.filter((row) => (row.canonical_name || "").toLowerCase().includes(query));
}

function renderRuleRows() {
  rulesBody.innerHTML = "";
  const visible = applyRuleFilter(ruleRows);
  if (!visible.length) {
    const tr = document.createElement("tr");
    tr.innerHTML = '<td colspan="5">No rules match your current filter.</td>';
    rulesBody.appendChild(tr);
    return;
  }

  visible.forEach((row) => {
    const tr = document.createElement("tr");
    const nameCell = row.is_new
      ? `<input type="text" id="rule-name-${row._id}" value="${escapeHtml(row.canonical_name)}" placeholder="Exact invoice line name" />`
      : `${escapeHtml(row.canonical_name)}`;
    const typeOptions = availableRuleTypes
      .map((t) => `<option value="${t}" ${t === row.rule_type ? "selected" : ""}>${escapeHtml(RULE_TYPE_LABELS[t] || t)}</option>`)
      .join("");

    tr.innerHTML = `
      <td>${nameCell}</td>
      <td><select id="rule-type-${row._id}">${typeOptions}</select></td>
      <td id="rule-params-${row._id}">${renderRuleParamsCell(row)}</td>
      <td><span class="muted-line">${escapeHtml(row.source || "")}</span></td>
      <td><button id="rule-del-${row._id}" type="button" class="${row.is_new ? "btn-secondary" : "btn-danger"}">${row.is_new ? "Remove" : "Delete"}</button></td>
    `;
    rulesBody.appendChild(tr);

    if (row.is_new) {
      document.getElementById(`rule-name-${row._id}`).addEventListener("input", (e) => { row.canonical_name = e.target.value; });
    }
    document.getElementById(`rule-type-${row._id}`).addEventListener("change", (e) => {
      row.rule_type = e.target.value;
      row.params = {};
      const cell = document.getElementById(`rule-params-${row._id}`);
      cell.innerHTML = renderRuleParamsCell(row);
      wireRuleParamsInputs(row);
    });
    wireRuleParamsInputs(row);
    document.getElementById(`rule-del-${row._id}`).addEventListener("click", async () => {
      if (row.is_new) {
        ruleRows = ruleRows.filter((item) => item._id !== row._id);
        renderRuleRows();
        return;
      }
      await deleteRuleRow(row);
    });
  });
}

async function loadRules() {
  updateVendorActions();
  setStatus("Loading Integricom allocation rules...");
  saveBtn.disabled = true;
  addRuleBtn.disabled = true;
  reloadBtn.disabled = true;
  try {
    const response = await fetch("/api/integricom/allocation-rules");
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Failed to load rules.");
    }
    const data = await response.json();
    availableBranches = data.branches || [];
    availableRuleTypes = data.rule_types || availableRuleTypes;
    ruleRows = (data.rules || []).map((r) => ({
      _id: nextRowId++,
      is_new: false,
      canonical_name: r.canonical_name,
      rule_type: r.rule_type,
      params: r.params || {},
      source: r.source || "",
    }));
    renderRuleRows();
    setStatus(`Loaded ${ruleRows.length} allocation rules.`, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    saveBtn.disabled = false;
    addRuleBtn.disabled = false;
    reloadBtn.disabled = false;
  }
}

function addRuleRow() {
  ruleRows.unshift({
    _id: nextRowId++,
    is_new: true,
    canonical_name: "",
    rule_type: "home_office",
    params: {},
    source: "admin",
  });
  renderRuleRows();
}

function collectValidatedRules() {
  const clean = [];
  const seen = new Set();
  for (const row of ruleRows) {
    const name = (row.canonical_name || "").trim();
    if (!name) throw new Error("Every rule needs an invoice line name.");
    if (seen.has(name)) throw new Error(`Duplicate rule for: ${name}`);
    seen.add(name);
    const type = row.rule_type;
    const params = {};
    if (type === "single_branch") {
      if (!row.params.branch) throw new Error(`Choose a branch for ${name}.`);
      params.branch = row.params.branch;
    } else if (type === "split") {
      if (!row.params.branch) throw new Error(`Choose a split branch for ${name}.`);
      if (!row.params.amount) throw new Error(`Enter a split amount for ${name}.`);
      params.branch = row.params.branch;
      params.amount = row.params.amount;
    } else if (type === "unit_sequence") {
      if (!row.params.branches || !row.params.branches.length) throw new Error(`Add at least one branch for ${name}.`);
      params.branches = row.params.branches;
    } else if (type === "dynamic_user") {
      if (!row.params.match_tokens || !row.params.match_tokens.length) throw new Error(`Add at least one license token for ${name}.`);
      params.match_tokens = row.params.match_tokens;
    }
    clean.push({ canonical_name: name, rule_type: type, params });
  }
  return clean;
}

async function saveRules() {
  let payload = [];
  try {
    payload = collectValidatedRules();
  } catch (error) {
    setStatus(error.message, "error");
    return;
  }
  setStatus(`Saving ${payload.length} allocation rules...`);
  saveBtn.disabled = true;
  try {
    const response = await fetch("/api/integricom/allocation-rules/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Failed to save rules.");
    setStatus(`Saved ${result.saved} allocation rules.`, "ok");
    await loadRules();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    saveBtn.disabled = false;
  }
}

async function deleteRuleRow(row) {
  if (!window.confirm(`Delete the rule for "${row.canonical_name}"? This line will prompt for a rule again on the next upload.`)) {
    return;
  }
  setStatus(`Deleting rule for ${row.canonical_name}...`);
  try {
    const response = await fetch("/api/integricom/allocation-rules/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ canonical_names: [row.canonical_name] }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Failed to delete rule.");
    ruleRows = ruleRows.filter((item) => item._id !== row._id);
    renderRuleRows();
    setStatus(`Deleted rule for ${row.canonical_name}.`, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

function onVendorChange() {
  if (isRulesMode()) {
    loadRules();
  } else {
    loadUsers();
  }
}

function onReload() {
  isRulesMode() ? loadRules() : loadUsers();
}

function onSearch() {
  isRulesMode() ? renderRuleRows() : renderRows();
}

function onSave() {
  isRulesMode() ? saveRules() : saveUsers();
}

async function loadUsers() {
  const vendor = vendorSelect.value;
  updateVendorActions();
  setStatus(`Loading ${vendor} users...`);
  saveBtn.disabled = true;
  addBtn.disabled = true;
  reloadBtn.disabled = true;
  syncEntraBtn.disabled = true;

  try {
    const response = await fetch(`/api/${vendor}/users?active_only=true`);
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Failed to load users.");
    }
    const data = await response.json();
    userRows = (data.users || []).map((row) => ({
      _id: nextRowId++,
      is_new: false,
      email: row.email || "",
      first_name: row.first_name || "",
      last_name: row.last_name || "",
      branch: row.branch || "Home Office",
      last_seen_at: row.last_seen_at || "",
      updated_at: row.updated_at || "",
    }));
    renderRows();
    setStatus(`Loaded ${userRows.length} active ${vendor} users.`, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    saveBtn.disabled = false;
    addBtn.disabled = false;
    reloadBtn.disabled = false;
    syncEntraBtn.disabled = vendorSelect.value !== "integricom";
  }
}

function addUserRow() {
  userRows.unshift({
    _id: nextRowId++,
    is_new: true,
    email: "",
    first_name: "",
    last_name: "",
    branch: "Home Office",
    last_seen_at: "",
    updated_at: "",
  });
  renderRows();
}

function collectValidatedRows() {
  const cleanRows = [];
  const seenEmails = new Set();

  for (const row of userRows) {
    const email = (row.email || "").trim().toLowerCase();
    const firstName = (row.first_name || "").trim();
    const lastName = (row.last_name || "").trim();
    const branch = (row.branch || "").trim();

    if (!email) {
      throw new Error("Every row must include an email.");
    }
    if (!branch) {
      throw new Error(`Branch is required for ${email}.`);
    }
    if (seenEmails.has(email)) {
      throw new Error(`Duplicate email found: ${email}`);
    }
    seenEmails.add(email);

    cleanRows.push({
      email,
      first_name: firstName,
      last_name: lastName,
      branch,
    });
  }
  return cleanRows;
}

async function saveUsers() {
  const vendor = vendorSelect.value;
  const endpoint = vendor === "adobe" ? "/api/adobe/users/save" : "/api/integricom/users/save";
  let payload = [];
  try {
    payload = collectValidatedRows();
  } catch (error) {
    setStatus(error.message, "error");
    return;
  }

  setStatus(`Saving ${payload.length} ${vendor} users...`);
  saveBtn.disabled = true;

  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Failed to save users.");
    }
    const result = await response.json();
    setStatus(`Saved ${result.saved} users.`, "ok");
    await loadUsers();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    saveBtn.disabled = false;
  }
}

async function deactivateRow(row) {
  const vendor = vendorSelect.value;
  const endpoint = vendor === "adobe" ? "/api/adobe/users/deactivate" : "/api/integricom/users/deactivate";
  const email = (row.email || "").trim().toLowerCase();
  if (!email) {
    setStatus("Cannot deactivate a row with a blank email.", "error");
    return;
  }

  if (!window.confirm(`Deactivate ${email}?`)) {
    return;
  }

  setStatus(`Deactivating ${email}...`);
  try {
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ emails: [email] }),
    });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Failed to deactivate user.");
    }
    userRows = userRows.filter((item) => item._id !== row._id);
    renderRows();
    setStatus(`Deactivated ${email}.`, "ok");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function syncFromEntra() {
  if (vendorSelect.value !== "integricom") {
    setStatus("Entra sync is only available for Integricom directory.", "error");
    return;
  }

  if (!window.confirm("Sync Integricom users from Microsoft Entra now?")) {
    return;
  }

  setStatus("Syncing from Microsoft Entra...");
  syncEntraBtn.disabled = true;
  try {
    const response = await fetch("/api/integricom/sync/entra", { method: "POST" });
    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || "Entra sync failed.");
    }
    const result = await response.json();
    const warningSuffix = result.warnings?.length ? ` Warnings: ${result.warnings.join(" | ")}` : "";
    setStatus(
      `Entra sync complete. Synced ${result.synced} users from ${result.users_scanned} scanned.${warningSuffix}`,
      "ok",
    );
    await loadUsers();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    syncEntraBtn.disabled = vendorSelect.value !== "integricom";
  }
}

async function importAdobeStartingList() {
  if (vendorSelect.value !== "adobe") {
    setStatus("Spreadsheet import is only available for Adobe directory.", "error");
    return;
  }

  const file = importFileInput.files && importFileInput.files[0];
  if (!file) {
    setStatus("Choose an Adobe mapping file first.", "error");
    return;
  }

  const payload = new FormData();
  payload.append("mapping_file", file);

  setStatus(`Importing ${file.name}...`);
  importBtn.disabled = true;
  try {
    const response = await fetch("/api/adobe/users/import", {
      method: "POST",
      body: payload,
    });
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "Import failed.");
    }

    const warningSuffix = result.warnings?.length ? ` Warnings: ${result.warnings.join(" | ")}` : "";
    setStatus(`Imported ${result.imported} Adobe users from ${result.filename}.${warningSuffix}`, "ok");
    importFileInput.value = "";
    await loadUsers();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    importBtn.disabled = false;
  }
}

function initializeResizableTables() {
  const tables = document.querySelectorAll("table.resizable-table");
  tables.forEach((table) => {
    table.querySelectorAll("thead th").forEach((headerCell) => {
      if (headerCell.dataset.resizable === "true") {
        return;
      }
      headerCell.dataset.resizable = "true";

      const resizer = document.createElement("span");
      resizer.className = "col-resizer";

      let startX = 0;
      let startWidth = 0;

      const handlePointerMove = (event) => {
        const delta = event.clientX - startX;
        const nextWidth = Math.max(110, startWidth + delta);
        headerCell.style.width = `${nextWidth}px`;
      };

      const handlePointerUp = () => {
        document.body.classList.remove("col-resize-active");
        window.removeEventListener("pointermove", handlePointerMove);
        window.removeEventListener("pointerup", handlePointerUp);
      };

      resizer.addEventListener("pointerdown", (event) => {
        event.preventDefault();
        startX = event.clientX;
        startWidth = headerCell.getBoundingClientRect().width;
        headerCell.style.width = `${startWidth}px`;
        document.body.classList.add("col-resize-active");
        window.addEventListener("pointermove", handlePointerMove);
        window.addEventListener("pointerup", handlePointerUp);
      });

      headerCell.appendChild(resizer);
    });
  });
}

vendorSelect.addEventListener("change", onVendorChange);
searchInput.addEventListener("input", onSearch);
reloadBtn.addEventListener("click", onReload);
syncEntraBtn.addEventListener("click", syncFromEntra);
importBtn.addEventListener("click", () => importFileInput.click());
importFileInput.addEventListener("change", importAdobeStartingList);
addBtn.addEventListener("click", addUserRow);
addRuleBtn.addEventListener("click", addRuleRow);
saveBtn.addEventListener("click", onSave);

initializeResizableTables();
updateVendorActions();
loadUsers();

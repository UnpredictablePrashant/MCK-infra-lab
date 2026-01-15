const form = document.getElementById("compare-form");
const submitBtn = document.getElementById("submit-btn");
const statusBox = document.getElementById("status");
const resultsBox = document.getElementById("results");
const summary = document.getElementById("summary");
const elapsed = document.getElementById("elapsed");
const resultList = document.getElementById("result-list");
const logBox = document.getElementById("log-box");
const logCount = document.getElementById("log-count");
const refreshStudentsBtn = document.getElementById("refresh-students");
const studentsList = document.getElementById("students-list");
const refreshLeaderboardBtn = document.getElementById("refresh-leaderboard");
const leaderboardList = document.getElementById("leaderboard-list");
const compareTimer = document.getElementById("compare-timer");
const autoFillTimer = document.getElementById("auto-fill-timer");
const autoFillEntry = document.getElementById("auto-fill-entry");
const labContext = document.getElementById("lab-context");
const activeLabId = labContext ? labContext.dataset.labId : null;

let socket;
const MAX_LOG_LINES = 200;
let autoFillRemaining = null;

function setStatus(message, kind) {
  if (!statusBox) {
    return;
  }
  statusBox.textContent = message;
  statusBox.classList.remove("hidden", "ok", "error");
  statusBox.classList.add(kind);
}

function clearStatus() {
  if (!statusBox) {
    return;
  }
  statusBox.classList.add("hidden");
  statusBox.textContent = "";
  statusBox.classList.remove("ok", "error");
}

function renderResults(data) {
  if (!resultsBox || !summary || !elapsed || !resultList) {
    return;
  }
  resultsBox.classList.remove("hidden");
  summary.textContent =
    data.status === "match"
      ? "All endpoints match the baseline."
      : "Differences detected. Review endpoint details.";
  summary.classList.remove("match", "mismatch");
  summary.classList.add(data.status === "match" ? "match" : "mismatch");
  elapsed.textContent = `Completed in ${data.elapsed_ms} ms`;

  resultList.innerHTML = "";
  data.results.forEach((item) => {
    const card = document.createElement("div");
    card.className = "result-card";

    const title = document.createElement("strong");
    title.textContent = `${item.endpoint} — ${item.status}`;
    card.appendChild(title);

    const meta = document.createElement("div");
    meta.className = "meta";

    if (item.status === "match") {
      meta.textContent = "Payload matches baseline.";
    } else if (item.status === "error") {
      meta.textContent = `Baseline: ${item.baseline_error || "ok"} | Target: ${
        item.target_error || "ok"
      }`;
    } else if ("missing_count" in item) {
      meta.textContent = `Missing rows: ${item.missing_count} | Extra rows: ${item.extra_count}`;
    } else {
      meta.textContent = "Payload differs from baseline.";
    }

    card.appendChild(meta);
    resultList.appendChild(card);
  });
}

function renderStudents(data) {
  if (!studentsList) {
    return;
  }
  studentsList.innerHTML = "";
  if (!data.students.length) {
    const empty = document.createElement("div");
    empty.className = "student-card";
    empty.textContent = "No student apps registered yet.";
    studentsList.appendChild(empty);
    return;
  }
  data.students.forEach((student) => {
    const card = document.createElement("div");
    card.className = "student-card";
    const title = document.createElement("strong");
    title.textContent = student.name;
    const url = document.createElement("span");
    url.textContent = student.url;
    card.appendChild(title);
    card.appendChild(url);
    studentsList.appendChild(card);
  });
}

function renderLeaderboard(data) {
  if (!leaderboardList) {
    return;
  }
  leaderboardList.innerHTML = "";
  if (!data.leaderboard.length) {
    const empty = document.createElement("div");
    empty.className = "student-card";
    empty.textContent = "No leaderboard entries yet.";
    leaderboardList.appendChild(empty);
    return;
  }

  data.leaderboard.forEach((entry) => {
    const card = document.createElement("div");
    card.className = "student-card";

    const title = document.createElement("strong");
    title.textContent = entry.name || "Unknown";

    const url = document.createElement("span");
    url.textContent = entry.url;

    const status = document.createElement("span");
    status.className = "sync";
    if (entry.sync === true) {
      status.textContent = "In sync";
    } else if (entry.sync === false) {
      status.textContent = "Out of sync";
      status.classList.add("off");
    } else {
      status.textContent = "Pending";
      status.classList.add("pending");
    }

    card.appendChild(title);
    card.appendChild(url);
    card.appendChild(status);
    leaderboardList.appendChild(card);
  });
}

async function refreshStudents() {
  if (!studentsList) {
    return;
  }
  try {
    const query = activeLabId ? `?lab=${encodeURIComponent(activeLabId)}` : "";
    const response = await fetch(`/api/students${query}`);
    const data = await response.json();
    renderStudents(data);
  } catch (err) {
    console.error(err);
  }
}

async function refreshLeaderboard() {
  if (!leaderboardList) {
    return;
  }
  try {
    const query = activeLabId ? `?lab=${encodeURIComponent(activeLabId)}` : "";
    const response = await fetch(`/api/leaderboard${query}`);
    const data = await response.json();
    renderLeaderboard(data);
  } catch (err) {
    console.error(err);
  }
}

if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearStatus();
    if (resultsBox) {
      resultsBox.classList.add("hidden");
    }

    const name = form.elements.name.value.trim();
    const url = form.elements.url.value.trim();
    const labId = form.dataset.labId || activeLabId;
    const compareEnabled = form.dataset.compareEnabled === "true";

    if (!name || !url) {
      setStatus("Please provide your name and app URL.", "error");
      return;
    }

    submitBtn.disabled = true;
    setStatus("Running comparison...", "ok");

    try {
      const response = await fetch("/api/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, url, lab: labId }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.error || "Unable to compare.");
      }
      if (compareEnabled && data.compare_enabled) {
        setStatus(`Comparison complete for ${data.name}.`, "ok");
        renderResults(data);
      } else {
        setStatus(`Submission saved for ${data.name}.`, "ok");
      }
      refreshStudents();
      refreshLeaderboard();
    } catch (err) {
      setStatus(err.message || "Something went wrong.", "error");
    } finally {
      submitBtn.disabled = false;
    }
  });
}

function addLogLine(message) {
  if (!logBox) {
    return;
  }
  const line = document.createElement("div");
  line.className = "log-line";
  line.textContent = message;
  logBox.appendChild(line);
  while (logBox.children.length > MAX_LOG_LINES) {
    logBox.removeChild(logBox.firstChild);
  }
  logBox.scrollTop = logBox.scrollHeight;
  if (logCount) {
    logCount.textContent = `${logBox.children.length} entries`;
  }
}

function connectSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  socket = new WebSocket(`${protocol}://${window.location.host}/ws`);

  socket.addEventListener("message", (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.event === "fill_log") {
        addLogLine(data.payload.message);
      } else if (data.event === "fill_start") {
        addLogLine(data.payload.message);
      } else if (data.event === "fill_done") {
        addLogLine(data.payload.message);
      } else if (data.event === "fill_error") {
        addLogLine(data.payload.message);
      } else if (data.event === "fill_meta") {
        if (autoFillTimer) {
          const nextIn = data.payload.next_in_seconds;
          if (nextIn === null || nextIn === undefined) {
            const status = data.payload.status || "pending";
            autoFillTimer.textContent =
              status === "paused" ? "Automation paused" : "Next auto-fill time pending";
            autoFillRemaining = null;
          } else {
            autoFillTimer.dataset.nextSeconds = String(nextIn);
            autoFillTimer.textContent = `Next auto-fill in ${nextIn}s`;
            autoFillRemaining = nextIn;
          }
        }
        if (autoFillEntry) {
          autoFillEntry.textContent = data.payload.entry_text || "Pending";
        }
      }
    } catch (err) {
      console.error(err);
    }
  });

  socket.addEventListener("close", () => {
    setTimeout(connectSocket, 2000);
  });
}

function startCompareCountdown() {
  if (!compareTimer) {
    return;
  }
  const intervalSeconds = Number(compareTimer.dataset.intervalSeconds || "0");
  if (!intervalSeconds) {
    return;
  }
  let remaining = intervalSeconds;
  const tick = () => {
    compareTimer.textContent = `Next sync check in ${remaining}s`;
    remaining -= 1;
    if (remaining < 0) {
      remaining = intervalSeconds;
      refreshLeaderboard();
    }
  };
  tick();
  setInterval(tick, 1000);
}

function startAutoFillCountdown() {
  if (!autoFillTimer) {
    return;
  }
  autoFillRemaining = Number(autoFillTimer.dataset.nextSeconds || "0") || null;
  const tick = () => {
    if (autoFillRemaining === null) {
      return;
    }
    autoFillTimer.textContent = `Next auto-fill in ${autoFillRemaining}s`;
    autoFillRemaining -= 1;
    if (autoFillRemaining < 0) {
      autoFillRemaining = 0;
    }
  };
  tick();
  setInterval(tick, 1000);
}

if (logBox) {
  connectSocket();
}
refreshStudents();
refreshLeaderboard();
startCompareCountdown();
startAutoFillCountdown();

if (refreshStudentsBtn) {
  refreshStudentsBtn.addEventListener("click", refreshStudents);
}
if (refreshLeaderboardBtn) {
  refreshLeaderboardBtn.addEventListener("click", refreshLeaderboard);
}

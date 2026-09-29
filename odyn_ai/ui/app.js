(() => {
  const $ = (id) => document.getElementById(id);
  const histories = new Map();
  let project = null;
  let file = null;
  let form = null;
  let formAppId = null;
  let lastAgentReport = null;

  async function loadAgents() {
    const r = await fetch("/api/agents", { cache: "no-store" });
    if (!r.ok) throw new Error("Nie udało się pobrać agentów.");
    const data = await r.json();
    const select = $("agent-select");
    const selected = select.value;
    select.replaceChildren(...data.agents.map((a) => new Option(a.name, a.id)));
    if (data.agents.some((a) => a.id === selected)) select.value = selected;
    if (!select.value && data.agents.length) select.value = data.agents[0].id;
    return data.agents;
  }

  async function loadProjects() {
    const r = await fetch("/api/apps");
    if (!r.ok) throw new Error("Nie udało się pobrać projektów.");
    const projects = (await r.json()).apps;
    const s = $("project-select");
    s.replaceChildren();
    if (!projects.length) s.add(new Option("Brak projektu", ""));
    for (const p of projects) s.add(new Option(`${p.name} · ${p.platform === "android" ? "ANDROID NATIVE" : "WEB"} · ${p.mode === "code" ? "CODE" : "NO CODE"}`, p.app_id));
  }

  async function status() {
    try {
      const r = await fetch("/api/status");
      const e = (await r.json()).engine;
      $("engine-badge").textContent = e.true_dual_gguf ? "PODWÓJNY GGUF · DEKODOWANIE SPEKULATYWNE" : e.backend === "server" ? "SILNIK SERWEROWY" : "SILNIK PYTHON";
      $("status").textContent = e.true_dual_gguf ? "Dwa modele GGUF + llama-server: dekodowanie spekulatywne jest aktywne." : e.backend === "python" ? "Tryb Python: aktywne lokalne dekodowanie z mechanizmem prompt-lookup." : "Tryb serwerowy: lokalny silnik llama-server.";
    } catch (e) { $("status").textContent = "Błąd odczytu statusu silnika."; }
  }

  function message(text, role) {
    const el = document.createElement("div");
    el.className = "message " + role;
    el.textContent = text;
    $("chat-history").appendChild(el);
    $("chat-history").scrollTop = $("chat-history").scrollHeight;
    return el;
  }

  async function send() {
    const text = $("user-input").value.trim();
    if (!text) return;
    message(text, "user");
    $("user-input").value = "";
    const out = message("Przetwarzanie…", "assistant");
    let reply = "";
    try {
      const r = await fetch("/chat/stream", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message:text, agent_id:$("agent-select").value, history:histories.get($("agent-select").value) || []})});
      if (!r.ok) throw new Error("Błąd HTTP " + r.status);
      const reader = r.body.getReader(), decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const x = await reader.read();
        if (x.done) break;
        buffer += decoder.decode(x.value, {stream:true});
        const events = buffer.split("\n\n"); buffer = events.pop();
        for (const event of events) {
          const lines = event.split("\n");
          const type = (lines.find(x => x.startsWith("event:")) || "").slice(6).trim();
          const data = lines.filter(x => x.startsWith("data:")).map(x => x.slice(5).trim()).join("\n");
          if (type === "token") { reply += data; out.textContent = reply; }
          if (type === "error") throw new Error(data);
        }
      }
      const agentId = $("agent-select").value;
      lastAgentReport = { agentId, title: "Raport · " + ($("agent-select").selectedOptions[0]?.textContent || "ODYN AI"), content: reply };
      if (!$("export-filename").value.trim()) $("export-filename").value = "raport-odyn";
      const agentHistory = histories.get(agentId) || [];
      agentHistory.push({role:"user",content:text},{role:"assistant",content:reply});
      histories.set(agentId, agentHistory.slice(-40));
    } catch (e) { out.textContent = "[Błąd ODYN AI] " + e.message; }
  }



  function initVoiceInput() {
    const voiceBtn = $("voice-btn");
    const voiceStatus = $("voice-status");
    const userInput = $("user-input");
    if (!voiceBtn || !voiceStatus || !userInput) return;

    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const nativeSupported = Boolean(navigator.mediaDevices?.getUserMedia && window.MediaRecorder);

    const setUi = (recording, status) => {
      voiceBtn.classList.toggle("recording", recording);
      voiceBtn.setAttribute("aria-pressed", String(recording));
      voiceBtn.textContent = recording ? "⏹ Zatrzymaj" : "🎤 Głos";
      voiceBtn.setAttribute("aria-label", recording ? "Zatrzymaj nagrywanie" : "Włącz dyktowanie");
      if (status) voiceStatus.textContent = status;
    };

    if (nativeSupported) {
      let recorder = null;
      let chunks = [];
      let baseText = "";

      const pickMimeType = () => {
        const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/ogg"];
        return types.find((type) => MediaRecorder.isTypeSupported(type)) || "";
      };

      const uploadRecording = async (blob) => {
        if (!blob.size) {
          setUi(false, "Głos: puste nagranie");
          return;
        }
        voiceStatus.textContent = "Głos: transkrybuję lokalnie…";
        const formData = new FormData();
        const extension = blob.type.includes("ogg") ? "ogg" : "webm";
        formData.append("file", blob, "odyn-voice." + extension);
        try {
          const response = await fetch("/api/stt/transcribe", { method: "POST", body: formData });
          if (!response.ok) {
            const detail = await response.text();
            throw new Error(detail || ("Błąd HTTP " + response.status));
          }
          const data = await response.json();
          const transcript = String(data.text || "").trim();
          userInput.value = [baseText, transcript].filter(Boolean).join(" ");
          userInput.dispatchEvent(new Event("input", { bubbles: true }));
          setUi(false, transcript ? "Głos: tekst gotowy do wysłania" : "Głos: nie rozpoznano mowy");
        } catch (error) {
          setUi(false, "Głos: błąd transkrypcji");
          voiceStatus.title = error.message;
        }
      };

      voiceBtn.addEventListener("click", async () => {
        if (recorder && recorder.state === "recording") {
          recorder.stop();
          return;
        }
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
          chunks = [];
          baseText = userInput.value.trim();
          const mimeType = pickMimeType();
          recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
          recorder.ondataavailable = (event) => {
            if (event.data.size) chunks.push(event.data);
          };
          recorder.onstop = async () => {
            stream.getTracks().forEach((track) => track.stop());
            const blob = new Blob(chunks, { type: recorder.mimeType || mimeType || "audio/webm" });
            await uploadRecording(blob);
            recorder = null;
          };
          recorder.onerror = () => {
            stream.getTracks().forEach((track) => track.stop());
            setUi(false, "Głos: błąd nagrywania");
            recorder = null;
          };
          recorder.start();
          setUi(true, "Głos: nagrywam…");
        } catch (error) {
          setUi(false, "Głos: brak zgody na mikrofon");
          voiceStatus.title = error.message;
        }
      });
      voiceStatus.textContent = "Głos: lokalny Whisper";
      return;
    }

    if (!SpeechRecognition) {
      voiceBtn.disabled = true;
      voiceBtn.title = "Ta przeglądarka nie obsługuje nagrywania ani rozpoznawania mowy.";
      voiceStatus.textContent = "Głos: niedostępny";
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.lang = "pl-PL";
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;
    let baseText = "";
    let finalText = "";

    voiceBtn.addEventListener("click", () => {
      if (voiceBtn.classList.contains("recording")) {
        recognition.stop();
        return;
      }
      baseText = userInput.value.trim();
      finalText = "";
      try { recognition.start(); } catch (_) { voiceStatus.textContent = "Głos: nie można uruchomić"; }
    });
    recognition.onstart = () => setUi(true, "Głos: słucham…");
    recognition.onresult = (event) => {
      let interimText = "";
      let completedText = finalText;
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const transcript = event.results[i][0].transcript.trim();
        if (event.results[i].isFinal) completedText = (completedText + " " + transcript).trim();
        else interimText = (interimText + " " + transcript).trim();
      }
      finalText = completedText;
      userInput.value = [baseText, finalText, interimText].filter(Boolean).join(" ");
    };
    recognition.onerror = (event) => {
      const messages = {"not-allowed":"Głos: brak zgody na mikrofon","no-speech":"Głos: nie wykryto mowy","audio-capture":"Głos: brak mikrofonu","network":"Głos: błąd usługi"};
      setUi(false, messages[event.error] || "Głos: błąd rozpoznawania");
    };
    recognition.onend = () => {
      setUi(false, finalText.trim() ? "Głos: tekst gotowy do wysłania" : "Głos: gotowy");
    };
    voiceStatus.textContent = "Głos: tryb awaryjny";
  }

  async function exportReport(format) {
    if (!lastAgentReport || !lastAgentReport.content.trim()) {
      $("status").textContent = "Najpierw wygeneruj raport odpowiedzią agenta.";
      return;
    }
    const requestedFormat = format || $("export-format").value;
    const filename = $("export-filename").value.trim() || "raport-odyn";
    const title = lastAgentReport.title || "Raport ODYN";
    const payload = {
      format: requestedFormat,
      title,
      content: lastAgentReport.content,
      filename,
    };
    $("terminal-output").textContent = "Przygotowywanie eksportu " + requestedFormat.toUpperCase() + "…";
    try {
      const r = await fetch("/api/agents/" + encodeURIComponent(lastAgentReport.agentId) + "/reports/export", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
      });
      if (!r.ok) {
        const detail = await r.text();
        throw new Error(detail || ("Błąd HTTP " + r.status));
      }
      const blob = await r.blob();
      const extension = requestedFormat === "docx" ? "docx" : requestedFormat;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = filename.replace(/\.(pdf|docx|xlsx)$/i, "") + "." + extension;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(a.href);
      $("terminal-output").textContent = "Eksport zakończony: " + a.download;
      $("status").textContent = "Raport pobrany jako " + requestedFormat.toUpperCase() + ".";
    } catch (e) {
      $("terminal-output").textContent = "Błąd eksportu: " + e.message;
      $("status").textContent = "Nie udało się pobrać raportu.";
    }
  }

  async function openNoCodeForm() {
    const id = $("project-select").value;
    if (!id) { $("status").textContent = "Wybierz najpierw aplikację Web w trybie No Code."; return; }
    const project = (await (await fetch("/api/apps")).json()).apps.find(x => x.app_id === id);
    if (!project || project.platform !== "web" || project.mode !== "no_code") { $("status").textContent = "Builder formularzy wymaga projektu Web + No Code."; return; }
    formAppId = id;
    $("form-project-name").textContent = project.name;
    $("no-code-builder").hidden = false;
    $("chat-history").hidden = true; $("chat-form").hidden = true;
  }

  function renderFormCanvas() {
    const canvas = $("form-canvas-fields"); canvas.replaceChildren();
    if (!form) return;
    form.fields.forEach((field, index) => {
      const card = document.createElement("button");
      card.type = "button"; card.className = "form-field-card";
      card.innerHTML = `<strong>${field.label}</strong><span>${field.type}${field.required ? " · wymagane" : ""}</span>`;
      card.onclick = () => inspectField(index);
      canvas.appendChild(card);
    });
    $("form-preview").innerHTML = form ? formPreviewHtml() : "";
  }

  function inspectField(index) {
    const field = form.fields[index];
    const box = $("form-inspector-content"); box.replaceChildren();
    const label = document.createElement("label"); label.textContent = "Etykieta";
    const input = document.createElement("input"); input.value = field.label;
    input.onchange = () => { field.label = input.value; renderFormCanvas(); };
    label.appendChild(input); box.appendChild(label);
    const req = document.createElement("label"); req.textContent = "Wymagane";
    const checkbox = document.createElement("input"); checkbox.type = "checkbox"; checkbox.checked = field.required;
    checkbox.onchange = () => { field.required = checkbox.checked; renderFormCanvas(); };
    req.appendChild(checkbox); box.appendChild(req);
    const validation = document.createElement("input"); validation.placeholder = "Walidacja, np. email"; validation.value = field.validation || "";
    validation.onchange = () => { field.validation = validation.value; renderFormCanvas(); }; box.appendChild(validation);
    if (["select","radio"].includes(field.type)) {
      const options = document.createElement("textarea"); options.value = field.options.join("\n"); options.placeholder = "Jedna opcja w wierszu";
      options.onchange = () => { field.options = options.value.split("\n").map(x => x.trim()).filter(Boolean); renderFormCanvas(); }; box.appendChild(options);
    }
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#x27;");
  }

  function formPreviewHtml() {
    return `<form class="live-form"><h3>${escapeHtml(form.name)}</h3>${form.fields.map(f => {
      const req = f.required ? " required" : "";
      const label = escapeHtml(f.label);
      if (f.type === "textarea") return `<label>${label}<textarea${req}>${escapeHtml(f.default || "")}</textarea></label>`;
      if (f.type === "select") return `<label>${label}<select${req}>${f.options.map(o=>`<option>${escapeHtml(o)}</option>`).join("")}</select></label>`;
      if (f.type === "checkbox") return `<label><input type="checkbox"${req}> ${label}</label>`;
      return `<label>${label}<input type="${escapeHtml(f.type)}"${req}></label>`;
    }).join("")}</form>`;
  }

  async function createForm() {
    if (!formAppId) return;
    const name = prompt("Nazwa formularza:", "Nowy formularz");
    if (!name) return;
    const r = await fetch("/api/apps/"+encodeURIComponent(formAppId)+"/forms", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name})});
    if (!r.ok) throw new Error("Nie udało się utworzyć formularza.");
    form = await r.json(); renderFormCanvas();
  }

  async function addField(type) {
    if (!form) { $("status").textContent = "Najpierw kliknij „Utwórz formularz”."; return; }
    const label = prompt("Etykieta pola:", type === "email" ? "Adres e-mail" : "Nowe pole");
    if (!label) return;
    const options = ["select","radio"].includes(type) ? ["Opcja 1","Opcja 2"] : [];
    const r = await fetch("/api/forms/"+encodeURIComponent(form.form_id)+"/fields",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({field_type:type,label,options})});
    if (!r.ok) throw new Error("Nie udało się dodać pola.");
    form = await (await fetch("/api/forms/"+encodeURIComponent(form.form_id))).json(); renderFormCanvas();
  }

  function openBuilder(kind) {
    const f = $("dialog-fields");
    f.replaceChildren();
    const isAgent = kind === "agent";
    $("dialog-title").textContent = isAgent ? "Kreator agentów" : "Kreator aplikacji";
    const add = (id, label, type="input", options="") => {
      const w = document.createElement("label"); w.className = "dialog-field"; w.htmlFor=id; w.textContent=label;
      const c = type === "textarea" ? document.createElement("textarea") : document.createElement(type);
      c.id=id; c.name=id; c.required=true;
      if (type === "select") c.innerHTML=options;
      w.appendChild(c); f.appendChild(w); return c;
    };
    if (!isAgent) {
      add("app-mode","Tryb tworzenia","select",'<option value="no_code">Tryb No Code</option><option value="code">Tryb Code</option>');
      add("app-platform","Platforma","select",'<option value="web">WEB</option><option value="android">ANDROID NATIVE</option>');
      add("app-name","Nazwa aplikacji");
      add("app-description","Opis aplikacji","textarea");
    } else {
      const mode=add("agent-mode","Tryb tworzenia","select",'<option value="no_code">Tryb bez kodu</option><option value="code">Tryb kodowy</option>');
      add("agent-id","Identyfikator agenta"); add("agent-name","Nazwa agenta");
      const prompt=add("agent-instructions","Instrukcje agenta","textarea");
      const code=add("agent-code","Kod agenta","textarea"); code.hidden=true; code.required=false;
      mode.onchange=()=>{ const isCode=mode.value==="code"; prompt.parentElement.hidden=isCode; prompt.required=!isCode; code.parentElement.hidden=!isCode; code.required=isCode; };
    }
    $("dialog-submit").dataset.builder=kind;
    $("builder-dialog").showModal();
  }

  async function openIde(id) {
    const appId=id || $("project-select").value;
    if (!appId) { $("status").textContent="Najpierw utwórz lub wybierz projekt."; return; }
    const r=await fetch("/api/apps/"+encodeURIComponent(appId)+"/workspace");
    if (!r.ok) throw new Error("Nie udało się otworzyć projektu.");
    project=await r.json();
    $("ide").hidden=false; $("chat-history").hidden=true; $("chat-form").hidden=true;
    $("ide-project-name").textContent=`${project.name} · ${project.platform === "android" ? "ANDROID NATIVE" : "WEB"} · ${project.mode === "code" ? "CODE" : "NO CODE"}`;
    renderFiles();
  }

  function renderFiles() {
    const tree=$("file-tree"); tree.replaceChildren();
    Object.keys(project.files).sort().forEach(path=>{
      const b=document.createElement("button"); b.className="file-item"; b.textContent=path; b.onclick=()=>selectFile(path); tree.appendChild(b);
    });
  }

  function selectFile(path) { file=path; $("editor-path").textContent=path; $("code-editor").value=project.files[path] || ""; }

  async function saveFile() {
    if (!project || !file) return;
    const content=$("code-editor").value;
    const r=await fetch("/api/apps/"+encodeURIComponent(project.app_id)+"/files",{method:"PUT",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:file,content})});
    if (!r.ok) throw new Error("Nie udało się zapisać pliku.");
    project.files[file]=content; $("terminal-output").textContent="Zapisano: "+file;
  }

  function ideAction(action) {
    if (!project) return;
    const cmd=project.platform==="android" ? {run:"./gradlew :app:installDebug",build:"./gradlew assembleDebug",test:"./gradlew test"} : {run:"npm run dev",build:"npm run build",test:"npm test"};
    $("terminal-output").textContent=`${action.toUpperCase()} · ${project.platform === "android" ? "ANDROID NATIVE" : "WEB"}\n\n${cmd[action]}\n\nPolecenie przygotowane dla projektu.`;
  }

  initVoiceInput();
  $("chat-form").onsubmit=e=>{e.preventDefault();send();};
  $("user-input").onkeydown=e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}};
  $("status-btn").onclick=status;
  $("agent-select").onchange=()=>{
    const agentId=$("agent-select").value;
    histories.set(agentId, (histories.get(agentId) || []).slice(-40));
    $("chat-history").replaceChildren();
    $("status").textContent="Aktywny agent: "+($("agent-select").selectedOptions[0]?.textContent || agentId);
  };
  $("new-agent").onclick=()=>openBuilder("agent");
  $("new-app").onclick=()=>openBuilder("app");
  $("new-form").onclick=()=>openNoCodeForm().catch(e=>$("status").textContent=e.message);
  $("form-create").onclick=()=>createForm().catch(e=>$("status").textContent=e.message);
  $("form-close").onclick=()=>{$("no-code-builder").hidden=true;$("chat-history").hidden=false;$("chat-form").hidden=false;};
  document.querySelectorAll("[data-field-type]").forEach(b=>b.onclick=()=>addField(b.dataset.fieldType).catch(e=>$("status").textContent=e.message));
  $("open-ide").onclick=()=>openIde().catch(e=>$("status").textContent=e.message);
  $("project-select").onchange=()=>openIde().catch(e=>$("status").textContent=e.message);
  $("project-open").onclick=()=>openIde().catch(e=>$("status").textContent=e.message);
  $("ide-close").onclick=()=>{$("ide").hidden=true;$("chat-history").hidden=false;$("chat-form").hidden=false;};
  $("save-file").onclick=()=>saveFile().catch(e=>$("terminal-output").textContent=e.message);
  $("ide-run").onclick=()=>ideAction("run"); $("ide-build").onclick=()=>ideAction("build"); $("ide-test").onclick=()=>ideAction("test");
  $("export-report").onclick=()=>exportReport().catch(e=>$("status").textContent=e.message);
  document.querySelectorAll(".export-quick").forEach(b=>b.onclick=()=>{ $("export-format").value=b.dataset.exportFormat; exportReport(b.dataset.exportFormat); });
  $("ai-apply").onclick=()=>{const x=$("ai-command").value.trim(); if(x)$("terminal-output").textContent="ODYN Coding Agent:\n"+x; $("ai-command").value="";};

  $("builder-form").onsubmit=async e=>{
    if($("dialog-submit").value==="cancel") return;
    e.preventDefault();
    const f=new FormData(e.currentTarget), kind=$("dialog-submit").dataset.builder;
    const payload=kind==="agent"
      ? {agent_id:f.get("agent-id"),name:f.get("agent-name"),mode:f.get("agent-mode"),prompt:f.get("agent-instructions")||"",code:f.get("agent-code")||"",can_search:false}
      : {name:f.get("app-name"),description:f.get("app-description"),agent_id:$("agent-select").value,language:"pl",platform:f.get("app-platform"),mode:f.get("app-mode")};
    try {
      const r=await fetch(kind==="agent"?"/api/agents":"/api/apps",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
      if(!r.ok){const d=await r.json().catch(()=>({}));throw new Error(d.detail||"Nie udało się utworzyć elementu.");}
      $("builder-dialog").close(); if(kind==="agent") await loadAgents(); else await loadProjects();
      $("status").textContent=kind==="agent"?"Agent został utworzony.":"Projekt został utworzony.";
    } catch(e) { $("status").textContent="Błąd tworzenia: "+e.message; }
  };

  Promise.all([loadAgents(),loadProjects(),status()]).catch(e=>{$("status").textContent="Nie udało się uruchomić interfejsu.";console.error(e);});
  setInterval(()=>loadAgents().catch(()=>{}), 5000);
  setInterval(()=>loadProjects().catch(()=>{}), 5000);
})();

(() => {
  const $ = (id) => document.getElementById(id);
  const history = [];
  let project = null;
  let file = null;

  async function loadAgents() {
    const r = await fetch("/api/agents");
    if (!r.ok) throw new Error("Nie udało się pobrać agentów.");
    const data = await r.json();
    $("agent-select").replaceChildren(...data.agents.map((a) => new Option(a.name, a.id)));
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
      const r = await fetch("/chat/stream", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message:text, agent_id:$("agent-select").value, history})});
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
      history.push({role:"user",content:text},{role:"assistant",content:reply});
    } catch (e) { out.textContent = "[Błąd ODYN AI] " + e.message; }
  }

  function openBuilder(kind) {
    const f = $("dialog-fields");
    f.replaceChildren();
    const isAgent = kind === "agent";
    $("dialog-title").textContent = isAgent ? "Kreator agenta" : "Kreator aplikacji";
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

  $("chat-form").onsubmit=e=>{e.preventDefault();send();};
  $("user-input").onkeydown=e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();send();}};
  $("status-btn").onclick=status;
  $("new-agent").onclick=()=>openBuilder("agent");
  $("new-app").onclick=()=>openBuilder("app");
  $("open-ide").onclick=()=>openIde().catch(e=>$("status").textContent=e.message);
  $("project-select").onchange=()=>openIde().catch(e=>$("status").textContent=e.message);
  $("project-open").onclick=()=>openIde().catch(e=>$("status").textContent=e.message);
  $("ide-close").onclick=()=>{$("ide").hidden=true;$("chat-history").hidden=false;$("chat-form").hidden=false;};
  $("save-file").onclick=()=>saveFile().catch(e=>$("terminal-output").textContent=e.message);
  $("ide-run").onclick=()=>ideAction("run"); $("ide-build").onclick=()=>ideAction("build"); $("ide-test").onclick=()=>ideAction("test");
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
})();

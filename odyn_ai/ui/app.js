(() => {
  const $ = (id) => document.getElementById(id);
  const history = [];
  const select = $("agent-select");
  const chat = $("chat-history");
  const input = $("user-input");
  const dialog = $("builder-dialog");

  async function agents() {
    const response = await fetch("/api/agents");
    if (!response.ok) throw new Error("Nie udało się pobrać listy agentów.");
    const data = await response.json();
    select.replaceChildren(
      ...data.agents.map((agent) => {
        const option = document.createElement("option");
        option.value = agent.id;
        option.textContent = agent.name;
        return option;
      })
    );
  }

  async function status() {
    try {
      const response = await fetch("/api/status");
      if (!response.ok) throw new Error("Nie udało się pobrać statusu silnika.");
      const engine = (await response.json()).engine;

      $("engine-badge").textContent = engine.true_dual_gguf
        ? "PODWÓJNY GGUF · DEKODOWANIE SPEKULATYWNE"
        : engine.backend === "server"
          ? "SILNIK SERWEROWY"
          : "SILNIK PYTHON";

      $("status").textContent = engine.true_dual_gguf
        ? "Dwa modele GGUF + llama-server: dekodowanie spekulatywne jest aktywne."
        : engine.backend === "python"
          ? "Tryb Python: aktywne lokalne dekodowanie z mechanizmem prompt-lookup."
          : "Tryb serwerowy: lokalny silnik llama-server.";
    } catch (error) {
      $("status").textContent = "Błąd odczytu statusu silnika.";
      console.error(error);
    }
  }

  function msg(text, role) {
    const element = document.createElement("div");
    element.className = "message " + role;
    element.textContent = text;
    chat.appendChild(element);
    chat.scrollTop = chat.scrollHeight;
    return element;
  }

  async function send() {
    const text = input.value.trim();
    if (!text) return;

    msg(text, "user");
    input.value = "";
    input.style.height = "auto";

    const output = msg("Przetwarzanie…", "assistant");
    let reply = "";

    try {
      const response = await fetch("/chat/stream", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          message: text,
          agent_id: select.value,
          history
        })
      });

      if (!response.ok) {
        throw new Error("Żądanie zakończyło się błędem HTTP " + response.status + ".");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const {done, value} = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, {stream: true});
        const events = buffer.split("\n\n");
        buffer = events.pop();

        for (const event of events) {
          const lines = event.split("\n");
          const type = (lines.find((line) => line.startsWith("event:")) || "").slice(6).trim();
          const data = lines
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trim())
            .join("\n");

          if (type === "token") {
            reply += data;
            output.textContent = reply;
            chat.scrollTop = chat.scrollHeight;
          } else if (type === "error") {
            throw new Error(data.replace(/^\[ERROR\]\s*/, ""));
          }
        }
      }

      history.push(
        {role: "user", content: text},
        {role: "assistant", content: reply}
      );
    } catch (error) {
      output.textContent = "[Błąd ODYN AI] " + error.message;
    }
  }

  function openBuilder(kind) {
    const isAgent = kind === "agent";
    $("dialog-title").textContent = isAgent ? "Kreator agenta" : "Kreator aplikacji";
    $("dialog-fields").replaceChildren();

    if (!isAgent) {
      const fields = [
        ["app-name", "Nazwa aplikacji", "np. Mój Asystent"],
        ["app-description", "Opis aplikacji", "Krótki opis przeznaczenia aplikacji."]
      ];
      for (const [id, label, placeholder] of fields) {
        const wrapper = document.createElement("label");
        wrapper.className = "dialog-field";
        wrapper.htmlFor = id;
        wrapper.textContent = label;
        const control = id.endsWith("description") ? document.createElement("textarea") : document.createElement("input");
        control.id = id;
        control.name = id;
        control.placeholder = placeholder;
        control.required = true;
        wrapper.appendChild(control);
        $("dialog-fields").appendChild(wrapper);
      }
      $("dialog-submit").dataset.builder = kind;
      dialog.showModal();
      return;
    }

    const modeLabel = document.createElement("label");
    modeLabel.className = "dialog-field";
    modeLabel.htmlFor = "agent-mode";
    modeLabel.textContent = "Tryb tworzenia";
    const mode = document.createElement("select");
    mode.id = "agent-mode";
    mode.name = "agent-mode";
    mode.innerHTML = '<option value="no_code">Tryb bez kodu</option><option value="code">Tryb kodowy</option>';
    modeLabel.appendChild(mode);
    $("dialog-fields").appendChild(modeLabel);

    const fields = [
      ["agent-id", "Identyfikator agenta", "np. moj-agent"],
      ["agent-name", "Nazwa agenta", "np. Analityk"]
    ];
    for (const [id, label, placeholder] of fields) {
      const wrapper = document.createElement("label");
      wrapper.className = "dialog-field";
      wrapper.htmlFor = id;
      wrapper.textContent = label;
      const control = document.createElement("input");
      control.id = id;
      control.name = id;
      control.placeholder = placeholder;
      control.required = true;
      wrapper.appendChild(control);
      $("dialog-fields").appendChild(wrapper);
    }

    const promptWrapper = document.createElement("label");
    promptWrapper.className = "dialog-field";
    promptWrapper.htmlFor = "agent-instructions";
    promptWrapper.textContent = "Instrukcje agenta";
    const prompt = document.createElement("textarea");
    prompt.id = "agent-instructions";
    prompt.name = "agent-instructions";
    prompt.placeholder = "Opisz rolę, zasady i sposób działania agenta.";
    prompt.required = true;
    promptWrapper.appendChild(prompt);
    $("dialog-fields").appendChild(promptWrapper);

    const codeWrapper = document.createElement("label");
    codeWrapper.className = "dialog-field";
    codeWrapper.htmlFor = "agent-code";
    codeWrapper.textContent = "Kod agenta";
    const code = document.createElement("textarea");
    code.id = "agent-code";
    code.name = "agent-code";
    code.placeholder = "W trybie kodowym zapisz tutaj źródło agenta. Kod nie jest wykonywany bezpośrednio przez serwer.";
    code.rows = 14;
    code.hidden = true;
    code.required = false;
    codeWrapper.appendChild(code);
    $("dialog-fields").appendChild(codeWrapper);

    const searchLabel = document.createElement("label");
    searchLabel.className = "dialog-field";
    const search = document.createElement("input");
    search.type = "checkbox";
    search.id = "agent-search";
    search.name = "agent-search";
    searchLabel.append(search, document.createTextNode(" Agent może korzystać z wyszukiwania internetowego"));
    $("dialog-fields").appendChild(searchLabel);

    mode.onchange = () => {
      const codeMode = mode.value === "code";
      promptWrapper.hidden = codeMode;
      prompt.required = !codeMode;
      code.hidden = !codeMode;
      code.required = codeMode;
      searchLabel.hidden = codeMode;
      search.checked = false;
    };

    $("dialog-submit").dataset.builder = kind;
    dialog.showModal();
  }

  $("chat-form").onsubmit = (event) => {
    event.preventDefault();
    send();
  };

  input.oninput = () => {
    input.style.height = "auto";
    input.style.height = input.scrollHeight + "px";
  };

  input.onkeydown = (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  };

  $("status-btn").onclick = status;
  $("new-agent").onclick = () => openBuilder("agent");
  $("new-app").onclick = () => openBuilder("app");

  $("builder-form").onsubmit = async (event) => {
    if ($("dialog-submit").value === "cancel") return;

    event.preventDefault();
    const kind = $("dialog-submit").dataset.builder;
    const formData = new FormData(event.currentTarget);

    try {
      const payload = kind === "agent"
        ? {
            agent_id: formData.get("agent-id"),
            name: formData.get("agent-name"),
            mode: formData.get("agent-mode") || "no_code",
            prompt: formData.get("agent-instructions") || "",
            code: formData.get("agent-code") || "",
            can_search: Boolean(formData.get("agent-search"))
          }
        : {
            name: formData.get("app-name"),
            description: formData.get("app-description"),
            agent_id: select.value,
            language: "pl"
          };

      const endpoint = kind === "agent" ? "/api/agents" : "/api/apps";
      const response = await fetch(endpoint, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });

      if (!response.ok) {
        const detail = await response.json().catch(() => ({}));
        throw new Error(detail.detail || "Nie udało się utworzyć elementu.");
      }

      dialog.close();
      if (kind === "agent") await agents();
      $("status").textContent = kind === "agent"
        ? "Agent został utworzony."
        : "Aplikacja została utworzona.";
    } catch (error) {
      $("status").textContent = "Błąd tworzenia: " + error.message;
    }
  };

  Promise.all([agents(), status()]).catch((error) => {
    $("status").textContent = "Nie udało się uruchomić interfejsu.";
    console.error(error);
  });
})();

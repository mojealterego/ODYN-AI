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

    const fields = isAgent
      ? [
          ["agent-id", "Identyfikator agenta", "np. mój-agent"],
          ["agent-name", "Nazwa agenta", "np. Analityk"],
          ["agent-prompt", "Instrukcja agenta", "Opisz rolę i sposób działania agenta."]
        ]
      : [
          ["app-name", "Nazwa aplikacji", "np. Mój Asystent"],
          ["app-description", "Opis aplikacji", "Krótki opis przeznaczenia aplikacji."]
        ];

    for (const [id, label, placeholder] of fields) {
      const wrapper = document.createElement("label");
      wrapper.className = "dialog-field";
      wrapper.htmlFor = id;
      wrapper.textContent = label;

      const control = id.endsWith("prompt") || id.endsWith("description")
        ? document.createElement("textarea")
        : document.createElement("input");

      control.id = id;
      control.name = id;
      control.placeholder = placeholder;
      control.required = true;
      wrapper.appendChild(control);
      $("dialog-fields").appendChild(wrapper);
    }

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
            prompt: formData.get("agent-prompt"),
            can_search: false
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

(() => {
  const config = window.realtimeConfig || {};
  const tokenForm = document.getElementById("token-form");
  const tokenInput = document.getElementById("token-input");
  const wsStatus = document.getElementById("ws-status");
  const sseStatus = document.getElementById("sse-status");
  const clientCount = document.getElementById("client-count");
  const cardForm = document.getElementById("card-form");
  const chatForm = document.getElementById("chat-form");
  const activityFeed = document.getElementById("activity-feed");
  const chatLog = document.getElementById("chat-log");
  const boardColumns = document.querySelectorAll(".column");

  let currentToken = "";
  let ws;
  let wsReconnectTimer;
  let wsDelay = config.reconnect?.initialDelay || 1.5;
  const wsDelayMax = config.reconnect?.maxDelay || 10;
  let eventSource;

  const columnNodes = Array.from(boardColumns).reduce((acc, column) => {
    const key = column.getAttribute("data-column");
    const cardContainer = column.querySelector(".column-cards");
    if (key && cardContainer) {
      acc[key] = cardContainer;
    }
    return acc;
  }, {});

  function setStatus(node, state, label) {
    if (!node) return;
    node.dataset.state = state;
    node.textContent = label;
  }

  function setClientCount(count) {
    if (clientCount) {
      clientCount.textContent = `Active collaborators: ${count}`;
    }
  }

  function renderCard(event) {
    const { payload = {}, user = "" } = event;
    const column = payload.column || "backlog";
    const title = payload.title || payload.message || "Untitled";
    const target = columnNodes[column];
    if (!target) {
      return;
    }
    const card = document.createElement("div");
    card.className = "card";
    const author = user ? `<span class="muted">@${user}</span>` : "";
    card.innerHTML = `<strong>${title}</strong><br />${author}`;
    target.prepend(card);
  }

  function renderChat(event) {
    if (!chatLog) return;
    const item = document.createElement("li");
    const { user = "anonymous", payload = {} } = event;
    const message = payload.message || event.payload?.text || event.message;
    const timestamp = new Date(event.timestamp).toLocaleTimeString();
    item.innerHTML = `<strong>${user}</strong> · <span class="muted">${timestamp}</span><br />${message}`;
    chatLog.prepend(item);
  }

  function renderActivity(event) {
    if (!activityFeed) return;
    const item = document.createElement("li");
    const timestamp = new Date(event.timestamp).toLocaleTimeString();
    const action = event.action.replace(/[_\.]/g, " ");
    const summary = event.payload?.title || event.payload?.message || event.payload?.text || "event";
    item.innerHTML = `<strong>${action}</strong> by ${event.user} · <span class="muted">${timestamp}</span><br />${summary}`;
    activityFeed.prepend(item);
  }

  function handleBoardEvent(event) {
    if (!event || typeof event !== "object") return;
    if (typeof event.active_connections === "number") {
      setClientCount(event.active_connections);
    }

    if (event.kind === "error") {
      renderActivity({
        action: "error",
        user: "system",
        timestamp: new Date().toISOString(),
        payload: { message: Array.isArray(event.detail) ? JSON.stringify(event.detail) : event.detail },
      });
      return;
    }

    switch (event.action) {
      case "card.added":
      case "card.updated":
        renderCard(event);
        break;
      case "chat.message":
        renderChat(event);
        break;
      default:
        renderActivity(event);
        break;
    }
  }

  function clearBoard() {
    Object.values(columnNodes).forEach((column) => {
      column.innerHTML = "";
    });
  }

  function disconnectWebSocket() {
    if (ws) {
      ws.close();
      ws = undefined;
    }
    clearTimeout(wsReconnectTimer);
    wsReconnectTimer = undefined;
  }

  function connectWebSocket() {
    if (!currentToken) return;
    disconnectWebSocket();

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = new URL(window.location.origin.replace(/^http/, protocol));
    url.pathname = "/ws/boards/demo";
    url.searchParams.set("token", currentToken);

    ws = new WebSocket(url);
    setStatus(wsStatus, "connecting", "WebSocket: connecting…");

    ws.addEventListener("open", () => {
      wsDelay = config.reconnect?.initialDelay || 1.5;
      setStatus(wsStatus, "connected", "WebSocket: connected");
    });

    ws.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data);
        handleBoardEvent(data);
      } catch (error) {
        console.error("Failed to parse websocket message", error);
      }
    });

    ws.addEventListener("close", () => {
      setStatus(wsStatus, "disconnected", "WebSocket: disconnected");
      if (!currentToken) return;
      clearTimeout(wsReconnectTimer);
      wsReconnectTimer = window.setTimeout(() => {
        wsDelay = Math.min(wsDelay * 1.8, wsDelayMax);
        connectWebSocket();
      }, wsDelay * 1000);
    });

    ws.addEventListener("error", () => {
      setStatus(wsStatus, "disconnected", "WebSocket: error encountered");
    });
  }

  function disconnectEventSource() {
    if (eventSource) {
      eventSource.close();
      eventSource = undefined;
    }
  }

  function connectEventSource() {
    if (!currentToken) return;
    disconnectEventSource();
    const url = new URL(window.location.origin);
    url.pathname = "/sse/activity";
    url.searchParams.set("token", currentToken);

    eventSource = new EventSource(url);
    setStatus(sseStatus, "connecting", "Activity stream: connecting…");

    eventSource.onopen = () => {
      setStatus(sseStatus, "connected", "Activity stream: connected");
    };

    eventSource.onerror = () => {
      setStatus(sseStatus, "disconnected", "Activity stream: reconnecting…");
    };

    eventSource.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        renderActivity(payload);
      } catch (error) {
        console.error("Failed to parse activity event", error);
      }
    };
  }

  function establishConnections(token) {
    currentToken = token;
    connectWebSocket();
    connectEventSource();
  }

  function resetConnections() {
    disconnectWebSocket();
    disconnectEventSource();
    setStatus(wsStatus, "disconnected", "WebSocket: disconnected");
    setStatus(sseStatus, "disconnected", "Activity stream: disconnected");
    setClientCount(0);
    clearBoard();
    if (activityFeed) activityFeed.innerHTML = "";
    if (chatLog) chatLog.innerHTML = "";
  }

  tokenForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const token = tokenInput?.value.trim();
    if (!token) return;
    resetConnections();
    establishConnections(token);
  });

  cardForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const title = document.getElementById("card-title").value.trim();
    const column = document.getElementById("card-column").value;
    if (!title) return;
    const message = {
      action: "card.added",
      user: "board",
      payload: { title, column },
    };
    ws.send(JSON.stringify(message));
    cardForm.reset();
  });

  chatForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const user = document.getElementById("chat-user").value.trim() || "teammate";
    const messageText = document.getElementById("chat-message").value.trim();
    if (!messageText) return;
    const payload = {
      action: "chat.message",
      user,
      message: messageText,
      payload: { message: messageText },
    };
    ws.send(JSON.stringify(payload));
    chatForm.reset();
  });

  window.addEventListener("beforeunload", () => {
    disconnectWebSocket();
    disconnectEventSource();
  });
})();

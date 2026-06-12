class RainBirdIQ4Card extends HTMLElement {
  static getStubConfig() {
    return {
      type: "custom:rainbird-iq4-card",
      title: "Rain Bird IQ4",
      auto: true,
      default_duration: 6,
    };
  }

  static getConfigElement() {
    return document.createElement("rainbird-iq4-card-editor");
  }

  setConfig(config) {
    this._config = {
      title: "Rain Bird IQ4",
      auto: true,
      default_duration: 6,
      ...config,
    };
    this._duration = Number(this._config.default_duration || 6);
    this._selectedControllerId = this._config.controller_id
      ? String(this._config.controller_id)
      : null;
    this._rainDelayDraft = this._rainDelayDraft || {};
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    const stations = this._getStations();
    return Math.max(3, Math.min(8, stations.length + 3));
  }

  _render() {
    if (!this.shadowRoot || !this._hass) return;

    const stations = this._getStations();
    const controllers = this._getControllers(stations);
    if (!this._selectedControllerId && controllers.length) {
      this._selectedControllerId = controllers[0].id;
    }
    if (
      this._selectedControllerId &&
      controllers.length &&
      !controllers.some((controller) => controller.id === this._selectedControllerId)
    ) {
      this._selectedControllerId = controllers[0].id;
    }

    const selectedController = controllers.find(
      (controller) => controller.id === this._selectedControllerId
    );
    const visibleStations = stations.filter(
      (station) => !selectedController || station.controllerId === selectedController.id
    );
    const rainDelayEntity = selectedController
      ? this._getRainDelayEntity(selectedController.id)
      : null;
    const rainDelayValue =
      selectedController && this._rainDelayDraft[selectedController.id] !== undefined
        ? this._rainDelayDraft[selectedController.id]
        : rainDelayEntity
          ? rainDelayEntity.state
          : "";

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }

        .card {
          padding: 0 16px 16px;
        }

        .empty {
          color: var(--secondary-text-color);
          padding: 16px 0 4px;
        }

        .toolbar {
          align-items: end;
          display: grid;
          gap: 12px;
          grid-template-columns: minmax(160px, 1fr) 108px 108px auto;
          margin: 4px 0 14px;
        }

        .field {
          display: flex;
          flex-direction: column;
          gap: 4px;
          min-width: 0;
        }

        label {
          color: var(--secondary-text-color);
          font-size: 12px;
          line-height: 16px;
        }

        select,
        input {
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          box-sizing: border-box;
          color: var(--primary-text-color);
          font: inherit;
          height: 36px;
          min-width: 0;
          padding: 0 10px;
          width: 100%;
        }

        button {
          align-items: center;
          background: var(--primary-color);
          border: 0;
          border-radius: 6px;
          color: var(--text-primary-color, white);
          cursor: pointer;
          display: inline-flex;
          font: inherit;
          font-weight: 600;
          gap: 6px;
          height: 36px;
          justify-content: center;
          padding: 0 12px;
          white-space: nowrap;
        }

        button.secondary {
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
        }

        button.danger {
          background: var(--error-color, #db4437);
          color: white;
        }

        button.icon {
          min-width: 36px;
          padding: 0;
        }

        button[disabled] {
          cursor: not-allowed;
          opacity: 0.55;
        }

        .status-strip {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
          margin: -2px 0 14px;
        }

        .pill {
          align-items: center;
          background: var(--secondary-background-color);
          border-radius: 999px;
          color: var(--secondary-text-color);
          display: inline-flex;
          font-size: 12px;
          gap: 6px;
          line-height: 20px;
          padding: 2px 10px;
        }

        .dot {
          background: var(--disabled-text-color);
          border-radius: 50%;
          height: 8px;
          width: 8px;
        }

        .dot.on {
          background: var(--success-color, #43a047);
        }

        .dot.off {
          background: var(--error-color, #db4437);
        }

        .station-list {
          border-top: 1px solid var(--divider-color);
        }

        .station {
          align-items: center;
          border-bottom: 1px solid var(--divider-color);
          display: grid;
          gap: 12px;
          grid-template-columns: minmax(0, 1fr) auto auto;
          min-height: 56px;
          padding: 8px 0;
        }

        .station-title {
          font-weight: 600;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }

        .station-meta {
          color: var(--secondary-text-color);
          display: flex;
          flex-wrap: wrap;
          font-size: 12px;
          gap: 8px;
          margin-top: 3px;
        }

        .running {
          color: var(--success-color, #43a047);
          font-weight: 700;
        }

        @media (max-width: 600px) {
          .toolbar {
            grid-template-columns: 1fr 1fr;
          }

          .field.controller {
            grid-column: 1 / -1;
          }

          .station {
            grid-template-columns: minmax(0, 1fr) auto auto;
          }

          button.stop-all {
            grid-column: 1 / -1;
          }
        }
      </style>

      <ha-card header="${this._escape(this._config.title)}">
        <div class="card">
          ${stations.length ? this._renderContent(controllers, selectedController, visibleStations, rainDelayValue, rainDelayEntity) : this._renderEmpty()}
        </div>
      </ha-card>
    `;

    this._bindEvents();
  }

  _renderContent(controllers, selectedController, stations, rainDelayValue, rainDelayEntity) {
    const connectionPills = controllers
      .map(
        (controller) => `
          <span class="pill">
            <span class="dot ${controller.connected === true ? "on" : controller.connected === false ? "off" : ""}"></span>
            ${this._escape(controller.name)}
          </span>
        `
      )
      .join("");

    const controllerOptions = controllers
      .map(
        (controller) => `
          <option value="${this._escape(controller.id)}" ${controller.id === this._selectedControllerId ? "selected" : ""}>
            ${this._escape(controller.name)}
          </option>
        `
      )
      .join("");

    const stationRows = stations.length
      ? stations.map((station) => this._renderStation(station)).join("")
      : `<div class="empty">No stations found for this controller.</div>`;

    return `
      <div class="status-strip">${connectionPills}</div>
      <div class="toolbar">
        <div class="field controller">
          <label>Controller</label>
          <select data-controller>${controllerOptions}</select>
        </div>
        <div class="field">
          <label>Duration, min</label>
          <input data-duration type="number" min="1" max="720" value="${this._escape(this._duration)}">
        </div>
        <div class="field">
          <label>Rain delay, days</label>
          <input data-rain-delay type="number" min="0" max="14" value="${this._escape(rainDelayValue)}" ${rainDelayEntity ? "" : "disabled"}>
        </div>
        <button class="secondary" data-apply-rain-delay ${rainDelayEntity ? "" : "disabled"}>
          <ha-icon icon="mdi:weather-rainy"></ha-icon>
          Apply
        </button>
        <button class="danger stop-all" data-stop-all ${selectedController ? "" : "disabled"}>
          <ha-icon icon="mdi:stop-circle-outline"></ha-icon>
          Stop all
        </button>
      </div>
      <div class="station-list">${stationRows}</div>
    `;
  }

  _renderEmpty() {
    return `
      <div class="empty">
        No Rain Bird IQ4 station switches were found. Add the Rain Bird IQ4 integration first, then refresh this dashboard.
      </div>
    `;
  }

  _renderStation(station) {
    const running = station.state === "on";
    const remaining = Number(station.attributes.remaining_seconds || 0);
    const remainingText = remaining > 0 ? `${Math.ceil(remaining / 60)} min left` : "";
    const meta = [
      station.attributes.terminal ? `Terminal ${this._escape(station.attributes.terminal)}` : null,
      station.attributes.landscape_type ? this._escape(station.attributes.landscape_type) : null,
      station.attributes.sprinkler_type ? this._escape(station.attributes.sprinkler_type) : null,
      running ? `<span class="running">${remainingText || "Running"}</span>` : null,
    ]
      .filter(Boolean)
      .join("<span>•</span>");

    return `
      <div class="station">
        <div>
          <div class="station-title">${this._escape(station.name)}</div>
          <div class="station-meta">${meta}</div>
        </div>
        <button class="icon" title="Start" data-start="${this._escape(station.stationId)}">
          <ha-icon icon="mdi:play"></ha-icon>
        </button>
        <button class="icon secondary" title="Stop" data-stop="${this._escape(station.stationId)}" ${running ? "" : ""}>
          <ha-icon icon="mdi:stop"></ha-icon>
        </button>
      </div>
    `;
  }

  _bindEvents() {
    this.shadowRoot.querySelector("[data-controller]")?.addEventListener("change", (event) => {
      this._selectedControllerId = event.target.value;
      this._render();
    });

    this.shadowRoot.querySelector("[data-duration]")?.addEventListener("change", (event) => {
      this._duration = Math.max(1, Math.min(720, Number(event.target.value || 1)));
      event.target.value = this._duration;
    });

    this.shadowRoot.querySelector("[data-rain-delay]")?.addEventListener("change", (event) => {
      if (!this._selectedControllerId) return;
      this._rainDelayDraft[this._selectedControllerId] = Math.max(
        0,
        Math.min(14, Number(event.target.value || 0))
      );
      event.target.value = this._rainDelayDraft[this._selectedControllerId];
    });

    this.shadowRoot.querySelector("[data-apply-rain-delay]")?.addEventListener("click", () => {
      if (!this._selectedControllerId) return;
      const input = this.shadowRoot.querySelector("[data-rain-delay]");
      const days = Math.max(0, Math.min(14, Number(input?.value || 0)));
      this._hass.callService("rainbird_iq4", "set_rain_delay", {
        controller_id: Number(this._selectedControllerId),
        days,
      });
    });

    this.shadowRoot.querySelector("[data-stop-all]")?.addEventListener("click", () => {
      if (!this._selectedControllerId) return;
      this._hass.callService("rainbird_iq4", "stop_all", {
        controller_id: Number(this._selectedControllerId),
      });
    });

    this.shadowRoot.querySelectorAll("[data-start]").forEach((button) => {
      button.addEventListener("click", () => {
        this._hass.callService("rainbird_iq4", "start_station", {
          station_id: Number(button.dataset.start),
          duration: Number(this._duration || this._config.default_duration || 6),
        });
      });
    });

    this.shadowRoot.querySelectorAll("[data-stop]").forEach((button) => {
      button.addEventListener("click", () => {
        this._hass.callService("rainbird_iq4", "stop_station", {
          station_id: Number(button.dataset.stop),
        });
      });
    });
  }

  _getStations() {
    if (!this._hass) return [];
    const configuredEntities = Array.isArray(this._config.entities)
      ? this._config.entities
      : [];
    const entries = configuredEntities.length
      ? configuredEntities
          .map((entityId) => [entityId, this._hass.states[entityId]])
          .filter(([, state]) => state)
      : this._config.auto === false
        ? []
      : Object.entries(this._hass.states).filter(([entityId, state]) => {
          return (
            entityId.startsWith("switch.") &&
            state.attributes.station_id !== undefined &&
            state.attributes.controller_id !== undefined
          );
        });

    return entries
      .map(([entityId, state]) => ({
        entityId,
        state: state.state,
        attributes: state.attributes,
        stationId: String(state.attributes.station_id),
        controllerId: String(state.attributes.controller_id),
        name: state.attributes.friendly_name || entityId,
      }))
      .sort((left, right) => {
        const terminalLeft = Number(left.attributes.terminal || 9999);
        const terminalRight = Number(right.attributes.terminal || 9999);
        return terminalLeft - terminalRight || left.name.localeCompare(right.name);
      });
  }

  _getControllers(stations) {
    const controllerIds = [...new Set(stations.map((station) => station.controllerId))];
    return controllerIds.map((id) => {
      const connection = this._getConnectionEntity(id);
      const name = this._controllerName(id, connection);
      return {
        id,
        name,
        connected: connection ? connection.state === "on" : undefined,
      };
    });
  }

  _controllerName(controllerId, connectionEntity) {
    if (this._config.controller_names?.[controllerId]) {
      return this._config.controller_names[controllerId];
    }
    const friendly = connectionEntity?.attributes?.friendly_name;
    if (friendly) {
      return friendly.replace(/\s+Connection$/i, "");
    }
    return `Controller ${controllerId}`;
  }

  _getConnectionEntity(controllerId) {
    return Object.values(this._hass.states).find((state) => {
      return (
        state.entity_id?.startsWith("binary_sensor.") &&
        String(state.attributes.controller_id) === String(controllerId)
      );
    });
  }

  _getRainDelayEntity(controllerId) {
    return Object.values(this._hass.states).find((state) => {
      return (
        state.entity_id?.startsWith("number.") &&
        String(state.attributes.controller_id) === String(controllerId)
      );
    });
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }
}

class RainBirdIQ4CardEditor extends HTMLElement {
  setConfig(config) {
    this._config = { auto: true, default_duration: 6, ...config };
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;
    const entities = Array.isArray(this._config.entities)
      ? this._config.entities.join("\n")
      : "";
    this.shadowRoot.innerHTML = `
      <style>
        .editor {
          display: grid;
          gap: 12px;
          padding: 8px 0;
        }

        label {
          color: var(--secondary-text-color);
          display: block;
          font-size: 12px;
          margin-bottom: 4px;
        }

        input,
        textarea {
          background: var(--card-background-color);
          border: 1px solid var(--divider-color);
          border-radius: 6px;
          box-sizing: border-box;
          color: var(--primary-text-color);
          font: inherit;
          min-height: 36px;
          padding: 8px 10px;
          width: 100%;
        }

        textarea {
          min-height: 92px;
        }

        .check {
          align-items: center;
          display: flex;
          gap: 8px;
        }

        .check input {
          width: auto;
        }
      </style>
      <div class="editor">
        <div>
          <label>Title</label>
          <input data-key="title" value="${this._escape(this._config.title || "Rain Bird IQ4")}">
        </div>
        <div>
          <label>Default duration, minutes</label>
          <input data-key="default_duration" type="number" min="1" max="720" value="${this._escape(this._config.default_duration || 6)}">
        </div>
        <div>
          <label>Controller ID to select by default</label>
          <input data-key="controller_id" type="number" min="1" value="${this._escape(this._config.controller_id || "")}">
        </div>
        <label class="check">
          <input data-key="auto" type="checkbox" ${this._config.auto !== false ? "checked" : ""}>
          Auto-discover Rain Bird IQ4 station switches
        </label>
        <div>
          <label>Station entities, one per line. Leave empty for auto-discovery.</label>
          <textarea data-key="entities">${this._escape(entities)}</textarea>
        </div>
      </div>
    `;
    this._bindEvents();
  }

  _bindEvents() {
    this.shadowRoot.querySelectorAll("[data-key]").forEach((input) => {
      input.addEventListener("change", () => {
        const key = input.dataset.key;
        const config = { ...this._config };
        if (key === "auto") {
          config.auto = input.checked;
        } else if (key === "default_duration" || key === "controller_id") {
          const value = input.value === "" ? undefined : Number(input.value);
          if (value === undefined) {
            delete config[key];
          } else {
            config[key] = value;
          }
        } else if (key === "entities") {
          const entities = input.value
            .split(/\n|,/)
            .map((item) => item.trim())
            .filter(Boolean);
          if (entities.length) config.entities = entities;
          else delete config.entities;
        } else {
          config[key] = input.value;
        }
        this._config = config;
        this.dispatchEvent(
          new CustomEvent("config-changed", {
            detail: { config },
            bubbles: true,
            composed: true,
          })
        );
      });
    });
  }

  _escape(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }
}

customElements.define("rainbird-iq4-card", RainBirdIQ4Card);
customElements.define("rainbird-iq4-card-editor", RainBirdIQ4CardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "rainbird-iq4-card",
  name: "Rain Bird IQ4",
  description: "Control Rain Bird IQ4 stations, rain delay, and stop-all from one card.",
});

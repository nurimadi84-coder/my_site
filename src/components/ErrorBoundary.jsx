import { Component } from "react";
import { SITE } from "../site";
import { reportError } from "../utils/report";

/**
 * name — метка в отчёте об ошибке.
 * fallback — что показать вместо упавшего блока; без него показывается полноэкранная заглушка с WhatsApp.
 * fallback={null} — блок просто скрывается (например, чат), остальная страница продолжает работать.
 */
export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { failed: false };
  }

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error, info) {
    reportError(`ui:${this.props.name || "app"}`, error, { componentStack: info?.componentStack });
  }

  render() {
    if (!this.state.failed) return this.props.children;
    if ("fallback" in this.props) return this.props.fallback;
    return (
      <main className="app-error" role="alert">
        <h1>Что-то пошло не так</h1>
        <p>Обновите страницу. Если ошибка повторится — напишите нам в WhatsApp, мы примем заказ вручную.</p>
        <div className="app-error__actions">
          <button className="btn btn--bronze" type="button" onClick={() => window.location.reload()}>
            Обновить страницу
          </button>
          <a className="btn btn--line" href={`https://wa.me/${SITE.phoneE164}`} target="_blank" rel="noopener">
            Написать в WhatsApp
          </a>
        </div>
      </main>
    );
  }
}

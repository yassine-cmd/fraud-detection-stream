import React from "react";
import { IconAlert } from "../icons.jsx";

export class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error("[Sentinel ErrorBoundary]", error, errorInfo);
  }

  handleReload = () => {
    window.location.reload();
  };

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary-container" style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          minHeight: "400px",
          padding: "2rem",
          textAlign: "center",
          color: "var(--color-text, #f8fafc)",
          background: "var(--color-bg, #0b1120)",
          borderRadius: "12px",
          margin: "2rem"
        }}>
          <div style={{
            width: "56px",
            height: "56px",
            borderRadius: "50%",
            background: "rgba(239, 68, 68, 0.15)",
            color: "#ef4444",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: "1rem"
          }}>
            <IconAlert size={28} />
          </div>
          <h2 style={{ fontSize: "1.25rem", fontWeight: "600", marginBottom: "0.5rem" }}>
            Une erreur d'affichage est survenue
          </h2>
          <p style={{ color: "#94a3b8", maxWidth: "460px", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
            Un composant de l'interface n'a pas pu être rendu correctement. Vos flux et alertes continuent de tourner en arrière-plan.
          </p>
          <div style={{ display: "flex", gap: "0.75rem" }}>
            <button
              onClick={this.handleReset}
              className="btn btn-secondary"
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "6px",
                border: "1px solid #334155",
                background: "#1e293b",
                color: "#f8fafc",
                cursor: "pointer"
              }}
            >
              Réessayer
            </button>
            <button
              onClick={this.handleReload}
              className="btn btn-primary"
              style={{
                padding: "0.5rem 1rem",
                borderRadius: "6px",
                border: "none",
                background: "#3b82f6",
                color: "#ffffff",
                cursor: "pointer"
              }}
            >
              Recharger la page
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

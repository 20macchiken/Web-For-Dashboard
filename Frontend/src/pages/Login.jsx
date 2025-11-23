import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function Login() {
  const [mode, setMode] = useState("login"); // "login" | "signup"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const [error, setError] = useState("");
  const [info, setInfo] = useState("");

  const { login, signup } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setInfo("");

    try {
      if (mode === "signup") {
        await signup(email.trim(), password);
        setInfo("Signup success! Check your email to verify, then login.");
        setMode("login");
      } else {
        await login(email.trim(), password);
        navigate("/");
      }
    } catch (err) {
      setError(err.message || "Auth failed");
    }
  };

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "100vh",
        backgroundColor: "#f5f5f5",
      }}
    >
      <div
        style={{
          backgroundColor: "white",
          padding: "40px",
          borderRadius: "8px",
          boxShadow: "0 2px 10px rgba(0,0,0,0.1)",
          width: "100%",
          maxWidth: "400px",
        }}
      >
        <h2 style={{ marginBottom: "8px", textAlign: "center" }}>
          Dashboard Viewer
        </h2>

        <p style={{ marginBottom: "24px", textAlign: "center", color: "#666" }}>
          {mode === "login" ? "Please login" : "Create an account"}
        </p>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: "16px" }}>
            <label
              style={{
                display: "block",
                marginBottom: "8px",
                fontWeight: "500",
              }}
            >
              Email
            </label>
            <input
              type="email"
              placeholder="yourname@siit.tu.ac.th"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                width: "100%",
                padding: "10px",
                border: "1px solid #ddd",
                borderRadius: "4px",
                fontSize: "14px",
                boxSizing: "border-box",
              }}
              autoFocus
            />
          </div>

          <div style={{ marginBottom: "16px" }}>
            <label
              style={{
                display: "block",
                marginBottom: "8px",
                fontWeight: "500",
              }}
            >
              Password
            </label>
            <input
              type="password"
              placeholder="Enter your password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              style={{
                width: "100%",
                padding: "10px",
                border: "1px solid #ddd",
                borderRadius: "4px",
                fontSize: "14px",
                boxSizing: "border-box",
              }}
            />
          </div>

          {error && (
            <div
              style={{
                padding: "10px",
                marginBottom: "12px",
                backgroundColor: "#fee",
                color: "#c33",
                borderRadius: "4px",
                fontSize: "14px",
              }}
            >
              {error}
            </div>
          )}

          {info && (
            <div
              style={{
                padding: "10px",
                marginBottom: "12px",
                backgroundColor: "#eef",
                color: "#225",
                borderRadius: "4px",
                fontSize: "14px",
              }}
            >
              {info}
            </div>
          )}

          <button
            type="submit"
            style={{
              width: "100%",
              padding: "12px",
              backgroundColor: "#007bff",
              color: "white",
              border: "none",
              borderRadius: "4px",
              fontSize: "16px",
              fontWeight: "500",
              cursor: "pointer",
              boxSizing: "border-box",
            }}
          >
            {mode === "login" ? "Login" : "Sign up"}
          </button>
        </form>

        <div style={{ marginTop: 12, textAlign: "center" }}>
          {mode === "login" ? (
            <button
              onClick={() => setMode("signup")}
              style={{
                background: "transparent",
                border: "none",
                color: "#007bff",
                cursor: "pointer",
              }}
            >
              No account? Sign up
            </button>
          ) : (
            <button
              onClick={() => setMode("login")}
              style={{
                background: "transparent",
                border: "none",
                color: "#007bff",
                cursor: "pointer",
              }}
            >
              Already have an account? Login
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

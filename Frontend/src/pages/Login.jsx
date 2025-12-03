import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { supabase } from "../lib/supabaseClient"; // use of supabase client for functions

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

  // Google OAuth login
  const loginWithGoogle = async () => {
    setError("");
    const { error } = await supabase.auth.signInWithOAuth({
      provider: "google",
      options: {
        redirectTo: window.location.origin, // redirect back to the app
      },
    });
    if (error) setError(error.message);
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
          {mode === "login" ? "Please login with Google Auth to Identify yourself" : "Create an account"}
        </p>

        {/* Sign in to Google button */}
        <button
          onClick={loginWithGoogle}
          style={{
            width: "100%",
            padding: "12px",
            marginTop: "10px",
            backgroundColor: "white",
            color: "#111",
            border: "1px solid #ddd",
            borderRadius: "4px",
            fontSize: "16px",
            fontWeight: "500",
            cursor: "pointer",
            boxSizing: "border-box",
          }}
        >
          Continue with Google
        </button>
      </div>
    </div>
  );
}

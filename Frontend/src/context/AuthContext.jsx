import { createContext, useContext, useEffect, useState } from "react";
import { supabase } from "../lib/supabaseClient";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);       // Supabase user
  const [session, setSession] = useState(null); // Supabase session
  const [userRole, setUserRole] = useState(null); // Store numeric Role ID
  const [loading, setLoading] = useState(true); 

  // Helper: Fetch role from public.Users table
  const fetchUserRole = async (userId) => {
    try {
      const { data, error } = await supabase
        .from('Users')
        .select('Role')
        .eq('id', userId)
        .single();
      
      if (data) {
        setUserRole(data.Role);
      }
    } catch (err) {
      console.error("Error fetching role:", err);
    }
  };

  useEffect(() => {
    // Initial session (refresh)
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session ?? null);
      setUser(data.session?.user ?? null);
      
      if (data.session?.user) {
        fetchUserRole(data.session.user.id);
      }
      setLoading(false);
    });

    // Listen for changes
    const { data: sub } = supabase.auth.onAuthStateChange(
      (_event, newSession) => {
        setSession(newSession ?? null);
        setUser(newSession?.user ?? null);

        if (newSession?.user) {
          fetchUserRole(newSession.user.id);
        } else {
          setUserRole(null);
        }
      }
    );

    return () => sub.subscription.unsubscribe();
  }, []);

  // --- NEW: Helper to create user profile in DB ---
  const createUserProfile = async (authUser) => {
    if (!authUser) return;

    // Logic: @siit.tu.ac.th = Student (1), Others = Staff (2)
    const isStudent = authUser.email.endsWith("@siit.tu.ac.th");
    const roleId = isStudent ? 1 : 2;

    const { error } = await supabase
      .from('Users')
      .upsert({
        id: authUser.id,
        Email: authUser.email,
        Role: roleId,
        Name: authUser.user_metadata?.full_name || authUser.email.split('@')[0],
        GrafanaID: 'pending', 
        Proxmox: 'pending'
      }, { onConflict: 'id' });

    if (error) {
      console.error("Error creating user profile in database:", error);
    } else {
      // Update local state immediately so UI reflects role
      setUserRole(roleId);
    }
  };
  // ---------------------------------------------------------------------

  // Sign up
  const signup = async (email, password) => {
    const { data, error } = await supabase.auth.signUp({
      email,
      password,
    });
    if (error) throw error;

    // Manually create the profile row if signup was successful
    if (data?.user) {
      await createUserProfile(data.user);
    }

    return data;
  };

  // Login
  const login = async (email, password) => {
    const { data, error } = await supabase.auth.signInWithPassword({
      email,
      password,
    });
    if (error) throw error;
    return data;
  };

  const logout = async () => {
    await supabase.auth.signOut();
    setUserRole(null);
  };

  const value = {
    user,
    session,
    userRole,
    isStaff: userRole === 2, // Helper boolean: True if Role is 2 (Staff)
    login,
    signup,
    logout,
    loading,
    isAuthenticated: !!user,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}
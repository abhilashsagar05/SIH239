"use client";

import React, { useState } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { ShieldCheck, ChevronRight, UserCircle, KeyRound, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

export default function LoginPage() {
  const router = useRouter();
  const [isLoading, setIsLoading] = useState(false);
  const [role, setRole] = useState<"applicant" | "admin">("applicant");

  const handleLogin = (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    // Simulate login delay
    setTimeout(() => {
      if (role === "admin") {
        router.push("/admin/queue");
      } else {
        router.push("/applicant/dashboard");
      }
    }, 800);
  };

  return (
    <div className="min-h-screen bg-transparent flex flex-col justify-center items-center p-4">
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="w-full max-w-md"
      >
        <div className="text-center mb-8">
          <div className="w-16 h-16 mx-auto rounded-2xl bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center text-white font-bold text-3xl shadow-xl shadow-brand-500/20 mb-6">
            Mo
          </div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">MoTA Portal</h1>
          <p className="text-slate-500 mt-2">Sign in to your account to continue</p>
        </div>

        <div className="glass-card rounded-3xl p-8 shadow-2xl border border-white/50">
          <div className="flex bg-slate-100/50 p-1 rounded-xl mb-8">
            <button 
              type="button"
              onClick={() => setRole("applicant")}
              className={cn(
                "flex-1 py-2 text-sm font-semibold rounded-lg transition-all",
                role === "applicant" ? "bg-white text-brand-600 shadow-sm" : "text-slate-500 hover:text-slate-700"
              )}
            >
              Applicant
            </button>
            <button 
              type="button"
              onClick={() => setRole("admin")}
              className={cn(
                "flex-1 py-2 text-sm font-semibold rounded-lg transition-all",
                role === "admin" ? "bg-white text-brand-600 shadow-sm" : "text-slate-500 hover:text-slate-700"
              )}
            >
              Admin / Scrutiny
            </button>
          </div>

          <form onSubmit={handleLogin} className="space-y-5">
            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1.5">
                {role === "admin" ? "Admin ID" : "Mobile / Application Number"}
              </label>
              <div className="relative">
                <UserCircle className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={20} />
                <input 
                  type="text" 
                  required
                  placeholder={role === "admin" ? "Enter Admin ID" : "Enter Mobile Number"}
                  className="w-full pl-10 pr-4 py-3 bg-white/50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-500 transition-all"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-semibold text-slate-700 mb-1.5">Password / OTP</label>
              <div className="relative">
                <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={20} />
                <input 
                  type="password" 
                  required
                  placeholder="Enter Password or OTP"
                  className="w-full pl-10 pr-4 py-3 bg-white/50 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-brand-500 transition-all"
                />
              </div>
              <div className="flex justify-end mt-2">
                <a href="#" className="text-xs font-semibold text-brand-600 hover:text-brand-700">Forgot password?</a>
              </div>
            </div>

            <button 
              type="submit" 
              disabled={isLoading}
              className="w-full mt-2 flex items-center justify-center gap-2 bg-gradient-to-r from-brand-600 to-brand-500 text-white font-bold py-3 px-4 rounded-xl shadow-lg hover:shadow-xl hover:from-brand-500 hover:to-brand-400 transition-all disabled:opacity-70 disabled:cursor-not-allowed"
            >
              {isLoading ? <Loader2 className="animate-spin" size={20} /> : "Sign In"}
              {!isLoading && <ChevronRight size={20} />}
            </button>
          </form>

          {role === "applicant" && (
            <div className="mt-8 text-center text-sm font-medium text-slate-500">
              Don't have an account? <a href="#" className="text-brand-600 hover:underline">Register here</a>
            </div>
          )}
        </div>
      </motion.div>
    </div>
  );
}

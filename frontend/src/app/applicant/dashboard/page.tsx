"use client";

import React, { useState } from "react";
import Link from "next/link";
import { 
  FileText, CheckCircle, Clock, AlertTriangle, 
  ChevronRight, Upload, Bell, User, LayoutDashboard,
  LogOut, Settings
} from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

const applications = [
  {
    id: "APP-2024-NFST-001",
    scheme: "National Fellowship for Scheduled Tribe (NFST)",
    status: "AI_REVIEW",
    progress: 45,
    submittedAt: "Oct 24, 2026",
    aiScore: 82,
  },
  {
    id: "APP-2023-NOS-089",
    scheme: "National Overseas Scholarship (NOS)",
    status: "DEFICIENT",
    progress: 85,
    submittedAt: "Sep 12, 2026",
    aiScore: 68,
  }
];

export default function ApplicantDashboard() {
  const [activeTab, setActiveTab] = useState("overview");

  return (
    <div className="min-h-screen bg-transparent flex">
      {/* Sidebar Navigation */}
      <motion.aside 
        initial={{ x: -250 }}
        animate={{ x: 0 }}
        className="w-64 glass-card border-r border-brand-100/20 hidden md:flex flex-col p-6 m-4 rounded-3xl"
      >
        <div className="flex items-center gap-3 mb-12">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-brand-500 to-purple-600 flex items-center justify-center text-white font-bold text-xl">
            Mo
          </div>
          <div>
            <h2 className="font-bold text-lg leading-tight">MoTA</h2>
            <p className="text-xs text-slate-500">Scholarship Portal</p>
          </div>
        </div>

        <nav className="flex-1 space-y-2">
          {[
            { id: "overview", icon: LayoutDashboard, label: "Overview" },
            { id: "applications", icon: FileText, label: "My Applications" },
            { id: "documents", icon: Upload, label: "Documents" },
            { id: "notifications", icon: Bell, label: "Notifications" },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all",
                activeTab === item.id 
                  ? "bg-brand-500/10 text-brand-600 font-medium" 
                  : "text-slate-600 hover:bg-slate-100/50 hover:text-slate-900"
              )}
            >
              <item.icon size={20} className={activeTab === item.id ? "text-brand-600" : ""} />
              {item.label}
            </button>
          ))}
        </nav>

        <div className="mt-auto space-y-2 pt-6 border-t border-slate-200/50">
          <button className="w-full flex items-center gap-3 px-4 py-2 text-slate-600 hover:text-slate-900 transition-colors">
            <Settings size={20} />
            Settings
          </button>
          <Link href="/" className="w-full flex items-center gap-3 px-4 py-2 text-red-500 hover:text-red-600 transition-colors">
            <LogOut size={20} />
            Sign Out
          </Link>
        </div>
      </motion.aside>

      {/* Main Content */}
      <main className="flex-1 p-4 md:p-8 overflow-y-auto">
        <header className="flex justify-between items-center mb-8 glass-card p-4 rounded-2xl">
          <div>
            <h1 className="text-2xl font-bold">Welcome back, Rahul 👋</h1>
            <p className="text-slate-500 text-sm">Here's what's happening with your applications today.</p>
          </div>
          <div className="flex items-center gap-4">
            <button className="relative p-2 rounded-full hover:bg-slate-100/50 transition-colors">
              <Bell size={24} className="text-slate-600" />
              <span className="absolute top-1 right-1 w-3 h-3 bg-red-500 border-2 border-white rounded-full"></span>
            </button>
            <div className="w-10 h-10 rounded-full bg-slate-200 flex items-center justify-center overflow-hidden">
              <User className="text-slate-500" />
            </div>
          </div>
        </header>

        {/* Stats Row */}
        <motion.div 
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8"
        >
          <div className="glass-card p-6 rounded-3xl relative overflow-hidden group hover:-translate-y-1 transition-transform">
            <div className="absolute top-0 right-0 w-32 h-32 bg-blue-500/10 rounded-full blur-2xl -mr-10 -mt-10 transition-transform group-hover:scale-150"></div>
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-slate-500 font-medium mb-1">Active Applications</p>
                <h3 className="text-4xl font-bold text-slate-800">2</h3>
              </div>
              <div className="p-3 bg-blue-50 text-blue-600 rounded-2xl shadow-sm">
                <FileText size={24} />
              </div>
            </div>
          </div>

          <div className="glass-card p-6 rounded-3xl relative overflow-hidden group hover:-translate-y-1 transition-transform">
            <div className="absolute top-0 right-0 w-32 h-32 bg-amber-500/10 rounded-full blur-2xl -mr-10 -mt-10 transition-transform group-hover:scale-150"></div>
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-slate-500 font-medium mb-1">Pending Actions</p>
                <h3 className="text-4xl font-bold text-slate-800">1</h3>
              </div>
              <div className="p-3 bg-amber-50 text-amber-600 rounded-2xl shadow-sm">
                <AlertTriangle size={24} />
              </div>
            </div>
          </div>

          <div className="glass-card p-6 rounded-3xl relative overflow-hidden group hover:-translate-y-1 transition-transform">
            <div className="absolute top-0 right-0 w-32 h-32 bg-green-500/10 rounded-full blur-2xl -mr-10 -mt-10 transition-transform group-hover:scale-150"></div>
            <div className="flex justify-between items-start mb-4">
              <div>
                <p className="text-slate-500 font-medium mb-1">Approved</p>
                <h3 className="text-4xl font-bold text-slate-800">0</h3>
              </div>
              <div className="p-3 bg-green-50 text-green-600 rounded-2xl shadow-sm">
                <CheckCircle size={24} />
              </div>
            </div>
          </div>
        </motion.div>

        {/* Applications List */}
        <h2 className="text-xl font-bold mb-6 text-slate-800">Recent Applications</h2>
        <div className="space-y-4">
          {applications.map((app, i) => (
            <motion.div 
              key={app.id}
              initial={{ opacity: 0, x: -20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 + (i * 0.1) }}
              className="glass-card p-6 rounded-3xl flex flex-col md:flex-row items-center justify-between gap-6 hover:shadow-lg hover:shadow-brand-500/5 transition-all border border-transparent hover:border-brand-500/20"
            >
              <div className="flex items-center gap-5 w-full md:w-auto">
                <div className={cn(
                  "w-14 h-14 rounded-2xl flex items-center justify-center shrink-0 shadow-sm",
                  app.status === 'DEFICIENT' ? 'bg-amber-100 text-amber-600' : 'bg-blue-100 text-blue-600'
                )}>
                  {app.status === 'DEFICIENT' ? <AlertTriangle size={28} /> : <Clock size={28} />}
                </div>
                <div>
                  <div className="flex items-center gap-3 mb-1">
                    <span className="text-xs font-semibold text-slate-500 tracking-wider uppercase">{app.id}</span>
                    <span className={cn(
                      "text-xs px-2.5 py-1 rounded-full font-medium shadow-sm",
                      app.status === 'DEFICIENT' ? 'bg-amber-100 text-amber-700' : 'bg-blue-100 text-blue-700'
                    )}>
                      {app.status.replace("_", " ")}
                    </span>
                  </div>
                  <h3 className="font-bold text-lg text-slate-800 leading-tight">{app.scheme}</h3>
                  <p className="text-sm text-slate-500 mt-1">Submitted on {app.submittedAt}</p>
                </div>
              </div>

              <div className="w-full md:w-1/3 flex items-center gap-6">
                <div className="flex-1">
                  <div className="flex justify-between text-sm mb-2">
                    <span className="text-slate-600 font-medium">Processing Progress</span>
                    <span className="font-bold text-slate-800">{app.progress}%</span>
                  </div>
                  <div className="h-2.5 bg-slate-200/60 rounded-full overflow-hidden shadow-inner">
                    <motion.div 
                      initial={{ width: 0 }}
                      animate={{ width: `${app.progress}%` }}
                      transition={{ duration: 1, delay: 0.5 }}
                      className={cn(
                        "h-full rounded-full",
                        app.status === 'DEFICIENT' ? 'bg-gradient-to-r from-amber-400 to-amber-500' : 'bg-gradient-to-r from-brand-500 to-purple-500'
                      )}
                    />
                  </div>
                </div>
                <button className="p-3 bg-white hover:bg-slate-50 shadow-sm border border-slate-200/50 rounded-xl transition-colors shrink-0">
                  <ChevronRight size={24} className="text-slate-400" />
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      </main>
    </div>
  );
}

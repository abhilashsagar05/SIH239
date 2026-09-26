"use client";

import React, { useState } from "react";
import Link from "next/link";
import { 
  Search, Filter, ShieldCheck, AlertCircle, 
  ChevronRight, MoreVertical, ShieldAlert, CheckCircle, Clock, LayoutDashboard, LogOut
} from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

// Mock Data
const workQueue = [
  {
    id: "APP-2026-NFST-892",
    applicant: "Rahul Kumar",
    scheme: "National Fellowship for Scheduled Tribe",
    submittedAt: "Oct 26, 2026",
    aiScore: 92.5,
    status: "MANUAL_SCRUTINY",
    priority: "High",
    flags: 0,
  },
  {
    id: "APP-2026-NOS-114",
    applicant: "Priya Sharma",
    scheme: "National Overseas Scholarship",
    submittedAt: "Oct 25, 2026",
    aiScore: 68.0,
    status: "DEFICIENT",
    priority: "Medium",
    flags: 3,
  },
  {
    id: "APP-2026-NFST-401",
    applicant: "Amit Singh",
    scheme: "National Fellowship for Scheduled Tribe",
    submittedAt: "Oct 25, 2026",
    aiScore: 88.2,
    status: "MANUAL_SCRUTINY",
    priority: "Normal",
    flags: 1,
  },
];

export default function AdminWorkQueue() {
  const [searchTerm, setSearchTerm] = useState("");
  const [activeTab, setActiveTab] = useState("queue");

  return (
    <div className="min-h-screen bg-transparent flex">
      {/* Sidebar for Admin */}
      <motion.aside 
        initial={{ x: -250 }}
        animate={{ x: 0 }}
        className="w-64 glass-card border-r border-brand-100/20 hidden lg:flex flex-col p-6 m-4 rounded-3xl shrink-0"
      >
        <div className="flex items-center gap-3 mb-12">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-slate-800 to-slate-900 flex items-center justify-center text-white font-bold text-xl shadow-lg">
            S
          </div>
          <div>
            <h2 className="font-bold text-lg text-slate-800 leading-tight">Scrutiny</h2>
            <p className="text-xs text-slate-500 font-medium">MoTA Admin Portal</p>
          </div>
        </div>

        <nav className="flex-1 space-y-2">
          {[
            { id: "queue", icon: LayoutDashboard, label: "Work Queue" },
            { id: "approved", icon: CheckCircle, label: "Approved" },
            { id: "flagged", icon: ShieldAlert, label: "Flagged Apps" },
          ].map((item) => (
            <button
              key={item.id}
              onClick={() => setActiveTab(item.id)}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-3 rounded-xl transition-all",
                activeTab === item.id 
                  ? "bg-slate-900 text-white font-medium shadow-md shadow-slate-900/20" 
                  : "text-slate-600 hover:bg-slate-100/50 hover:text-slate-900"
              )}
            >
              <item.icon size={20} className={activeTab === item.id ? "text-white" : "text-slate-500"} />
              {item.label}
            </button>
          ))}
        </nav>
        
        <div className="mt-auto pt-6 border-t border-slate-200/50">
          <Link href="/" className="w-full flex items-center gap-3 px-4 py-2 text-red-500 hover:text-red-600 font-medium transition-colors">
            <LogOut size={20} />
            Sign Out
          </Link>
        </div>
      </motion.aside>

      <main className="flex-1 p-4 lg:p-8 lg:pl-4 overflow-y-auto w-full">
        {/* Header */}
        <header className="mb-8 flex flex-col md:flex-row md:items-center justify-between gap-4 glass-card p-6 rounded-3xl">
          <div>
            <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">Scrutiny Queue</h1>
            <p className="text-slate-500 mt-1 font-medium">Review and process submitted applications.</p>
          </div>
          <div className="flex items-center gap-3 w-full md:w-auto">
            <div className="relative w-full md:w-64">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={20} />
              <input 
                type="text" 
                placeholder="Search ID or Name..." 
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full pl-10 pr-4 py-3 bg-white/80 border border-slate-200/60 rounded-xl focus:outline-none focus:ring-2 focus:ring-slate-900 shadow-sm transition-all"
              />
            </div>
            <button className="p-3 bg-white/80 border border-slate-200/60 rounded-xl hover:bg-white text-slate-600 transition-colors shadow-sm shrink-0">
              <Filter size={20} />
            </button>
          </div>
        </header>

        {activeTab === "queue" && (
          <>
            {/* Stats Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 lg:gap-6 mb-8">
              {[
                { label: "Pending Scrutiny", count: 124, icon: Clock, color: "text-blue-600", bg: "bg-blue-100/50", border: "border-blue-200/50" },
                { label: "AI Flagged", count: 18, icon: ShieldAlert, color: "text-rose-600", bg: "bg-rose-100/50", border: "border-rose-200/50" },
                { label: "Approved Today", count: 45, icon: CheckCircle, color: "text-emerald-600", bg: "bg-emerald-100/50", border: "border-emerald-200/50" },
                { label: "Deficient", count: 12, icon: AlertCircle, color: "text-amber-600", bg: "bg-amber-100/50", border: "border-amber-200/50" },
              ].map((stat, i) => (
                <motion.div 
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i * 0.1 }}
                  key={i} 
                  className={cn("glass-card p-6 rounded-3xl flex items-center justify-between border-t-4", stat.border)}
                >
                  <div>
                    <p className="text-sm text-slate-500 font-semibold mb-1 uppercase tracking-wider">{stat.label}</p>
                    <h4 className="text-4xl font-extrabold text-slate-800">{stat.count}</h4>
                  </div>
                  <div className={cn("p-4 rounded-2xl shadow-sm", stat.bg, stat.color)}>
                    <stat.icon size={28} />
                  </div>
                </motion.div>
              ))}
            </div>

            {/* Table Container */}
            <div className="glass-card rounded-3xl overflow-hidden shadow-lg border border-slate-200/50">
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse whitespace-nowrap">
                  <thead>
                    <tr className="bg-slate-50/80 border-b border-slate-200/50">
                      <th className="py-5 px-6 font-bold text-xs uppercase tracking-wider text-slate-500">Application Info</th>
                      <th className="py-5 px-6 font-bold text-xs uppercase tracking-wider text-slate-500">Scheme</th>
                      <th className="py-5 px-6 font-bold text-xs uppercase tracking-wider text-slate-500">AI Trust Score</th>
                      <th className="py-5 px-6 font-bold text-xs uppercase tracking-wider text-slate-500">Status</th>
                      <th className="py-5 px-6 font-bold text-xs uppercase tracking-wider text-slate-500">Submitted</th>
                      <th className="py-5 px-6 font-bold text-xs uppercase tracking-wider text-slate-500 text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100/80">
                    {workQueue.map((app, i) => (
                      <motion.tr 
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.3 + (i * 0.05) }}
                        key={app.id} 
                        className="hover:bg-white/60 transition-colors group"
                      >
                        <td className="py-5 px-6">
                          <div className="font-bold text-slate-900 text-base">{app.applicant}</div>
                          <div className="text-xs font-semibold text-slate-400 font-mono mt-1 uppercase tracking-wider">{app.id}</div>
                        </td>
                        <td className="py-5 px-6">
                          <div className="text-sm font-medium text-slate-700 max-w-[250px] truncate">{app.scheme}</div>
                        </td>
                        <td className="py-5 px-6">
                          <div className="flex items-center gap-3">
                            <div className="relative w-12 h-12 flex items-center justify-center">
                              <svg className="w-full h-full -rotate-90" viewBox="0 0 36 36">
                                <path
                                  className="text-slate-100"
                                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="3"
                                />
                                <path
                                  className={cn(
                                    app.aiScore >= 80 ? "text-emerald-500" : app.aiScore >= 60 ? "text-amber-500" : "text-rose-500"
                                  )}
                                  strokeDasharray={`${app.aiScore}, 100`}
                                  d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="3"
                                />
                              </svg>
                              <span className="absolute text-[10px] font-bold text-slate-700">{app.aiScore}%</span>
                            </div>
                            {app.flags > 0 && (
                              <span className="flex items-center gap-1 text-[11px] font-bold text-rose-700 bg-rose-100 px-2 py-1 rounded-md shadow-sm border border-rose-200">
                                <ShieldAlert size={12} />
                                {app.flags} Flags
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="py-5 px-6">
                          <span className={cn(
                            "text-xs px-3 py-1.5 rounded-full font-bold shadow-sm border",
                            app.status === 'MANUAL_SCRUTINY' 
                              ? 'bg-blue-50 text-blue-700 border-blue-200' 
                              : 'bg-amber-50 text-amber-700 border-amber-200'
                          )}>
                            {app.status.replace("_", " ")}
                          </span>
                        </td>
                        <td className="py-5 px-6 text-sm font-medium text-slate-500">
                          {app.submittedAt}
                        </td>
                        <td className="py-5 px-6 text-right">
                          <Link 
                            href={`/admin/review/${app.id}`}
                            className="inline-flex items-center gap-1.5 text-sm font-bold text-white bg-slate-900 hover:bg-slate-800 px-4 py-2.5 rounded-xl transition-all shadow-md hover:shadow-lg hover:-translate-y-0.5"
                          >
                            Review <ChevronRight size={16} />
                          </Link>
                        </td>
                      </motion.tr>
                    ))}
                  </tbody>
                </table>
              </div>
              
              {/* Pagination */}
              <div className="bg-slate-50/50 border-t border-slate-200/50 p-5 flex flex-col sm:flex-row items-center justify-between gap-4 text-sm font-medium text-slate-500">
                <span>Showing 1 to 3 of 124 applications</span>
                <div className="flex gap-2">
                  <button className="px-4 py-2 rounded-lg border border-slate-200 hover:bg-white shadow-sm disabled:opacity-50 transition-colors" disabled>Previous</button>
                  <button className="px-4 py-2 rounded-lg bg-slate-900 text-white shadow-md">1</button>
                  <button className="px-4 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 shadow-sm transition-colors">2</button>
                  <button className="px-4 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 shadow-sm transition-colors">3</button>
                  <button className="px-4 py-2 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 shadow-sm transition-colors">Next</button>
                </div>
              </div>
            </div>
          </>
        )}

        {activeTab === "approved" && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass-card p-12 rounded-3xl text-center border border-slate-200/50 shadow-sm">
            <CheckCircle size={48} className="mx-auto text-emerald-500 mb-4 opacity-70" />
            <h2 className="text-2xl font-bold text-slate-800 mb-2">Approved Applications</h2>
            <p className="text-slate-500 max-w-md mx-auto">There are 45 approved applications today. They have been forwarded to the disbursement module.</p>
          </motion.div>
        )}

        {activeTab === "flagged" && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass-card p-12 rounded-3xl text-center border border-slate-200/50 shadow-sm">
            <ShieldAlert size={48} className="mx-auto text-rose-500 mb-4 opacity-70" />
            <h2 className="text-2xl font-bold text-slate-800 mb-2">AI Flagged Applications</h2>
            <p className="text-slate-500 max-w-md mx-auto">There are 18 applications flagged by the AI for document mismatches or blurriness requiring manual attention.</p>
          </motion.div>
        )}
      </main>
    </div>
  );
}

"use client";

import React, { use } from "react";
import { useRouter } from "next/navigation";
import { 
  ArrowLeft, CheckCircle2, XCircle, ShieldAlert,
  FileText, Check, AlertCircle, Download, FileCheck, ShieldCheck
} from "lucide-react";
import { cn } from "@/lib/utils";

export default function ApplicationReviewPage({ params }: { params: Promise<{ id: string }> }) {
  const router = useRouter();
  const unwrappedParams = use(params);

  return (
    <div className="min-h-screen bg-transparent p-4 lg:p-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <button 
            onClick={() => router.push("/admin/queue")}
            className="p-2 rounded-xl bg-white border border-slate-200 hover:bg-slate-50 transition-colors shadow-sm"
          >
            <ArrowLeft size={24} className="text-slate-600" />
          </button>
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Review Application</h1>
            <p className="text-sm font-mono text-slate-500 uppercase">{unwrappedParams.id}</p>
          </div>
        </div>
        
        <div className="flex gap-3">
          <button className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white border border-red-200 text-red-600 hover:bg-red-50 font-bold shadow-sm transition-all">
            <XCircle size={18} /> Reject
          </button>
          <button className="flex items-center gap-2 px-4 py-2 rounded-xl bg-amber-500 text-white hover:bg-amber-600 font-bold shadow-sm transition-all">
            <AlertCircle size={18} /> Mark Deficient
          </button>
          <button className="flex items-center gap-2 px-6 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-emerald-600 text-white font-bold shadow-md hover:shadow-lg transition-all">
            <CheckCircle2 size={18} /> Approve
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Applicant Details */}
        <div className="lg:col-span-2 space-y-6">
          <div className="glass-card p-6 rounded-3xl border border-slate-200/60 shadow-sm">
            <h2 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
              <UserCircle size={20} className="text-brand-500" /> Applicant Details
            </h2>
            
            <div className="grid grid-cols-2 md:grid-cols-3 gap-6">
              <div>
                <p className="text-sm font-medium text-slate-500 mb-1">Full Name</p>
                <p className="font-semibold text-slate-900">Rahul Kumar</p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500 mb-1">Gender</p>
                <p className="font-semibold text-slate-900">Male</p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500 mb-1">Category</p>
                <p className="font-semibold text-slate-900">ST</p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500 mb-1">DOB</p>
                <p className="font-semibold text-slate-900">14 Aug 1999</p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500 mb-1">State</p>
                <p className="font-semibold text-slate-900">Maharashtra (MH)</p>
              </div>
              <div>
                <p className="text-sm font-medium text-slate-500 mb-1">Annual Income</p>
                <p className="font-semibold text-slate-900">₹ 2,40,000</p>
              </div>
            </div>
          </div>

          <div className="glass-card p-6 rounded-3xl border border-slate-200/60 shadow-sm">
            <h2 className="text-lg font-bold text-slate-800 mb-6 flex items-center gap-2">
              <FileCheck size={20} className="text-brand-500" /> Uploaded Documents
            </h2>
            
            <div className="space-y-4">
              {[
                { name: "Caste Certificate", type: "CASTE_CERT", status: "VERIFIED", score: 98 },
                { name: "Income Certificate", type: "INCOME_CERT", status: "VERIFIED", score: 95 },
                { name: "Aadhaar Card", type: "ID_PROOF", status: "FLAGGED", score: 62 },
                { name: "10th Marksheet", type: "ACADEMIC", status: "VERIFIED", score: 89 }
              ].map((doc, idx) => (
                <div key={idx} className="flex items-center justify-between p-4 rounded-2xl bg-slate-50 border border-slate-100">
                  <div className="flex items-center gap-4">
                    <div className={cn(
                      "p-3 rounded-xl",
                      doc.status === 'VERIFIED' ? 'bg-emerald-100 text-emerald-600' : 'bg-rose-100 text-rose-600'
                    )}>
                      <FileText size={20} />
                    </div>
                    <div>
                      <h4 className="font-bold text-slate-800">{doc.name}</h4>
                      <p className="text-xs font-mono text-slate-500">{doc.type}</p>
                    </div>
                  </div>
                  
                  <div className="flex items-center gap-6">
                    <div className="text-right">
                      <p className="text-xs text-slate-500 font-medium mb-1">AI Confidence</p>
                      <div className="flex items-center gap-2">
                        <div className="w-24 h-2 bg-slate-200 rounded-full overflow-hidden">
                          <div 
                            className={cn("h-full rounded-full", doc.status === 'VERIFIED' ? 'bg-emerald-500' : 'bg-rose-500')}
                            style={{ width: `${doc.score}%` }}
                          />
                        </div>
                        <span className="text-xs font-bold text-slate-700">{doc.score}%</span>
                      </div>
                    </div>
                    <button className="p-2 text-slate-400 hover:text-brand-600 hover:bg-brand-50 rounded-lg transition-colors">
                      <Download size={20} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Right Column: AI Analysis */}
        <div className="space-y-6">
          <div className="glass-card p-6 rounded-3xl border border-slate-200/60 shadow-sm bg-gradient-to-br from-slate-900 to-slate-800 text-white">
            <div className="flex items-center gap-2 mb-6">
              <ShieldCheck size={24} className="text-emerald-400" />
              <h2 className="text-lg font-bold">AI Scrutiny Report</h2>
            </div>
            
            <div className="mb-8">
              <p className="text-sm text-slate-300 font-medium mb-2">Overall Trust Score</p>
              <div className="flex items-end gap-3">
                <span className="text-5xl font-extrabold text-white">92.5</span>
                <span className="text-lg text-emerald-400 font-bold mb-1">%</span>
              </div>
            </div>

            <div className="space-y-4">
              <div className="p-4 rounded-2xl bg-white/10 border border-white/5 backdrop-blur-sm">
                <div className="flex items-start gap-3">
                  <Check size={20} className="text-emerald-400 shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-bold text-sm">Identity Verified</h4>
                    <p className="text-xs text-slate-300 mt-1">Aadhaar details perfectly match application data and certificates.</p>
                  </div>
                </div>
              </div>
              <div className="p-4 rounded-2xl bg-rose-500/20 border border-rose-500/20 backdrop-blur-sm">
                <div className="flex items-start gap-3">
                  <ShieldAlert size={20} className="text-rose-400 shrink-0 mt-0.5" />
                  <div>
                    <h4 className="font-bold text-sm text-rose-100">Document Flag</h4>
                    <p className="text-xs text-rose-200 mt-1">Slight blurriness detected in Aadhaar card scan. Human review recommended.</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// Ensure UserCircle is imported
import { UserCircle } from "lucide-react";

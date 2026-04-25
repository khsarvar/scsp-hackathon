"use client";

import LeftSidebar from "./LeftSidebar";
import RightPanel from "./RightPanel";
import WorkspaceArea from "@/components/workspace/WorkspaceArea";
import { useSession } from "@/hooks/useSession";

export default function AppShell() {
  const { state } = useSession();

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50">
      {/* Left Sidebar */}
      <aside className="w-72 flex-shrink-0 border-r border-slate-200 bg-white flex flex-col overflow-hidden">
        <LeftSidebar />
      </aside>

      {/* Main Workspace */}
      <main className="flex-1 overflow-y-auto">
        <WorkspaceArea />
      </main>

      {/* Right Chat Panel */}
      <aside className="w-80 flex-shrink-0 border-l border-slate-200 bg-white flex flex-col overflow-hidden">
        <RightPanel sessionId={state.sessionId} />
      </aside>
    </div>
  );
}

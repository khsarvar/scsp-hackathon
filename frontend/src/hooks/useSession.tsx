"use client";

import React, {
  createContext,
  useContext,
  useReducer,
  useCallback,
} from "react";
import type {
  AppState,
  AppStep,
  UploadResponse,
  ProfileResponse,
  AnalyzeResponse,
  AgentEvent,
  Hypothesis,
  RunTestResponse,
  LiteratureResult,
  WorkspaceTab,
  SessionHistory,
} from "@/types";

type Action =
  | { type: "SET_STEP"; step: AppStep }
  | { type: "SET_UPLOAD"; payload: UploadResponse }
  | { type: "SET_PROFILE"; payload: ProfileResponse }
  | { type: "SET_ANALYSIS"; payload: AnalyzeResponse }
  | { type: "SET_ERROR"; error: string }
  | { type: "RESET" }
  | { type: "LOAD_HISTORY"; history: SessionHistory[] }
  | { type: "DISCOVER_EVENT"; event: AgentEvent }
  | { type: "DISCOVER_RESET" }
  | { type: "CLEAN_EVENT"; event: AgentEvent }
  | { type: "CLEAN_RESET" }
  | { type: "ASK_EVENT"; event: AgentEvent }
  | { type: "ASK_RESET" }
  | { type: "SET_HYPOTHESES"; hypotheses: Hypothesis[] }
  | { type: "SET_TEST_RESULT"; result: RunTestResponse }
  | { type: "LITERATURE_EVENT"; event: AgentEvent }
  | { type: "LITERATURE_RESET" }
  | { type: "SET_LITERATURE_RESULT"; result: LiteratureResult }
  | { type: "SET_ACTIVE_TAB"; tab: WorkspaceTab }
  | { type: "SET_PLAN"; plan: string };

const initialState: AppState = {
  step: "idle",
  sessionId: null,
  uploadResult: null,
  profileResult: null,
  analysisResult: null,
  error: null,
  history: [],
  discoverEvents: [],
  cleanEvents: [],
  askEvents: [],
  hypotheses: [],
  lastTestResult: null,
  literatureEvents: [],
  literatureResult: null,
  activeTab: "discover",
};

function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case "SET_STEP":
      return { ...state, step: action.step, error: null };
    case "SET_UPLOAD":
      return {
        ...state,
        step: "preview",
        sessionId: action.payload.session_id,
        uploadResult: action.payload,
        profileResult: null,
        analysisResult: null,
        error: null,
        cleanEvents: [],
        askEvents: [],
        hypotheses: [],
        lastTestResult: null,
        literatureEvents: [],
        literatureResult: null,
        activeTab: "discover",
      };
    case "SET_PROFILE":
      return {
        ...state,
        step: "planned",
        profileResult: action.payload,
        error: null,
      };
    case "SET_ANALYSIS":
      return {
        ...state,
        step: "results",
        analysisResult: action.payload,
        error: null,
      };
    case "SET_ERROR":
      return { ...state, step: "error", error: action.error };
    case "RESET":
      return { ...initialState, history: state.history };
    case "LOAD_HISTORY":
      return { ...state, history: action.history };
    case "DISCOVER_EVENT":
      return { ...state, discoverEvents: [...state.discoverEvents, action.event] };
    case "DISCOVER_RESET":
      return { ...state, discoverEvents: [] };
    case "CLEAN_EVENT":
      return { ...state, cleanEvents: [...state.cleanEvents, action.event] };
    case "CLEAN_RESET":
      return { ...state, cleanEvents: [] };
    case "ASK_EVENT":
      return { ...state, askEvents: [...state.askEvents, action.event] };
    case "ASK_RESET":
      return { ...state, askEvents: [] };
    case "SET_HYPOTHESES":
      return { ...state, hypotheses: action.hypotheses };
    case "SET_TEST_RESULT":
      return { ...state, lastTestResult: action.result };
    case "LITERATURE_EVENT":
      return { ...state, literatureEvents: [...state.literatureEvents, action.event] };
    case "LITERATURE_RESET":
      return { ...state, literatureEvents: [], literatureResult: null };
    case "SET_LITERATURE_RESULT":
      return { ...state, literatureResult: action.result };
    case "SET_ACTIVE_TAB":
      return { ...state, activeTab: action.tab };
    case "SET_PLAN":
      if (!state.profileResult) return state;
      return {
        ...state,
        profileResult: { ...state.profileResult, analysis_plan: action.plan },
      };
    default:
      return state;
  }
}

interface SessionContextValue {
  state: AppState;
  dispatch: React.Dispatch<Action>;
  reset: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);

const reset = useCallback(() => dispatch({ type: "RESET" }), []);

  return (
    <SessionContext.Provider value={{ state, dispatch, reset }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}

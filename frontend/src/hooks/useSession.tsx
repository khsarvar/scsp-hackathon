"use client";

import React, {
  createContext,
  useContext,
  useReducer,
  useCallback,
  useEffect,
} from "react";
import type {
  AppState,
  AppStep,
  UploadResponse,
  ProfileResponse,
  AnalyzeResponse,
  SessionHistory,
  AgentEvent,
  Hypothesis,
  RunTestResponse,
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
  | { type: "SET_TEST_RESULT"; result: RunTestResponse };

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

  // Persist history to localStorage
  useEffect(() => {
    try {
      const saved = localStorage.getItem("healthlab_history");
      if (saved) {
        dispatch({ type: "LOAD_HISTORY", history: JSON.parse(saved) });
      }
    } catch {}
  }, []);

  useEffect(() => {
    if (state.uploadResult && state.sessionId) {
      const entry: SessionHistory = {
        session_id: state.sessionId,
        filename: state.uploadResult.filename,
        row_count: state.uploadResult.row_count,
        col_count: state.uploadResult.col_count,
        created_at: new Date().toISOString(),
      };
      const updated = [entry, ...state.history.filter(h => h.session_id !== state.sessionId)].slice(0, 10);
      try {
        localStorage.setItem("healthlab_history", JSON.stringify(updated));
      } catch {}
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.uploadResult, state.sessionId]);

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

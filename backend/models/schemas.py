from pydantic import BaseModel
from typing import Any, Optional


class OutlierInfo(BaseModel):
    row_index: int
    value: float
    method: str = "IQR"


class ColumnProfile(BaseModel):
    name: str
    dtype_inferred: str  # 'datetime', 'numeric', 'categorical', 'id'
    missing_count: int
    missing_pct: float
    unique_count: int
    sample_values: list[Any] = []
    min: Optional[float] = None
    max: Optional[float] = None
    mean: Optional[float] = None
    std: Optional[float] = None
    is_datetime_like: bool = False
    is_categorical: bool = False
    outliers: list[OutlierInfo] = []


class DataSource(BaseModel):
    alias: str
    source_str: str
    cdc_id: Optional[str] = None
    cdc_url: Optional[str] = None
    soql_filter: Optional[str] = None
    soql_select: Optional[str] = None
    parents: list[str] = []


class DataProvenance(BaseModel):
    type: str  # 'upload' | 'cdc_discover'
    filename: Optional[str] = None
    research_question: Optional[str] = None
    primary_alias: Optional[str] = None
    sources: list[DataSource] = []


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    row_count: int
    col_count: int
    columns: list[str]
    preview_rows: list[dict[str, Any]]
    file_size_bytes: int
    provenance: Optional[DataProvenance] = None


class ProfileRequest(BaseModel):
    session_id: str


class ProfileResponse(BaseModel):
    session_id: str
    row_count: int
    col_count: int
    duplicate_rows: int
    columns: list[ColumnProfile]
    analysis_plan: str


class AnalyzeRequest(BaseModel):
    session_id: str
    question: Optional[str] = None


class StatRow(BaseModel):
    column: str
    count: int
    mean: Optional[float] = None
    median: Optional[float] = None
    std: Optional[float] = None
    min: Optional[float] = None
    max: Optional[float] = None
    p25: Optional[float] = None
    p75: Optional[float] = None


class ChartSpec(BaseModel):
    chart_type: str  # 'line', 'scatter', 'bar'
    title: str
    x_key: str
    y_keys: list[str] = []
    y_key: Optional[str] = None
    data: list[dict[str, Any]]


class CodeStep(BaseModel):
    rationale: str = ""
    code: str
    stdout: str = ""
    stderr: str = ""
    charts: list[str] = []
    ok: bool = True


class AnalyzeResponse(BaseModel):
    session_id: str
    research_question: Optional[str] = None
    cleaning_steps: list[str] = []
    steps: list[CodeStep] = []
    summary: str = ""
    findings: str = ""
    limitations: str = ""
    follow_up: str = ""


class ChatMessage(BaseModel):
    role: str  # 'user' | 'assistant'
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: list[ChatMessage] = []


# ---------- akbar/init agent upgrades ----------

class RecommendRequest(BaseModel):
    """Search the CDC catalog and return dataset recommendations for a research question."""
    question: str


class DiscoverRequest(BaseModel):
    """Run the CDC discovery agent to fetch + prepare datasets for a research question."""
    question: str
    selected_dataset_ids: list[str] = []
    """Optional: user-pre-selected CDC dataset IDs from the recommend step. If provided,
    the agent skips scouting and fetches these directly."""


class HypothesesRequest(BaseModel):
    session_id: str
    n: int = 4


class Hypothesis(BaseModel):
    question: str
    variables: list[str] = []
    test_type: Optional[str] = None
    args: dict[str, Any] = {}
    rationale: Optional[str] = None


class HypothesesResponse(BaseModel):
    session_id: str
    hypotheses: list[Hypothesis]


class RunTestRequest(BaseModel):
    """Run a single statistical test (no LLM) against a session's primary dataset."""
    session_id: str
    test: str  # 'two_group_numeric' | 'multi_group_numeric' | 'two_categorical' | 'correlation'
    args: dict[str, Any]


class RunTestResponse(BaseModel):
    session_id: str
    test: str
    args: dict[str, Any]
    result: dict[str, Any]


class AskRequest(BaseModel):
    """Ask a free-form analytical question; the agent picks a test and explains."""
    session_id: str
    question: str


class UpdatePlanRequest(BaseModel):
    """Overwrite the analysis plan with user-edited text."""
    session_id: str
    plan: str


class RefinePlanRequest(BaseModel):
    """Ask the AI to revise the current analysis plan based on a user instruction."""
    session_id: str
    instruction: str

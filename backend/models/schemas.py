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


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    row_count: int
    col_count: int
    columns: list[str]
    preview_rows: list[dict[str, Any]]
    file_size_bytes: int


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


class AnalyzeResponse(BaseModel):
    session_id: str
    cleaning_steps: list[str]
    stats: list[StatRow]
    charts: list[ChartSpec]
    findings: str
    limitations: str
    follow_up: str


class ChatMessage(BaseModel):
    role: str  # 'user' | 'assistant'
    content: str


class ChatRequest(BaseModel):
    session_id: str
    message: str
    history: list[ChatMessage] = []

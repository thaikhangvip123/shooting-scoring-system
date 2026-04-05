"""
backend/models/stats.py
Response models for analytics endpoints.
"""

from pydantic import BaseModel, Field


class MeanPOI(BaseModel):
    x_mm: float
    y_mm: float


class RingDistribution(BaseModel):
    X:  int = 0
    r10: int = Field(0, alias="10")
    r9:  int = Field(0, alias="9")
    r8:  int = Field(0, alias="8")
    r7:  int = Field(0, alias="7")
    r6:  int = Field(0, alias="6")
    r5:  int = Field(0, alias="5")
    r4:  int = Field(0, alias="4")
    r3:  int = Field(0, alias="3")
    r2:  int = Field(0, alias="2")
    r1:  int = Field(0, alias="1")
    M:   int = 0

    model_config = {"populate_by_name": True}


from pydantic import Field


class StatsResponse(BaseModel):
    """Aggregated statistics for a set of shots."""

    count:           int
    total_score:     int
    avg_score:       float
    cep_mm:          float    # Circular Error Probable
    r50_mm:          float    # R50 group centre radius
    group_size_mm:   float    # extreme spread
    std_x_mm:        float    # standard deviation in X
    std_y_mm:        float    # standard deviation in Y
    mean_poi:        MeanPOI
    hit_rate:        float    # fraction with score > 0
    ring_distribution: dict[str, int]
    session_id:      str | None = None


class HeatmapResponse(BaseModel):
    resolution:       int
    target_radius_mm: float
    grid:             list[list[int]]   # [row][col] hit counts
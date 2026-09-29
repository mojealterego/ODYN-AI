from pydantic import BaseModel, Field


class MCPServerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    endpoint: str = Field(min_length=8, max_length=2000)


class MCPToolRequest(BaseModel):
    server_name: str = Field(min_length=1, max_length=100)
    tool_name: str = Field(min_length=1, max_length=200)
    payload: dict = Field(default_factory=dict)

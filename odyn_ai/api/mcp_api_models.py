from pydantic import BaseModel, Field


class MCPServerRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    endpoint: str = Field(min_length=8, max_length=2000)
    auth_kind: str = Field(default="none", pattern=r"^(none|api_key|bearer)$")
    secret_env: str | None = Field(default=None, max_length=200)
    auth_header: str = Field(default="Authorization", max_length=100)
    auth_prefix: str = Field(default="Bearer ", max_length=50)
    client_id_env: str | None = Field(default=None, max_length=200)
    client_secret_env: str | None = Field(default=None, max_length=200)
    token_url: str | None = Field(default=None, max_length=2000)
    scope: str | None = Field(default=None, max_length=1000)


class MCPToolRequest(BaseModel):
    server_name: str = Field(min_length=1, max_length=100)
    tool_name: str = Field(min_length=1, max_length=200)
    payload: dict = Field(default_factory=dict)

"""
Workflow Orchestrator routes -- FastAPI router for workflow orchestration.

Endpoints:
  GET    /api/orchestrator/state-machines         — list available state machines
  GET    /api/orchestrator/state-machines/{name}   — get state machine definition
  POST   /api/orchestrator/plan                    — dry-run: show execution plan
  POST   /api/orchestrator/execute                 — start an execution
  GET    /api/orchestrator/executions               — list recent executions
  GET    /api/orchestrator/executions/{id}          — get execution status
  POST   /api/orchestrator/executions/{id}/cancel   — cancel a running execution
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from workflow_orchestrator import (
    list_state_machines,
    get_state_machine_definition,
    get_execution_plan,
    start_execution,
    get_execution,
    get_execution_dict,
    list_executions,
    cancel_execution,
    resume_execution,
    ExecutionMode,
)

router = APIRouter(prefix="/api/orchestrator", tags=["orchestrator"])


class ExecuteRequest(BaseModel):
    state_machine: str
    input_params: dict = {}
    mode: Optional[str] = None


class PlanRequest(BaseModel):
    state_machine: str
    input_params: dict = {}


@router.get("/state-machines")
async def api_list_state_machines():
    return {"state_machines": list_state_machines()}


@router.get("/state-machines/{name}")
async def api_get_state_machine(name: str):
    defn = get_state_machine_definition(name)
    if not defn:
        raise HTTPException(status_code=404, detail=f"State machine '{name}' not found")
    return {"name": name, "definition": defn}


@router.post("/plan")
async def api_get_plan(req: PlanRequest):
    plan = get_execution_plan(req.state_machine, req.input_params)
    if "error" in plan:
        raise HTTPException(status_code=400, detail=plan["error"])
    return plan


@router.post("/execute")
async def api_start_execution(req: ExecuteRequest):
    mode = None
    if req.mode:
        try:
            mode = ExecutionMode(req.mode)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid mode: {req.mode}. Use 'local' or 'aws'.")

    try:
        execution = await start_execution(req.state_machine, req.input_params, mode)
        return execution.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/executions")
async def api_list_executions(limit: int = 20):
    execs = await list_executions(limit)
    return {"executions": execs, "count": len(execs)}


@router.get("/executions/{execution_id}")
async def api_get_execution(execution_id: str):
    data = await get_execution_dict(execution_id)
    if not data:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return data


@router.post("/executions/{execution_id}/cancel")
async def api_cancel_execution(execution_id: str):
    cancelled = await cancel_execution(execution_id)
    if not cancelled:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return {"execution_id": execution_id, "status": "cancelled"}


@router.post("/executions/{execution_id}/resume")
async def api_resume_execution(execution_id: str):
    execution = await resume_execution(execution_id)
    if not execution:
        raise HTTPException(
            status_code=400,
            detail=f"Execution '{execution_id}' not found or not in a resumable state (must be failed or cancelled)",
        )
    return execution.to_dict()


@router.get("/executions/{execution_id}/agent-stats")
async def api_get_execution_agent_stats(execution_id: str):
    from workflow_orchestrator import _get_execution_agent_stats
    execution = await get_execution(execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return {
        "success": True,
        "agent_stats": _get_execution_agent_stats(execution),
        "agent_events": execution.agent_events,
    }

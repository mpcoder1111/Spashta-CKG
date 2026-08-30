"""
Spashta-CKG – FastAPI Adapter Dummy Test Code (v1)

PURPOSE
-------
This file is part of the FastAPI Adapter test suite for Spashta-CKG.
It is NOT a runnable FastAPI application.

The goal of this code is to provide realistic FastAPI patterns that allow:
- Builders to extract correct Python AST structure
- Adapters to detect FastAPI-specific semantics
- Validators to verify framework rules and contracts

This code intentionally balances realism with simplicity.

WHAT THIS FILE IS (AND IS NOT)
------------------------------
✔ IS:
- Representative FastAPI-style code (SQLModel, Pydantic, Routers)
- Used for semantic detection testing
- Used to validate adapter framework_mapping.json rules
- Used to test adapter contract enforcement

❌ IS NOT:
- A full FastAPI project
- Intended to run via `uvicorn`
- Used for application logic testing
- Expected to be production-correct FastAPI code

SEMANTIC COVERAGE
-----------------
Across the dummy FastAPI file, the following framework concepts are exercised:

- DataModels:
  - SQLModel classes (e.g. `Hero`)
- APIContracts:
  - Pydantic BaseModel schemas (e.g. `HeroCreate`)
- Views:
  - Decorated path operations (@app.get, @router.post)
- Routes:
  - Inferred from View decorators (semantic wiring, not call-level routing)
- Dependencies:
  - `Depends()` usage in function arguments
  - Dependency providers (simple functions)
- Intentional Violations:
  - Intentional violations are not included in v1 FastAPI tests but may be added later to exercise adapter contracts.

KNOWN & ACCEPTABLE LIMITATIONS (v1)
-----------------------------------
- Route detection is decorator-based only. Call-level wiring is not validated using explicit Route nodes yet.
- Dependency detection confirms structural usage (calls to `Depends`) but does not infer lifecycle or purity semantics.
- Async-specific semantics are not distinguished in v1.
- These limitations are intentional, documented, and will be revisited as builders evolve.

HOW THIS FILE IS USED IN THE TEST FLOW
--------------------------------------
This file participates in the following validation pipeline:

    dummy_fastapi_app.py
            ↓
    run_build_fastapi_ast.py        (Runs Python Builder)
            ↓
    test_output_ast.json           (Raw, objective AST)
            ↓
    check_fastapi_mapping_coverage.py
        - Performs mock enrichment
        - Verifies FastAPI semantic detectability (DataModel, APIContract, View)
        - Checks inferred structural edges (Route, Dependency)

DESIGN PRINCIPLE
----------------
Builders capture *what exists*.
Adapters explain *what it means*.
Tests verify *what can be safely inferred*.

If you are modifying this file:
- Do NOT add application logic
- Do NOT simplify away real FastAPI patterns
- Do NOT remove intentional test cases
- Keep changes aligned with framework_mapping.json

This file exists to protect adapter correctness and agent safety.
"""
from typing import List, Optional
from fastapi import FastAPI, Depends, APIRouter
from pydantic import BaseModel
from sqlmodel import SQLModel, Field

app = FastAPI()
router = APIRouter()

# --- DataModel Detection (SQLModel) ---
class Hero(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    secret_name: str

# --- APIContract Detection (Pydantic) ---
class HeroCreate(BaseModel):
    name: str
    secret_name: str
    age: Optional[int] = None

# --- View & Route Detection (@app.post) ---
@app.post("/heroes/", response_model=Hero)
def create_hero(hero: HeroCreate):
    return hero

# --- View & Route Detection (@router.get) ---
@router.get("/heroes/", response_model=List[Hero])
def read_heroes():
    return []

# --- Dependency Detection (Depends) ---
def get_session():
    return "session"

@app.get("/users/")
def read_users(session: str = Depends(get_session)):
    pass

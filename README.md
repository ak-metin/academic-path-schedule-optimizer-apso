# Academic Path & Schedule Optimizer (APSO)

> **Adana Alparslan Türkeş Science and Technology University (ATÜ)**  
> **Faculty of Computer and Informatics — Department of Software Engineering**  
> **Software Graduation Project (2026–2027)**  
> **Student:** Metin Ak (`220602047`)  
> **Supervisor:** Asst. Prof. Dr. Havva Esin ÜNAL  

---

## 1. One-Sentence Problem Statement

To eliminate the time loss and scheduling conflict issues caused by managing curriculum dependencies (prerequisites), weekly course timetabling, and exam/proctor allocations manually via Excel in a disconnected manner without constraint optimization.

---

## 2. Quick Setup (In 3 Commands or Fewer)

Per **Section 1.2.1.2** of the *ATÜ Graduation Project Guide*, the entire system (PostgreSQL 16 + FastAPI CP-SAT Backend + React 18 Frontend + pre-seeded ATÜ Software Engineering dataset) starts in **3 commands**:

```bash
git clone https://github.com/ak-metin/academic-path-schedule-optimizer-apso.git
cd academic-path-schedule-optimizer-apso
docker compose up --build
```

- **Frontend Web Application:** `http://localhost:5173`
- **FastAPI Interactive Swagger UI / OpenAPI Docs:** `http://localhost:8000/docs`
- **Health Check Endpoint:** `http://localhost:8000/api/v1/health`

*(Optional Local Development without Docker)*:
```bash
# Terminal 1 (Backend - uses local SQLite fallback automatically if DATABASE_URL is unset)
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload --port 8000

# Terminal 2 (Frontend)
cd frontend && npm install && npm run dev
```

---

## 3. Demo Account & Pre-Seeded ATÜ Dataset

When the application starts (`AUTO_SEED_ON_STARTUP=true`), it automatically initializes an idempotent, **KVKK-compliant** demo dataset calibrated to the **ATÜ Department of Software Engineering**:
- **Demo Role / Access:** No login barrier is required for evaluation; the web console at `http://localhost:5173` opens directly in **Department Coordinator & Academic Advisor Demo Mode** (`coord_demo@atu.edu.tr` / Full Access).
- **Curriculum Catalog:** 40 courses across 8 semesters linked by 36 directed prerequisite/co-requisite edges.
- **Faculty & Rooms:** 12 instructors with availability/preference matrices and 10 lecture halls/computer labs (`B-AMFI-1`..`LAB-AI`).
- **Students & TAs:** 100 synthetic student profiles (`220601001`–`220601100`, including 80 regular cohort students and 20 irregular students retaking failed bottleneck prerequisites) and 8 teaching assistants (`TA-01`–`TA-08`).

---

## 4. How to Run the Automated Tests

The backend test suite verifies database constraints, KVKK compliance, the 1-empty-seat capacity formula, DAG cycle rejection (`HTTP 422`), Critical Path failure simulation, Weekly CP-SAT optimization, Unsat Core diagnostics, Exam/Seating/Proctor Minimax CP-SAT optimization, and Excel/PDF import-export services:

```bash
PYTHONPATH=backend pytest backend/tests -v
```

To verify the Frontend TypeScript types and production bundle:

```bash
cd frontend && npm run build
```

---

## 5. Unified System Architecture (3 Core Modules)

1. **Module 1 — Curriculum Graph Engine (`backend/app/engines/dag_engine.py`):**
   - Models the 8-semester curriculum as a **Directed Acyclic Graph (DAG)** using `NetworkX`.
   - Rejects circular dependencies ($A \to B \to A$) with `HTTP 422` and full cycle path trace.
   - Simulates student course failures (*Critical Path Analysis*), computing downstream transitive closures and graduation delays under 30/40 ECTS caps.
   - Generates the mandatory **Non-Conflict Matrix ($C_{\text{DAG}}$)** for Module 2.

2. **Module 2 — Course Scheduling Engine (`backend/app/engines/weekly_csp.py`):**
   - Solves weekly course timetabling via **Google OR-Tools CP-SAT**.
   - **Hard Constraints (0 Tolerance):** Room capacities, LAB room matching, zero room/instructor double-booking, and all $C_{\text{DAG}}$ non-conflict rules.
   - **Soft Constraints:** Minimizes student daily idle gaps and instructor time-slot preference penalties.
   - **Unsat Core Diagnostics:** Reports actionable Turkish bottleneck explanations (`unsat_diagnostics_tr`) when inputs are over-constrained.

3. **Module 3 — Exam & Proctor Allocation Module (`backend/app/engines/exam_proctor_csp.py`):**
   - Prevents student exam clashes across all shared enrollments.
   - Enforces the **1-Empty-Seat Rule** ($\text{Cap}_{\text{exam}}(r) = \text{Rows}(r) \times \lceil \text{Cols}(r) / 2 \rceil$), automatically splitting large exams across multiple halls and assigning students to odd column coordinates ($\text{col} \in \{1, 3, 5, \dots\}$).
   - Distributes proctoring duties among Teaching Assistants using the **Minimax fairness criterion** ($\min (L_{\max} - L_{\min})$) without clashing with TAs' graduate courses.

---

## 6. Documentation & Deliverables Links

- **[Project Rules & Architectural Contract (AGENTS.md)](./AGENTS.md)**
- **[Short User Manual (docs/USER_MANUAL.md)](./docs/USER_MANUAL.md)**
- **[AI-Use Log (docs/AI_USE_LOG.md)](./docs/AI_USE_LOG.md)**

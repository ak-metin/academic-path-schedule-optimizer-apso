# AI-Use Log — Academic Path & Schedule Optimizer (APSO)

This document fulfills the mandatory **AI-use log: tools used, for what, and in which files** deliverable requirement specified in **Section 1.2.1.2 (Software Project Final Deliverables Checklist)** of the *ATÜ Software Engineering Graduation Project Guide*.

---

## 1. Summary of AI Tools Used

| AI Tool / Environment | Role in the Project | Verification & Human Oversight Policy |
| :--- | :--- | :--- |
| **Google Antigravity (Gemini Agentic IDE)** | Pair-programming assistant for database modeling, NetworkX DAG algorithms, OR-Tools CP-SAT constraint formulation, React/TypeScript frontend scaffolding, and automated Pytest verification. | Every generated constraint formula, SQLAlchemy model, and API endpoint was governed by project-specific architectural rules (`AGENTS.md`) and verified against 14 automated `pytest` invariants and `tsc` compiler checks. |

---

## 2. File-by-File AI Usage Log

| File Path | AI Tool Used | Purpose / What It Was Used For | Verification Method |
| :--- | :--- | :--- | :--- |
| `AGENTS.md` | Google Antigravity | Codifying project-specific architectural, algorithmic (DAG, CP-SAT, 1-Empty-Seat, Minimax Proctor), and KVKK privacy rules. | Manual review & rule enforcement check. |
| `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile` | Google Antigravity | Configuring 3-command containerized startup (`db`, `backend`, `frontend`) with health checks. | Verified Docker Compose configuration & port bindings. |
| `backend/app/config.py`, `backend/app/database.py` | Google Antigravity | Setting up environment-driven configuration (`pydantic-settings`) and SQLAlchemy 2.0 session management with foreign-key enforcement. | `pytest` database fixture verification. |
| `backend/app/models/academic.py` | Google Antigravity | Designing the Single Source of Truth relational schema (`Course`, `CoursePrerequisite`, `Instructor`, `InstructorAvailability`, `Room`, `Student`, `Enrollment`, `WeeklyScheduleAssignment`, `TeachingAssistant`, `TAUnavailability`, `ExamSession`, `ExamRoomAllocation`, `ExamSeatingAssignment`, `ProctorAssignment`) and the `effective_exam_capacity` property ($\text{Rows} \times \lceil \text{Cols}/2 \rceil$). | Verified by `backend/tests/test_step1_foundation.py`. |
| `backend/app/schemas/academic.py` | Google Antigravity | Creating strict Pydantic v2 request/response and Excel row validation schemas. | Verified by FastAPI OpenAPI schema generation & `pytest`. |
| `backend/app/seed/atu_software_eng_seed.py` | Google Antigravity | Generating the idempotent ATÜ Software Engineering 8-semester dataset (40 courses, 36 prerequisite edges, 12 instructors, 10 rooms, 8 TAs, and 100 KVKK-compliant `22060xxxx` synthetic students). | Verified by `test_seed_dataset_completeness_and_idempotency` and `test_kvkk_student_anonymization_compliance`. |
| `backend/app/engines/dag_engine.py` | Google Antigravity | Implementing Module 1: `NetworkX` DAG construction, cycle detection (`HTTP 422`), longest-path Critical Path Analysis, 30/40 ECTS course failure graduation delay simulation, and $C_{\text{DAG}}$ non-conflict matrix generation. | Verified by `backend/tests/test_step2_dag_engine.py`. |
| `backend/app/engines/weekly_csp.py` | Google Antigravity | Implementing Module 2: Google OR-Tools CP-SAT weekly course scheduling solver (hard capacity/LAB/instructor/$C_{\text{DAG}}$ constraints, soft student idle-gap minimization, and Turkish Unsat Core assumption diagnostics). | Verified by `backend/tests/test_step3_csp_engines.py`. |
| `backend/app/engines/exam_proctor_csp.py` | Google Antigravity | Implementing Module 3: Google OR-Tools CP-SAT exam timetabling (zero student clash), multi-room partitioning under the 1-empty-seat rule, 2D odd-column seating grid generation, and Minimax TA proctor workload balancing. | Verified by `test_module3_exam_seating_1_empty_seat_and_minimax_proctors`. |
| `backend/app/services/export_service.py`, `backend/app/services/import_service.py` | Google Antigravity | Implementing `OpenPyXL` Excel schedule export, `ReportLab` official exam/seating/proctor PDF generation, and Pydantic v2 row-validated Excel import. | Verified by `backend/tests/test_step4_exports.py`. |
| `backend/app/main.py` | Google Antigravity | Wiring FastAPI REST endpoints, lifespan auto-seeding, CORS middleware, and structured HTTP error handling (`400`, `404`, `422`). | Verified across all 14 integration tests. |
| `frontend/src/App.tsx`, `frontend/src/api.ts`, `frontend/src/pages/*.tsx` | Google Antigravity | Building the React 18 + TypeScript + Tailwind CSS interactive UI for Curriculum DAG & Failure Simulation, Weekly CP-SAT Timetable, and Exam 1-Empty-Seat Grid & Proctor Workload visualization. | Verified by `tsc -b && vite build` (0 TypeScript errors). |
| `backend/tests/test_step1_foundation.py` .. `test_step4_exports.py` | Google Antigravity | Authoring 14 automated unit and integration tests covering all hard/soft constraints, cycle detection, KVKK compliance, and file exports/imports. | Executed via `pytest backend/tests -v` (`14 passed`). |

# Academic Path & Schedule Optimizer (APSO)

> **Adana Alparslan Türkeş Science and Technology University (ATÜ)**  
> **Faculty of Computer and Informatics — Department of Software Engineering**  
> **Software Graduation Project (2026–2027)**  
> **Student:** Metin Ak (`220602047`)  
> **Supervisor:** Asst. Prof. Dr. Havva Esin ÜNAL  

---

## One-Sentence Problem Statement

To eliminate the time loss and scheduling conflict issues caused by managing curriculum dependencies (prerequisites), weekly course timetabling, and exam/proctor allocations manually via Excel in a disconnected manner without constraint optimization.

---

## Unified System Architecture (3 Core Modules)

1. **Curriculum Graph Engine (DAG Engine — Prerequisite & Path Analysis):**
   - Models the departmental curriculum as a Directed Acyclic Graph (DAG).
   - Simulates graduation risks and prerequisite chains (*Critical Path Analysis*) for students and academic advisors in the event of failing a course.
   - Directly identifies which courses must strictly not conflict within the same semester (prerequisite, co-requisite, and irregular retake sets) and feeds them into the scheduling engine.

2. **Course Scheduling Engine (Weekly Schedule CSP):**
   - Takes non-conflict rules from the curriculum engine, instructor availabilities, class enrollments, and lecture hall capacities as inputs.
   - Automatically calculates the weekly course timetable using **Google OR-Tools (CP-SAT)** under hard constraints (zero conflicts, no capacity overflows) and soft constraints (minimizing student daily idle gaps, balancing instructor preferences).

3. **Exam & Proctor Allocation Module (Exam & Proctor CSP):**
   - Automatically generates midterm and final exam schedules based on the course timetable and enrolled student lists.
   - Prevents student exam clashes, generates 2D classroom seating plans enforcing the **1-empty-seat spacing rule**, and equitably distributes proctoring workloads among teaching assistants (TAs).

---

## Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Backend API** | Python 3.12 + FastAPI |
| **Constraint Optimization Solver** | Google OR-Tools (CP-SAT) |
| **Curriculum Graph Analysis** | NetworkX + Custom DAG Critical Path Analyzer |
| **Database & ORM** | PostgreSQL 16 + SQLAlchemy 2.0 |
| **Frontend Client** | React 18 + TypeScript + Tailwind CSS |
| **Data Import / Report Export** | Pandas + OpenPyXL + ReportLab (PDF) |
| **Containerization & Testing** | Docker Compose + Pytest + GitHub Actions |

---

## Quick Setup (In 3 Commands or Fewer)

```bash
git clone https://github.com/ak-metin/academic-path-schedule-optimizer-apso.git
cd academic-path-schedule-optimizer-apso
docker compose up --build
```

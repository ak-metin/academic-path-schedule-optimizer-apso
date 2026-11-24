export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export interface SystemDatasetSummary {
  app_name: string;
  version: string;
  total_courses: number;
  total_prerequisite_edges: number;
  total_instructors: number;
  total_rooms: number;
  total_lecture_halls: number;
  total_lab_rooms: number;
  total_students: number;
  regular_students: number;
  irregular_students: number;
  total_enrollments: number;
  total_teaching_assistants: number;
}

export interface CourseGraphNodeMetric {
  course_id: number;
  code: string;
  name: string;
  semester: number;
  ects: number;
  is_mandatory: boolean;
  direct_prerequisites: string[];
  direct_dependents: string[];
  transitive_dependents: string[];
  blocking_factor: number;
  critical_path_length: number;
  critical_path_chain: string[];
}

export interface CurriculumGraphAnalysisResponse {
  is_valid_dag: boolean;
  total_nodes: number;
  total_edges: number;
  longest_critical_path_length: number;
  global_critical_path: string[];
  top_bottleneck_courses: string[];
  topological_order: string[];
  nodes: CourseGraphNodeMetric[];
}

export interface SimulatedSemesterPlan {
  simulated_term_index: number;
  semester_type: string;
  planned_courses: string[];
  retake_courses: string[];
  blocked_courses_in_this_term: string[];
  total_ects: number;
  ects_cap_applied: number;
}

export interface FailureSimulationResponse {
  current_semester: number;
  failed_course_codes: string[];
  directly_locked_courses: string[];
  transitively_locked_courses: string[];
  critical_prerequisite_chains: Record<string, string[]>;
  nominal_remaining_semesters: number;
  simulated_remaining_semesters: number;
  estimated_graduation_delay_semesters: number;
  applied_ects_cap: number;
  advisor_recommendations: string[];
  semester_by_semester_plan: SimulatedSemesterPlan[];
}

export interface WeeklySlotAssignmentRead {
  course_id: number;
  course_code: string;
  course_name: string;
  semester: number;
  room_id: number;
  room_code: string;
  room_type: string;
  room_capacity: number;
  enrolled_count: number;
  instructor_id: number | null;
  instructor_name: string;
  day_of_week: number;
  slot_index: number;
  session_type: string;
}

export interface WeeklyScheduleOptimizationResponse {
  academic_term: string;
  solver_status: string;
  solve_time_seconds: number;
  total_courses_scheduled: number;
  total_slot_assignments: number;
  hard_constraints_satisfied: boolean;
  c_dag_pairs_enforced: number;
  total_student_idle_gap_hours: number;
  total_instructor_preference_penalty: number;
  objective_value: number;
  unsat_diagnostics_tr: string[];
  assignments: WeeklySlotAssignmentRead[];
}

export interface ExamRoomProctorItem {
  room_id: number;
  room_code: string;
  room_normal_capacity: number;
  room_effective_exam_capacity: number;
  allocated_student_count: number;
  proctor_ta_id: number;
  proctor_ta_code: string;
  proctor_ta_name: string;
  duty_weight: number;
}

export interface ExamSessionRead {
  exam_session_id: number;
  course_id: number;
  course_code: string;
  course_name: string;
  semester: number;
  enrolled_count: number;
  exam_day: number;
  session_index: number;
  is_weekend_or_evening: boolean;
  duty_weight: number;
  rooms: ExamRoomProctorItem[];
}

export interface ProctorWorkloadSummaryItem {
  ta_id: number;
  ta_code: string;
  ta_name: string;
  assigned_exam_rooms_count: number;
  total_weighted_workload: number;
}

export interface ExamScheduleOptimizationResponse {
  academic_term: string;
  exam_type: string;
  solver_status: string;
  solve_time_seconds: number;
  total_exams_scheduled: number;
  total_room_allocations: number;
  total_seated_students: number;
  zero_student_clash_verified: boolean;
  one_empty_seat_rule_verified: boolean;
  min_ta_workload: number;
  max_ta_workload: number;
  workload_max_min_spread: number;
  unsat_diagnostics_tr: string[];
  exam_sessions: ExamSessionRead[];
  proctor_workloads: ProctorWorkloadSummaryItem[];
}

export interface SeatCellItem {
  student_id: number;
  student_number: string;
  student_name: string;
  room_code: string;
  seat_row: number;
  seat_col: number;
}

export interface RoomSeatingGridResponse {
  exam_session_id: number;
  course_code: string;
  course_name: string;
  exam_day: number;
  session_index: number;
  total_seated_students: number;
  one_empty_seat_verified: boolean;
  seats: SeatCellItem[];
}

export interface ExcelImportRowError {
  sheet_name: string;
  row_number: number;
  identifier: string;
  error_message_tr: string;
}

export interface ExcelImportResultResponse {
  filename: string;
  courses_created: number;
  courses_updated: number;
  rooms_created: number;
  rooms_updated: number;
  total_errors: number;
  row_errors: ExcelImportRowError[];
}


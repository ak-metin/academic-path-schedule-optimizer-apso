"""APSO SQLAlchemy 2.0 Veritabanı Modelleri Paketi."""

from app.models.academic import (
    Course,
    CoursePrerequisite,
    Enrollment,
    ExamRoomAllocation,
    ExamSeatingAssignment,
    ExamSession,
    Instructor,
    InstructorAvailability,
    ProctorAssignment,
    Room,
    Student,
    TAUnavailability,
    TeachingAssistant,
    WeeklyScheduleAssignment,
)

__all__ = [
    "Course",
    "CoursePrerequisite",
    "Enrollment",
    "ExamRoomAllocation",
    "ExamSeatingAssignment",
    "ExamSession",
    "Instructor",
    "InstructorAvailability",
    "ProctorAssignment",
    "Room",
    "Student",
    "TAUnavailability",
    "TeachingAssistant",
    "WeeklyScheduleAssignment",
]

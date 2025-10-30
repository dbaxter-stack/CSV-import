
import io
import re
import zipfile
from typing import Dict, Any, List, Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="All-in-One School Data Builder", layout="wide")
st.title("📦 All-in-One School Data Builder")
st.caption("Upload your source spreadsheets on one page, then download a single ZIP containing every output.")

# ------------------------------
# Helpers
# ------------------------------
def _read_any(file) -> pd.DataFrame:
    name = file.name.lower()
    if name.endswith(".csv"):
        return pd.read_csv(file)
    return pd.read_excel(file)

def _infer_year_from_name(name: str) -> str:
    s = name.lower()
    m = re.search(r"(yr|year)[\s\-]?(\d{1,2})", s)
    return m.group(2) if m else ""

def _split_name(name: str) -> Tuple[str, str]:
    if pd.isna(name):
        return "", ""
    s = str(name).strip()
    if "," in s:
        last, first = s.split(",", 1)
        return first.strip(), last.strip()
    parts = s.split()
    if len(parts) == 1:
        return "", parts[0]
    return " ".join(parts[:-1]), parts[-1]

def _map_rotation(v: Any) -> str:
    if pd.isna(v):
        return "WHOLE YEAR"
    s = str(v).strip()
    if not s:
        return "WHOLE YEAR"
    s_norm = re.sub(r"[;:/\s]+", ",", s)         # allow ; : / space as separators
    parts = [re.sub(r"[^0-9]", "", p) for p in s_norm.split(",") if p]
    setp = set([p for p in parts if p in {"1", "2", "3", "4"}])
    if setp == {"1", "2"}: return "SEMESTER 1"
    if setp == {"3", "4"}: return "SEMESTER 2"
    if setp == {"1"}: return "TERM 1"
    if setp == {"2"}: return "TERM 2"
    if setp == {"3"}: return "TERM 3"
    if setp == {"4"}: return "TERM 4"
    term_map = {"1": "TERM 1", "2": "TERM 2", "3": "TERM 3", "4": "TERM 4"}
    labels = [term_map.get(p, p) for p in parts]
    return ", ".join(sorted(set(labels))) if labels else "WHOLE YEAR"

def _pick(df: pd.DataFrame, candidates: List[str]):
    lower_map = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns: return c
        if c.lower() in lower_map: return lower_map[c.lower()]
    return None

# ------------------------------
# Conversions (your finalized specs)
# ------------------------------
def build_rooms(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame()
    out["RoomCode"] = df.get("Code", "")
    out["RoomName"] = df.get("Notes", "")
    cap = pd.to_numeric(df.get("Size", pd.Series([None]*len(df))), errors="coerce").fillna(0).astype(int)
    out["Capacity"] = cap
    return out[["RoomCode","RoomName","Capacity"]]

def build_teachers(df: pd.DataFrame, target_cols: List[str]) -> pd.DataFrame:
    out = pd.DataFrame(columns=target_cols)
    out.loc[:, "TeacherCode"] = df.get("Code", "")
    if "Name" in df.columns:
        first, last = zip(*df["Name"].map(_split_name))
        out.loc[:, "FirstName"] = pd.Series(first)
        out.loc[:, "LastName"] = pd.Series(last)
    out.loc[:, "FacultyCode"] = df.get("Faculty", "")
    if "HomeSpace" in out.columns: out.loc[:, "HomeSpace"] = ""
    if "LearningSupport" in out.columns: out.loc[:, "LearningSupport"] = ""
    return out

def build_students(files: List[Any], target_cols: List[str]) -> pd.DataFrame:
    frames = []
    for f in files:
        df = _read_any(f)
        yl = _infer_year_from_name(f.name)
        out = pd.DataFrame(columns=target_cols)
        out.loc[:, "StudentCode"] = df.get("Code", "")
        if "Name" in df.columns:
            first, last = zip(*df["Name"].map(_split_name))
            out.loc[:, "FirstName"] = pd.Series(first)
            out.loc[:, "LastName"] = pd.Series(last)
        letter = df.get("Letter") if "Letter" in df.columns else df.get("CoreStudentBodyCode", "")
        if "CoreStudentBodyCode" in out.columns: out.loc[:, "CoreStudentBodyCode"] = letter
        if "YearLevelCode" in out.columns: out.loc[:, "YearLevelCode"] = yl
        if "YearLevel" in out.columns: out.loc[:, "YearLevel"] = yl
        if "Curriculum" in out.columns: out.loc[:, "Curriculum"] = yl
        if "Gender" in out.columns: out.loc[:, "Gender"] = ""
        if "Email" in out.columns: out.loc[:, "Email"] = df.get("Email", "")
        frames.append(out)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=target_cols)

def build_class_memberships(files: List[Any]) -> pd.DataFrame:
    rows = []
    for f in files:
        df = _read_any(f)
        if "Code" not in df.columns: continue
        class_cols = [c for c in df.columns if re.match(r"(?i)^class\s*_?\s*\d+", str(c).replace(" ", ""))]
        if not class_cols:
            class_cols = [c for c in df.columns if str(c).strip().lower().startswith("class")]
        long = df[["Code"] + class_cols].melt(id_vars=["Code"], var_name="src", value_name="ClassCode")
        long = long[long["ClassCode"].notna() & (long["ClassCode"].astype(str).str.strip() != "")]
        long["StudentCode"] = long["Code"].astype(str)
        rows.append(long[["StudentCode","ClassCode"]])
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=["StudentCode","ClassCode"])

def build_courses(files: List[Any], target_cols: List[str]) -> pd.DataFrame:
    frames = []
    for f in files:
        df = _read_any(f)
        yr = _infer_year_from_name(f.name)
        tmp = pd.DataFrame(columns=target_cols)
        cand_course = _pick(df, ["Course","CourseCode","Course Code"])
        cand_subject = _pick(df, ["Subject","CourseName","Course Name"])
        cand_faculty = _pick(df, ["Faculty","SubjectCode","Subject Code"])
        cand_rot = _pick(df, ["Rot","Rotation","RotationSet","Rotation Set"])
        cand_line = _pick(df, ["Line","Type"])
        tmp.loc[:, "CourseCode"] = df[cand_course].astype(str) if cand_course else ""
        tmp.loc[:, "CourseName"] = df[cand_subject].astype(str) if cand_subject else ""
        tmp.loc[:, "CurriculumName"] = yr
        tmp.loc[:, "SubjectCode"] = df[cand_faculty].astype(str) if cand_faculty else ""
        tmp.loc[:, "RotationSet"] = (df[cand_rot] if cand_rot else pd.Series([None]*len(df))).map(_map_rotation)
        tmp.loc[:, "Type"] = (df[cand_line] if cand_line else pd.Series([None]*len(df))).map(
            lambda x: "Core" if str(x).strip().lower().startswith("group") else "Elective"
        )
        frames.append(tmp)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=target_cols)
    out = out[out["CourseCode"].astype(str).str.strip() != ""].drop_duplicates(subset=["CourseCode"], keep="first")
    return out[target_cols]

def build_classes_and_lessons(df: pd.DataFrame, courses_df: pd.DataFrame) -> pd.DataFrame:
    target_cols = ["PeriodCode","CourseCode","ClassIdentifier","TeacherCode","RoomCode","Rotation"]
    out = pd.DataFrame(columns=target_cols)
    cday = _pick(df, ["Day","DAY","day","DayName"])
    cper = _pick(df, ["Period","PERIOD","period","Per"])
    out.loc[:, "PeriodCode"] = (df.get(cday, "").astype(str).str.strip() + df.get(cper, "").astype(str).str.strip()) if cday and cper else ""
    cclass = _pick(df, ["Class","ClassCode","Class Code","ClassIdentifier","Class Identifier"])
    cteach = _pick(df, ["TeacherCode","Teacher Code","Teacher","StaffCode","Staff Code","Staff"])
    croom = _pick(df, ["RoomCode","Room Code","Room","Rm","RM"])
    crot = _pick(df, ["Rotation","Rot","RotationSet","Rotation Set"])
    codes = sorted([str(x).strip() for x in courses_df.get("CourseCode", pd.Series(dtype=str)).dropna() if str(x).strip()], key=len, reverse=True)
    def split_class(val: Any) -> Tuple[str, str]:
        s = str(val) if pd.notna(val) else ""
        for code in codes:
            if s.startswith(code):
                rem = s[len(code):]
                rem = re.sub(r"^[\s\-\._/]+", "", rem)
                return code, rem
        return "", s
    if cclass:
        cc, ident = zip(*df[cclass].map(split_class))
        out.loc[:, "CourseCode"] = pd.Series(cc, dtype=str)
        out.loc[:, "ClassIdentifier"] = pd.Series(ident, dtype=str)
    else:
        out.loc[:, "CourseCode"] = ""
        out.loc[:, "ClassIdentifier"] = ""
    out.loc[:, "TeacherCode"] = df.get(cteach, "")
    out.loc[:, "RoomCode"] = df.get(croom, "")
    rot_lookup = courses_df.set_index("CourseCode").get("RotationSet", pd.Series(dtype=str))
    out.loc[:, "Rotation"] = out["CourseCode"].map(rot_lookup).fillna(df.get(crot, ""))
    return out[target_cols]

# ------------------------------
# Upload UI (single page)
# ------------------------------
st.subheader("1) Upload sources")
col1, col2 = st.columns(2)
with col1:
    f_room = st.file_uploader("Room spreadsheet", type=["csv","xlsx","xls"], key="rooms")
    f_teacher = st.file_uploader("Teacher spreadsheet", type=["csv","xlsx","xls"], key="teachers")
    f_subjects = st.file_uploader("Subject CSV (static)", type=["csv"], key="subjects")
with col2:
    f_students = st.file_uploader("Student spreadsheets (multi)", type=["csv","xlsx","xls"], accept_multiple_files=True, key="students")
    f_courses = st.file_uploader("ClassData (Courses) — multi", type=["csv","xlsx","xls"], accept_multiple_files=True, key="courses")
    f_classes = st.file_uploader("Classes & Lessons spreadsheet", type=["csv","xlsx","xls"], key="classes")

st.subheader("2) Build outputs & download ZIP")
if st.button("🧰 Build all files"):
    outputs: Dict[str, bytes] = {}

    # Rooms
    if f_room is not None:
        df_room = _read_any(f_room)
        rooms = build_rooms(df_room)
        outputs["ROOM.csv"] = rooms.to_csv(index=False).encode("utf-8")
        st.success(f"ROOM.csv ✓ ({len(rooms)} rows)")

    # Teachers
    if f_teacher is not None:
        df_teacher = _read_any(f_teacher)
        teacher_cols = ["TeacherCode","FirstName","LastName","FacultyCode","HomeSpace","LearningSupport"]
        teachers = build_teachers(df_teacher, teacher_cols)
        outputs["Teacher.csv"] = teachers.to_csv(index=False).encode("utf-8")
        st.success(f"Teacher.csv ✓ ({len(teachers)} rows)")

    # Courses (must be ready before Classes & Lessons)
    courses_df = pd.DataFrame(columns=["CourseCode","CourseName","CurriculumName","SubjectCode","Type","RotationSet"])
    if f_courses:
        courses_df = build_courses(f_courses, list(courses_df.columns))
        outputs["COURSES.csv"] = courses_df.to_csv(index=False).encode("utf-8")
        st.success(f"COURSES.csv ✓ ({len(courses_df)} rows)")

    # Students + Class Memberships from same uploads
    if f_students:
        student_cols = [
            "StudentCode","FirstName","LastName","CoreStudentBodyCode","YearLevelCode","YearLevel","Curriculum","Gender","Email"
        ]
        students = build_students(f_students, student_cols)
        outputs["Student.csv"] = students.to_csv(index=False).encode("utf-8")
        st.success(f"Student.csv ✓ ({len(students)} rows)")

        memberships = build_class_memberships(f_students)
        outputs["ClassMemberships.csv"] = memberships.to_csv(index=False).encode("utf-8")
        st.success(f"ClassMemberships.csv ✓ ({len(memberships)} rows)")

    # Classes & Lessons (requires courses for rotation lookup)
    if f_classes is not None:
        df_classes = _read_any(f_classes)
        classes_out = build_classes_and_lessons(df_classes, courses_df)
        outputs["ClassesAndLessons.csv"] = classes_out.to_csv(index=False).encode("utf-8")
        st.success(f"ClassesAndLessons.csv ✓ ({len(classes_out)} rows)")

    # Subjects (static include)
    if f_subjects is not None:
        outputs["SUBJECT.csv"] = f_subjects.read()
        st.success("SUBJECT.csv ✓ (included as-is)")

    if not outputs:
        st.warning("Please upload at least one source file.")
    else:
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for name, data in outputs.items():
                zf.writestr(name, data)
        st.download_button(
            "⬇️ Download all as ZIP",
            data=zip_buf.getvalue(),
            file_name="school-data-bundle.zip",
            mime="application/zip",
        )

st.caption("Single-page app: upload everything once and download a ZIP of ROOM, Teacher, Student, ClassMemberships, SUBJECT, COURSES, and ClassesAndLessons outputs.")
